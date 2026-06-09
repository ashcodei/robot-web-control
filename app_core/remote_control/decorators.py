"""
Remote Control Decorators Module
远程控制装饰器模块

Provides decorators to mark functions as remotely callable.
提供装饰器来标记可远程调用的函数。
"""

from functools import wraps
from typing import Callable, List, Optional
from dataclasses import dataclass


@dataclass
class RemoteFunctionInfo:
    """Information about a remote-callable function / 远程可调用函数的信息"""
    name: str
    category: str
    description: str
    description_zh: str
    requires_confirm: bool
    is_emergency: bool
    allowed_args: Optional[List[str]]


def remote_callable(
    name: str = None,
    category: str = "general",
    description: str = "",
    description_zh: str = "",
    requires_confirm: bool = False,
    is_emergency: bool = False,
    allowed_args: List[str] = None
):
    """
    Decorator to mark a function as remotely callable.
    装饰器，用于标记函数为可远程调用。

    Args:
        name: Display name (defaults to function name)
              显示名称（默认为函数名）
        category: Category for grouping (e.g., "lebai", "gantry", "wok")
                  用于分组的类别
        description: English description
                    英文描述
        description_zh: Chinese description
                       中文描述
        requires_confirm: Whether to require confirmation before execution
                         是否需要在执行前确认
        is_emergency: Whether this is an emergency function (high priority)
                     是否是紧急函数（高优先级）
        allowed_args: List of allowed argument names (None = any)
                     允许的参数名列表（None = 任意）

    Usage:
        @remote_callable(name="归位", category="gantry", description_zh="龙门架归位")
        def home(self):
            ...

        @remote_callable(category="lebai", requires_confirm=True, is_emergency=True)
        def emergency_stop(self):
            ...
    """
    def decorator(func: Callable):
        # Store metadata on the function
        func._remote_callable = True
        func._remote_info = RemoteFunctionInfo(
            name=name or func.__name__,
            category=category,
            description=description or func.__doc__ or "",
            description_zh=description_zh or description or func.__doc__ or "",
            requires_confirm=requires_confirm,
            is_emergency=is_emergency,
            allowed_args=allowed_args
        )

        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        # Preserve the remote info on the wrapper
        wrapper._remote_callable = True
        wrapper._remote_info = func._remote_info

        return wrapper

    return decorator


def is_remote_callable(func: Callable) -> bool:
    """
    Check if a function is marked as remote callable.
    检查函数是否被标记为可远程调用。

    Args:
        func: Function to check

    Returns:
        True if remote callable, False otherwise
    """
    return getattr(func, '_remote_callable', False)


def get_remote_info(func: Callable) -> Optional[RemoteFunctionInfo]:
    """
    Get remote function information.
    获取远程函数信息。

    Args:
        func: Function to get info for

    Returns:
        RemoteFunctionInfo or None if not remote callable
    """
    if is_remote_callable(func):
        return getattr(func, '_remote_info', None)
    return None
