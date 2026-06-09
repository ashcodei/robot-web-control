"""
Remote Control Server Module
远程控制服务器模块

HTTP + WebSocket server for remote control.
用于远程控制的HTTP + WebSocket服务器。

Features:
- RESTful API for hardware control
- Authentication framework (LAN mode / API Key)
- Rate limiting
- Input validation
- Health check endpoint
"""

import json
import threading
import time
import re
from typing import Dict, Any, Optional, List, Set
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import socketserver

from app_core.remote_control.function_registry import get_function_registry, HardwareFunctionRegistry
from app_core.remote_control.auth import (
    get_auth_manager, AuthManager, AuthMode, AuthResult, RequestContext
)
from app_core.threading_model import MessageDeduplicator  # Use unified implementation
from app_core.emergency_controller import get_emergency_controller, EmergencyController
from app_core.state_manager import get_state_manager, StateManager
from app_core.event_bus import get_event_bus, EventType
from app_core.logger import get_logger

logger = get_logger(__name__)


# Input validation patterns
VALID_FUNCTION_ID_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)*$')
VALID_MESSAGE_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_\-\.]+$')


def validate_function_id(function_id: str) -> bool:
    """
    Validate function ID format.
    验证函数ID格式。

    Args:
        function_id: Function ID to validate

    Returns:
        True if valid, False otherwise
    """
    if not function_id or len(function_id) > 100:
        return False
    return bool(VALID_FUNCTION_ID_PATTERN.match(function_id))


def validate_message_id(message_id: str) -> bool:
    """
    Validate message ID format.
    验证消息ID格式。

    Args:
        message_id: Message ID to validate

    Returns:
        True if valid, False otherwise
    """
    if not message_id or len(message_id) > 100:
        return False
    return bool(VALID_MESSAGE_ID_PATTERN.match(message_id))


class RemoteControlHandler(BaseHTTPRequestHandler):
    """HTTP request handler for remote control / 远程控制的HTTP请求处理器"""

    def __init__(self, *args, server_instance=None, **kwargs):
        self.server_instance = server_instance
        super().__init__(*args, **kwargs)

    def log_message(self, format, *args):
        """Override to use our logger / 覆盖以使用我们的日志记录器"""
        logger.debug(f"Remote request: {format % args}")

    def _get_client_ip(self) -> str:
        """Get client IP address / 获取客户端IP地址"""
        # Check for proxy headers
        forwarded_for = self.headers.get('X-Forwarded-For')
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()
        return self.client_address[0]

    def _create_request_context(self) -> RequestContext:
        """Create request context for authentication / 创建认证请求上下文"""
        return RequestContext(
            client_ip=self._get_client_ip(),
            headers=dict(self.headers),
            path=urlparse(self.path).path,
            method=self.command
        )

    def _authenticate(self) -> AuthResult:
        """Authenticate the request / 认证请求"""
        auth_manager = get_auth_manager()
        context = self._create_request_context()
        return auth_manager.authenticate(context)

    def _set_headers(self, status: int = 200, content_type: str = "application/json"):
        """Set response headers / 设置响应头"""
        self.send_response(status)
        self.send_header('Content-Type', content_type)

        # CORS headers - configurable based on auth mode
        auth_manager = get_auth_manager()
        if auth_manager.get_mode() == AuthMode.NONE:
            # LAN mode - allow all origins
            self.send_header('Access-Control-Allow-Origin', '*')
        else:
            # Restricted mode - could be configured per deployment
            origin = self.headers.get('Origin', '*')
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Access-Control-Allow-Credentials', 'true')

        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-API-Key')

        # Rate limit info
        if self.server_instance:
            rate_limiter = auth_manager._rate_limiter
            remaining = rate_limiter.get_remaining(self._get_client_ip())
            self.send_header('X-RateLimit-Remaining', str(remaining))
            self.send_header('X-RateLimit-Limit', str(rate_limiter.max_requests))

        self.end_headers()

    def _send_json(self, data: Dict[str, Any], status: int = 200):
        """Send JSON response / 发送JSON响应"""
        self._set_headers(status)
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def _read_json(self) -> Dict[str, Any]:
        """Read JSON from request body / 从请求体读取JSON"""
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length == 0:
            return {}
        if content_length > 1024 * 1024:  # 1MB limit
            raise ValueError("Request body too large")
        body = self.rfile.read(content_length)
        return json.loads(body.decode('utf-8'))

    def do_OPTIONS(self):
        """Handle CORS preflight / 处理CORS预检"""
        self._set_headers()

    def do_GET(self):
        """Handle GET requests / 处理GET请求"""
        # Authenticate
        auth_result = self._authenticate()
        if not auth_result.success:
            self._send_json({
                "error": auth_result.error_message,
                "code": "AUTH_FAILED"
            }, 401)
            return

        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/api/ping':
            self._handle_ping()
        elif path == '/api/health':
            self._handle_health()
        elif path == '/api/functions':
            self._handle_get_functions()
        elif path == '/api/status':
            self._handle_get_status()
        elif path == '/api/history':
            self._handle_get_history()
        elif path == '/api/auth/status':
            self._handle_auth_status()
        else:
            self._send_json({"error": "Not found"}, 404)

    def do_POST(self):
        """Handle POST requests / 处理POST请求"""
        # Authenticate
        auth_result = self._authenticate()
        if not auth_result.success:
            self._send_json({
                "error": auth_result.error_message,
                "code": "AUTH_FAILED"
            }, 401)
            return

        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/api/execute':
            self._handle_execute(auth_result)
        elif path == '/api/emergency_stop':
            self._handle_emergency_stop(auth_result)
        elif path == '/api/release_emergency':
            self._handle_release_emergency(auth_result)
        else:
            self._send_json({"error": "Not found"}, 404)

    def _handle_ping(self):
        """Handle ping request / 处理ping请求"""
        self._send_json({
            "status": "ok",
            "timestamp": time.time(),
            "server_name": "CookingRobotRemoteControl"
        })

    def _handle_health(self):
        """
        Handle health check request.
        处理健康检查请求。

        Returns comprehensive system health status.
        返回全面的系统健康状态。
        """
        state_manager = get_state_manager()
        emergency_controller = get_emergency_controller()

        # Get all hardware status
        all_status = state_manager.get_all_status()
        hardware_status = all_status.get('hardware', {})

        # Calculate health metrics
        total_hardware = len(hardware_status)
        connected_count = sum(
            1 for hw in hardware_status.values()
            if hw.get('state') in ['connected', 'running']
        )
        error_count = sum(
            1 for hw in hardware_status.values()
            if hw.get('state') == 'error'
        )

        # Determine overall health
        if emergency_controller.is_emergency_active:
            health_status = "emergency_stop"
        elif error_count > 0:
            health_status = "degraded"
        elif connected_count == total_hardware:
            health_status = "healthy"
        else:
            health_status = "partial"

        self._send_json({
            "status": health_status,
            "timestamp": time.time(),
            "system_state": all_status.get('system_state'),
            "emergency_active": emergency_controller.is_emergency_active,
            "hardware": {
                "total": total_hardware,
                "connected": connected_count,
                "errors": error_count
            },
            "components": {
                name: {
                    "state": hw.get('state'),
                    "healthy": hw.get('state') in ['connected', 'running']
                }
                for name, hw in hardware_status.items()
            }
        })

    def _handle_auth_status(self):
        """Handle auth status request / 处理认证状态请求"""
        auth_manager = get_auth_manager()
        self._send_json(auth_manager.get_status())

    def _handle_get_functions(self):
        """Handle get functions request / 处理获取函数请求"""
        registry = get_function_registry()
        functions = registry.get_available_functions()
        categories = registry.get_categories()

        self._send_json({
            "functions": functions,
            "categories": categories,
            "count": len(functions)
        })

    def _handle_get_status(self):
        """Handle get status request / 处理获取状态请求"""
        state_manager = get_state_manager()
        emergency_controller = get_emergency_controller()

        self._send_json({
            "system": state_manager.get_all_status(),
            "emergency_active": emergency_controller.is_emergency_active,
            "timestamp": time.time()
        })

    def _handle_get_history(self):
        """Handle get execution history / 处理获取执行历史"""
        registry = get_function_registry()
        history = registry.get_execution_history(limit=50)

        self._send_json({
            "history": history,
            "count": len(history)
        })

    def _handle_execute(self, auth_result: AuthResult):
        """Handle function execution request / 处理函数执行请求"""
        try:
            data = self._read_json()
            function_id = data.get('function_id')
            args = data.get('args', [])
            kwargs = data.get('kwargs', {})
            message_id = data.get('message_id')

            # Validate function_id
            if not function_id:
                self._send_json({
                    "error": "function_id required",
                    "code": "MISSING_PARAM"
                }, 400)
                return

            if not validate_function_id(function_id):
                self._send_json({
                    "error": "Invalid function_id format",
                    "code": "INVALID_FORMAT"
                }, 400)
                return

            # Validate message_id if provided
            if message_id and not validate_message_id(message_id):
                self._send_json({
                    "error": "Invalid message_id format",
                    "code": "INVALID_FORMAT"
                }, 400)
                return

            # Validate args and kwargs
            if not isinstance(args, list):
                self._send_json({
                    "error": "args must be a list",
                    "code": "INVALID_FORMAT"
                }, 400)
                return

            if not isinstance(kwargs, dict):
                self._send_json({
                    "error": "kwargs must be an object",
                    "code": "INVALID_FORMAT"
                }, 400)
                return

            # Check for duplicate message
            if message_id and self.server_instance:
                if self.server_instance.deduplicator.is_duplicate(message_id):
                    self._send_json({
                        "status": "duplicate",
                        "message_id": message_id
                    })
                    return

            # Check emergency stop
            emergency_controller = get_emergency_controller()
            if emergency_controller.is_emergency_active:
                # Only allow emergency-related functions
                registry = get_function_registry()
                func_info = registry.get_function_info(function_id)
                if not func_info or not func_info.get('is_emergency'):
                    self._send_json({
                        "error": "Emergency stop active - operation blocked",
                        "code": "EMERGENCY_ACTIVE",
                        "emergency_active": True
                    }, 403)
                    return

            # Execute function
            registry = get_function_registry()
            result = registry.execute_function(function_id, args, kwargs)

            logger.info(f"Executed {function_id} by {auth_result.user_id}: {'success' if result.success else 'failed'}")

            self._send_json({
                "status": "success" if result.success else "error",
                "result": str(result.result) if result.result is not None else None,
                "error": result.error,
                "execution_time_ms": result.execution_time_ms,
                "function_id": function_id,
                "message_id": message_id
            })

        except json.JSONDecodeError:
            self._send_json({
                "error": "Invalid JSON",
                "code": "PARSE_ERROR"
            }, 400)
        except ValueError as e:
            self._send_json({
                "error": str(e),
                "code": "VALIDATION_ERROR"
            }, 400)
        except Exception as e:
            logger.error(f"Execution error: {e}")
            self._send_json({
                "error": str(e),
                "code": "INTERNAL_ERROR"
            }, 500)

    def _handle_emergency_stop(self, auth_result: AuthResult):
        """Handle emergency stop request / 处理紧急停止请求"""
        emergency_controller = get_emergency_controller()
        results = emergency_controller.emergency_stop_all()

        # Convert results to serializable format
        results_dict = {}
        for name, result in results.items():
            results_dict[name] = {
                "success": result.success,
                "error": result.error_message,
                "duration_ms": result.duration_ms
            }

        self._send_json({
            "status": "emergency_stop_executed",
            "results": results_dict,
            "timestamp": time.time()
        })

        logger.warning(f"Remote emergency stop executed by {auth_result.user_id}")

    def _handle_release_emergency(self, auth_result: AuthResult):
        """Handle release emergency stop / 处理释放紧急停止"""
        emergency_controller = get_emergency_controller()
        success = emergency_controller.release_emergency_stop()

        self._send_json({
            "status": "released" if success else "failed",
            "emergency_active": emergency_controller.is_emergency_active,
            "timestamp": time.time()
        })

        logger.info(f"Emergency stop released by {auth_result.user_id}")


class ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    """Threaded HTTP server / 多线程HTTP服务器"""
    allow_reuse_address = True


class RemoteControlServer:
    """
    Remote Control Server.
    远程控制服务器。

    Provides HTTP API for remote control of hardware.
    提供用于远程控制硬件的HTTP API。
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 8088):
        """
        Initialize server.

        Args:
            host: Bind host address
            port: Bind port
        """
        self.host = host
        self.port = port
        self.server: Optional[ThreadedHTTPServer] = None
        self.server_thread: Optional[threading.Thread] = None
        self.is_running = False

        # Use unified MessageDeduplicator from threading_model
        self.deduplicator = MessageDeduplicator(max_history=1000, ttl_seconds=60.0)

        self.connected_clients: Set[str] = set()
        self._status_broadcast_thread: Optional[threading.Thread] = None

        # Get singletons
        self.function_registry = get_function_registry()
        self.emergency_controller = get_emergency_controller()
        self.state_manager = get_state_manager()
        self.event_bus = get_event_bus()
        self.auth_manager = get_auth_manager()

    def start(self):
        """Start the server / 启动服务器"""
        if self.is_running:
            logger.warning("Server already running")
            return

        # Create handler factory with server reference
        server_instance = self

        def handler_factory(*args, **kwargs):
            return RemoteControlHandler(*args, server_instance=server_instance, **kwargs)

        try:
            self.server = ThreadedHTTPServer((self.host, self.port), handler_factory)
            self.server_thread = threading.Thread(
                target=self.server.serve_forever,
                name="RemoteControlServer",
                daemon=True
            )
            self.server_thread.start()
            self.is_running = True

            logger.info(f"Remote control server started on {self.host}:{self.port}")
            logger.info(f"Auth mode: {self.auth_manager.get_mode().value}")

            # Publish event
            self.event_bus.publish(
                EventType.REMOTE_CONNECTED,
                "remote_server",
                {"host": self.host, "port": self.port}
            )

        except Exception as e:
            logger.error(f"Failed to start server: {e}")
            raise

    def stop(self):
        """Stop the server / 停止服务器"""
        if not self.is_running:
            return

        self.is_running = False

        if self.server:
            self.server.shutdown()
            self.server = None

        if self.server_thread:
            self.server_thread.join(timeout=2.0)
            self.server_thread = None

        logger.info("Remote control server stopped")

        # Publish event
        self.event_bus.publish(
            EventType.REMOTE_DISCONNECTED,
            "remote_server",
            {}
        )

    def set_auth_mode(self, mode: AuthMode):
        """Set authentication mode / 设置认证模式"""
        self.auth_manager.set_mode(mode)

    def generate_api_key(self, user_id: str, roles: List[str] = None) -> str:
        """Generate API key / 生成API密钥"""
        return self.auth_manager.generate_api_key(user_id, roles)

    def get_status(self) -> Dict[str, Any]:
        """Get server status / 获取服务器状态"""
        return {
            "is_running": self.is_running,
            "host": self.host,
            "port": self.port,
            "connected_clients": len(self.connected_clients),
            "registered_functions": len(self.function_registry.functions),
            "auth": self.auth_manager.get_status()
        }


# Global server instance / 全局服务器实例
_server: Optional[RemoteControlServer] = None


def get_remote_server() -> RemoteControlServer:
    """Get the global remote control server / 获取全局远程控制服务器"""
    global _server
    if _server is None:
        from config.settings import get_settings
        settings = get_settings()
        _server = RemoteControlServer(
            host=settings.remote_control.host,
            port=settings.remote_control.port
        )
    return _server
