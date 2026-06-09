/*
     * @brief   机械臂运动学正向和逆向运动学接口调用示例
*/
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <string.h>
#include "lbot_api.h"


// 测试正向运动学
bool test_forward_kinematics() 
{
    printf("\n=== Testing Forward Kinematics ===\n");
    
    // 测试几个不同的关节角度配置
    double test_joints[][7] = {
        {0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0},      // 零位
        {0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7},      // 随机角度1
        {-0.1, -0.2, -0.3, -0.4, -0.5, -0.6, -0.7}, // 随机角度2
        {0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0},      // 仅第一个关节转动
        {0.0, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0}       // 仅第二个关节转动
    };
    
    int num_tests = sizeof(test_joints) / sizeof(test_joints[0]);
    
    for (int i = 0; i < num_tests; i++) 
    {
        printf("\n--- Test Case %d ---\n", i + 1);
        printf("Input joints: [%.3f, %.3f, %.3f, %.3f, %.3f, %.3f, %.3f]\n",
               test_joints[i][0], test_joints[i][1], test_joints[i][2],
               test_joints[i][3], test_joints[i][4], test_joints[i][5],
               test_joints[i][6]);
        
        // 测试左臂
        lbot_position_t left_position;
        lbot_euler_t left_euler;
        bool success = lbot_forward_kinematics(LBOT_LEFT_ARM, test_joints[i], &left_position, &left_euler);
        
        if (success) {
            printf("Left Arm FK Result:\n");
            printf("  Position: (%.3f, %.3f, %.3f)\n", 
                   left_position.x, left_position.y, left_position.z);
            printf("  Euler Angles: (%.3f, %.3f, %.3f)\n",
                   left_euler.x, left_euler.y, left_euler.z);
        } else {
            printf("Left Arm FK Failed: %s\n", lbot_get_last_error());
        }
        
        // 测试右臂
        lbot_position_t right_position;
        lbot_euler_t right_euler;
        success = lbot_forward_kinematics(LBOT_RIGHT_ARM, test_joints[i], &right_position, &right_euler);
        
        if (success) {
            printf("Right Arm FK Result:\n");
            printf("  Position: (%.3f, %.3f, %.3f)\n", 
                   right_position.x, right_position.y, right_position.z);
            printf("  Euler Angles: (%.3f, %.3f, %.3f)\n",
                   right_euler.x, right_euler.y, right_euler.z);
        } else {
            printf("Right Arm FK Failed: %s\n", lbot_get_last_error());
        }
        
        sleep(1); // 短暂延迟，避免请求过快
    }
    return true;
}

// 测试逆向运动学
bool test_inverse_kinematics() 
{
    printf("\n=== Testing Inverse Kinematics ===\n");
    // 测试几个不同的目标位置和姿态
    struct {
        lbot_position_t position;
        lbot_euler_t euler;
        double initial_joints[7];
    } test_cases[] = {
        // 案例1：接近零位的位置
        {
            {0.3, 0.2, -0.3},           // position
            {0.0, -1.57, 0.0},          // euler
            {0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0}  // initial joints
        },
        // 案例2：右侧位置
        {
            {0.3, -0.2, -0.3},          // position
            {0.0, -1.57, 0.0},          // euler
            {0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0}  // initial joints
        },
        // 案例3：较高位置
        {
            {0.2, 0.1, 0.1},            // position
            {0.0, 0.0, 0.0},            // euler
            {0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1}  // initial joints
        }
    };
    int num_tests = sizeof(test_cases) / sizeof(test_cases[0]);
    
    for (int i = 0; i < num_tests; i++) 
    {
        printf("\n--- Test Case %d ---\n", i + 1);
        printf("Target Position: (%.3f, %.3f, %.3f)\n",
               test_cases[i].position.x, test_cases[i].position.y, test_cases[i].position.z);
        printf("Target Euler: (%.3f, %.3f, %.3f)\n",
               test_cases[i].euler.x, test_cases[i].euler.y, test_cases[i].euler.z);
        printf("Initial Joints: [%.3f, %.3f, %.3f, %.3f, %.3f, %.3f, %.3f]\n",
               test_cases[i].initial_joints[0], test_cases[i].initial_joints[1],
               test_cases[i].initial_joints[2], test_cases[i].initial_joints[3],
               test_cases[i].initial_joints[4], test_cases[i].initial_joints[5],
               test_cases[i].initial_joints[6]);
        
        // 测试左臂逆向运动学
        double left_result_joints[7];
        bool success = lbot_inverse_kinematics(LBOT_LEFT_ARM, 
                                              test_cases[i].initial_joints,
                                              &test_cases[i].position,
                                              &test_cases[i].euler,
                                              left_result_joints);
        if (success) 
        {
            printf("Left Arm IK Result:\n");
            printf("  Solved Joints: [%.3f, %.3f, %.3f, %.3f, %.3f, %.3f, %.3f]\n",
                   left_result_joints[0], left_result_joints[1], left_result_joints[2],
                   left_result_joints[3], left_result_joints[4], left_result_joints[5],
                   left_result_joints[6]);
        } 
        else 
        {
            printf("Left Arm IK Failed: %s\n", lbot_get_last_error());
        }
        
        // 测试右臂逆向运动学
        double right_result_joints[7];
        success = lbot_inverse_kinematics(LBOT_RIGHT_ARM, 
                                         test_cases[i].initial_joints,
                                         &test_cases[i].position,
                                         &test_cases[i].euler,
                                         right_result_joints);
        
        if (success) 
        {
            printf("Right Arm IK Result:\n");
            printf("  Solved Joints: [%.3f, %.3f, %.3f, %.3f, %.3f, %.3f, %.3f]\n",
                   right_result_joints[0], right_result_joints[1], right_result_joints[2],
                   right_result_joints[3], right_result_joints[4], right_result_joints[5],
                   right_result_joints[6]);
            
        } 
        else 
        {
            printf("Right Arm IK Failed: %s\n", lbot_get_last_error());
        }
        
        sleep(1); // 短暂延迟
    }
    
    return true;
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
    
    
    test_forward_kinematics();


    printf("\nCleaning up...\n");
    lbot_cleanup();
    printf("API cleanup completed\n");
    return 0;
}