#!/usr/bin/env python3
"""
LBOT API Comprehensive Test - Python Version
测试L6和L10手的控制功能
"""

import time
from lbot.lbot_robot import LbotRobot, LbotArm, LbotPosition, LbotEuler


def test_l6_hand(robot):
    """测试L6手功能"""
    print("\n=== Testing L6 Hand ===")
    
    try:
        # 设置位置到200
        left_position = [200, 200, 200, 200, 200, 200]
        success = robot.l6_set_position(LbotArm.LEFT_ARM, left_position)
        print(f"Left L6 Set Position: {'SUCCESS' if success else 'FAILED'}")
        right_position = [200, 200, 200, 200, 200, 200]
        success = robot.l6_set_position(LbotArm.RIGHT_ARM, right_position)
        print(f"Right L6 Set Position: {'SUCCESS' if success else 'FAILED'}")
        time.sleep(3)
        
        # 设置位置到255
        left_position1 = [255, 255, 255, 255, 255, 255]
        success = robot.l6_set_position(LbotArm.LEFT_ARM, left_position1)
        print(f"Left L6 Set Position: {'SUCCESS' if success else 'FAILED'}")
        right_position1 = [255, 255, 255, 255, 255, 255]
        success = robot.l6_set_position(LbotArm.RIGHT_ARM, right_position1)
        print(f"Right L6 Set Position: {'SUCCESS' if success else 'FAILED'}")
        
    except Exception as e:
        print(f"Error in L6 hand test: {e}")
        return False
    
    return True


def test_l10_hand(robot):
    """测试L10手功能"""
    print("\n=== Testing L10 Hand ===")
    
    try:
        # 设置位置到200
        left_position = [200, 200, 200, 200, 200, 200, 200, 200, 200, 200]
        success = robot.l10_set_position(LbotArm.LEFT_ARM, left_position)
        print(f"Left L10 Set Position: {'SUCCESS' if success else 'FAILED'}")
        right_position = [200, 200, 200, 200, 200, 200, 200, 200, 200, 200]
        success = robot.l10_set_position(LbotArm.RIGHT_ARM, right_position)
        print(f"Right L10 Set Position: {'SUCCESS' if success else 'FAILED'}")
        time.sleep(3)
        
        # 设置位置到255
        left_position1 = [255, 255, 255, 255, 255, 255, 255, 255, 255, 255]
        success = robot.l10_set_position(LbotArm.LEFT_ARM, left_position1)
        print(f"Left L10 Set Position: {'SUCCESS' if success else 'FAILED'}")
        right_position1 = [255, 255, 255, 255, 255, 255, 255, 255, 255, 255]
        success = robot.l10_set_position(LbotArm.RIGHT_ARM, right_position1)
        print(f"Right L10 Set Position: {'SUCCESS' if success else 'FAILED'}")
        
    except Exception as e:
        print(f"Error in L10 hand test: {e}")
        return False
    
    return True


def test_simple_l6(robot):
    """简单的L6手测试（原代码中的测试）"""
    print("\n=== Simple L6 Hand Test ===")
    
    try:
        hand_close = [0, 0, 0, 0, 0, 0]
        hand_open = [255, 255, 255, 255, 255, 255]
        
        print("Closing left L6 hand...")
        robot.left_l6_set_position(hand_close)
        time.sleep(3)
        
        print("Opening left L6 hand...")
        robot.left_l6_set_position(hand_open)
        
    except Exception as e:
        print(f"Error in simple L6 test: {e}")
        return False
    
    return True


def main():
    """主函数"""
    print("=== LBOT API Comprehensive Test ===\n")
    
    robot = LbotRobot('192.168.10.21')
    
    try:
        # 连接机器人
        print("Connecting to robot...")
        if robot.connect():
            print("Robot connected successfully\n")
            
            # 执行测试（可以按需启用）
            
            # 测试1: 简单的L6手测试
            # test_simple_l6(robot)
            
            # 测试2: 完整的L6手测试
            # test_l6_hand(robot)
            
            # 测试3: L10手测试
            test_l10_hand(robot)
            
        else:
            print("Failed to connect to robot")
            return 1
            
    except Exception as e:
        print(f"Error during test: {e}")
        return 1
        
    finally:
        # 断开连接
        print("\nDisconnecting from robot...")
        robot.disconnect()
        print("Robot disconnected")
    
    print("\n运动控制测试完成")
    return 0


if __name__ == "__main__":
    main()