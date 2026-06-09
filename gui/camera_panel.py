"""
Camera Panel Module (PySide6)
摄像头面板模块

Panel for dual camera display and controls using QPainter.
用于双摄像头显示和控制的面板，使用 QPainter。
"""

import threading
import time
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple, List, Callable, Dict, Any

from gui.qt_imports import (
    QWidget, QGroupBox, QVBoxLayout, QHBoxLayout, QFrame,
    QLabel, QPushButton, QCheckBox,
    QPainter, QPen, QBrush, QColor, QImage, QPixmap, QFont,
    Qt, QRect, QPoint, QSize,
    QMouseEvent, QPaintEvent, QResizeEvent,
)
from config.i18n import t
from config.settings import get_settings
from app_core.logger import get_logger
from app_core.event_bus import get_event_bus, EventType
from gui.signals import get_thread_bridge

logger = get_logger(__name__)


@dataclass
class ROI:
    """Region of Interest / 感兴趣区域"""
    x: int
    y: int
    width: int
    height: int
    name: str = "ROI"
    color: str = "#00ff00"

    def to_tuple(self) -> Tuple[int, int, int, int]:
        return (self.x, self.y, self.width, self.height)

    def contains_point(self, px: int, py: int) -> bool:
        return (self.x <= px <= self.x + self.width and
                self.y <= py <= self.y + self.height)


class CameraView(QWidget):
    """
    Camera display widget with ROI selection using QPainter.
    支持 ROI 选择的摄像头显示部件，使用 QPainter。
    """

    def __init__(self, parent=None, width=320, height=240):
        super().__init__(parent)
        self.setMinimumSize(160, 120)

        self._roi_mode = False
        self._roi_start: Optional[QPoint] = None
        self._roi_current: Optional[QPoint] = None
        self._rois: List[ROI] = []
        self._roi_callback: Optional[Callable[[ROI], None]] = None

        self._current_pixmap: Optional[QPixmap] = None
        self._placeholder_text = "Camera Feed\n摄像头画面"

    def set_roi_mode(self, enabled: bool):
        self._roi_mode = enabled
        self.setCursor(Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.ArrowCursor)
        if not enabled:
            self._roi_start = None
            self._roi_current = None
            self.update()

    def set_roi_callback(self, callback: Callable[[ROI], None]):
        self._roi_callback = callback

    def update_frame(self, qimage: QImage):
        """Update display with new QImage (called from main thread)."""
        self._current_pixmap = QPixmap.fromImage(qimage)
        self.update()

    def set_placeholder(self, text: str = "Camera Feed\n摄像头画面"):
        self._placeholder_text = text
        self._current_pixmap = None
        self.update()

    def clear_rois(self):
        self._rois.clear()
        self.update()

    def get_rois(self) -> List[ROI]:
        return self._rois.copy()

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        if self._current_pixmap:
            # Scale pixmap to fit
            scaled = self._current_pixmap.scaled(
                w, h, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            x = (w - scaled.width()) // 2
            y = (h - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        else:
            # Draw placeholder
            painter.fillRect(0, 0, w, h, QColor('#2d2d2d'))
            painter.setPen(QPen(QColor('#666666')))
            painter.setFont(QFont('Arial', 10))
            painter.drawText(QRect(0, 0, w, h), Qt.AlignmentFlag.AlignCenter,
                           self._placeholder_text)

        # Draw ROIs
        for roi in self._rois:
            painter.setPen(QPen(QColor(roi.color), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(roi.x, roi.y, roi.width, roi.height)
            painter.setFont(QFont('Arial', 9))
            painter.drawText(roi.x + 5, roi.y + 15, roi.name)

        # Draw temp ROI selection
        if self._roi_start and self._roi_current:
            painter.setPen(QPen(QColor('#00ff00'), 2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            x1, y1 = self._roi_start.x(), self._roi_start.y()
            x2, y2 = self._roi_current.x(), self._roi_current.y()
            painter.drawRect(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))

        painter.end()

    def mousePressEvent(self, event: QMouseEvent):
        if not self._roi_mode or event.button() != Qt.MouseButton.LeftButton:
            return
        self._roi_start = event.position().toPoint()

    def mouseMoveEvent(self, event: QMouseEvent):
        if not self._roi_mode or not self._roi_start:
            return
        self._roi_current = event.position().toPoint()
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if not self._roi_mode or not self._roi_start:
            return

        pos = event.position().toPoint()
        x1, y1 = self._roi_start.x(), self._roi_start.y()
        x2, y2 = pos.x(), pos.y()

        x = min(x1, x2)
        y = min(y1, y2)
        w = abs(x2 - x1)
        h = abs(y2 - y1)

        if w > 10 and h > 10:
            roi = ROI(x=x, y=y, width=w, height=h, name=f"ROI_{len(self._rois) + 1}")
            self._rois.append(roi)
            if self._roi_callback:
                self._roi_callback(roi)

        self._roi_start = None
        self._roi_current = None
        self.update()


class CameraPanel(QGroupBox):
    """
    Dual camera display panel with ROI selection.
    双摄像头显示面板，支持 ROI 选择。
    """

    def __init__(self, parent=None):
        super().__init__(t("panel.camera"), parent)
        self.settings = get_settings()
        self.event_bus = get_event_bus()
        self._bridge = get_thread_bridge()

        self._is_running = False
        self._is_recording = False
        self._capture_threads: Dict[int, threading.Thread] = {}
        self._video_writers: Dict[int, Any] = {}
        self._recording_lock = threading.Lock()

        self._frame_counts: Dict[int, int] = {0: 0, 1: 0}
        self._fps_start_time = time.time()
        self._current_fps: Dict[int, float] = {0: 0.0, 1: 0.0}

        self._project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._available_cameras: List[int] = []
        self._detection_done = False
        self._capture_generation = 0

        self._active_cameras: Dict[int, bool] = {}
        self._camera_release_event = threading.Event()
        self._camera_release_event.set()
        self._skip_callbacks = False

        self._last_frames: Dict[int, Any] = {}
        self._frame_lock = threading.Lock()

        # Connect thread bridge signal for frame updates
        self._bridge.frame_ready.connect(self._on_frame_ready)

        self._build_ui()
        self._detect_cameras()

    def _get_image_dir(self) -> str:
        date_str = datetime.now().strftime("%Y-%m-%d")
        path = os.path.join(self._project_root, "Images&Video", "Image", date_str)
        os.makedirs(path, exist_ok=True)
        return path

    def _get_video_dir(self) -> str:
        date_str = datetime.now().strftime("%Y-%m-%d")
        path = os.path.join(self._project_root, "Images&Video", "Video", date_str)
        os.makedirs(path, exist_ok=True)
        return path

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Camera display area
        display_layout = QHBoxLayout()

        # Left camera
        left_frame = QVBoxLayout()
        self.cam_label1 = QLabel("Camera 1")
        self.cam_label1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_frame.addWidget(self.cam_label1)
        self.canvas1 = CameraView(self)
        self.canvas1.set_roi_callback(self._on_roi_created)
        left_frame.addWidget(self.canvas1)
        display_layout.addLayout(left_frame)

        # Right camera
        right_frame = QVBoxLayout()
        self.cam_label2 = QLabel("Camera 2")
        self.cam_label2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_frame.addWidget(self.cam_label2)
        self.canvas2 = CameraView(self)
        self.canvas2.set_roi_callback(self._on_roi_created)
        right_frame.addWidget(self.canvas2)
        display_layout.addLayout(right_frame)

        layout.addLayout(display_layout)

        self._canvases = {0: self.canvas1, 1: self.canvas2}

        # Info bar
        info_layout = QHBoxLayout()
        self.fps_label1 = QLabel("Cam1: --")
        self.fps_label1.setStyleSheet("font-size: 9pt;")
        info_layout.addWidget(self.fps_label1)
        self.res_label1 = QLabel("--x--")
        self.res_label1.setStyleSheet("font-size: 9pt;")
        info_layout.addWidget(self.res_label1)
        self.fps_label2 = QLabel("Cam2: --")
        self.fps_label2.setStyleSheet("font-size: 9pt;")
        info_layout.addWidget(self.fps_label2)
        self.res_label2 = QLabel("--x--")
        self.res_label2.setStyleSheet("font-size: 9pt;")
        info_layout.addWidget(self.res_label2)
        info_layout.addStretch()
        self.roi_count_label = QLabel("ROI: 0")
        self.roi_count_label.setStyleSheet("font-size: 9pt;")
        info_layout.addWidget(self.roi_count_label)
        layout.addLayout(info_layout)

        self._fps_labels = {0: self.fps_label1, 1: self.fps_label2}
        self._res_labels = {0: self.res_label1, 1: self.res_label2}

        # Control buttons row 1
        btn_layout1 = QHBoxLayout()
        self.start_btn = QPushButton(t("common.start"))
        self.start_btn.clicked.connect(self._toggle_camera)
        btn_layout1.addWidget(self.start_btn)

        self.capture_btn = QPushButton(t("panel.capture"))
        self.capture_btn.clicked.connect(self._on_capture)
        btn_layout1.addWidget(self.capture_btn)

        self.record_btn = QPushButton(t("panel.record"))
        self.record_btn.clicked.connect(self._toggle_recording)
        btn_layout1.addWidget(self.record_btn)
        btn_layout1.addStretch()
        layout.addLayout(btn_layout1)

        # Control buttons row 2 (ROI)
        btn_layout2 = QHBoxLayout()
        self.roi_check = QCheckBox("ROI Mode")
        self.roi_check.toggled.connect(self._toggle_roi_mode)
        btn_layout2.addWidget(self.roi_check)

        self.clear_roi_btn = QPushButton("Clear ROI")
        self.clear_roi_btn.clicked.connect(self._clear_rois)
        btn_layout2.addWidget(self.clear_roi_btn)
        btn_layout2.addStretch()
        layout.addLayout(btn_layout2)

    # ── Camera detection ──

    def _detect_cameras(self):
        self._detection_done = False

        def detect():
            try:
                import cv2
                available = []
                if sys.platform.startswith('win'):
                    backend = cv2.CAP_DSHOW
                elif sys.platform.startswith('linux'):
                    backend = cv2.CAP_V4L2
                else:
                    backend = cv2.CAP_ANY
                for i in range(8):
                    cap = cv2.VideoCapture(i, backend)
                    if cap.isOpened():
                        ret, _ = cap.read()
                        if ret:
                            available.append(i)
                            logger.info(f"Detected camera {i}")
                    cap.release()
                self._available_cameras = available
                logger.info(f"Available cameras: {available}")
            except ImportError:
                self._available_cameras = [0]
            finally:
                self._detection_done = True
                self._bridge.gui_callback.emit(self._update_camera_labels)

        threading.Thread(target=detect, daemon=True, name="CameraDetect").start()

    def _update_camera_labels(self):
        cams = self._available_cameras
        self.cam_label1.setText(f"Camera {cams[0]}" if len(cams) >= 1 else "Camera 1 (N/A)")
        self.cam_label2.setText(f"Camera {cams[1]}" if len(cams) >= 2 else "Camera 2 (N/A)")

    # ── ROI ──

    def _toggle_roi_mode(self, enabled):
        self.canvas1.set_roi_mode(enabled)
        self.canvas2.set_roi_mode(enabled)

    def _on_roi_created(self, roi: ROI):
        total = len(self.canvas1.get_rois()) + len(self.canvas2.get_rois())
        self.roi_count_label.setText(f"ROI: {total}")
        logger.info(f"ROI created: {roi.name} at ({roi.x}, {roi.y}) size {roi.width}x{roi.height}")

    def _clear_rois(self):
        self.canvas1.clear_rois()
        self.canvas2.clear_rois()
        self.roi_count_label.setText("ROI: 0")

    # ── Frame ready signal handler ──

    def _on_frame_ready(self, slot: int, qimage):
        """Handle frame from capture thread (runs on main thread via signal)."""
        if self._skip_callbacks or not self._is_running:
            return
        canvas = self._canvases.get(slot)
        if canvas:
            canvas.update_frame(qimage)

    # ── Camera start/stop ──

    def _toggle_camera(self):
        if self._is_running:
            self._stop_camera()
        else:
            self._start_camera()

    def _start_camera(self):
        if not self._detection_done:
            from gui.qt_imports import QTimer
            QTimer.singleShot(300, self._start_camera)
            return

        if self._active_cameras:
            self.start_btn.setEnabled(False)
            from gui.qt_imports import QTimer
            QTimer.singleShot(100, lambda: self._start_camera_after_release(0))
            return

        self._do_start_camera()

    def _start_camera_after_release(self, retry_count=0):
        if not self._camera_release_event.is_set():
            if self._active_cameras and retry_count < 30:
                from gui.qt_imports import QTimer
                QTimer.singleShot(100, lambda: self._start_camera_after_release(retry_count + 1))
                return
            elif retry_count >= 30:
                logger.warning("Camera release timeout, forcing start")
                self._active_cameras.clear()
                self._camera_release_event.set()

        self.start_btn.setEnabled(True)
        self._do_start_camera()

    def _do_start_camera(self):
        try:
            import cv2

            self._skip_callbacks = False
            self._capture_generation += 1
            self._is_running = True
            self.start_btn.setText(t("common.stop"))
            self.start_btn.setEnabled(True)

            self._frame_counts = {0: 0, 1: 0}
            self._fps_start_time = time.time()
            with self._frame_lock:
                self._last_frames = {}

            gen = self._capture_generation
            cams = self._available_cameras
            self._camera_release_event.clear()

            for slot in range(min(2, len(cams))):
                camera_id = cams[slot]
                self._active_cameras[slot] = True
                logger.info(f"Starting slot {slot} -> camera {camera_id} (gen={gen})")
                t_thread = threading.Thread(
                    target=self._capture_loop,
                    args=(slot, camera_id, gen),
                    daemon=True,
                    name=f"CameraCapture-{slot}"
                )
                self._capture_threads[slot] = t_thread
                t_thread.start()

            if len(cams) < 2:
                self.canvas2.set_placeholder("No Camera\n无摄像头")

            self._start_fps_timer()

        except ImportError:
            logger.warning("OpenCV not installed, camera preview disabled")
            self._is_running = True
            self.start_btn.setText(t("common.stop"))
            self._show_no_opencv_message()

    def _stop_camera(self):
        self._skip_callbacks = True
        self._is_running = False
        self._capture_generation += 1

        self.start_btn.setText(t("common.start"))

        if self._is_recording:
            threading.Thread(
                target=self._stop_recording_background,
                daemon=True, name="StopRecording"
            ).start()

        self.fps_label1.setText("Cam1: --")
        self.fps_label2.setText("Cam2: --")
        self.res_label1.setText("--x--")
        self.res_label2.setText("--x--")

        from gui.qt_imports import QTimer
        QTimer.singleShot(300, self._draw_placeholders_if_stopped)

        if self._frame_lock.acquire(blocking=False):
            try:
                self._last_frames = {}
            finally:
                self._frame_lock.release()

        if self._active_cameras:
            self._camera_release_event.clear()

    def _draw_placeholders_if_stopped(self):
        if not self._is_running:
            self.canvas1.set_placeholder()
            self.canvas2.set_placeholder()

    def _stop_recording_background(self):
        with self._recording_lock:
            self._is_recording = False
            for slot, writer in self._video_writers.items():
                try:
                    writer.release()
                except Exception as e:
                    logger.warning(f"Error releasing video writer {slot}: {e}")
            self._video_writers = {}
        self._bridge.gui_callback.emit(lambda: self.record_btn.setText(t("panel.record")))

    # ── FPS ──

    def _start_fps_timer(self):
        if not hasattr(self, '_fps_timer'):
            from gui.qt_imports import QTimer
            self._fps_timer = QTimer(self)
            self._fps_timer.timeout.connect(self._update_fps_display)
        self._fps_timer.start(500)

    def _update_fps_display(self):
        if not self._is_running:
            if hasattr(self, '_fps_timer'):
                self._fps_timer.stop()
            return

        elapsed = time.time() - self._fps_start_time
        if elapsed > 0:
            self._current_fps[0] = self._frame_counts[0] / elapsed
            self._current_fps[1] = self._frame_counts[1] / elapsed

        self.fps_label1.setText(f"Cam1: {self._current_fps[0]:.1f}")
        self.fps_label2.setText(f"Cam2: {self._current_fps[1]:.1f}")

        if elapsed > 2.0:
            self._frame_counts = {0: 0, 1: 0}
            self._fps_start_time = time.time()

    # ── Capture loop ──

    def _open_camera(self, camera_id: int):
        import cv2

        if sys.platform.startswith('linux'):
            backend = cv2.CAP_V4L2
        elif sys.platform.startswith('win'):
            backend = cv2.CAP_DSHOW
        else:
            backend = cv2.CAP_ANY
        cap = cv2.VideoCapture(camera_id, backend)

        if not cap.isOpened():
            logger.error(f"Failed to open camera {camera_id}")
            return None, 0, 0

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.settings.camera.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.settings.camera.height)
        cap.set(cv2.CAP_PROP_FPS, self.settings.camera.fps)

        if sys.platform.startswith('linux'):
            fourcc = cv2.VideoWriter_fourcc('M', 'J', 'P', 'G')
            cap.set(cv2.CAP_PROP_FOURCC, fourcc)

        cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)

        actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        logger.info(f"Camera {camera_id} opened: {actual_width}x{actual_height}")
        return cap, actual_width, actual_height

    def _capture_loop(self, slot: int, camera_id: int, my_generation: int):
        cap = None
        try:
            import cv2

            cap, actual_width, actual_height = self._open_camera(camera_id)

            if cap is None:
                if self._capture_generation == my_generation:
                    cid = camera_id
                    self._bridge.gui_callback.emit(
                        lambda: self._canvases[slot].set_placeholder(
                            f"Cannot open camera {cid}\n无法打开摄像头 {cid}"))
                return

            if self._capture_generation == my_generation:
                w, h = actual_width, actual_height
                self._bridge.gui_callback.emit(
                    lambda: self._res_labels[slot].setText(f"{w}x{h}"))

            fail_count = 0
            target_interval = 1.0 / self.settings.camera.fps
            loop_start = time.time()

            while self._is_running and self._capture_generation == my_generation:
                ret, frame = cap.read()

                if not self._is_running or self._capture_generation != my_generation:
                    break

                if ret:
                    fail_count = 0
                    self._frame_counts[slot] += 1

                    if self._capture_generation != my_generation:
                        break

                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                    with self._frame_lock:
                        self._last_frames[slot] = (frame, frame_rgb, time.time())

                    with self._recording_lock:
                        writer = self._video_writers.get(slot)
                        if self._is_recording and writer:
                            writer.write(frame)

                    # Convert numpy RGB to QImage
                    h, w, ch = frame_rgb.shape
                    bytes_per_line = ch * w
                    qimage = QImage(frame_rgb.data, w, h, bytes_per_line,
                                   QImage.Format.Format_RGB888).copy()

                    if self._capture_generation == my_generation:
                        self._bridge.frame_ready.emit(slot, qimage)
                else:
                    fail_count += 1
                    if fail_count == 1:
                        logger.warning(f"Camera {camera_id} (slot {slot}): frame read failed")
                    if fail_count >= 30:
                        logger.error(f"Camera {camera_id} (slot {slot}): too many failures")
                        if self._capture_generation == my_generation:
                            self._bridge.gui_callback.emit(
                                lambda: self._canvases[slot].set_placeholder(
                                    "Camera read failed\n摄像头读取失败"))
                        break

                elapsed = time.time() - loop_start
                sleep_time = target_interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
                loop_start = time.time()

        except Exception as e:
            logger.error(f"Camera {camera_id} (slot {slot}) error: {e}", exc_info=True)
            if self._capture_generation == my_generation:
                self._bridge.gui_callback.emit(
                    lambda: self._canvases[slot].set_placeholder(
                        f"Camera Error\n摄像头错误\n\n{e}"))
        finally:
            if cap is not None:
                try:
                    cap.release()
                    logger.info(f"Camera {camera_id} (slot {slot}) released")
                except Exception:
                    pass

            if slot in self._active_cameras:
                del self._active_cameras[slot]

            if not self._active_cameras:
                self._camera_release_event.set()

    def _show_no_opencv_message(self):
        msg = "OpenCV not installed\n未安装OpenCV\n\npip install opencv-python"
        self.canvas1.set_placeholder(msg)
        self.canvas2.set_placeholder(msg)

    # ── Screenshot ──

    def _on_capture(self):
        if not self._is_running:
            return

        try:
            import cv2
            save_dir = self._get_image_dir()
            timestamp = datetime.now().strftime("%H_%M_%S")
            saved = 0

            with self._frame_lock:
                frames_snapshot = dict(self._last_frames)

            for slot in range(min(2, len(self._available_cameras))):
                entry = frames_snapshot.get(slot)
                if entry is not None:
                    bgr_frame = entry[0] if isinstance(entry, tuple) else entry
                    filename = os.path.join(save_dir, f"{timestamp}_camera{slot + 1}.jpg")
                    cv2.imwrite(filename, bgr_frame)
                    logger.info(f"Screenshot saved: {filename}")
                    saved += 1

            if saved > 0:
                self.capture_btn.setText(f"Saved {saved}!")
                from gui.qt_imports import QTimer
                QTimer.singleShot(1000, lambda: self.capture_btn.setText(t("panel.capture")))

        except Exception as e:
            logger.error(f"Capture error: {e}")

    # ── Recording ──

    def _toggle_recording(self):
        if self._is_recording:
            self.record_btn.setText(t("panel.record"))
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        if not self._is_running:
            return

        try:
            import cv2
            save_dir = self._get_video_dir()
            timestamp = datetime.now().strftime("%H_%M_%S")
            fourcc = cv2.VideoWriter_fourcc(*'XVID')
            writers = {}

            for slot in range(min(2, len(self._available_cameras))):
                filename = os.path.join(save_dir, f"{timestamp}_camera{slot + 1}.avi")
                writer = cv2.VideoWriter(
                    filename, fourcc, self.settings.camera.fps,
                    (self.settings.camera.width, self.settings.camera.height)
                )
                writers[slot] = writer
                logger.info(f"Recording started: {filename}")

            with self._recording_lock:
                self._video_writers = writers
                self._is_recording = True

            self.record_btn.setText(f"{t('panel.record')} ●")

        except Exception as e:
            logger.error(f"Failed to start recording: {e}")

    def _stop_recording(self):
        if not self._is_recording:
            return
        threading.Thread(
            target=self._stop_recording_background,
            daemon=True, name="StopRecording"
        ).start()

    # ── Public API ──

    def update_language(self):
        self.setTitle(t("panel.camera"))
        if self._is_running:
            self.start_btn.setText(t("common.stop"))
        else:
            self.start_btn.setText(t("common.start"))
        self.capture_btn.setText(t("panel.capture"))
        if self._is_recording:
            self.record_btn.setText(f"{t('panel.record')} ●")
        else:
            self.record_btn.setText(t("panel.record"))

    def get_rois(self) -> List[ROI]:
        return self.canvas1.get_rois() + self.canvas2.get_rois()

    def get_current_fps(self) -> float:
        fps_values = [v for v in self._current_fps.values() if v > 0]
        return sum(fps_values) / len(fps_values) if fps_values else 0.0

    def get_last_frames(self) -> Dict[int, tuple]:
        with self._frame_lock:
            return dict(self._last_frames)

    def _cleanup(self):
        self._is_running = False
        self._capture_generation += 1

        if hasattr(self, '_fps_timer'):
            self._fps_timer.stop()

        with self._recording_lock:
            for writer in self._video_writers.values():
                try:
                    writer.release()
                except Exception:
                    pass
            self._video_writers = {}
            self._is_recording = False

        self._active_cameras.clear()
        self._camera_release_event.set()
        self._capture_threads = {}
