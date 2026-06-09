"""
Kinematics Module
运动学模块

Forward and inverse kinematics utilities for dual-arm robot.
双臂机器人的正逆运动学工具。
"""

import math
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass


@dataclass
class CartesianPose:
    """Cartesian pose (position + orientation) / 笛卡尔位姿"""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    roll: float = 0.0   # Rotation around X axis
    pitch: float = 0.0  # Rotation around Y axis
    yaw: float = 0.0    # Rotation around Z axis

    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary / 转换为字典"""
        return {
            "x": self.x, "y": self.y, "z": self.z,
            "roll": self.roll, "pitch": self.pitch, "yaw": self.yaw
        }

    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> 'CartesianPose':
        """Create from dictionary / 从字典创建"""
        return cls(
            x=data.get("x", 0.0), y=data.get("y", 0.0), z=data.get("z", 0.0),
            roll=data.get("roll", 0.0), pitch=data.get("pitch", 0.0), yaw=data.get("yaw", 0.0)
        )

    def distance_to(self, other: 'CartesianPose') -> float:
        """Calculate Euclidean distance to another pose / 计算到另一个位姿的欧几里得距离"""
        return math.sqrt(
            (self.x - other.x) ** 2 +
            (self.y - other.y) ** 2 +
            (self.z - other.z) ** 2
        )


@dataclass
class JointState:
    """Joint state for 7-DOF arm / 7自由度手臂的关节状态"""
    joints: List[float]  # 7 joint angles in degrees

    def __post_init__(self):
        if len(self.joints) != 7:
            # Pad or truncate to 7 joints
            self.joints = (self.joints + [0.0] * 7)[:7]

    def to_radians(self) -> List[float]:
        """Convert to radians / 转换为弧度"""
        return [math.radians(j) for j in self.joints]

    def from_radians(self, radians: List[float]):
        """Set from radians / 从弧度设置"""
        self.joints = [math.degrees(r) for r in radians]


class WorkspaceValidator:
    """
    Workspace validator for robot arms.
    机器人手臂的工作空间验证器。
    """

    # Default workspace limits (can be customized)
    DEFAULT_LIMITS = {
        "x_min": -1000, "x_max": 1000,
        "y_min": -1000, "y_max": 1000,
        "z_min": 0, "z_max": 1500,
    }

    # Default joint limits for 7-DOF arm
    DEFAULT_JOINT_LIMITS = [
        (-170, 170),  # Joint 1
        (-120, 120),  # Joint 2
        (-170, 170),  # Joint 3
        (-120, 120),  # Joint 4
        (-170, 170),  # Joint 5
        (-120, 120),  # Joint 6
        (-360, 360),  # Joint 7
    ]

    def __init__(self, workspace_limits: Dict[str, float] = None,
                 joint_limits: List[Tuple[float, float]] = None):
        """
        Initialize workspace validator.
        初始化工作空间验证器。

        Args:
            workspace_limits: Cartesian workspace limits
            joint_limits: List of (min, max) for each joint
        """
        self._workspace_limits = workspace_limits or self.DEFAULT_LIMITS
        self._joint_limits = joint_limits or self.DEFAULT_JOINT_LIMITS

    def is_pose_valid(self, pose: CartesianPose) -> Tuple[bool, str]:
        """
        Check if Cartesian pose is within workspace.
        检查笛卡尔位姿是否在工作空间内。

        Returns:
            (is_valid, error_message)
        """
        limits = self._workspace_limits

        if not (limits["x_min"] <= pose.x <= limits["x_max"]):
            return False, f"X out of range [{limits['x_min']}, {limits['x_max']}]"

        if not (limits["y_min"] <= pose.y <= limits["y_max"]):
            return False, f"Y out of range [{limits['y_min']}, {limits['y_max']}]"

        if not (limits["z_min"] <= pose.z <= limits["z_max"]):
            return False, f"Z out of range [{limits['z_min']}, {limits['z_max']}]"

        return True, ""

    def is_joints_valid(self, joints: List[float]) -> Tuple[bool, str]:
        """
        Check if joint angles are within limits.
        检查关节角度是否在限位内。

        Returns:
            (is_valid, error_message)
        """
        for i, (angle, (min_val, max_val)) in enumerate(zip(joints, self._joint_limits)):
            if not (min_val <= angle <= max_val):
                return False, f"Joint {i+1} out of range [{min_val}, {max_val}]"

        return True, ""

    def clamp_joints(self, joints: List[float]) -> List[float]:
        """
        Clamp joint angles to valid limits.
        将关节角度限制在有效限位内。

        Args:
            joints: List of joint angles

        Returns:
            Clamped joint angles
        """
        clamped = []
        for angle, (min_val, max_val) in zip(joints, self._joint_limits):
            clamped.append(max(min_val, min(max_val, angle)))
        return clamped


class KinematicsHelper:
    """
    Kinematics helper utilities.
    运动学辅助工具。

    Note: Actual FK/IK requires robot-specific DH parameters.
    This provides utility functions and interfaces for kinematics.
    """

    def __init__(self):
        """Initialize kinematics helper / 初始化运动学辅助"""
        self._validator = WorkspaceValidator()

    @staticmethod
    def interpolate_joints(start: List[float], end: List[float],
                           num_points: int) -> List[List[float]]:
        """
        Linear interpolation between joint configurations.
        关节配置之间的线性插值。

        Args:
            start: Starting joint configuration
            end: Ending joint configuration
            num_points: Number of interpolation points

        Returns:
            List of interpolated joint configurations
        """
        if num_points < 2:
            return [end]

        trajectory = []
        for i in range(num_points):
            t = i / (num_points - 1)
            point = [
                start[j] + t * (end[j] - start[j])
                for j in range(len(start))
            ]
            trajectory.append(point)

        return trajectory

    @staticmethod
    def interpolate_cartesian(start: CartesianPose, end: CartesianPose,
                              num_points: int) -> List[CartesianPose]:
        """
        Linear interpolation between Cartesian poses.
        笛卡尔位姿之间的线性插值。

        Args:
            start: Starting pose
            end: Ending pose
            num_points: Number of interpolation points

        Returns:
            List of interpolated poses
        """
        if num_points < 2:
            return [end]

        trajectory = []
        for i in range(num_points):
            t = i / (num_points - 1)
            pose = CartesianPose(
                x=start.x + t * (end.x - start.x),
                y=start.y + t * (end.y - start.y),
                z=start.z + t * (end.z - start.z),
                roll=start.roll + t * (end.roll - start.roll),
                pitch=start.pitch + t * (end.pitch - start.pitch),
                yaw=start.yaw + t * (end.yaw - start.yaw),
            )
            trajectory.append(pose)

        return trajectory

    def validate_pose(self, pose: CartesianPose) -> Tuple[bool, str]:
        """Validate Cartesian pose / 验证笛卡尔位姿"""
        return self._validator.is_pose_valid(pose)

    def validate_joints(self, joints: List[float]) -> Tuple[bool, str]:
        """Validate joint configuration / 验证关节配置"""
        return self._validator.is_joints_valid(joints)

    def clamp_joints(self, joints: List[float]) -> List[float]:
        """Clamp joints to valid range / 将关节限制在有效范围内"""
        return self._validator.clamp_joints(joints)

    @staticmethod
    def joints_to_dict(joints: List[float]) -> Dict[str, float]:
        """Convert joint list to named dictionary / 将关节列表转换为命名字典"""
        names = ['j1', 'j2', 'j3', 'j4', 'j5', 'j6', 'j7']
        return {name: angle for name, angle in zip(names, joints)}

    @staticmethod
    def dict_to_joints(joint_dict: Dict[str, float]) -> List[float]:
        """Convert named dictionary to joint list / 将命名字典转换为关节列表"""
        names = ['j1', 'j2', 'j3', 'j4', 'j5', 'j6', 'j7']
        return [joint_dict.get(name, 0.0) for name in names]


def compute_minimum_jerk_trajectory(start: List[float], end: List[float],
                                    duration: float, dt: float = 0.01) -> List[List[float]]:
    """
    Compute minimum jerk trajectory between two configurations.
    计算两个配置之间的最小急动度轨迹。

    Minimum jerk trajectory provides smooth motion with zero velocity
    and acceleration at endpoints.

    Args:
        start: Starting configuration
        end: Ending configuration
        duration: Trajectory duration in seconds
        dt: Time step

    Returns:
        List of configurations along trajectory
    """
    num_points = int(duration / dt) + 1
    trajectory = []

    for i in range(num_points):
        t = i * dt
        tau = t / duration

        # Minimum jerk polynomial: 10*tau^3 - 15*tau^4 + 6*tau^5
        s = 10 * tau ** 3 - 15 * tau ** 4 + 6 * tau ** 5

        point = [
            start[j] + s * (end[j] - start[j])
            for j in range(len(start))
        ]
        trajectory.append(point)

    return trajectory


def compute_trajectory_duration(distance: float, max_velocity: float,
                                max_acceleration: float) -> float:
    """
    Compute trajectory duration for trapezoidal velocity profile.
    计算梯形速度曲线的轨迹持续时间。

    Args:
        distance: Total distance to travel
        max_velocity: Maximum velocity
        max_acceleration: Maximum acceleration

    Returns:
        Trajectory duration in seconds
    """
    # Time to accelerate/decelerate
    t_acc = max_velocity / max_acceleration

    # Distance during acceleration phase
    d_acc = 0.5 * max_acceleration * t_acc ** 2

    if 2 * d_acc >= distance:
        # Triangular profile (never reaches max velocity)
        return 2 * math.sqrt(distance / max_acceleration)
    else:
        # Trapezoidal profile
        d_cruise = distance - 2 * d_acc
        t_cruise = d_cruise / max_velocity
        return 2 * t_acc + t_cruise
