/*
    @brief
    获取版本信息
    设置关节零位    
*/
#include "lbot_api_cpp.h"
#include <iostream>
#include <string>
#include <unistd.h>
#include <chrono>
#include <iomanip>
#include <vector>

using namespace lbot;

int main() 
{
    std::cout << "=== LBOT API Test Arm Setting ===" << std::endl;
    
    // 创建API实例
    LbotApi lbotApi;
    
    // 初始化API
    std::cout << "Initializing API..." << std::endl;
    if (!lbotApi.lbot_init("192.168.10.21")) 
    {
        std::cout << "Failed to initialize API: " << lbotApi.lbot_get_last_error() << std::endl;
        return 1;
    }
    std::cout << "API initialized successfully" << std::endl;
    
    // 1. 获取API版本
    std::cout << "API Version: " << SDK_VERSION << std::endl;

    // 2. 获取控制器信息
    std::cout << "\nGetting controller information..." << std::endl;
    std::string robot_model, controller_version;
    if (lbotApi.lbot_get_controller_info(robot_model, controller_version))
    {
        std::cout << "Robot Model: " << robot_model << std::endl;
        std::cout << "Controller Version: " << controller_version << std::endl;
    }
    else
    {
        std::cout << "Failed to get controller information: " << lbotApi.lbot_get_last_error() << std::endl;
    }

    
    // 3. 设置零点
    bool result = lbotApi.lbot_set_zero(LBOT_LEFT_ARM);
    if (result)
    {
        std::cout << "Left arm set zero successfully" << std::endl;
    }
    else
    {
        std::cout << "Failed to set left arm zero: " << lbotApi.lbot_get_last_error() << std::endl;
    }
    
    result = lbotApi.lbot_set_zero(LBOT_RIGHT_ARM);
    if (result)
    {
        std::cout << "Right arm set zero successfully" << std::endl;
    }
    else
    {
        std::cout << "Failed to set right arm zero: " << lbotApi.lbot_get_last_error() << std::endl;
    }

    // 4. 掉使能测试
    std::cout << "\nTesting disable arm..." << std::endl;
    result = lbotApi.lbot_enable_arm(LBOT_LEFT_ARM, false);
    if (result)
    {
        std::cout << "Left arm disabled successfully" << std::endl;
    }
    else
    {
        std::cout << "Failed to disable left arm: " << lbotApi.lbot_get_last_error() << std::endl;
    }
    result = lbotApi.lbot_enable_arm(LBOT_RIGHT_ARM, false);
    if (result)
    {
        std::cout << "Right arm disabled successfully" << std::endl;
    }
    else
    {
        std::cout << "Failed to disable right arm: " << lbotApi.lbot_get_last_error() << std::endl;
    }
    sleep(5);

    // 5. 使能测试
    std::cout << "Enabling arms..." << std::endl;
    result = lbotApi.lbot_enable_arm(LBOT_LEFT_ARM, true);
    if (result)
    {
        std::cout << "Left arm enabled successfully" << std::endl;
    }
    else
    {
        std::cout << "Failed to enable left arm: " << lbotApi.lbot_get_last_error() << std::endl;
    }
    result = lbotApi.lbot_enable_arm(LBOT_RIGHT_ARM, true);
    if (result)
    {
        std::cout << "Right arm enabled successfully" << std::endl;
    }
    else
    {
        std::cout << "Failed to enable right arm: " << lbotApi.lbot_get_last_error() << std::endl;
    }
    
    // 6. 测试急停
    std::cout << "\nTesting emergency stop..." << std::endl;
    sleep(3);
    result = lbotApi.lbot_emergency_stop(LBOT_LEFT_ARM, true);
    if (result)
    {
        std::cout << "Left arm emergency stop triggered successfully" << std::endl;
    }
    else
    {
        std::cout << "Failed to trigger left arm emergency stop: " << lbotApi.lbot_get_last_error() << std::endl;
    }
    result = lbotApi.lbot_emergency_stop(LBOT_RIGHT_ARM, true);
    if (result)
    {
        std::cout << "Right arm emergency stop triggered successfully" << std::endl;
    }
    else
    {
        std::cout << "Failed to trigger right arm emergency stop: " << lbotApi.lbot_get_last_error() << std::endl;
    }
    sleep(5);
    // 7. 测试急停解除
    result = lbotApi.lbot_emergency_stop(LBOT_LEFT_ARM, false);
    if (result)
    {
        std::cout << "Left arm emergency stop released successfully" << std::endl;
    }
    else
    {
        std::cout << "Failed to release left arm emergency stop: " << lbotApi.lbot_get_last_error() << std::endl;
    }
    result = lbotApi.lbot_emergency_stop(LBOT_RIGHT_ARM, false);
    if (result)
    {
        std::cout << "Right arm emergency stop released successfully" << std::endl;
    }
    else
    {
        std::cout << "Failed to release right arm emergency stop: " << lbotApi.lbot_get_last_error() << std::endl;
    }
    sleep(5);

    std::cout << "\nCleaning up..." << std::endl;
    lbotApi.lbot_cleanup();
    std::cout << "API cleanup completed" << std::endl;
    return 0;
}