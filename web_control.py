"""
Unified web control panel for the NextRobot Wok + Lingzu Dual Arm.
NextRobot 炒锅 + 灵心双臂 统一网页控制台。

Dependency-free: Python stdlib http.server backend (no Flask/NiceGUI/requests).
- Dual arm / hands / gripper: drives the local controllers directly.
- Wok: talks to the NextRobot cloud API over urllib.

Run (with the project venv so the lbot SDK + controllers import):
    .venv/bin/python web_control.py
Then open  http://<this-pc-ip>:8090  from any device on the same network.

NOTE: this OWNS the dual-arm hardware (arm/CAN/serial). Do NOT run it at the
same time as the PyQt app (lingzu_main.py) — only one process can hold the arm.
"""
from __future__ import annotations

import json
import os
import signal
import ssl
import threading
import time
import urllib.request
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app_core.logger import get_logger
from hardware.dual_arm.dual_arm_controller import DualArmController, ArmSide
from hardware.dual_arm.linker_hand_controller import LinkerHandController, HandSide
from hardware.gripper.gripper_controller import GripperController
from hardware.dual_arm.poses import DualArmPoseManager
from hardware.dual_arm.pose_control_widget import RecordedPose

logger = get_logger("web_control")

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8090

# ──────────────────────────────────────────────────────────────────────────
# Hardware singletons (this process owns the hardware while running)
# ──────────────────────────────────────────────────────────────────────────
ARM = DualArmController()
HAND = LinkerHandController()
GRIP = GripperController()
POSES = DualArmPoseManager()

_exec_stop = threading.Event()      # aborts a running pose-step execution
_exec_thread: threading.Thread | None = None
_last_grip_cmd = None               # change-tracking for end-effector settle waits
_last_hand_cmd: dict = {}


# ──────────────────────────────────────────────────────────────────────────
# Wok cloud client (urllib; mirrors nextrobot_client without the requests dep)
# ──────────────────────────────────────────────────────────────────────────
class WokClient:
    API_HOST = "https://api.nextrobot.com"
    CLIENT_ID = "77a1d8c4d8a78d04e9079a8e4e1d9e98"
    CLIENT_SECRET = "851d6270c044997caca400aa354b8a5816b4162613524955da4ae00ecec4df7f"
    RESTAURANT_ID = "e1e7e06a-61d2-47ea-89df-b345f6fa4c9a"

    def __init__(self, language: str = "en", timeout: float = 30.0):
        self.language = language
        self.timeout = timeout
        self._token: str | None = None
        self._ctx = ssl.create_default_context()

    def _req(self, method, path, body=None, params=None, auth=True):
        url = self.API_HOST + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        headers = {"Content-Type": "application/json", "Language": self.language}
        if auth:
            headers["Authorization"] = f"Bearer {self.get_token()}"
            headers["NextRobot-Restaurant-External-ID"] = self.RESTAURANT_ID
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=self.timeout, context=self._ctx) as resp:
            raw = resp.read().decode("utf-8", "ignore")
        return json.loads(raw) if raw else {}

    def get_token(self) -> str:
        if self._token:
            return self._token
        data = self._req("POST", "/integration/v1/authentication/login", auth=False, body={
            "clientId": self.CLIENT_ID, "clientSecret": self.CLIENT_SECRET,
            "userAccessType": "NEXTROBOT_MACHINE_CLIENT",
        })
        tok = self._extract_token(data)
        if not tok:
            raise RuntimeError(f"No token in login response: {data}")
        self._token = tok
        return tok

    @staticmethod
    def _extract_token(d):
        if not isinstance(d, dict):
            return None
        for k in ("token", "accessToken", "access_token"):
            if isinstance(d.get(k), str):
                return d[k]
        return WokClient._extract_token(d.get("data")) if isinstance(d.get("data"), dict) else None

    def get_robots(self):
        return self._req("GET", "/integration/v1/humanoid/robots")

    def get_seasonings(self, robot_type="robby"):
        return self._req("GET", "/integration/v1/humanoid/seasonings", params={"robotType": robot_type})

    def get_command_status(self, cid):
        return self._req("GET", f"/integration/v1/humanoid/commands/{cid}")

    def send_command(self, sn, action_name, payload=None):
        body = {"sn": sn, "actionName": action_name}
        if payload is not None:
            body["payload"] = payload
        return self._req("POST", "/integration/v1/humanoid/commands", body=body)


WOK = WokClient()
WOK_ROBOT: dict = {}     # the connected robot (sn, name, robotType …)
WOK_SEASONINGS: list = []


# ──────────────────────────────────────────────────────────────────────────
# Dual-arm pose-step replay (smooth) — mirrors the GUI's smooth pipeline
# ──────────────────────────────────────────────────────────────────────────
def _pose_to_waypoint(p):
    if getattr(p, "pose_type", "") == "hand_only":
        return {"left": None, "right": None}
    if p.arm == "both":
        return {"left": list(p.joints) if p.joints else None,
                "right": list(p.right_joints) if p.right_joints else None}
    if p.arm == "left":
        return {"left": list(p.joints) if p.joints else None, "right": None}
    return {"left": None, "right": list(p.joints) if p.joints else None}


def _apply_pose_end_effectors(p):
    try:
        if HAND and HAND.is_ready():
            if p.arm == "both":
                if p.hand_positions:
                    HAND.set_finger_positions(HandSide.LEFT, [float(x) for x in p.hand_positions])
                if p.right_hand_positions:
                    HAND.set_finger_positions(HandSide.RIGHT, [float(x) for x in p.right_hand_positions])
            elif p.arm == "left" and p.hand_positions:
                HAND.set_finger_positions(HandSide.LEFT, [float(x) for x in p.hand_positions])
            elif p.arm == "right" and p.hand_positions:
                HAND.set_finger_positions(HandSide.RIGHT, [float(x) for x in p.hand_positions])
        if p.arm in ("both", "right") and p.gripper_position is not None and GRIP and GRIP.is_ready():
            GRIP.set_opening(int(p.gripper_position))
    except Exception as e:
        logger.debug("apply end-effectors failed: %s", e)


def _wait_end_effectors_settled(pose, grip_timeout=1.5, hand_timeout=0.8):
    """Wait for the gripper/hand to reach target — only when their command changed
    (so unchanged poses don't stall), capped by a short timeout, interruptible by stop."""
    global _last_grip_cmd
    # Gripper (right / both poses)
    if (getattr(pose, "arm", "") in ("both", "right") and pose.gripper_position is not None
            and GRIP and GRIP.is_ready()):
        target = int(pose.gripper_position)
        if target != _last_grip_cmd:
            _last_grip_cmd = target
            deadline = time.monotonic() + grip_timeout
            while not _exec_stop.is_set() and time.monotonic() < deadline:
                try:
                    if abs(GRIP.get_position() - target) <= 4:
                        break
                except Exception:
                    break
                _exec_stop.wait(0.05)
    # Hand fingers (per side)
    if HAND and HAND.is_ready():
        targets = []
        if pose.arm == "both":
            if pose.hand_positions:
                targets.append(("left", [float(x) for x in pose.hand_positions]))
            if pose.right_hand_positions:
                targets.append(("right", [float(x) for x in pose.right_hand_positions]))
        elif pose.arm == "left":
            if pose.hand_positions:
                targets.append(("left", [float(x) for x in pose.hand_positions]))
        else:
            if pose.hand_positions:
                targets.append(("right", [float(x) for x in pose.hand_positions]))
        for side, tgt in targets:
            if _last_hand_cmd.get(side) == tgt:
                continue
            _last_hand_cmd[side] = list(tgt)
            deadline = time.monotonic() + hand_timeout
            while not _exec_stop.is_set() and time.monotonic() < deadline:
                try:
                    real = HAND.get_finger_positions_real(side)
                except Exception:
                    break
                if real and all(abs(a - b) <= 15 for a, b in zip(real, tgt)):
                    break
                _exec_stop.wait(0.05)


def run_step_smooth(poses, speed, effort_limit):
    global _last_grip_cmd, _last_hand_cmd
    _last_grip_cmd = None        # reset change-tracking so the first grasp is waited on
    _last_hand_cmd = {}
    waypoints = [_pose_to_waypoint(p) for p in poses]

    def on_wp(idx):
        _apply_pose_end_effectors(poses[idx])
        # Wait for the gripper/hand to finish before the arm moves on.
        _wait_end_effectors_settled(poses[idx])

    prev = ARM._speed_factor
    ARM._speed_factor = speed
    try:
        ARM.smooth_replay(waypoints, speed_factor=speed, stop_event=_exec_stop,
                          on_waypoint=on_wp, effort_limit=effort_limit, hold_timeout=10.0)
    finally:
        ARM._speed_factor = prev


def run_step_blocking(poses, speed, delay):
    """Non-smooth replay: blocking move to each pose, pausing `delay` s between poses."""
    for i, p in enumerate(poses):
        if _exec_stop.is_set():
            return
        _apply_pose_end_effectors(p)
        if getattr(p, "pose_type", "") != "hand_only":
            try:
                if p.arm == "both" and p.joints and p.right_joints:
                    ARM.move_both_arms(list(p.joints), list(p.right_joints), speed=speed)
                elif p.arm == "left" and p.joints:
                    ARM.move_left_joints(list(p.joints), speed=speed)
                elif p.arm == "right" and p.joints:
                    ARM.move_right_joints(list(p.joints), speed=speed)
            except Exception as e:
                logger.error("blocking move failed: %s", e)
        if i < len(poses) - 1 and delay > 0:
            _exec_stop.wait(delay)


def _find_step(name):
    for s in POSES._steps:
        if (s.name or "").strip().lower() == (name or "").strip().lower():
            return s
    return None


def _load_initial_pose():
    """Load the dedicated startup poses from config/initial_pose.json (protected copy)."""
    path = os.path.join(HERE, "config", "initial_pose.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return [RecordedPose.from_dict(p) for p in data.get("poses", [])] or None
    except Exception as e:
        logger.warning("Failed to load initial pose: %s", e)
        return None


def _run_init_sequence(effort_limit=3.5):
    """Enable both arms -> ease to zero -> run the initial pose (smooth)."""
    try:
        logger.info("Web init: enabling both arms")
        ARM.enable_arm(ArmSide.LEFT, True)
        ARM.enable_arm(ArmSide.RIGHT, True)
        if _exec_stop.wait(1.5):
            return
        logger.info("Web init: easing to zero")
        ARM.smooth_replay([{"left": [0.0] * 7, "right": [0.0] * 7}],
                          speed_factor=0.5, stop_event=_exec_stop,
                          effort_limit=effort_limit, hold_timeout=10.0)
        if _exec_stop.is_set():
            return
        poses = _load_initial_pose()
        if not poses:
            logger.warning("Web init: no initial pose available; done after zero")
            return
        logger.info("Web init: running initial pose (%d poses) at speed 1.5", len(poses))
        run_step_smooth(poses, 1.5, effort_limit)
        logger.info("Web init: sequence complete")
    except Exception as e:
        logger.exception("Web init sequence failed: %s", e)


# ──────────────────────────────────────────────────────────────────────────
# API endpoint handlers — each returns a JSON-able dict
# ──────────────────────────────────────────────────────────────────────────
def _arm_busy() -> bool:
    return _exec_thread is not None and _exec_thread.is_alive()


def api_status(_):
    """Aggregate live status of all components."""
    def safe(fn, default=None):
        try:
            return fn()
        except Exception:
            return default
    return {
        "arm": {
            "connected": bool(safe(ARM.is_ready, False)),
            "ip": getattr(ARM, "_ip", ""),
            "left_enabled": bool(getattr(ARM, "_left_enabled", False)),
            "right_enabled": bool(getattr(ARM, "_right_enabled", False)),
            "moving": bool(getattr(ARM, "_is_moving", False)) or _arm_busy(),
            "left_joints": [round(x, 3) for x in safe(ARM.get_left_joints, []) or []],
            "right_joints": [round(x, 3) for x in safe(ARM.get_right_joints, []) or []],
            "torque": round((safe(ARM.get_effort_status, {}) or {}).get("max", 0.0), 2),
        },
        "hand": {
            "left": bool(safe(lambda: HAND.is_hand_connected("left"), False)),
            "right": bool(safe(lambda: HAND.is_hand_connected("right"), False)),
        },
        "gripper": {
            "connected": bool(safe(GRIP.is_ready, False)),
            "opening": safe(GRIP.get_position, None),
        },
        "wok": {
            "connected": bool(WOK_ROBOT),
            "name": WOK_ROBOT.get("name") if WOK_ROBOT else None,
            "sn": WOK_ROBOT.get("sn") if WOK_ROBOT else None,
        },
        "executing": _arm_busy(),
    }


def api_arm_connect(_):
    def _connect_all():
        try:
            ARM.connect()
        except Exception as e:
            logger.warning("arm connect failed: %s", e)
        # Best-effort: also bring up the hands and gripper on the same action.
        try:
            HAND.connect()
        except Exception as e:
            logger.debug("hand connect failed: %s", e)
        try:
            GRIP.connect()
        except Exception as e:
            logger.debug("gripper connect failed: %s", e)
    threading.Thread(target=_connect_all, daemon=True).start()
    return {"ok": True, "msg": "connecting"}


def api_arm_disconnect(_):
    ARM.disconnect()
    return {"ok": True}


def api_arm_enable(body):
    side = ArmSide.LEFT if body.get("side") == "left" else ArmSide.RIGHT
    enable = bool(body.get("enable", True))
    ok = ARM.enable_arm(side, enable)
    return {"ok": bool(ok)}


def api_arm_zero(_):
    if not ARM.is_ready():
        return {"ok": False, "msg": "arm not connected"}
    if _arm_busy():
        return {"ok": False, "msg": "busy"}
    _exec_stop.clear()
    global _exec_thread
    _exec_thread = threading.Thread(
        target=lambda: ARM.smooth_replay(
            [{"left": [0.0] * 7, "right": [0.0] * 7}], speed_factor=0.5,
            stop_event=_exec_stop), daemon=True)
    _exec_thread.start()
    return {"ok": True}


def api_test_pose(_):
    """Run the 'test_pose' step non-smoothly: speed 0.5, no contact limit, 0.5s delay."""
    if not ARM.is_ready():
        return {"ok": False, "msg": "arm not connected"}
    if _arm_busy():
        return {"ok": False, "msg": "busy"}
    step = _find_step("test_pose")
    if not step or not step.poses:
        return {"ok": False, "msg": "test_pose step not found"}
    _exec_stop.clear()
    global _exec_thread
    _exec_thread = threading.Thread(
        target=lambda: run_step_blocking(list(step.poses), 0.5, 0.5), daemon=True)
    _exec_thread.start()
    return {"ok": True, "poses": len(step.poses)}


def api_arm_init(_):
    if not ARM.is_ready():
        return {"ok": False, "msg": "arm not connected"}
    if _arm_busy():
        return {"ok": False, "msg": "busy"}
    _exec_stop.clear()
    global _exec_thread
    _exec_thread = threading.Thread(target=_run_init_sequence, daemon=True)
    _exec_thread.start()
    return {"ok": True}


def api_arm_stop(_):
    _exec_stop.set()
    return {"ok": True}


def api_steps(_):
    return {"steps": POSES.list_steps()}


def api_run_step(body):
    if not ARM.is_ready():
        return {"ok": False, "msg": "arm not connected"}
    if _arm_busy():
        return {"ok": False, "msg": "busy"}
    step = _find_step(body.get("name", ""))
    if not step or not step.poses:
        return {"ok": False, "msg": "step not found / empty"}
    speed = float(body.get("speed", 0.5))
    effort_limit = body.get("effort_limit") or None
    if effort_limit:
        effort_limit = float(effort_limit)
    _exec_stop.clear()
    global _exec_thread
    _exec_thread = threading.Thread(
        target=run_step_smooth, args=(list(step.poses), speed, effort_limit), daemon=True)
    _exec_thread.start()
    return {"ok": True, "poses": len(step.poses)}


def api_hand_connect(body):
    side = body.get("side")
    if side in ("left", "right"):
        ok = HAND.connect_hand(side)
    else:
        ok = HAND.connect()
    return {"ok": bool(ok)}


def api_hand_set(body):
    """Set all fingers of a side to one value (0=closed .. 255=open)."""
    side = HandSide.LEFT if body.get("side") == "left" else HandSide.RIGHT
    val = int(body.get("value", 255))
    ok = HAND.set_finger_positions(side, [float(val)] * 6)
    return {"ok": bool(ok)}


def api_gripper_connect(_):
    threading.Thread(target=GRIP.connect, daemon=True).start()
    return {"ok": True, "msg": "connecting"}


def api_gripper_set(body):
    ok = GRIP.set_opening(int(body.get("opening", 100)))
    return {"ok": bool(ok)}


# ---- Wok endpoints ----
def api_wok_connect(body):
    global WOK_ROBOT, WOK_SEASONINGS, WOK
    WOK.language = body.get("language", "en")
    WOK.get_token()
    robots = WOK.get_robots()
    rlist = robots.get("robots", []) if isinstance(robots, dict) else []
    if not rlist:
        return {"ok": False, "msg": "no robots"}
    WOK_ROBOT = rlist[0]
    try:
        s = WOK.get_seasonings(WOK_ROBOT.get("robotType", "robby"))
        WOK_SEASONINGS = s.get("seasonings", []) if isinstance(s, dict) else []
    except Exception:
        WOK_SEASONINGS = []
    return {"ok": True, "robot": WOK_ROBOT, "seasonings": WOK_SEASONINGS}


def api_wok_seasonings(_):
    return {"seasonings": WOK_SEASONINGS}


def api_wok_action(body):
    if not WOK_ROBOT:
        return {"ok": False, "msg": "wok not connected"}
    resp = WOK.send_command(WOK_ROBOT.get("sn"), body["action"], body.get("payload"))
    return {"ok": True, "resp": resp}


def api_wok_command(body):
    cid = body.get("id")
    return {"resp": WOK.get_command_status(cid)}


ROUTES = {
    "/api/status": api_status,
    "/api/arm/connect": api_arm_connect,
    "/api/arm/disconnect": api_arm_disconnect,
    "/api/arm/enable": api_arm_enable,
    "/api/arm/zero": api_arm_zero,
    "/api/arm/init": api_arm_init,
    "/api/arm/test_pose": api_test_pose,
    "/api/arm/stop": api_arm_stop,
    "/api/arm/steps": api_steps,
    "/api/arm/run_step": api_run_step,
    "/api/hand/connect": api_hand_connect,
    "/api/hand/set": api_hand_set,
    "/api/gripper/connect": api_gripper_connect,
    "/api/gripper/set": api_gripper_set,
    "/api/wok/connect": api_wok_connect,
    "/api/wok/seasonings": api_wok_seasonings,
    "/api/wok/action": api_wok_action,
    "/api/wok/command": api_wok_command,
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, filename="web_control_ui.html"):
        path = os.path.join(HERE, filename)
        try:
            with open(path, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def do_GET(self):
        route = self.path.split("?")[0]
        if route in ("/", "/index.html"):
            return self._send_html("web_control_ui.html")
        fn = ROUTES.get(route)
        if fn:
            try:
                return self._send_json(fn({}))
            except Exception as e:
                logger.exception("GET %s failed", route)
                return self._send_json({"ok": False, "error": str(e)}, 500)
        self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        route = self.path.split("?")[0]
        fn = ROUTES.get(route)
        if not fn:
            return self._send_json({"error": "not found"}, 404)
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length).decode() or "{}") if length else {}
            return self._send_json(fn(body))
        except Exception as e:
            logger.exception("POST %s failed", route)
            return self._send_json({"ok": False, "error": str(e)}, 500)


def _graceful_shutdown():
    """On Ctrl+C: ease the arms to zero (contact limit on, hold+resume), then disable."""
    try:
        if not (ARM and ARM.is_ready()):
            return
        # Stop any running step and let it yield before we take over.
        _exec_stop.set()
        if _exec_thread and _exec_thread.is_alive():
            _exec_thread.join(timeout=3.0)
        _exec_stop.clear()
        logger.info("Shutdown: easing arms to zero (contact limit on)…")
        ARM.smooth_replay([{"left": [0.0] * 7, "right": [0.0] * 7}],
                          speed_factor=0.4, stop_event=_exec_stop,
                          effort_limit=3.5, hold_timeout=None)
        ARM.enable_arm(ArmSide.LEFT, False)
        ARM.enable_arm(ArmSide.RIGHT, False)
        logger.info("Shutdown: arms disabled.")
    except Exception as e:
        logger.warning("Graceful shutdown error: %s", e)


def main():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    logger.info("Web control panel on http://0.0.0.0:%d  (open from any device on the LAN)", PORT)
    print(f"\n  Web control panel:  http://localhost:{PORT}\n")

    # First Ctrl+C: gracefully ease arms to zero (contact-aware) and disable, then quit.
    # Second Ctrl+C: force-stop immediately.
    sigint = {"n": 0}

    def _sigint(signum, frame):
        sigint["n"] += 1
        if sigint["n"] == 1:
            print("\n  Ctrl+C: easing arms to zero & disabling… "
                  "(press Ctrl+C again to force-stop)")

            def _go():
                _graceful_shutdown()
                server.shutdown()
            threading.Thread(target=_go, daemon=True).start()
        else:
            print("\n  Force stop.")
            _exec_stop.set()      # abort the in-progress graceful move
            os._exit(130)
    signal.signal(signal.SIGINT, _sigint)

    try:
        server.serve_forever()
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
