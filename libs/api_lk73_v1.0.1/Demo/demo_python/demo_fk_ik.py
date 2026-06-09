#!/usr/bin/env python3
"""
运动学计算测试 - 对应C语言的test_forward_kinematics和test_inverse_kinematics
"""

import math
import time
from lbot.lbot_robot import LbotRobot, LbotArm, LbotPosition, LbotEuler


def test_forward_kinematics(robot):
    """测试正向运动学"""
    print("\n=== 测试正向运动学 ===")
    
    # 测试不同的关节角度配置
    test_joints = [
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],        # 零位
        [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],        # 随机角度1
        [-0.1, -0.2, -0.3, -0.4, -0.5, -0.6, -0.7], # 随机角度2
        [0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],        # 仅第一个关节转动
        [0.0, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0]         # 仅第二个关节转动
    ]
    
    for i, joints in enumerate(test_joints):
        print(f"\n--- 测试案例 {i + 1} ---")
        print(f"输入关节: [{', '.join(f'{j:.3f}' for j in joints)}]")
        
        # 测试左臂
        left_result = robot.compute_forward_kinematics(LbotArm.LEFT_ARM, joints)
        if left_result:
            position, euler = left_result
            print("左臂正向运动学结果:")
            print(f"  位置: ({position.x:.3f}, {position.y:.3f}, {position.z:.3f})")
            print(f"  欧拉角: ({euler.x:.3f}, {euler.y:.3f}, {euler.z:.3f})")
        else:
            print(f"左臂正向运动学失败: {robot.get_last_error()}")
        
        # 测试右臂
        right_result = robot.compute_forward_kinematics(LbotArm.RIGHT_ARM, joints)
        if right_result:
            position, euler = right_result
            print("右臂正向运动学结果:")
            print(f"  位置: ({position.x:.3f}, {position.y:.3f}, {position.z:.3f})")
            print(f"  欧拉角: ({euler.x:.3f}, {euler.y:.3f}, {euler.z:.3f})")
        else:
            print(f"右臂正向运动学失败: {robot.get_last_error()}")
        
        time.sleep(1)  # 短暂延迟


def test_inverse_kinematics(robot):
    """测试逆向运动学"""
    print("\n=== 测试逆向运动学 ===")
    
    # 测试不同的目标位置和姿态
    test_cases = [
        {
            'position': LbotPosition(0.3, 0.2, -0.3),
            'euler': LbotEuler(0.0, -math.pi/2, 0.0),
            'initial_joints': [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        },
        {
            'position': LbotPosition(0.3, -0.2, -0.3),
            'euler': LbotEuler(0.0, -math.pi/2, 0.0),
            'initial_joints': [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        },
        {
            'position': LbotPosition(0.2, 0.1, 0.1),
            'euler': LbotEuler(0.0, 0.0, 0.0),
            'initial_joints': [0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1]
        }
    ]
    
    for i, case in enumerate(test_cases):
        print(f"\n--- 测试案例 {i + 1} ---")
        print(f"目标位置: ({case['position'].x:.3f}, {case['position'].y:.3f}, {case['position'].z:.3f})")
        print(f"目标欧拉角: ({case['euler'].x:.3f}, {case['euler'].y:.3f}, {case['euler'].z:.3f})")
        print(f"初始关节: [{', '.join(f'{j:.3f}' for j in case['initial_joints'])}]")
        
        # 测试左臂逆向运动学
        left_result = robot.compute_inverse_kinematics(
            LbotArm.LEFT_ARM, 
            case['position'], 
            case['euler'], 
            case['initial_joints']
        )
        
        if left_result:
            print(f"左臂逆向运动学结果:")
            print(f"  求解关节: [{', '.join(f'{j:.3f}' for j in left_result)}]")
        else:
            print(f"左臂逆向运动学失败: {robot.get_last_error()}")
        
        # 测试右臂逆向运动学
        right_result = robot.compute_inverse_kinematics(
            LbotArm.RIGHT_ARM, 
            case['position'], 
            case['euler'], 
            case['initial_joints']
        )
        
        if right_result:
            print(f"右臂逆向运动学结果:")
            print(f"  求解关节: [{', '.join(f'{j:.3f}' for j in right_result)}]")
        else:
            print(f"右臂逆向运动学失败: {robot.get_last_error()}")
        
        time.sleep(1)


if __name__ == "__main__":
    # 使用上下文管理器自动处理连接
    with LbotRobot('192.168.10.21') as robot:
        test_forward_kinematics(robot)
        test_inverse_kinematics(robot)
    
    print("运动学测试完成")