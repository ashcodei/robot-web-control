"""
RL Recording Module
强化学习录制模块

Recording system for reinforcement learning data collection.
用于强化学习数据收集的录制系统。
"""

import os
import time
import json
import threading
import logging
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)

# Optional imports
HDF5_AVAILABLE = False
PICKLE_AVAILABLE = True

try:
    import h5py
    HDF5_AVAILABLE = True
except ImportError:
    logger.warning("h5py not available, HDF5 export disabled")

try:
    import pickle
except ImportError:
    PICKLE_AVAILABLE = False


class RecordingState(Enum):
    """Recording state / 录制状态"""
    IDLE = "idle"
    RECORDING = "recording"
    PAUSED = "paused"
    SAVING = "saving"
    ERROR = "error"


@dataclass
class TrajectoryPoint:
    """Single trajectory point / 单个轨迹点"""
    timestamp: float
    # Robot state
    left_joints: Optional[List[float]] = None
    right_joints: Optional[List[float]] = None
    left_tcp: Optional[Dict[str, float]] = None
    right_tcp: Optional[Dict[str, float]] = None
    # Hand state
    left_hand: Optional[List[int]] = None
    right_hand: Optional[List[int]] = None
    # Actions (target positions)
    action_left_joints: Optional[List[float]] = None
    action_right_joints: Optional[List[float]] = None
    action_left_hand: Optional[List[int]] = None
    action_right_hand: Optional[List[int]] = None
    # Image data (paths or embeddings)
    image_paths: Optional[List[str]] = None
    depth_paths: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary / 转换为字典"""
        return asdict(self)


@dataclass
class Episode:
    """Recording episode / 录制回合"""
    episode_id: int
    start_time: float
    end_time: float = 0.0
    points: List[TrajectoryPoint] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def duration(self) -> float:
        """Get episode duration / 获取回合持续时间"""
        if self.end_time > 0:
            return self.end_time - self.start_time
        return 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary / 转换为字典"""
        return {
            'episode_id': self.episode_id,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'duration': self.duration(),
            'num_points': len(self.points),
            'points': [p.to_dict() for p in self.points],
            'metadata': self.metadata
        }


class RLRecordingManager:
    """
    Recording manager for RL data collection.
    强化学习数据收集的录制管理器。

    Supports:
    - Unified timestamp recording
    - Joint states + images + actions
    - HDF5/pickle export
    - Episode management
    """

    def __init__(self, output_dir: str = "recordings"):
        """
        Initialize recording manager.
        初始化录制管理器。

        Args:
            output_dir: Output directory for recordings
        """
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

        self._state = RecordingState.IDLE
        self._current_episode: Optional[Episode] = None
        self._episodes: List[Episode] = []
        self._episode_counter = 0

        # Recording settings
        self._record_rate = 30.0  # Hz
        self._include_images = True
        self._include_depth = False
        self._image_size = (640, 480)
        self._max_episode_length = 300.0  # seconds

        # Threading
        self._lock = threading.Lock()
        self._record_thread: Optional[threading.Thread] = None
        self._stop_flag = threading.Event()

        # Data sources (callbacks)
        self._state_callback: Optional[Callable[[], Dict[str, Any]]] = None
        self._action_callback: Optional[Callable[[], Dict[str, Any]]] = None
        self._image_callback: Optional[Callable[[], Any]] = None

        # Callbacks
        self._point_added_callbacks: List[Callable[[TrajectoryPoint], None]] = []
        self._state_callbacks: List[Callable[[RecordingState], None]] = []

    @property
    def state(self) -> RecordingState:
        """Get current state / 获取当前状态"""
        return self._state

    @property
    def current_episode(self) -> Optional[Episode]:
        """Get current episode / 获取当前回合"""
        return self._current_episode

    @property
    def episode_count(self) -> int:
        """Get total episode count / 获取总回合数"""
        return len(self._episodes)

    def configure(self, record_rate: float = None, include_images: bool = None,
                  include_depth: bool = None, image_size: tuple = None,
                  max_episode_length: float = None):
        """Configure recording parameters / 配置录制参数"""
        if record_rate is not None:
            self._record_rate = record_rate
        if include_images is not None:
            self._include_images = include_images
        if include_depth is not None:
            self._include_depth = include_depth
        if image_size is not None:
            self._image_size = image_size
        if max_episode_length is not None:
            self._max_episode_length = max_episode_length

    def set_state_callback(self, callback: Callable[[], Dict[str, Any]]):
        """
        Set callback for getting robot state.
        设置获取机器人状态的回调。

        Callback should return dict with keys:
        - left_joints, right_joints
        - left_tcp, right_tcp
        - left_hand, right_hand
        """
        self._state_callback = callback

    def set_action_callback(self, callback: Callable[[], Dict[str, Any]]):
        """
        Set callback for getting current actions.
        设置获取当前动作的回调。
        """
        self._action_callback = callback

    def set_image_callback(self, callback: Callable[[], Any]):
        """Set callback for getting camera images / 设置获取相机图像的回调"""
        self._image_callback = callback

    def add_point_callback(self, callback: Callable[[TrajectoryPoint], None]):
        """Add callback for point added events / 添加点添加事件回调"""
        self._point_added_callbacks.append(callback)

    def add_state_change_callback(self, callback: Callable[[RecordingState], None]):
        """Add callback for state changes / 添加状态变化回调"""
        self._state_callbacks.append(callback)

    def _set_state(self, new_state: RecordingState):
        """Set state and notify callbacks / 设置状态并通知回调"""
        self._state = new_state
        for callback in self._state_callbacks:
            try:
                callback(new_state)
            except Exception as e:
                logger.warning(f"State callback error: {e}")

    def start_episode(self, metadata: Dict[str, Any] = None) -> bool:
        """
        Start new recording episode.
        开始新的录制回合。

        Args:
            metadata: Optional episode metadata

        Returns:
            True if started successfully
        """
        if self._state == RecordingState.RECORDING:
            logger.warning("Already recording")
            return False

        self._episode_counter += 1
        self._current_episode = Episode(
            episode_id=self._episode_counter,
            start_time=time.time(),
            metadata=metadata or {}
        )

        self._stop_flag.clear()
        self._record_thread = threading.Thread(target=self._recording_loop, daemon=True)
        self._record_thread.start()

        self._set_state(RecordingState.RECORDING)
        logger.info(f"Started episode {self._episode_counter}")
        return True

    def stop_episode(self) -> Optional[Episode]:
        """
        Stop current recording episode.
        停止当前录制回合。

        Returns:
            Completed episode or None
        """
        if self._state not in [RecordingState.RECORDING, RecordingState.PAUSED]:
            return None

        self._stop_flag.set()
        if self._record_thread:
            self._record_thread.join(timeout=2.0)

        if self._current_episode:
            self._current_episode.end_time = time.time()
            self._episodes.append(self._current_episode)
            completed = self._current_episode
            self._current_episode = None

            self._set_state(RecordingState.IDLE)
            logger.info(f"Stopped episode {completed.episode_id} with {len(completed.points)} points")
            return completed

        self._set_state(RecordingState.IDLE)
        return None

    def pause(self):
        """Pause recording / 暂停录制"""
        if self._state == RecordingState.RECORDING:
            self._set_state(RecordingState.PAUSED)

    def resume(self):
        """Resume recording / 恢复录制"""
        if self._state == RecordingState.PAUSED:
            self._set_state(RecordingState.RECORDING)

    def _recording_loop(self):
        """Recording loop / 录制循环"""
        interval = 1.0 / self._record_rate

        while not self._stop_flag.is_set():
            if self._state != RecordingState.RECORDING:
                time.sleep(0.01)
                continue

            start_time = time.time()

            # Collect data point
            point = self._collect_point()
            if point:
                with self._lock:
                    if self._current_episode:
                        self._current_episode.points.append(point)

                # Notify callbacks
                for callback in self._point_added_callbacks:
                    try:
                        callback(point)
                    except Exception as e:
                        logger.warning(f"Point callback error: {e}")

            # Check max length
            if self._current_episode:
                duration = time.time() - self._current_episode.start_time
                if duration >= self._max_episode_length:
                    logger.info("Max episode length reached")
                    self.stop_episode()
                    return

            # Wait for next sample
            elapsed = time.time() - start_time
            sleep_time = max(0, interval - elapsed)
            time.sleep(sleep_time)

    def _collect_point(self) -> Optional[TrajectoryPoint]:
        """Collect single data point / 收集单个数据点"""
        try:
            point = TrajectoryPoint(timestamp=time.time())

            # Get robot state
            if self._state_callback:
                state = self._state_callback()
                point.left_joints = state.get('left_joints')
                point.right_joints = state.get('right_joints')
                point.left_tcp = state.get('left_tcp')
                point.right_tcp = state.get('right_tcp')
                point.left_hand = state.get('left_hand')
                point.right_hand = state.get('right_hand')

            # Get actions
            if self._action_callback:
                action = self._action_callback()
                point.action_left_joints = action.get('left_joints')
                point.action_right_joints = action.get('right_joints')
                point.action_left_hand = action.get('left_hand')
                point.action_right_hand = action.get('right_hand')

            # Get images (if enabled)
            if self._include_images and self._image_callback:
                # Images would be saved to disk, paths stored in point
                pass

            return point

        except Exception as e:
            logger.error(f"Data collection error: {e}")
            return None

    def add_manual_point(self, point: TrajectoryPoint):
        """Add point manually / 手动添加点"""
        with self._lock:
            if self._current_episode:
                self._current_episode.points.append(point)

    def export_episode(self, episode: Episode, filename: str,
                       format: str = "json") -> bool:
        """
        Export episode to file.
        将回合导出到文件。

        Args:
            episode: Episode to export
            filename: Output filename
            format: "json", "hdf5", or "pickle"

        Returns:
            True if export successful
        """
        self._set_state(RecordingState.SAVING)

        try:
            filepath = self._output_dir / filename

            if format == "json":
                return self._export_json(episode, filepath)
            elif format == "hdf5":
                return self._export_hdf5(episode, filepath)
            elif format == "pickle":
                return self._export_pickle(episode, filepath)
            else:
                logger.error(f"Unknown format: {format}")
                return False

        except Exception as e:
            logger.error(f"Export error: {e}")
            self._set_state(RecordingState.ERROR)
            return False
        finally:
            if self._state == RecordingState.SAVING:
                self._set_state(RecordingState.IDLE)

    def _export_json(self, episode: Episode, filepath: Path) -> bool:
        """Export to JSON / 导出为 JSON"""
        with open(filepath.with_suffix('.json'), 'w', encoding='utf-8') as f:
            json.dump(episode.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info(f"Exported to {filepath.with_suffix('.json')}")
        return True

    def _export_hdf5(self, episode: Episode, filepath: Path) -> bool:
        """Export to HDF5 / 导出为 HDF5"""
        if not HDF5_AVAILABLE:
            logger.error("h5py not available")
            return False

        import numpy as np

        with h5py.File(filepath.with_suffix('.hdf5'), 'w') as f:
            # Metadata
            f.attrs['episode_id'] = episode.episode_id
            f.attrs['start_time'] = episode.start_time
            f.attrs['end_time'] = episode.end_time
            f.attrs['num_points'] = len(episode.points)

            # Convert points to arrays
            timestamps = [p.timestamp for p in episode.points]
            f.create_dataset('timestamps', data=np.array(timestamps))

            # Robot state
            if episode.points[0].left_joints:
                left_joints = [p.left_joints for p in episode.points if p.left_joints]
                if left_joints:
                    f.create_dataset('left_joints', data=np.array(left_joints))

            if episode.points[0].right_joints:
                right_joints = [p.right_joints for p in episode.points if p.right_joints]
                if right_joints:
                    f.create_dataset('right_joints', data=np.array(right_joints))

        logger.info(f"Exported to {filepath.with_suffix('.hdf5')}")
        return True

    def _export_pickle(self, episode: Episode, filepath: Path) -> bool:
        """Export to pickle / 导出为 pickle"""
        if not PICKLE_AVAILABLE:
            logger.error("pickle not available")
            return False

        import pickle
        with open(filepath.with_suffix('.pkl'), 'wb') as f:
            pickle.dump(episode.to_dict(), f)
        logger.info(f"Exported to {filepath.with_suffix('.pkl')}")
        return True

    def export_all(self, format: str = "json") -> int:
        """
        Export all episodes.
        导出所有回合。

        Returns:
            Number of episodes exported
        """
        count = 0
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        for episode in self._episodes:
            filename = f"episode_{episode.episode_id:04d}_{timestamp}"
            if self.export_episode(episode, filename, format):
                count += 1

        return count

    def clear_episodes(self):
        """Clear all recorded episodes / 清除所有录制的回合"""
        self._episodes.clear()
        self._episode_counter = 0

    def get_episodes(self) -> List[Episode]:
        """Get all recorded episodes / 获取所有录制的回合"""
        return self._episodes.copy()
