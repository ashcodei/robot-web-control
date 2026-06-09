#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <string.h>
#include "lbot_api.h"

void test_l6_hand()
{
    printf("\n=== Testing L6 Hand ===\n");
    uint8_t left_position[6] = {200, 200, 200, 200, 200, 200};
    bool success = lbot_l6_set_position(LBOT_LEFT_ARM,left_position);
    printf("Left L6 Set Position: %s\n", success ? "SUCCESS" : "FAILED");
    uint8_t right_position[6] = {200, 200, 200, 200, 200, 200};
    success = lbot_l6_set_position(LBOT_RIGHT_ARM,right_position);
    printf("Right L6 Set Position: %s\n", success ? "SUCCESS" : "FAILED");
    sleep(3);
    uint8_t left_position1[6] = {255, 255, 255, 255, 255, 255};
    success = lbot_l6_set_position(LBOT_LEFT_ARM,left_position1);
    printf("Left L6 Set Position: %s\n", success ? "SUCCESS" : "FAILED");
    uint8_t right_position1[6] = {255, 255, 255, 255, 255, 255};
    success = lbot_l6_set_position(LBOT_RIGHT_ARM,right_position1);
    printf("Right L6 Set Position: %s\n", success ? "SUCCESS" : "FAILED");
}
void test_l10_hand()
{
    printf("\n=== Testing L10 Hand ===\n");
    uint8_t left_position[10] = {200, 200, 200, 200, 200, 200, 200, 200, 200, 200};
    bool success = lbot_l10_set_position(LBOT_LEFT_ARM,left_position);
    printf("Left L10 Set Position: %s\n", success ? "SUCCESS" : "FAILED");
    uint8_t right_position[10] = {200, 200, 200, 200, 200, 200, 200, 200, 200, 200};
    success = lbot_l10_set_position(LBOT_RIGHT_ARM,right_position);
    printf("Right L10 Set Position: %s\n", success ? "SUCCESS" : "FAILED");
    sleep(3);
    uint8_t left_position1[10] = {255, 255, 255, 255, 255, 255, 255, 255, 255, 255};
    success = lbot_l10_set_position(LBOT_LEFT_ARM,left_position1);
    printf("Left L10 Set Position: %s\n", success ? "SUCCESS" : "FAILED");
    uint8_t right_position1[10] = {255, 255, 255, 255, 255, 255, 255, 255, 255, 255};
    success = lbot_l10_set_position(LBOT_RIGHT_ARM,right_position1);
    printf("Right L10 Set Position: %s\n", success ? "SUCCESS" : "FAILED");

}
int main() 
{
    printf("=== LBOT API Comprehensive Test ===\n");
    
    // 初始化API
    printf("\nInitializing API...\n");
    if (!lbot_init("192.168.10.21")) 
    {
        printf("Failed to initialize API: %s\n", lbot_get_last_error());
        return 1;
    }
    printf("API initialized successfully\n");
    
    // test_l6_hand();

    test_l10_hand();

    printf("\nCleaning up...\n");
    lbot_cleanup();
    printf("API cleanup completed\n");
    
    return 0;
}