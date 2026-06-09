"""
Dual Arm Hardware Package
双臂硬件包

Controls the dual-arm robot system and L6 linker hands.
控制双臂机器人系统和L6机械手。
"""

from .dual_arm_controller import DualArmController, ArmSide
from .linker_hand_controller import LinkerHandController, HandSide, HandGesture
from .dual_arm_widget import DualArmWidget
from .linker_hand_widget import LinkerHandWidget
from .poses import DualArmPoseManager, DualArmPose
from .joint_control_widget import JointControlWidget, DualJointControlWidget, JointLimits
from .pose_control_widget import PoseControlWidget, PoseListWidget, RecordedPose, Step
from .state_display_widget import ArmStateWidget, DualArmStateWidget, RobotInfoWidget
from .kinematics import (
    CartesianPose, JointState, WorkspaceValidator, KinematicsHelper,
    compute_minimum_jerk_trajectory, compute_trajectory_duration
)

__all__ = [
    'DualArmController',
    'ArmSide',
    'LinkerHandController',
    'HandSide',
    'HandGesture',
    'DualArmWidget',
    'LinkerHandWidget',
    'DualArmPoseManager',
    'DualArmPose',
    # New joint control widgets
    'JointControlWidget',
    'DualJointControlWidget',
    'JointLimits',
    # New pose control widgets
    'PoseControlWidget',
    'PoseListWidget',
    'RecordedPose',
    'Step',
    # New state display widgets
    'ArmStateWidget',
    'DualArmStateWidget',
    'RobotInfoWidget',
    # Kinematics utilities
    'CartesianPose',
    'JointState',
    'WorkspaceValidator',
    'KinematicsHelper',
    'compute_minimum_jerk_trajectory',
    'compute_trajectory_duration',
]
