"""
Hand Configuration Module
灵巧手配置模块

Defines hand type configurations (L6/L10) with joint names, limits, and presets.
定义灵巧手类型配置（L6/L10），包括关节名称、限位和预设动作。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class HandConfig:
    """Hand configuration dataclass / 手部配置数据类"""
    joint_names: List[str] = field(default_factory=list)
    joint_names_en: Optional[List[str]] = None
    init_pos: List[int] = field(default_factory=list)
    preset_actions: Optional[Dict[str, List[int]]] = None
    num_joints: int = 6


# Hand configurations from LinkerHand SDK
HAND_CONFIGS: Dict[str, HandConfig] = {
    "L25": HandConfig(
        joint_names=["大拇指根部", "食指根部", "中指根部", "无名指根部", "小拇指根部",
                     "大拇指侧摆", "食指侧摆", "中指侧摆", "无名指侧摆", "小拇指侧摆",
                     "大拇指横滚", "预留", "预留", "预留", "预留", "大拇指中部", "食指中部",
                     "中指中部", "无名指中部", "小拇指中部", "大拇指指尖", "食指指尖",
                     "中指指尖", "无名指指尖", "小拇指指尖"],
        init_pos=[255] * 25,
        preset_actions={
            "握拳": [0] * 25,
            "张开": [255] * 25,
            "OK": [255, 255, 255, 255, 255, 255, 255, 255, 255, 255,
                   255, 255, 255, 255, 255, 255, 0, 0, 255, 255,
                   0, 0, 0, 255, 255]
        },
        num_joints=25
    ),
    "L21": HandConfig(
        joint_names=["大拇指根部", "食指根部", "中指根部", "无名指根部", "小拇指根部",
                     "大拇指侧摆", "食指侧摆", "中指侧摆", "无名指侧摆", "小拇指侧摆",
                     "大拇指横滚", "预留", "预留", "预留", "预留", "大拇指中部", "预留",
                     "预留", "预留", "预留", "大拇指指尖", "食指指尖", "中指指尖",
                     "无名指指尖", "小拇指指尖"],
        init_pos=[255] * 25,
        num_joints=25
    ),
    "L20": HandConfig(
        joint_names=["拇指根部", "食指根部", "中指根部", "无名指根部", "小指根部",
                     "拇指侧摆", "食指侧摆", "中指侧摆", "无名指侧摆", "小指侧摆",
                     "拇指横摆", "预留", "预留", "预留", "预留", "拇指尖部", "食指末端",
                     "中指末端", "无名指末端", "小指末端"],
        init_pos=[255, 255, 255, 255, 255, 255, 10, 100, 180, 240, 245, 255, 255, 255, 255, 255, 255, 255, 255, 255],
        preset_actions={
            "握拳": [40, 0, 0, 0, 0, 131, 10, 100, 180, 240, 19, 255, 255, 255, 255, 135, 0, 0, 0, 0],
            "张开": [255, 255, 255, 255, 255, 255, 10, 100, 180, 240, 245, 255, 255, 255, 255, 255, 255, 255, 255, 255],
            "OK": [191, 95, 255, 255, 255, 136, 107, 100, 180, 240, 72, 255, 255, 255, 255, 116, 99, 255, 255, 255],
            "点赞": [255, 0, 0, 0, 0, 127, 10, 100, 180, 240, 255, 255, 255, 255, 255, 255, 0, 0, 0, 0],
        },
        num_joints=20
    ),
    "G20": HandConfig(
        joint_names=["拇指根部", "食指根部", "中指根部", "无名指根部", "小指根部",
                     "拇指侧摆", "食指侧摆", "中指侧摆", "无名指侧摆", "小指侧摆",
                     "拇指横摆", "预留", "预留", "预留", "预留", "拇指尖部", "食指末端",
                     "中指末端", "无名指末端", "小指末端"],
        init_pos=[255, 255, 255, 255, 255, 255, 193, 148, 105, 42, 245, 255, 255, 255, 255, 255, 255, 255, 255, 255],
        preset_actions={
            "点赞": [255, 0, 0, 0, 0, 255, 162, 162, 144, 100, 210, 255, 255, 255, 255, 255, 0, 0, 0, 0],
            "握拳": [96, 0, 0, 0, 0, 0, 193, 158, 128, 91, 132, 255, 255, 255, 255, 144, 0, 0, 0, 0],
            "张开": [255, 255, 255, 255, 255, 255, 193, 148, 105, 42, 245, 255, 255, 255, 255, 255, 255, 255, 255, 255],
            "OK": [148, 110, 255, 255, 255, 44, 164, 100, 114, 127, 178, 255, 255, 255, 255, 94, 71, 255, 255, 255],
        },
        num_joints=20
    ),
    "L10": HandConfig(
        joint_names_en=["thumb_cmc_pitch", "thumb_cmc_roll", "index_mcp_pitch", "middle_mcp_pitch",
                        "ring_mcp_pitch", "pinky_mcp_pitch", "index_mcp_roll", "ring_mcp_roll",
                        "pinky_mcp_roll", "thumb_cmc_yaw"],
        joint_names=["拇指根部", "拇指侧摆", "食指根部", "中指根部", "无名指根部",
                     "小指根部", "食指侧摆", "无名指侧摆", "小指侧摆", "拇指旋转"],
        init_pos=[255] * 10,
        preset_actions={
            "张开": [255, 255, 255, 255, 255, 255, 128, 67, 89, 255],
            "点赞": [255, 255, 0, 0, 0, 0, 128, 67, 89, 255],
            "握拳": [90, 0, 0, 0, 0, 0, 128, 67, 89, 197],
            "壹": [55, 0, 255, 0, 0, 0, 128, 67, 89, 124],
            "贰": [55, 0, 255, 255, 0, 0, 128, 67, 89, 124],
            "叁": [116, 255, 255, 255, 255, 0, 128, 67, 89, 255],
            "肆": [0, 0, 255, 255, 255, 255, 128, 67, 89, 255],
            "伍": [255, 255, 255, 255, 255, 255, 128, 67, 89, 255],
            "OK": [84, 39, 122, 255, 255, 255, 128, 67, 89, 255],
        },
        num_joints=10
    ),
    "L7": HandConfig(
        joint_names=["大拇指弯曲", "大拇指横摆", "食指弯曲", "中指弯曲", "无名指弯曲",
                     "小拇指弯曲", "拇指旋转"],
        init_pos=[250] * 7,
        preset_actions={
            "张开": [255, 111, 250, 250, 250, 250, 55],
            "点赞": [255, 255, 0, 0, 0, 0, 255],
            "握拳": [65, 0, 0, 0, 0, 0, 93],
            "壹": [66, 0, 255, 0, 0, 0, 93],
            "贰": [0, 0, 255, 255, 0, 0, 255],
            "OK": [99, 15, 146, 250, 250, 250, 206],
        },
        num_joints=7
    ),
    "O6": HandConfig(
        joint_names_en=["thumb_cmc_pitch", "thumb_cmc_yaw", "index_mcp_pitch",
                        "middle_mcp_pitch", "pinky_mcp_pitch", "ring_mcp_pitch"],
        joint_names=["大拇指弯曲", "大拇指横摆", "食指弯曲", "中指弯曲", "无名指弯曲", "小拇指弯曲"],
        init_pos=[250] * 6,
        preset_actions={
            "张开": [250, 250, 250, 250, 250, 250],
            "壹": [125, 18, 255, 0, 0, 0],
            "贰": [92, 87, 255, 255, 0, 0],
            "OK": [96, 100, 118, 250, 250, 250],
            "点赞": [250, 79, 0, 0, 0, 0],
            "握拳": [102, 18, 0, 0, 0, 0],
        },
        num_joints=6
    ),
    "L6": HandConfig(
        joint_names_en=["thumb_cmc_pitch", "thumb_cmc_yaw", "index_mcp_pitch",
                        "middle_mcp_pitch", "pinky_mcp_pitch", "ring_mcp_pitch"],
        joint_names=["大拇指弯曲", "大拇指横摆", "食指弯曲", "中指弯曲", "无名指弯曲", "小拇指弯曲"],
        init_pos=[250] * 6,
        preset_actions={
            "张开": [250, 250, 250, 250, 250, 250],
            "壹": [0, 18, 255, 0, 0, 0],
            "贰": [0, 39, 255, 255, 0, 0],
            "OK": [74, 13, 153, 255, 255, 255],
            "点赞": [255, 255, 0, 0, 0, 0],
            "握拳": [79, 11, 0, 0, 0, 0],
        },
        num_joints=6
    ),
}

# English finger names for L6 (commonly used)
L6_FINGER_NAMES_EN = ["Thumb Bend", "Thumb Rotate", "Index", "Middle", "Ring", "Pinky"]

# English finger names for L10
L10_FINGER_NAMES_EN = ["Thumb Bend", "Thumb Rotate", "Index Bend", "Index Rotate",
                       "Middle Bend", "Middle Rotate", "Ring Bend", "Ring Rotate",
                       "Pinky Bend", "Pinky Rotate"]

# Default positions for common actions
DEFAULT_POSITIONS = {
    "open": 255,
    "close": 0,
    "half": 128,
    "grab": 50,
}


def get_hand_config(hand_type: str) -> Optional[HandConfig]:
    """
    Get hand configuration by type.
    根据类型获取手部配置。

    Args:
        hand_type: Hand type string (e.g., "L6", "L10")

    Returns:
        HandConfig if found, None otherwise
    """
    return HAND_CONFIGS.get(hand_type.upper())


def get_finger_names(hand_type: str, language: str = "en") -> List[str]:
    """
    Get finger names for a hand type.
    获取指定手型的手指名称。

    Args:
        hand_type: Hand type string (e.g., "L6", "L10")
        language: "en" for English, "zh" for Chinese

    Returns:
        List of finger names
    """
    config = get_hand_config(hand_type)
    if not config:
        return []

    if language == "en" and config.joint_names_en:
        return list(config.joint_names_en)
    return list(config.joint_names)


def get_preset_action(hand_type: str, action_name: str) -> Optional[List[int]]:
    """
    Get preset action positions for a hand type.
    获取指定手型的预设动作位置。

    Args:
        hand_type: Hand type string (e.g., "L6", "L10")
        action_name: Action name (e.g., "张开", "握拳")

    Returns:
        List of joint positions if found, None otherwise
    """
    config = get_hand_config(hand_type)
    if not config or not config.preset_actions:
        return None
    return config.preset_actions.get(action_name)
