"""
Dual Arm Controller Module
双臂控制器模块

Controls the dual-arm robot system via lbot API v1.0.1.
通过lbot API v1.0.1控制双臂机器人系统。
"""

import math
import os
import sys
import threading
import time
from typing import Dict, Any, Optional, List
from enum import Enum

from hardware.base_hardware import BaseHardwareController, HardwareState
from config.settings import get_settings
from app_core.logger import get_logger
from app_core.remote_control import remote_callable

logger = get_logger(__name__)

# Add lbot Python SDK to sys.path
_lbot_sdk_path = os.path.join(
    os.path.dirname(__file__), '..', '..', 'libs', 'api_lk73_v1.0.1', 'Python'
)
if os.path.isdir(_lbot_sdk_path) and os.path.abspath(_lbot_sdk_path) not in sys.path:
    sys.path.insert(0, os.path.abspath(_lbot_sdk_path))

# Try to import lbot API
_lbot_available = False
_api = None
_LbotArm = None
_LbotFullState = None
_LbotPosition = None
_LbotEuler = None
try:
    from lbot.lbot_api import api, LbotArm, LbotFullState, LbotPosition, LbotEuler
    _api = api
    _LbotArm = LbotArm
    _LbotFullState = LbotFullState
    _LbotPosition = LbotPosition
    _LbotEuler = LbotEuler
    _lbot_available = True
except ImportError as e:
    logger.warning(f"lbot SDK not available: {e}")


# Max per-joint angular speed (rad/s) at speed_factor=1.0, used to time the
# segments of smooth (joint_follow-streamed) replay. Kept conservative for safety.
_SMOOTH_MAX_JOINT_SPEED = 1.2


def _cr_knots(points: List[List[float]], alpha: float = 0.5) -> List[float]:
    """Centripetal Catmull-Rom knot sequence for a list of joint vectors.

    Knot spacing is the Euclidean distance between consecutive points raised to
    `alpha` (0.5 = centripetal), which prevents the cusps/overshoot that uniform
    Catmull-Rom can produce on unevenly spaced waypoints. Distances are floored
    to a small epsilon so coincident points don't create zero-width intervals.
    """
    t = [0.0]
    for i in range(1, len(points)):
        d = math.sqrt(sum((points[i][j] - points[i - 1][j]) ** 2
                          for j in range(len(points[i]))))
        t.append(t[-1] + max(d, 1e-6) ** alpha)
    return t


def _cr_tangents(points: List[List[float]], knots: List[float]) -> List[List[float]]:
    """Non-uniform Catmull-Rom tangents (dP/dt) at each control point.

    Endpoints get a zero tangent so the whole replay eases in and out (starts and
    ends at rest); interior tangents use the standard non-uniform CR formula.
    """
    n = len(points)
    dim = len(points[0])
    tangents: List[List[float]] = []
    for k in range(n):
        if k == 0 or k == n - 1:
            tangents.append([0.0] * dim)
            continue
        d_prev = knots[k] - knots[k - 1]
        d_next = knots[k + 1] - knots[k]
        d_span = knots[k + 1] - knots[k - 1]
        m = [
            (points[k + 1][j] - points[k][j]) / d_next
            - (points[k + 1][j] - points[k - 1][j]) / d_span
            + (points[k][j] - points[k - 1][j]) / d_prev
            for j in range(dim)
        ]
        tangents.append(m)
    return tangents


def _hermite(p0: List[float], p1: List[float],
             m0: List[float], m1: List[float], s: float) -> List[float]:
    """Cubic Hermite interpolation at s in [0,1]. m0/m1 are tangents already
    scaled to this segment's parameter interval."""
    s2 = s * s
    s3 = s2 * s
    h00 = 2 * s3 - 3 * s2 + 1
    h10 = s3 - 2 * s2 + s
    h01 = -2 * s3 + 3 * s2
    h11 = s3 - s2
    return [h00 * p0[j] + h10 * m0[j] + h01 * p1[j] + h11 * m1[j]
            for j in range(len(p0))]


# Per-joint limits in RADIANS, converted from WorkspaceValidator.DEFAULT_JOINT_LIMITS
# (which are degrees). Streamed joint targets are in radians, so we convert here.
_JOINT_LIMITS_RAD = [
    (math.radians(lo), math.radians(hi)) for (lo, hi) in (
        (-170, 170), (-120, 120), (-170, 170), (-120, 120),
        (-170, 170), (-120, 120), (-360, 360),
    )
]
# Within this distance (rad) of a limit, while heading toward it, motion is scaled
# down so the arm eases up to the boundary instead of slamming into it.
_LIMIT_MARGIN_RAD = math.radians(10.0)


def _clamp_to_limits(q: List[float]) -> List[float]:
    """Hard-clamp a joint vector to the configured limits (safety net)."""
    return [max(lo, min(hi, v)) for v, (lo, hi) in zip(q, _JOINT_LIMITS_RAD)]


def _limit_scale(q: List[float], direction: List[int],
                 margin: float = _LIMIT_MARGIN_RAD) -> float:
    """Velocity scale in [0,1] from joint-limit proximity.

    Only throttles joints that are moving *toward* their nearer limit and are
    within `margin` of it; returns the most restrictive (smallest) scale.
    """
    scale = 1.0
    for j, (lo, hi) in enumerate(_JOINT_LIMITS_RAD):
        d = direction[j]
        if d > 0:
            dist = hi - q[j]
        elif d < 0:
            dist = q[j] - lo
        else:
            continue
        if dist < margin:
            scale = min(scale, max(0.0, dist / margin))
    return scale


class ArmSide(Enum):
    """Arm side enumeration / 手臂侧枚举"""
    LEFT = "left"
    RIGHT = "right"


def _arm_enum(side):
    """Convert ArmSide / string to LbotArm enum."""
    if isinstance(side, ArmSide):
        side = side.value
    if side == "left":
        return _LbotArm.LEFT_ARM
    return _LbotArm.RIGHT_ARM


class DualArmController(BaseHardwareController):
    """
    Dual arm robot controller.
    双臂机器人控制器。

    Uses lbot API v1.0.1 for communication with the robot.
    使用lbot API v1.0.1与机器人通信。
    """

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__("dual_arm", config)

        settings = get_settings()
        self._ip = config.get('ip') if config else settings.dual_arm.ip
        self._port = config.get('port') if config else settings.dual_arm.port
        self._speed_factor = config.get('speed_factor') if config else settings.dual_arm.speed_factor
        self._accel_factor: float = 0.5

        self._connected = False
        self._left_enabled = False
        self._right_enabled = False
        self._left_joints: List[float] = [0.0] * 7
        self._right_joints: List[float] = [0.0] * 7
        self._left_arm_state = None
        self._right_arm_state = None
        self._is_moving = False
        self._lock = threading.Lock()

        # Background state poller cache (for VLA recording)
        self._cached_state: Dict[str, Dict[str, Any]] = {"left": {}, "right": {}}
        self._cached_state_timestamp: float = 0.0
        self._state_cache_lock = threading.Lock()
        self._state_poller_thread: Optional[threading.Thread] = None
        self._state_poller_stop = threading.Event()

        self._lbot_available = _lbot_available
        if not self._lbot_available:
            logger.warning("lbot not installed, running in simulation mode")

    def connect(self) -> bool:
        """Connect to dual arm robot / 连接双臂机器人"""
        self.state = HardwareState.CONNECTING

        if not self._lbot_available:
            logger.warning("Dual arm: lbot SDK not installed, cannot connect (simulation mode)")
            self.state = HardwareState.DISCONNECTED
            return False

        try:
            logger.info(f"Connecting to dual arm at {self._ip}...")
            result = _api.init(self._ip)

            if result:
                self._connected = True

                # Start state monitor with callback
                try:
                    _api.start_state_monitor(
                        state_callback=self._on_state_update,
                        error_callback=self._on_error,
                    )
                    logger.info("State monitor started via API callback")
                except Exception as e:
                    logger.warning(f"Failed to start state monitor callback: {e}")

                # Clear any stale controller fault so motion commands are accepted.
                try:
                    if _api.clear_errors():
                        logger.info("Cleared controller errors on connect")
                except Exception as e:
                    logger.debug(f"clear_errors on connect failed: {e}")

                # Wait briefly for initial state
                for _ in range(20):
                    if self._left_arm_state is not None:
                        break
                    time.sleep(0.05)

                # Get controller info
                try:
                    success, model, version = _api.get_controller_info()
                    if success:
                        logger.info(f"Connected to {model} (version: {version})")
                except Exception:
                    pass

                self.state = HardwareState.CONNECTED
                self._update_positions()
                logger.info(f"Dual arm connected to {self._ip}")
                return True
            else:
                error_msg = _api.get_last_error()
                raise Exception(f"API init failed: {error_msg}")

        except Exception as e:
            logger.error(f"Failed to connect dual arm: {e}")
            self._set_error(str(e))
            return False

    def disconnect(self) -> bool:
        """Disconnect from dual arm robot / 断开双臂机器人连接"""
        if self._connected and self._lbot_available:
            try:
                _api.stop_state_monitor()
                _api.cleanup()
            except Exception:
                pass

        self._connected = False
        self._left_enabled = False
        self._right_enabled = False
        self._left_arm_state = None
        self._right_arm_state = None
        self.state = HardwareState.DISCONNECTED
        logger.info("Dual arm disconnected")
        return True

    def start(self) -> bool:
        """Start (enable) robot / 启动机器人"""
        if self.state != HardwareState.CONNECTED:
            return False

        if self._connected and self._lbot_available:
            try:
                _api.enable_arm(_LbotArm.LEFT_ARM, True)
                _api.enable_arm(_LbotArm.RIGHT_ARM, True)
            except Exception as e:
                logger.error(f"Failed to enable robot: {e}")
                return False

        self.state = HardwareState.RUNNING
        return True

    def enable_arm(self, side: ArmSide, enable: bool) -> bool:
        """Enable or disable a single arm / 使能或禁用单臂"""
        if not self._connected or not self._lbot_available:
            return False
        try:
            arm_enum = _arm_enum(side)
            result = _api.enable_arm(arm_enum, enable)
            if result:
                # Track commanded enable state (for status display).
                if _arm_enum(side) == _LbotArm.LEFT_ARM:
                    self._left_enabled = enable
                else:
                    self._right_enabled = enable
                logger.info(f"{side.value} arm {'enabled' if enable else 'disabled'}")
            else:
                err = _api.get_last_error()
                logger.error(f"Enable arm failed for {side.value}: {err}")
            return result
        except Exception as e:
            logger.error(f"Enable arm error: {e}")
            return False

    def clear_errors(self) -> bool:
        """Clear controller fault/error state (lbot clear_errors) so motion is accepted."""
        if not (self._connected and self._lbot_available):
            return False
        try:
            ok = bool(_api.clear_errors())
            logger.info("clear_errors -> %s", ok)
            return ok
        except Exception as e:
            logger.error(f"clear_errors failed: {e}")
            return False

    def stop(self) -> bool:
        """Stop robot / 停止机器人"""
        self._is_moving = False
        self.state = HardwareState.CONNECTED
        return True

    def pause(self) -> bool:
        """Pause robot / 暂停机器人"""
        self.state = HardwareState.PAUSED
        return True

    def resume(self) -> bool:
        """Resume robot / 恢复机器人"""
        self.state = HardwareState.RUNNING
        return True

    @remote_callable(
        name="急停",
        category="dual_arm",
        description="Emergency stop dual arm",
        description_zh="双臂机器人紧急停止",
        is_emergency=True
    )
    def emergency_stop(self) -> bool:
        """Emergency stop robot / 机器人紧急停止"""
        if self._connected and self._lbot_available:
            try:
                _api.emergency_stop(_LbotArm.LEFT_ARM, True)
                _api.emergency_stop(_LbotArm.RIGHT_ARM, True)
            except Exception as e:
                logger.error(f"Emergency stop error: {e}")

        self._is_moving = False
        self.state = HardwareState.EMERGENCY_STOP
        logger.warning("Dual arm emergency stop executed")
        return True

    # --- State monitor callbacks ---

    def _on_state_update(self, state):
        """Callback from lbot API state monitor."""
        try:
            with self._lock:
                self._left_arm_state = {
                    'joints': state.left_arm.get_joints_list(),
                    'position': state.left_arm.end_effector_position.to_dict(),
                    'euler': state.left_arm.euler.to_dict(),
                    'orientation': state.left_arm.orientation.to_dict(),
                    'velocities': state.left_arm.get_velocities_list(),
                    'efforts': state.left_arm.get_efforts_list(),
                }
                self._right_arm_state = {
                    'joints': state.right_arm.get_joints_list(),
                    'position': state.right_arm.end_effector_position.to_dict(),
                    'euler': state.right_arm.euler.to_dict(),
                    'orientation': state.right_arm.orientation.to_dict(),
                    'velocities': state.right_arm.get_velocities_list(),
                    'efforts': state.right_arm.get_efforts_list(),
                }
                self._left_joints = self._left_arm_state['joints']
                self._right_joints = self._right_arm_state['joints']
        except Exception as e:
            logger.debug(f"State callback error: {e}")

    def _on_error(self, error_code, error_msg):
        """Error callback from the lbot controller (faults/warnings it reports)."""
        if isinstance(error_msg, bytes):
            error_msg = error_msg.decode('utf-8', errors='ignore')
        msg = error_msg or ""
        self._last_error_code = error_code
        # Throttle: the controller can emit the same error every cycle — log at most
        # once per 5s per (code, msg) so it doesn't flood the log.
        key = (error_code, msg)
        now = time.monotonic()
        if (key == getattr(self, "_last_err_key", None)
                and now - getattr(self, "_last_err_time", 0.0) < 5.0):
            return
        self._last_err_key = key
        self._last_err_time = now
        logger.error("lbot controller error: code=%s%s",
                     error_code, f" — {msg}" if msg else " (no message)")

    # --- Status & state ---

    def get_status(self) -> Dict[str, Any]:
        """Get robot status / 获取机器人状态"""
        self._update_positions()
        return {
            "name": self._name,
            "state": self._state.value,
            "left_joints": self._left_joints,
            "right_joints": self._right_joints,
            "is_moving": self._is_moving,
            "ip": self._ip,
            "speed_factor": self._speed_factor
        }

    def is_ready(self) -> bool:
        """Check if robot is ready / 检查机器人是否就绪"""
        return self.state in [HardwareState.CONNECTED, HardwareState.RUNNING]

    def _update_positions(self):
        """Update joint positions from cached state / 更新关节位置"""
        with self._lock:
            if self._left_arm_state:
                self._left_joints = list(self._left_arm_state['joints'])
            if self._right_arm_state:
                self._right_joints = list(self._right_arm_state['joints'])

    # --- Motion commands ---

    @remote_callable(
        name="左臂关节运动",
        category="dual_arm",
        description="Move left arm joints",
        description_zh="左臂关节运动"
    )
    def move_left_joints(self, joints: List[float], speed: float = None) -> bool:
        """Move left arm joints / 移动左臂关节"""
        return self._move_arm_joints(ArmSide.LEFT, joints, speed)

    @remote_callable(
        name="右臂关节运动",
        category="dual_arm",
        description="Move right arm joints",
        description_zh="右臂关节运动"
    )
    def move_right_joints(self, joints: List[float], speed: float = None) -> bool:
        """Move right arm joints / 移动右臂关节"""
        return self._move_arm_joints(ArmSide.RIGHT, joints, speed)

    def _move_arm_joints(self, side: ArmSide, joints: List[float],
                         speed: float = None, accel: float = None) -> bool:
        """Move arm joints / 移动手臂关节"""
        if len(joints) != 7:
            logger.error("Joint positions must have 7 values")
            return False

        speed = speed or self._speed_factor
        accel = accel or self._accel_factor

        if self._connected and self._lbot_available:
            try:
                self._is_moving = True
                arm_enum = _arm_enum(side)
                result = _api.move_joint(arm_enum, joints, speed, accel, block=True)
                self._is_moving = False
                self._update_positions()
                if result:
                    logger.info(f"Moved {side.value} arm to: {joints}")
                else:
                    error_msg = _api.get_last_error()
                    logger.error(f"Move joint failed for {side.value} arm: {error_msg}")
                return result
            except Exception as e:
                logger.error(f"Joint move failed: {e}")
                self._is_moving = False
                return False
        else:
            # Simulation mode
            if side == ArmSide.LEFT:
                self._left_joints = list(joints)
            else:
                self._right_joints = list(joints)
            logger.info(f"Simulated {side.value} arm move to: {joints}")
            return True

    @remote_callable(
        name="双臂同步运动",
        category="dual_arm",
        description="Move both arms synchronously",
        description_zh="双臂同步运动"
    )
    def move_both_arms(self, left_joints: List[float],
                       right_joints: List[float],
                       speed: float = None,
                       accel: float = None,
                       right_speed: float = None,
                       right_accel: float = None) -> bool:
        """Move both arms synchronously using parallel threads / 双臂同步运动（双线程并行）"""
        left_speed = speed or self._speed_factor
        left_accel = accel or self._accel_factor
        r_speed = right_speed or left_speed
        r_accel = right_accel or left_accel

        if self._connected and self._lbot_available:
            results = {'left': False, 'right': False}

            def _move_left():
                try:
                    results['left'] = _api.move_joint(
                        _LbotArm.LEFT_ARM, left_joints, left_speed, left_accel, block=True)
                except Exception as e:
                    logger.error(f"Left arm move failed: {e}")

            def _move_right():
                try:
                    results['right'] = _api.move_joint(
                        _LbotArm.RIGHT_ARM, right_joints, r_speed, r_accel, block=True)
                except Exception as e:
                    logger.error(f"Right arm move failed: {e}")

            try:
                self._is_moving = True
                import threading as _th
                lt = _th.Thread(target=_move_left, daemon=True)
                rt = _th.Thread(target=_move_right, daemon=True)
                lt.start()
                rt.start()
                lt.join()
                rt.join()
                self._is_moving = False
                self._update_positions()
                return results['left'] and results['right']
            except Exception as e:
                logger.error(f"Sync move failed: {e}")
                self._is_moving = False
                return False
        else:
            self._left_joints = list(left_joints)
            self._right_joints = list(right_joints)
            logger.info("Simulated sync arm move")
            return True

    def joint_follow(self, side, joints: List[float]) -> bool:
        """Joint follow control for teleoperation / 关节跟随控制"""
        if not self._connected or not self._lbot_available:
            return False
        try:
            arm_enum = _arm_enum(side)
            return _api.joint_follow(arm_enum, joints)
        except Exception as e:
            logger.debug(f"Joint follow failed: {e}")
            return False

    def _max_effort(self) -> float:
        """Largest absolute joint torque across both arms, from the state cache."""
        with self._lock:
            le = self._left_arm_state.get('efforts') if self._left_arm_state else None
            re = self._right_arm_state.get('efforts') if self._right_arm_state else None
        peak = 0.0
        for arr in (le, re):
            if arr:
                for v in arr:
                    peak = max(peak, abs(float(v)))
        return peak

    def _actual_joints(self):
        """Current measured joints (left, right) from the state cache; None if absent."""
        with self._lock:
            l = list(self._left_arm_state['joints']) if self._left_arm_state else None
            r = list(self._right_arm_state['joints']) if self._right_arm_state else None
        return l, r

    def get_effort_status(self) -> Dict[str, Any]:
        """Live joint torques from the state cache, for display/calibration.

        Returns {'left': [7], 'right': [7], 'max': float}; lists empty if no data.
        """
        with self._lock:
            le = list(self._left_arm_state.get('efforts', [])) if self._left_arm_state else []
            re = list(self._right_arm_state.get('efforts', [])) if self._right_arm_state else []
        mx = 0.0
        for arr in (le, re):
            for v in arr:
                mx = max(mx, abs(float(v)))
        return {'left': le, 'right': re, 'max': mx}

    def smooth_replay(self, waypoints: List[Dict[str, Any]],
                      speed_factor: float = None,
                      rate_hz: float = 100.0,
                      stop_event: Optional[threading.Event] = None,
                      on_waypoint=None,
                      enforce_limits: bool = True,
                      effort_limit: float = None,
                      effort_soft_frac: float = 0.7,
                      effort_release_frac: float = 0.8,
                      effort_debounce: float = 0.08,
                      resume_delay: float = 1.0,
                      hold_timeout: float = None) -> bool:
        """Stream a sequence of joint waypoints continuously via joint_follow.

        Unlike the blocking move_joint() path (which comes to a full stop at every
        pose), this fits a centripetal Catmull-Rom spline through the waypoints and
        streams the sampled targets at a fixed rate. The motion flows *through* the
        interior waypoints with continuous velocity (no corner snap) and eases in/out
        at the trajectory ends.
        通过 joint_follow 连续流式播放关节路点（向心 Catmull-Rom 样条），位姿之间速度连续、不停顿。

        Two safety behaviours layer on top of the stream:
          * Joint-limit avoidance (enforce_limits): targets are hard-clamped to the
            joint limits, and the streaming velocity is scaled down when a joint nears
            its limit while moving toward it, so it eases up to the boundary.
          * Effort-based contact reaction (effort_limit): if set, the largest joint
            torque is monitored each tick. In the soft band (effort_soft_frac *
            effort_limit .. effort_limit) the motion slows; at/above effort_limit — once
            sustained for effort_debounce seconds — it *holds at the arm's actual position*
            (where contact occurred, not the commanded target slightly ahead) and waits (no
            emergency stop); on resume it eases on from that actual position. It stays held
            (hysteresis) until torque drops below
            effort_release_frac * effort_limit, then resumes; the debounce + hysteresis
            prevent chattering when torque hovers near the limit. After a contact clears
            it dwells resume_delay seconds (holding) before resuming. With hold_timeout given,
            a contact held that long stops the replay cleanly (None = wait indefinitely,
            only the stop_event ends it). effort_limit is in the SDK's torque units
            (hardware-dependent) and must be calibrated — the peak effort seen during a
            run is logged to help. Left as None (default) the feature is OFF.

        Args:
            waypoints: list of {"left": [7 floats] | None, "right": [7 floats] | None}.
                       A None side holds its previous target (that arm does not move).
            speed_factor: scales the max joint speed used to time each segment;
                          defaults to the controller's speed factor.
            rate_hz: streaming control rate in Hz.
            stop_event: optional Event; streaming aborts cleanly when set.
            on_waypoint: optional callable(index) invoked when each waypoint is reached
                         (used to fire hand/gripper actions at pose boundaries).
            enforce_limits: clamp targets to joint limits and ease near them (default True).
            effort_limit: torque magnitude that triggers a contact halt; None disables.
            effort_soft_frac: fraction of effort_limit at which slowing begins (0..1).

        Returns:
            True if the full sequence completed, False if aborted, halted on contact,
            or unavailable.
        """
        if not waypoints:
            return True

        sf = speed_factor if speed_factor is not None else self._speed_factor
        sf = max(0.02, min(2.0, sf))
        max_w = _SMOOTH_MAX_JOINT_SPEED * sf
        dt = 1.0 / max(10.0, rate_hz)

        # Simulation / not connected: snap to final targets and fire callbacks.
        if not (self._connected and self._lbot_available):
            last_l, last_r = list(self._left_joints), list(self._right_joints)
            for idx, wp in enumerate(waypoints):
                if wp.get("left"):
                    last_l = list(wp["left"])
                if wp.get("right"):
                    last_r = list(wp["right"])
                if on_waypoint:
                    try:
                        on_waypoint(idx)
                    except Exception:
                        pass
            self._left_joints, self._right_joints = last_l, last_r
            return True

        # Build the full control-point sequence per arm, starting from the
        # current measured joints. A None side holds its previous target, so the
        # held arm contributes coincident control points (zero motion).
        start_l = list(self.get_left_joints())
        start_r = list(self.get_right_joints())
        pts_l: List[List[float]] = [start_l]
        pts_r: List[List[float]] = [start_r]
        last_l, last_r = list(start_l), list(start_r)
        for wp in waypoints:
            if wp.get("left"):
                last_l = list(wp["left"])
            if wp.get("right"):
                last_r = list(wp["right"])
            pts_l.append(list(last_l))
            pts_r.append(list(last_r))

        # Centripetal Catmull-Rom tangents (each arm parameterized independently,
        # but every segment is traversed with the same normalized s so the arms
        # stay synchronized and meet at each waypoint together).
        kn_l, kn_r = _cr_knots(pts_l), _cr_knots(pts_r)
        tan_l, tan_r = _cr_tangents(pts_l, kn_l), _cr_tangents(pts_r, kn_r)

        n_seg = len(waypoints)  # control points = n_seg + 1; segment i: pts[i]->pts[i+1]
        peak_effort = 0.0
        # Contact state spans segments (a contact doesn't care about waypoint boundaries).
        contact_active = False   # latched contact hold (debounced, released via hysteresis)
        over_time = 0.0          # seconds torque has been continuously over the trip level
        held = 0.0               # seconds spent in the latched hold (for hold_timeout)
        cooldown = 0.0           # post-contact dwell remaining before resuming (s)

        self._is_moving = True
        try:
            for i in range(n_seg):
                if stop_event is not None and stop_event.is_set():
                    return False

                a_l, b_l = pts_l[i], pts_l[i + 1]
                a_r, b_r = pts_r[i], pts_r[i + 1]

                # Segment duration from the largest joint delta across both arms,
                # so the arms stay synchronized and move at a bounded speed.
                max_delta = 0.0
                for a, b in zip(a_l, b_l):
                    max_delta = max(max_delta, abs(b - a))
                for a, b in zip(a_r, b_r):
                    max_delta = max(max_delta, abs(b - a))
                duration = max(0.05, max_delta / max_w)
                du_nom = dt / duration  # nominal parameter advance per tick (s in [0,1])

                # Scale tangents from knot-parameter space to this segment's s in [0,1].
                seg_l = kn_l[i + 1] - kn_l[i]
                seg_r = kn_r[i + 1] - kn_r[i]
                m0_l = [v * seg_l for v in tan_l[i]]
                m1_l = [v * seg_l for v in tan_l[i + 1]]
                m0_r = [v * seg_r for v in tan_r[i]]
                m1_r = [v * seg_r for v in tan_r[i + 1]]

                # Per-segment travel direction for limit-proximity throttling.
                dir_l = [(1 if b_l[j] > a_l[j] else -1 if b_l[j] < a_l[j] else 0)
                         for j in range(7)]
                dir_r = [(1 if b_r[j] > a_r[j] else -1 if b_r[j] < a_r[j] else 0)
                         for j in range(7)]

                # Integrate the spline parameter forward, throttled by effort/limits,
                # rather than stepping a fixed count — so slowing stretches time.
                u = 0.0
                last_l, last_r = list(a_l), list(a_r)
                max_ticks = int(duration / dt) * 8 + 100  # backstop against a stall
                ticks = 0          # counts only productive (advancing) ticks
                hold_l = hold_r = None  # actual position captured at contact (hold target)
                while u < 1.0:
                    if stop_event is not None and stop_event.is_set():
                        return False
                    if ticks > max_ticks:
                        logger.warning(
                            "smooth_replay: segment %d stalled under throttle; "
                            "advancing to next waypoint", i)
                        break

                    eff = self._max_effort()
                    peak_effort = max(peak_effort, eff)

                    # (2) Effort-based contact reaction with debounce + hysteresis.
                    eff_scale = 1.0
                    if effort_limit:
                        trip = effort_limit
                        release = effort_limit * effort_release_frac
                        soft = effort_limit * max(0.0, min(1.0, effort_soft_frac))
                        # Debounce: require sustained over-limit before latching a hold.
                        over_time = over_time + dt if eff >= trip else 0.0
                        if contact_active:
                            # Hysteresis: stay held until torque drops below release level.
                            if eff < release:
                                contact_active = False
                                cooldown = resume_delay
                                logger.info("smooth_replay: contact cleared; "
                                            "resuming in %.1fs", resume_delay)
                        elif over_time >= effort_debounce:
                            contact_active = True
                            cooldown = 0.0
                            logger.info(
                                "smooth_replay: contact (effort %.3f >= limit %.3f for "
                                "%.0fms) — holding", eff, trip, effort_debounce * 1000)
                        if contact_active:
                            eff_scale = 0.0
                        elif eff > soft:
                            eff_scale = max(0.0, (trip - eff) / max(1e-9, trip - soft))

                    # (1) Joint-limit proximity throttle (directional).
                    lim_scale = 1.0
                    if enforce_limits:
                        lim_scale = min(_limit_scale(last_l, dir_l),
                                        _limit_scale(last_r, dir_r))

                    # Latched contact hold: stop, hold position, wait (optional timeout).
                    if contact_active:
                        if hold_l is None:
                            _al, _ar = self._actual_joints()
                            hold_l = _al if _al else list(last_l)
                            hold_r = _ar if _ar else list(last_r)
                        held += dt
                        if hold_timeout is not None and held >= hold_timeout:
                            logger.warning(
                                "smooth_replay: sustained contact (effort %.3f) for %.1fs; "
                                "stopping replay", eff, held)
                            return False
                        try:
                            _api.joint_follow(_LbotArm.LEFT_ARM, hold_l)
                            _api.joint_follow(_LbotArm.RIGHT_ARM, hold_r)
                        except Exception:
                            pass
                        time.sleep(dt)
                        continue
                    held = 0.0

                    # Post-contact dwell: keep holding for resume_delay before resuming.
                    if cooldown > 0.0:
                        if hold_l is None:
                            _al, _ar = self._actual_joints()
                            hold_l = _al if _al else list(last_l)
                            hold_r = _ar if _ar else list(last_r)
                        cooldown = max(0.0, cooldown - dt)
                        try:
                            _api.joint_follow(_LbotArm.LEFT_ARM, hold_l)
                            _api.joint_follow(_LbotArm.RIGHT_ARM, hold_r)
                        except Exception:
                            pass
                        if cooldown <= 0.0:
                            logger.info("smooth_replay: resuming")
                        time.sleep(dt)
                        continue

                    # Joint limit pinned (not a transient) — can't progress; next waypoint.
                    if enforce_limits and lim_scale <= 1e-3:
                        logger.warning(
                            "smooth_replay: joint limit reached in segment %d; "
                            "advancing to next waypoint", i)
                        break

                    scale = max(0.0, eff_scale) * lim_scale
                    if scale <= 1e-6:
                        # Transient throttle-to-zero (e.g. a brief spike before debounce
                        # latches): slow without latching; hold the actual position.
                        if hold_l is None:
                            _al, _ar = self._actual_joints()
                            hold_l = _al if _al else list(last_l)
                            hold_r = _ar if _ar else list(last_r)
                        try:
                            _api.joint_follow(_LbotArm.LEFT_ARM, hold_l)
                            _api.joint_follow(_LbotArm.RIGHT_ARM, hold_r)
                        except Exception:
                            pass
                        time.sleep(dt)
                        continue

                    # Resuming after a hold: re-seed this segment from the actual position
                    # the arm was held at, so it eases on from there (no jump to the old
                    # commanded target).
                    if hold_l is not None:
                        a_l, a_r = list(hold_l), list(hold_r)
                        m0_l = [0.0] * 7
                        m0_r = [0.0] * 7
                        dir_l = [(1 if b_l[j] > a_l[j] else -1 if b_l[j] < a_l[j] else 0)
                                 for j in range(7)]
                        dir_r = [(1 if b_r[j] > a_r[j] else -1 if b_r[j] < a_r[j] else 0)
                                 for j in range(7)]
                        md = 0.0
                        for x, y in zip(a_l, b_l):
                            md = max(md, abs(y - x))
                        for x, y in zip(a_r, b_r):
                            md = max(md, abs(y - x))
                        du_nom = dt / max(0.05, md / max_w)
                        u = 0.0
                        last_l, last_r = list(a_l), list(a_r)
                        hold_l = hold_r = None

                    ticks += 1
                    u = min(1.0, u + du_nom * scale)
                    tgt_l = _hermite(a_l, b_l, m0_l, m1_l, u)
                    tgt_r = _hermite(a_r, b_r, m0_r, m1_r, u)
                    if enforce_limits:
                        tgt_l = _clamp_to_limits(tgt_l)
                        tgt_r = _clamp_to_limits(tgt_r)
                    try:
                        _api.joint_follow(_LbotArm.LEFT_ARM, tgt_l)
                        _api.joint_follow(_LbotArm.RIGHT_ARM, tgt_r)
                    except Exception as e:
                        logger.error(f"Smooth replay joint_follow failed: {e}")
                        return False
                    last_l, last_r = tgt_l, tgt_r
                    time.sleep(dt)

                with self._lock:
                    self._left_joints = list(last_l)
                    self._right_joints = list(last_r)
                if on_waypoint:
                    try:
                        on_waypoint(i)
                    except Exception as e:
                        logger.debug(f"smooth_replay on_waypoint callback failed: {e}")
            return True
        finally:
            self._is_moving = False
            self._update_positions()
            logger.info("smooth_replay finished; peak joint effort observed: %.3f "
                        "(set effort_limit above this + margin to enable contact halt)",
                        peak_effort)

    def hold_position_protected(self, stop_event: threading.Event,
                                effort_limit: float = None,
                                rate_hz: float = 100.0,
                                effort_release_frac: float = 0.8,
                                effort_debounce: float = 0.08) -> None:
        """Actively hold the current pose with contact protection until stop_event is set.

        Runs after a replay so the contact limit still governs while the arm sits at the
        final pose. While torque is below the limit it holds the captured target; if you
        push past effort_limit (sustained effort_debounce s) it *yields* — re-captures the
        arm's actual position and holds there instead of stiffly fighting — and stops
        yielding once torque drops below effort_release_frac * effort_limit.
        在回放结束后保持最终位姿并保留接触保护，直到 stop_event 置位（用户按停止）。

        Requires a stop_event (the only exit); does nothing if not connected or if
        effort_limit is not set.
        """
        if stop_event is None or not effort_limit:
            return
        if not (self._connected and self._lbot_available):
            return

        dt = 1.0 / max(10.0, rate_hz)
        hold_l = list(self.get_left_joints())
        hold_r = list(self.get_right_joints())
        trip = effort_limit
        release = effort_limit * effort_release_frac
        contact_active = False
        over_time = 0.0

        logger.info("Protected hold active at final pose (limit %.3f); press Stop to release",
                    effort_limit)
        self._is_moving = True
        try:
            while not stop_event.is_set():
                eff = self._max_effort()
                over_time = over_time + dt if eff >= trip else 0.0
                if contact_active:
                    if eff < release:
                        contact_active = False
                        logger.info("Protected hold: contact cleared")
                elif over_time >= effort_debounce:
                    contact_active = True
                    logger.info("Protected hold: contact (effort %.3f) — yielding", eff)
                if contact_active:
                    # Yield: hold wherever the arm is actually pushed to, don't fight it.
                    with self._lock:
                        if self._left_arm_state:
                            hold_l = list(self._left_arm_state['joints'])
                        if self._right_arm_state:
                            hold_r = list(self._right_arm_state['joints'])
                try:
                    _api.joint_follow(_LbotArm.LEFT_ARM, hold_l)
                    _api.joint_follow(_LbotArm.RIGHT_ARM, hold_r)
                except Exception:
                    pass
                time.sleep(dt)
        finally:
            self._is_moving = False
            self._update_positions()
            logger.info("Protected hold released")

    # --- Joint / TCP getters ---

    def get_arm_state(self, arm) -> Optional[Dict[str, Any]]:
        """Get current arm state dict with joints, position, euler.

        Performs a direct API query (get_current_state) to ensure fresh data
        rather than relying solely on the state-monitor callback cache.

        Args:
            arm: ArmSide enum or string ("left"/"right")

        Returns:
            Dict with 'joints', 'position', 'euler' keys, or None if unavailable.
        """
        if isinstance(arm, ArmSide):
            arm = arm.value

        # Try direct API query for fresh data
        if self._connected and self._lbot_available:
            try:
                fresh = _api.get_current_state()
                if fresh is not None:
                    arm_data = fresh.left_arm if arm == "left" else fresh.right_arm
                    return {
                        'joints': arm_data.get_joints_list(),
                        'position': arm_data.end_effector_position.to_dict(),
                        'euler': arm_data.euler.to_dict(),
                    }
            except Exception as e:
                logger.debug(f"Direct state query failed for {arm}, using cache: {e}")

        # Fallback to cached state
        with self._lock:
            state = self._left_arm_state if arm == "left" else self._right_arm_state
        if state is None:
            return None
        return {
            'joints': list(state['joints']),
            'position': dict(state.get('position', {})),
            'euler': dict(state.get('euler', {})),
        }

    def get_left_joints(self) -> List[float]:
        """Get left arm joint positions / 获取左臂关节位置"""
        self._update_positions()
        return self._left_joints

    def get_right_joints(self) -> List[float]:
        """Get right arm joint positions / 获取右臂关节位置"""
        self._update_positions()
        return self._right_joints

    def get_tcp_pose(self, arm: str = "left") -> Dict[str, Any]:
        """
        Get TCP position + quaternion for specified arm.
        获取指定手臂的TCP位姿。
        """
        with self._lock:
            arm_state = self._left_arm_state if arm == "left" else self._right_arm_state

        if arm_state:
            pos = arm_state['position']
            orient = arm_state.get('orientation')
            if orient:
                quaternion = [orient.get('w', 1.0), orient.get('x', 0.0),
                              orient.get('y', 0.0), orient.get('z', 0.0)]
            else:
                # Convert euler to quaternion as fallback
                euler = arm_state.get('euler', {})
                quaternion = self._euler_to_quaternion(
                    euler.get('x', 0.0), euler.get('y', 0.0), euler.get('z', 0.0)
                )
            return {
                "position": [pos.get('x', 0.0), pos.get('y', 0.0), pos.get('z', 0.0)],
                "quaternion": quaternion
            }

        return {"position": [0.0, 0.0, 0.0], "quaternion": [1.0, 0.0, 0.0, 0.0]}

    @staticmethod
    def _euler_to_quaternion(rx, ry, rz):
        """Convert euler angles to quaternion [w, x, y, z]."""
        cr, sr = math.cos(rx / 2), math.sin(rx / 2)
        cp, sp = math.cos(ry / 2), math.sin(ry / 2)
        cy, sy = math.cos(rz / 2), math.sin(rz / 2)
        return [
            cr * cp * cy + sr * sp * sy,
            sr * cp * cy - cr * sp * sy,
            cr * sp * cy + sr * cp * sy,
            cr * cp * sy - sr * sp * cy,
        ]

    def get_joint_velocities(self, arm: str = "left") -> List[float]:
        """Get joint velocities for specified arm / 获取关节速度"""
        with self._lock:
            arm_state = self._left_arm_state if arm == "left" else self._right_arm_state
        if arm_state:
            return list(arm_state.get('velocities', [0.0] * 7))
        return [0.0] * 7

    def get_joint_efforts(self, arm: str = "left") -> List[float]:
        """Get joint torques for specified arm / 获取关节力矩"""
        with self._lock:
            arm_state = self._left_arm_state if arm == "left" else self._right_arm_state
        if arm_state:
            return list(arm_state.get('efforts', [0.0] * 7))
        return [0.0] * 7

    def get_full_state(self, arm: str = "left") -> Dict[str, Any]:
        """
        Get complete robot state for VLA recording.
        获取完整的机器人状态（用于VLA录制）。
        """
        self._update_positions()
        tcp = self.get_tcp_pose(arm)
        joints = self._left_joints if arm == "left" else self._right_joints

        return {
            "tcp_position": tcp["position"],
            "tcp_quaternion": tcp["quaternion"],
            "joint_positions": list(joints),
            "joint_velocities": self.get_joint_velocities(arm),
            "joint_efforts": self.get_joint_efforts(arm),
        }

    # --- Background state poller (for VLA recording) ---

    def start_state_poller(self, rate_hz: float = 50):
        """
        Start background thread that polls robot state into cache.
        启动后台线程轮询机器人状态到缓存。
        """
        if self._state_poller_thread and self._state_poller_thread.is_alive():
            return

        self._state_poller_stop.clear()
        min_interval = 1.0 / rate_hz

        def _poller():
            logger.info(f"State poller started (target {rate_hz}Hz)")
            while not self._state_poller_stop.is_set():
                t0 = time.time()
                try:
                    self._poll_state_once()
                except Exception as e:
                    logger.debug(f"State poller error: {e}")
                elapsed = time.time() - t0
                sleep_time = max(0, min_interval - elapsed)
                if sleep_time > 0:
                    self._state_poller_stop.wait(sleep_time)
            logger.info("State poller stopped")

        self._state_poller_thread = threading.Thread(
            target=_poller, daemon=True, name="StatePoller"
        )
        self._state_poller_thread.start()

    def stop_state_poller(self):
        """Stop background state poller thread. / 停止后台状态轮询线程。"""
        self._state_poller_stop.set()
        if self._state_poller_thread:
            self._state_poller_thread.join(timeout=2.0)
            self._state_poller_thread = None

    def _poll_state_once(self):
        """Poll full state for both arms and update cache. / 轮询双臂完整状态并更新缓存。"""
        now = time.time()
        new_cache: Dict[str, Dict[str, Any]] = {}

        with self._lock:
            left_state = self._left_arm_state
            right_state = self._right_arm_state

        for arm_name, arm_state in [("left", left_state), ("right", right_state)]:
            if arm_state:
                pos = arm_state['position']
                orient = arm_state.get('orientation')
                if orient:
                    quaternion = [orient.get('w', 1.0), orient.get('x', 0.0),
                                  orient.get('y', 0.0), orient.get('z', 0.0)]
                else:
                    euler = arm_state.get('euler', {})
                    quaternion = self._euler_to_quaternion(
                        euler.get('x', 0.0), euler.get('y', 0.0), euler.get('z', 0.0)
                    )
                new_cache[arm_name] = {
                    "tcp_position": [pos.get('x', 0.0), pos.get('y', 0.0), pos.get('z', 0.0)],
                    "tcp_quaternion": quaternion,
                    "joint_positions": list(arm_state['joints']),
                    "joint_velocities": list(arm_state.get('velocities', [0.0] * 7)),
                    "joint_efforts": list(arm_state.get('efforts', [0.0] * 7)),
                    "robot_timestamp": now,
                }
            else:
                joints = list(self._left_joints if arm_name == "left" else self._right_joints)
                new_cache[arm_name] = {
                    "tcp_position": [0.0, 0.0, 0.0],
                    "tcp_quaternion": [1.0, 0.0, 0.0, 0.0],
                    "joint_positions": joints,
                    "joint_velocities": [0.0] * 7,
                    "joint_efforts": [0.0] * 7,
                    "robot_timestamp": now,
                }

        with self._state_cache_lock:
            self._cached_state = new_cache
            self._cached_state_timestamp = now

            if "left" in new_cache:
                self._left_joints = list(new_cache["left"]["joint_positions"])
            if "right" in new_cache:
                self._right_joints = list(new_cache["right"]["joint_positions"])

    def get_full_state_cached(self, arm: str = "left") -> Dict[str, Any]:
        """
        Get cached robot state (sub-millisecond read).
        获取缓存的机器人状态（亚毫秒级读取）。
        """
        with self._state_cache_lock:
            cached = self._cached_state.get(arm)
            if cached:
                return dict(cached)

        return self.get_full_state(arm)
