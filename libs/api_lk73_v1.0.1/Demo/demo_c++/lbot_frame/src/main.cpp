/*
    @brief : 测试API,机械臂工具坐标系和工作坐标系操作    
*/
#include "lbot_api_cpp.h"
#include <iostream>
#include <vector>
#include <chrono>
#include <iomanip>

using namespace lbot;

void test_frame_management(LbotApi& lbotApi) 
{
    std::cout << "\n=== Testing Frame Management ===" << std::endl;
    
    // 测试工具坐标系
    std::cout << "1. Testing Tool Frame Operations:" << std::endl;
    
    // 创建自定义工具坐标系
    const char* tool_name = "custom_gripper";
    lbot_position_t tool_position = {0.1, 0.05, 0.02};
    lbot_euler_t tool_euler = {0.0, 0.0, 0.0};
    
    bool success = lbotApi.lbot_set_tool_frame(LBOT_LEFT_ARM, tool_name, &tool_position, &tool_euler);
    std::cout << "Left Set Tool Frame: " << (success ? "SUCCESS" : "FAILED") << std::endl;
    
    success = lbotApi.lbot_set_tool_frame(LBOT_RIGHT_ARM, tool_name, &tool_position, &tool_euler);
    std::cout << "Right Set Tool Frame: " << (success ? "SUCCESS" : "FAILED") << std::endl;
    
    std::this_thread::sleep_for(std::chrono::seconds(1));
    
    // 获取工具坐标系
    lbot_position_t retrieved_position;
    lbot_euler_t retrieved_euler;
    
    success = lbotApi.lbot_get_tool_frame(LBOT_LEFT_ARM, tool_name, &retrieved_position, &retrieved_euler);
    if (success) {
        std::cout << "Left Get Tool Frame: SUCCESS - Position: ("
                  << std::fixed << std::setprecision(3)
                  << retrieved_position.x << ", " 
                  << retrieved_position.y << ", " 
                  << retrieved_position.z << "), Euler: ("
                  << retrieved_euler.x << ", " 
                  << retrieved_euler.y << ", " 
                  << retrieved_euler.z << ")" << std::endl;
    } else {
        std::cout << "Left Get Tool Frame: FAILED" << std::endl;
    }
    
    // 获取所有工具坐标系 - 使用新的 API 接口
    std::vector<std::string> tool_names;
    
    success = lbotApi.lbot_get_all_tool_frames(LBOT_LEFT_ARM, tool_names);
    if (success) {
        std::cout << "Left Get All Tool Frames: SUCCESS - Found " << tool_names.size() << " frames:" << std::endl;
        for (size_t i = 0; i < tool_names.size(); i++) {
            std::cout << "  " << i + 1 << ": " << tool_names[i] << std::endl;
        }
    } else {
        std::cout << "Left Get All Tool Frames: FAILED" << std::endl;
    }
    
    // 切换工具坐标系
    success = lbotApi.lbot_change_tool_frame(LBOT_LEFT_ARM, tool_name);
    std::cout << "Left Change Tool Frame: " << (success ? "SUCCESS" : "FAILED") << std::endl;
    
    // 删除工具坐标系
    success = lbotApi.lbot_delete_tool_frame(LBOT_LEFT_ARM, tool_name);
    std::cout << "Left Delete Tool Frame: " << (success ? "SUCCESS" : "FAILED") << std::endl;
    
    // 测试工作坐标系（类似实现）
    std::cout << "\n2. Testing Work Frame Operations:" << std::endl;
    
    const char* work_name = "work_table";
    lbot_position_t work_position = {0.5, 0.3, 0.1};
    lbot_euler_t work_euler = {0.0, 0.0, 0.0};
    
    success = lbotApi.lbot_set_work_frame(LBOT_LEFT_ARM, work_name, &work_position, &work_euler);
    std::cout << "Left Set Work Frame: " << (success ? "SUCCESS" : "FAILED") << std::endl;
    
    // 获取所有工作坐标系 - 使用新的 API 接口
    std::vector<std::string> work_names;
    
    success = lbotApi.lbot_get_all_work_frames(LBOT_LEFT_ARM, work_names);
    if (success) {
        std::cout << "Left Get All Work Frames: SUCCESS - Found " << work_names.size() << " frames:" << std::endl;
        for (size_t i = 0; i < work_names.size(); i++) {
            std::cout << "  " << i + 1 << ": " << work_names[i] << std::endl;
        }
    } else {
        std::cout << "Left Get All Work Frames: FAILED" << std::endl;
    }
}

int main() 
{
    std::cout << "=== LBOT API Test Frame Management ===" << std::endl;
    
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
    
    test_frame_management(lbotApi);

    std::cout << "\nCleaning up..." << std::endl;
    lbotApi.lbot_cleanup();
    std::cout << "API cleanup completed" << std::endl;
    return 0;
}