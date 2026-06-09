"""
Trajectory Manager Module
轨迹管理器模块

Records and replays teleoperation trajectories.
记录和回放遥操作轨迹。
"""

import json
import os
import time
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, asdict
from datetime import datetime

from app_core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TrajectoryPoint:
    """Single trajectory point / 单个轨迹点"""
    timestamp: float
    positions: List[float]
    velocities: Optional[List[float]] = None


@dataclass
class Trajectory:
    """Complete trajectory / 完整轨迹"""
    name: str
    points: List[TrajectoryPoint]
    duration: float = 0.0
    description: str = ""
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if self.points and not self.duration:
            self.duration = self.points[-1].timestamp - self.points[0].timestamp


class TrajectoryManager:
    """
    Trajectory recording and playback manager.
    轨迹记录和回放管理器。
    """

    def __init__(self, trajectories_dir: str = None):
        if trajectories_dir is None:
            from config.settings import DATA_DIR
            trajectories_dir = os.path.join(DATA_DIR, "trajectories")

        self._trajectories_dir = trajectories_dir
        os.makedirs(trajectories_dir, exist_ok=True)

        self._is_recording = False
        self._is_playing = False
        self._current_trajectory: Optional[Trajectory] = None
        self._record_start_time: float = 0.0
        self._play_callbacks: List[Callable[[TrajectoryPoint], None]] = []

    @property
    def is_recording(self) -> bool:
        """Check if recording / 检查是否正在录制"""
        return self._is_recording

    @property
    def is_playing(self) -> bool:
        """Check if playing / 检查是否正在播放"""
        return self._is_playing

    def start_recording(self, name: str = None) -> bool:
        """
        Start trajectory recording.
        开始轨迹录制。

        Args:
            name: Trajectory name (auto-generated if not provided)
        """
        if self._is_recording:
            logger.warning("Already recording")
            return False

        if not name:
            name = f"trajectory_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        self._current_trajectory = Trajectory(name=name, points=[])
        self._record_start_time = time.time()
        self._is_recording = True

        logger.info(f"Started recording trajectory: {name}")
        return True

    def record_point(self, positions: List[float],
                     velocities: List[float] = None):
        """
        Record a trajectory point.
        记录一个轨迹点。

        Args:
            positions: Joint positions
            velocities: Joint velocities (optional)
        """
        if not self._is_recording or not self._current_trajectory:
            return

        point = TrajectoryPoint(
            timestamp=time.time() - self._record_start_time,
            positions=list(positions),
            velocities=list(velocities) if velocities else None
        )
        self._current_trajectory.points.append(point)

    def stop_recording(self) -> Optional[Trajectory]:
        """
        Stop recording and return trajectory.
        停止录制并返回轨迹。

        Returns:
            Recorded trajectory or None
        """
        if not self._is_recording:
            return None

        self._is_recording = False

        if self._current_trajectory and len(self._current_trajectory.points) > 0:
            self._current_trajectory.duration = (
                self._current_trajectory.points[-1].timestamp -
                self._current_trajectory.points[0].timestamp
            )
            trajectory = self._current_trajectory
            self._current_trajectory = None
            logger.info(f"Stopped recording: {len(trajectory.points)} points, "
                       f"{trajectory.duration:.2f}s duration")
            return trajectory

        self._current_trajectory = None
        return None

    def save_trajectory(self, trajectory: Trajectory) -> bool:
        """
        Save trajectory to file.
        保存轨迹到文件。

        Args:
            trajectory: Trajectory to save
        """
        try:
            file_path = os.path.join(
                self._trajectories_dir,
                f"{trajectory.name}.json"
            )

            data = {
                "name": trajectory.name,
                "duration": trajectory.duration,
                "description": trajectory.description,
                "created_at": trajectory.created_at,
                "points": [
                    {
                        "timestamp": p.timestamp,
                        "positions": p.positions,
                        "velocities": p.velocities
                    }
                    for p in trajectory.points
                ]
            }

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)

            logger.info(f"Saved trajectory: {trajectory.name}")
            return True

        except Exception as e:
            logger.error(f"Failed to save trajectory: {e}")
            return False

    def load_trajectory(self, name: str) -> Optional[Trajectory]:
        """
        Load trajectory from file.
        从文件加载轨迹。

        Args:
            name: Trajectory name

        Returns:
            Loaded trajectory or None
        """
        try:
            file_path = os.path.join(self._trajectories_dir, f"{name}.json")

            if not os.path.exists(file_path):
                logger.warning(f"Trajectory not found: {name}")
                return None

            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            points = [
                TrajectoryPoint(
                    timestamp=p["timestamp"],
                    positions=p["positions"],
                    velocities=p.get("velocities")
                )
                for p in data["points"]
            ]

            return Trajectory(
                name=data["name"],
                points=points,
                duration=data["duration"],
                description=data.get("description", ""),
                created_at=data.get("created_at", "")
            )

        except Exception as e:
            logger.error(f"Failed to load trajectory: {e}")
            return None

    def delete_trajectory(self, name: str) -> bool:
        """Delete trajectory / 删除轨迹"""
        file_path = os.path.join(self._trajectories_dir, f"{name}.json")

        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Deleted trajectory: {name}")
            return True

        return False

    def list_trajectories(self) -> List[str]:
        """List all saved trajectories / 列出所有保存的轨迹"""
        trajectories = []
        for filename in os.listdir(self._trajectories_dir):
            if filename.endswith('.json'):
                trajectories.append(filename[:-5])
        return sorted(trajectories)

    def add_play_callback(self, callback: Callable[[TrajectoryPoint], None]):
        """Add playback callback / 添加回放回调"""
        self._play_callbacks.append(callback)

    def remove_play_callback(self, callback: Callable[[TrajectoryPoint], None]):
        """Remove playback callback / 移除回放回调"""
        if callback in self._play_callbacks:
            self._play_callbacks.remove(callback)

    def play_trajectory(self, trajectory: Trajectory,
                        speed_factor: float = 1.0) -> bool:
        """
        Play trajectory.
        播放轨迹。

        Args:
            trajectory: Trajectory to play
            speed_factor: Speed multiplier (1.0 = normal speed)
        """
        if self._is_playing:
            logger.warning("Already playing")
            return False

        if not trajectory.points:
            logger.warning("Empty trajectory")
            return False

        self._is_playing = True

        import threading
        threading.Thread(
            target=self._play_loop,
            args=(trajectory, speed_factor),
            daemon=True
        ).start()

        return True

    def _play_loop(self, trajectory: Trajectory, speed_factor: float):
        """Playback loop / 回放循环"""
        start_time = time.time()
        point_index = 0

        logger.info(f"Playing trajectory: {trajectory.name}")

        while self._is_playing and point_index < len(trajectory.points):
            elapsed = (time.time() - start_time) * speed_factor
            point = trajectory.points[point_index]

            if elapsed >= point.timestamp:
                # Send point to callbacks
                for callback in self._play_callbacks:
                    try:
                        callback(point)
                    except Exception as e:
                        logger.error(f"Play callback error: {e}")

                point_index += 1
            else:
                time.sleep(0.01)

        self._is_playing = False
        logger.info("Playback complete")

    def stop_playback(self):
        """Stop trajectory playback / 停止轨迹回放"""
        self._is_playing = False
        logger.info("Playback stopped")
