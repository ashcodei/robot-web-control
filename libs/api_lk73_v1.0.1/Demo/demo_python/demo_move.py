#!/usr/bin/env python3
"""
    @brief : 测试API,机械臂运动控制接口测试
    1. 关节角度运动
    2. 笛卡尔空间点到点运动
    3. 直线运动
    4. 关节角度跟随运动
"""

import math
import time
from lbot.lbot_robot import LbotRobot, LbotArm, LbotPosition, LbotEuler


def state_callback(state):
    """状态回调函数"""
    print(f"收到状态更新 - 时间戳: {state.timestamp}")
    print(f"左臂位置: ({state.left_arm.end_effector_position.x:.4f}, {state.left_arm.end_effector_position.y:.4f}, {state.left_arm.end_effector_position.z:.4f})")
    print(f"右臂位置: ({state.right_arm.end_effector_position.x:.4f}, {state.right_arm.end_effector_position.y:.4f}, {state.right_arm.end_effector_position.z:.4f})")


def error_callback(error_code, error_msg):
    """错误回调函数"""
    print(f"错误 {error_code}: {error_msg}")


def print_arm_state(robot):
    """打印机械臂状态"""
    state = robot.get_state()
    if state:
        print("=== 当前机械臂状态 ===")
        print(f"时间戳: {state.timestamp}")
        
        print("左臂:")
        left_joints = state.left_arm.get_joints_list()
        print(f"  关节: [{', '.join(f'{j:.3f}' for j in left_joints)}]")
        print(f"  位置: ({state.left_arm.end_effector_position.x:.3f}, {state.left_arm.end_effector_position.y:.3f}, {state.left_arm.end_effector_position.z:.3f})")
        
        print("右臂:")
        right_joints = state.right_arm.get_joints_list()
        print(f"  关节: [{', '.join(f'{j:.3f}' for j in right_joints)}]")
        print(f"  位置: ({state.right_arm.end_effector_position.x:.3f}, {state.right_arm.end_effector_position.y:.3f}, {state.right_arm.end_effector_position.z:.3f})")
        print("=========================")


def test_movej(robot):
    """测试关节运动"""
    print("\n=== 测试关节运动 ===")
    
    controller_info = robot.get_controller_info()
    if controller_info:
        print(f"机器人型号: {controller_info['robot_model']}")
        print(f"控制器版本: {controller_info['controller_version']}")
    robot_model = controller_info['robot_model']
    if(robot_model == "LKRS73-I2"):
        # 定义目标关节位置
        left_joints = [1.57, -1.57, -1.57, 1.57, -1.57, -1.57, -1.57]
        right_joints = [-1.57, 1.57, 1.57, -1.57, 1.57, 1.57, 1.57]
        # 执行左臂运动
        move_result = robot.move_to_joint_target(LbotArm.LEFT_ARM, left_joints, 0.5, 1.0, False)
        print(f"左臂运动命令结果: {'成功' if move_result else '失败'}")
        if not move_result:
            print(f"运动命令失败: {robot.get_last_error()}")
        # 执行右臂运动
        move_result = robot.move_to_joint_target(LbotArm.RIGHT_ARM, right_joints, 0.5, 1.0, True)
        print(f"右臂运动命令结果: {'成功' if move_result else '失败'}")
        if not move_result:
            print(f"右臂运动命令失败: {robot.get_last_error()}")
   
    if(robot_model == "LKLS73-O1" or robot_model == "LKLS73-O2"):
        # 定义目标关节位置
        left_joints = [-1.57, 1.57, 1.57, 1.57, 1.57, 1.57, 1.57]
        right_joints = [1.57, -1.57, -1.57, 1.57, -1.57, -1.57, -1.57]
        # 执行左臂运动
        move_result = robot.move_to_joint_target(LbotArm.LEFT_ARM, left_joints, 0.5, 1.0, False)
        print(f"左臂运动命令结果: {'成功' if move_result else '失败'}")
        if not move_result:
            print(f"运动命令失败: {robot.get_last_error()}")
        # 执行右臂运动
        move_result = robot.move_to_joint_target(LbotArm.RIGHT_ARM, right_joints, 0.5, 1.0, True)
        print(f"右臂运动命令结果: {'成功' if move_result else '失败'}")
        if not move_result:
            print(f"右臂运动命令失败: {robot.get_last_error()}")
    # 获取运动后状态
    print_arm_state(robot)
    
    # 回到零位
    home_joints = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    move_result = robot.move_to_joint_target(LbotArm.LEFT_ARM, home_joints, 0.5, 1.0, False)
    if not move_result:
        print(f"回到零位命令失败: {robot.get_last_error()}")
    
    move_result = robot.move_to_joint_target(LbotArm.RIGHT_ARM, home_joints, 0.5, 1.0, True)
    if not move_result:
        print(f"右臂回到零位命令失败: {robot.get_last_error()}")
    
    print_arm_state(robot)


def test_move_pose(robot):
    """测试笛卡尔空间运动"""
    print("\n=== 测试笛卡尔空间点到点运动 ===")
    
    # 定义目标位置和姿态
    l_target_position = LbotPosition(0.3, 0.3, -0.3)
    l_target_euler = LbotEuler(0.0, -math.pi/2, 0.0)
    
    r_target_position = LbotPosition(0.3, -0.3, -0.3)
    r_target_euler = LbotEuler(0.0, -math.pi/2, 0.0)
    
    # 执行点到点运动（非阻塞模式）
    success = robot.move_to_pose_target(LbotArm.LEFT_ARM, l_target_position, l_target_euler, 0.5, False)
    if not success:
        print(f"左臂点到点运动失败: {robot.get_last_error()}")
        return False
    print("左臂点到点运动命令发送成功")
    
    success = robot.move_to_pose_target(LbotArm.RIGHT_ARM, r_target_position, r_target_euler, 0.5, True)
    if not success:
        print(f"右臂点到点运动失败: {robot.get_last_error()}")
        return False
    print("右臂点到点运动命令发送成功")
    
    # 等待运动完成
    robot.wait_for_motion_completion()
    
    # 获取当前状态验证
    print_arm_state(robot)
    
    print("\n=== 测试直线运动 ===")
    
    # 左臂直线运动测试
    print("测试左臂直线运动...")
    linear_target = LbotPosition(0.4, 0.3, -0.3)  # x+0.1
    
    success = robot.linear_move_to_pose(LbotArm.LEFT_ARM, linear_target, l_target_euler, 0.5, True)
    if not success:
        print(f"左臂直线运动失败: {robot.get_last_error()}")
    else:
        print("左臂直线运动命令1发送成功")
    
    linear_target = LbotPosition(0.2, 0.3, -0.3)  # x-0.1
    success = robot.linear_move_to_pose(LbotArm.LEFT_ARM, linear_target, l_target_euler, 0.5, True)
    if not success:
        print(f"左臂直线运动失败: {robot.get_last_error()}")
    else:
        print("左臂直线运动命令2发送成功")
    
    # 右臂直线运动测试
    print("测试右臂直线运动...")
    linear_target = LbotPosition(0.4, -0.3, -0.3)  # x+0.1
    
    success = robot.linear_move_to_pose(LbotArm.RIGHT_ARM, linear_target, r_target_euler, 0.5, True)
    if not success:
        print(f"右臂直线运动失败: {robot.get_last_error()}")
    else:
        print("右臂直线运动命令1发送成功")
    
    linear_target = LbotPosition(0.2, -0.3, -0.3)  # x-0.1
    success = robot.linear_move_to_pose(LbotArm.RIGHT_ARM, linear_target, r_target_euler, 0.5, True)
    if not success:
        print(f"右臂直线运动失败: {robot.get_last_error()}")
    else:
        print("右臂直线运动命令2发送成功")
    
    time.sleep(2)
    return True
def test_joint_follow(robot):
    """测试关节跟踪运动"""
    print("\n=== 测试关节跟踪运动 ===")
    left_joints = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    right_joints = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    robot.move_to_joint_target(LbotArm.LEFT_ARM, left_joints, 0.5, 1.0, False)
    robot.move_to_joint_target(LbotArm.RIGHT_ARM, right_joints, 0.5, 1.0, True)
    time.sleep(2)
    for i in range(100):
        left_joints[0] += 0.01
        right_joints[0] += 0.01
        robot.joint_follow(LbotArm.LEFT_ARM, left_joints)
        robot.joint_follow(LbotArm.RIGHT_ARM, right_joints)
        time.sleep(0.01)

    for i in range(100):
        left_joints[0] -= 0.01
        right_joints[0] -= 0.01
        robot.joint_follow(LbotArm.LEFT_ARM, left_joints)
        robot.joint_follow(LbotArm.RIGHT_ARM, right_joints)
        time.sleep(0.01)



if __name__ == "__main__":
    robot = LbotRobot('192.168.10.21')
    
    try:
        if robot.connect():
            # 添加状态回调
            robot.add_state_callback(state_callback)
            robot.add_error_callback(error_callback)
            
            # 获取初始状态
            print("获取初始状态...")
            print_arm_state(robot)
            
            # 执行测试
            test_movej(robot)
            test_move_pose(robot)
            test_joint_follow(robot)
            
    finally:
        robot.disconnect()
    
    print("运动控制测试完成")