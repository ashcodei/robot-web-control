"""
Threading Model Module
线程模型模块

Provides thread-safe command execution for hardware controllers.
为硬件控制器提供线程安全的命令执行。

This prevents GUI blocking when executing hardware operations.
这可以防止执行硬件操作时GUI阻塞。
"""

import threading
import queue
import time
from typing import Callable, Any, Optional, Dict, Tuple
from dataclasses import dataclass
from enum import Enum


class CommandPriority(Enum):
    """Command priority enumeration / 命令优先级枚举"""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    EMERGENCY = 3  # Highest priority for emergency operations


@dataclass
class CommandResult:
    """Command execution result / 命令执行结果"""
    success: bool
    result: Any
    error: Optional[Exception]
    execution_time_ms: float
    command_id: str


class HardwareCommandQueue:
    """
    Thread-safe command queue for hardware operations.
    用于硬件操作的线程安全命令队列。

    Executes hardware commands in a separate thread to prevent GUI blocking.
    在单独的线程中执行硬件命令以防止GUI阻塞。
    """

    def __init__(self, name: str = "hardware"):
        """
        Initialize command queue.

        Args:
            name: Queue name for identification
        """
        self.name = name
        self.command_queue: queue.PriorityQueue = queue.PriorityQueue()
        self.result_queue: queue.Queue = queue.Queue()
        self.worker_thread: Optional[threading.Thread] = None
        self.is_running = False
        self._command_counter = 0
        self._counter_lock = threading.Lock()
        self._pending_callbacks: Dict[str, Callable] = {}

    def start(self):
        """Start worker thread / 启动工作线程"""
        if self.is_running:
            return

        self.is_running = True
        self.worker_thread = threading.Thread(
            target=self._worker_loop,
            name=f"CommandQueue-{self.name}",
            daemon=True
        )
        self.worker_thread.start()

    def stop(self, timeout: float = 2.0):
        """
        Stop worker thread.
        停止工作线程。

        Args:
            timeout: Maximum time to wait for thread to stop
        """
        self.is_running = False
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=timeout)

    def _generate_command_id(self) -> str:
        """Generate unique command ID / 生成唯一命令ID"""
        with self._counter_lock:
            self._command_counter += 1
            return f"{self.name}-{time.time()}-{self._command_counter}"

    def execute_async(self, command: Callable, *args,
                      callback: Callable[[CommandResult], None] = None,
                      priority: CommandPriority = CommandPriority.NORMAL,
                      **kwargs) -> str:
        """
        Execute command asynchronously.
        异步执行命令。

        Args:
            command: Function to execute
            *args: Positional arguments
            callback: Callback for result (called in main thread via result_queue)
            priority: Command priority
            **kwargs: Keyword arguments

        Returns:
            Command ID for tracking
        """
        command_id = self._generate_command_id()

        if callback:
            self._pending_callbacks[command_id] = callback

        # Priority queue uses (priority, timestamp, data)
        # Lower number = higher priority, so we negate the enum value
        self.command_queue.put((
            -priority.value,
            time.time(),
            (command_id, command, args, kwargs)
        ))

        return command_id

    def execute_sync(self, command: Callable, *args,
                     timeout: float = 30.0,
                     **kwargs) -> CommandResult:
        """
        Execute command synchronously (blocking).
        同步执行命令（阻塞）。

        WARNING: Do not call from GUI thread!
        警告：不要从GUI线程调用！

        Args:
            command: Function to execute
            timeout: Maximum execution time
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            CommandResult with execution details
        """
        result_event = threading.Event()
        result_container = [None]

        def sync_callback(result: CommandResult):
            result_container[0] = result
            result_event.set()

        command_id = self.execute_async(
            command, *args,
            callback=sync_callback,
            priority=CommandPriority.HIGH,
            **kwargs
        )

        # Wait for result
        if result_event.wait(timeout=timeout):
            return result_container[0]
        else:
            return CommandResult(
                success=False,
                result=None,
                error=TimeoutError(f"Command timed out after {timeout}s"),
                execution_time_ms=timeout * 1000,
                command_id=command_id
            )

    def _worker_loop(self):
        """Worker thread main loop / 工作线程主循环"""
        while self.is_running:
            try:
                # Get command with timeout to allow checking is_running
                _, _, (command_id, command, args, kwargs) = \
                    self.command_queue.get(timeout=0.1)

                # Execute command
                start_time = time.time()
                try:
                    result = command(*args, **kwargs)
                    execution_time_ms = (time.time() - start_time) * 1000
                    cmd_result = CommandResult(
                        success=True,
                        result=result,
                        error=None,
                        execution_time_ms=execution_time_ms,
                        command_id=command_id
                    )
                except Exception as e:
                    execution_time_ms = (time.time() - start_time) * 1000
                    cmd_result = CommandResult(
                        success=False,
                        result=None,
                        error=e,
                        execution_time_ms=execution_time_ms,
                        command_id=command_id
                    )

                # Put result in queue for callback
                if command_id in self._pending_callbacks:
                    callback = self._pending_callbacks.pop(command_id)
                    self.result_queue.put((callback, cmd_result))

            except queue.Empty:
                continue
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Command queue worker error: {e}")

    def process_results(self, max_results: int = 10) -> int:
        """
        Process pending results (call callbacks).
        处理待处理的结果（调用回调）。

        Call this from main/GUI thread periodically.
        从主/GUI线程定期调用此方法。

        Args:
            max_results: Maximum number of results to process per call

        Returns:
            Number of results processed
        """
        processed = 0
        while processed < max_results:
            try:
                callback, result = self.result_queue.get_nowait()
                callback(result)
                processed += 1
            except queue.Empty:
                break
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Command result callback error: {e}")

        return processed

    def get_queue_size(self) -> int:
        """Get number of pending commands / 获取待处理命令数"""
        return self.command_queue.qsize()

    def clear_queue(self):
        """Clear all pending commands / 清空所有待处理命令"""
        while not self.command_queue.empty():
            try:
                self.command_queue.get_nowait()
            except queue.Empty:
                break


class CircuitBreakerOpen(Exception):
    """Exception raised when circuit breaker is open / 熔断器开启时抛出的异常"""
    pass


class CircuitBreaker:
    """
    Circuit Breaker pattern implementation.
    熔断器模式实现。

    Prevents cascade failures by failing fast when a hardware is unreliable.
    当硬件不可靠时通过快速失败来防止级联故障。
    """

    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing fast
    HALF_OPEN = "half_open"  # Testing recovery

    def __init__(self, name: str,
                 failure_threshold: int = 3,
                 recovery_timeout: float = 30.0,
                 half_open_max_calls: int = 1):
        """
        Initialize circuit breaker.

        Args:
            name: Breaker name for identification
            failure_threshold: Number of failures before opening
            recovery_timeout: Time before trying recovery (seconds)
            half_open_max_calls: Max calls allowed in half-open state
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self.failure_count = 0
        self.success_count = 0
        self.state = self.CLOSED
        self.last_failure_time: Optional[float] = None
        self.half_open_calls = 0
        self._lock = threading.Lock()

    def execute(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.
        使用熔断器保护执行函数。

        Args:
            func: Function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Function result

        Raises:
            CircuitBreakerOpen: If circuit breaker is open
        """
        with self._lock:
            if not self._can_execute():
                raise CircuitBreakerOpen(
                    f"Circuit breaker '{self.name}' is open"
                )

            if self.state == self.HALF_OPEN:
                self.half_open_calls += 1

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _can_execute(self) -> bool:
        """Check if execution is allowed / 检查是否允许执行"""
        if self.state == self.CLOSED:
            return True

        if self.state == self.OPEN:
            # Check if recovery timeout has passed
            if self.last_failure_time is None:
                return False

            if time.time() - self.last_failure_time > self.recovery_timeout:
                # Transition to half-open
                self.state = self.HALF_OPEN
                self.half_open_calls = 0
                return True

            return False

        if self.state == self.HALF_OPEN:
            # Allow limited calls in half-open state
            return self.half_open_calls < self.half_open_max_calls

        return False

    def _on_success(self):
        """Handle successful execution / 处理成功执行"""
        with self._lock:
            self.failure_count = 0
            self.success_count += 1

            if self.state == self.HALF_OPEN:
                # Recovery successful, close the circuit
                self.state = self.CLOSED
                self.half_open_calls = 0

    def _on_failure(self):
        """Handle failed execution / 处理失败执行"""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == self.HALF_OPEN:
                # Recovery failed, open the circuit again
                self.state = self.OPEN
                self.half_open_calls = 0
            elif self.failure_count >= self.failure_threshold:
                # Threshold reached, open the circuit
                self.state = self.OPEN

    def reset(self):
        """Reset circuit breaker to closed state / 重置熔断器到关闭状态"""
        with self._lock:
            self.failure_count = 0
            self.success_count = 0
            self.state = self.CLOSED
            self.last_failure_time = None
            self.half_open_calls = 0

    def get_state(self) -> Dict[str, Any]:
        """Get circuit breaker state / 获取熔断器状态"""
        with self._lock:
            return {
                "name": self.name,
                "state": self.state,
                "failure_count": self.failure_count,
                "success_count": self.success_count,
                "last_failure_time": self.last_failure_time
            }


class MessageDeduplicator:
    """
    Message deduplication for preventing repeated command execution.
    消息去重，防止重复命令执行。
    """

    def __init__(self, max_history: int = 1000, ttl_seconds: float = 60.0):
        """
        Initialize deduplicator.

        Args:
            max_history: Maximum number of message IDs to track
            ttl_seconds: Time-to-live for message IDs
        """
        self.max_history = max_history
        self.ttl_seconds = ttl_seconds
        self._processed: Dict[str, float] = {}  # message_id -> timestamp
        self._lock = threading.Lock()
        self._sequence_counter = 0

    def get_next_sequence(self) -> str:
        """Generate unique message ID / 生成唯一消息ID"""
        with self._lock:
            self._sequence_counter += 1
            return f"{time.time()}-{self._sequence_counter}"

    def is_duplicate(self, message_id: str) -> bool:
        """
        Check if message is duplicate.
        检查消息是否重复。

        Args:
            message_id: Message ID to check

        Returns:
            True if duplicate, False otherwise
        """
        current_time = time.time()

        with self._lock:
            # Clean expired entries
            self._cleanup(current_time)

            if message_id in self._processed:
                return True

            self._processed[message_id] = current_time

            # Cleanup if over limit
            if len(self._processed) > self.max_history:
                self._cleanup_oldest()

            return False

    def _cleanup(self, current_time: float):
        """Remove expired entries / 移除过期条目"""
        expired = [
            mid for mid, ts in self._processed.items()
            if current_time - ts > self.ttl_seconds
        ]
        for mid in expired:
            del self._processed[mid]

    def _cleanup_oldest(self):
        """Remove oldest entries when over limit / 超过限制时移除最旧的条目"""
        if len(self._processed) <= self.max_history // 2:
            return

        # Sort by timestamp and keep newest half
        sorted_items = sorted(
            self._processed.items(),
            key=lambda x: x[1],
            reverse=True
        )
        self._processed = dict(sorted_items[:self.max_history // 2])

    def clear(self):
        """Clear all processed message IDs / 清除所有已处理的消息ID"""
        with self._lock:
            self._processed.clear()
