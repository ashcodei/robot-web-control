"""
Status Broadcaster Module
状态广播器模块

Broadcasts hardware status updates to connected clients.
向连接的客户端广播硬件状态更新。
"""

import json
import threading
import time
from typing import Dict, Any, List, Optional, Callable
from http.server import HTTPServer, BaseHTTPRequestHandler
import socketserver

from app_core.state_manager import get_state_manager
from app_core.emergency_controller import get_emergency_controller
from app_core.event_bus import get_event_bus, EventType, Event
from app_core.logger import get_logger

logger = get_logger(__name__)


class SSEHandler(BaseHTTPRequestHandler):
    """
    Server-Sent Events handler for real-time status updates.
    用于实时状态更新的服务器发送事件处理器。
    """

    def __init__(self, *args, broadcaster=None, **kwargs):
        self.broadcaster = broadcaster
        super().__init__(*args, **kwargs)

    def log_message(self, format, *args):
        """Use our logger / 使用我们的日志记录器"""
        logger.debug(f"SSE request: {format % args}")

    def do_GET(self):
        """Handle SSE connection / 处理SSE连接"""
        if self.path == '/events':
            self._handle_sse()
        else:
            self.send_error(404)

    def _handle_sse(self):
        """Handle SSE stream / 处理SSE流"""
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'keep-alive')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        client_id = f"{self.client_address[0]}:{self.client_address[1]}"
        logger.info(f"SSE client connected: {client_id}")

        if self.broadcaster:
            self.broadcaster.add_client(client_id, self)

        try:
            # Keep connection alive
            while self.broadcaster and self.broadcaster.is_running:
                # Send heartbeat every 15 seconds
                self._send_event("heartbeat", {"timestamp": time.time()})
                time.sleep(15)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            if self.broadcaster:
                self.broadcaster.remove_client(client_id)
            logger.info(f"SSE client disconnected: {client_id}")

    def _send_event(self, event_type: str, data: Dict[str, Any]):
        """Send SSE event / 发送SSE事件"""
        try:
            message = f"event: {event_type}\n"
            message += f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
            self.wfile.write(message.encode('utf-8'))
            self.wfile.flush()
        except Exception as e:
            logger.debug(f"Failed to send SSE event: {e}")

    def send_status_update(self, data: Dict[str, Any]):
        """Send status update event / 发送状态更新事件"""
        self._send_event("status_update", data)

    def send_log_message(self, data: Dict[str, Any]):
        """Send log message event / 发送日志消息事件"""
        self._send_event("log", data)

    def send_emergency_alert(self, data: Dict[str, Any]):
        """Send emergency alert event / 发送紧急警报事件"""
        self._send_event("emergency", data)


class ThreadedSSEServer(socketserver.ThreadingMixIn, HTTPServer):
    """Threaded SSE server / 多线程SSE服务器"""
    allow_reuse_address = True


class StatusBroadcaster:
    """
    Status Broadcaster using Server-Sent Events.
    使用服务器发送事件的状态广播器。

    Provides real-time status updates to remote clients.
    向远程客户端提供实时状态更新。
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 8089,
                 update_interval: float = 0.1):
        """
        Initialize broadcaster.

        Args:
            host: Bind host address
            port: Bind port
            update_interval: Status update interval in seconds
        """
        self.host = host
        self.port = port
        self.update_interval = update_interval

        self.server: Optional[ThreadedSSEServer] = None
        self.server_thread: Optional[threading.Thread] = None
        self.broadcast_thread: Optional[threading.Thread] = None
        self.is_running = False

        self.clients: Dict[str, SSEHandler] = {}
        self._clients_lock = threading.Lock()

        # Get singletons
        self.state_manager = get_state_manager()
        self.emergency_controller = get_emergency_controller()
        self.event_bus = get_event_bus()

        # Subscribe to events
        self._setup_event_subscriptions()

    def _setup_event_subscriptions(self):
        """Setup event bus subscriptions / 设置事件总线订阅"""
        self.event_bus.subscribe(EventType.HARDWARE_STATE_CHANGED, self._on_hardware_event)
        self.event_bus.subscribe(EventType.EMERGENCY_STOP, self._on_emergency_event)
        self.event_bus.subscribe(EventType.EMERGENCY_STOP_RELEASED, self._on_emergency_event)
        self.event_bus.subscribe(EventType.LOG_MESSAGE, self._on_log_event)

    def _on_hardware_event(self, event: Event):
        """Handle hardware state change event / 处理硬件状态变化事件"""
        self._broadcast_to_all("status_update", {
            "type": "hardware_state",
            "data": event.data,
            "timestamp": event.timestamp
        })

    def _on_emergency_event(self, event: Event):
        """Handle emergency event / 处理紧急事件"""
        self._broadcast_to_all("emergency", {
            "type": event.event_type.value,
            "data": event.data,
            "timestamp": event.timestamp
        })

    def _on_log_event(self, event: Event):
        """Handle log event / 处理日志事件"""
        self._broadcast_to_all("log", {
            "data": event.data,
            "timestamp": event.timestamp
        })

    def add_client(self, client_id: str, handler: SSEHandler):
        """Add SSE client / 添加SSE客户端"""
        with self._clients_lock:
            self.clients[client_id] = handler
        logger.debug(f"Added SSE client: {client_id}, total: {len(self.clients)}")

    def remove_client(self, client_id: str):
        """Remove SSE client / 移除SSE客户端"""
        with self._clients_lock:
            if client_id in self.clients:
                del self.clients[client_id]
        logger.debug(f"Removed SSE client: {client_id}, total: {len(self.clients)}")

    def _broadcast_to_all(self, event_type: str, data: Dict[str, Any]):
        """Broadcast event to all clients / 向所有客户端广播事件"""
        with self._clients_lock:
            clients_snapshot = list(self.clients.values())

        for handler in clients_snapshot:
            try:
                if event_type == "status_update":
                    handler.send_status_update(data)
                elif event_type == "log":
                    handler.send_log_message(data)
                elif event_type == "emergency":
                    handler.send_emergency_alert(data)
            except Exception:
                pass  # Client may have disconnected

    def _broadcast_loop(self):
        """Periodic status broadcast loop / 定期状态广播循环"""
        while self.is_running:
            try:
                # Get current status
                status = self.state_manager.get_all_status()
                status["emergency_active"] = self.emergency_controller.is_emergency_active
                status["timestamp"] = time.time()

                # Broadcast to all clients
                self._broadcast_to_all("status_update", {"type": "periodic", "data": status})

            except Exception as e:
                logger.error(f"Broadcast error: {e}")

            time.sleep(self.update_interval)

    def start(self):
        """Start the broadcaster / 启动广播器"""
        if self.is_running:
            logger.warning("Broadcaster already running")
            return

        broadcaster = self

        def handler_factory(*args, **kwargs):
            return SSEHandler(*args, broadcaster=broadcaster, **kwargs)

        try:
            self.server = ThreadedSSEServer((self.host, self.port), handler_factory)
            self.server_thread = threading.Thread(
                target=self.server.serve_forever,
                name="StatusBroadcastServer",
                daemon=True
            )
            self.server_thread.start()

            self.is_running = True

            # Start broadcast loop
            self.broadcast_thread = threading.Thread(
                target=self._broadcast_loop,
                name="StatusBroadcastLoop",
                daemon=True
            )
            self.broadcast_thread.start()

            logger.info(f"Status broadcaster started on {self.host}:{self.port}")

        except Exception as e:
            logger.error(f"Failed to start broadcaster: {e}")
            raise

    def stop(self):
        """Stop the broadcaster / 停止广播器"""
        if not self.is_running:
            return

        self.is_running = False

        if self.server:
            self.server.shutdown()
            self.server = None

        if self.server_thread:
            self.server_thread.join(timeout=2.0)
            self.server_thread = None

        if self.broadcast_thread:
            self.broadcast_thread.join(timeout=2.0)
            self.broadcast_thread = None

        logger.info("Status broadcaster stopped")

    def get_status(self) -> Dict[str, Any]:
        """Get broadcaster status / 获取广播器状态"""
        with self._clients_lock:
            client_count = len(self.clients)

        return {
            "is_running": self.is_running,
            "host": self.host,
            "port": self.port,
            "connected_clients": client_count,
            "update_interval": self.update_interval
        }


# Global broadcaster instance / 全局广播器实例
_broadcaster: Optional[StatusBroadcaster] = None


def get_status_broadcaster() -> StatusBroadcaster:
    """Get the global status broadcaster / 获取全局状态广播器"""
    global _broadcaster
    if _broadcaster is None:
        from config.settings import get_settings
        settings = get_settings()
        _broadcaster = StatusBroadcaster(
            host=settings.remote_control.host,
            port=settings.remote_control.port + 1,  # Use next port
            update_interval=settings.remote_control.status_broadcast_interval
        )
    return _broadcaster
