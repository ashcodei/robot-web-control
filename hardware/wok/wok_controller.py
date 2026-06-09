"""
Wok Controller Module
炒锅控制器模块

Controls the automatic wok via Modbus RTU.
通过Modbus RTU控制自动炒锅。

Implements best practices from ha-modbus-integration skill:
- Message pacing (message_wait_ms)
- Cache fallback on read failures
- Connection retry mechanism
- pymodbus version compatibility
"""

import threading
import time
from typing import Dict, Any, Optional, Tuple
from enum import IntEnum

from hardware.base_hardware import BaseHardwareController, HardwareState
from config.settings import get_settings
from app_core.logger import get_logger
from app_core.remote_control import remote_callable

logger = get_logger(__name__)

# pymodbus version detection for compatibility
PYMODBUS_VERSION: Tuple[int, int] = (3, 0)
_PYMODBUS_SLAVE_ARG: Optional[str] = None  # Will be detected at runtime
try:
    from pymodbus import __version__ as _pymodbus_version
    _parts = _pymodbus_version.split('.')[:2]
    PYMODBUS_VERSION = (int(_parts[0]), int(_parts[1]) if len(_parts) > 1 else 0)
    logger.debug(f"pymodbus version detected: {PYMODBUS_VERSION}")
except Exception:
    pass


class WokPosition(IntEnum):
    """Wok position enumeration / 炒锅位置枚举"""
    WORKING = 0      # 工作位
    POUR = 1         # 倒出位
    WASH = 2         # 清洗位


class WokController(BaseHardwareController):
    """
    Automatic wok controller using Modbus RTU.
    使用Modbus RTU的自动炒锅控制器。
    """

    # Modbus coil addresses (matching reference wok hardware)
    COIL_AUTO_COOK   = 0x0FA0   # Auto cooking ON/OFF
    COIL_WOK_UP      = 0x0FA1   # Wok up (momentary)
    COIL_WOK_DOWN    = 0x0FA2   # Wok down (momentary)
    COIL_WORKING_POS = 0x0FA4   # Working position
    COIL_POUR_POS    = 0x0FA5   # Pour position
    COIL_LOADING_POS = 0x0FA6   # Ingredient loading position (M6)

    # Sauce dispensing trigger coils (M11–M15)
    COIL_SAUCE_1     = 0x0FAB
    COIL_SAUCE_2     = 0x0FAC
    COIL_SAUCE_3     = 0x0FAD
    COIL_SAUCE_4     = 0x0FAE
    COIL_SAUCE_5     = 0x0FAF

    # Position feedback coils (read-only, M26–M28)
    COIL_AT_STIRFRY_POS  = 0x0FBA
    COIL_AT_POUR_POS     = 0x0FBB
    COIL_AT_LOADING_POS  = 0x0FBC

    # Modbus holding registers
    REG_RECIPE_ID    = 0x00C8   # Recipe ID register
    REG_TEMPERATURE  = 0x0001   # Temperature register
    REG_STIR_SPEED   = 0x0002   # Stir speed register
    REG_HEATING      = 0x0003   # Heating on/off
    REG_STIRRING     = 0x0004   # Stirring on/off
    REG_STATUS       = 0x0010   # Status register

    # Sauce dispensing pulse value registers (D31–D35)
    REG_SAUCE_1_PULSE = 0x001F
    REG_SAUCE_2_PULSE = 0x0020
    REG_SAUCE_3_PULSE = 0x0021
    REG_SAUCE_4_PULSE = 0x0022
    REG_SAUCE_5_PULSE = 0x0023

    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize wok controller.

        Args:
            config: Configuration dictionary (optional)
        """
        super().__init__("wok", config)

        settings = get_settings()
        self._port = config.get('serial_port') if config else settings.wok.serial_port
        self._baudrate = config.get('baudrate') if config else settings.wok.baudrate
        self._slave_address = config.get('slave_address') if config else settings.wok.slave_address
        self._timeout = config.get('timeout') if config else settings.wok.timeout

        self._client = None
        self._position = WokPosition.WORKING
        self._temperature = 0.0
        self._stir_speed = 0
        self._is_heating = False
        self._is_stirring = False
        self._is_auto_cooking = False
        self._position_feedback = {"at_stirfry": False, "at_pour": False, "at_loading": False}
        self._lock = threading.Lock()

        # Modbus communication settings (ha-modbus-integration best practices)
        self._message_wait_ms = config.get('message_wait_ms', 30) if config else 30  # RTU recommended: 20-50ms
        self._last_io_time: float = 0
        self._write_confirm_delay_ms = config.get('write_confirm_delay_ms', 100) if config else 100

        # Cache fallback settings (modbus-troubleshooting best practices)
        self._read_failure_count = 0
        self._max_read_failures = 3  # Mark unavailable after this many consecutive failures
        self._last_good_status: Optional[Dict[str, Any]] = None

        # Connection retry settings
        self._max_connect_retries = 2
        self._connect_retry_delay = 0.3  # seconds

        # Background status poller
        self._poller_stop = threading.Event()
        self._poller_thread: Optional[threading.Thread] = None

        # Try to import pymodbus
        self._modbus_available = False
        try:
            from pymodbus.client import ModbusSerialClient
            self._modbus_available = True
        except ImportError:
            logger.warning("pymodbus not installed, running in simulation mode")

    def connect(self, max_retries: int = None) -> bool:
        """
        Connect to wok via Modbus with retry support.
        通过Modbus连接炒锅（支持重试）。

        Args:
            max_retries: Maximum connection attempts (default: self._max_connect_retries)

        Returns:
            True if connection successful, False otherwise.
        """
        self.state = HardwareState.CONNECTING
        retries = max_retries if max_retries is not None else self._max_connect_retries

        if not self._modbus_available:
            logger.warning("Wok: pymodbus not installed, cannot connect (simulation mode)")
            self.state = HardwareState.DISCONNECTED
            return False

        from pymodbus.client import ModbusSerialClient

        for attempt in range(retries):
            try:
                self._client = ModbusSerialClient(
                    port=self._port,
                    baudrate=self._baudrate,
                    timeout=self._timeout
                )

                if self._client.connect():
                    logger.info(f"Wok connected on {self._port} (attempt {attempt + 1})")
                    self.state = HardwareState.CONNECTED
                    self._read_failure_count = 0
                    # Detect correct slave/unit argument for this pymodbus version
                    self._detect_slave_arg()
                    self._read_status()
                    self._start_poller()
                    return True
                else:
                    logger.warning(f"Wok connection attempt {attempt + 1} failed")

            except Exception as e:
                logger.warning(f"Wok connection attempt {attempt + 1} error: {e}")

            # Wait before retry (except on last attempt)
            if attempt < retries - 1:
                time.sleep(self._connect_retry_delay)

        self._set_error(f"Failed to connect after {retries} attempts")
        return False

    def disconnect(self) -> bool:
        """Disconnect from wok / 断开炒锅连接"""
        self._stop_poller()
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

        self.state = HardwareState.DISCONNECTED
        logger.info("Wok disconnected")
        return True

    def reconnect(self, max_retries: int = None) -> bool:
        """
        Reconnect to wok (disconnect first, then connect).
        重新连接炒锅（先断开，再连接）。

        This method resets failure counters and is meant to be called
        when user clicks a "Connect" button after connection failures.

        Args:
            max_retries: Maximum connection attempts

        Returns:
            True if reconnection successful, False otherwise.
        """
        global _PYMODBUS_SLAVE_ARG
        # Reset cached slave argument detection
        _PYMODBUS_SLAVE_ARG = None
        # Reset failure count
        self._read_failure_count = 0
        # Disconnect first
        self.disconnect()
        # Try to connect
        return self.connect(max_retries=max_retries)

    def start(self) -> bool:
        """Start wok operation / 启动炒锅"""
        if self.state != HardwareState.CONNECTED:
            return False

        self.state = HardwareState.RUNNING
        return True

    def stop(self) -> bool:
        """Stop wok operation / 停止炒锅"""
        self.stop_heating()
        self.stop_stirring()
        self.state = HardwareState.CONNECTED
        return True

    def pause(self) -> bool:
        """Pause wok operation / 暂停炒锅"""
        self.stop_stirring()
        self.state = HardwareState.PAUSED
        return True

    def resume(self) -> bool:
        """Resume wok operation / 恢复炒锅"""
        if self.state == HardwareState.PAUSED:
            self.state = HardwareState.RUNNING
            return True
        return False

    @remote_callable(
        name="急停",
        category="wok",
        description="Emergency stop wok",
        description_zh="炒锅紧急停止",
        is_emergency=True
    )
    def emergency_stop(self) -> bool:
        """Emergency stop wok / 炒锅紧急停止"""
        self.stop_heating()
        self.stop_stirring()
        self.state = HardwareState.EMERGENCY_STOP
        logger.warning("Wok emergency stop executed")
        return True

    def _start_poller(self):
        """Start background status poller / 启动后台状态轮询"""
        self._stop_poller()
        self._poller_stop.clear()
        self._poller_thread = threading.Thread(
            target=self._poller_loop, daemon=True, name="WokPoller"
        )
        self._poller_thread.start()
        logger.debug("Wok status poller started")

    def _stop_poller(self):
        """Stop background status poller / 停止后台状态轮询"""
        self._poller_stop.set()
        if self._poller_thread and self._poller_thread.is_alive():
            self._poller_thread.join(timeout=2.0)
        self._poller_thread = None

    def _poller_loop(self):
        """Background loop that polls wok status / 后台轮询循环"""
        while not self._poller_stop.is_set():
            self._read_status()
            # Stop polling if too many consecutive failures
            if self._read_failure_count >= self._max_read_failures:
                logger.warning("Wok poller stopped due to too many failures. Manual reconnect required.")
                self._poller_stop.set()
                break
            self._poller_stop.wait(1.0)

    def get_status(self) -> Dict[str, Any]:
        """Get wok status (returns cached values, updated by background poller) / 获取炒锅状态"""
        return {
            "name": self._name,
            "state": self._state.value,
            "position": self._position.name,
            "temperature": self._temperature,
            "stir_speed": self._stir_speed,
            "is_heating": self._is_heating,
            "is_stirring": self._is_stirring,
            "is_auto_cooking": self._is_auto_cooking,
            "position_feedback": self._position_feedback,
            "port": self._port
        }

    def is_ready(self) -> bool:
        """Check if wok is ready / 检查炒锅是否就绪"""
        return self.state in [HardwareState.CONNECTED, HardwareState.RUNNING]

    def _get_slave_kwargs(self) -> Dict[str, int]:
        """
        Get correct slave/unit keyword argument based on pymodbus version.
        根据pymodbus版本获取正确的slave/unit关键字参数。

        Runtime detection is used because pymodbus API changed across versions:
        - pymodbus 2.x: 'unit' keyword
        - pymodbus 3.0-3.4: 'slave' keyword
        - pymodbus 3.5+: varies by method
        """
        global _PYMODBUS_SLAVE_ARG

        # If already detected, use cached value
        if _PYMODBUS_SLAVE_ARG is not None:
            if _PYMODBUS_SLAVE_ARG == '':
                return {}  # No slave argument needed
            return {_PYMODBUS_SLAVE_ARG: self._slave_address}

        # Default based on version, will be corrected on first use if wrong
        if PYMODBUS_VERSION >= (3, 0):
            return {'slave': self._slave_address}
        else:
            return {'unit': self._slave_address}

    def _detect_slave_arg(self) -> str:
        """
        Detect which slave/unit argument pymodbus accepts.
        检测pymodbus接受哪个slave/unit参数。

        Returns:
            The argument name that works ('slave', 'unit', or '' if none needed)
        """
        global _PYMODBUS_SLAVE_ARG

        if _PYMODBUS_SLAVE_ARG is not None:
            return _PYMODBUS_SLAVE_ARG

        if not self._client:
            return 'slave' if PYMODBUS_VERSION >= (3, 0) else 'unit'

        # Try 'slave' first (pymodbus 3.x)
        try:
            self._client.read_holding_registers(0, 1, slave=self._slave_address)
            _PYMODBUS_SLAVE_ARG = 'slave'
            logger.debug("pymodbus uses 'slave' argument")
            return 'slave'
        except TypeError:
            pass

        # Try 'unit' (pymodbus 2.x)
        try:
            self._client.read_holding_registers(0, 1, unit=self._slave_address)
            _PYMODBUS_SLAVE_ARG = 'unit'
            logger.debug("pymodbus uses 'unit' argument")
            return 'unit'
        except TypeError:
            pass

        # Try without argument (some versions)
        try:
            self._client.read_holding_registers(0, 1)
            _PYMODBUS_SLAVE_ARG = ''
            logger.debug("pymodbus does not need slave/unit argument")
            return ''
        except Exception:
            pass

        # Default to 'slave'
        _PYMODBUS_SLAVE_ARG = 'slave'
        return 'slave'

    def _ensure_message_pacing(self):
        """
        Ensure minimum time between Modbus messages.
        确保Modbus消息之间有最小间隔时间。

        This prevents overloading RTU gateways (ha-modbus-integration best practice).
        """
        elapsed_ms = (time.time() - self._last_io_time) * 1000
        if elapsed_ms < self._message_wait_ms:
            sleep_time = (self._message_wait_ms - elapsed_ms) / 1000
            time.sleep(sleep_time)

    def _write_register(self, register: int, value: int) -> bool:
        """
        Write Modbus register with pacing.
        写入Modbus寄存器（带消息间隔控制）。
        """
        if not self._client:
            return True  # Simulation mode

        with self._lock:
            try:
                self._ensure_message_pacing()
                result = self._client.write_register(
                    register, value, **self._get_slave_kwargs()
                )
                self._last_io_time = time.time()
                return not result.isError()
            except Exception as e:
                logger.error(f"Modbus write error (reg={register:#x}, val={value}): {e}")
                return False

    def _write_coil(self, address: int, state: bool) -> bool:
        """
        Write Modbus coil with pacing.
        写入Modbus线圈（带消息间隔控制）。
        """
        if not self._client:
            return True  # Simulation mode

        with self._lock:
            try:
                self._ensure_message_pacing()
                result = self._client.write_coil(
                    address, state, **self._get_slave_kwargs()
                )
                self._last_io_time = time.time()
                return not result.isError()
            except Exception as e:
                logger.error(f"Modbus coil write error (addr={address:#x}, state={state}): {e}")
                return False

    def _read_register(self, register: int) -> Optional[int]:
        """
        Read Modbus register with pacing.
        读取Modbus寄存器（带消息间隔控制）。
        """
        if not self._client:
            return 0  # Simulation mode

        with self._lock:
            try:
                self._ensure_message_pacing()
                result = self._client.read_holding_registers(
                    register, 1, **self._get_slave_kwargs()
                )
                self._last_io_time = time.time()
                if not result.isError():
                    return result.registers[0]
            except Exception as e:
                logger.error(f"Modbus read error (reg={register:#x}): {e}")

        return None

    def _read_status(self) -> bool:
        """
        Read all status from wok with cache fallback.
        从炒锅读取所有状态（带缓存回退）。

        Implements cache fallback pattern from ha-modbus-integration:
        - On success: reset failure count, cache as last good data
        - On failure: increment count, return cached data
        - After max_failures: mark device as unavailable

        Returns:
            True if read successful, False if using cached data.
        """
        if not self._client:
            return True  # Simulation mode

        with self._lock:
            try:
                self._ensure_message_pacing()
                # Read temperature and control registers (position is tracked via coils)
                result = self._client.read_holding_registers(
                    self.REG_TEMPERATURE, 4, **self._get_slave_kwargs()
                )
                self._last_io_time = time.time()

                if not result.isError():
                    # Success - update values and reset failure count
                    # Position is tracked locally from coil commands
                    self._temperature = result.registers[0] / 10.0
                    self._stir_speed = result.registers[1]
                    self._is_heating = bool(result.registers[2])
                    self._is_stirring = bool(result.registers[3])

                    # Read position feedback coils (M26–M28, consecutive)
                    try:
                        self._ensure_message_pacing()
                        coil_result = self._client.read_coils(
                            self.COIL_AT_STIRFRY_POS, 3, **self._get_slave_kwargs()
                        )
                        self._last_io_time = time.time()
                        if not coil_result.isError():
                            self._position_feedback = {
                                "at_stirfry": bool(coil_result.bits[0]),
                                "at_pour": bool(coil_result.bits[1]),
                                "at_loading": bool(coil_result.bits[2]),
                            }
                    except Exception as e:
                        logger.debug(f"Position feedback read error: {e}")

                    # Read M0 (auto cook coil) to detect recipe completion
                    try:
                        self._ensure_message_pacing()
                        m0_result = self._client.read_coils(
                            self.COIL_AUTO_COOK, 1, **self._get_slave_kwargs()
                        )
                        self._last_io_time = time.time()
                        if not m0_result.isError():
                            self._is_auto_cooking = bool(m0_result.bits[0])
                    except Exception as e:
                        logger.debug(f"Auto cook readback error: {e}")

                    # Cache as last good data
                    self._last_good_status = {
                        'position': self._position,
                        'temperature': self._temperature,
                        'stir_speed': self._stir_speed,
                        'is_heating': self._is_heating,
                        'is_stirring': self._is_stirring
                    }
                    self._read_failure_count = 0
                    return True
                else:
                    self._read_failure_count += 1
                    logger.warning(f"Modbus read error (attempt {self._read_failure_count}): {result}")

            except Exception as e:
                self._read_failure_count += 1
                logger.warning(f"Read status error (attempt {self._read_failure_count}): {e}")

        # Check if we should mark as unavailable
        if self._read_failure_count >= self._max_read_failures:
            if self.state not in [HardwareState.ERROR, HardwareState.EMERGENCY_STOP]:
                logger.error(f"Wok marked unavailable after {self._read_failure_count} consecutive failures")
                self._set_error(f"Communication lost after {self._read_failure_count} failures")

        # Return cached data if available (keeps entity available during transient failures)
        return False

    def _write_and_confirm(self, register: int, value: int, read_back: bool = True) -> bool:
        """
        Write register and optionally confirm by reading back.
        写入寄存器并可选地通过读取确认。

        This avoids immediate post-write refresh issues (ha-modbus-integration).

        Args:
            register: Register address
            value: Value to write
            read_back: Whether to read status after write delay

        Returns:
            True if write successful
        """
        success = self._write_register(register, value)
        if success and read_back:
            # Wait for device to process the command
            time.sleep(self._write_confirm_delay_ms / 1000)
            self._read_status()
        return success

    @remote_callable(
        name="工作位",
        category="wok",
        description="Move wok to working position",
        description_zh="移动炒锅到工作位"
    )
    def move_to_working_position(self) -> bool:
        """Move wok to working position / 移动炒锅到工作位"""
        success = self._write_coil(self.COIL_WORKING_POS, True)
        if success:
            self._position = WokPosition.WORKING
            logger.info("Wok moved to working position")
        return success

    @remote_callable(
        name="倒出位",
        category="wok",
        description="Move wok to pour position",
        description_zh="移动炒锅到倒出位"
    )
    def move_to_pour_position(self) -> bool:
        """Move wok to pour position / 移动炒锅到倒出位"""
        success = self._write_coil(self.COIL_POUR_POS, True)
        if success:
            self._position = WokPosition.POUR
            logger.info("Wok moved to pour position")
        return success

    @remote_callable(
        name="清洗位",
        category="wok",
        description="Move wok to wash position",
        description_zh="移动炒锅到清洗位"
    )
    def move_to_wash_position(self) -> bool:
        """Move wok to wash position (wok down for 4500ms) / 移动炒锅到清洗位"""
        success = self._write_coil(self.COIL_WOK_DOWN, True)
        if success:
            self._position = WokPosition.WASH
            # Release after 4500ms (matching reference implementation)
            threading.Timer(4.5, lambda: self._write_coil(self.COIL_WOK_DOWN, False)).start()
            logger.info("Wok moved to wash position")
        return success

    @remote_callable(
        name="上料位",
        category="wok",
        description="Move wok to ingredient loading position",
        description_zh="移动炒锅到上料位"
    )
    def move_to_loading_position(self) -> bool:
        """Move wok to ingredient loading position / 移动炒锅到上料位"""
        success = self._write_coil(self.COIL_LOADING_POS, True)
        if success:
            logger.info("Wok moved to loading position")
        return success

    def wok_up(self) -> bool:
        """Move wok up (momentary) / 炒锅上升"""
        return self._write_coil(self.COIL_WOK_UP, True)

    def wok_up_release(self) -> bool:
        """Release wok up / 释放炒锅上升"""
        return self._write_coil(self.COIL_WOK_UP, False)

    def wok_down(self) -> bool:
        """Move wok down (momentary) / 炒锅下降"""
        return self._write_coil(self.COIL_WOK_DOWN, True)

    def wok_down_release(self) -> bool:
        """Release wok down / 释放炒锅下降"""
        return self._write_coil(self.COIL_WOK_DOWN, False)

    def move_to_max_up(self) -> bool:
        """Move wok all the way up (hardware limit switch stops it) / 炒锅升到最高位"""
        success = self._write_coil(self.COIL_WOK_UP, True)
        if success:
            logger.info("Wok moving to max up position")
        return success

    @remote_callable(
        name="运行菜谱",
        category="wok",
        description="Run a wok recipe by ID",
        description_zh="按ID运行炒锅菜谱"
    )
    def run_recipe(self, recipe_id: int) -> bool:
        """Run a wok recipe by ID / 运行炒锅菜谱"""
        self._write_register(self.REG_RECIPE_ID, recipe_id)
        success = self._write_coil(self.COIL_AUTO_COOK, True)
        if success:
            logger.info(f"Wok recipe {recipe_id} started")
        return success

    @remote_callable(
        name="停止自动烹饪",
        category="wok",
        description="Stop auto cooking",
        description_zh="停止自动烹饪"
    )
    def stop_auto_cooking(self) -> bool:
        """Stop auto cooking / 停止自动烹饪"""
        success = self._write_coil(self.COIL_AUTO_COOK, False)
        if success:
            logger.info("Wok auto cooking stopped")
        return success

    def wait_for_recipe_done(self, timeout: float = 600.0, poll_interval: float = 1.0) -> bool:
        """
        Block until M0 (auto cook coil) reads back OFF, indicating recipe completion.
        阻塞直到M0（自动烹饪线圈）读回OFF，表示菜谱执行完成。

        Args:
            timeout: Maximum wait time in seconds (default 10 minutes)
            poll_interval: Time between polls in seconds

        Returns:
            True if recipe completed, False if timed out
        """
        if not self._client:
            return True  # Simulation mode

        elapsed = 0.0
        logger.info(f"Waiting for recipe to finish (timeout={timeout}s)...")
        while elapsed < timeout:
            time.sleep(poll_interval)
            elapsed += poll_interval

            with self._lock:
                try:
                    self._ensure_message_pacing()
                    result = self._client.read_coils(
                        self.COIL_AUTO_COOK, 1, **self._get_slave_kwargs()
                    )
                    self._last_io_time = time.time()
                    if not result.isError() and not bool(result.bits[0]):
                        logger.info(f"Recipe completed (M0 OFF after {elapsed:.1f}s)")
                        return True
                except Exception as e:
                    logger.debug(f"M0 poll error: {e}")

        logger.warning(f"Recipe wait timed out after {timeout}s")
        return False

    @remote_callable(
        name="调料出料",
        category="wok",
        description="Dispense sauce by ID and pulse value",
        description_zh="按编号和脉冲值出调料"
    )
    def dispense_sauce(self, sauce_id: int, pulse_value: int) -> bool:
        """
        Dispense sauce. Write pulse value first, then trigger coil.
        出调料：先写脉冲值，再触发线圈。

        Args:
            sauce_id: Sauce number (1-5)
            pulse_value: Pulse count controlling dispensing amount
        """
        if not 1 <= sauce_id <= 5:
            logger.error(f"Invalid sauce_id: {sauce_id}, must be 1-5")
            return False

        pulse_regs = {
            1: self.REG_SAUCE_1_PULSE, 2: self.REG_SAUCE_2_PULSE,
            3: self.REG_SAUCE_3_PULSE, 4: self.REG_SAUCE_4_PULSE,
            5: self.REG_SAUCE_5_PULSE,
        }
        trigger_coils = {
            1: self.COIL_SAUCE_1, 2: self.COIL_SAUCE_2,
            3: self.COIL_SAUCE_3, 4: self.COIL_SAUCE_4,
            5: self.COIL_SAUCE_5,
        }

        # Step 1: Write pulse value to the D register
        if not self._write_register(pulse_regs[sauce_id], pulse_value):
            logger.error(f"Failed to write pulse value for sauce {sauce_id}")
            return False

        # Step 2: Trigger the M coil
        success = self._write_coil(trigger_coils[sauce_id], True)
        if success:
            logger.info(f"Sauce {sauce_id} dispensed (pulse={pulse_value})")
        return success

    @remote_callable(
        name="开始加热",
        category="wok",
        description="Start heating",
        description_zh="开始加热"
    )
    def start_heating(self, target_temperature: float = None) -> bool:
        """Start heating / 开始加热"""
        if target_temperature:
            self._write_register(self.REG_TEMPERATURE, int(target_temperature * 10))

        success = self._write_and_confirm(self.REG_HEATING, 1)
        if success:
            logger.info("Wok heating started")
        return success

    @remote_callable(
        name="停止加热",
        category="wok",
        description="Stop heating",
        description_zh="停止加热"
    )
    def stop_heating(self) -> bool:
        """Stop heating / 停止加热"""
        success = self._write_and_confirm(self.REG_HEATING, 0)
        if success:
            logger.info("Wok heating stopped")
        return success

    @remote_callable(
        name="开始搅拌",
        category="wok",
        description="Start stirring",
        description_zh="开始搅拌"
    )
    def start_stirring(self, speed: int = 50) -> bool:
        """
        Start stirring.
        开始搅拌。

        Args:
            speed: Stir speed (0-100)
        """
        self._write_register(self.REG_STIR_SPEED, speed)
        success = self._write_and_confirm(self.REG_STIRRING, 1)
        if success:
            logger.info(f"Wok stirring started at speed {speed}")
        return success

    @remote_callable(
        name="停止搅拌",
        category="wok",
        description="Stop stirring",
        description_zh="停止搅拌"
    )
    def stop_stirring(self) -> bool:
        """Stop stirring / 停止搅拌"""
        success = self._write_and_confirm(self.REG_STIRRING, 0)
        if success:
            logger.info("Wok stirring stopped")
        return success

    def set_stir_speed(self, speed: int) -> bool:
        """
        Set stir speed.
        设置搅拌速度。

        Args:
            speed: Speed 0-100
        """
        success = self._write_and_confirm(self.REG_STIR_SPEED, speed)
        return success

    @property
    def temperature(self) -> float:
        """Get current temperature / 获取当前温度"""
        return self._temperature

    @property
    def position(self) -> WokPosition:
        """Get current position / 获取当前位置"""
        return self._position
