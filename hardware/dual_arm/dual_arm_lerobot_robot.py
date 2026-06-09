"""
DualArmRobot — Official LeRobot Robot Interface
双臂机器人 — 官方LeRobot Robot接口

Implements lerobot.robots.robot.Robot for the dual 7-DOF arm system so that
the existing DualArmController hardware integrates with the official LeRobot
recording pipeline (record_loop / record).

Ref: https://github.com/huggingface/lerobot/blob/main/src/lerobot/robots/robot.py
     https://github.com/huggingface/lerobot/blob/main/src/lerobot/scripts/lerobot_record.py
"""

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np

from app_core.logger import get_logger

logger = get_logger(__name__)

# ── LeRobot imports ────────────────────────────────────────────────────────────
try:
    from lerobot.robots.robot import Robot
    from lerobot.robots.config import RobotConfig
    LEROBOT_AVAILABLE = True
except ImportError:
    # Provide stub base classes so the module is importable even without lerobot
    LEROBOT_AVAILABLE = False

    import abc

    class RobotConfig:  # type: ignore[no-redef]
        id: str = "dual_arm_7dof"
        calibration_dir: Optional[Path] = None

    class Robot(abc.ABC):  # type: ignore[no-redef]
        def __init__(self, config):
            self.id = getattr(config, "id", "dual_arm_7dof")
            self.calibration_dir = Path(".")
            self.calibration = {}

        @property
        @abc.abstractmethod
        def observation_features(self) -> dict: ...
        @property
        @abc.abstractmethod
        def action_features(self) -> dict: ...
        @property
        @abc.abstractmethod
        def is_connected(self) -> bool: ...
        @abc.abstractmethod
        def connect(self, calibrate: bool = True) -> None: ...
        @property
        @abc.abstractmethod
        def is_calibrated(self) -> bool: ...
        @abc.abstractmethod
        def calibrate(self) -> None: ...
        @abc.abstractmethod
        def configure(self) -> None: ...
        @abc.abstractmethod
        def get_observation(self) -> dict: ...
        @abc.abstractmethod
        def send_action(self, action: dict) -> dict: ...
        @abc.abstractmethod
        def disconnect(self) -> None: ...


# ── Config ─────────────────────────────────────────────────────────────────────

@dataclass
class DualArmRobotConfig(RobotConfig):
    """
    Configuration dataclass for DualArmRobot.
    No motor-bus configs needed — hardware is managed by DualArmController.
    """
    id: str = "dual_arm_7dof"
    calibration_dir: Optional[Path] = None


# ── Robot implementation ───────────────────────────────────────────────────────

class DualArmRobot(Robot):
    """
    LeRobot-compatible Robot implementation for the dual 7-DOF arm system.

    Wraps the existing callback-based hardware interface (DualArmController,
    cameras, LinkerHand, gripper) into the official Robot API so the system can
    be driven by lerobot's record_loop() / record() pipeline.

    Observation keys (no prefix — "observation." is added by the pipeline):
        images.desk              (H, W, 3)  uint8 RGB
        images.wrist             (H, W, 3)  uint8 RGB
        left.tcp_position        (3,)
        left.tcp_quaternion      (4,)       [w, x, y, z]
        left.joint_positions     (7,)
        left.joint_velocities    (7,)
        left.joint_efforts       (7,)
        left.hand_state          (6,)
        right.tcp_position       (3,)
        right.tcp_quaternion     (4,)
        right.joint_positions    (7,)
        right.joint_velocities   (7,)
        right.joint_efforts      (7,)
        right.hand_state         (6,)
        gripper.position         float      normalised 0–1
        gripper.torque           float      normalised 0–1

    Action keys (no prefix — "action." is added by the pipeline):
        left.delta_position      (3,)
        left.delta_rotation      (3,)       axis-angle
        left.hand_command        (6,)
        right.delta_position     (3,)
        right.delta_rotation     (3,)
        right.hand_command       (6,)
        gripper.command          float      normalised 0–1
    """

    name          = "dual_arm_7dof"
    config_class  = DualArmRobotConfig

    def __init__(
        self,
        config: DualArmRobotConfig,
        *,
        camera_source:       Optional[Callable] = None,
        left_state_source:   Optional[Callable] = None,
        right_state_source:  Optional[Callable] = None,
        left_hand_source:    Optional[Callable] = None,
        right_hand_source:   Optional[Callable] = None,
        gripper_source:      Optional[Callable] = None,
    ):
        """
        Args:
            config:              DualArmRobotConfig instance.
            camera_source:       Callable → Dict[int, frame]  (0=desk, 1=wrist)
            left_state_source:   Callable → dict  (tcp_position, joint_positions, …)
            right_state_source:  Callable → dict
            left_hand_source:    Callable → list[float] (6-DOF)
            right_hand_source:   Callable → list[float] (6-DOF)
            gripper_source:      Callable → dict  (position, torque, target_opening; 0-100)
        """
        super().__init__(config)

        self._camera_source      = camera_source
        self._left_state_source  = left_state_source
        self._right_state_source = right_state_source
        self._left_hand_source   = left_hand_source
        self._right_hand_source  = right_hand_source
        self._gripper_source     = gripper_source

        self._connected = False
        self._cam_w     = 640
        self._cam_h     = 480

    # ── LeRobot Robot interface ────────────────────────────────────────────────

    @property
    def observation_features(self) -> dict:
        """
        Describes the structure of what get_observation() returns.
        Tuple values = array shape; float = scalar.
        The "observation." prefix is added by the LeRobot pipeline.
        """
        return {
            # Camera images — shape (H, W, C)
            "images.desk":            (self._cam_h, self._cam_w, 3),
            "images.wrist":           (self._cam_h, self._cam_w, 3),
            # Left arm proprioception
            "left.tcp_position":      (3,),
            "left.tcp_quaternion":    (4,),
            "left.joint_positions":   (7,),
            "left.joint_velocities":  (7,),
            "left.joint_efforts":     (7,),
            "left.hand_state":        (6,),
            # Right arm proprioception
            "right.tcp_position":     (3,),
            "right.tcp_quaternion":   (4,),
            "right.joint_positions":  (7,),
            "right.joint_velocities": (7,),
            "right.joint_efforts":    (7,),
            "right.hand_state":       (6,),
            # Gripper (right arm, LMG-90)
            "gripper.position":       float,
            "gripper.torque":         float,
        }

    @property
    def action_features(self) -> dict:
        """
        Describes the structure of what send_action() accepts.
        The "action." prefix is added by the LeRobot pipeline.
        """
        return {
            "left.delta_position":  (3,),
            "left.delta_rotation":  (3,),
            "left.hand_command":    (6,),
            "right.delta_position": (3,),
            "right.delta_rotation": (3,),
            "right.hand_command":   (6,),
            "gripper.command":      float,
        }

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self, calibrate: bool = True) -> None:
        """
        Mark robot as connected and probe camera resolution.
        Actual hardware connection is managed by DualArmController / GUI.
        """
        self._probe_camera_resolution()
        self._connected = True
        logger.info(f"DualArmRobot connected (cam={self._cam_w}×{self._cam_h})")

    @property
    def is_calibrated(self) -> bool:
        return True  # Calibration handled by DualArmController

    def calibrate(self) -> None:
        pass  # Handled by DualArmController

    def configure(self) -> None:
        pass  # Hardware already configured by DualArmController

    def get_observation(self) -> dict:
        """
        Read all sensor modalities and return as a flat dict.
        Keys match observation_features (without "observation." prefix).
        All numpy arrays are float32 except images (uint8).
        """
        blank = np.zeros((self._cam_h, self._cam_w, 3), dtype=np.uint8)
        obs: dict = {
            "images.desk":            blank.copy(),
            "images.wrist":           blank.copy(),
            "left.tcp_position":      np.zeros(3,  dtype=np.float32),
            "left.tcp_quaternion":    np.array([1., 0., 0., 0.], dtype=np.float32),
            "left.joint_positions":   np.zeros(7,  dtype=np.float32),
            "left.joint_velocities":  np.zeros(7,  dtype=np.float32),
            "left.joint_efforts":     np.zeros(7,  dtype=np.float32),
            "left.hand_state":        np.zeros(6,  dtype=np.float32),
            "right.tcp_position":     np.zeros(3,  dtype=np.float32),
            "right.tcp_quaternion":   np.array([1., 0., 0., 0.], dtype=np.float32),
            "right.joint_positions":  np.zeros(7,  dtype=np.float32),
            "right.joint_velocities": np.zeros(7,  dtype=np.float32),
            "right.joint_efforts":    np.zeros(7,  dtype=np.float32),
            "right.hand_state":       np.zeros(6,  dtype=np.float32),
            "gripper.position":       np.zeros(1, dtype=np.float32),
            "gripper.torque":         np.zeros(1, dtype=np.float32),
        }

        # ── Camera frames ──────────────────────────────────────────────────
        if self._camera_source:
            try:
                frames = self._camera_source()
                if frames:
                    for idx, key in ((0, "images.desk"), (1, "images.wrist")):
                        fd = frames.get(idx)
                        if fd is not None:
                            arr = fd[1] if isinstance(fd, tuple) else fd
                            if arr is not None:
                                obs[key] = (
                                    arr if arr.dtype == np.uint8
                                    else cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
                                )
            except Exception as e:
                logger.debug(f"Camera source error: {e}")

        # ── Left arm ───────────────────────────────────────────────────────
        if self._left_state_source:
            try:
                s = self._left_state_source()
                if s:
                    obs["left.tcp_position"]    = self._parse_pos(s.get("tcp_position"))
                    obs["left.tcp_quaternion"]  = self._parse_quat(s)
                    obs["left.joint_positions"] = self._parse_joints(s, "joint_positions")
                    obs["left.joint_velocities"]= self._parse_joints(s, "joint_velocities", "velocities")
                    obs["left.joint_efforts"]   = self._parse_joints(s, "joint_efforts",    "efforts")
            except Exception as e:
                logger.debug(f"Left robot state error: {e}")

        if self._left_hand_source:
            try:
                h = self._left_hand_source()
                if h and len(h) >= 6:
                    obs["left.hand_state"] = np.array(h[:6], dtype=np.float32)
            except Exception as e:
                logger.debug(f"Left hand source error: {e}")

        # ── Right arm ──────────────────────────────────────────────────────
        if self._right_state_source:
            try:
                s = self._right_state_source()
                if s:
                    obs["right.tcp_position"]    = self._parse_pos(s.get("tcp_position"))
                    obs["right.tcp_quaternion"]  = self._parse_quat(s)
                    obs["right.joint_positions"] = self._parse_joints(s, "joint_positions")
                    obs["right.joint_velocities"]= self._parse_joints(s, "joint_velocities", "velocities")
                    obs["right.joint_efforts"]   = self._parse_joints(s, "joint_efforts",    "efforts")
            except Exception as e:
                logger.debug(f"Right robot state error: {e}")

        if self._right_hand_source:
            try:
                h = self._right_hand_source()
                if h and len(h) >= 6:
                    obs["right.hand_state"] = np.array(h[:6], dtype=np.float32)
            except Exception as e:
                logger.debug(f"Right hand source error: {e}")

        # ── Gripper (right arm, LMG-90, 0–100 → 0.0–1.0) ─────────────────
        if self._gripper_source:
            try:
                g = self._gripper_source()
                if g:
                    obs["gripper.position"] = np.array([float(g.get("position", 0)) / 100.0], dtype=np.float32)
                    obs["gripper.torque"]   = np.array([float(g.get("torque",   0)) / 100.0], dtype=np.float32)
            except Exception as e:
                logger.debug(f"Gripper source error: {e}")

        return obs

    def send_action(self, action: dict) -> dict:
        """
        In VLA recording the robot is teleoperated externally — we observe and
        record its movements but do not command it here.
        Returns the action unchanged (as required by the Robot interface).
        """
        return action

    def disconnect(self) -> None:
        self._connected = False
        logger.info("DualArmRobot disconnected")

    # ── Parsing helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _parse_pos(tcp_pos) -> np.ndarray:
        if isinstance(tcp_pos, (list, tuple)) and len(tcp_pos) >= 3:
            return np.array(tcp_pos[:3], dtype=np.float32)
        if isinstance(tcp_pos, dict):
            return np.array([tcp_pos.get("x", 0.), tcp_pos.get("y", 0.), tcp_pos.get("z", 0.)],
                            dtype=np.float32)
        return np.zeros(3, dtype=np.float32)

    @staticmethod
    def _parse_quat(state: dict) -> np.ndarray:
        q = state.get("tcp_quaternion")
        if isinstance(q, (list, tuple)) and len(q) >= 4:
            return np.array(q[:4], dtype=np.float32)
        if "euler" in state:
            e  = state["euler"]
            rx, ry, rz = e.get("x", 0.), e.get("y", 0.), e.get("z", 0.)
            cy, sy = math.cos(rz*.5), math.sin(rz*.5)
            cp, sp = math.cos(ry*.5), math.sin(ry*.5)
            cr, sr = math.cos(rx*.5), math.sin(rx*.5)
            return np.array([
                cr*cp*cy + sr*sp*sy,
                sr*cp*cy - cr*sp*sy,
                cr*sp*cy + sr*cp*sy,
                cr*cp*sy - sr*sp*cy,
            ], dtype=np.float32)
        return np.array([1., 0., 0., 0.], dtype=np.float32)

    @staticmethod
    def _parse_joints(state: dict, key: str, fallback_key: str = None) -> np.ndarray:
        v = state.get(key, state.get(fallback_key) if fallback_key else None)
        if v is not None:
            return np.array(v, dtype=np.float32)[:7]
        return np.zeros(7, dtype=np.float32)

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _probe_camera_resolution(self) -> None:
        """Detect actual camera resolution from the first available frame."""
        if not self._camera_source:
            return
        try:
            frames = self._camera_source()
            if frames and 0 in frames and frames[0] is not None:
                fd  = frames[0]
                arr = fd[1] if isinstance(fd, tuple) else fd
                h, w = arr.shape[:2]
                self._cam_h, self._cam_w = h, w
        except Exception:
            pass
