"""
Core Package
核心包

Provides core functionality for the cooking robot system.
为烹饪机器人系统提供核心功能。
"""

from app_core.event_bus import EventBus, EventType, Event, get_event_bus
from app_core.state_manager import StateManager, SystemState, get_state_manager
from app_core.emergency_controller import EmergencyController, get_emergency_controller
from app_core.logger import AppLogger, LogEntry, LogLevel, get_app_logger, get_logger
from app_core.threading_model import (
    HardwareCommandQueue,
    CircuitBreaker,
    CircuitBreakerOpen,
    MessageDeduplicator,
    CommandPriority,
    CommandResult
)

__all__ = [
    # Event Bus
    'EventBus',
    'EventType',
    'Event',
    'get_event_bus',

    # State Manager
    'StateManager',
    'SystemState',
    'get_state_manager',

    # Emergency Controller
    'EmergencyController',
    'get_emergency_controller',

    # Logger
    'AppLogger',
    'LogEntry',
    'LogLevel',
    'get_app_logger',
    'get_logger',

    # Threading Model
    'HardwareCommandQueue',
    'CircuitBreaker',
    'CircuitBreakerOpen',
    'MessageDeduplicator',
    'CommandPriority',
    'CommandResult',
]
