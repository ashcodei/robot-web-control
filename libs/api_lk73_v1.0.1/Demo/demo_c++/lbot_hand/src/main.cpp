/*
    @brief
    获取版本信息
    设置关节零位    
*/
#include "lbot_api_cpp.h"
#include <iostream>
#include <string>
#include <chrono>
#include <iomanip>
#include <vector>
#include <cstdlib>
#include <unistd.h>

using namespace lbot;

void test_l6_hand(LbotApi& api)
{
    std::cout << "\n=== Testing L6 Hand ===" << std::endl;
    // 设置位置到200
    std::vector<uint8_t> left_position = {200, 200, 200, 200, 200, 200};
    bool success = api.lbot_l6_set_position(LBOT_LEFT_ARM, left_position);
    std::cout << "Left L6 Set Position: " << (success ? "SUCCESS" : "FAILED") << std::endl;
    
    std::vector<uint8_t> right_position = {200, 200, 200, 200, 200, 200};
    success = api.lbot_l6_set_position(LBOT_RIGHT_ARM, right_position);
    std::cout << "Right L6 Set Position: " << (success ? "SUCCESS" : "FAILED") << std::endl;
    
    sleep(3);
    // 设置位置到255
    std::vector<uint8_t> left_position1 = {255, 255, 255, 255, 255, 255};
    success = api.lbot_l6_set_position(LBOT_LEFT_ARM, left_position1);
    std::cout << "Left L6 Set Position: " << (success ? "SUCCESS" : "FAILED") << std::endl;
    
    std::vector<uint8_t> right_position1 = {255, 255, 255, 255, 255, 255};
    success = api.lbot_l6_set_position(LBOT_RIGHT_ARM, right_position1);
    std::cout << "Right L6 Set Position: " << (success ? "SUCCESS" : "FAILED") << std::endl;
}

void test_l10_hand(LbotApi& api)
{
    std::cout << "\n=== Testing L10 Hand ===" << std::endl;
    
    // 设置位置到200
    std::vector<uint8_t> left_position = {200, 200, 200, 200, 200, 200, 200, 200, 200, 200};
    bool success = api.lbot_l10_set_position(LBOT_LEFT_ARM, left_position);
    std::cout << "Left L10 Set Position: " << (success ? "SUCCESS" : "FAILED") << std::endl;
    std::vector<uint8_t> right_position = {200, 200, 200, 200, 200, 200, 200, 200, 200, 200};
    success = api.lbot_l10_set_position(LBOT_RIGHT_ARM, right_position);
    std::cout << "Right L10 Set Position: " << (success ? "SUCCESS" : "FAILED") << std::endl;
    sleep(3);
    
    // 设置位置到255
    std::vector<uint8_t> left_position1 = {255, 255, 255, 255, 255, 255, 255, 255, 255, 255};
    success = api.lbot_l10_set_position(LBOT_LEFT_ARM, left_position1);
    std::cout << "Left L10 Set Position: " << (success ? "SUCCESS" : "FAILED") << std::endl;
    std::vector<uint8_t> right_position1 = {255, 255, 255, 255, 255, 255, 255, 255, 255, 255};
    success = api.lbot_l10_set_position(LBOT_RIGHT_ARM, right_position1);
    std::cout << "Right L10 Set Position: " << (success ? "SUCCESS" : "FAILED") << std::endl;
}

int main() 
{
    std::cout << "=== LBOT API Comprehensive Test ===" << std::endl;
    
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
    
    // 测试L6手
    // test_l6_hand(lbotApi);
    
    // 测试L10手
    test_l10_hand(lbotApi);
    
    std::cout << "\nCleaning up..." << std::endl;
    lbotApi.lbot_cleanup();
    std::cout << "API cleanup completed" << std::endl;
    return 0;
}