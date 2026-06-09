/*
    @brief : 测试API,机械臂工具坐标系和工作坐标系操作    
*/
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <string.h>
#include "lbot_api.h"

void test_frame_management() 
{
    printf("\n=== Testing Frame Management ===\n");
    
    // 测试工具坐标系
    printf("1. Testing Tool Frame Operations:\n");
    
    // 创建自定义工具坐标系
    const char* tool_name = "custom_gripper";
    lbot_position_t tool_position = {0.1, 0.05, 0.02};
    lbot_euler_t tool_euler = {0.0, 0.0, 0.0};
    
    bool success = lbot_set_tool_frame(LBOT_LEFT_ARM, tool_name, &tool_position, &tool_euler);
    printf("Left Set Tool Frame: %s\n", success ? "SUCCESS" : "FAILED");
    
    success = lbot_set_tool_frame(LBOT_RIGHT_ARM, tool_name, &tool_position, &tool_euler);
    printf("Right Set Tool Frame: %s\n", success ? "SUCCESS" : "FAILED");
    
    sleep(1);
    
    // 获取工具坐标系
    lbot_position_t retrieved_position;
    lbot_euler_t retrieved_euler;
    
    success = lbot_get_tool_frame(LBOT_LEFT_ARM, tool_name, &retrieved_position, &retrieved_euler);
    if (success) {
        printf("Left Get Tool Frame: SUCCESS - Position: (%.3f, %.3f, %.3f), Euler: (%.3f, %.3f, %.3f)\n",
               retrieved_position.x, retrieved_position.y, retrieved_position.z,
               retrieved_euler.x, retrieved_euler.y, retrieved_euler.z);
    } else {
        printf("Left Get Tool Frame: FAILED\n");
    }
    
    // 获取所有工具坐标系
    char** tool_names = NULL;
    int tool_count = 0;
    
    success = lbot_get_all_tool_frames(LBOT_LEFT_ARM, &tool_names, &tool_count);
    if (success && tool_names) {
        printf("Left Get All Tool Frames: SUCCESS - Found %d frames:\n", tool_count);
        for (int i = 0; i < tool_count; i++) {
            printf("  %d: %s\n", i + 1, tool_names[i]);
        }
        lbot_free_string_array(tool_names, tool_count);
    } else {
        printf("Left Get All Tool Frames: FAILED\n");
    }
    
    // 切换工具坐标系
    success = lbot_change_tool_frame(LBOT_LEFT_ARM, tool_name);
    printf("Left Change Tool Frame: %s\n", success ? "SUCCESS" : "FAILED");
    
    // 删除工具坐标系
    success = lbot_delete_tool_frame(LBOT_LEFT_ARM, tool_name);
    printf("Left Delete Tool Frame: %s\n", success ? "SUCCESS" : "FAILED");
    
    // 测试工作坐标系（类似实现）
    printf("\n2. Testing Work Frame Operations:\n");
    
    const char* work_name = "work_table";
    lbot_position_t work_position = {0.5, 0.3, 0.1};
    lbot_euler_t work_euler = {0.0, 0.0, 0.0};
    
    success = lbot_set_work_frame(LBOT_LEFT_ARM, work_name, &work_position, &work_euler);
    printf("Left Set Work Frame: %s\n", success ? "SUCCESS" : "FAILED");
    
    // 获取所有工作坐标系
    char** work_names = NULL;
    int work_count = 0;
    
    success = lbot_get_all_work_frames(LBOT_LEFT_ARM, &work_names, &work_count);
    if (success && work_names) {
        printf("Left Get All Work Frames: SUCCESS - Found %d frames:\n", work_count);
        for (int i = 0; i < work_count; i++) {
            printf("  %d: %s\n", i + 1, work_names[i]);
        }
        lbot_free_string_array(work_names, work_count);
    } else {
        printf("Left Get All Work Frames: FAILED\n");
    }
}

int main() 
{
    printf("=== LBOT API Test movej ===\n");
    // 初始化API
    printf("Initializing API...\n");
    if (!lbot_init("192.168.10.21")) 
    {
        printf("Failed to initialize API: %s\n", lbot_get_last_error());
        return 1;
    }
    printf("API initialized successfully\n");
    
    
    test_frame_management();


    printf("\nCleaning up...\n");
    lbot_cleanup();
    printf("API cleanup completed\n");
    return 0;
}