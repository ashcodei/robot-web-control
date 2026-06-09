"""
Gripper Controller Module
夹爪控制器模块

Controls the LMG-90 gripper via Modbus RTU.
通过Modbus RTU控制LMG-90夹爪。

Modbus Registers (from Lebai LMG-90 documentation):
- 40000: Target opening (0-100%)
- 40001: Target force (0-100%)
- 40005: Current position (0-100%)
- 40006: Current torque (0-100%)
- 40007: Command complete (1=done, 0=busy)
- 40010: Speed (0-100%)
"""

import threading
import time
from typing import Dict, Any, Optional, Tuple

from hardware.base_hardware import BaseHardwareController, HardwareState
from config.settings import get_settings
from app_core.logger import get_logger
from app_core.remote_control import remote_callable

logger = get_logger(__name__)

# pymodbus version detection and logging suppression
PYMODBUS_VERSION: Tuple[int, int] = (3, 0)
try:
    from pymodbus import __version__ as _pymodbus_version
    _parts = _pymodbus_version.split('.')[:2]
    PYMODBUS_VERSION = (int(_parts[0]), int(_parts[1]) if len(_parts) > 1 else 0)

    # Suppress pymodbus internal logging to prevent log spam in GUI
    import logging as _std_logging
    _std_logging.getLogger("pymodbus").setLevel(_std_logging.CRITICAL)
    _std_logging.getLogger("pymodbus.logging").setLevel(_std_logging.CRITICAL)
    _std_logging.getLogger("pymodbus.client").setLevel(_std_logging.CRITICAL)
except Exception:
    pass


class GripperController(BaseHardwareController):
    """
    LMG-90 Gripper controller using Modbus RTU.
    使用Modbus RTU的LMG-90夹爪控制器。
    """

    # Modbus register addresses (from Lebai LMG-90 documentation)
    REG_OPENING = 40000      # Write: target opening 0-100%
    REG_FORCE = 40001        # Write: target force 0-100%
    REG_POSITION = 40005     # Read: current position 0-100%
    REG_TORQUE = 40006       # Read: current torque 0-100%
    REG_COMPLETE = 40007     # Read: command complete (1=done, 0=busy)
    REG_SPEED = 40010        # Read/Write: speed 0-100%

    def __init__(self, name: str = "gripper", config: Dict[str, Any] = None):
        """
        Initialize gripper controller.

        Args:
            name: Controller name
            config: Configuration dictionary (optional)
        """
        super().__init__(name, config)

        settings = get_settings()
        self._port = config.get('serial_port') if config else settings.gripper.serial_port
        self._baudrate = config.get('baudrate') if config else settings.gripper.baudrate
        self._slave_address = config.get('slave_address') if config else settings.gripper.slave_address
        self._parity = config.get('parity') if config else settings.gripper.parity
        self._timeout = config.get('timeout') if config else settings.gripper.timeout

        self._client = None
        self._position = 0
        self._torque = 0
        self._target_opening = 50
        self._target_force = 50
        self._speed = 50
        self._lock = threading.Lock()

        # Connection retry settings
        self._max_connect_retries = 2
        self._connect_retry_delay = 0.3

        # Background status poller
        self._poller_stop = threading.Event()
        self._poller_thread: Optional[threading.Thread] = None
        self._read_failure_count = 0
        self._max_read_failures = 3

        # Try to import pymodbus
        self._modbus_available = False
        try:
            from pymodbus.client import ModbusSerialClient
            self._modbus_available = True
        except ImportError:
            logger.warning("pymodbus not installed, gripper running in simulation mode")

    def _get_slave_kwargs(self) -> Dict[str, int]:
        """Get correct slave/unit argument based on pymodbus version."""
        # pymodbus 3.7+ uses 'device_id', older 3.x uses 'slave', 2.x uses 'unit'
        if PYMODBUS_VERSION >= (3, 7):
            return {'device_id': self._slave_address}
        elif PYMODBUS_VERSION[0] >= 3:
            return {'slave': self._slave_address}
        return {'unit': self._slave_address}

    def connect(self, max_retries: int = None) -> bool:
        """
        Connect to gripper via Modbus RTU.
        通过Modbus RTU连接夹爪。

        Args:
            max_retries: Maximum connection attempts

        Returns:
            True if connection successful, False otherwise.
        """
        self.state = HardwareState.CONNECTING
        retries = max_retries if max_retries is not None else self._max_connect_retries

        if not self._modbus_available:
            logger.warning("Gripper: pymodbus not installed, cannot connect (simulation mode)")
            self.state = HardwareState.DISCONNECTED
            return False

        from pymodbus.client import ModbusSerialClient

        for attempt in range(retries):
            try:
                self._client = ModbusSerialClient(
                    port=self._port,
                    baudrate=self._baudrate,
                    parity=self._parity,
                    stopbits=1,
                    bytesize=8,
                    timeout=self._timeout
                )

                if self._client.connect():
                    logger.info(f"Gripper connected on {self._port} (attempt {attempt + 1})")
                    self.state = HardwareState.CONNECTED
                    self._read_failure_count = 0
                    self._read_status()
                    self._start_poller()
                    return True
                else:
                    logger.warning(f"Gripper connection attempt {attempt + 1} failed")

            except Exception as e:
                logger.warning(f"Gripper connection attempt {attempt + 1} error: {e}")

            if attempt < retries - 1:
                time.sleep(self._connect_retry_delay)

        self._set_error(f"Failed to connect after {retries} attempts")
        return False

    def disconnect(self) -> bool:
        """Disconnect from gripper / 断开夹爪连接"""
        self._stop_poller()
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

        self.state = HardwareState.DISCONNECTED
        logger.info("Gripper disconnected")
        return True

    def reconnect(self, max_retries: int = None) -> bool:
        """Reconnect to gripper (disconnect first, then connect)."""
        self._read_failure_count = 0
        self.disconnect()
        return self.connect(max_retries=max_retries)

    def start(self) -> bool:
        """Start gripper operation / 启动夹爪"""
        if self.state != HardwareState.CONNECTED:
            return False
        self.state = HardwareState.RUNNING
        return True

    def stop(self) -> bool:
        """Stop gripper operation / 停止夹爪"""
        self.state = HardwareState.CONNECTED
        return True

    def pause(self) -> bool:
        """Pause gripper operation / 暂停夹爪"""
        self.state = HardwareState.PAUSED
        return True

    def resume(self) -> bool:
        """Resume gripper operation / 恢复夹爪"""
        if self.state == HardwareState.PAUSED:
            self.state = HardwareState.RUNNING
            return True
        return False

    @remote_callable(
        name="夹爪急停",
        category="gripper",
        description="Emergency stop gripper",
        description_zh="夹爪紧急停止",
        is_emergency=True
    )
    def emergency_stop(self) -> bool:
        """Emergency stop gripper / 夹爪紧急停止"""
        self.state = HardwareState.EMERGENCY_STOP
        logger.warning("Gripper emergency stop executed")
        return True

    def _start_poller(self):
        """Start background status poller / 启动后台状态轮询"""
        self._stop_poller()
        self._poller_stop.clear()
        self._poller_thread = threading.Thread(
            target=self._poller_loop, daemon=True, name="GripperPoller"
        )
        self._poller_thread.start()
        logger.debug("Gripper status poller started")

    def _stop_poller(self):
        """Stop background status poller / 停止后台状态轮询"""
        self._poller_stop.set()
        if self._poller_thread and self._poller_thread.is_alive():
            self._poller_thread.join(timeout=2.0)
        self._poller_thread = None

    def _poller_loop(self):
        """Background loop that polls gripper status / 后台轮询循环"""
        while not self._poller_stop.is_set():
            self._read_status()
            if self._read_failure_count >= self._max_read_failures:
                logger.warning("Gripper poller stopped due to too many failures. Manual reconnect required.")
                self._poller_stop.set()
                break
            self._poller_stop.wait(0.5)

    def _read_status(self) -> bool:
        """Read current gripper status (position and torque)."""
        if not self._client:
            return True  # Simulation mode

        with self._lock:
            try:
                # Read registers 40005 (position) and 40006 (torque)
                result = self._client.read_holding_registers(
                    self.REG_POSITION, count=2, **self._get_slave_kwargs()
                )

                if result and not result.isError():
                    self._position = result.registers[0]
                    self._torque = result.registers[1]
                    self._read_failure_count = 0
                    return True
                else:
                    self._read_failure_count += 1

            except Exception:
                self._read_failure_count += 1

        if self._read_failure_count >= self._max_read_failures:
            if self.state not in [HardwareState.ERROR, HardwareState.EMERGENCY_STOP]:
                logger.error(f"Gripper marked unavailable after {self._read_failure_count} consecutive failures")
                self._set_error(f"Communication lost after {self._read_failure_count} failures")

        return False

    def get_status(self) -> Dict[str, Any]:
        """Get gripper status / 获取夹爪状态"""
        return {
            "name": self._name,
            "state": self._state.value,
            "position": self._position,
            "torque": self._torque,
            "target_opening": self._target_opening,
            "target_force": self._target_force,
            "speed": self._speed,
            "port": self._port
        }

    def is_ready(self) -> bool:
        """Check if gripper is ready / 检查夹爪是否就绪"""
        return self.state in [HardwareState.CONNECTED, HardwareState.RUNNING]

    @remote_callable(
        name="设置开度",
        category="gripper",
        description="Set gripper opening",
        description_zh="设置夹爪开度"
    )
    def set_opening(self, opening: int) -> bool:
        """
        Set gripper opening (0-100%).
        设置夹爪开度。

        Args:
            opening: Opening percentage (0=closed, 100=open)
        """
        opening = max(0, min(100, int(opening)))

        # Store target even if not connected (for display)
        self._target_opening = opening

        if not self._client or not self.is_ready():
            return True  # Simulation mode or not connected

        with self._lock:
            try:
                result = self._client.write_registers(
                    self.REG_OPENING, [opening], **self._get_slave_kwargs()
                )
                if not result.isError():
                    return True
            except Exception:
                pass
        return False

    @remote_callable(
        name="设置力度",
        category="gripper",
        description="Set gripper force",
        description_zh="设置夹爪力度"
    )
    def set_force(self, force: int) -> bool:
        """
        Set gripper force (0-100%).
        设置夹爪力度。

        Args:
            force: Force percentage (0-100)
        """
        force = max(0, min(100, int(force)))

        # Store target even if not connected (for display)
        self._target_force = force

        if not self._client or not self.is_ready():
            return True  # Simulation mode or not connected

        with self._lock:
            try:
                result = self._client.write_registers(
                    self.REG_FORCE, [force], **self._get_slave_kwargs()
                )
                if not result.isError():
                    return True
            except Exception:
                pass
        return False

    @remote_callable(
        name="设置速度",
        category="gripper",
        description="Set gripper speed",
        description_zh="设置夹爪速度"
    )
    def set_speed(self, speed: int) -> bool:
        """
        Set gripper speed (0-100%).
        设置夹爪速度。

        Args:
            speed: Speed percentage (0-100)
        """
        speed = max(0, min(100, int(speed)))

        # Store target even if not connected (for display)
        self._speed = speed

        if not self._client or not self.is_ready():
            return True  # Simulation mode or not connected

        with self._lock:
            try:
                result = self._client.write_registers(
                    self.REG_SPEED, [speed], **self._get_slave_kwargs()
                )
                if not result.isError():
                    return True
            except Exception:
                pass
        return False

    def set_gripper(self, opening: int, force: int) -> bool:
        """
        Set both opening and force at once.
        同时设置开度和力度。

        Args:
            opening: Opening percentage (0-100)
            force: Force percentage (0-100)
        """
        opening = max(0, min(100, int(opening)))
        force = max(0, min(100, int(force)))

        # Store targets even if not connected (for display)
        self._target_opening = opening
        self._target_force = force

        if not self._client or not self.is_ready():
            return True  # Simulation mode or not connected

        with self._lock:
            try:
                # Write both registers at once (40000=opening, 40001=force)
                result = self._client.write_registers(
                    self.REG_OPENING, [opening, force], **self._get_slave_kwargs()
                )
                if not result.isError():
                    return True
            except Exception:
                pass
        return False

    @property
    def position(self) -> int:
        """Get current position / 获取当前位置"""
        return self._position

    @property
    def torque(self) -> int:
        """Get current torque / 获取当前扭矩"""
        return self._torque

    # ==================== Public API for VLA Recording ====================

    def get_position(self) -> int:
        """
        Get current gripper position (0-100).
        Method version of position property for VLA recording.

        Returns:
            Current position 0-100 (0=closed, 100=open)
        """
        return self._position

    def set_position(self, position: int, torque: int = 100) -> bool:
        """
        Set gripper position with specified torque.
        Convenience method for VLA recording gripper control.

        Args:
            position: Target position 0-100 (0=closed, 100=open)
            torque: Grip force 0-100 (default 100)

        Returns:
            True if command sent successfully
        """
        return self.set_gripper(position, torque)

    def is_connected(self) -> bool:
        """
        Check if gripper is connected and ready.

        Returns:
            True if gripper is connected and operational
        """
        return self.is_ready()
