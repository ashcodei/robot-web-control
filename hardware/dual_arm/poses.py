"""
Dual Arm Poses Management Module
双臂点位管理模块

Manages saved poses and steps (sets of poses) for dual arm robot.
管理双臂机器人的保存点位和步骤（点位集合）。

Uses RecordedPose/Step from pose_control_widget (matches reference format).
"""

import json
import os
from typing import Dict, List, Optional
from datetime import datetime

from app_core.logger import get_logger
from .pose_control_widget import RecordedPose, Step

logger = get_logger(__name__)

# Backward-compatible alias
DualArmPose = RecordedPose


def _migrate_pose_data(data: dict) -> dict:
    """Migrate old DualArmPose format to RecordedPose format.

    Old format: left_joints, right_joints, left_hand_positions, created_at, description
    New format: joints, right_joints, hand_positions, timestamp, pose_type, position, euler
    """
    # Already new format (has 'joints' key and no 'left_joints')
    if "joints" in data and "left_joints" not in data:
        return data

    migrated = dict(data)

    # left_joints -> joints (primary arm)
    if "left_joints" in migrated:
        migrated["joints"] = migrated.pop("left_joints")

    # left_hand_positions -> hand_positions
    if "left_hand_positions" in migrated:
        migrated["hand_positions"] = migrated.pop("left_hand_positions")

    # created_at -> timestamp
    if "created_at" in migrated and "timestamp" not in migrated:
        migrated["timestamp"] = migrated.pop("created_at")

    # Remove 'description' (not in RecordedPose)
    migrated.pop("description", None)

    # Add defaults for required fields
    migrated.setdefault("pose_type", "joint")
    migrated.setdefault("position", {})
    migrated.setdefault("euler", {})
    migrated.setdefault("timestamp", datetime.now().isoformat())
    migrated.setdefault("speed", 0.5)
    migrated.setdefault("acceleration", 0.5)

    return migrated


class DualArmPoseManager:
    """
    Pose and step manager for dual arm robot.
    双臂机器人的点位与步骤管理器。
    """

    def __init__(self, poses_file: str = None):
        if poses_file is None:
            from config.settings import DUAL_ARM_STEPS_DIR
            poses_file = os.path.join(DUAL_ARM_STEPS_DIR, "dual_arm_poses.json")

        self._poses_file = poses_file
        self._poses: Dict[str, RecordedPose] = {}
        self._steps: List[Step] = []
        self._load_poses()

    def _load_poses(self):
        """Load poses and steps from file (handles both old and new formats)."""
        if not os.path.exists(self._poses_file):
            return

        try:
            with open(self._poses_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Flat poses
            poses_data = data.get("poses")
            if poses_data is None and isinstance(data, dict) and "steps" not in data:
                # Legacy: detect flat pose dicts by presence of joints or left_joints
                poses_data = {
                    k: v for k, v in data.items()
                    if isinstance(v, dict) and ("left_joints" in v or "joints" in v)
                }
            if poses_data:
                for name, pose_data in poses_data.items():
                    if not isinstance(pose_data, dict):
                        continue
                    try:
                        migrated = _migrate_pose_data(pose_data)
                        self._poses[name] = RecordedPose.from_dict(migrated)
                    except Exception as e:
                        logger.warning(f"Skip pose {name}: {e}")

            # Steps
            for step_data in data.get("steps", []):
                try:
                    # Migrate each pose within steps
                    migrated_poses = []
                    for p in step_data.get("poses", []):
                        migrated_poses.append(_migrate_pose_data(p))
                    step_data_migrated = dict(step_data)
                    step_data_migrated["poses"] = migrated_poses
                    self._steps.append(Step.from_dict(step_data_migrated))
                except Exception as e:
                    logger.warning(f"Skip step: {e}")

            if self._steps or self._poses:
                logger.info(f"Loaded {len(self._poses)} poses, {len(self._steps)} steps")
        except Exception as e:
            logger.error(f"Failed to load poses: {e}")

    def _save_poses(self):
        """Save poses and steps to file."""
        try:
            os.makedirs(os.path.dirname(self._poses_file), exist_ok=True)
            data = {
                "poses": {name: p.to_dict() for name, p in self._poses.items()},
                "steps": [s.to_dict() for s in self._steps],
                "version": "2.0",
                "saved_at": datetime.now().isoformat(),
            }
            with open(self._poses_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save poses: {e}")

    def _autosave(self):
        """Autosave steps and poses."""
        self._save_poses()

    # --- Flat pose API (backward compatible) ---

    def save_pose(
        self,
        name: str,
        left_joints: List[float],
        right_joints: List[float],
        description: str = "",
        left_hand_positions: Optional[List[int]] = None,
        right_hand_positions: Optional[List[int]] = None,
        arm: str = "both",
    ) -> bool:
        """Save a pose (flat list, backward-compatible API)."""
        self._poses[name] = RecordedPose(
            name=name,
            timestamp=datetime.now().isoformat(),
            arm=arm,
            pose_type="joint",
            joints=list(left_joints),
            right_joints=list(right_joints),
            hand_positions=list(left_hand_positions) if left_hand_positions else None,
            right_hand_positions=list(right_hand_positions) if right_hand_positions else None,
        )
        self._save_poses()
        logger.info(f"Saved dual arm pose: {name}")
        return True

    def get_pose(self, name: str) -> Optional[RecordedPose]:
        """Get pose by name from flat list."""
        return self._poses.get(name)

    def delete_pose(self, name: str) -> bool:
        """Delete pose from flat list."""
        if name in self._poses:
            del self._poses[name]
            self._save_poses()
            return True
        return False

    def list_poses(self) -> List[str]:
        """List all pose names (flat list)."""
        return list(self._poses.keys())

    # --- Step API ---

    def list_steps(self) -> List[str]:
        """List step names."""
        return [s.name for s in self._steps]

    def get_step(self, index: int) -> Optional[Step]:
        """Get step by index."""
        if 0 <= index < len(self._steps):
            return self._steps[index]
        return None

    def add_step(self, name: str) -> int:
        """Add a new step; returns its index."""
        self._steps.append(Step(name=name, poses=[], created=datetime.now().isoformat()))
        self._autosave()
        return len(self._steps) - 1

    def delete_step(self, index: int) -> bool:
        """Delete step by index."""
        if 0 <= index < len(self._steps):
            del self._steps[index]
            self._autosave()
            return True
        return False

    def add_pose_to_step(self, step_index: int, pose: RecordedPose) -> bool:
        """Append a pose to a step."""
        if 0 <= step_index < len(self._steps):
            self._steps[step_index].poses.append(pose)
            self._autosave()
            return True
        return False

    def get_pose_in_step(self, step_index: int, pose_index: int) -> Optional[RecordedPose]:
        """Get pose by index within a step."""
        step = self.get_step(step_index)
        if step and 0 <= pose_index < len(step.poses):
            return step.poses[pose_index]
        return None

    def delete_pose_from_step(self, step_index: int, pose_index: int) -> bool:
        """Remove a pose from a step."""
        step = self.get_step(step_index)
        if step and 0 <= pose_index < len(step.poses):
            del step.poses[pose_index]
            self._autosave()
            return True
        return False

    def move_pose_in_step(self, step_index: int, pose_index: int, direction: int) -> bool:
        """Move pose up (-1) or down (+1) within step."""
        step = self.get_step(step_index)
        if not step or pose_index < 0 or pose_index >= len(step.poses):
            return False
        new_idx = pose_index + direction
        if new_idx < 0 or new_idx >= len(step.poses):
            return False
        step.poses[pose_index], step.poses[new_idx] = step.poses[new_idx], step.poses[pose_index]
        self._autosave()
        return True

    def next_default_pose_name(self, step_index: Optional[int] = None) -> str:
        """Return next default pose name (Pose_1, Pose_2, ...)."""
        existing = set()
        if step_index is not None and 0 <= step_index < len(self._steps):
            for p in self._steps[step_index].poses:
                existing.add(p.name)
        for name in self._poses:
            existing.add(name)
        for i in range(1, 10000):
            candidate = f"Pose_{i}"
            if candidate not in existing:
                return candidate
        return f"Pose_{datetime.now().strftime('%H%M%S')}"

    def next_default_step_name(self) -> str:
        """Return next default step name (Step_1, Step_2, ...)."""
        existing = {s.name for s in self._steps}
        for i in range(1, 10000):
            candidate = f"Step_{i}"
            if candidate not in existing:
                return candidate
        return f"Step_{datetime.now().strftime('%H%M%S')}"

    # --- File management API ---

    @staticmethod
    def scan_data_dir() -> List[tuple]:
        """Scan dual_arm_steps directory for JSON files. Returns list of (filename, full_path) tuples."""
        from config.settings import DUAL_ARM_STEPS_DIR
        data_dir = str(DUAL_ARM_STEPS_DIR)
        results = []
        if os.path.isdir(data_dir):
            for fname in sorted(os.listdir(data_dir)):
                if fname.lower().endswith(".json"):
                    results.append((fname, os.path.join(data_dir, fname)))
        return results

    def load_file(self, filepath: str, replace: bool = True) -> bool:
        """Load steps/poses from a given file, optionally replacing or appending."""
        if not os.path.exists(filepath):
            logger.warning(f"File not found: {filepath}")
            return False

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load file {filepath}: {e}")
            return False

        if replace:
            self._steps.clear()
            self._poses.clear()

        # Load flat poses
        poses_data = data.get("poses")
        if poses_data is None and isinstance(data, dict) and "steps" not in data:
            poses_data = {
                k: v for k, v in data.items()
                if isinstance(v, dict) and ("left_joints" in v or "joints" in v)
            }
        if poses_data:
            for name, pose_data in poses_data.items():
                if not isinstance(pose_data, dict):
                    continue
                try:
                    migrated = _migrate_pose_data(pose_data)
                    self._poses[name] = RecordedPose.from_dict(migrated)
                except Exception as e:
                    logger.warning(f"Skip pose {name}: {e}")

        # Load steps
        for step_data in data.get("steps", []):
            try:
                migrated_poses = []
                for p in step_data.get("poses", []):
                    migrated_poses.append(_migrate_pose_data(p))
                step_data_migrated = dict(step_data)
                step_data_migrated["poses"] = migrated_poses
                self._steps.append(Step.from_dict(step_data_migrated))
            except Exception as e:
                logger.warning(f"Skip step: {e}")

        logger.info(f"Loaded from {filepath}: {len(self._poses)} poses, {len(self._steps)} steps")
        return True

    def set_poses_file(self, filepath: str):
        """Change the current save target file."""
        self._poses_file = filepath
