"""
Authentication Module
认证模块

Provides extensible authentication framework for remote control.
为远程控制提供可扩展的认证框架。

Supports:
- No auth (LAN mode)
- API Key auth
- JWT auth (for future WAN access)
- Rate limiting
- IP whitelist
"""

import time
import hashlib
import secrets
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Set
from dataclasses import dataclass, field
from enum import Enum
import threading

from app_core.logger import get_logger

logger = get_logger(__name__)


class AuthMode(Enum):
    """Authentication mode enumeration / 认证模式枚举"""
    NONE = "none"           # No authentication (LAN mode)
    API_KEY = "api_key"     # API Key authentication
    JWT = "jwt"             # JWT authentication (future)
    BASIC = "basic"         # Basic authentication


@dataclass
class AuthResult:
    """Authentication result / 认证结果"""
    success: bool
    user_id: Optional[str] = None
    roles: List[str] = field(default_factory=list)
    error_message: Optional[str] = None

    @staticmethod
    def success_result(user_id: str = "anonymous", roles: List[str] = None) -> 'AuthResult':
        return AuthResult(
            success=True,
            user_id=user_id,
            roles=roles or ["user"]
        )

    @staticmethod
    def failure_result(message: str) -> 'AuthResult':
        return AuthResult(
            success=False,
            error_message=message
        )


@dataclass
class RequestContext:
    """Request context for authentication / 请求上下文"""
    client_ip: str
    headers: Dict[str, str]
    path: str
    method: str
    timestamp: float = field(default_factory=time.time)


class RateLimiter:
    """
    Rate limiter for API requests.
    API请求速率限制器。

    Uses sliding window algorithm.
    使用滑动窗口算法。
    """

    def __init__(self, max_requests: int = 100, window_seconds: float = 60.0):
        """
        Initialize rate limiter.

        Args:
            max_requests: Maximum requests per window
            window_seconds: Time window in seconds
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def is_allowed(self, client_id: str) -> bool:
        """
        Check if request is allowed.
        检查请求是否被允许。

        Args:
            client_id: Client identifier (usually IP)

        Returns:
            True if allowed, False if rate limited
        """
        current_time = time.time()
        cutoff_time = current_time - self.window_seconds

        with self._lock:
            # Get or create request list
            if client_id not in self._requests:
                self._requests[client_id] = []

            # Remove old requests
            self._requests[client_id] = [
                t for t in self._requests[client_id]
                if t > cutoff_time
            ]

            # Check limit
            if len(self._requests[client_id]) >= self.max_requests:
                return False

            # Add current request
            self._requests[client_id].append(current_time)
            return True

    def get_remaining(self, client_id: str) -> int:
        """Get remaining requests for client / 获取客户端剩余请求数"""
        current_time = time.time()
        cutoff_time = current_time - self.window_seconds

        with self._lock:
            if client_id not in self._requests:
                return self.max_requests

            valid_requests = [
                t for t in self._requests[client_id]
                if t > cutoff_time
            ]
            return max(0, self.max_requests - len(valid_requests))

    def reset(self, client_id: str = None):
        """Reset rate limiter / 重置速率限制器"""
        with self._lock:
            if client_id:
                self._requests.pop(client_id, None)
            else:
                self._requests.clear()


class IPWhitelist:
    """
    IP whitelist manager.
    IP白名单管理器。
    """

    def __init__(self, enabled: bool = False, allowed_ips: List[str] = None):
        """
        Initialize IP whitelist.

        Args:
            enabled: Whether whitelist is enabled
            allowed_ips: List of allowed IP addresses/patterns
        """
        self.enabled = enabled
        self._allowed: Set[str] = set(allowed_ips or [])
        self._lock = threading.Lock()

        # Always allow localhost
        self._allowed.update(['127.0.0.1', '::1', 'localhost'])

    def is_allowed(self, ip: str) -> bool:
        """
        Check if IP is allowed.
        检查IP是否被允许。

        Args:
            ip: IP address to check

        Returns:
            True if allowed, False otherwise
        """
        if not self.enabled:
            return True

        with self._lock:
            # Exact match
            if ip in self._allowed:
                return True

            # Check for subnet patterns (simple implementation)
            # Example: 192.168.* matches 192.168.1.100
            for pattern in self._allowed:
                if pattern.endswith('*'):
                    prefix = pattern[:-1]
                    if ip.startswith(prefix):
                        return True

            return False

    def add_ip(self, ip: str):
        """Add IP to whitelist / 添加IP到白名单"""
        with self._lock:
            self._allowed.add(ip)

    def remove_ip(self, ip: str):
        """Remove IP from whitelist / 从白名单移除IP"""
        with self._lock:
            self._allowed.discard(ip)

    def get_allowed_ips(self) -> List[str]:
        """Get list of allowed IPs / 获取允许的IP列表"""
        with self._lock:
            return list(self._allowed)


class BaseAuthenticator(ABC):
    """
    Base class for authenticators.
    认证器基类。
    """

    @abstractmethod
    def authenticate(self, context: RequestContext) -> AuthResult:
        """
        Authenticate a request.
        认证请求。

        Args:
            context: Request context

        Returns:
            Authentication result
        """
        pass

    @abstractmethod
    def get_mode(self) -> AuthMode:
        """Get authentication mode / 获取认证模式"""
        pass


class NoAuthenticator(BaseAuthenticator):
    """
    No authentication (LAN mode).
    无认证（内网模式）。
    """

    def authenticate(self, context: RequestContext) -> AuthResult:
        """Always succeeds / 始终成功"""
        return AuthResult.success_result(
            user_id=f"lan_user_{context.client_ip}",
            roles=["admin"]  # Full access in LAN mode
        )

    def get_mode(self) -> AuthMode:
        return AuthMode.NONE


class APIKeyAuthenticator(BaseAuthenticator):
    """
    API Key authentication.
    API密钥认证。
    """

    def __init__(self):
        self._api_keys: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def authenticate(self, context: RequestContext) -> AuthResult:
        """
        Authenticate using API key from header or query.
        使用请求头或查询参数中的API密钥进行认证。
        """
        # Get API key from header (preferred)
        api_key = context.headers.get('X-API-Key') or context.headers.get('x-api-key')

        if not api_key:
            return AuthResult.failure_result("Missing API key")

        with self._lock:
            if api_key not in self._api_keys:
                return AuthResult.failure_result("Invalid API key")

            key_info = self._api_keys[api_key]

            # Check if key is active
            if not key_info.get('active', True):
                return AuthResult.failure_result("API key is disabled")

            # Check expiration
            expires = key_info.get('expires')
            if expires and time.time() > expires:
                return AuthResult.failure_result("API key has expired")

            return AuthResult.success_result(
                user_id=key_info.get('user_id', 'api_user'),
                roles=key_info.get('roles', ['user'])
            )

    def get_mode(self) -> AuthMode:
        return AuthMode.API_KEY

    def generate_key(self, user_id: str, roles: List[str] = None,
                     expires_in: float = None) -> str:
        """
        Generate a new API key.
        生成新的API密钥。

        Args:
            user_id: User identifier
            roles: User roles
            expires_in: Expiration time in seconds (None = never)

        Returns:
            Generated API key
        """
        api_key = secrets.token_urlsafe(32)

        key_info = {
            'user_id': user_id,
            'roles': roles or ['user'],
            'active': True,
            'created': time.time()
        }

        if expires_in:
            key_info['expires'] = time.time() + expires_in

        with self._lock:
            self._api_keys[api_key] = key_info

        logger.info(f"Generated API key for user: {user_id}")
        return api_key

    def revoke_key(self, api_key: str) -> bool:
        """Revoke an API key / 撤销API密钥"""
        with self._lock:
            if api_key in self._api_keys:
                del self._api_keys[api_key]
                return True
            return False

    def list_keys(self) -> List[Dict[str, Any]]:
        """List all API keys (without the actual key values) / 列出所有API密钥"""
        with self._lock:
            return [
                {
                    'user_id': info['user_id'],
                    'roles': info['roles'],
                    'active': info['active'],
                    'created': info['created'],
                    'expires': info.get('expires'),
                    'key_preview': key[:8] + '...'
                }
                for key, info in self._api_keys.items()
            ]


class AuthManager:
    """
    Authentication manager.
    认证管理器。

    Coordinates authentication, rate limiting, and IP filtering.
    协调认证、速率限制和IP过滤。
    """

    _instance: Optional['AuthManager'] = None
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

        # Default to no authentication (LAN mode)
        self._authenticator: BaseAuthenticator = NoAuthenticator()
        self._rate_limiter = RateLimiter(max_requests=100, window_seconds=60.0)
        self._ip_whitelist = IPWhitelist(enabled=False)

        # API key authenticator (for future use)
        self._api_key_auth = APIKeyAuthenticator()

        # Exempt paths (no auth required)
        self._exempt_paths: Set[str] = {
            '/api/ping',
            '/api/health',
        }

        # Rate limit exempt paths
        self._rate_limit_exempt: Set[str] = {
            '/api/emergency_stop',  # Emergency stop should never be rate limited
        }

        self._initialized = True

    def authenticate(self, context: RequestContext) -> AuthResult:
        """
        Authenticate a request.
        认证请求。

        Args:
            context: Request context

        Returns:
            Authentication result
        """
        # Check IP whitelist first
        if not self._ip_whitelist.is_allowed(context.client_ip):
            logger.warning(f"Blocked request from non-whitelisted IP: {context.client_ip}")
            return AuthResult.failure_result("IP not allowed")

        # Check rate limit (unless exempt)
        if context.path not in self._rate_limit_exempt:
            if not self._rate_limiter.is_allowed(context.client_ip):
                logger.warning(f"Rate limited: {context.client_ip}")
                return AuthResult.failure_result("Rate limit exceeded")

        # Check if path is exempt from auth
        if context.path in self._exempt_paths:
            return AuthResult.success_result(user_id="anonymous", roles=["guest"])

        # Perform authentication
        return self._authenticator.authenticate(context)

    def set_mode(self, mode: AuthMode):
        """
        Set authentication mode.
        设置认证模式。

        Args:
            mode: Authentication mode
        """
        if mode == AuthMode.NONE:
            self._authenticator = NoAuthenticator()
            logger.info("Authentication mode: NONE (LAN mode)")
        elif mode == AuthMode.API_KEY:
            self._authenticator = self._api_key_auth
            logger.info("Authentication mode: API_KEY")
        else:
            raise ValueError(f"Unsupported auth mode: {mode}")

    def get_mode(self) -> AuthMode:
        """Get current authentication mode / 获取当前认证模式"""
        return self._authenticator.get_mode()

    def enable_ip_whitelist(self, allowed_ips: List[str] = None):
        """Enable IP whitelist / 启用IP白名单"""
        self._ip_whitelist = IPWhitelist(enabled=True, allowed_ips=allowed_ips)
        logger.info(f"IP whitelist enabled with {len(allowed_ips or [])} IPs")

    def disable_ip_whitelist(self):
        """Disable IP whitelist / 禁用IP白名单"""
        self._ip_whitelist.enabled = False
        logger.info("IP whitelist disabled")

    def set_rate_limit(self, max_requests: int, window_seconds: float):
        """Set rate limit parameters / 设置速率限制参数"""
        self._rate_limiter = RateLimiter(max_requests, window_seconds)
        logger.info(f"Rate limit set: {max_requests} requests per {window_seconds}s")

    def generate_api_key(self, user_id: str, roles: List[str] = None,
                         expires_in: float = None) -> str:
        """Generate API key / 生成API密钥"""
        return self._api_key_auth.generate_key(user_id, roles, expires_in)

    def revoke_api_key(self, api_key: str) -> bool:
        """Revoke API key / 撤销API密钥"""
        return self._api_key_auth.revoke_key(api_key)

    def add_exempt_path(self, path: str):
        """Add path exempt from authentication / 添加免认证路径"""
        self._exempt_paths.add(path)

    def get_status(self) -> Dict[str, Any]:
        """Get authentication status / 获取认证状态"""
        return {
            'mode': self._authenticator.get_mode().value,
            'ip_whitelist_enabled': self._ip_whitelist.enabled,
            'rate_limit': {
                'max_requests': self._rate_limiter.max_requests,
                'window_seconds': self._rate_limiter.window_seconds
            },
            'exempt_paths': list(self._exempt_paths),
            'api_keys_count': len(self._api_key_auth._api_keys)
        }


# Global auth manager instance
def get_auth_manager() -> AuthManager:
    """Get the global authentication manager / 获取全局认证管理器"""
    return AuthManager()
