/*
    @brief : 测试API,机械臂运动控制接口测试
    1. 关节角度运动
    2. 笛卡尔空间点到点运动
    3. 直线运动
    4. 关节角度跟随运动
*/
#include "lbot_api_cpp.h"
#include <iostream>
#include <stdlib.h>
#include <unistd.h>
#include <chrono>
#include <iomanip>
#include <vector>

using namespace lbot;

void state_callback(const lbot_full_state_t* state) 
{
    std::cout << "Received state update - Timestamp: " << state->system_timestamp << std::endl;
    std::cout << "Left arm position: (" 
              << std::fixed << std::setprecision(4) 
              << state->left_arm.end_effector_position.x << ", " 
              << state->left_arm.end_effector_position.y << ", " 
              << state->left_arm.end_effector_position.z << ")" << std::endl;
    std::cout << "Right arm position: (" 
              << state->right_arm.end_effector_position.x << ", " 
              << state->right_arm.end_effector_position.y << ", " 
              << state->right_arm.end_effector_position.z << ")" << std::endl;
}

void error_callback(int error_code, const char* error_msg) 
{
    std::cout << "Error " << error_code << ": " << error_msg << std::endl;
}

void print_arm_state(const lbot_full_state_t* state) 
{
    std::cout << "=== Current Arm State ===" << std::endl;
    std::cout << "Timestamp: " << state->system_timestamp << std::endl;
    
    std::cout << "Left Arm:" << std::endl;
    std::cout << "  Joints: [";
    for (int i = 0; i < 7; ++i) {
        std::cout << std::fixed << std::setprecision(3) << state->left_arm.joint_position[i];
        if (i < 6) std::cout << ", ";
    }
    std::cout << "]" << std::endl;
    std::cout << "  Position: (" 
              << state->left_arm.end_effector_position.x << ", " 
              << state->left_arm.end_effector_position.y << ", " 
              << state->left_arm.end_effector_position.z << ")" << std::endl;
    
    std::cout << "Right Arm:" << std::endl;
    std::cout << "  Joints: [";
    for (int i = 0; i < 7; ++i) {
        std::cout << state->right_arm.joint_position[i];
        if (i < 6) std::cout << ", ";
    }
    std::cout << "]" << std::endl;
    std::cout << "  Position: (" 
              << state->right_arm.end_effector_position.x << ", " 
              << state->right_arm.end_effector_position.y << ", " 
              << state->right_arm.end_effector_position.z << ")" << std::endl;
    std::cout << "=========================" << std::endl;
}

// 测试运动控制movej
void test_movej(LbotApi& lbotApi)
{
    std::cout << "\n=== Testing Joint Movement ===" << std::endl;
    std::string robot_model, controller_version;
    if (lbotApi.lbot_get_controller_info(robot_model, controller_version))
    {
        std::cout << "Robot Model: " << robot_model << std::endl;
        std::cout << "Controller Version: " << controller_version << std::endl;
    }

    if(robot_model == "LKRS73-I2")
    {
        std::vector<double> left_joints = {1.57, -1.57, -1.57, 1.57, -1.57, -1.57, -1.57};
        std::vector<double> right_joints = {-1.57, 1.57, 1.57, -1.57, 1.57, 1.57, 1.57};
        
        bool move_result = lbotApi.lbot_move_joint(LBOT_LEFT_ARM, left_joints.data(), 0.5, 1.0, false);
        std::cout << "Left move command result: " << (move_result ? "SUCCESS" : "FAILED") << std::endl;
        if (!move_result) 
        {
            std::cout << "Move command failed: " << lbotApi.lbot_get_last_error() << std::endl;
        }
        move_result = lbotApi.lbot_move_joint(LBOT_RIGHT_ARM, right_joints.data(), 0.5, 1.0, true);
        std::cout << "Right move command result: " << (move_result ? "SUCCESS" : "FAILED") << std::endl;
        if (!move_result) 
        {
            std::cout << "Right move command failed: " << lbotApi.lbot_get_last_error() << std::endl;
        }
    }
    if(robot_model == "LKLS73-O1" || robot_model == "LKLS73-O2")
    {
        std::vector<double> left_joints = {-1.57, 1.57, 1.57, 1.57, 1.57, 1.57, 1.57};
        std::vector<double> right_joints = {1.57, -1.57, -1.57, 1.57, -1.57, -1.57, -1.57};
        
        bool move_result = lbotApi.lbot_move_joint(LBOT_LEFT_ARM, left_joints.data(), 0.5, 1.0, false);
        std::cout << "Left move command result: " << (move_result ? "SUCCESS" : "FAILED") << std::endl;
        if (!move_result) 
        {
            std::cout << "Move command failed: " << lbotApi.lbot_get_last_error() << std::endl;
        }
        
        move_result = lbotApi.lbot_move_joint(LBOT_RIGHT_ARM, right_joints.data(), 0.5, 1.0, true);
        std::cout << "Right move command result: " << (move_result ? "SUCCESS" : "FAILED") << std::endl;
        if (!move_result) 
        {
            std::cout << "Right move command failed: " << lbotApi.lbot_get_last_error() << std::endl;
        }
    }
    
    lbot_full_state_t after_move_state;
    if (lbotApi.lbot_get_current_state(&after_move_state)) 
    {
        print_arm_state(&after_move_state);
    }
    
    std::vector<double> home_joints = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
    bool move_result = lbotApi.lbot_move_joint(LBOT_LEFT_ARM, home_joints.data(), 0.5, 1.0, false);
    if (!move_result) 
    {
        std::cout << "Second move command failed: " << lbotApi.lbot_get_last_error() << std::endl;
    }
    
    move_result = lbotApi.lbot_move_joint(LBOT_RIGHT_ARM, home_joints.data(), 0.5, 1.0, true);
    if (!move_result) 
    {
        std::cout << "Second move command failed: " << lbotApi.lbot_get_last_error() << std::endl;
    }
    
    lbot_full_state_t final_state;
    if (lbotApi.lbot_get_current_state(&final_state)) 
    {
        print_arm_state(&final_state);
    }
}

// 测试笛卡尔空间点到点运动
bool test_move_pose(LbotApi& lbotApi) 
{
    std::cout << "=== Testing LBOT_MOVE_POSE ===" << std::endl;
    
    // 定义目标位置和姿态
    lbot_position_t l_target_position = {0.3, 0.2, -0.25};  // x, y, z (米)
    lbot_euler_t l_target_euler = {0.0, -1.57, 0.0};       // 滚转, 俯仰, 偏航 (弧度)
    
    // 执行点到点运动 (非阻塞模式)
    bool success = lbotApi.lbot_move_pose(LBOT_LEFT_ARM, &l_target_position, &l_target_euler, 0.5, 1, false);
    if (!success) 
    {
        std::cout << "Left move pose failed: " << lbotApi.lbot_get_last_error() << std::endl;
        return false;
    }
    std::cout << "Left move pose command sent successfully" << std::endl;
    
    lbot_position_t r_target_position = {0.3, -0.2, -0.25};  // x, y, z (米)
    lbot_euler_t r_target_euler = {0.0, -1.57, 0.0};       // 滚转, 俯仰, 偏航 (弧度)
    
    success = lbotApi.lbot_move_pose(LBOT_RIGHT_ARM, &r_target_position, &r_target_euler, 0.5, 1, true);
    if (!success) 
    {
        std::cout << "Right move pose failed: " << lbotApi.lbot_get_last_error() << std::endl;
        return false;
    }
    std::cout << "Right move pose command sent successfully" << std::endl;
    
    // 等待运动完成
    std::cout << "Waiting for movement completion..." << std::endl;
    
    // 获取当前状态验证
    lbot_full_state_t current_state;
    if (lbotApi.lbot_get_current_state(&current_state)) 
    {
        std::cout << "Final left position: (" 
                  << std::fixed << std::setprecision(3)
                  << current_state.left_arm.end_effector_position.x << ", "
                  << current_state.left_arm.end_effector_position.y << ", "
                  << current_state.left_arm.end_effector_position.z << ")" << std::endl;
        std::cout << "Final right position: ("
                  << current_state.right_arm.end_effector_position.x << ", "
                  << current_state.right_arm.end_effector_position.y << ", "
                  << current_state.right_arm.end_effector_position.z << ")" << std::endl;
    }
    
    std::cout << "=== Testing LBOT_MOVE_LINEAR ===" << std::endl;
    
    // 测试直线运动
    lbot_position_t linear_target;
    
    // 左臂直线运动测试
    std::cout << "Testing left arm linear movement..." << std::endl;
    linear_target.x = 0.3 + 0.1;
    linear_target.y = 0.2;
    linear_target.z = -0.25;
    
    success = lbotApi.lbot_move_linear(LBOT_LEFT_ARM, &linear_target, &l_target_euler, 0.5, 1, true);
    if (!success) 
    {
        std::cout << "Left move linear failed: " << lbotApi.lbot_get_last_error() << std::endl;
        return false;
    }
    std::cout << "Left move linear command 1 sent successfully" << std::endl;
    
    linear_target.x = 0.3 - 0.1;
    success = lbotApi.lbot_move_linear(LBOT_LEFT_ARM, &linear_target, &l_target_euler, 0.5, 1, true);
    if (!success) 
    {
        std::cout << "Left move linear failed: " << lbotApi.lbot_get_last_error() << std::endl;
        return false;
    }
    std::cout << "Left move linear command 2 sent successfully" << std::endl;

    // 右臂直线运动测试
    std::cout << "Testing right arm linear movement..." << std::endl;
    linear_target.x = 0.3 + 0.1;
    linear_target.y = -0.2;
    linear_target.z = -0.25;
    
    success = lbotApi.lbot_move_linear(LBOT_RIGHT_ARM, &linear_target, &r_target_euler, 0.5, 1, true);
    if (!success) 
    {
        std::cout << "Right move linear failed: " << lbotApi.lbot_get_last_error() << std::endl;
        return false;
    }
    std::cout << "Right move linear command 1 sent successfully" << std::endl;
    sleep(2);
    
    linear_target.x = 0.3 - 0.1;
    success = lbotApi.lbot_move_linear(LBOT_RIGHT_ARM, &linear_target, &r_target_euler, 0.5, 1, true);
    if (!success) 
    {
        std::cout << "Right move linear failed: " << lbotApi.lbot_get_last_error() << std::endl;
        return false;
    }
    std::cout << "Right move linear command 2 sent successfully" << std::endl;
    sleep(2);
    
    return true;
}
// 测试关节跟随
void test_joint_follow(LbotApi& lbotApi)
{
    std::cout << "\n=== Testing Joint Follow ===" << std::endl;
    
    std::vector<double> left_joints = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
    std::vector<double> right_joints = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
    bool move_result = lbotApi.lbot_move_joint(LBOT_LEFT_ARM, left_joints.data(), 0.5, 1.0, true);
    std::cout << "Left move command result: " << (move_result ? "SUCCESS" : "FAILED") << std::endl;
    if (!move_result) 
    {
        std::cout << "Move command failed: " << lbotApi.lbot_get_last_error() << std::endl;
    }
    move_result = lbotApi.lbot_move_joint(LBOT_RIGHT_ARM, right_joints.data(), 0.5, 1.0, true);
    std::cout << "Right move command result: " << (move_result ? "SUCCESS" : "FAILED") << std::endl;
    if (!move_result) 
    {
        std::cout << "Right move command failed: " << lbotApi.lbot_get_last_error() << std::endl;
    }

    
    
    // 测试左臂关节跟随 - 正向运动
    std::cout << "Testing left arm joint follow (forward)..." << std::endl;
    for(int i = 0; i < 100; i++)
    {
        left_joints[0] += 0.01;
        bool success = lbotApi.lbot_joint_follow(LBOT_LEFT_ARM,left_joints);
        if (!success) {
            std::cout << "Left Joint Follow failed at step " << i << std::endl;
        }
        usleep(1000*20);
    }
    
    // 测试左臂关节跟随 - 反向运动
    std::cout << "Testing left arm joint follow (backward)..." << std::endl;
    for(int i = 0; i < 100; i++)
    {
        left_joints[0] -= 0.01;
        bool success = lbotApi.lbot_joint_follow(LBOT_LEFT_ARM,left_joints);
        if (!success) {
            std::cout << "Left Joint Follow failed at step " << i << std::endl;
        }
        usleep(1000*20);
    }
    
    sleep(1);
    
    // 测试右臂关节跟随 - 正向运动
    std::cout << "Testing right arm joint follow (forward)..." << std::endl;
    for(int i = 0; i < 100; i++)
    {
        right_joints[0] += 0.01;
        bool success = lbotApi.lbot_joint_follow(LBOT_RIGHT_ARM,right_joints);
        if (!success) {
            std::cout << "Right Joint Follow failed at step " << i << std::endl;
        }
        usleep(1000*20);
    }
    
    // 测试右臂关节跟随 - 反向运动
    std::cout << "Testing right arm joint follow (backward)..." << std::endl;
    for(int i = 0; i < 100; i++)
    {
        right_joints[0] -= 0.01;
        bool success = lbotApi.lbot_joint_follow(LBOT_RIGHT_ARM,right_joints);
        if (!success) {
            std::cout << "Right Joint Follow failed at step " << i << std::endl;
        }
        usleep(1000*20);
    }
    
    std::cout << "Joint follow test completed" << std::endl;
}
int main() 
{
    std::cout << "=== LBOT API C++ Test movej ===" << std::endl;
    LbotApi lbotApi;

    std::cout << "Initializing LBOT API..." << std::endl;
    if (!lbotApi.lbot_init("192.168.10.21")) 
    {
        std::cout << "Failed to initialize API: " << lbotApi.lbot_get_last_error() << std::endl;
        return 1;
    }
    std::cout << "API initialized successfully" << std::endl;
    
    // 1. 获取初始状态
    lbot_full_state_t initial_state;
    if (lbotApi.lbot_get_current_state(&initial_state)) 
    {
        print_arm_state(&initial_state);
    } 
    else 
    {
        std::cout << "Failed to get initial state" << std::endl;
    }
    
    // 2. 启动状态监控，实时获取状态
    std::cout << "Starting state monitor..." << std::endl;
    if (!lbotApi.lbot_start_state_monitor(state_callback, error_callback)) 
    {
        std::cout << "Failed to start state monitor: " << lbotApi.lbot_get_last_error() << std::endl;
        lbotApi.lbot_cleanup();
        return 1;
    }
    std::cout << "State monitor started" << std::endl;
    std::cout << "Waiting for state updates..." << std::endl;
    
    // 执行测试
    test_movej(lbotApi);
    test_move_pose(lbotApi);
    test_joint_follow(lbotApi);

    std::cout << "\nCleaning up..." << std::endl;
    lbotApi.lbot_stop_state_monitor(); 
    lbotApi.lbot_cleanup();
    
    std::cout << "API cleanup completed" << std::endl;
    return 0;
}