#!/usr/bin/env python3
"""
    @brief : 测试API,机械臂工具坐标系和工作坐标系操作    
"""

import time
from lbot.lbot_robot import LbotRobot, LbotArm, LbotPosition, LbotEuler


def test_frame_management(robot):
    """测试坐标系管理"""
    print("\n=== 测试坐标系管理 ===")
    
    # 测试工具坐标系
    print("1. 测试工具坐标系操作:")
    
    # 创建自定义工具坐标系
    tool_name = "custom_gripper"
    tool_position = LbotPosition(0.1, 0.05, 0.02)
    tool_euler = LbotEuler(0.0, 0.0, 0.0)
    
    # 设置工具坐标系
    success = robot.set_tool_frame(LbotArm.LEFT_ARM, tool_name, tool_position, tool_euler)
    print(f"左臂设置工具坐标系: {'成功' if success else '失败'}")
    
    success = robot.set_tool_frame(LbotArm.RIGHT_ARM, tool_name, tool_position, tool_euler)
    print(f"右臂设置工具坐标系: {'成功' if success else '失败'}")
    
    time.sleep(1)
    
    # 获取工具坐标系
    left_tool_result = robot.get_tool_frame(LbotArm.LEFT_ARM, tool_name)
    if left_tool_result:
        position, euler = left_tool_result
        print(f"左臂获取工具坐标系: 成功")
        print(f"  位置: ({position.x:.3f}, {position.y:.3f}, {position.z:.3f})")
        print(f"  欧拉角: ({euler.x:.3f}, {euler.y:.3f}, {euler.z:.3f})")
    else:
        print("左臂获取工具坐标系: 失败")
    
    # 注意：Python API中可能需要额外的方法来获取所有坐标系名称
    # 这里假设有相应的方法，如果没有可以跳过
    
    print("\n2. 测试工作坐标系操作:")
    
    # 测试工作坐标系
    work_name = "work_table"
    work_position = LbotPosition(0.5, 0.3, 0.1)
    work_euler = LbotEuler(0.0, 0.0, 0.0)
    
    success = robot.set_work_frame(LbotArm.LEFT_ARM, work_name, work_position, work_euler)
    print(f"左臂设置工作坐标系: {'成功' if success else '失败'}")
    
    # 获取工作坐标系
    left_work_result = robot.get_work_frame(LbotArm.LEFT_ARM, work_name)
    if left_work_result:
        position, euler = left_work_result
        print(f"左臂获取工作坐标系: 成功")
        print(f"  位置: ({position.x:.3f}, {position.y:.3f}, {position.z:.3f})")
        print(f"  欧拉角: ({euler.x:.3f}, {euler.y:.3f}, {euler.z:.3f})")
    else:
        print("左臂获取工作坐标系: 失败")


if __name__ == "__main__":
    with LbotRobot('192.168.10.21') as robot:
        test_frame_management(robot)
    
    print("坐标系管理测试完成")