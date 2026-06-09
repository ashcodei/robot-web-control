"""
Hardware Function Registry Module
硬件函数注册表模块

Manages all remotely callable hardware functions.
管理所有可远程调用的硬件函数。
"""

from typing import Dict, List, Any, Optional, Callable
import threading
import time
from dataclasses import dataclass, asdict

from app_core.remote_control.decorators import is_remote_callable, get_remote_info, RemoteFunctionInfo
from app_core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RegisteredFunction:
    """Registered function information / 注册的函数信息"""
    function_id: str
    name: str
    category: str
    description: str
    description_zh: str
    requires_confirm: bool
    is_emergency: bool
    controller_name: str
    callable: Callable

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (excluding callable) / 转换为字典（不包括callable）"""
        return {
            "function_id": self.function_id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "description_zh": self.description_zh,
            "requires_confirm": self.requires_confirm,
            "is_emergency": self.is_emergency,
            "controller_name": self.controller_name
        }


@dataclass
class ExecutionResult:
    """Function execution result / 函数执行结果"""
    success: bool
    result: Any
    error: Optional[str]
    execution_time_ms: float
    function_id: str
    timestamp: float


class HardwareFunctionRegistry:
    """
    Registry for all remotely callable hardware functions.
    所有可远程调用硬件函数的注册表。
    """

    _instance: Optional['HardwareFunctionRegistry'] = None
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

        self.functions: Dict[str, RegisteredFunction] = {}
        self.controllers: Dict[str, Any] = {}
        self._execution_history: List[ExecutionResult] = []
        self._max_history = 1000
        self._initialized = True

    def register_controller(self, name: str, controller: Any):
        """
        Register a hardware controller and scan for @remote_callable functions.
        注册硬件控制器并扫描@remote_callable函数。

        Args:
            name: Controller name / 控制器名称
            controller: Controller instance / 控制器实例
        """
        self.controllers[name] = controller

        # Scan for remote callable methods
        for attr_name in dir(controller):
            if attr_name.startswith('_'):
                continue

            try:
                attr = getattr(controller, attr_name)
                if callable(attr) and is_remote_callable(attr):
                    info = get_remote_info(attr)
                    if info:
                        func_id = f"{name}.{attr_name}"
                        self.functions[func_id] = RegisteredFunction(
                            function_id=func_id,
                            name=info.name,
                            category=info.category,
                            description=info.description,
                            description_zh=info.description_zh,
                            requires_confirm=info.requires_confirm,
                            is_emergency=info.is_emergency,
                            controller_name=name,
                            callable=attr
                        )
                        logger.info(f"Registered remote function: {func_id}")
            except Exception as e:
                logger.warning(f"Failed to scan {attr_name}: {e}")

    def unregister_controller(self, name: str):
        """
        Unregister a controller and its functions.
        取消注册控制器及其函数。

        Args:
            name: Controller name / 控制器名称
        """
        if name in self.controllers:
            del self.controllers[name]

        # Remove associated functions
        to_remove = [
            func_id for func_id in self.functions
            if func_id.startswith(f"{name}.")
        ]
        for func_id in to_remove:
            del self.functions[func_id]

    def get_available_functions(self) -> List[Dict[str, Any]]:
        """
        Get list of all available functions for remote clients.
        获取所有可用函数列表供远程客户端使用。

        Returns:
            List of function info dictionaries
        """
        return [func.to_dict() for func in self.functions.values()]

    def get_functions_by_category(self, category: str) -> List[Dict[str, Any]]:
        """
        Get functions filtered by category.
        按类别过滤获取函数。

        Args:
            category: Category to filter by

        Returns:
            List of function info dictionaries
        """
        return [
            func.to_dict() for func in self.functions.values()
            if func.category == category
        ]

    def get_categories(self) -> List[str]:
        """
        Get list of all categories.
        获取所有类别列表。

        Returns:
            List of unique categories
        """
        categories = set(func.category for func in self.functions.values())
        return sorted(list(categories))

    def execute_function(self, function_id: str,
                         args: List = None,
                         kwargs: Dict = None) -> ExecutionResult:
        """
        Execute a registered function.
        执行注册的函数。

        Args:
            function_id: Function ID (e.g., "lebai.move_to_default")
            args: Positional arguments
            kwargs: Keyword arguments

        Returns:
            ExecutionResult with details
        """
        if function_id not in self.functions:
            return ExecutionResult(
                success=False,
                result=None,
                error=f"Unknown function: {function_id}",
                execution_time_ms=0,
                function_id=function_id,
                timestamp=time.time()
            )

        func_info = self.functions[function_id]
        start_time = time.time()

        try:
            result = func_info.callable(*(args or []), **(kwargs or {}))
            execution_time_ms = (time.time() - start_time) * 1000

            exec_result = ExecutionResult(
                success=True,
                result=result,
                error=None,
                execution_time_ms=execution_time_ms,
                function_id=function_id,
                timestamp=time.time()
            )

            logger.info(f"Executed {function_id} successfully in {execution_time_ms:.1f}ms")

        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000

            exec_result = ExecutionResult(
                success=False,
                result=None,
                error=str(e),
                execution_time_ms=execution_time_ms,
                function_id=function_id,
                timestamp=time.time()
            )

            logger.error(f"Execution of {function_id} failed: {e}")

        # Add to history
        self._execution_history.append(exec_result)
        if len(self._execution_history) > self._max_history:
            self._execution_history = self._execution_history[-self._max_history:]

        return exec_result

    def get_function_info(self, function_id: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a specific function.
        获取特定函数的信息。

        Args:
            function_id: Function ID

        Returns:
            Function info dictionary or None
        """
        if function_id in self.functions:
            return self.functions[function_id].to_dict()
        return None

    def get_execution_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get recent execution history.
        获取最近的执行历史。

        Args:
            limit: Maximum number of entries

        Returns:
            List of execution results (newest first)
        """
        history = self._execution_history[-limit:][::-1]
        return [
            {
                "success": r.success,
                "result": str(r.result) if r.result is not None else None,
                "error": r.error,
                "execution_time_ms": r.execution_time_ms,
                "function_id": r.function_id,
                "timestamp": r.timestamp
            }
            for r in history
        ]

    def clear_history(self):
        """Clear execution history / 清除执行历史"""
        self._execution_history.clear()


# Global registry instance / 全局注册表实例
def get_function_registry() -> HardwareFunctionRegistry:
    """Get the global function registry / 获取全局函数注册表"""
    return HardwareFunctionRegistry()
