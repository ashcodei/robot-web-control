/*
    @brief
    获取版本信息
    设置关节零位    
*/
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <string.h>
#include "lbot_api.h"

int main() 
{
    printf("=== LBOT API Test Arm Setting ===\n");
    // 初始化API
    printf("Initializing API...\n");
    if (!lbot_init("192.168.10.21")) 
    {
        printf("Failed to initialize API: %s\n", lbot_get_last_error());
        return 1;
    }
    printf("API initialized successfully\n");
    
    //1. 获取api版本
    printf("API Version: %s\n", SDK_VERSION);
        printf("\n=== Testing Controller Information ===\n");

    //2. 获取控制器信息
    char* robot_model = NULL;
    char* controller_version = NULL;
    bool success = lbot_get_controller_info(&robot_model, &controller_version);
    if (success) {
        printf("Controller Info: SUCCESS\n");
        printf("  Robot Model: %s\n", robot_model ? robot_model : "Unknown");
        printf("  Controller Version: %s\n", controller_version ? controller_version : "Unknown");
        
        // 释放内存
        if (robot_model) free(robot_model);
        if (controller_version) free(controller_version);
    } else {
        printf("Controller Info: FAILED - %s\n", lbot_get_last_error());
    }

    //3. 设置零点
    bool result = lbot_set_zero(LBOT_LEFT_ARM);
    if (result)
    {
        printf("Set zero successfully\n");
    }
    else
    {
        printf("Failed to set zero: %s\n", lbot_get_last_error());
    }
    result = lbot_set_zero(LBOT_RIGHT_ARM);
    if (result)
    {
        printf("Set zero successfully\n");
    }
    else
    {
        printf("Failed to set zero: %s\n", lbot_get_last_error());
    }
    // 4. 掉使能测试
    printf("\n=== Testing Disable Arm ===\n");
    result = lbot_enable_arm(LBOT_LEFT_ARM, false);
    if (result) 
    {
        printf("Disable left arm: SUCCESS\n");
    } 
    else 
    {
        printf("Disable left arm: FAILED - %s\n", lbot_get_last_error());
    }
    result = lbot_enable_arm(LBOT_RIGHT_ARM, false);
    if (result) 
    {
        printf("Disable right arm: SUCCESS\n");
    } 
    else 
    {
        printf("Disable right arm: FAILED - %s\n", lbot_get_last_error());
    }
    sleep(5);
    // 5. 启动使能
    printf("\n=== Testing Enable Arm ===\n");
    result = lbot_enable_arm(LBOT_LEFT_ARM, true);
    if (result) 
    {
        printf("Enable left arm: SUCCESS\n");
    } 
    else 
    {
        printf("Enable left arm: FAILED - %s\n", lbot_get_last_error());
    }
    result = lbot_enable_arm(LBOT_RIGHT_ARM, true);
    if (result) 
    {
        printf("Enable right arm: SUCCESS\n");
    } 
    else 
    {
        printf("Enable right arm: FAILED - %s\n", lbot_get_last_error());
    }
    // 6. 测试急停
    printf("\n=== Testing Emergency Stop ===\n");
    result = lbot_emergency_stop(LBOT_LEFT_ARM, true);
    if (result) 
    {
        printf("Emergency stop left arm: SUCCESS\n");
    } 
    else 
    {
        printf("Emergency stop left arm: FAILED - %s\n", lbot_get_last_error());
    }
    result = lbot_emergency_stop(LBOT_RIGHT_ARM, true);
    if (result) 
    {
        printf("Emergency stop right arm: SUCCESS\n");
    } 
    else 
    {
        printf("Emergency stop right arm: FAILED - %s\n", lbot_get_last_error());
    }
    sleep(5);
    // 7. 测试急停解除
    printf("\n=== Testing Emergency Release ===\n");
    result = lbot_emergency_stop(LBOT_LEFT_ARM, false);
    if (result) 
    {
        printf("Emergency release left arm: SUCCESS\n");
    } 
    else 
    {
        printf("Emergency release left arm: FAILED - %s\n", lbot_get_last_error());
    }
    result = lbot_emergency_stop(LBOT_RIGHT_ARM, false);
    if (result) 
    {
        printf("Emergency release right arm: SUCCESS\n");
    } 
    else 
    {
        printf("Emergency release right arm: FAILED - %s\n", lbot_get_last_error());
    }

    printf("\nCleaning up...\n");
    lbot_cleanup();
    printf("API cleanup completed\n");
    return 0;
}