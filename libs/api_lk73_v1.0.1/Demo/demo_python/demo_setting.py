#!/usr/bin/env python3
"""
    @brief
    获取版本信息
    设置关节零位  
"""

from lbot.lbot_robot import LbotRobot, LbotArm
import time
def test_system_functions(robot):
    """测试系统功能"""
    print("=== LBOT API 系统功能测试 ===")
    
    # 1. 获取API版本信息
    # 注意：Python API中可能需要额外的方法来获取版本信息
    print("1. API版本信息: 需要查看lbot_api模块的版本常量")
    
    # 2. 获取控制器信息
    controller_info = robot.get_controller_info()
    if controller_info:
        print(f"机器人型号: {controller_info['robot_model']}")
        print(f"控制器版本: {controller_info['controller_version']}")

    # 3. 设置零点
    print("\n2. 测试设置零点:")
    
    result = robot.set_zero(LbotArm.LEFT_ARM)
    if result:
        print("左臂设置零点: 成功")
    else:
        print(f"左臂设置零点失败: {robot.get_last_error()}")
    
    result = robot.set_zero(LbotArm.RIGHT_ARM)
    if result:
        print("右臂设置零点: 成功")
    else:
        print(f"右臂设置零点失败: {robot.get_last_error()}")
    
    # 4. 测试错误处理
    print("\n3. 测试错误处理功能:")
    
    # 清除错误
    result = robot.clear_errors()
    if result:
        print("清除错误: 成功")
    else:
        print("清除错误: 失败")
    
    # 获取最后错误信息
    last_error = robot.get_last_error()
    print(f"最后错误信息: {last_error}")

    # 5. 测试掉使能
    time.sleep(3)
    print("\n4. 测试掉使能功能:")
    result = robot.enable_arm(LbotArm.LEFT_ARM, False)
    if result:
        print("左臂掉使能: 成功")
    else:
        print(f"左臂掉使能失败: {robot.get_last_error()}")
    result = robot.enable_arm(LbotArm.RIGHT_ARM, False)
    if result:
        print("右臂掉使能: 成功")
    else:
        print(f"右臂掉使能失败: {robot.get_last_error()}")
    
    # 6. 测试使能 
    print("\n5. 测试使能功能:")
    time.sleep(3)
    result = robot.enable_arm(LbotArm.LEFT_ARM, True)
    if result:
        print("左臂使能: 成功")
    else:
        print(f"左臂使能失败: {robot.get_last_error()}")
    result = robot.enable_arm(LbotArm.RIGHT_ARM, True)
    if result:
        print("右臂使能: 成功")
    else:
        print(f"右臂使能失败: {robot.get_last_error()}")
    
    # 7. 测试急停
    print("\n6. 测试急停功能:")
    time.sleep(3)
    result = robot.emergency_stop(LbotArm.LEFT_ARM, True)
    if result:
        print("左臂急停: 成功")
    else:
        print(f"左臂急停失败: {robot.get_last_error()}")
    result = robot.emergency_stop(LbotArm.RIGHT_ARM, True)
    if result:
        print("右臂急停: 成功")
    else:
        print(f"右臂急停失败: {robot.get_last_error()}")

    # 8. 测试取消急停
    print("\n7. 测试取消急停功能:")
    time.sleep(3)
    result = robot.emergency_stop(LbotArm.LEFT_ARM, False)
    if result:
        print("左臂取消急停: 成功")
    else:
        print(f"左臂取消急停失败: {robot.get_last_error()}")
    result = robot.emergency_stop(LbotArm.RIGHT_ARM, False)
    if result:
        print("右臂取消急停: 成功")
    else:
        print(f"右臂取消急停失败: {robot.get_last_error()}")
    

if __name__ == "__main__":
    with LbotRobot('192.168.10.21') as robot:
        test_system_functions(robot)
    
    print("系统功能测试完成")