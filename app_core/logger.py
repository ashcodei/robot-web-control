"""
Logger Module
统一日志系统模块

Provides unified logging for all modules with GUI integration.
为所有模块提供统一的日志记录，支持GUI集成。

Log structure:
日志结构:
    logs/
    ├── 2026-01-27/
    │   ├── session_001_10-30-45.log
    │   ├── session_002_14-20-30.log
    │   └── ...
    ├── 2026-01-28/
    │   ├── session_001_09-00-00.log
    │   └── ...
    └── ...
"""

import logging
import sys
import os
import re
from datetime import datetime
from typing import Optional, Callable, List, Dict, Any
from enum import Enum
import threading
from dataclasses import dataclass
import queue
from pathlib import Path


class LogLevel(Enum):
    """Log level enumeration / 日志级别枚举"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class LogEntry:
    """Log entry data class / 日志条目数据类"""
    timestamp: datetime
    level: LogLevel
    source: str
    message: str
    extra: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "level": self.level.value,
            "source": self.source,
            "message": self.message,
            "extra": self.extra or {}
        }

    def format(self, include_date: bool = False) -> str:
        """Format log entry as string / 将日志条目格式化为字符串"""
        if include_date:
            time_str = self.timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        else:
            time_str = self.timestamp.strftime("%H:%M:%S.%f")[:-3]

        return f"[{time_str}] [{self.level.value}] [{self.source}] {self.message}"


class GUILogHandler(logging.Handler):
    """
    Custom log handler that integrates with GUI and event bus.
    与GUI和事件总线集成的自定义日志处理器。
    """

    def __init__(self, logger_instance: 'AppLogger'):
        super().__init__()
        self.logger = logger_instance

    def emit(self, record: logging.LogRecord):
        try:
            level = LogLevel[record.levelname]
            entry = LogEntry(
                timestamp=datetime.fromtimestamp(record.created),
                level=level,
                source=record.name,
                message=record.getMessage(),
                extra=getattr(record, 'extra', None)
            )
            self.logger._add_entry(entry)
        except Exception:
            self.handleError(record)


class AppLogger:
    """
    Application Logger with GUI integration and file persistence.
    带有GUI集成和文件持久化的应用程序日志记录器。

    Features:
    - Daily log folders (e.g., logs/2026-01-27/)
    - Session-based log files (e.g., session_001_10-30-45.log)
    - GUI integration via event bus
    - Thread-safe operations

    Singleton pattern implementation.
    单例模式实现。
    """

    _instance: Optional['AppLogger'] = None
    _lock = threading.Lock()

    def __new__(cls):
        """Singleton pattern / 单例模式"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._entries: List[LogEntry] = []
        self._max_entries = 10000
        self._callbacks: List[Callable[[LogEntry], None]] = []
        self._entries_lock = threading.Lock()
        self._log_queue: queue.Queue = queue.Queue()
        self._file_handler: Optional[logging.FileHandler] = None
        self._log_file_path: Optional[str] = None
        self._session_number: int = 0

        # Delay event bus import to avoid circular dependency
        self._event_bus = None

        # Setup root logger
        self._setup_logging()

        self._initialized = True

    def _get_event_bus(self):
        """Lazy load event bus to avoid circular import"""
        if self._event_bus is None:
            from app_core.event_bus import get_event_bus, EventType
            self._event_bus = get_event_bus()
        return self._event_bus

    def _get_log_directory(self) -> Path:
        """
        Get or create log directory structure.
        获取或创建日志目录结构。

        Returns:
            Path to today's log directory
        """
        # Base logs directory
        base_dir = Path(__file__).parent.parent / "logs"
        base_dir.mkdir(parents=True, exist_ok=True)

        # Today's date folder
        today = datetime.now().strftime("%Y-%m-%d")
        today_dir = base_dir / today
        today_dir.mkdir(parents=True, exist_ok=True)

        return today_dir

    def _get_session_number(self, log_dir: Path) -> int:
        """
        Calculate session number for today.
        计算今天的会话编号。

        Scans existing log files and returns the next session number.
        扫描现有日志文件并返回下一个会话编号。

        Args:
            log_dir: Today's log directory

        Returns:
            Next session number (1-based)
        """
        # Pattern: session_XXX_HH-MM-SS.log
        pattern = re.compile(r'session_(\d{3})_\d{2}-\d{2}-\d{2}\.log')

        max_session = 0
        for file in log_dir.iterdir():
            if file.is_file():
                match = pattern.match(file.name)
                if match:
                    session_num = int(match.group(1))
                    max_session = max(max_session, session_num)

        return max_session + 1

    def _create_log_filename(self, log_dir: Path) -> Path:
        """
        Create log filename with session number and timestamp.
        创建带有会话编号和时间戳的日志文件名。

        Format: session_XXX_HH-MM-SS.log

        Args:
            log_dir: Today's log directory

        Returns:
            Full path to the log file
        """
        self._session_number = self._get_session_number(log_dir)
        timestamp = datetime.now().strftime("%H-%M-%S")
        filename = f"session_{self._session_number:03d}_{timestamp}.log"
        return log_dir / filename

    def _setup_logging(self):
        """Setup Python logging configuration / 设置Python日志配置"""
        # Get today's log directory
        log_dir = self._get_log_directory()

        # Create log file path
        log_path = self._create_log_filename(log_dir)
        self._log_file_path = str(log_path)

        # Setup root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)

        # Remove existing handlers to avoid duplicates
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_format = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
            datefmt='%H:%M:%S'
        )
        console_handler.setFormatter(console_format)
        root_logger.addHandler(console_handler)

        # File handler with detailed format
        self._file_handler = logging.FileHandler(
            self._log_file_path,
            encoding='utf-8',
            mode='w'  # Start fresh for each session
        )
        self._file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter(
            '[%(asctime)s.%(msecs)03d] [%(levelname)-8s] [%(name)-30s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self._file_handler.setFormatter(file_format)
        root_logger.addHandler(self._file_handler)

        # GUI handler
        gui_handler = GUILogHandler(self)
        gui_handler.setLevel(logging.DEBUG)
        root_logger.addHandler(gui_handler)

        # Write session header
        self._write_session_header()

    def _write_session_header(self):
        """Write session header to log file / 在日志文件中写入会话头信息"""
        logger = logging.getLogger("system")
        logger.info("=" * 70)
        logger.info("  Automatic Cooking Robot Control System - Session Log")
        logger.info("  自动做饭机器人控制系统 - 会话日志")
        logger.info("=" * 70)
        logger.info(f"  Session Number: {self._session_number}")
        logger.info(f"  Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"  Log File: {self._log_file_path}")
        logger.info("=" * 70)

    def _add_entry(self, entry: LogEntry):
        """Add log entry / 添加日志条目"""
        with self._entries_lock:
            self._entries.append(entry)
            if len(self._entries) > self._max_entries:
                self._entries = self._entries[-self._max_entries:]

        # Notify callbacks (with error logging)
        for callback in self._callbacks:
            try:
                callback(entry)
            except Exception as e:
                # Log to file directly to avoid recursion
                sys.stderr.write(f"Log callback error: {e}\n")

        # Publish to event bus (lazy loaded)
        try:
            from app_core.event_bus import EventType
            event_bus = self._get_event_bus()
            event_bus.publish(
                EventType.LOG_MESSAGE,
                entry.source,
                entry.to_dict()
            )
        except Exception:
            pass  # Event bus may not be ready during initialization

    def add_callback(self, callback: Callable[[LogEntry], None]):
        """Add log entry callback / 添加日志条目回调"""
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[LogEntry], None]):
        """Remove log entry callback / 移除日志条目回调"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def get_entries(self, level: LogLevel = None,
                    source: str = None,
                    limit: int = 100) -> List[LogEntry]:
        """
        Get log entries with optional filtering.
        获取日志条目，支持可选过滤。

        Args:
            level: Filter by level (None = all)
            source: Filter by source (None = all)
            limit: Maximum number of entries to return

        Returns:
            List of log entries (newest first)
        """
        with self._entries_lock:
            entries = list(self._entries)

        if level:
            entries = [e for e in entries if e.level == level]

        if source:
            entries = [e for e in entries if e.source == source]

        return entries[-limit:][::-1]

    def clear(self):
        """Clear all log entries / 清空所有日志条目"""
        with self._entries_lock:
            self._entries.clear()

    def get_logger(self, name: str) -> logging.Logger:
        """
        Get a named logger.
        获取命名的日志记录器。

        Args:
            name: Logger name (usually module name)

        Returns:
            Python logger instance
        """
        return logging.getLogger(name)

    @property
    def log_file_path(self) -> Optional[str]:
        """Get current log file path / 获取当前日志文件路径"""
        return self._log_file_path

    @property
    def session_number(self) -> int:
        """Get current session number / 获取当前会话编号"""
        return self._session_number

    def flush(self):
        """Flush log file handler / 刷新日志文件处理器"""
        if self._file_handler:
            self._file_handler.flush()


# Global logger instance / 全局日志实例
_app_logger: Optional[AppLogger] = None


def get_app_logger() -> AppLogger:
    """Get the global application logger / 获取全局应用日志记录器"""
    global _app_logger
    if _app_logger is None:
        _app_logger = AppLogger()
    return _app_logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a named logger instance.
    获取命名的日志记录器实例。

    This is the main entry point for getting loggers in modules.
    这是模块中获取日志记录器的主要入口点。

    Args:
        name: Logger name (usually __name__)

    Returns:
        Python logger instance
    """
    return get_app_logger().get_logger(name)
