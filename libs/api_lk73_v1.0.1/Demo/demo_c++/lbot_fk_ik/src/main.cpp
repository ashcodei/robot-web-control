/*
     * @brief   机械臂运动学正向和逆向运动学接口调用示例
*/
#include "lbot_api_cpp.h"
#include <iostream>
#include <vector>
#include <chrono>
#include <iomanip>
#include <unistd.h>
using namespace lbot;

// 测试正向运动学
bool test_forward_kinematics(LbotApi& lbotApi) 
{
    std::cout << "\n=== Testing Forward Kinematics ===" << std::endl;
    
    // 测试几个不同的关节角度配置
    std::vector<std::vector<double>> test_joints = {
        {0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0},      // 零位
        {0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7},      // 随机角度1
        {-0.1, -0.2, -0.3, -0.4, -0.5, -0.6, -0.7}, // 随机角度2
        {0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0},      // 仅第一个关节转动
        {0.0, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0}       // 仅第二个关节转动
    };
    
    for (size_t i = 0; i < test_joints.size(); i++) 
    {
        std::cout << "\n--- Test Case " << i + 1 << " ---" << std::endl;
        std::cout << "Input joints: [";
        for (size_t j = 0; j < test_joints[i].size(); j++) {
            std::cout << std::fixed << std::setprecision(3) << test_joints[i][j];
            if (j < test_joints[i].size() - 1) std::cout << ", ";
        }
        std::cout << "]" << std::endl;
        
        // 测试左臂
        lbot_position_t left_position;
        lbot_euler_t left_euler;
        bool success = lbotApi.lbot_forward_kinematics(LBOT_LEFT_ARM, test_joints[i].data(), &left_position, &left_euler);
        
        if (success) {
            std::cout << "Left Arm FK Result:" << std::endl;
            std::cout << "  Position: (" 
                      << std::fixed << std::setprecision(3)
                      << left_position.x << ", " 
                      << left_position.y << ", " 
                      << left_position.z << ")" << std::endl;
            std::cout << "  Euler Angles: ("
                      << left_euler.x << ", " 
                      << left_euler.y << ", " 
                      << left_euler.z << ")" << std::endl;
        } else {
            std::cout << "Left Arm FK Failed: " << lbotApi.lbot_get_last_error() << std::endl;
        }
        
        // 测试右臂
        lbot_position_t right_position;
        lbot_euler_t right_euler;
        success = lbotApi.lbot_forward_kinematics(LBOT_RIGHT_ARM, test_joints[i].data(), &right_position, &right_euler);
        
        if (success) {
            std::cout << "Right Arm FK Result:" << std::endl;
            std::cout << "  Position: (" 
                      << right_position.x << ", " 
                      << right_position.y << ", " 
                      << right_position.z << ")" << std::endl;
            std::cout << "  Euler Angles: ("
                      << right_euler.x << ", " 
                      << right_euler.y << ", " 
                      << right_euler.z << ")" << std::endl;
        } else {
            std::cout << "Right Arm FK Failed: " << lbotApi.lbot_get_last_error() << std::endl;
        }
        
        sleep(1);
    }
    return true;
}

// 测试逆向运动学
bool test_inverse_kinematics(LbotApi& lbotApi) 
{
    std::cout << "\n=== Testing Inverse Kinematics ===" << std::endl;
    
    // 定义测试用例结构
    struct TestCase {
        lbot_position_t position;
        lbot_euler_t euler;
        std::vector<double> initial_joints;
    };
    
    // 测试几个不同的目标位置和姿态
    std::vector<TestCase> test_cases = {
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
    
    for (size_t i = 0; i < test_cases.size(); i++) 
    {
        std::cout << "\n--- Test Case " << i + 1 << " ---" << std::endl;
        std::cout << "Target Position: ("
                  << std::fixed << std::setprecision(3)
                  << test_cases[i].position.x << ", "
                  << test_cases[i].position.y << ", "
                  << test_cases[i].position.z << ")" << std::endl;
        std::cout << "Target Euler: ("
                  << test_cases[i].euler.x << ", "
                  << test_cases[i].euler.y << ", "
                  << test_cases[i].euler.z << ")" << std::endl;
        std::cout << "Initial Joints: [";
        for (size_t j = 0; j < test_cases[i].initial_joints.size(); j++) {
            std::cout << test_cases[i].initial_joints[j];
            if (j < test_cases[i].initial_joints.size() - 1) std::cout << ", ";
        }
        std::cout << "]" << std::endl;
        
        // 测试左臂逆向运动学
        std::vector<double> left_result_joints(7);
        bool success = lbotApi.lbot_inverse_kinematics(LBOT_LEFT_ARM, 
                                                      test_cases[i].initial_joints.data(),
                                                      &test_cases[i].position,
                                                      &test_cases[i].euler,
                                                      left_result_joints.data());
        if (success) 
        {
            std::cout << "Left Arm IK Result:" << std::endl;
            std::cout << "  Solved Joints: [";
            for (size_t j = 0; j < left_result_joints.size(); j++) {
                std::cout << std::fixed << std::setprecision(3) << left_result_joints[j];
                if (j < left_result_joints.size() - 1) std::cout << ", ";
            }
            std::cout << "]" << std::endl;
        } 
        else 
        {
            std::cout << "Left Arm IK Failed: " << lbotApi.lbot_get_last_error() << std::endl;
        }
        
        // 测试右臂逆向运动学
        std::vector<double> right_result_joints(7);
        success = lbotApi.lbot_inverse_kinematics(LBOT_RIGHT_ARM, 
                                                 test_cases[i].initial_joints.data(),
                                                 &test_cases[i].position,
                                                 &test_cases[i].euler,
                                                 right_result_joints.data());
        
        if (success) 
        {
            std::cout << "Right Arm IK Result:" << std::endl;
            std::cout << "  Solved Joints: [";
            for (size_t j = 0; j < right_result_joints.size(); j++) {
                std::cout << right_result_joints[j];
                if (j < right_result_joints.size() - 1) std::cout << ", ";
            }
            std::cout << "]" << std::endl;
        } 
        else 
        {
            std::cout << "Right Arm IK Failed: " << lbotApi.lbot_get_last_error() << std::endl;
        }
        
        sleep(1);
    }
    
    return true;
}

int main() 
{
    std::cout << "=== LBOT API Test Kinematics ===" << std::endl;
    
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
    
    // 测试正向运动学
    test_forward_kinematics(lbotApi);
    
    // 测试逆向运动学
    test_inverse_kinematics(lbotApi);

    std::cout << "\nCleaning up..." << std::endl;
    lbotApi.lbot_cleanup();
    std::cout << "API cleanup completed" << std::endl;
    return 0;
}