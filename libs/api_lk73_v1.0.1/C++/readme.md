# LBot API 版本更新日志

========================================================================================================================
版本：v1.0.1 (2025.12.12) → v1.0.0 (2025.11.20)
本次版本更新主要为API功能扩展和数据结构优化，存在不兼容的API变更。v1.0.0的代码需要在v1.0.1中做相应修改。
## API接口变更

1. 初始化函数优化
``` bash c++
    // v1.0.0 - 需要TCP和UDP参数
    bool lbot_init(const char* tcp_host, int tcp_port, const char* udp_host, int udp_port);
    // v1.0.1 - 简化初始化，只需TCP地址
    bool lbot_init(const char* tcp_host);
    影响: 简化了API初始化过程，移除了UDP连接，但需要更新所有初始化调用。
```

2. 运动控制函数参数完善， 笛卡尔空间运动增加加速度参数
``` bash c++
    // v1.0.0 - 缺少加速度参数
    bool lbot_move_pose(lbot_arm_t arm, const lbot_position_t* position, 
                    const lbot_euler_t* euler, double speed, bool block);
    bool lbot_move_linear(lbot_arm_t arm, const lbot_position_t* position, 
                        const lbot_euler_t* euler, double speed, bool block);
    // v1.0.1 - 增加加速度控制
    bool lbot_move_pose(lbot_arm_t arm, const lbot_position_t* position, 
                    const lbot_euler_t* euler, double speed, double accel, bool block);
    bool lbot_move_linear(lbot_arm_t arm, const lbot_position_t* position, 
                        const lbot_euler_t* euler, double speed, double accel, bool block);
    影响: 需要为所有lbot_move_pose和lbot_move_linear调用添加加速度参数。
```

3. 紧急停止函数增强
``` bash c++
    // v1.0.0 - 全局紧急停止
    bool lbot_emergency_stop();
    // v1.0.1 - 指定机械臂紧急停止/恢复
    bool lbot_emergency_stop(lbot_arm_t arm, bool enable);
```
## 新增功能
1. L6手部控制接口（全新功能）
``` bash c++
    // 左L6手控制（位置/速度/力矩模式）
    bool lbot_left_l6_set_position(const std::vector<uint8_t>& position);
    bool lbot_left_l6_set_velocity(const std::vector<uint8_t>& velocity);
    bool lbot_left_l6_set_effort(const std::vector<uint8_t>& torque);

    // 右L6手控制（位置/速度/力矩模式）
    bool lbot_right_l6_set_position(const std::vector<uint8_t>& position);
    bool lbot_right_l6_set_velocity(const std::vector<uint8_t>& velocity);
    bool lbot_right_l6_set_effort(const std::vector<uint8_t>& torque);
```
2. 机械臂使能控制
``` bash c++
    bool lbot_enable_arm(lbot_arm_t arm, bool enable);
    功能: 独立控制单臂的使能/掉使能状态。
```
3. 工具坐标系管理增强
``` bash c++
    bool lbot_get_current_tool_frame(lbot_arm_t arm, 
                                    std::string& name, 
                                    lbot_position_t& position, 
                                    lbot_euler_t& euler);

    功能: 新增获取当前使用的工具坐标系信息的接口，使用C++标准库简化字符串处理。
    数据结构优化
```
## 关节状态结构体字段重命名和扩展
``` bash c++
    // v1.0.0 - 基础状态信息
    typedef struct {
        double joints[7];               // 关节角度
        lbot_position_t position;       // 末端位置
        lbot_euler_t euler;             // 欧拉角
        lbot_orientation_t orientation; // 四元数姿态
        uint64_t timestamp;             // 时间戳
    } lbot_arm_state_t;
```
``` bash c++
    // v1.0.1 - 增强的状态信息
    typedef struct {
        // 关节数据
        char name[7][32];               // 7个关节名称
        double joint_position[7];       // 关节位置（重命名）
        double velocity[7];             // 关节速度（新增）
        double effort[7];               // 关节力矩（新增）
        
        // 时间戳
        int32_t sec;                    // 秒（新增）
        uint32_t nanosec;               // 纳秒（新增）
        char frame_id[64];              // 坐标系ID（新增）
        
        // 末端状态
        lbot_position_t end_effector_position;  // 末端位置（重命名）
        lbot_euler_t euler;                      // 欧拉角
        lbot_orientation_t orientation;          // 四元数姿态
    } lbot_arm_state_t;
    影响: 结构体字段名称和布局完全改变，需要更新所有状态访问代码。
```
    完整状态结构体优化
``` bash c++
    // v1.0.0
    typedef struct {
        lbot_arm_state_t left_arm;
        lbot_arm_state_t right_arm;
        uint64_t timestamp;             // 时间戳
    } lbot_full_state_t;
```
``` bash c++
    // v1.0.1
    typedef struct {
        lbot_arm_state_t left_arm;
        lbot_arm_state_t right_arm;
        uint64_t system_timestamp;      // 系统时间戳（重命名）
    } lbot_full_state_t;
    影响: 时间戳字段名称变更，需要更新相关访问代码。
```

## 文档完善

详细的Doxygen注释
为所有API函数添加了完整的参数说明
明确了参数的有效范围（如速度：0.0~20.0 rad/s）
添加了返回值说明和错误处理指南
明确的单位定义

    // 运动控制参数单位明确化
    // 关节空间: rad/s, rad/s²
    // 笛卡尔空间: m/s, m/s²
    // L6手控制: 0-255范围

## ❌ 不兼容的变更
1. 
- lbot_arm_state_t和lbot_full_state_t结构体布局完全改变
- lbot_init()函数参数减少
- lbot_emergency_stop()函数签名变更
``` bash c++
    // v1.0.0代码
    api.lbot_init("192.168.10.21", 10001, "192.168.10.21", 10002);
    // v1.0.1代码
    api.lbot_init("192.168.10.21");
```
2. 更新状态访问代码
``` bash c++
    // v1.0.0状态访问
    double joint0 = state->left_arm.joints[0];
    double pos_x = state->left_arm.position.x;
    // v1.0.1状态访问
    double joint0 = state->left_arm.joint_position[0];
    double pos_x = state->left_arm.end_effector_position.x;
```
3. 更新运动控制调用
``` bash c++
    // v1.0.0代码示例
    lbot_move_pose(LBOT_LEFT_ARM, &pos, &euler, 0.5, true);
    // v1.0.1代码示例
    lbot_move_pose(LBOT_LEFT_ARM, &pos, &euler, 0.5, 0.1, true);
```

## 🚀 新功能使用示例
L6手部控制示例
``` bash c++
    // 控制左L6手到指定位置
    std::vector<uint8_t> hand_position = {128, 128, 128, 128, 128, 128};
    lbot_left_l6_set_position(hand_position);
    // 使能右臂
    lbot_enable_arm(LBOT_RIGHT_ARM, true);
    // 特定机械臂紧急停止
    lbot_emergency_stop(LBOT_LEFT_ARM, true);  // 停止左臂
    lbot_emergency_stop(LBOT_LEFT_ARM, false); // 恢复左臂
```
更新日期：2025年12月12日
更新作者：孟凡吉
版权所有 © 灵心巧手科技有限公司
========================================================================================================================
