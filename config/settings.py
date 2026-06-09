"""
Settings Module
全局配置模块

Global configuration for all hardware and system settings.
所有硬件和系统设置的全局配置。

Features:
- Dataclass-based configuration
- JSON file persistence
- Validation on load
- Cross-platform path handling
"""

import os
import sys
import json
import re
import logging
import threading
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict
from pathlib import Path

# Configure module logger
logger = logging.getLogger(__name__)


# Base paths / 基础路径 (动态获取，跨平台兼容)
BASE_DIR = Path(__file__).parent.parent.resolve()
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
DUAL_ARM_STEPS_DIR = DATA_DIR / "dual_arm_steps"
EPISODES_DIR = DATA_DIR / "episodes"

# 自动创建必要的目录 / Auto-create necessary directories
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)
DUAL_ARM_STEPS_DIR.mkdir(parents=True, exist_ok=True)
EPISODES_DIR.mkdir(parents=True, exist_ok=True)


def get_platform() -> str:
    """获取当前操作系统平台 / Get current OS platform"""
    if sys.platform.startswith('win'):
        return 'windows'
    elif sys.platform.startswith('linux'):
        return 'linux'
    elif sys.platform.startswith('darwin'):
        return 'macos'
    return 'unknown'


def get_default_serial_port(device_name: str) -> str:
    """
    根据操作系统获取默认串口路径
    Get default serial port path based on OS

    Args:
        device_name: 设备名称 ('gantry', 'wok', etc.)
    """
    platform = get_platform()

    if platform == 'windows':
        # Windows 使用 COM 端口
        defaults = {
            'gantry': 'COM3',
            'wok': 'COM2',
        }
    else:
        # Linux/macOS 使用 /dev/tty* 路径
        # Arduino Mega 2560 通常使用 /dev/ttyACM0
        # Wok uses /dev/ttyUSB0, gripper uses /dev/ttyUSB1
        defaults = {
            'gantry': '/dev/ttyACM0',
            'wok': '/dev/ttyUSB0',
            'gripper': '/dev/ttyUSB1',
        }

    return defaults.get(device_name, 'COM1' if platform == 'windows' else '/dev/ttyUSB0')


@dataclass
class LebaiConfig:
    """Lebai LM3 robot arm configuration / 乐白LM3机械臂配置"""
    ip: str = "10.20.17.1"
    port: int = 5180
    speed_factor: float = 0.7
    acceleration: float = 0.5
    default_pose: list = field(default_factory=lambda: [0, -60, 80, -110, -90, 0])


@dataclass
class GantryConfig:
    """Gantry configuration / 龙门架配置 (Arduino Mega 2560 custom protocol)"""
    serial_port: str = field(default_factory=lambda: get_default_serial_port('gantry'))
    baudrate: int = 9600
    timeout: float = 0.2  # Must match original (0.2s) - longer timeout blocks RX loop
    connect_delay: float = 1.2  # Arduino重启等待时间
    vertical_max: float = 5000.0  # 垂直最大行程(mm)
    horizontal_max: float = 5000.0  # 水平最大行程(mm)
    ppr: int = 5000  # 每转脉冲数
    mm_per_rev: float = 160.0  # 每转移动距离(mm)
    firmware_fqbn: str = "arduino:avr:mega:cpu=atmega2560"  # Arduino board FQBN


@dataclass
class DualArmConfig:
    """Dual arm robot configuration / 双臂机器人配置"""
    ip: str = "192.168.10.21"
    port: int = 8080
    left_arm_id: str = "left"
    right_arm_id: str = "right"
    speed_factor: float = 0.3


@dataclass
class LinkerHandConfig:
    """L6 Linker Hand configuration / L6机械手配置"""
    can_interface: str = "can0"
    baudrate: int = 1000000
    left_hand_id: int = 1
    right_hand_id: int = 2


@dataclass
class DexhandConfig:
    """Dexterous hand configuration / 灵巧手配置"""
    can_interface: str = "can0"
    baudrate: int = 1000000
    modbus_port: Optional[str] = None
    hand_type: str = "L6"  # "L6" or "L10"
    left_enabled: bool = True
    right_enabled: bool = True
    # Speed and torque defaults
    default_speed: int = 100
    default_torque: int = 150
    # Force grab defaults
    force_threshold: int = 50
    grab_step: int = 5
    stall_time: float = 1.5


@dataclass
class GlovesConfig:
    """Teleoperation gloves configuration / 遥操作手套配置"""
    enabled: bool = False
    ros_host: str = "localhost"
    ros_port: int = 9090
    left_topic: str = "/gloves/left_hand"
    right_topic: str = "/gloves/right_hand"
    calibration_file: Optional[str] = None
    smoothing_factor: float = 0.8
    update_rate: float = 50.0  # Hz


@dataclass
class RecordingConfig:
    """RL recording configuration / 强化学习录制配置"""
    output_dir: str = "recordings"
    format: str = "hdf5"  # "hdf5" or "pickle"
    include_images: bool = True
    include_depth: bool = False
    image_size: tuple = (640, 480)
    record_rate: float = 30.0  # Hz
    max_episode_length: float = 300.0  # seconds


@dataclass
class TeleopConfig:
    """Teleoperation configuration / 遥操作配置"""
    mode: str = "local"  # "local", "remote_lan", "remote_wan"
    ros_host: str = "localhost"
    ros_port: int = 9090
    relay_server: Optional[str] = None
    update_rate: float = 100.0  # Hz


@dataclass
class WokConfig:
    """Automatic wok configuration / 自动炒锅配置"""
    serial_port: str = field(default_factory=lambda: get_default_serial_port('wok'))
    baudrate: int = 9600
    slave_address: int = 1
    timeout: float = 1.0


@dataclass
class GripperConfig:
    """LMG-90 Gripper configuration / LMG-90夹爪配置"""
    serial_port: str = field(default_factory=lambda: get_default_serial_port('gripper'))
    baudrate: int = 115200
    slave_address: int = 1
    parity: str = "N"
    timeout: float = 1.0
    default_force: int = 50
    default_speed: int = 50


@dataclass
class InventoryConfig:
    """Refrigerator inventory configuration / 冰箱库存配置"""
    rows: int = 4
    columns: int = 3
    slot_width: float = 100.0
    slot_height: float = 80.0


@dataclass
class CameraConfig:
    """Camera configuration / 摄像头配置"""
    device_id: int = 0
    width: int = 640
    height: int = 480
    fps: int = 30


@dataclass
class RemoteControlConfig:
    """Remote control server configuration / 远程控制服务器配置"""
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 8088
    websocket_enabled: bool = True
    status_broadcast_interval: float = 0.1  # seconds


@dataclass
class GUIConfig:
    """GUI configuration / GUI配置"""
    window_width: int = 1600
    window_height: int = 900
    theme: str = "light"  # "light" or "dark"
    default_language: str = "en"  # "zh" or "en"
    log_max_lines: int = 1000
    status_update_interval: float = 0.1  # seconds


@dataclass
class SystemConfig:
    """System configuration / 系统配置"""
    debug_mode: bool = False
    auto_connect: bool = False
    emergency_stop_timeout: float = 5.0
    heartbeat_interval: float = 1.0


@dataclass
class AppConfig:
    """Application configuration container / 应用程序配置容器"""
    lebai: LebaiConfig = field(default_factory=LebaiConfig)
    gantry: GantryConfig = field(default_factory=GantryConfig)
    dual_arm: DualArmConfig = field(default_factory=DualArmConfig)
    linker_hand: LinkerHandConfig = field(default_factory=LinkerHandConfig)
    dexhand: DexhandConfig = field(default_factory=DexhandConfig)
    gloves: GlovesConfig = field(default_factory=GlovesConfig)
    recording: RecordingConfig = field(default_factory=RecordingConfig)
    teleop: TeleopConfig = field(default_factory=TeleopConfig)
    wok: WokConfig = field(default_factory=WokConfig)
    gripper: GripperConfig = field(default_factory=GripperConfig)
    inventory: InventoryConfig = field(default_factory=InventoryConfig)
    camera: CameraConfig = field(default_factory=CameraConfig)
    remote_control: RemoteControlConfig = field(default_factory=RemoteControlConfig)
    gui: GUIConfig = field(default_factory=GUIConfig)
    system: SystemConfig = field(default_factory=SystemConfig)


class ConfigValidator:
    """
    Configuration validator.
    配置验证器。

    Validates configuration values and logs warnings for invalid values.
    验证配置值并为无效值记录警告。
    """

    # Validation patterns
    IP_PATTERN = re.compile(
        r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}'
        r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$|^localhost$'
    )

    # Valid baudrates
    VALID_BAUDRATES = {300, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600, 1000000}

    @classmethod
    def validate_ip(cls, ip: str, field_name: str) -> bool:
        """Validate IP address format / 验证IP地址格式"""
        if not cls.IP_PATTERN.match(ip):
            logger.warning(f"Invalid IP address for {field_name}: {ip}")
            return False
        return True

    @classmethod
    def validate_port(cls, port: int, field_name: str) -> bool:
        """Validate port number / 验证端口号"""
        if not (1 <= port <= 65535):
            logger.warning(f"Invalid port for {field_name}: {port} (must be 1-65535)")
            return False
        return True

    @classmethod
    def validate_speed_factor(cls, speed: float, field_name: str) -> bool:
        """Validate speed factor (0-1) / 验证速度因子"""
        if not (0.0 <= speed <= 1.0):
            logger.warning(f"Invalid speed factor for {field_name}: {speed} (must be 0-1)")
            return False
        return True

    @classmethod
    def validate_baudrate(cls, baudrate: int, field_name: str) -> bool:
        """Validate baudrate / 验证波特率"""
        if baudrate not in cls.VALID_BAUDRATES:
            logger.warning(f"Unusual baudrate for {field_name}: {baudrate}")
            # Not a hard error, just a warning
        return True

    @classmethod
    def validate_positive(cls, value: float, field_name: str) -> bool:
        """Validate positive number / 验证正数"""
        if value <= 0:
            logger.warning(f"Invalid value for {field_name}: {value} (must be positive)")
            return False
        return True

    @classmethod
    def validate_config(cls, config: AppConfig) -> List[str]:
        """
        Validate entire configuration.
        验证整个配置。

        Args:
            config: Application configuration

        Returns:
            List of validation warning messages
        """
        warnings = []

        # Validate Lebai config
        if not cls.validate_ip(config.lebai.ip, "lebai.ip"):
            warnings.append(f"Invalid lebai.ip: {config.lebai.ip}")
        if not cls.validate_port(config.lebai.port, "lebai.port"):
            warnings.append(f"Invalid lebai.port: {config.lebai.port}")
        if not cls.validate_speed_factor(config.lebai.speed_factor, "lebai.speed_factor"):
            warnings.append(f"Invalid lebai.speed_factor: {config.lebai.speed_factor}")

        # Validate Gantry config
        cls.validate_baudrate(config.gantry.baudrate, "gantry.baudrate")
        if not cls.validate_positive(config.gantry.timeout, "gantry.timeout"):
            warnings.append(f"Invalid gantry.timeout: {config.gantry.timeout}")

        # Validate Dual Arm config
        if not cls.validate_ip(config.dual_arm.ip, "dual_arm.ip"):
            warnings.append(f"Invalid dual_arm.ip: {config.dual_arm.ip}")
        if not cls.validate_port(config.dual_arm.port, "dual_arm.port"):
            warnings.append(f"Invalid dual_arm.port: {config.dual_arm.port}")
        if not cls.validate_speed_factor(config.dual_arm.speed_factor, "dual_arm.speed_factor"):
            warnings.append(f"Invalid dual_arm.speed_factor: {config.dual_arm.speed_factor}")

        # Validate Linker Hand config
        cls.validate_baudrate(config.linker_hand.baudrate, "linker_hand.baudrate")

        # Validate Wok config
        cls.validate_baudrate(config.wok.baudrate, "wok.baudrate")
        if not cls.validate_positive(config.wok.timeout, "wok.timeout"):
            warnings.append(f"Invalid wok.timeout: {config.wok.timeout}")

        # Validate Teleop config
        if not cls.validate_port(config.teleop.ros_port, "teleop.ros_port"):
            warnings.append(f"Invalid teleop.ros_port: {config.teleop.ros_port}")
        if not cls.validate_positive(config.teleop.update_rate, "teleop.update_rate"):
            warnings.append(f"Invalid teleop.update_rate: {config.teleop.update_rate}")

        # Validate Remote Control config
        if not cls.validate_port(config.remote_control.port, "remote_control.port"):
            warnings.append(f"Invalid remote_control.port: {config.remote_control.port}")
        if not cls.validate_positive(config.remote_control.status_broadcast_interval, "remote_control.status_broadcast_interval"):
            warnings.append(f"Invalid remote_control.status_broadcast_interval")

        # Validate GUI config
        if config.gui.window_width < 800:
            logger.warning(f"Small window width: {config.gui.window_width}")
        if config.gui.window_height < 600:
            logger.warning(f"Small window height: {config.gui.window_height}")
        if config.gui.default_language not in ['zh', 'en']:
            warnings.append(f"Invalid default_language: {config.gui.default_language}")

        # Validate System config
        if not cls.validate_positive(config.system.emergency_stop_timeout, "system.emergency_stop_timeout"):
            warnings.append(f"Invalid system.emergency_stop_timeout")
        if not cls.validate_positive(config.system.heartbeat_interval, "system.heartbeat_interval"):
            warnings.append(f"Invalid system.heartbeat_interval")

        if warnings:
            logger.warning(f"Configuration validation found {len(warnings)} issue(s)")
        else:
            logger.info("Configuration validation passed")

        return warnings


class Settings:
    """
    Settings manager with file persistence.
    带有文件持久化的设置管理器。

    Singleton pattern implementation.
    单例模式实现。
    """

    _instance: Optional['Settings'] = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._config_file = CONFIG_DIR / "hardware_config.json"
        self._config = AppConfig()
        self._load_config()
        self._initialized = True

    def _load_config(self):
        """Load configuration from file / 从文件加载配置"""
        if self._config_file.exists():
            try:
                with open(self._config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._apply_config_dict(data)
                logger.info(f"Configuration loaded from {self._config_file}")
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in config file: {e}")
            except Exception as e:
                logger.warning(f"Failed to load config: {e}")
        else:
            logger.info("No config file found, using defaults")

        # Validate configuration
        self._validation_warnings = ConfigValidator.validate_config(self._config)

    def _apply_config_dict(self, data: Dict[str, Any]):
        """Apply configuration dictionary / 应用配置字典"""
        if "lebai" in data:
            self._config.lebai = LebaiConfig(**data["lebai"])
        if "gantry" in data:
            self._config.gantry = GantryConfig(**data["gantry"])
        if "dual_arm" in data:
            self._config.dual_arm = DualArmConfig(**data["dual_arm"])
        if "linker_hand" in data:
            self._config.linker_hand = LinkerHandConfig(**data["linker_hand"])
        if "dexhand" in data:
            self._config.dexhand = DexhandConfig(**data["dexhand"])
        if "gloves" in data:
            self._config.gloves = GlovesConfig(**data["gloves"])
        if "recording" in data:
            self._config.recording = RecordingConfig(**data["recording"])
        if "teleop" in data:
            self._config.teleop = TeleopConfig(**data["teleop"])
        if "wok" in data:
            self._config.wok = WokConfig(**data["wok"])
        if "gripper" in data:
            self._config.gripper = GripperConfig(**data["gripper"])
        if "inventory" in data:
            self._config.inventory = InventoryConfig(**data["inventory"])
        if "camera" in data:
            self._config.camera = CameraConfig(**data["camera"])
        if "remote_control" in data:
            self._config.remote_control = RemoteControlConfig(**data["remote_control"])
        if "gui" in data:
            self._config.gui = GUIConfig(**data["gui"])
        if "system" in data:
            self._config.system = SystemConfig(**data["system"])

    def save_config(self, validate: bool = True):
        """
        Save configuration to file.
        保存配置到文件。

        Args:
            validate: Whether to validate before saving
        """
        # Validate before saving
        if validate:
            warnings = ConfigValidator.validate_config(self._config)
            if warnings:
                logger.warning(f"Saving config with {len(warnings)} validation warning(s)")

        os.makedirs(CONFIG_DIR, exist_ok=True)

        # Convert dataclasses to dict
        config_dict = {
            "lebai": asdict(self._config.lebai),
            "gantry": asdict(self._config.gantry),
            "dual_arm": asdict(self._config.dual_arm),
            "linker_hand": asdict(self._config.linker_hand),
            "dexhand": asdict(self._config.dexhand),
            "gloves": asdict(self._config.gloves),
            "recording": asdict(self._config.recording),
            "teleop": asdict(self._config.teleop),
            "wok": asdict(self._config.wok),
            "gripper": asdict(self._config.gripper),
            "inventory": asdict(self._config.inventory),
            "camera": asdict(self._config.camera),
            "remote_control": asdict(self._config.remote_control),
            "gui": asdict(self._config.gui),
            "system": asdict(self._config.system)
        }

        with open(self._config_file, 'w', encoding='utf-8') as f:
            json.dump(config_dict, f, indent=2, ensure_ascii=False)

        logger.info(f"Configuration saved to {self._config_file}")

    def get_validation_warnings(self) -> List[str]:
        """Get validation warnings from last load / 获取上次加载的验证警告"""
        return getattr(self, '_validation_warnings', [])

    def validate(self) -> List[str]:
        """Validate current configuration / 验证当前配置"""
        return ConfigValidator.validate_config(self._config)

    @property
    def lebai(self) -> LebaiConfig:
        return self._config.lebai

    @property
    def gantry(self) -> GantryConfig:
        return self._config.gantry

    @property
    def dual_arm(self) -> DualArmConfig:
        return self._config.dual_arm

    @property
    def linker_hand(self) -> LinkerHandConfig:
        return self._config.linker_hand

    @property
    def dexhand(self) -> DexhandConfig:
        return self._config.dexhand

    @property
    def gloves(self) -> GlovesConfig:
        return self._config.gloves

    @property
    def recording(self) -> RecordingConfig:
        return self._config.recording

    @property
    def teleop(self) -> TeleopConfig:
        return self._config.teleop

    @property
    def wok(self) -> WokConfig:
        return self._config.wok

    @property
    def gripper(self) -> GripperConfig:
        return self._config.gripper

    @property
    def inventory(self) -> InventoryConfig:
        return self._config.inventory

    @property
    def camera(self) -> CameraConfig:
        return self._config.camera

    @property
    def remote_control(self) -> RemoteControlConfig:
        return self._config.remote_control

    @property
    def gui(self) -> GUIConfig:
        return self._config.gui

    @property
    def system(self) -> SystemConfig:
        return self._config.system

    def get_all(self) -> AppConfig:
        """Get all configuration / 获取所有配置"""
        return self._config

    def update(self, section: str, **kwargs):
        """
        Update configuration section.
        更新配置部分。

        Args:
            section: Configuration section name
            **kwargs: Key-value pairs to update
        """
        if hasattr(self._config, section):
            config_obj = getattr(self._config, section)
            for key, value in kwargs.items():
                if hasattr(config_obj, key):
                    setattr(config_obj, key, value)
            self.save_config()


# Global settings instance / 全局设置实例
def get_settings() -> Settings:
    """Get the global settings instance / 获取全局设置实例"""
    return Settings()
