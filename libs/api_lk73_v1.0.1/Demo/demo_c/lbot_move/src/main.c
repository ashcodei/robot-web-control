/*
    @brief : 测试API,机械臂运动控制接口测试
    1. 关节角度运动
    2. 笛卡尔空间点到点运动
    3. 直线运动
    4. 关节角度跟随运动
*/
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <string.h>
#include "lbot_api.h"

void state_callback(const lbot_full_state_t* state) 
{
    printf("Received state update - Timestamp: %lu\n", state->system_timestamp);
    printf("Left arm position: (%.4f, %.4f, %.4f)\n", 
           state->left_arm.end_effector_position.x, 
           state->left_arm.end_effector_position.y, 
           state->left_arm.end_effector_position.z);
    printf("Right arm position: (%.4f, %.4f, %.4f)\n", 
           state->right_arm.end_effector_position.x, 
           state->right_arm.end_effector_position.y, 
           state->right_arm.end_effector_position.z);
}

void error_callback(int error_code, const char* error_msg) 
{
    printf("Error %d: %s\n", error_code, error_msg);
}

void print_arm_state(const lbot_full_state_t* state) 
{
    printf("=== Current Arm State ===\n");
    printf("Timestamp: %lu\n", state->system_timestamp);
    printf("Left Arm:\n");
    printf("  Joints: [%.3f, %.3f, %.3f, %.3f, %.3f, %.3f, %.3f]\n",
           state->left_arm.joint_position[0], state->left_arm.joint_position[1],
           state->left_arm.joint_position[2], state->left_arm.joint_position[3],
           state->left_arm.joint_position[4], state->left_arm.joint_position[5],
           state->left_arm.joint_position[6]);
    printf("  Position: (%.3f, %.3f, %.3f)\n",
           state->left_arm.end_effector_position.x, state->left_arm.end_effector_position.y, state->left_arm.end_effector_position.z);
    printf("Right Arm:\n");
    printf("  Joints: [%.3f, %.3f, %.3f, %.3f, %.3f, %.3f, %.3f]\n",
           state->right_arm.joint_position[0], state->right_arm.joint_position[1],
           state->right_arm.joint_position[2], state->right_arm.joint_position[3],
           state->right_arm.joint_position[4], state->right_arm.joint_position[5],
           state->right_arm.joint_position[6]);
    printf("  Position: (%.3f, %.3f, %.3f)\n",
           state->right_arm.end_effector_position.x, state->right_arm.end_effector_position.y, state->right_arm.end_effector_position.z);
    printf("=========================\n");
}
// 测试运动控制movej
void test_movej()
{
    char* robot_model = NULL;
    char* controller_version = NULL;
    bool success = lbot_get_controller_info(&robot_model, &controller_version);
    if (success) {
        printf("Controller Info: SUCCESS\n");
        printf("  Robot Model: %s\n", robot_model ? robot_model : "Unknown");
        printf("  Controller Version: %s\n", controller_version ? controller_version : "Unknown");
    } 
    if(success && strcmp(robot_model, "LKRS73-I2") == 0)
    {
        printf("\n=== LKRS73-I2 Testing Joint Movement ===\n");
        double left_joints[7] = {1.57, -1.57, -1.57, 1.57, -1.57, -1.57, -1.57};
        double right_joints[7] = {-1.57, 1.57, 1.57, -1.57, 1.57, 1.57, 1.57};
        //非阻塞模式
        bool move_result = lbot_move_joint(LBOT_LEFT_ARM, left_joints, 0.5, 1.0, false);
        printf("Left move command result: %s\n", move_result ? "SUCCESS" : "FAILED");
        if (!move_result) 
        {
            printf("Move command failed: %s\n", lbot_get_last_error());
        }
        move_result = lbot_move_joint(LBOT_RIGHT_ARM, right_joints, 0.5, 1.0, true);
        printf("Right move command result: %s\n", move_result ? "SUCCESS" : "FAILED");
        if (!move_result) 
        {
            printf("Right move command failed: %s\n", lbot_get_last_error());
        }
    }
    if(success && (strcmp(robot_model, "LKLS73-O1") == 0 || strcmp(robot_model, "LKLS73-O2") == 0))
    {
        printf("\n=== LKLS73-O1 Testing Joint Movement ===\n");
        double left_joints[7] = {-1.57, 1.57, 1.57, 1.57, 1.57, 1.57, 1.57};
        double right_joints[7] = {1.57, -1.57, -1.57, 1.57, -1.57, -1.57, -1.57};
        bool move_result = lbot_move_joint(LBOT_LEFT_ARM, left_joints, 0.5, 1.0, false);
        printf("Left move command result: %s\n", move_result ? "SUCCESS" : "FAILED");
        if (!move_result) 
        {
            printf("Move command failed: %s\n", lbot_get_last_error());
        }
        move_result = lbot_move_joint(LBOT_RIGHT_ARM, right_joints, 0.5, 1.0, true);
        printf("Right move command result: %s\n", move_result ? "SUCCESS" : "FAILED");
        if (!move_result) 
        {
            printf("Right move command failed: %s\n", lbot_get_last_error());
        } 
    }
    sleep(1);
    lbot_full_state_t after_move_state;
    if (lbot_get_current_state(&after_move_state)) 
    {
        print_arm_state(&after_move_state);
    }
    double home_joints[7] = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
    bool move_result = lbot_move_joint(LBOT_LEFT_ARM, home_joints, 1.0, 1.0, false);
    if (!move_result) 
    {
        printf("Second move command failed: %s\n", lbot_get_last_error());
    }
    move_result = lbot_move_joint(LBOT_RIGHT_ARM, home_joints, 1.0, 1.0, true);
    if (!move_result) 
    {
        printf("Second move command failed: %s\n", lbot_get_last_error());
    }
    lbot_full_state_t final_state;
    if (lbot_get_current_state(&final_state)) 
    {
        print_arm_state(&final_state);
    }
}
// 测试笛卡尔空间点到点运动
bool test_move_pose() 
{
    printf("=== Testing LBOT_MOVE_POSE ===\n");
    
    // 定义目标位置和姿态
    lbot_position_t l_target_position = {0.3, 0.2, -0.25};  // x, y, z (米)
    lbot_euler_t l_target_euler = {0.0, -1.57, 0.0};       // 滚转, 俯仰, 偏航 (弧度)
    
    // 执行点到点运动 (非阻塞模式)
    bool success = lbot_move_pose(LBOT_LEFT_ARM, &l_target_position, &l_target_euler, 1.0, 1, false);
    if (!success) 
    {
        printf("Left move pose failed: %s\n", lbot_get_last_error());
        return false;
    }
    printf("Left move pose command sent successfully\n");
    
    lbot_position_t r_target_position = {0.3, -0.2, -0.25};  // x, y, z (米)
    lbot_euler_t r_target_euler = {0.0, -1.57, 0.0};       // 滚转, 俯仰, 偏航 (弧度)
    
    success = lbot_move_pose(LBOT_RIGHT_ARM, &r_target_position, &r_target_euler, 1, 1, true);
    if (!success) 
    {
        printf("Right move pose failed: %s\n", lbot_get_last_error());
        return false;
    }
    sleep(1);
    printf("Right move pose command sent successfully\n");
    
    // 获取当前状态验证
    lbot_full_state_t current_state;
    if (lbot_get_current_state(&current_state)) 
    {
        printf("Final left position: (%.3f, %.3f, %.3f)\n",
               current_state.left_arm.end_effector_position.x,
               current_state.left_arm.end_effector_position.y,
               current_state.left_arm.end_effector_position.z);
        printf("Final right position: (%.3f, %.3f, %.3f)\n",
               current_state.right_arm.end_effector_position.x,
               current_state.right_arm.end_effector_position.y,
               current_state.right_arm.end_effector_position.z);
    }
    
    printf("=== Testing LBOT_MOVE_LINEAR ===\n");
    
    // 测试直线运动 - 修正参数传递问题
    lbot_position_t linear_target;
    // 左臂直线运动测试
    printf("Testing left arm linear movement...\n");
    linear_target.x = 0.3 + 0.1;
    linear_target.y = 0.2;
    linear_target.z = -0.3;
    
    success = lbot_move_linear(LBOT_LEFT_ARM, &linear_target, &l_target_euler, 1, 1, true);
    if (!success) 
    {
        printf("Left move linear failed: %s\n", lbot_get_last_error());
        return false;
    }
    printf("Left move linear command 1 sent successfully\n");
    
    linear_target.x = 0.3 - 0.1;
    success = lbot_move_linear(LBOT_LEFT_ARM, &linear_target, &l_target_euler, 1, 1, true);
    if (!success) 
    {
        printf("Left move linear failed: %s\n", lbot_get_last_error());
        return false;
    }
    printf("Left move linear command 2 sent successfully\n");

    // 右臂直线运动测试
    printf("Testing right arm linear movement...\n");
    linear_target.x = 0.3 + 0.1;
    linear_target.y = -0.2;
    linear_target.z = -0.3;
    
    success = lbot_move_linear(LBOT_RIGHT_ARM, &linear_target, &r_target_euler, 1, 1, true);
    if (!success) 
    {
        printf("Right move linear failed: %s\n", lbot_get_last_error());
        return false;
    }
    printf("Right move linear command 1 sent successfully\n");
    
    linear_target.x = 0.3 - 0.1;
    success = lbot_move_linear(LBOT_RIGHT_ARM, &linear_target, &r_target_euler, 1, 1, true);
    if (!success) 
    {
        printf("Right move linear failed: %s\n", lbot_get_last_error());
        return false;
    }
    printf("Right move linear command 2 sent successfully\n");
    sleep(2);
    
    return true;
}
void test_joint_follow()
{
    printf("\n=== Testing Joint Movement ===\n");
    double left_joints[7] = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
    double right_joints[7] = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
    bool move_result = lbot_move_joint(LBOT_LEFT_ARM, left_joints, 1, 1.0, true);
    printf("Left move command result: %s\n", move_result ? "SUCCESS" : "FAILED");
    if (!move_result) 
    {
        printf("Move command failed: %s\n", lbot_get_last_error());
    }
    move_result = lbot_move_joint(LBOT_RIGHT_ARM, right_joints, 1, 1.0, true);
    printf("Right move command result: %s\n", move_result ? "SUCCESS" : "FAILED");
    if (!move_result) 
    {
        printf("Right move command failed: %s\n", lbot_get_last_error());
    }

    printf("\n=== Testing Joint Follow ===\n");
    // 测试左臂关节跟随
    for(int i = 0; i < 100; i++)
    {
        left_joints[0] += 0.01;
        bool success = lbot_joint_follow(LBOT_LEFT_ARM,left_joints);
        printf("Left Joint Follow: %s\n", success ? "SUCCESS" : "FAILED");
        usleep(1000*20);
    }
    for(int i = 0; i < 100; i++)
    {
        left_joints[0] -= 0.01;
        bool success = lbot_joint_follow(LBOT_LEFT_ARM,left_joints);
        printf("Left Joint Follow: %s\n", success ? "SUCCESS" : "FAILED");
        usleep(1000*20);
    }
    sleep(1);
    for(int i = 0; i < 100; i++)
    {
        right_joints[0] += 0.01;
        bool success = lbot_joint_follow(LBOT_RIGHT_ARM,right_joints);
        printf("Right Joint Follow: %s\n", success ? "SUCCESS" : "FAILED");
        usleep(1000*20);
    }
    for(int i = 0; i < 100; i++)
    {
        right_joints[0] -= 0.01;
        bool success = lbot_joint_follow(LBOT_RIGHT_ARM,right_joints);
        printf("Right Joint Follow: %s\n", success ? "SUCCESS" : "FAILED");
        usleep(1000*20);
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
    
    // 1. 获取初始状态
    lbot_full_state_t initial_state;
    if (lbot_get_current_state(&initial_state)) 
    {
        print_arm_state(&initial_state);
    } 
    else 
    {
        printf("Failed to get initial state\n");
    }
    
    // 2. 启动状态监控，实时获取状态
    printf("Starting state monitor...\n");
    if (!lbot_start_state_monitor(state_callback, error_callback)) 
    {
        printf("Failed to start state monitor: %s\n", lbot_get_last_error());
        lbot_cleanup();
        return 1;
    }
    printf("State monitor started\n");
    printf("Waiting for state updates...\n");
    
    test_movej();
    
    test_move_pose();

    test_joint_follow();

    printf("\nCleaning up...\n");
    lbot_stop_state_monitor();
    lbot_cleanup();
    
    printf("API cleanup completed\n");
    return 0;
}