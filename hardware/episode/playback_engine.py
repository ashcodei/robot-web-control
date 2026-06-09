"""
Episode Playback Engine
编排播放引擎

Executes episodes with dependency resolution across components.
"""

import json
import os
import time
import threading
from typing import Dict, List, Optional, Callable, Any

from app_core.logger import get_logger
from .episode_model import ComponentAction, Episode

logger = get_logger(__name__)


class PlaybackEngine:
    """
    Executes multi-component episodes respecting dependency ordering.

    Each action runs on its own thread. Dependencies are resolved via
    threading.Event pairs (started / completed) per action.
    """

    def __init__(self, dual_arm, linker_hand, lebai, wok, gripper=None):
        self._dual_arm = dual_arm
        self._linker_hand = linker_hand
        self._lebai = lebai
        self._wok = wok
        self._gripper = gripper
        self._stop_event = threading.Event()
        self._running = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def play_episode(self, episode: Episode,
                     on_progress: Callable[[int, str], None] = None,
                     action_delay: float = 0.0):
        """
        Play a single episode (blocking). Call from a background thread.

        Args:
            episode: The episode to play.
            on_progress: Callback(action_index, status) for UI updates.
            action_delay: Seconds to wait before starting each action (except first).
        """
        self._stop_event.clear()
        self._running = True

        actions = episode.actions
        if not actions:
            self._running = False
            return

        # Create started/completed events per action index
        started: Dict[int, threading.Event] = {}
        completed: Dict[int, threading.Event] = {}
        for i in range(len(actions)):
            started[i] = threading.Event()
            completed[i] = threading.Event()

        # Build target lookup: dependency_target stores action index or "group:<gid>"
        # For single-action targets: list with one index
        # For group targets: list of all action indices in that group
        target_indices: Dict[int, list] = {}
        for i, a in enumerate(actions):
            if a.dependency != "none" and a.dependency_target:
                dt = a.dependency_target
                if dt.startswith("group:"):
                    gid = dt[6:]
                    group_members = [
                        j for j, act in enumerate(actions)
                        if getattr(act, 'group_id', '') == gid and j != i
                    ]
                    target_indices[i] = group_members if group_members else []
                else:
                    try:
                        tidx = int(dt)
                        if 0 <= tidx < len(actions) and tidx != i:
                            target_indices[i] = [tidx]
                        else:
                            target_indices[i] = []
                    except (ValueError, TypeError):
                        target_indices[i] = []
            else:
                target_indices[i] = []

        threads: List[threading.Thread] = []

        for i, action in enumerate(actions):
            if self._stop_event.is_set():
                break

            def _run_action(idx=i, act=action):
                try:
                    dep = act.dependency
                    targets = target_indices.get(idx, [])

                    # Wait for dependency
                    if dep == "starts_with" and targets:
                        # Run in parallel with target(s) — wait for first to start
                        started[targets[0]].wait()
                    elif dep == "starts_after" and targets:
                        # Wait for all target(s) to complete
                        for tidx in targets:
                            completed[tidx].wait()
                            if self._stop_event.is_set():
                                return
                        if action_delay > 0:
                            self._interruptible_sleep(action_delay)
                    else:
                        # dep=="none", OR dep was starts_with/starts_after but the
                        # target resolved to empty (e.g. playing a subset of actions
                        # where the original target index is out of range).
                        # Default: run sequentially — wait for all preceding to finish.
                        for prev in range(idx):
                            completed[prev].wait()
                            if self._stop_event.is_set():
                                return
                        if idx > 0 and action_delay > 0:
                            self._interruptible_sleep(action_delay)

                    if self._stop_event.is_set():
                        return

                    # Signal started
                    started[idx].set()
                    if on_progress:
                        on_progress(idx, "running")

                    # Execute
                    self._dispatch(act)

                except Exception as e:
                    logger.error(f"Action {idx} ({act.component}) failed: {e}")
                finally:
                    completed[idx].set()
                    if on_progress:
                        on_progress(idx, "done")

            t = threading.Thread(target=_run_action, daemon=True)
            threads.append(t)
            t.start()

            # "none":         thread waits for all preceding actions to complete
            # "starts_with":  thread waits for target's started event (parallel)
            # "starts_after": thread waits for target's completed event

        # Wait for all actions to complete
        for t in threads:
            t.join()

        self._running = False

    def play_all(self, episodes: List[Episode],
                 on_episode_progress: Callable[[int, int, str], None] = None,
                 on_action_progress: Callable[[int, str], None] = None,
                 episode_delay: float = 0.0,
                 action_delay: float = 0.0):
        """
        Play all episodes sequentially (blocking).

        Args:
            episodes: List of episodes.
            on_episode_progress: Callback(episode_idx, total, status).
            on_action_progress: Callback(action_idx, status).
            episode_delay: Seconds to wait between episodes.
            action_delay: Seconds to wait between actions within an episode.
        """
        self._stop_event.clear()
        self._running = True

        for ei, episode in enumerate(episodes):
            if self._stop_event.is_set():
                break
            # Wait between episodes (skip before the first one)
            if ei > 0 and episode_delay > 0:
                self._interruptible_sleep(episode_delay)
                if self._stop_event.is_set():
                    break
            if on_episode_progress:
                on_episode_progress(ei, len(episodes), "running")
            self.play_episode(episode, on_progress=on_action_progress,
                              action_delay=action_delay)
            if on_episode_progress:
                on_episode_progress(ei, len(episodes), "done")

        self._running = False

    def stop(self):
        """Soft-stop current playback and all hardware."""
        self._stop_event.set()
        # Dual arm — soft stop
        if self._dual_arm is not None:
            try:
                self._dual_arm.stop()
            except Exception as e:
                logger.warning(f"Error stopping dual arm: {e}")
        # Lebai
        if self._lebai is not None:
            try:
                self._lebai.stop_move()
            except Exception as e:
                logger.warning(f"Error stopping lebai: {e}")
        # Wok
        if self._wok is not None:
            try:
                self._wok.stop_auto_cooking()
                self._wok.move_to_max_up()
            except Exception as e:
                logger.warning(f"Error stopping wok: {e}")

    def emergency_stop(self):
        """Immediately halt all hardware mid-action."""
        self._stop_event.set()
        # Dual arm
        if self._dual_arm is not None:
            try:
                self._dual_arm.emergency_stop()
            except Exception as e:
                logger.warning(f"Error emergency-stopping dual arm: {e}")
        # Lebai
        if self._lebai is not None:
            try:
                self._lebai.stop_move()
            except Exception as e:
                logger.warning(f"Error stopping lebai: {e}")
        # Wok
        if self._wok is not None:
            try:
                self._wok.stop_auto_cooking()
                self._wok.move_to_max_up()
            except Exception as e:
                logger.warning(f"Error stopping wok: {e}")

    def _interruptible_sleep(self, seconds: float):
        """Sleep that can be interrupted by the stop event."""
        self._stop_event.wait(timeout=seconds)

    @property
    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Dispatch to component adapters
    # ------------------------------------------------------------------

    def _dispatch(self, action: ComponentAction):
        """Route action to the appropriate component adapter."""
        if self._stop_event.is_set():
            return

        if action.component == "dual_arm":
            self._run_dual_arm(action)
        elif action.component == "lebai":
            self._run_lebai(action)
        elif action.component == "wok":
            self._run_wok(action)
        elif action.component == "wait":
            self._run_wait(action)
        else:
            logger.warning(f"Unknown component: {action.component}")

    # ------------------------------------------------------------------
    # Dual Arm adapter
    # ------------------------------------------------------------------

    def _run_dual_arm(self, action: ComponentAction):
        """Execute dual arm step from a recording file."""
        from hardware.dual_arm.pose_control_widget import RecordedPose, Step

        filepath = action.recording_file
        if not filepath or not os.path.isfile(filepath):
            logger.error(f"Dual arm file not found: {filepath}")
            return

        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        steps_data = data.get('steps', [])
        if not steps_data:
            logger.error(f"No steps in {filepath}")
            return

        idx = action.step_index
        if idx < 0:
            # Play all steps
            steps_to_play = [Step.from_dict(s) for s in steps_data]
        elif idx < len(steps_data):
            steps_to_play = [Step.from_dict(steps_data[idx])]
        else:
            logger.error(f"Step index {idx} out of range in {filepath}")
            return

        params = action.parameters or {}
        speed_val = params.get("speed", 0.0) or 0.0
        accel_val = params.get("accel", 0.0) or 0.0
        pose_delay = params.get("pose_delay", 0.3) or 0.3
        # 0.0 means "no override — use each pose's own speed/accel"
        speed_override = speed_val if speed_val > 0.0 else None
        accel_override = accel_val if accel_val > 0.0 else None

        for step in steps_to_play:
            for pose in step.poses:
                if self._stop_event.is_set():
                    return
                self._execute_pose(pose, speed_override, accel_override)
                if pose_delay > 0:
                    time.sleep(pose_delay)

    def _execute_pose(self, pose, speed_override=None, accel_override=None):
        """Execute a single dual arm pose (blocking)."""
        from hardware.dual_arm.dual_arm_controller import ArmSide

        speed = speed_override if speed_override is not None else (pose.speed or 0.5)
        accel = accel_override if accel_override is not None else (pose.acceleration or 0.5)
        is_hand_only = (pose.pose_type == "hand_only")
        hand = self._linker_hand if self._linker_hand and self._linker_hand.is_ready() else None

        if pose.arm == "both":
            self._execute_dual_pose(pose, speed, accel, hand, is_hand_only)
        else:
            arm_side = ArmSide.LEFT if pose.arm == "left" else ArmSide.RIGHT
            if hand and pose.hand_positions:
                from hardware.dual_arm.linker_hand_controller import HandSide
                hs = HandSide.LEFT if pose.arm == "left" else HandSide.RIGHT
                try:
                    hand.set_finger_positions(hs, [float(x) for x in pose.hand_positions])
                except Exception as e:
                    logger.debug(f"Hand move error: {e}")
            # Apply gripper for right arm poses
            if pose.arm == "right":
                self._apply_pose_gripper(pose)
            if not is_hand_only:
                self._dual_arm._move_arm_joints(arm_side, pose.joints, speed, accel)

    def _execute_dual_pose(self, pose, speed, accel, hand, is_hand_only):
        """Execute dual-arm pose with parallel threads (blocking)."""
        from hardware.dual_arm.dual_arm_controller import ArmSide
        from hardware.dual_arm.linker_hand_controller import HandSide

        right_speed = pose.right_speed if pose.right_speed is not None else speed
        right_accel = pose.right_acceleration if pose.right_acceleration is not None else accel

        def _left():
            try:
                if hand and pose.hand_positions:
                    hand.set_finger_positions(HandSide.LEFT, [float(x) for x in pose.hand_positions])
                if not is_hand_only:
                    self._dual_arm._move_arm_joints(ArmSide.LEFT, pose.joints, speed, accel)
            except Exception as e:
                logger.error(f"Left side failed: {e}")

        def _right():
            try:
                if hand and pose.right_hand_positions:
                    hand.set_finger_positions(HandSide.RIGHT, [float(x) for x in pose.right_hand_positions])
                self._apply_pose_gripper(pose)
                if not is_hand_only and pose.right_joints:
                    self._dual_arm._move_arm_joints(ArmSide.RIGHT, pose.right_joints, right_speed, right_accel)
            except Exception as e:
                logger.error(f"Right side failed: {e}")

        lt = threading.Thread(target=_left, daemon=True)
        rt = threading.Thread(target=_right, daemon=True)
        lt.start()
        rt.start()
        lt.join()
        rt.join()

    def _apply_pose_gripper(self, pose):
        """Apply gripper position from pose to hardware."""
        if not self._gripper or not self._gripper.is_ready():
            return
        grip_pos = getattr(pose, 'gripper_position', None)
        if grip_pos is None:
            return
        try:
            self._gripper.set_opening(int(grip_pos))
        except Exception as e:
            logger.debug(f"Apply pose gripper: {e}")

    # ------------------------------------------------------------------
    # Lebai / Gantry adapter
    # ------------------------------------------------------------------

    def _run_lebai(self, action: ComponentAction):
        """Execute lebai trajectory replay (blocking)."""
        filepath = action.recording_file
        if not filepath or not os.path.isfile(filepath):
            logger.error(f"Lebai file not found: {filepath}")
            return

        records = self._load_lebai_records(filepath)
        if not records:
            logger.error(f"No valid records in {filepath}")
            return

        robot = self._lebai._robot if self._lebai else None
        if robot is None:
            logger.error("Lebai robot not available")
            return

        # Build plan (reuse the compression/plan-building logic)
        plan = self._build_lebai_plan(records)
        if not plan:
            logger.error("Failed to build lebai replay plan")
            return

        # Init SDK
        try:
            robot.end_teach_mode()
        except Exception:
            pass
        try:
            robot.start_sys()
            time.sleep(0.3)
        except Exception:
            pass

        # Execute plan – speed/accel from unified controller config
        speed = self._lebai.replay_speed
        accel = self._lebai.replay_accel
        prev_joints = None
        for idx, (action_type, action_data) in enumerate(plan):
            if self._stop_event.is_set():
                try:
                    robot.stop()
                except Exception:
                    pass
                break

            if action_type == "movej":
                joints = action_data
                try:
                    from hardware.gantry_lebai.lebai_controller import LebaiController
                    joints_dict = LebaiController._joints_list_to_dict(joints)
                    robot.movej(joints_dict, accel, speed, 0, 0)
                except Exception as e:
                    logger.error(f"movej failed: {e}")
                    if prev_joints is None:
                        return
                    continue

                # Wait until close to target
                if not self._wait_lebai_close(robot, joints):
                    if self._stop_event.is_set():
                        try:
                            robot.stop()
                        except Exception:
                            pass
                        break
                prev_joints = joints

            elif action_type == "gripper":
                try:
                    self._lebai.set_claw(amplitude=float(action_data), force=100)
                except Exception as e:
                    logger.warning(f"set_claw failed: {e}")

    def _load_lebai_records(self, filepath: str) -> List[Dict]:
        """Load lebai trajectory records from JSON."""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if isinstance(data, dict) and "records" in data:
            recs = data.get("records", [])
        else:
            recs = data if isinstance(data, list) else []

        out = []
        t0 = time.time()
        for i, r in enumerate(recs):
            if isinstance(r, dict) and isinstance(r.get("joints"), list):
                out.append({
                    "timestamp": float(r.get("timestamp", t0 + i * 0.02)),
                    "joints": list(r["joints"]),
                    "gripper": float(r.get("gripper", 0.0)),
                    "session_id": r.get("session_id"),
                })
            elif isinstance(r, list):
                out.append({
                    "timestamp": t0 + i * 0.02,
                    "joints": [float(v) for v in r],
                    "gripper": 0.0,
                })
        return out

    def _build_lebai_plan(self, records: List[Dict]) -> List[tuple]:
        """Build a flat (action_type, data) plan from lebai records.

        Uses the same algorithm as the teach widget's _replay_build_plan:
        1. Split records into session chunks (by session_id or timestamp gap).
        2. Within each chunk, split at gripper-value changes.
        3. Compress each sub-segment into keyframes via _compress_chunk.
        4. Emit movej/gripper actions with gripper only at boundaries.
        """
        GRIP_THRESH = 0.5

        # --- 1. extract dense (joints, gripper) + metadata ---
        dense: List[tuple] = []
        meta: List[dict] = []
        for r in records:
            if isinstance(r, dict) and isinstance(r.get("joints"), list):
                dense.append(([float(x) for x in r["joints"]],
                              float(r.get("gripper", 0.0))))
                meta.append({
                    "t": float(r.get("timestamp", 0)) if r.get("timestamp") else None,
                    "sid": r.get("session_id"),
                })
        if len(dense) < 2:
            return []

        # --- 2. split into session chunks (session_id or timestamp gap) ---
        gap_s = 0.6
        has_sid = any(m.get("sid") is not None for m in meta)
        session_chunks: List[List[tuple]] = []
        cur_chunk = [dense[0]]
        for i in range(1, len(dense)):
            new_chunk = False
            if has_sid:
                if meta[i - 1].get("sid") != meta[i].get("sid"):
                    new_chunk = True
            else:
                t0, t1 = meta[i - 1].get("t"), meta[i].get("t")
                if t0 is not None and t1 is not None and (t1 - t0) > gap_s:
                    new_chunk = True
            if new_chunk:
                session_chunks.append(cur_chunk)
                cur_chunk = [dense[i]]
            else:
                cur_chunk.append(dense[i])
        session_chunks.append(cur_chunk)
        session_chunks = [c for c in session_chunks if len(c) >= 2]
        if not session_chunks:
            return []

        # --- 3 & 4. split at gripper changes, compress, build plan ---
        plan: List[tuple] = []
        current_grip: Optional[float] = None

        for session_chunk in session_chunks:
            # Split at gripper transitions
            sub_segments: List[tuple] = []
            seg_start = 0
            seg_grip = session_chunk[0][1]
            for i in range(1, len(session_chunk)):
                if abs(session_chunk[i][1] - seg_grip) >= GRIP_THRESH:
                    sub_segments.append((session_chunk[seg_start:i], seg_grip))
                    seg_grip = session_chunk[i][1]
                    seg_start = i
            sub_segments.append((session_chunk[seg_start:], seg_grip))

            for seg_idx, (segment, grip_val) in enumerate(sub_segments):
                # Emit gripper if changed or first segment (initialise)
                if current_grip is None or abs(grip_val - current_grip) >= GRIP_THRESH:
                    plan.append(("gripper", grip_val))
                    current_grip = grip_val

                # Compress joint keyframes
                if len(segment) >= 2:
                    kf = self._compress_chunk(segment)
                    if kf and len(kf) >= 2:
                        for joints, _g in kf:
                            plan.append(("movej", joints))
                elif len(segment) == 1:
                    plan.append(("movej", segment[0][0]))

        return plan

    @staticmethod
    def _compress_chunk(poses_with_gripper: list) -> list:
        """Compress a chunk of (joints, gripper) into keyframes.

        Same algorithm as teach_record_widget._compress_chunk — dominant-joint
        segmentation with dither cancellation and subset merging.
        """
        round_dec = 2
        min_step = 0.01
        dom_debounce = 3
        gap_allow = 4
        minor_persist_frames = 4

        def qN(q):
            return [round(float(v), round_dec) for v in q]

        def joint_set(a, b):
            return frozenset(j for j in range(len(a)) if b[j] != a[j])

        normalized = []
        for p in poses_with_gripper:
            if isinstance(p, (list, tuple)) and len(p) == 2 and isinstance(p[0], (list, tuple)):
                normalized.append((list(p[0]), float(p[1])))
            elif isinstance(p, (list, tuple)) and len(p) >= 2 and isinstance(p[0], (int, float)):
                normalized.append((list(p), 0.0))
            else:
                normalized.append((list(p), 0.0))
        qseq = [(qN(p[0]), float(p[1])) for p in normalized]
        keyframes = [qseq[0]]
        prev = qseq[0]

        cur_dom = None
        pending_dom = None
        pending_count = 0
        gap_count = 0
        minor_persist = [0] * len(prev[0])

        def _close_run(at_pose):
            if keyframes[-1][0] != at_pose[0]:
                keyframes.append(at_pose)

        for i in range(1, len(qseq)):
            cur = qseq[i]
            d = [cur[0][j] - prev[0][j] for j in range(len(cur[0]))]
            changed = [j for j in range(len(d)) if d[j] != 0.0]

            if not changed:
                gap_count += 1
                if cur_dom is not None and gap_count > gap_allow:
                    _close_run(prev)
                    cur_dom = None
                    pending_dom = None
                    pending_count = 0
                    minor_persist = [0] * len(prev[0])
                    gap_count = 0
                prev = cur
                continue

            gap_count = 0
            dom = max(changed, key=lambda j: abs(d[j]))
            dom_mag = abs(d[dom])
            if dom_mag < min_step:
                prev = cur
                continue

            for j in range(len(d)):
                if j == dom:
                    minor_persist[j] = 0
                else:
                    minor_persist[j] = minor_persist[j] + 1 if abs(d[j]) >= min_step else 0

            minor_real = any(
                minor_persist[j] >= minor_persist_frames
                for j in range(len(minor_persist))
                if j != dom
            )

            if cur_dom is None:
                cur_dom = dom
                prev = cur
                continue

            if minor_real and dom != cur_dom:
                _close_run(prev)
                cur_dom = dom
                pending_dom = None
                pending_count = 0
                minor_persist = [0] * len(prev[0])
                prev = cur
                continue

            if dom != cur_dom:
                if pending_dom == dom:
                    pending_count += 1
                else:
                    pending_dom = dom
                    pending_count = 1
                if pending_count >= dom_debounce:
                    _close_run(prev)
                    cur_dom = dom
                    pending_dom = None
                    pending_count = 0
                    minor_persist = [0] * len(prev[0])
                prev = cur
                continue

            pending_dom = None
            pending_count = 0
            prev = cur

        if keyframes[-1][0] != prev[0]:
            keyframes.append(prev)

        if len(keyframes) < 2:
            return []

        # Post-merge: collapse segments with subset/superset joint sets
        merged = [keyframes[0]]
        last_set = None

        for k in keyframes[1:]:
            prev_m = merged[-1]
            js = joint_set(prev_m[0], k[0])
            if not js:
                continue
            if last_set is None:
                merged.append(k)
                last_set = js
                continue
            if js.issubset(last_set) or last_set.issubset(js):
                merged[-1] = k
                if len(merged) >= 2:
                    last_set = joint_set(merged[-2][0], merged[-1][0])
                else:
                    last_set = js
            else:
                merged.append(k)
                last_set = js

        # Dither cancel: remove A->B->A patterns
        cleaned = [merged[0]]
        i = 1
        while i < len(merged):
            if i + 1 < len(merged):
                A = cleaned[-1][0]
                C = merged[i + 1][0]
                if all(A[j] == C[j] for j in range(len(A))):
                    i += 2
                    continue
            cleaned.append(merged[i])
            i += 1

        return cleaned

    def _wait_lebai_close(self, robot, target: List[float],
                          tol: float = 0.05, timeout_s: float = 8.0) -> bool:
        """Wait until lebai joints are close to target."""
        from hardware.gantry_lebai.lebai_controller import LebaiController
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            if self._stop_event.is_set():
                return False
            try:
                # pylebai: get_actual_joint_positions() returns dict{"j1".."j6"}
                joints_dict = robot.get_actual_joint_positions() if robot else None
                cur = LebaiController._joints_dict_to_list(joints_dict) if joints_dict else None
                if isinstance(cur, list) and len(cur) >= len(target):
                    if all(abs(cur[i] - target[i]) <= tol for i in range(len(target))):
                        return True
            except Exception:
                pass
            time.sleep(0.05)
        return False

    # ------------------------------------------------------------------
    # Wait adapter
    # ------------------------------------------------------------------

    def _run_wait(self, action: ComponentAction):
        """Execute a wait/delay action (blocking, interruptible)."""
        params = getattr(action, 'parameters', {}) or {}
        duration = int(params.get("duration", 0))
        if duration <= 0:
            return
        logger.info(f"Wait action: sleeping {duration}s")
        self._interruptible_sleep(duration)
        logger.info(f"Wait action completed: {duration}s")

    # ------------------------------------------------------------------
    # Wok adapter
    # ------------------------------------------------------------------

    def _run_wok(self, action: ComponentAction):
        """Execute a wok command, with optional parameters."""
        cmd = action.wok_command
        wok = self._wok
        if not wok:
            logger.warning("Wok controller not available")
            return

        params = getattr(action, 'parameters', {}) or {}

        # Simple (parameterless) commands
        simple_commands = {
            "working_pos": wok.move_to_working_position,
            "pour_pos": wok.move_to_pour_position,
            "wash_pos": wok.move_to_wash_position,
            "loading_pos": wok.move_to_loading_position,
            "max_up": wok.move_to_max_up,
            "start_heating": wok.start_heating,
            "stop_heating": wok.stop_heating,
            "start_stirring": lambda: wok.start_stirring(50),
            "stop_stirring": wok.stop_stirring,
            "stop_recipe": wok.stop_auto_cooking,
        }

        if cmd in simple_commands:
            simple_commands[cmd]()
            logger.info(f"Wok command executed: {cmd}")
        elif cmd == "dispense_sauce":
            sauce_id = int(params.get("sauce_id", 1))
            pulse_value = int(params.get("pulse_value", 100))
            wok.dispense_sauce(sauce_id, pulse_value)
            logger.info(f"Wok sauce {sauce_id} dispensed (pulse={pulse_value})")
        elif cmd == "run_recipe":
            recipe_id = int(params.get("recipe_id", 1))
            timer = int(params.get("timer", 0))
            wok.run_recipe(recipe_id)
            logger.info(f"Wok recipe {recipe_id} started (timer={timer}s)")
            if timer > 0:
                # Block: wait for M0 OFF or timer expiry
                done = wok.wait_for_recipe_done(timeout=float(timer))
                if done:
                    logger.info(f"Wok recipe {recipe_id} completed naturally")
                else:
                    logger.info(f"Wok recipe {recipe_id} timer expired, stopping")
                    wok.stop_auto_cooking()
            else:
                # No timer — block until recipe finishes naturally
                done = wok.wait_for_recipe_done(timeout=3600.0)
                if done:
                    logger.info(f"Wok recipe {recipe_id} completed naturally")
                else:
                    logger.warning(f"Wok recipe {recipe_id} wait timed out (1h)")
                    wok.stop_auto_cooking()
            # Settle after recipe is done
            time.sleep(2)
        elif cmd == "wait_for_recipe_done":
            timeout = float(params.get("timeout", 600))
            done = wok.wait_for_recipe_done(timeout=timeout)
            if done:
                logger.info("Wok recipe finished (M0 OFF)")
            else:
                logger.warning("Wok recipe wait timed out")
        else:
            logger.warning(f"Unknown wok command: {cmd}")
