# LBot API 版本更新日志
========================================================================================================================
版本：v1.0.1 (2025.12.12) → v1.0.0 (2025.11.20)
本次版本更新主要是文档完善和函数参数优化，没有破坏性的API变更。所有v1.0.0的代码都可以在v1.0.1中直接运行。

## API接口变更
1. 初始化函数优化
``` bash c
    // v1.0.0 - 需要TCP和UDP参数
    bool lbot_init(const char* tcp_host, int tcp_port, const char* udp_host, int udp_port);
    // v1.0.1 - 简化初始化，只需TCP地址
    bool lbot_init(const char* tcp_host);
    影响: 简化了API初始化过程，移除了UDP连接。
```
2. 运动控制函数参数完善
    笛卡尔空间运动增加加速度参数
``` bash c
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
```
3. 紧急停止函数增强
``` bash c
    // v1.0.0 - 全局紧急停止
    bool lbot_emergency_stop();
    // v1.0.1 - 指定机械臂紧急停止/恢复
    bool lbot_emergency_stop(lbot_arm_t arm, bool enable);
```
## 新增功能
1. L6手部控制接口（全新功能）
``` bash c
    // 左L6手控制（位置/速度/力矩模式）
    bool lbot_left_l6_set_position(const uint8_t position[6]);
    bool lbot_left_l6_set_velocity(const uint8_t velocity[6]);
    bool lbot_left_l6_set_effort(const uint8_t torque[6]);
    // 右L6手控制（位置/速度/力矩模式）
    bool lbot_right_l6_set_position(const uint8_t position[6]);
    bool lbot_right_l6_set_velocity(const uint8_t velocity[6]);
    bool lbot_right_l6_set_effort(const uint8_t torque[6]);
```
2. 机械臂使能控制
``` bash c
    bool lbot_enable_arm(lbot_arm_t arm, bool enable);
    功能: 独立控制单臂的使能/掉使能状态。
    3. 工具坐标系管理增强
    bool lbot_get_current_tool_frame(lbot_arm_t arm, char** name, 
                                    lbot_position_t* position, lbot_euler_t* euler);
    功能: 新增获取当前使用的工具坐标系信息的接口。
```
## 数据结构优化
1. 关节状态结构体字段重命名
``` bash c
    // v1.0.0 - 可能存在命名冲突
    double joints[7];  // 关节角度
    lbot_position_t position;  // 末端位置
    // v1.0.1 - 更明确的命名
    double joint_position[7];  // 关节位置
    lbot_position_t end_effector_position;  // 末端执行器位置
    影响: 提高了代码可读性，避免了命名混淆。
```
2. 时间戳格式优化
``` bash c
    // v1.0.0 - 简单的时间戳
    uint64_t timestamp;
    // v1.0.1 - ROS兼容的时间戳格式
    int32_t sec;       // 秒
    uint32_t nanosec;  // 纳秒
    char frame_id[64]; // 坐标系ID
    好处: 更好的与其他系统（如ROS）集成。
```
## 文档完善
1. 详细的Doxygen注释
    为所有API函数添加了完整的参数说明
    明确了参数的有效范围（如速度：0.0~20.0 rad/s）
    添加了返回值说明和错误处理指南
2. 明确的单位定义
// 运动控制参数单位明确化
// 关节空间: rad/s, rad/s²
// 笛卡尔空间: m/s, m/s²
// L6手控制: 0-255范围

## 向后兼容性
✅ 完全兼容的功能
    所有基本的运动控制函数（关节运动、笛卡尔运动）
    运动学计算函数（正逆运动学）
    坐标系管理函数（工具/工件坐标系）
    状态监控回调机制
    错误处理和系统功能
⚠️ 需要注意的变更
    初始化简化: 只需要更新lbot_init()调用
    状态结构体: 如果直接访问结构体字段需要更新
    运动控制: 建议补充加速度参数
## 迁移指南
``` bash c
    // v1.0.0代码示例
    lbot_move_pose(LBOT_LEFT_ARM, &pos, &euler, 0.5, true);
    // v1.0.1代码示例（推荐）
    lbot_move_pose(LBOT_LEFT_ARM, &pos, &euler, 0.5, 0.1, true);
    // 仍然兼容旧调用方式（加速度使用默认值）
```
## 🚀 新功能使用示例

1. L6手部控制示例
``` bash c
    // 控制左L6手到指定位置
    uint8_t hand_position[6] = {128, 128, 128, 128, 128, 128};
    lbot_left_l6_set_position(hand_position);
    // 使能右臂
    lbot_enable_arm(LBOT_RIGHT_ARM, true);
```
更新日期：2025年12月12日
更新作者：孟凡吉
版权所有 © 灵心巧手科技有限公司
============================================================================