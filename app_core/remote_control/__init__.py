"""
Remote Control Package
远程控制包

Provides remote control functionality for the cooking robot system.
为烹饪机器人系统提供远程控制功能。
"""

from app_core.remote_control.decorators import remote_callable, is_remote_callable, get_remote_info
from app_core.remote_control.function_registry import (
    HardwareFunctionRegistry,
    get_function_registry,
    RegisteredFunction,
    ExecutionResult
)
from app_core.remote_control.server import RemoteControlServer, get_remote_server
from app_core.remote_control.status_broadcaster import StatusBroadcaster, get_status_broadcaster
from app_core.remote_control.auth import (
    AuthManager,
    AuthMode,
    AuthResult,
    get_auth_manager,
    RateLimiter,
    IPWhitelist
)

__all__ = [
    # Decorators
    'remote_callable',
    'is_remote_callable',
    'get_remote_info',

    # Function Registry
    'HardwareFunctionRegistry',
    'get_function_registry',
    'RegisteredFunction',
    'ExecutionResult',

    # Server
    'RemoteControlServer',
    'get_remote_server',

    # Status Broadcaster
    'StatusBroadcaster',
    'get_status_broadcaster',

    # Authentication
    'AuthManager',
    'AuthMode',
    'AuthResult',
    'get_auth_manager',
    'RateLimiter',
    'IPWhitelist',
]
