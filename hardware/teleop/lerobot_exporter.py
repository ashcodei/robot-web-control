"""
LeRobot Dataset Exporter — v3.0
LeRobot数据集导出器 — v3.0

Converts HDF5 episodes to LeRobot v3.0 format (sharded Parquet + sharded MP4
+ chunked episode metadata) for π0 training and HuggingFace Hub upload.
将HDF5回合转换为LeRobot v3.0格式（分片Parquet + 分片MP4
+ 分块episode元数据），用于π0训练和HuggingFace Hub上传。
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Optional imports
HDF5_AVAILABLE = False
try:
    import h5py
    HDF5_AVAILABLE = True
except ImportError:
    pass

PYARROW_AVAILABLE = False
try:
    import pyarrow as pa
    import pyarrow.parquet as pq
    PYARROW_AVAILABLE = True
except ImportError:
    pass

PANDAS_AVAILABLE = False
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    pass

CV2_AVAILABLE = False
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    pass

# LeRobot v3.0
LEROBOT_VERSION = "v3.0"
DEFAULT_CHUNKS_SIZE = 1000


class LeRobotExporter:
    """
    Export HDF5 episodes to LeRobot v3.0 dataset format.
    将HDF5回合导出为LeRobot v3.0数据集格式。

    Output structure:
        {output_dir}/
        ├── meta/
        │   ├── info.json
        │   ├── stats.json
        │   ├── tasks.parquet
        │   └── episodes/
        │       └── chunk-000/
        │           └── file-000.parquet
        ├── data/
        │   └── chunk-000/
        │       ├── file-000.parquet      (multi-episode shard)
        │       └── ...
        └── videos/
            ├── observation.images.desk/
            │   └── chunk-000/
            │       ├── file-000.mp4      (multi-episode shard)
            │       └── ...
            └── observation.images.wrist/
                └── chunk-000/
                    ├── file-000.mp4
                    └── ...
    """

    # Default state/action dimensions for single-arm binary-hand mode
    STATE_DIM = 29   # tcp(3) + quat(4) + joints(7) + vel(7) + eff(7) + hand(1)
    ACTION_DIM = 7   # delta_pos(3) + delta_rot(3) + hand(1)

    def __init__(self, fps: int = 30, robot_type: str = "dual_arm_7dof",
                 video_codec: str = "avc1", image_size: Optional[Tuple[int, int]] = None,
                 chunks_size: int = DEFAULT_CHUNKS_SIZE):
        """
        Args:
            fps: Recording frame rate.
            robot_type: Robot type string for info.json.
            video_codec: FourCC codec for MP4 encoding.
            image_size: Optional (width, height) to resize images during export.
                        If None, uses original resolution.
            chunks_size: Max episodes per chunk directory (default 1000).
        """
        self._fps = fps
        self._robot_type = robot_type
        self._video_codec = video_codec
        self._image_size = image_size  # (W, H) or None
        self._chunks_size = chunks_size

        # Accumulate across episodes for stats
        self._all_states: List[np.ndarray] = []
        self._all_actions: List[np.ndarray] = []
        self._tasks: Dict[str, int] = {}  # task_text -> task_index
        self._episode_metas: List[Dict[str, Any]] = []
        self._global_frame_idx = 0
        self._image_shape: Optional[Tuple[int, int, int]] = None  # (H, W, 3)

        # Video writers for sharded concatenation (per camera key)
        self._video_writers: Dict[str, cv2.VideoWriter] = {}
        self._video_frame_counts: Dict[str, int] = {}  # total frames written per camera
        self._video_file_indices: Dict[str, int] = {}   # current file index per camera

        # Data shard accumulator
        self._data_shard_rows: List[Dict[str, Any]] = []
        self._data_file_index = 0
        self._data_chunk_index = 0

    def export_from_hdf5(self, h5_files: List[Path], output_dir: Path,
                         action_mode: str = "delta",
                         progress_callback=None) -> bool:
        """
        Main entry: convert HDF5 episodes to LeRobot v3.0 format.
        主入口：将HDF5回合转换为LeRobot v3.0格式。

        Args:
            h5_files: List of HDF5 episode file paths, sorted by episode order.
            output_dir: Output directory for the LeRobot dataset.
            action_mode: "delta" (default) or "absolute".
            progress_callback: Optional callable(current, total, message).

        Returns:
            True if export succeeded.
        """
        if not HDF5_AVAILABLE:
            logger.error("h5py is required for LeRobot export")
            return False
        if not PYARROW_AVAILABLE:
            logger.error("pyarrow is required for LeRobot export")
            return False
        if not PANDAS_AVAILABLE:
            logger.error("pandas is required for LeRobot v3.0 export")
            return False
        if not CV2_AVAILABLE:
            logger.error("opencv-python is required for LeRobot export (video encoding)")
            return False

        if not h5_files:
            logger.error("No HDF5 files provided for LeRobot export")
            return False

        # Reset state
        self._all_states = []
        self._all_actions = []
        self._tasks = {}
        self._episode_metas = []
        self._global_frame_idx = 0
        self._image_shape = None
        self._video_writers = {}
        self._video_frame_counts = {}
        self._video_file_indices = {}
        self._data_shard_rows = []
        self._data_file_index = 0
        self._data_chunk_index = 0

        # Create output dirs
        output_dir = Path(output_dir)
        (output_dir / "meta").mkdir(parents=True, exist_ok=True)

        total = len(h5_files)
        total_frames = 0
        camera_keys_seen = set()

        for ep_idx, h5_path in enumerate(h5_files):
            if progress_callback:
                progress_callback(ep_idx, total, f"Processing episode {ep_idx}/{total}")

            try:
                ep_data = self._read_episode_hdf5(h5_path)
                if ep_data is None:
                    logger.warning(f"Skipping unreadable episode: {h5_path}")
                    continue

                n_frames = ep_data['num_steps']
                if n_frames == 0:
                    continue

                # Build vectors
                states = self._build_state_vector(ep_data)
                actions = self._build_action_vector(ep_data, action_mode)

                # Register task
                task_text = ep_data.get('language_instruction', '')
                if task_text not in self._tasks:
                    self._tasks[task_text] = len(self._tasks)
                task_idx = self._tasks[task_text]

                # Timestamps relative to episode start
                timestamps = ep_data['timestamps']
                t0 = timestamps[0] if len(timestamps) > 0 else 0.0
                rel_timestamps = (timestamps - t0).astype(np.float32)

                # Chunk index for this episode
                chunk_idx = ep_idx // self._chunks_size

                # Accumulate data rows for sharded parquet
                global_start = self._global_frame_idx
                self._accumulate_data_rows(
                    ep_idx, states, actions, rel_timestamps, task_idx, n_frames
                )
                global_end = self._global_frame_idx

                # Encode video frames into sharded MP4s and track offsets
                video_offsets = {}
                for cam_name, cam_key_suffix in [('observation.images.desk', 'desk_camera'),
                                                 ('observation.images.wrist', 'wrist_camera')]:
                    if cam_key_suffix in ep_data and ep_data[cam_key_suffix] is not None:
                        camera_keys_seen.add(cam_name)
                        offsets = self._append_to_video_shard(
                            output_dir, ep_data[cam_key_suffix], cam_name, chunk_idx
                        )
                        video_offsets[cam_name] = offsets

                # Accumulate stats
                self._all_states.append(states)
                self._all_actions.append(actions)

                # Per-episode stats
                ep_stats = self._compute_episode_stats(states, actions, n_frames)

                # Episode metadata
                self._episode_metas.append({
                    'episode_index': ep_idx,
                    'tasks': [task_text],
                    'length': n_frames,
                    'dataset_from_index': global_start,
                    'dataset_to_index': global_end,
                    'data_chunk_index': chunk_idx,
                    'data_file_index': self._data_file_index,
                    'episodes_chunk_index': chunk_idx,
                    'episodes_file_index': 0,
                    'video_offsets': video_offsets,
                    'stats': ep_stats,
                })

                total_frames += n_frames

            except Exception as e:
                logger.error(f"Error processing {h5_path}: {e}", exc_info=True)
                continue

        if total_frames == 0:
            logger.error("No valid frames found in any episode")
            return False

        # Flush remaining data shard
        self._flush_data_shard(output_dir)

        # Release all video writers
        self._release_video_writers()

        # Write metadata files
        self._write_info_json(output_dir, len(self._episode_metas), total_frames,
                              camera_keys_seen)
        self._write_tasks_parquet(output_dir)
        self._write_episodes_parquet(output_dir, camera_keys_seen)
        self._compute_and_write_stats(output_dir, total_frames)

        if progress_callback:
            progress_callback(total, total, "Export complete")

        logger.info(
            f"LeRobot v3.0 export complete: {len(self._episode_metas)} episodes, "
            f"{total_frames} frames → {output_dir}"
        )
        return True

    # ------------------------------------------------------------------
    # HDF5 reading
    # ------------------------------------------------------------------

    def _read_episode_hdf5(self, h5_path: Path) -> Optional[Dict[str, Any]]:
        """Read a single HDF5 episode into a dict of arrays."""
        try:
            with h5py.File(str(h5_path), 'r') as f:
                data = {
                    'task_id': f.attrs.get('task_id', ''),
                    'language_instruction': f.attrs.get('language_instruction', ''),
                    'arm_side': f.attrs.get('arm_side', 'left'),
                    'control_freq': float(f.attrs.get('control_freq', 30)),
                    'num_steps': int(f.attrs.get('num_steps', 0)),
                }

                if data['num_steps'] == 0:
                    return data

                # Timestamps
                data['timestamps'] = f['timestamps'][:].astype(np.float64)

                # Observations
                data['tcp_position'] = f['observations/tcp_position'][:].astype(np.float32)
                data['tcp_quaternion'] = f['observations/tcp_quaternion'][:].astype(np.float32)
                data['joint_positions'] = f['observations/joint_positions'][:].astype(np.float32)
                data['joint_velocities'] = f['observations/joint_velocities'][:].astype(np.float32)
                data['joint_efforts'] = f['observations/joint_efforts'][:].astype(np.float32)
                data['hand_state'] = f['observations/hand_state'][:].astype(np.float32)

                # Camera frames (optional)
                if 'observations/desk_camera' in f:
                    data['desk_camera'] = f['observations/desk_camera'][:]
                    if self._image_shape is None:
                        self._image_shape = data['desk_camera'].shape[1:]  # (H, W, 3)
                if 'observations/wrist_camera' in f:
                    data['wrist_camera'] = f['observations/wrist_camera'][:]

                # Actions
                data['delta_position'] = f['actions/delta_position'][:].astype(np.float32)
                data['delta_rotation'] = f['actions/delta_rotation'][:].astype(np.float32)
                data['hand_command'] = f['actions/hand_command'][:].astype(np.float32)

                # Absolute actions (for absolute mode)
                data['target_tcp_position'] = f['actions/target_tcp_position'][:].astype(np.float32)
                data['target_tcp_quaternion'] = f['actions/target_tcp_quaternion'][:].astype(np.float32)

                return data

        except Exception as e:
            logger.error(f"Failed to read HDF5 {h5_path}: {e}")
            return None

    # ------------------------------------------------------------------
    # Vector building
    # ------------------------------------------------------------------

    def _build_state_vector(self, ep_data: Dict[str, Any]) -> np.ndarray:
        """
        Build observation.state [29-dim] from episode data.
        构建 observation.state [29维] 状态向量。

        Layout: tcp_pos(3) + tcp_quat(4) + joints(7) + vel(7) + eff(7) + hand(1) = 29
        """
        parts = [
            ep_data['tcp_position'],          # (T, 3)
            ep_data['tcp_quaternion'],         # (T, 4)
            ep_data['joint_positions'],        # (T, 7)
            ep_data['joint_velocities'],       # (T, 7)
            ep_data['joint_efforts'],          # (T, 7)
            ep_data['hand_state'],             # (T, 1)
        ]
        return np.concatenate(parts, axis=1).astype(np.float32)

    def _build_action_vector(self, ep_data: Dict[str, Any],
                             action_mode: str = "delta") -> np.ndarray:
        """
        Build action [7-dim] from episode data.
        构建 action [7维] 动作向量。

        Delta mode:    delta_pos(3) + delta_rot(3) + hand(1) = 7
        Absolute mode: target_tcp_pos(3) + target_tcp_quat(4) + hand(1) = 8
        """
        if action_mode == "absolute":
            parts = [
                ep_data['target_tcp_position'],     # (T, 3)
                ep_data['target_tcp_quaternion'],    # (T, 4)
                ep_data['hand_command'],             # (T, 1)
            ]
        else:
            parts = [
                ep_data['delta_position'],     # (T, 3)
                ep_data['delta_rotation'],     # (T, 3)
                ep_data['hand_command'],       # (T, 1)
            ]
        return np.concatenate(parts, axis=1).astype(np.float32)

    # ------------------------------------------------------------------
    # Sharded data parquet writing
    # ------------------------------------------------------------------

    def _accumulate_data_rows(self, episode_idx: int,
                              states: np.ndarray, actions: np.ndarray,
                              timestamps: np.ndarray, task_idx: int,
                              n_frames: int):
        """Accumulate frame rows for the current data shard."""
        for i in range(n_frames):
            is_last_frame = (i == n_frames - 1)
            self._data_shard_rows.append({
                'observation.state': states[i].tolist(),
                'action': actions[i].tolist(),
                'timestamp': float(timestamps[i]),
                'frame_index': i,
                'episode_index': episode_idx,
                'index': self._global_frame_idx,
                'task_index': task_idx,
                'next.done': is_last_frame,
            })
            self._global_frame_idx += 1

    def _flush_data_shard(self, output_dir: Path):
        """Write accumulated data rows as a sharded parquet file."""
        if not self._data_shard_rows:
            return

        chunk_dir = output_dir / "data" / f"chunk-{self._data_chunk_index:03d}"
        chunk_dir.mkdir(parents=True, exist_ok=True)
        parquet_path = chunk_dir / f"file-{self._data_file_index:03d}.parquet"

        table = pa.table({
            'observation.state': pa.array(
                [r['observation.state'] for r in self._data_shard_rows],
                type=pa.list_(pa.float32())
            ),
            'action': pa.array(
                [r['action'] for r in self._data_shard_rows],
                type=pa.list_(pa.float32())
            ),
            'timestamp': pa.array(
                [r['timestamp'] for r in self._data_shard_rows],
                type=pa.float32()
            ),
            'frame_index': pa.array(
                [r['frame_index'] for r in self._data_shard_rows],
                type=pa.int64()
            ),
            'episode_index': pa.array(
                [r['episode_index'] for r in self._data_shard_rows],
                type=pa.int64()
            ),
            'index': pa.array(
                [r['index'] for r in self._data_shard_rows],
                type=pa.int64()
            ),
            'task_index': pa.array(
                [r['task_index'] for r in self._data_shard_rows],
                type=pa.int64()
            ),
            'next.done': pa.array(
                [r['next.done'] for r in self._data_shard_rows],
                type=pa.bool_()
            ),
        })

        pq.write_table(table, str(parquet_path))
        logger.debug(f"Wrote data shard: {parquet_path} ({len(self._data_shard_rows)} frames)")
        self._data_shard_rows = []

    # ------------------------------------------------------------------
    # Sharded video encoding
    # ------------------------------------------------------------------

    def _get_video_writer(self, output_dir: Path, camera_key: str,
                          chunk_idx: int, height: int, width: int) -> cv2.VideoWriter:
        """Get or create a video writer for the given camera shard."""
        if camera_key in self._video_writers:
            return self._video_writers[camera_key]

        file_idx = self._video_file_indices.get(camera_key, 0)
        video_dir = output_dir / "videos" / camera_key / f"chunk-{chunk_idx:03d}"
        video_dir.mkdir(parents=True, exist_ok=True)
        video_path = video_dir / f"file-{file_idx:03d}.mp4"

        out_w, out_h = width, height
        if self._image_size is not None:
            out_w, out_h = self._image_size

        fourcc = cv2.VideoWriter_fourcc(*self._video_codec)
        writer = cv2.VideoWriter(str(video_path), fourcc, self._fps, (out_w, out_h))

        if not writer.isOpened():
            logger.error(f"Failed to open video writer for {video_path}")
            return None

        self._video_writers[camera_key] = writer
        self._video_file_indices[camera_key] = file_idx
        if camera_key not in self._video_frame_counts:
            self._video_frame_counts[camera_key] = 0

        return writer

    def _append_to_video_shard(self, output_dir: Path, frames: np.ndarray,
                               camera_key: str, chunk_idx: int) -> Dict[str, Any]:
        """
        Append episode frames to the current video shard for this camera.
        Returns offset info for episode metadata.
        """
        T, H, W, C = frames.shape
        writer = self._get_video_writer(output_dir, camera_key, chunk_idx, H, W)
        if writer is None:
            return {}

        from_frame = self._video_frame_counts[camera_key]
        from_timestamp = from_frame / self._fps

        out_w, out_h = W, H
        if self._image_size is not None:
            out_w, out_h = self._image_size

        for i in range(T):
            bgr = cv2.cvtColor(frames[i], cv2.COLOR_RGB2BGR)
            if self._image_size is not None and (W != out_w or H != out_h):
                bgr = cv2.resize(bgr, (out_w, out_h))
            writer.write(bgr)

        self._video_frame_counts[camera_key] += T
        to_timestamp = self._video_frame_counts[camera_key] / self._fps

        return {
            'chunk_index': chunk_idx,
            'file_index': self._video_file_indices.get(camera_key, 0),
            'from_timestamp': from_timestamp,
            'to_timestamp': to_timestamp,
        }

    def _release_video_writers(self):
        """Release all open video writers."""
        for key, writer in self._video_writers.items():
            try:
                writer.release()
            except Exception as e:
                logger.warning(f"Error releasing video writer {key}: {e}")
        self._video_writers.clear()

    # ------------------------------------------------------------------
    # Per-episode statistics
    # ------------------------------------------------------------------

    def _compute_episode_stats(self, states: np.ndarray, actions: np.ndarray,
                               n_frames: int) -> Dict[str, Dict[str, Any]]:
        """Compute per-episode stats for embedding in episodes parquet."""
        stats = {}
        stats['observation.state'] = {
            'mean': states.mean(axis=0).tolist(),
            'std': states.std(axis=0).tolist(),
            'min': states.min(axis=0).tolist(),
            'max': states.max(axis=0).tolist(),
            'count': [n_frames],
        }
        stats['action'] = {
            'mean': actions.mean(axis=0).tolist(),
            'std': actions.std(axis=0).tolist(),
            'min': actions.min(axis=0).tolist(),
            'max': actions.max(axis=0).tolist(),
            'count': [n_frames],
        }
        return stats

    # ------------------------------------------------------------------
    # Metadata files
    # ------------------------------------------------------------------

    def _write_info_json(self, output_dir: Path, num_episodes: int,
                         total_frames: int, camera_keys: set):
        """Generate info.json (LeRobot v3.0 format)."""
        # Determine image shape
        if self._image_size is not None:
            img_w, img_h = self._image_size
            img_shape = [img_h, img_w, 3]
        elif self._image_shape is not None:
            img_shape = list(self._image_shape)  # [H, W, 3]
        else:
            img_shape = [480, 640, 3]

        # Determine dimensions from accumulated data
        action_dim = self.ACTION_DIM
        state_dim = self.STATE_DIM
        if self._all_actions:
            action_dim = self._all_actions[0].shape[1]
        if self._all_states:
            state_dim = self._all_states[0].shape[1]

        features = {
            "observation.state": {
                "dtype": "float32",
                "shape": [state_dim],
                "names": self._get_state_names(),
                "fps": self._fps,
            },
            "action": {
                "dtype": "float32",
                "shape": [action_dim],
                "names": self._get_action_names(),
                "fps": self._fps,
            },
            "timestamp": {
                "dtype": "float32",
                "shape": [1],
                "names": None,
            },
            "frame_index": {
                "dtype": "int64",
                "shape": [1],
                "names": None,
            },
            "episode_index": {
                "dtype": "int64",
                "shape": [1],
                "names": None,
            },
            "index": {
                "dtype": "int64",
                "shape": [1],
                "names": None,
            },
            "task_index": {
                "dtype": "int64",
                "shape": [1],
                "names": None,
            },
        }

        # Add video features for each camera
        for cam_key in sorted(camera_keys):
            features[cam_key] = {
                "dtype": "video",
                "shape": img_shape,
                "names": ["height", "width", "channels"],
                "fps": self._fps,
                "video_info": {
                    "video.fps": float(self._fps),
                    "video.codec": self._video_codec,
                    "video.pix_fmt": "yuv420p",
                    "video.is_depth_map": False,
                    "has_audio": False,
                }
            }

        # Compute file sizes
        data_size = self._compute_dir_size_mb(output_dir / "data")
        video_size = self._compute_dir_size_mb(output_dir / "videos")

        info = {
            "codebase_version": LEROBOT_VERSION,
            "robot_type": self._robot_type,
            "total_episodes": num_episodes,
            "total_frames": total_frames,
            "total_tasks": len(self._tasks),
            "chunks_size": self._chunks_size,
            "fps": self._fps,
            "splits": {
                "train": f"0:{num_episodes}"
            },
            "data_path": "data/chunk-{chunk_index:03d}/file-{file_index:03d}.parquet",
            "video_path": "videos/{video_key}/chunk-{chunk_index:03d}/file-{file_index:03d}.mp4",
            "data_files_size_in_mb": round(data_size, 2),
            "video_files_size_in_mb": round(video_size, 2),
            "features": features,
        }

        info_path = output_dir / "meta" / "info.json"
        with open(info_path, 'w', encoding='utf-8') as f:
            json.dump(info, f, indent=2, ensure_ascii=False)
        logger.debug(f"Wrote {info_path}")

    def _write_tasks_parquet(self, output_dir: Path):
        """Generate tasks.parquet — v3.0 format (pandas DataFrame with task as index)."""
        tasks_path = output_dir / "meta" / "tasks.parquet"

        task_items = sorted(self._tasks.items(), key=lambda x: x[1])
        df = pd.DataFrame({
            'task_index': [idx for _, idx in task_items],
        }, index=pd.Index([text for text, _ in task_items], name='task'))

        df.to_parquet(str(tasks_path))
        logger.debug(f"Wrote {tasks_path}")

    def _write_episodes_parquet(self, output_dir: Path, camera_keys: set):
        """Generate episodes parquet under meta/episodes/ — v3.0 format."""
        if not self._episode_metas:
            return

        # Build column data
        rows = []
        for meta in self._episode_metas:
            row = {
                'episode_index': meta['episode_index'],
                'length': meta['length'],
                'tasks': meta['tasks'],
                'dataset_from_index': meta['dataset_from_index'],
                'dataset_to_index': meta['dataset_to_index'],
                'data/chunk_index': meta['data_chunk_index'],
                'data/file_index': meta['data_file_index'],
                'meta/episodes/chunk_index': meta['episodes_chunk_index'],
                'meta/episodes/file_index': meta['episodes_file_index'],
            }

            # Video offset columns per camera
            for cam_key in sorted(camera_keys):
                v = meta.get('video_offsets', {}).get(cam_key, {})
                row[f'videos/{cam_key}/chunk_index'] = v.get('chunk_index', 0)
                row[f'videos/{cam_key}/file_index'] = v.get('file_index', 0)
                row[f'videos/{cam_key}/from_timestamp'] = v.get('from_timestamp', 0.0)
                row[f'videos/{cam_key}/to_timestamp'] = v.get('to_timestamp', 0.0)

            # Per-episode stats columns
            ep_stats = meta.get('stats', {})
            for feat_name, feat_stats in ep_stats.items():
                for stat_name, stat_val in feat_stats.items():
                    row[f'stats/{feat_name}/{stat_name}'] = stat_val

            rows.append(row)

        # Build schema dynamically
        fields = [
            pa.field('episode_index', pa.int64()),
            pa.field('length', pa.int64()),
            pa.field('tasks', pa.list_(pa.string())),
            pa.field('dataset_from_index', pa.int64()),
            pa.field('dataset_to_index', pa.int64()),
            pa.field('data/chunk_index', pa.int64()),
            pa.field('data/file_index', pa.int64()),
            pa.field('meta/episodes/chunk_index', pa.int64()),
            pa.field('meta/episodes/file_index', pa.int64()),
        ]

        for cam_key in sorted(camera_keys):
            fields.extend([
                pa.field(f'videos/{cam_key}/chunk_index', pa.int64()),
                pa.field(f'videos/{cam_key}/file_index', pa.int64()),
                pa.field(f'videos/{cam_key}/from_timestamp', pa.float64()),
                pa.field(f'videos/{cam_key}/to_timestamp', pa.float64()),
            ])

        # Stats columns as list types
        ep_stats_sample = self._episode_metas[0].get('stats', {})
        for feat_name, feat_stats in ep_stats_sample.items():
            for stat_name, stat_val in feat_stats.items():
                if isinstance(stat_val, list) and stat_val and isinstance(stat_val[0], int):
                    fields.append(pa.field(f'stats/{feat_name}/{stat_name}',
                                           pa.list_(pa.int64())))
                else:
                    fields.append(pa.field(f'stats/{feat_name}/{stat_name}',
                                           pa.list_(pa.float64())))

        schema = pa.schema(fields)

        # Build column arrays
        columns = {}
        for field_def in schema:
            col_name = field_def.name
            col_data = [r[col_name] for r in rows]
            columns[col_name] = pa.array(col_data, type=field_def.type)

        table = pa.table(columns, schema=schema)

        # Write to chunked path
        chunk_idx = 0
        ep_dir = output_dir / "meta" / "episodes" / f"chunk-{chunk_idx:03d}"
        ep_dir.mkdir(parents=True, exist_ok=True)
        ep_path = ep_dir / "file-000.parquet"
        pq.write_table(table, str(ep_path))
        logger.debug(f"Wrote {ep_path}")

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def _compute_and_write_stats(self, output_dir: Path, total_frames: int):
        """Compute global mean/std/min/max/count for state and action, write stats.json."""
        stats = {}

        if self._all_states:
            all_s = np.concatenate(self._all_states, axis=0)
            stats["observation.state"] = {
                "mean": all_s.mean(axis=0).tolist(),
                "std": all_s.std(axis=0).tolist(),
                "min": all_s.min(axis=0).tolist(),
                "max": all_s.max(axis=0).tolist(),
                "count": [total_frames],
            }

        if self._all_actions:
            all_a = np.concatenate(self._all_actions, axis=0)
            stats["action"] = {
                "mean": all_a.mean(axis=0).tolist(),
                "std": all_a.std(axis=0).tolist(),
                "min": all_a.min(axis=0).tolist(),
                "max": all_a.max(axis=0).tolist(),
                "count": [total_frames],
            }

        stats_path = output_dir / "meta" / "stats.json"
        with open(stats_path, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2)
        logger.debug(f"Wrote {stats_path}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_dir_size_mb(dir_path: Path) -> float:
        """Compute total size of all files in a directory tree in MB."""
        total = 0
        if dir_path.exists():
            for f in dir_path.rglob('*'):
                if f.is_file():
                    total += f.stat().st_size
        return total / (1024 * 1024)

    @staticmethod
    def _get_state_names() -> List[str]:
        """Return name list for the 29-dim state vector."""
        names = []
        for axis in ['x', 'y', 'z']:
            names.append(f"tcp_position.{axis}")
        for comp in ['w', 'x', 'y', 'z']:
            names.append(f"tcp_quaternion.{comp}")
        for i in range(7):
            names.append(f"joint_positions.j{i}")
        for i in range(7):
            names.append(f"joint_velocities.j{i}")
        for i in range(7):
            names.append(f"joint_efforts.j{i}")
        names.append("hand_state")
        return names

    @staticmethod
    def _get_action_names() -> List[str]:
        """Return name list for the 7-dim delta action vector."""
        return [
            "delta_position.x", "delta_position.y", "delta_position.z",
            "delta_rotation.rx", "delta_rotation.ry", "delta_rotation.rz",
            "hand_command",
        ]
