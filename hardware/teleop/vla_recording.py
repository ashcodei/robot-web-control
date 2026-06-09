"""
VLA Recording Module — Official LeRobot Pipeline
VLA数据录制模块 — 官方LeRobot流水线

Integrates with the official LeRobot recording pipeline:
    https://github.com/huggingface/lerobot/blob/main/src/lerobot/scripts/lerobot_record.py

Recording follows the record_loop() pattern:
    obs  = robot.get_observation()           # DualArmRobot
    ---- compute delta actions from obs ----
    robot.send_action(action)                # no-op — robot is teleoperated externally
    dataset.add_frame({...obs, ...action,
                       "task": instruction}) # LeRobotDataset
    # repeat per episode
    dataset.save_episode()
    # repeat per trial
    dataset.finalize()
    # optional: push_to_hub(...)

DualArmRobot (hardware/dual_arm/dual_arm_lerobot_robot.py) implements
lerobot.robots.robot.Robot for the existing DualArmController hardware.
"""

import math
import os
import json
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from app_core.logger import get_logger
from hardware.dual_arm.dual_arm_lerobot_robot import DualArmRobot, DualArmRobotConfig

logger = get_logger(__name__)


# ── LeRobot imports ────────────────────────────────────────────────────────────
LEROBOT_AVAILABLE = False

try:
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    LEROBOT_AVAILABLE = True
    logger.info("LeRobot dataset library loaded")
except ImportError:
    try:
        from lerobot.common.datasets.lerobot_dataset import LeRobotDataset  # older path
        LEROBOT_AVAILABLE = True
        logger.info("LeRobot dataset library loaded (legacy path)")
    except ImportError:
        logger.warning("lerobot not installed — VLA recording disabled")

# Uses lerobot's feature-building helpers when available, falls back locally.
try:
    from lerobot.datasets.pipeline_features import create_initial_features
    from lerobot.datasets.utils import combine_feature_dicts
    _HAS_PIPELINE_HELPERS = True
except ImportError:
    _HAS_PIPELINE_HELPERS = False

# pyarrow for list_episodes() (lerobot dependency, should always be present)
try:
    import pyarrow.parquet as pq
    PYARROW_AVAILABLE = True
except ImportError:
    PYARROW_AVAILABLE = False


# ── Helpers: build LeRobot features from robot specs ──────────────────────────

def _robot_feature_to_lerobot(key: str, value, use_videos: bool = True) -> dict:
    """
    Convert one entry from Robot.observation_features / action_features to the
    LeRobot dataset feature format.
        float        →  {"dtype": "float32", "shape": (1,)}
        (H, W, 3)    →  {"dtype": "video",   "shape": (H, W, 3)}
        (N,)         →  {"dtype": "float32", "shape": (N,)}
    """
    if value is float:
        return {"dtype": "float32", "shape": (1,)}
    shape = tuple(value)
    if len(shape) == 3 and shape[2] == 3:
        dtype = "video" if use_videos else "image"
        return {"dtype": dtype, "shape": shape, "names": ["height", "width", "channel"]}
    return {"dtype": "float32", "shape": shape}


def build_lerobot_features(robot: DualArmRobot, use_videos: bool = True) -> dict:
    """
    Build the full LeRobot dataset features dict from DualArmRobot's
    observation_features and action_features, mirroring what
    create_initial_features() + combine_feature_dicts() does in record().
    Observation keys get "observation." prefix, action keys get "action." prefix.
    """
    if _HAS_PIPELINE_HELPERS:
        try:
            obs_feat = create_initial_features(observation=robot.observation_features)
            act_feat = create_initial_features(action=robot.action_features)
            return combine_feature_dicts(obs_feat, act_feat)
        except Exception as e:
            logger.debug(f"lerobot pipeline helpers failed, using fallback: {e}")

    features: dict = {}
    for k, v in robot.observation_features.items():
        features[f"observation.{k}"] = _robot_feature_to_lerobot(k, v, use_videos)
    for k, v in robot.action_features.items():
        features[f"action.{k}"] = _robot_feature_to_lerobot(k, v, use_videos=False)
    return features


# ── State machine ──────────────────────────────────────────────────────────────

class RecordingState(Enum):
    IDLE      = "idle"
    RECORDING = "recording"
    PAUSED    = "paused"
    SAVING    = "saving"
    ERROR     = "error"


# ── VLAStep — UI-facing step snapshot (used by widget step callbacks) ──────────

@dataclass
class VLAStep:
    """
    Per-frame snapshot passed to UI step callbacks.
    Mirrors the attribute names expected by vla_recording_widget.py.
    Built from robot.get_observation() + computed actions each frame.
    """
    # Timestamps
    timestamp:        float = 0.0
    camera_timestamp: float = 0.0
    robot_timestamp:  float = 0.0

    # Active arm mode (informational)
    arm_side: str = "both"

    # Camera frames (RGB uint8 numpy arrays, H×W×3)
    desk_frame:  Optional[np.ndarray] = None
    wrist_frame: Optional[np.ndarray] = None

    # Left arm observations
    left_tcp_position:    List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    left_tcp_quaternion:  List[float] = field(default_factory=lambda: [1.0, 0.0, 0.0, 0.0])
    left_joint_positions: List[float] = field(default_factory=lambda: [0.0] * 7)
    left_joint_velocities:List[float] = field(default_factory=lambda: [0.0] * 7)
    left_joint_efforts:   List[float] = field(default_factory=lambda: [0.0] * 7)
    left_hand_state:      List[float] = field(default_factory=lambda: [0.0] * 6)

    # Right arm observations
    right_tcp_position:    List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    right_tcp_quaternion:  List[float] = field(default_factory=lambda: [1.0, 0.0, 0.0, 0.0])
    right_joint_positions: List[float] = field(default_factory=lambda: [0.0] * 7)
    right_joint_velocities:List[float] = field(default_factory=lambda: [0.0] * 7)
    right_joint_efforts:   List[float] = field(default_factory=lambda: [0.0] * 7)
    right_hand_state:      List[float] = field(default_factory=lambda: [0.0] * 6)

    # Left arm actions
    left_delta_position: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    left_delta_rotation: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    left_hand_command:   List[float] = field(default_factory=lambda: [0.0] * 6)

    # Right arm actions
    right_delta_position: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    right_delta_rotation: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    right_hand_command:   List[float] = field(default_factory=lambda: [0.0] * 6)

    # Gripper (right arm, LMG-90, normalised 0.0–1.0)
    gripper_position: float = 0.0
    gripper_torque:   float = 0.0
    gripper_command:  float = 0.0


def _obs_action_to_vlastep(
    obs: dict, action: dict, arm_side: str, ts: float
) -> VLAStep:
    """
    Build a VLAStep from a robot observation dict and action dict so that the
    existing widget step callbacks continue to work unchanged.
    """
    def _f(arr) -> List[float]:
        return arr.tolist() if isinstance(arr, np.ndarray) else list(arr)

    step = VLAStep(
        timestamp        = ts,
        arm_side         = arm_side,
        desk_frame       = obs.get("images.desk"),
        wrist_frame      = obs.get("images.wrist"),
        # observations
        left_tcp_position     = _f(obs.get("left.tcp_position",    [0.]*3)),
        left_tcp_quaternion   = _f(obs.get("left.tcp_quaternion",  [1.,0.,0.,0.])),
        left_joint_positions  = _f(obs.get("left.joint_positions",  [0.]*7)),
        left_joint_velocities = _f(obs.get("left.joint_velocities", [0.]*7)),
        left_joint_efforts    = _f(obs.get("left.joint_efforts",    [0.]*7)),
        left_hand_state       = _f(obs.get("left.hand_state",       [0.]*6)),
        right_tcp_position    = _f(obs.get("right.tcp_position",   [0.]*3)),
        right_tcp_quaternion  = _f(obs.get("right.tcp_quaternion", [1.,0.,0.,0.])),
        right_joint_positions = _f(obs.get("right.joint_positions",  [0.]*7)),
        right_joint_velocities= _f(obs.get("right.joint_velocities", [0.]*7)),
        right_joint_efforts   = _f(obs.get("right.joint_efforts",    [0.]*7)),
        right_hand_state      = _f(obs.get("right.hand_state",       [0.]*6)),
        gripper_position      = float(obs.get("gripper.position", 0.0)),
        gripper_torque        = float(obs.get("gripper.torque",   0.0)),
        # actions
        left_delta_position   = _f(action.get("left.delta_position",  [0.]*3)),
        left_delta_rotation   = _f(action.get("left.delta_rotation",  [0.]*3)),
        left_hand_command     = _f(action.get("left.hand_command",    [0.]*6)),
        right_delta_position  = _f(action.get("right.delta_position", [0.]*3)),
        right_delta_rotation  = _f(action.get("right.delta_rotation", [0.]*3)),
        right_hand_command    = _f(action.get("right.hand_command",   [0.]*6)),
        gripper_command       = float(action.get("gripper.command", 0.0)),
    )
    return step


# ── Episode dataclass (metadata) ──────────────────────────────────────────────

@dataclass
class VLAEpisode:
    task_id:              str   = ""
    language_instruction: str   = ""
    arm_side:             str   = "both"
    episode_num:          int   = 0
    trial_name:           str   = ""
    date_str:             str   = ""
    start_time:           float = 0.0
    end_time:             float = 0.0
    metadata:             Dict  = field(default_factory=dict)


# ── Recording manager ──────────────────────────────────────────────────────────

class VLARecordingManager:
    """
    VLA recording manager following the official LeRobot record_loop() pipeline.

    Ref: https://github.com/huggingface/lerobot/blob/main/src/lerobot/scripts/lerobot_record.py

    Workflow:
        1. Register hardware callbacks (set_*_source)
        2. start_new_trial()  — LeRobotDataset.create()
        3. start_episode()    — recording thread starts
              loop: robot.get_observation()
                    compute delta action
                    robot.send_action(action)        ← no-op
                    dataset.add_frame({**obs_frame,
                                       **act_frame,
                                       "task": ...}) ← official API
        4. stop_episode()     — dataset.save_episode()
        5. Repeat 3–4 for more episodes in the same trial
        6. finalize_trial()   — dataset.finalize()
        # optional: push_to_hub()

    Step callbacks receive (step: VLAStep, frame_index: int) — same as before.
    """

    def __init__(self, output_dir: str = "VLA_Recorded_Data"):
        if not LEROBOT_AVAILABLE:
            logger.error("lerobot not installed — VLA recording disabled")

        self.output_dir      = output_dir
        self.state           = RecordingState.IDLE
        self.record_rate     = 30.0
        self.record_interval = 1.0 / self.record_rate

        # Active LeRobotDataset (persists across episodes within a trial)
        self._lerobot_dataset: Optional[Any] = None
        self._current_trial_name: Optional[str] = None
        self._current_date_str:   Optional[str] = None

        # Finalized dataset — kept alive after finalize_trial() so push_to_hub() can use it
        self._finalized_dataset: Optional[Any] = None
        self._trial_finalized: bool = False

        # Hardware callbacks — same public interface as the original manager
        self._camera_source:            Optional[Callable] = None
        self._left_robot_state_source:  Optional[Callable] = None
        self._right_robot_state_source: Optional[Callable] = None
        self._teleop_action_source:     Optional[Callable] = None
        self._left_hand_state_source:   Optional[Callable] = None
        self._right_hand_state_source:  Optional[Callable] = None
        self._gripper_state_source:     Optional[Callable] = None

        # DualArmRobot wrapping the callbacks (rebuilt when any callback changes)
        self._robot: Optional[DualArmRobot] = None

        # Current episode
        self.current_episode:  Optional[VLAEpisode] = None
        self.current_arm_side: str = "both"

        # Recording thread
        self._recording_thread: Optional[threading.Thread] = None
        self._stop_recording    = False
        self._pause_recording   = False

        # Step callbacks — called each frame with (VLAStep, frame_index)
        self._step_callbacks: List[Callable] = []

        # Delta-action state (previous observation for diff)
        self._prev_left_tcp_pos:   Optional[np.ndarray] = None
        self._prev_left_tcp_quat:  Optional[np.ndarray] = None
        self._prev_right_tcp_pos:  Optional[np.ndarray] = None
        self._prev_right_tcp_quat: Optional[np.ndarray] = None

        os.makedirs(output_dir, exist_ok=True)

    # ── Configuration ──────────────────────────────────────────────────────────

    def configure(self, record_rate: float = 30.0):
        self.record_rate     = record_rate
        self.record_interval = 1.0 / record_rate

    # ── Hardware callback registration (same public API as before) ─────────────

    def set_camera_source(self, callback: Callable):
        self._camera_source = callback
        self._rebuild_robot()

    def set_left_robot_state_source(self, callback: Callable):
        self._left_robot_state_source = callback
        self._rebuild_robot()

    def set_right_robot_state_source(self, callback: Callable):
        self._right_robot_state_source = callback
        self._rebuild_robot()

    def set_teleop_action_source(self, callback: Callable):
        """Hand command source (optional)."""
        self._teleop_action_source = callback

    def set_left_hand_state_source(self, callback: Callable):
        self._left_hand_state_source = callback
        self._rebuild_robot()

    def set_right_hand_state_source(self, callback: Callable):
        self._right_hand_state_source = callback
        self._rebuild_robot()

    def set_gripper_state_source(self, callback: Callable):
        self._gripper_state_source = callback
        self._rebuild_robot()

    def add_step_callback(self, callback: Callable):
        """Register callback called each frame with (step: VLAStep, frame_index: int)."""
        self._step_callbacks.append(callback)

    def remove_step_callback(self, callback: Callable):
        if callback in self._step_callbacks:
            self._step_callbacks.remove(callback)

    def _rebuild_robot(self):
        """Recreate DualArmRobot whenever a callback changes."""
        self._robot = DualArmRobot(
            DualArmRobotConfig(),
            camera_source      = self._camera_source,
            left_state_source  = self._left_robot_state_source,
            right_state_source = self._right_robot_state_source,
            left_hand_source   = self._left_hand_state_source,
            right_hand_source  = self._right_hand_state_source,
            gripper_source     = self._gripper_state_source,
        )

    def _ensure_robot(self) -> DualArmRobot:
        if self._robot is None:
            self._rebuild_robot()
        assert self._robot is not None
        if not self._robot.is_connected:
            self._robot.connect()
        return self._robot

    # ── Trial management ───────────────────────────────────────────────────────

    def _get_date_str(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def _get_trial_name(self, force_new: bool = False) -> str:
        date_dir = os.path.join(self.output_dir, "LeRobot", self._get_date_str())
        existing = sorted(
            [d for d in os.listdir(date_dir) if os.path.isdir(os.path.join(date_dir, d))]
        ) if os.path.exists(date_dir) else []
        if not force_new and existing:
            return existing[-1]
        n = len(existing) + 1
        return {1: "1st", 2: "2nd", 3: "3rd"}.get(n, f"{n}th")

    def _lerobot_root(self) -> Path:
        return Path(self.output_dir) / "LeRobot"

    def _create_dataset(self, date_str: str, trial_name: str) -> Any:
        """
        LeRobotDataset.create() — mirrors record() in lerobot_record.py.
        Features derived from DualArmRobot.observation_features / action_features.
        """
        if not LEROBOT_AVAILABLE:
            raise RuntimeError("lerobot is not installed")

        robot    = self._ensure_robot()
        features = build_lerobot_features(robot, use_videos=True)
        repo_id  = f"{date_str}/{trial_name}"
        root     = self._lerobot_root()

        logger.info(
            f"Creating LeRobotDataset — repo_id='{repo_id}', root={root}, "
            f"fps={int(self.record_rate)}, robot={robot.name}"
        )
        return LeRobotDataset.create(
            repo_id    = repo_id,
            fps        = int(self.record_rate),
            root       = root,
            robot_type = robot.name,
            features   = features,
            use_videos = True,
        )

    def start_new_trial(self) -> str:
        """
        Finalises any active dataset then calls LeRobotDataset.create() for a
        new trial folder. Returns the trial name ("1st", "2nd", …).
        """
        if self._lerobot_dataset is not None:
            self.finalize_trial()
        self._finalized_dataset = None
        self._trial_finalized   = False

        date_str   = self._get_date_str()
        trial_name = self._get_trial_name(force_new=True)
        self._current_date_str   = date_str
        self._current_trial_name = trial_name
        self._lerobot_dataset    = self._create_dataset(date_str, trial_name)
        logger.info(f"New trial: {trial_name} ({date_str})")
        return trial_name

    def finalize_trial(self):
        """
        dataset.finalize() — mirrors the finally block in lerobot_record.py record().
        Must be called before push_to_hub(). After this a new trial must be started.
        Keeps a reference in _finalized_dataset so push_to_hub() can still use it.
        """
        if self._lerobot_dataset is None:
            return
        try:
            logger.info(f"Finalizing trial '{self._current_trial_name}' …")
            self._lerobot_dataset.finalize()
            logger.info("Trial finalized")
            self._finalized_dataset = self._lerobot_dataset
            self._trial_finalized   = True
        except Exception as e:
            logger.error(f"finalize() error: {e}")
        finally:
            self._lerobot_dataset    = None
            self._current_trial_name = None
            self._current_date_str   = None

    # ── Episode recording ──────────────────────────────────────────────────────

    def start_episode(
        self,
        task_id: str,
        language_instruction: str,
        arm_side: str = "both",
        metadata: Optional[Dict] = None,
    ) -> bool:
        if self.state != RecordingState.IDLE:
            logger.warning(f"Cannot start: state is {self.state.value}")
            return False
        if not LEROBOT_AVAILABLE:
            logger.error("lerobot not installed")
            return False

        if self._lerobot_dataset is None:
            date_str   = self._get_date_str()
            trial_name = self._get_trial_name(force_new=False)
            self._current_date_str   = date_str
            self._current_trial_name = trial_name
            try:
                self._lerobot_dataset = self._create_dataset(date_str, trial_name)
            except Exception as e:
                logger.error(f"Failed to create LeRobotDataset: {e}")
                return False

        self.current_arm_side = arm_side
        self.current_episode  = VLAEpisode(
            task_id              = task_id,
            language_instruction = language_instruction,
            arm_side             = arm_side,
            episode_num          = self._lerobot_dataset.num_episodes,
            trial_name           = self._current_trial_name,
            date_str             = self._current_date_str,
            start_time           = time.time(),
            metadata             = metadata or {},
        )

        self._prev_left_tcp_pos   = None
        self._prev_left_tcp_quat  = None
        self._prev_right_tcp_pos  = None
        self._prev_right_tcp_quat = None

        self._stop_recording  = False
        self._pause_recording = False
        self.state            = RecordingState.RECORDING
        self._recording_thread = threading.Thread(
            target=self._recording_loop, daemon=True
        )
        self._recording_thread.start()

        logger.info(
            f"Started episode {self.current_episode.episode_num} "
            f"task='{task_id}' arm={arm_side} trial={self._current_trial_name}"
        )
        return True

    def stop_episode(self) -> Optional[VLAEpisode]:
        """
        Stop recording and call dataset.save_episode() asynchronously.
        Mirrors: lerobot_record.py → dataset.save_episode()
        """
        if self.state not in (RecordingState.RECORDING, RecordingState.PAUSED):
            logger.warning(f"Cannot stop: state is {self.state.value}")
            return None

        self._stop_recording = True
        self.state           = RecordingState.SAVING
        episode              = self.current_episode
        self.current_episode = None
        episode.end_time     = time.time()

        rec_thread            = self._recording_thread
        self._recording_thread = None
        dataset               = self._lerobot_dataset

        def _save():
            try:
                if rec_thread:
                    rec_thread.join(timeout=5.0)
                logger.info(f"Saving episode {episode.episode_num} …")
                dataset.save_episode()
                logger.info(
                    f"Episode {episode.episode_num} saved "
                    f"({dataset.num_episodes} total in trial)"
                )
            except Exception as e:
                logger.error(f"save_episode() error: {e}")
                import traceback; traceback.print_exc()
            finally:
                self.state = RecordingState.IDLE

        threading.Thread(target=_save, daemon=True).start()
        return episode

    def pause_episode(self):
        if self.state == RecordingState.RECORDING:
            self._pause_recording = True
            self.state            = RecordingState.PAUSED

    def resume_episode(self):
        if self.state == RecordingState.PAUSED:
            self._pause_recording = False
            self.state            = RecordingState.RECORDING

    def discard_episode(self):
        """
        Abort without saving. Calls dataset.clear_episode_buffer() —
        the official API from lerobot_record.py (events["rerecord_episode"] branch).
        """
        if self.state not in (RecordingState.RECORDING, RecordingState.PAUSED, RecordingState.SAVING):
            return
        self._stop_recording = True
        if self._recording_thread:
            self._recording_thread.join(timeout=2.0)
            self._recording_thread = None

        if self._lerobot_dataset is not None:
            try:
                self._lerobot_dataset.clear_episode_buffer()
            except AttributeError:
                buf = getattr(self._lerobot_dataset, "episode_buffer",
                              getattr(self._lerobot_dataset, "_episode_buffer", None))
                if buf is not None and hasattr(buf, "clear"):
                    buf.clear()

        ep_num               = self.current_episode.episode_num if self.current_episode else 0
        self.current_episode = None
        self.state           = RecordingState.IDLE
        logger.info(f"Discarded episode {ep_num}")

    # ── Hub push ───────────────────────────────────────────────────────────────
    # Ref: lerobot_record.py → dataset.push_to_hub(...)

    def push_to_hub(
        self,
        hub_repo_id: str,
        tags: Optional[List[str]] = None,
        private: bool = False,
    ) -> bool:
        """
        Push the finalized dataset to Hugging Face Hub.

        Requirements:
            - huggingface-cli login  (run once, stores token)
            - hub_repo_id: valid HF repo id, e.g. "myusername/my-dataset"
            - call finalize_trial() first — push_to_hub() will refuse otherwise

        Returns True on success, False on failure.
        """
        # Safety: must have a finalized dataset
        if not self._trial_finalized or self._finalized_dataset is None:
            if self._lerobot_dataset is not None:
                logger.error(
                    "Trial has not been finalized. Call finalize_trial() before push_to_hub()."
                )
            else:
                logger.error(
                    "No dataset to push. Record episodes and call finalize_trial() first."
                )
            return False

        # Safety: must not be recording right now
        if self.state != RecordingState.IDLE:
            logger.error("Cannot push while recording is active. Stop recording first.")
            return False

        # Safety: check HuggingFace login before attempting upload
        try:
            import importlib
            hf_hub = importlib.import_module("huggingface_hub")
            hf_hub.whoami()  # raises if token missing / invalid
        except ModuleNotFoundError:
            logger.warning("huggingface_hub not installed — skipping login check")
        except Exception as e:
            logger.error(
                f"Not logged in to Hugging Face ({type(e).__name__}: {e})\n"
                "Run:  huggingface-cli login"
            )
            return False

        try:
            logger.info(f"Pushing dataset to hub: {hub_repo_id} …")
            self._finalized_dataset.push_to_hub(
                repo_id = hub_repo_id,
                tags    = tags,
                private = private,
            )
            logger.info(f"Successfully pushed to: {hub_repo_id}")
            # Clear after successful push so it can't be pushed twice by accident
            self._finalized_dataset = None
            self._trial_finalized   = False
            return True
        except Exception as e:
            logger.error(f"push_to_hub() failed: {e}")
            return False

    # ── Recording loop — mirrors record_loop() from lerobot_record.py ─────────

    def _recording_loop(self):
        """
        Core loop following the LeRobot record_loop() pattern:

            obs  = robot.get_observation()
            obs  = robot_observation_processor(obs)      ← identity (no-op here)
            act  = teleop.get_action()                   ← we compute delta from obs
            act  = teleop_action_processor((act, obs))   ← identity
            act  = robot_action_processor((act, obs))    ← identity
            robot.send_action(act)                       ← no-op
            dataset.add_frame({**obs_frame, **act_frame, "task": task})

        After the loop: stop_episode() calls dataset.save_episode().
        """
        robot     = self._ensure_robot()
        last_time = time.perf_counter()
        frame_idx = 0

        while not self._stop_recording:
            if self._pause_recording:
                time.sleep(0.01)
                continue

            now = time.perf_counter()
            if now - last_time < self.record_interval:
                time.sleep(self.record_interval - (now - last_time))
                continue

            last_time = time.perf_counter()

            try:
                if self.current_episode is None:
                    break

                # ── get_observation() ────────────────────────────────────
                obs = robot.get_observation()

                # ── compute delta action ─────────────────────────────────
                action = self._compute_action(obs)

                # ── send_action() (no-op — robot is teleoperated) ────────
                robot.send_action(action)

                # ── add_frame() ──────────────────────────────────────────
                # Mirrors record_loop():
                #   obs_frame = build_dataset_frame(features, obs, prefix="observation")
                #   act_frame = build_dataset_frame(features, act, prefix="action")
                #   dataset.add_frame({**obs_frame, **act_frame, "task": task})
                obs_frame = {f"observation.{k}": v for k, v in obs.items()}
                act_frame = {f"action.{k}": v for k, v in action.items()}
                frame = {
                    **obs_frame,
                    **act_frame,
                    "task": self.current_episode.language_instruction,
                }
                self._lerobot_dataset.add_frame(frame)
                frame_idx += 1

                # ── step callbacks (VLAStep, frame_index) — widget compat ─
                if self._step_callbacks:
                    step = _obs_action_to_vlastep(
                        obs, action, self.current_arm_side, time.time()
                    )
                    for cb in self._step_callbacks:
                        try:
                            cb(step, frame_idx)
                        except Exception as e:
                            logger.warning(f"Step callback error: {e}")
                    # free frame copies after callbacks are done
                    step.desk_frame  = None
                    step.wrist_frame = None

            except Exception as e:
                logger.error(f"Recording loop error at frame {frame_idx}: {e}")
                import traceback; traceback.print_exc()

    def _compute_action(self, obs: dict) -> dict:
        """
        Compute action from consecutive observations (delta position / rotation).
        In LeRobot's paradigm a Teleoperator generates actions; here we derive them
        from the robot's own state since it is externally teleoperated.
        Hand/gripper commands come from the teleop source when available.
        """
        action: dict = {}

        # Left arm deltas
        lpos  = obs["left.tcp_position"]
        lquat = obs["left.tcp_quaternion"]
        if self._prev_left_tcp_pos is not None and self._prev_left_tcp_quat is not None:
            action["left.delta_position"] = (lpos - self._prev_left_tcp_pos).astype(np.float32)
            action["left.delta_rotation"] = self._quat_delta(self._prev_left_tcp_quat, lquat)
        else:
            action["left.delta_position"] = np.zeros(3, dtype=np.float32)
            action["left.delta_rotation"] = np.zeros(3, dtype=np.float32)
        self._prev_left_tcp_pos  = lpos.copy()
        self._prev_left_tcp_quat = lquat.copy()

        # Right arm deltas
        rpos  = obs["right.tcp_position"]
        rquat = obs["right.tcp_quaternion"]
        if self._prev_right_tcp_pos is not None and self._prev_right_tcp_quat is not None:
            action["right.delta_position"] = (rpos - self._prev_right_tcp_pos).astype(np.float32)
            action["right.delta_rotation"] = self._quat_delta(self._prev_right_tcp_quat, rquat)
        else:
            action["right.delta_position"] = np.zeros(3, dtype=np.float32)
            action["right.delta_rotation"] = np.zeros(3, dtype=np.float32)
        self._prev_right_tcp_pos  = rpos.copy()
        self._prev_right_tcp_quat = rquat.copy()

        # Hand/gripper commands
        left_hand   = np.zeros(6, dtype=np.float32)
        right_hand  = np.zeros(6, dtype=np.float32)
        gripper_cmd = 0.0

        if self._teleop_action_source:
            try:
                t = self._teleop_action_source()
                if t:
                    lhc = t.get("left_hand_command",  [0.] * 6)
                    rhc = t.get("right_hand_command", [0.] * 6)
                    left_hand   = np.array(lhc[:6], dtype=np.float32)
                    right_hand  = np.array(rhc[:6], dtype=np.float32)
                    gripper_cmd = float(t.get("gripper_command", 0.0))
            except Exception as e:
                logger.debug(f"Teleop source error: {e}")
        else:
            # No separate teleop: mirror current hand state as command
            left_hand   = obs.get("left.hand_state",  np.zeros(6, dtype=np.float32)).copy()
            right_hand  = obs.get("right.hand_state", np.zeros(6, dtype=np.float32)).copy()
            gripper_cmd = float(obs.get("gripper.position", 0.0))

        action["left.hand_command"]  = left_hand
        action["right.hand_command"] = right_hand
        action["gripper.command"]    = np.array([gripper_cmd], dtype=np.float32)

        return action

    # ── Math helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _quat_delta(q_cur: np.ndarray, q_tgt: np.ndarray) -> np.ndarray:
        """Axis-angle delta between two unit quaternions [w, x, y, z]."""
        q_inv = np.array([q_cur[0], -q_cur[1], -q_cur[2], -q_cur[3]])
        w1, x1, y1, z1 = q_tgt
        w2, x2, y2, z2 = q_inv
        q_d = np.array([
            w1*w2 - x1*x2 - y1*y2 - z1*z2,
            w1*x2 + x1*w2 + y1*z2 - z1*y2,
            w1*y2 - x1*z2 + y1*w2 + z1*x2,
            w1*z2 + x1*y2 - y1*x2 + z1*w2,
        ])
        w, x, y, z = q_d
        angle = 2.0 * math.acos(float(np.clip(w, -1.0, 1.0)))
        if abs(angle) < 1e-6:
            return np.zeros(3, dtype=np.float32)
        s = math.sin(angle / 2.0)
        if abs(s) < 1e-6:
            return np.zeros(3, dtype=np.float32)
        return np.array([x/s * angle, y/s * angle, z/s * angle], dtype=np.float32)

    # ── Dataset browsing ───────────────────────────────────────────────────────

    def list_dates(self) -> List[str]:
        base = os.path.join(self.output_dir, "LeRobot")
        if not os.path.exists(base):
            return []
        return sorted(
            [d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))],
            reverse=True,
        )

    def list_trials(self, date_str: str) -> List[str]:
        d = os.path.join(self.output_dir, "LeRobot", date_str)
        if not os.path.exists(d):
            return []
        return sorted([t for t in os.listdir(d) if os.path.isdir(os.path.join(d, t))])

    def list_episodes(self, date_str: Optional[str] = None, trial_name: Optional[str] = None) -> List[Dict]:
        if not PYARROW_AVAILABLE:
            return []
        base = os.path.join(self.output_dir, "LeRobot")
        if not os.path.exists(base):
            return []

        if date_str and trial_name:
            trial_dirs = [(date_str, trial_name, os.path.join(base, date_str, trial_name))]
        elif date_str:
            dp = os.path.join(base, date_str)
            trial_dirs = [
                (date_str, t, os.path.join(dp, t))
                for t in (os.listdir(dp) if os.path.exists(dp) else [])
                if os.path.isdir(os.path.join(dp, t))
            ]
        else:
            trial_dirs = []
            for d in os.listdir(base):
                dp = os.path.join(base, d)
                if os.path.isdir(dp):
                    for t in os.listdir(dp):
                        tp = os.path.join(dp, t)
                        if os.path.isdir(tp):
                            trial_dirs.append((d, t, tp))

        episodes = []
        for date, trial, tpath in trial_dirs:
            fps = int(self.record_rate)
            info_path = os.path.join(tpath, "meta", "info.json")
            if os.path.exists(info_path):
                try:
                    with open(info_path) as f:
                        fps = json.load(f).get("fps", fps)
                except Exception:
                    pass

            tasks: Dict[int, str] = {}
            # v3.0: tasks.parquet (pandas DataFrame with task as index)
            tasks_pq_path = os.path.join(tpath, "meta", "tasks.parquet")
            tasks_jsonl_path = os.path.join(tpath, "meta", "tasks.jsonl")
            if PYARROW_AVAILABLE and os.path.exists(tasks_pq_path):
                try:
                    t_table = pq.read_table(tasks_pq_path)
                    if "task_index" in t_table.schema.names:
                        indices = t_table.column("task_index").to_pylist()
                        # task text is stored as the __index_level_0__ column
                        if "__index_level_0__" in t_table.schema.names:
                            texts = t_table.column("__index_level_0__").to_pylist()
                        else:
                            texts = [""] * len(indices)
                        for idx, txt in zip(indices, texts):
                            tasks[idx] = txt
                except Exception:
                    pass
            elif os.path.exists(tasks_jsonl_path):
                # v2.1 fallback
                try:
                    with open(tasks_jsonl_path) as f:
                        for line in f:
                            t = json.loads(line.strip())
                            tasks[t.get("task_index", 0)] = t.get("task", "")
                except Exception:
                    pass

            data_dir = os.path.join(tpath, "data", "chunk-000")
            if not os.path.exists(data_dir):
                continue
            for pq_file in sorted(f for f in os.listdir(data_dir) if f.endswith(".parquet")):
                fpath = os.path.join(data_dir, pq_file)
                try:
                    ep_num    = int(pq_file.replace("file-", "").replace(".parquet", ""))
                    table     = pq.read_table(fpath)
                    num_steps = len(table)
                    task_idx  = (
                        table.column("task_index")[0].as_py()
                        if "task_index" in table.schema.names else 0
                    )
                    episodes.append({
                        "filepath":             fpath,
                        "filename":             pq_file,
                        "date_str":             date,
                        "trial_name":           trial,
                        "episode_num":          ep_num,
                        "num_steps":            num_steps,
                        "duration":             num_steps / max(fps, 1),
                        "arm_side":             "both",
                        "language_instruction": tasks.get(task_idx, ""),
                        "task_id":              "",
                        "date":                 date,
                    })
                except Exception as e:
                    logger.debug(f"Error reading {pq_file}: {e}")
        return episodes

    def delete_episode(self, date_str: str, trial_name: str, episode_num: int) -> bool:
        trial_dir = os.path.join(self.output_dir, "LeRobot", date_str, trial_name)
        deleted   = False
        pq_path   = os.path.join(trial_dir, "data", "chunk-000", f"file-{episode_num:03d}.parquet")
        if os.path.exists(pq_path):
            os.remove(pq_path)
            deleted = True
        for cam in ("observation.images.desk", "observation.images.wrist"):
            vid = os.path.join(trial_dir, "videos", cam, "chunk-000", f"file-{episode_num:03d}.mp4")
            if os.path.exists(vid):
                os.remove(vid)
        return deleted

    def delete_trial(self, date_str: str, trial_name: str) -> bool:
        import shutil
        tpath = os.path.join(self.output_dir, "LeRobot", date_str, trial_name)
        if os.path.exists(tpath):
            shutil.rmtree(tpath)
            logger.info(f"Deleted trial: {tpath}")
            return True
        return False
