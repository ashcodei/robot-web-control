"""
Internationalization Module
国际化模块

Provides Chinese/English bilingual support.
提供中英双语支持。
"""

import threading
from typing import Dict, Optional, Callable, List
from enum import Enum


class Language(Enum):
    """Language enumeration / 语言枚举"""
    CHINESE = "zh"
    ENGLISH = "en"


# Translation dictionary / 翻译字典
TRANSLATIONS: Dict[str, Dict[str, str]] = {
    # ==========================================================================
    # System / 系统
    # ==========================================================================
    "app.title": {
        "zh": "自动做饭机器人控制系统",
        "en": "Automatic Cooking Robot Control System"
    },
    "app.version": {
        "zh": "版本",
        "en": "Version"
    },

    # ==========================================================================
    # Common / 通用
    # ==========================================================================
    "common.connect": {
        "zh": "连接",
        "en": "Connect"
    },
    "common.disconnect": {
        "zh": "断开",
        "en": "Disconnect"
    },
    "common.start": {
        "zh": "启动",
        "en": "Start"
    },
    "common.stop": {
        "zh": "停止",
        "en": "Stop"
    },
    "common.pause": {
        "zh": "暂停",
        "en": "Pause"
    },
    "common.resume": {
        "zh": "恢复",
        "en": "Resume"
    },
    "common.reset": {
        "zh": "重置",
        "en": "Reset"
    },
    "common.save": {
        "zh": "保存",
        "en": "Save"
    },
    "common.load": {
        "zh": "加载",
        "en": "Load"
    },
    "common.cancel": {
        "zh": "取消",
        "en": "Cancel"
    },
    "common.confirm": {
        "zh": "确认",
        "en": "Confirm"
    },
    "common.close": {
        "zh": "关闭",
        "en": "Close"
    },
    "common.refresh": {
        "zh": "刷新",
        "en": "Refresh"
    },
    "common.settings": {
        "zh": "设置",
        "en": "Settings"
    },
    "common.status": {
        "zh": "状态",
        "en": "Status"
    },
    "common.error": {
        "zh": "错误",
        "en": "Error"
    },
    "common.warning": {
        "zh": "警告",
        "en": "Warning"
    },
    "common.success": {
        "zh": "成功",
        "en": "Success"
    },
    "common.failed": {
        "zh": "失败",
        "en": "Failed"
    },
    "common.yes": {
        "zh": "是",
        "en": "Yes"
    },
    "common.no": {
        "zh": "否",
        "en": "No"
    },
    "common.connecting": {
        "zh": "连接中...",
        "en": "Connecting..."
    },
    "common.connected": {
        "zh": "已连接",
        "en": "Connected"
    },
    "common.disconnected": {
        "zh": "已断开",
        "en": "Disconnected"
    },
    "common.active": {
        "zh": "运行中",
        "en": "Active"
    },
    "common.stopped": {
        "zh": "已停止",
        "en": "Stopped"
    },
    "common.ready": {
        "zh": "就绪",
        "en": "Ready"
    },

    # ==========================================================================
    # Control Panel / 控制面板
    # ==========================================================================
    "control.title": {
        "zh": "控制面板",
        "en": "Control Panel"
    },
    "control.emergency_stop": {
        "zh": "紧急停止",
        "en": "EMERGENCY STOP"
    },
    "control.emergency_stop_release": {
        "zh": "释放紧急停止",
        "en": "Release E-Stop"
    },
    "control.connect_all": {
        "zh": "全部连接",
        "en": "Connect All"
    },
    "control.disconnect_all": {
        "zh": "全部断开",
        "en": "Disconnect All"
    },
    "control.start_all": {
        "zh": "全部启动",
        "en": "Start All"
    },
    "control.stop_all": {
        "zh": "全部停止",
        "en": "Stop All"
    },
    "control.pause_all": {
        "zh": "全部暂停",
        "en": "Pause All"
    },
    "control.resume_all": {
        "zh": "全部恢复",
        "en": "Resume All"
    },
    "control.system_status": {
        "zh": "系统状态",
        "en": "System Status"
    },
    "control.quick_actions": {
        "zh": "快速操作",
        "en": "Quick Actions"
    },

    # ==========================================================================
    # Hardware States / 硬件状态
    # ==========================================================================
    "state.disconnected": {
        "zh": "未连接",
        "en": "Disconnected"
    },
    "state.connecting": {
        "zh": "连接中",
        "en": "Connecting"
    },
    "state.connected": {
        "zh": "已连接",
        "en": "Connected"
    },
    "state.partial": {
        "zh": "部分连接",
        "en": "Partial"
    },
    "hardware.left": {
        "zh": "左",
        "en": "Left"
    },
    "hardware.right": {
        "zh": "右",
        "en": "Right"
    },
    "connection.arm_ip": {
        "zh": "IP",
        "en": "IP"
    },
    "gripper.port": {
        "zh": "端口",
        "en": "Port"
    },
    "state.running": {
        "zh": "运行中",
        "en": "Running"
    },
    "state.paused": {
        "zh": "已暂停",
        "en": "Paused"
    },
    "state.error": {
        "zh": "错误",
        "en": "Error"
    },
    "state.emergency_stop": {
        "zh": "紧急停止",
        "en": "E-Stop"
    },

    # ==========================================================================
    # Hardware Names / 硬件名称
    # ==========================================================================
    "hardware.gantry_lebai": {
        "zh": "龙门架+乐白",
        "en": "Gantry+Lebai"
    },
    "hardware.gantry": {
        "zh": "龙门架",
        "en": "Gantry"
    },
    "hardware.lebai": {
        "zh": "乐白机械臂",
        "en": "Lebai Arm"
    },
    "hardware.dual_arm": {
        "zh": "灵心双臂",
        "en": "Dual Arm"
    },
    "hardware.left_arm": {
        "zh": "左臂",
        "en": "Left Arm"
    },
    "hardware.right_arm": {
        "zh": "右臂",
        "en": "Right Arm"
    },
    "hardware.linker_hand": {
        "zh": "L6机械手",
        "en": "L6 Hands"
    },
    "hardware.left_hand": {
        "zh": "左手",
        "en": "Left Hand"
    },
    "hardware.right_hand": {
        "zh": "右手",
        "en": "Right Hand"
    },
    "hardware.wok": {
        "zh": "自动炒锅",
        "en": "Auto Wok"
    },
    "hardware.teleop": {
        "zh": "遥操作",
        "en": "Teleoperation"
    },
    "hardware.inventory": {
        "zh": "冰箱库存",
        "en": "Inventory"
    },

    # ==========================================================================
    # Gantry + Lebai / 龙门架+乐白
    # ==========================================================================
    "gantry.vertical": {
        "zh": "垂直轴",
        "en": "Vertical Axis"
    },
    "gantry.horizontal": {
        "zh": "水平轴",
        "en": "Horizontal Axis"
    },
    "gantry.distance": {
        "zh": "距离(mm)",
        "en": "Distance(mm)"
    },
    "gantry.move_up": {
        "zh": "上移",
        "en": "Move Up"
    },
    "gantry.move_down": {
        "zh": "下移",
        "en": "Move Down"
    },
    "gantry.move_left": {
        "zh": "左移",
        "en": "Move Left"
    },
    "gantry.move_right": {
        "zh": "右移",
        "en": "Move Right"
    },
    "gantry.soft_stop": {
        "zh": "软停止",
        "en": "Soft Stop"
    },
    "gantry.upload_firmware": {
        "zh": "上传固件",
        "en": "Upload Firmware"
    },
    "gantry.upload_firmware_confirm": {
        "zh": "确定要上传固件到Arduino吗？上传期间串口将断开。",
        "en": "Upload firmware to Arduino? Serial will disconnect during upload."
    },
    "gantry.fw_disconnecting": {
        "zh": "断开串口...",
        "en": "Disconnecting serial..."
    },
    "gantry.fw_compiling": {
        "zh": "编译中...",
        "en": "Compiling..."
    },
    "gantry.fw_compiled": {
        "zh": "编译完成",
        "en": "Compiled"
    },
    "gantry.fw_uploading": {
        "zh": "正在上传...",
        "en": "Uploading to board..."
    },
    "gantry.fw_uploaded": {
        "zh": "上传完成",
        "en": "Upload complete"
    },
    "gantry.fw_reconnecting": {
        "zh": "重新连接...",
        "en": "Reconnecting..."
    },
    "gantry.fw_done": {
        "zh": "固件上传成功",
        "en": "Firmware uploaded OK"
    },
    "gantry.axis_select": {
        "zh": "轴选择",
        "en": "Axis Select"
    },
    "gantry.both_columns": {
        "zh": "双列同步",
        "en": "Both Columns"
    },
    "gantry.motion_status": {
        "zh": "运动状态",
        "en": "Motion Status"
    },
    "gantry.moving": {
        "zh": "移动中...",
        "en": "Moving..."
    },
    "gantry.idle": {
        "zh": "空闲",
        "en": "Idle"
    },
    "gantry.stopped": {
        "zh": "已停止",
        "en": "Stopped"
    },
    "lebai.joints": {
        "zh": "关节角度",
        "en": "Joint Angles"
    },
    "lebai.tcp": {
        "zh": "TCP位置",
        "en": "TCP Position"
    },
    "lebai.move_joint": {
        "zh": "关节运动",
        "en": "Move Joint"
    },
    "lebai.move_linear": {
        "zh": "直线运动",
        "en": "Move Linear"
    },
    "lebai.gripper": {
        "zh": "夹爪",
        "en": "Gripper"
    },
    "lebai.gripper.open": {
        "zh": "打开夹爪",
        "en": "Open Gripper"
    },
    "lebai.gripper.close": {
        "zh": "关闭夹爪",
        "en": "Close Gripper"
    },
    "lebai.suction": {
        "zh": "吸盘",
        "en": "Suction"
    },
    "lebai.suction.on": {
        "zh": "开启吸盘",
        "en": "Suction On"
    },
    "lebai.suction.off": {
        "zh": "关闭吸盘",
        "en": "Suction Off"
    },

    # ==========================================================================
    # Dual Arm / 双臂
    # ==========================================================================
    "dual_arm.sync_mode": {
        "zh": "同步模式",
        "en": "Sync Mode"
    },
    "dual_arm.independent_mode": {
        "zh": "独立模式",
        "en": "Independent Mode"
    },
    "dual_arm.mirror_mode": {
        "zh": "镜像模式",
        "en": "Mirror Mode"
    },
    "dual_arm.arm_control": {
        "zh": "手臂控制",
        "en": "Arm Control"
    },
    "dual_arm.enable_left": {
        "zh": "使能左臂",
        "en": "Enable Left"
    },
    "dual_arm.disable_left": {
        "zh": "禁用左臂",
        "en": "Disable Left"
    },
    "dual_arm.enable_right": {
        "zh": "使能右臂",
        "en": "Enable Right"
    },
    "dual_arm.disable_right": {
        "zh": "禁用右臂",
        "en": "Disable Right"
    },
    "dual_arm.auto_reenable": {
        "zh": "自动重新使能",
        "en": "Auto re-enable"
    },
    "dual_arm.auto_reenable_sec": {
        "zh": "秒后",
        "en": "sec"
    },
    "dual_arm.auto_disable": {
        "zh": "自动禁用",
        "en": "Auto disable"
    },
    "dual_arm.auto_disable_sec": {
        "zh": "秒后",
        "en": "sec"
    },
    "dual_arm.auto_cycle_start": {
        "zh": "启动循环",
        "en": "Start"
    },
    "dual_arm.auto_cycle_stop": {
        "zh": "停止循环",
        "en": "Stop"
    },
    "dual_arm.auto_cycle_reset": {
        "zh": "重置循环",
        "en": "Reset"
    },
    "dual_arm.record_on_enable": {
        "zh": "使能后录制",
        "en": "Record on enable"
    },
    "dual_arm.pose_move_up": {
        "zh": "上移",
        "en": "Up"
    },
    "dual_arm.pose_move_down": {
        "zh": "下移",
        "en": "Down"
    },
    "dual_arm.move_to_step": {
        "zh": "移至步骤",
        "en": "Move to Step"
    },
    "dual_arm.pose_drag_title": {
        "zh": "移动或复制点位",
        "en": "Move or Copy Pose"
    },
    "dual_arm.pose_drag_msg": {
        "zh": "将点位 \"{pose}\" 放到步骤 \"{step}\"？",
        "en": "Place pose \"{pose}\" into step \"{step}\"?"
    },
    "dual_arm.pose_drag_move": {
        "zh": "移动",
        "en": "Move"
    },
    "dual_arm.pose_drag_copy": {
        "zh": "复制",
        "en": "Copy"
    },
    "dual_arm.get_position": {
        "zh": "获取位置",
        "en": "Get Position"
    },
    "dual_arm.set_to_zero": {
        "zh": "关节归零",
        "en": "Set Joints to Zero"
    },
    "dual_arm.move_to_joints": {
        "zh": "移动到关节",
        "en": "Move to Joints"
    },
    "dual_arm.copy_current": {
        "zh": "复制当前位置",
        "en": "Copy Current"
    },
    "dual_arm.get_both_positions": {
        "zh": "获取双臂位置",
        "en": "Get Both Positions"
    },
    "dual_arm.set_both_zero": {
        "zh": "双臂关节归零",
        "en": "Set Both Joints to Zero"
    },
    "dual_arm.confirm_set_zero": {
        "zh": "确定要将此手臂的所有关节移动到零位吗？",
        "en": "Are you sure to move all joints of this arm to zero position?"
    },
    "dual_arm.confirm_set_both_zero": {
        "zh": "确定要将双臂的所有关节都移动到零位吗？",
        "en": "Are you sure to move all joints of both arms to zero position?"
    },
    "dual_arm.finger_control": {
        "zh": "手指控制",
        "en": "Finger Control"
    },
    "dual_arm.presets": {
        "zh": "预设动作",
        "en": "Presets"
    },
    "dual_arm.touch_sensor": {
        "zh": "触摸传感器",
        "en": "Touch Sensor"
    },
    "dual_arm.send_position": {
        "zh": "发送位置",
        "en": "Send Position"
    },
    "dual_arm.set_all_zero": {
        "zh": "全部设为0",
        "en": "Set All to 0"
    },
    "dual_arm.speed": {
        "zh": "速度",
        "en": "Speed"
    },
    "dual_arm.accel": {
        "zh": "加速度",
        "en": "Accel"
    },
    "dual_arm.torque": {
        "zh": "扭矩",
        "en": "Torque"
    },
    "dual_arm.steps": {
        "zh": "步骤",
        "en": "Steps"
    },
    "dual_arm.poses_in_step": {
        "zh": "步骤中的点位",
        "en": "Poses in Step"
    },
    "dual_arm.record_pose": {
        "zh": "录制点位",
        "en": "Record Pose"
    },
    "dual_arm.record_arm": {
        "zh": "手臂",
        "en": "Arm"
    },
    "dual_arm.include_hand": {
        "zh": "包含手指",
        "en": "Include Hand"
    },
    "dual_arm.include_gripper": {
        "zh": "包含夹爪",
        "en": "Include Gripper"
    },
    "dual_arm.execute_pose": {
        "zh": "执行点位",
        "en": "Execute Pose"
    },
    "dual_arm.execute_step": {
        "zh": "执行步骤",
        "en": "Execute Step"
    },
    "dual_arm.execute_all_steps": {
        "zh": "执行全部步骤",
        "en": "Execute All Steps"
    },
    "dual_arm.add_step": {
        "zh": "添加步骤",
        "en": "Add Step"
    },
    "dual_arm.delete_step": {
        "zh": "删除步骤",
        "en": "Delete Step"
    },
    "dual_arm.rename_step": {
        "zh": "重命名",
        "en": "Rename"
    },
    "dual_arm.save_step": {
        "zh": "导出步骤",
        "en": "Export Step"
    },
    "dual_arm.rename_step_prompt": {
        "zh": "输入新名称:",
        "en": "Enter new name:"
    },
    "dual_arm.step_saved": {
        "zh": "步骤已导出: {name}",
        "en": "Step exported: {name}"
    },
    "dual_arm.delay_sec": {
        "zh": "延迟(秒)",
        "en": "Delay (s)"
    },
    "dual_arm.record_from_hand_tab": {
        "zh": "录制当前手臂+手指为点位",
        "en": "Record current arms + fingers as pose"
    },
    "dual_arm.record_from_gripper_tab": {
        "zh": "录制当前手臂+夹爪为点位",
        "en": "Record current arms + gripper as pose"
    },
    "dual_arm.gesture_open": {
        "zh": "张开",
        "en": "Open"
    },
    "dual_arm.gesture_close": {
        "zh": "握拳",
        "en": "Close"
    },
    "dual_arm.gesture_pinch": {
        "zh": "捏",
        "en": "Pinch"
    },
    "dual_arm.gesture_point": {
        "zh": "指向",
        "en": "Point"
    },
    "dual_arm.gesture_fist": {
        "zh": "握拳",
        "en": "Fist"
    },
    "dual_arm.gesture_half": {
        "zh": "半开",
        "en": "Half (128)"
    },
    "dual_arm.gesture_grab": {
        "zh": "抓取",
        "en": "Grab (50)"
    },
    "dual_arm.msg_select_step_first": {
        "zh": "请先选择步骤",
        "en": "Select a step first"
    },
    "dual_arm.msg_select_or_add_step": {
        "zh": "请选择或添加步骤",
        "en": "Select or add a step first"
    },
    "dual_arm.msg_select_pose_execute": {
        "zh": "请选择要执行的点位",
        "en": "Select a pose to execute"
    },
    "dual_arm.msg_step_has_no_poses": {
        "zh": "该步骤中没有点位",
        "en": "Step has no poses"
    },
    "dual_arm.msg_delete_step_confirm": {
        "zh": "确定要删除步骤「{name}」吗？",
        "en": "Delete step '{name}'?"
    },
    "dual_arm.msg_delete_pose_confirm": {
        "zh": "确定要删除点位「{name}」吗？",
        "en": "Delete pose '{name}'?"
    },
    "dual_arm.msg_delete_poses_confirm": {
        "zh": "确定要删除以下 {count} 个点位吗？\n{names}",
        "en": "Delete {count} poses?\n{names}"
    },
    "dual_arm.msg_recorded_pose": {
        "zh": "已录制点位「{name}」（手臂+手指）",
        "en": "Recorded pose '{name}' (arms + fingers)"
    },
    "dual_arm.file_label": {
        "zh": "文件:",
        "en": "File:"
    },
    "dual_arm.load_file": {
        "zh": "加载文件",
        "en": "Load File"
    },
    "dual_arm.save_file": {
        "zh": "保存文件",
        "en": "Save File"
    },
    "dual_arm.save_as": {
        "zh": "另存为",
        "en": "Save As"
    },
    "dual_arm.file_loaded": {
        "zh": "已加载文件: {name}",
        "en": "Loaded file: {name}"
    },
    "dual_arm.file_saved": {
        "zh": "已保存文件: {name}",
        "en": "Saved file: {name}"
    },
    "dual_arm.replace_or_append": {
        "zh": "替换当前内容？（否=追加）",
        "en": "Replace current content? (No = Append)"
    },
    "dual_arm.smooth_replay": {
        "zh": "平滑播放",
        "en": "Smooth"
    },
    "dual_arm.touch_not_connected": {
        "zh": "手未连接 — 无触觉数据",
        "en": "Hand not connected — no touch data"
    },
    "dual_arm.touch_no_sensor": {
        "zh": "此手未安装矩阵触觉传感器",
        "en": "No matrix tactile sensor on this hand"
    },
    "dual_arm.touch_querying": {
        "zh": "正在查询触觉传感器…",
        "en": "Querying tactile sensor…"
    },
    "dual_arm.smooth_replay_tip": {
        "zh": "连续流式播放各位姿，位姿之间不停顿（关节跟随模式）",
        "en": "Stream poses continuously without stopping between them (joint-follow mode)"
    },
    "dual_arm.contact_limit": {
        "zh": "接触力限",
        "en": "Contact limit"
    },
    "dual_arm.contact_limit_tip": {
        "zh": "平滑播放时的力矩阈值；0=关闭。超过阈值手臂会减速并保持，松开后继续（不会急停）。请参考右侧实时力矩进行标定。",
        "en": "Torque threshold during smooth replay; 0 = off. Above it the arm slows and holds, then resumes when released (no e-stop). Use the live torque readout to calibrate."
    },
    "dual_arm.live_torque": {
        "zh": "力矩",
        "en": "Torque"
    },
    "dual_arm.live_torque_tip": {
        "zh": "两臂关节最大力矩（实时）。用于标定接触力限。",
        "en": "Live max joint torque across both arms. Use it to calibrate the contact limit."
    },
    "linker_hand.connection": {
        "zh": "连接设置",
        "en": "Connection"
    },
    "linker_hand.can_interface": {
        "zh": "CAN接口:",
        "en": "CAN:"
    },
    "linker_hand.connect": {
        "zh": "连接",
        "en": "Connect"
    },
    "linker_hand.disconnect": {
        "zh": "断开",
        "en": "Disconnect"
    },
    "linker_hand.setup_can": {
        "zh": "设置CAN",
        "en": "Setup CAN"
    },
    "linker_hand.status_disconnected": {
        "zh": "未连接",
        "en": "Disconnected"
    },
    "linker_hand.status_connecting": {
        "zh": "连接中...",
        "en": "Connecting..."
    },
    "linker_hand.status_connected": {
        "zh": "已连接",
        "en": "Connected"
    },
    "linker_hand.status_can_setup": {
        "zh": "正在设置CAN...",
        "en": "Setting up CAN..."
    },
    "linker_hand.status_can_ready": {
        "zh": "CAN {iface} 已就绪",
        "en": "CAN {iface} ready"
    },
    "linker_hand.status_can_failed": {
        "zh": "CAN设置失败",
        "en": "CAN setup failed"
    },
    "common.apply": {
        "zh": "应用",
        "en": "Apply"
    },
    "common.info": {
        "zh": "信息",
        "en": "Information"
    },

    # ==========================================================================
    # Teleop / 遥操作
    # ==========================================================================
    "teleop.mode": {
        "zh": "连接模式",
        "en": "Connection Mode"
    },
    "teleop.mode.local": {
        "zh": "本地Docker",
        "en": "Local Docker"
    },
    "teleop.mode.remote_lan": {
        "zh": "局域网远程",
        "en": "Remote LAN"
    },
    "teleop.mode.remote_wan": {
        "zh": "跨网络远程",
        "en": "Remote WAN"
    },
    "teleop.ros_host": {
        "zh": "ROS主机",
        "en": "ROS Host"
    },
    "teleop.ros_port": {
        "zh": "ROS端口",
        "en": "ROS Port"
    },
    "teleop.start_teleop": {
        "zh": "启动遥操作",
        "en": "Start Teleop"
    },
    "teleop.stop_teleop": {
        "zh": "停止遥操作",
        "en": "Stop Teleop"
    },
    "teleop.record": {
        "zh": "录制轨迹",
        "en": "Record"
    },
    "teleop.playback": {
        "zh": "回放轨迹",
        "en": "Playback"
    },

    # ==========================================================================
    # Wok / 炒锅
    # ==========================================================================
    "wok.working_position": {
        "zh": "工作位",
        "en": "Working Position"
    },
    "wok.pour_position": {
        "zh": "倒出位",
        "en": "Pour Position"
    },
    "wok.wash_position": {
        "zh": "清洗位",
        "en": "Wash Position"
    },
    "wok.temperature": {
        "zh": "温度",
        "en": "Temperature"
    },
    "wok.heating": {
        "zh": "加热",
        "en": "Heating"
    },
    "wok.stirring": {
        "zh": "搅拌",
        "en": "Stirring"
    },
    "wok.stir_speed": {
        "zh": "搅拌速度",
        "en": "Stir Speed"
    },
    "wok.wok_up": {
        "zh": "锅上升",
        "en": "Wok Up"
    },
    "wok.wok_down": {
        "zh": "锅下降",
        "en": "Wok Down"
    },
    "wok.move_up": {
        "zh": "升到最高",
        "en": "Max Up"
    },
    "wok.loading_position": {
        "zh": "上料位",
        "en": "Loading Position"
    },
    "wok.position_feedback": {
        "zh": "位置反馈",
        "en": "Position Feedback"
    },
    "wok.at_stirfry": {
        "zh": "炒菜位",
        "en": "Stir-Fry"
    },
    "wok.at_pour": {
        "zh": "倒出位",
        "en": "Pour"
    },
    "wok.at_loading": {
        "zh": "上料位",
        "en": "Loading"
    },
    "wok.recipe": {
        "zh": "菜谱控制",
        "en": "Recipe Control"
    },
    "wok.recipe_id": {
        "zh": "菜谱编号",
        "en": "Recipe ID"
    },
    "wok.run_recipe": {
        "zh": "运行菜谱",
        "en": "Run Recipe"
    },
    "wok.stop_recipe": {
        "zh": "停止菜谱",
        "en": "Stop Recipe"
    },
    "wok.sauce": {
        "zh": "调料",
        "en": "Sauce"
    },
    "wok.sauce_id": {
        "zh": "调料编号",
        "en": "Sauce ID"
    },
    "wok.pulse_value": {
        "zh": "脉冲值",
        "en": "Pulse Value"
    },
    "wok.dispense": {
        "zh": "出料",
        "en": "Dispense"
    },
    "wok.timer": {
        "zh": "定时 (秒)",
        "en": "Timer (sec)"
    },
    "wok.countdown": {
        "zh": "剩余",
        "en": "Remaining"
    },
    "wok.timer_zero_warning": {
        "zh": "定时器为0，炒锅将运行完整配方时间。确定继续吗？",
        "en": "Timer is 0 — the wok will run for the full recipe duration. Continue?"
    },

    # ==========================================================================
    # Gripper / 夹爪
    # ==========================================================================
    "hardware.gripper": {
        "zh": "夹爪",
        "en": "Gripper"
    },
    "tab.gripper": {
        "zh": "夹爪",
        "en": "Gripper"
    },
    "gripper.opening": {
        "zh": "开度控制",
        "en": "Opening Control"
    },
    "gripper.force": {
        "zh": "力度控制",
        "en": "Force Control"
    },
    "gripper.speed": {
        "zh": "速度",
        "en": "Speed"
    },
    "gripper.target": {
        "zh": "目标开度",
        "en": "Target Opening"
    },
    "gripper.target_force": {
        "zh": "目标力度",
        "en": "Target Force"
    },
    "gripper.open": {
        "zh": "打开",
        "en": "Open"
    },
    "gripper.close": {
        "zh": "关闭",
        "en": "Close"
    },
    "gripper.light": {
        "zh": "轻",
        "en": "Light"
    },
    "gripper.medium": {
        "zh": "中",
        "en": "Medium"
    },
    "gripper.strong": {
        "zh": "强",
        "en": "Strong"
    },
    "gripper.max": {
        "zh": "最大",
        "en": "Max"
    },
    "gripper.current_status": {
        "zh": "当前状态",
        "en": "Current Status"
    },
    "gripper.position": {
        "zh": "位置",
        "en": "Position"
    },
    "gripper.torque": {
        "zh": "扭矩",
        "en": "Torque"
    },

    # ==========================================================================
    # Episode Orchestrator / 编排器
    # ==========================================================================
    "episode.episodes": {
        "zh": "剧集列表",
        "en": "Episodes"
    },
    "episode.actions": {
        "zh": "动作列表",
        "en": "Actions"
    },
    "episode.playback": {
        "zh": "播放控制",
        "en": "Playback"
    },
    "episode.play_action": {
        "zh": "播放",
        "en": "Play"
    },
    "episode.play_episode": {
        "zh": "播放当前剧集",
        "en": "Play Episode"
    },
    "episode.play_all": {
        "zh": "播放全部",
        "en": "Play All"
    },
    "episode.stop": {
        "zh": "停止",
        "en": "Stop"
    },
    "episode.emergency_stop": {
        "zh": "紧急停止",
        "en": "Emergency Stop"
    },
    "episode.save": {
        "zh": "保存",
        "en": "Save"
    },
    "episode.load": {
        "zh": "加载",
        "en": "Load"
    },
    "episode.rename": {
        "zh": "重命名",
        "en": "Rename"
    },
    "episode.name": {
        "zh": "名称",
        "en": "Name"
    },
    "episode.editor": {
        "zh": "动作编辑器",
        "en": "Action Editor"
    },
    "episode.component": {
        "zh": "组件",
        "en": "Component"
    },
    "episode.action_type": {
        "zh": "动作类型",
        "en": "Action Type"
    },
    "episode.file": {
        "zh": "文件",
        "en": "File"
    },
    "episode.step": {
        "zh": "步骤",
        "en": "Step"
    },
    "episode.wok_cmd": {
        "zh": "炒锅命令",
        "en": "Wok Command"
    },
    "episode.dependency": {
        "zh": "依赖关系",
        "en": "Depends On"
    },
    "episode.target": {
        "zh": "目标组件",
        "en": "Target"
    },
    "episode.apply": {
        "zh": "应用更改",
        "en": "Apply Changes"
    },
    "episode.no_actions": {
        "zh": "当前剧集没有动作",
        "en": "No actions in this episode"
    },
    "episode.saved": {
        "zh": "剧集已保存",
        "en": "Episode saved"
    },
    "episode.add": {
        "zh": "添加",
        "en": "Add"
    },
    "episode.remove": {
        "zh": "删除",
        "en": "Remove"
    },
    "episode.move_up": {
        "zh": "上移",
        "en": "Up"
    },
    "episode.move_down": {
        "zh": "下移",
        "en": "Down"
    },
    "episode.new_action": {
        "zh": "新建动作",
        "en": "New Action"
    },
    "episode.add_action": {
        "zh": "添加动作",
        "en": "Add Action"
    },
    "episode.remove_action": {
        "zh": "删除",
        "en": "Remove"
    },
    "episode.wait_between_episodes": {
        "zh": "集间等待 (秒)",
        "en": "Wait between episodes (s)"
    },
    "episode.wait_between_actions": {
        "zh": "动作间等待 (秒)",
        "en": "Wait between actions (s)"
    },
    "episode.select_episode_first": {
        "zh": "请先选择一个集",
        "en": "Please select an episode first"
    },
    "episode.current_action": {
        "zh": "当前动作",
        "en": "Current Action"
    },
    "episode.idle": {
        "zh": "空闲",
        "en": "Idle"
    },
    "episode.remaining": {
        "zh": "剩余",
        "en": "Remaining"
    },
    "episode.duration": {
        "zh": "持续时间 (秒)",
        "en": "Duration (s)"
    },
    "episode.speed": {
        "zh": "速度 (0=原值)",
        "en": "Speed (0=pose)"
    },
    "episode.accel": {
        "zh": "加速度 (0=原值)",
        "en": "Accel (0=pose)"
    },
    "episode.pose_delay": {
        "zh": "点位间隔 (秒)",
        "en": "Pose Delay (s)"
    },
    "episode.waiting": {
        "zh": "等待中",
        "en": "Waiting"
    },
    "episode.group": {
        "zh": "分组",
        "en": "Group"
    },
    "episode.ungroup": {
        "zh": "取消分组",
        "en": "Ungroup"
    },
    "episode.rename_group": {
        "zh": "重命名分组",
        "en": "Rename Grp"
    },
    "episode.group_name": {
        "zh": "分组名称",
        "en": "Group Name"
    },
    "episode.select_two_or_more": {
        "zh": "请选择两个或以上的动作来创建分组",
        "en": "Select two or more actions to create a group"
    },
    "episode.cannot_merge_groups": {
        "zh": "不能合并来自不同分组的动作",
        "en": "Cannot merge actions from different groups"
    },
    "episode.new_group": {
        "zh": "+ 新分组",
        "en": "+ New Group"
    },
    "episode.ungrouped": {
        "zh": "(无)",
        "en": "(None)"
    },

    # ==========================================================================
    # Inventory / 库存
    # ==========================================================================
    "inventory.grid": {
        "zh": "库存网格",
        "en": "Inventory Grid"
    },
    "inventory.slot": {
        "zh": "库位",
        "en": "Slot"
    },
    "inventory.empty": {
        "zh": "空",
        "en": "Empty"
    },
    "inventory.ingredient": {
        "zh": "食材",
        "en": "Ingredient"
    },
    "inventory.quantity": {
        "zh": "数量",
        "en": "Quantity"
    },
    "inventory.add": {
        "zh": "添加食材",
        "en": "Add Ingredient"
    },
    "inventory.remove": {
        "zh": "移除食材",
        "en": "Remove Ingredient"
    },

    # ==========================================================================
    # Recipes / 配方
    # ==========================================================================
    "recipe.title": {
        "zh": "配方管理",
        "en": "Recipe Management"
    },
    "recipe.name": {
        "zh": "配方名称",
        "en": "Recipe Name"
    },
    "recipe.steps": {
        "zh": "步骤",
        "en": "Steps"
    },
    "recipe.execute": {
        "zh": "执行配方",
        "en": "Execute Recipe"
    },
    "recipe.current_step": {
        "zh": "当前步骤",
        "en": "Current Step"
    },

    # ==========================================================================
    # Orders / 订单
    # ==========================================================================
    "order.title": {
        "zh": "订单管理",
        "en": "Order Management"
    },
    "order.queue": {
        "zh": "订单队列",
        "en": "Order Queue"
    },
    "order.new": {
        "zh": "新建订单",
        "en": "New Order"
    },
    "order.processing": {
        "zh": "处理中",
        "en": "Processing"
    },
    "order.completed": {
        "zh": "已完成",
        "en": "Completed"
    },

    # ==========================================================================
    # Tabs / 标签页
    # ==========================================================================
    "tab.gantry_lebai": {
        "zh": "龙门架+乐白",
        "en": "Gantry+Lebai"
    },
    "tab.dual_arm": {
        "zh": "灵心双臂",
        "en": "Dual Arm"
    },
    "tab.wok": {
        "zh": "炒锅",
        "en": "Wok"
    },
    "tab.inventory": {
        "zh": "库存",
        "en": "Inventory"
    },
    "tab.orders": {
        "zh": "订单",
        "en": "Orders"
    },
    "tab.recipes": {
        "zh": "配方",
        "en": "Recipes"
    },
    "tab.dexhand": {
        "zh": "灵巧手",
        "en": "Dexhand"
    },
    "tab.master_teleop": {
        "zh": "主臂遥操作",
        "en": "Teleoperation"
    },
    "tab.recording": {
        "zh": "VLA数据录制",
        "en": "VLA Recording"
    },
    "tab.episode": {
        "zh": "编排器",
        "en": "Episode"
    },

    # ==========================================================================
    # Master Arm Teleoperation / 主臂遥操作
    # ==========================================================================
    "master_teleop.ros_connection": {
        "zh": "ROS2 连接 (通过 rosbridge)",
        "en": "ROS2 Connection (via rosbridge)"
    },
    "master_teleop.host": {
        "zh": "主机",
        "en": "Host"
    },
    "master_teleop.port": {
        "zh": "端口",
        "en": "Port"
    },
    "master_teleop.control": {
        "zh": "遥操作控制",
        "en": "Teleoperation Control"
    },
    "master_teleop.left_arm": {
        "zh": "左臂",
        "en": "Left Arm"
    },
    "master_teleop.right_arm": {
        "zh": "右臂",
        "en": "Right Arm"
    },
    "master_teleop.start": {
        "zh": "开始遥操作",
        "en": "Start Teleop"
    },
    "master_teleop.stop": {
        "zh": "停止遥操作",
        "en": "Stop Teleop"
    },
    "master_teleop.motion_settings": {
        "zh": "运动设置",
        "en": "Motion Settings"
    },
    "master_teleop.max_speed": {
        "zh": "最大速度",
        "en": "Max Speed"
    },
    "master_teleop.max_accel": {
        "zh": "最大加速度",
        "en": "Max Accel"
    },
    "master_teleop.smoothing": {
        "zh": "平滑系数",
        "en": "Smoothing"
    },
    "master_teleop.deg_to_rad": {
        "zh": "度→弧度",
        "en": "Deg→Rad"
    },
    "master_teleop.apply_negation": {
        "zh": "应用取反",
        "en": "Apply Negation"
    },
    "master_teleop.debug": {
        "zh": "调试",
        "en": "Debug"
    },
    "master_teleop.calibrate": {
        "zh": "校准偏移",
        "en": "Calibrate Offsets"
    },
    "master_teleop.not_calibrated": {
        "zh": "未校准",
        "en": "Not calibrated"
    },
    "master_teleop.calibrated": {
        "zh": "已校准",
        "en": "Calibrated"
    },
    "master_teleop.calibration": {
        "zh": "校准",
        "en": "Calibration"
    },
    "master_teleop.calibration_failed": {
        "zh": "校准失败",
        "en": "Calibration failed"
    },
    "master_teleop.trajectory_recording": {
        "zh": "轨迹录制",
        "en": "Trajectory Recording"
    },
    "master_teleop.name": {
        "zh": "名称",
        "en": "Name"
    },
    "master_teleop.start_recording": {
        "zh": "开始录制",
        "en": "Start Recording"
    },
    "master_teleop.stop_recording": {
        "zh": "停止录制",
        "en": "Stop Recording"
    },
    "master_teleop.recording": {
        "zh": "录制中",
        "en": "Recording"
    },
    "master_teleop.record_left": {
        "zh": "录制左臂",
        "en": "Record Left"
    },
    "master_teleop.record_right": {
        "zh": "录制右臂",
        "en": "Record Right"
    },
    "master_teleop.sample_rate": {
        "zh": "采样率",
        "en": "Sample Rate"
    },
    "master_teleop.status": {
        "zh": "主臂状态",
        "en": "Master Arm Status"
    },
    "master_teleop.left": {
        "zh": "左",
        "en": "Left"
    },
    "master_teleop.right": {
        "zh": "右",
        "en": "Right"
    },
    "master_teleop.no_data": {
        "zh": "无数据",
        "en": "No data"
    },
    "master_teleop.connection_failed": {
        "zh": "连接失败",
        "en": "Connection failed"
    },
    "master_teleop.robot_not_connected": {
        "zh": "机器人未连接，请先连接机器人",
        "en": "Robot not connected. Please connect to robot first."
    },
    "master_teleop.ros_not_connected": {
        "zh": "ROS未连接，请先连接ROS",
        "en": "Not connected to ROS. Please connect first."
    },
    "master_teleop.no_master_data": {
        "zh": "未收到主臂数据，请先移动主臂",
        "en": "No master arm data received yet. Move the master arm first."
    },
    "master_teleop.select_arm": {
        "zh": "请至少选择一个手臂进行遥操作",
        "en": "Please select at least one arm for teleoperation."
    },
    "master_teleop.start_teleop_first": {
        "zh": "请先开始遥操作再录制",
        "en": "Start teleoperation first before recording."
    },
    "master_teleop.too_short": {
        "zh": "录制太短",
        "en": "Too short!"
    },
    "master_teleop.recording_too_short": {
        "zh": "录制太短，未保存",
        "en": "Recording too short. Not saved."
    },
    "master_teleop.saved": {
        "zh": "已保存",
        "en": "Saved"
    },
    "master_teleop.nothing_saved": {
        "zh": "未保存",
        "en": "Nothing saved"
    },
    "master_teleop.docker_control": {
        "zh": "主臂 Docker 控制",
        "en": "Master Arm Docker"
    },
    "master_teleop.start_docker": {
        "zh": "启动 Docker",
        "en": "Start Docker"
    },
    "master_teleop.stop_docker": {
        "zh": "停止 Docker",
        "en": "Stop Docker"
    },
    "master_teleop.docker_running": {
        "zh": "Docker 运行中",
        "en": "Docker Running"
    },
    "master_teleop.docker_stopped": {
        "zh": "Docker 已停止",
        "en": "Docker Stopped"
    },
    "master_teleop.docker_starting": {
        "zh": "启动中...",
        "en": "Starting..."
    },
    "master_teleop.docker_stopping": {
        "zh": "停止中...",
        "en": "Stopping..."
    },
    "master_teleop.docker_failed": {
        "zh": "失败: {reason}",
        "en": "Failed: {reason}"
    },
    "master_teleop.roslibpy_not_installed": {
        "zh": "roslibpy 未安装",
        "en": "roslibpy not installed"
    },
    "master_teleop.roslibpy_install_hint": {
        "zh": "roslibpy 未安装。\n请运行: pip install roslibpy",
        "en": "roslibpy not installed.\nInstall with: pip install roslibpy"
    },
    "master_teleop.invalid_port": {
        "zh": "无效的端口号",
        "en": "Invalid port number"
    },

    # ==========================================================================
    # VLA Recording / VLA数据录制
    # ==========================================================================
    "vla.title": {
        "zh": "VLA 数据录制",
        "en": "VLA Data Recording"
    },
    "vla.task_id": {
        "zh": "任务ID",
        "en": "Task ID"
    },
    "vla.new_task": {
        "zh": "新建任务",
        "en": "New Task"
    },
    "vla.arm_side": {
        "zh": "操作臂",
        "en": "Arm"
    },
    "vla.language_inst": {
        "zh": "语言指令",
        "en": "Language Instruction"
    },
    "vla.sample_rate": {
        "zh": "采样率",
        "en": "Sample Rate"
    },
    "vla.start_episode": {
        "zh": "开始录制",
        "en": "Start Episode"
    },
    "vla.stop_save": {
        "zh": "停止并保存",
        "en": "Stop & Save"
    },
    "vla.discard": {
        "zh": "丢弃",
        "en": "Discard"
    },
    "vla.pause": {
        "zh": "暂停",
        "en": "Pause"
    },
    "vla.resume": {
        "zh": "继续",
        "en": "Resume"
    },
    "vla.export_selected": {
        "zh": "导出选中",
        "en": "Export Selected"
    },
    "vla.export_all_npz": {
        "zh": "导出全部(NPZ)",
        "en": "Export All (NPZ)"
    },
    "vla.delete": {
        "zh": "删除",
        "en": "Delete"
    },
    "vla.open_folder": {
        "zh": "打开文件夹",
        "en": "Open Folder"
    },
    "vla.status_idle": {
        "zh": "空闲",
        "en": "IDLE"
    },
    "vla.status_recording": {
        "zh": "录制中",
        "en": "RECORDING"
    },
    "vla.status_paused": {
        "zh": "已暂停",
        "en": "PAUSED"
    },
    "vla.episode": {
        "zh": "回合",
        "en": "Episode"
    },
    "vla.steps": {
        "zh": "步数",
        "en": "Steps"
    },
    "vla.duration": {
        "zh": "时长",
        "en": "Duration"
    },
    "vla.no_robot": {
        "zh": "机器人未连接",
        "en": "Robot not connected"
    },
    "vla.no_teleop": {
        "zh": "遥操未连接",
        "en": "Teleop not connected"
    },
    "vla.no_camera": {
        "zh": "摄像头未启动",
        "en": "Camera not running"
    },
    "vla.live_data": {
        "zh": "实时数据",
        "en": "Live Data"
    },
    "vla.state_action": {
        "zh": "状态与动作",
        "en": "State & Action"
    },
    "vla.camera_desk": {
        "zh": "桌面摄像头",
        "en": "Desk Cam"
    },
    "vla.camera_wrist": {
        "zh": "腕部摄像头",
        "en": "Wrist Cam"
    },
    "vla.column_task": {
        "zh": "任务",
        "en": "Task"
    },
    "vla.column_date": {
        "zh": "日期",
        "en": "Date"
    },
    "vla.column_size": {
        "zh": "大小",
        "en": "Size"
    },
    "vla.export_label": {
        "zh": "导出：",
        "en": "Export:"
    },
    "vla.status_saving": {
        "zh": "保存中",
        "en": "SAVING"
    },
    "vla.status_error": {
        "zh": "错误",
        "en": "ERROR"
    },
    "vla.camera_ok": {
        "zh": "摄像头: {fps:.0f}fps",
        "en": "Camera: {fps:.0f}fps"
    },
    "vla.robot_ok": {
        "zh": "机器人: 正常",
        "en": "Robot: OK"
    },
    "vla.teleop_ok": {
        "zh": "遥操: 正常",
        "en": "Teleop: OK"
    },
    "vla.msg_task_required": {
        "zh": "任务ID为必填项",
        "en": "Task ID is required"
    },
    "vla.msg_lang_required": {
        "zh": "语言指令为必填项",
        "en": "Language instruction is required"
    },
    "vla.confirm_discard": {
        "zh": "丢弃当前回合？",
        "en": "Discard current episode?"
    },
    "vla.msg_no_episodes": {
        "zh": "未选择回合",
        "en": "No episodes selected"
    },
    "vla.msg_already_hdf5": {
        "zh": "回合已保存为HDF5格式。\n位置: {path}",
        "en": "Episodes are already saved as HDF5.\nLocation: {path}"
    },
    "vla.msg_export_success": {
        "zh": "任务 {task} 已导出NPZ",
        "en": "Exported NPZ for task: {task}"
    },
    "vla.msg_export_failed": {
        "zh": "NPZ导出失败: {task}",
        "en": "NPZ export failed for task: {task}"
    },
    "vla.msg_task_first": {
        "zh": "请先输入任务ID",
        "en": "Enter a task ID first"
    },
    "vla.msg_npz_failed": {
        "zh": "NPZ导出失败",
        "en": "NPZ export failed"
    },
    "vla.confirm_delete": {
        "zh": "删除 {count} 个回合？",
        "en": "Delete {count} episode(s)?"
    },
    "vla.input_task_id": {
        "zh": "输入任务ID：",
        "en": "Enter task ID:"
    },
    "vla.hand_closed": {
        "zh": "关闭",
        "en": "CLOSED"
    },
    "vla.hand_open": {
        "zh": "打开",
        "en": "OPEN"
    },
    "vla.robot_status": {
        "zh": "机器人: {status}",
        "en": "Robot: {status}"
    },
    "vla.teleop_status": {
        "zh": "遥操: {status}",
        "en": "Teleop: {status}"
    },
    "vla.location": {
        "zh": "位置: {path}",
        "en": "Location: {path}"
    },

    # LeRobot export
    "vla.export_lerobot": {
        "zh": "导出 LeRobot",
        "en": "Export LeRobot"
    },
    "vla.lerobot_exporting": {
        "zh": "LeRobot 导出中 ({progress})...",
        "en": "LeRobot exporting ({progress})..."
    },
    "vla.lerobot_export_done": {
        "zh": "LeRobot 数据集导出完成",
        "en": "LeRobot dataset export complete"
    },
    "vla.lerobot_export_failed": {
        "zh": "LeRobot 导出失败",
        "en": "LeRobot export failed"
    },
    "vla.lerobot_dataset_name": {
        "zh": "数据集名称",
        "en": "Dataset Name"
    },
    "vla.lerobot_action_mode": {
        "zh": "动作模式",
        "en": "Action Mode"
    },
    "vla.lerobot_delta": {
        "zh": "增量模式",
        "en": "Delta"
    },
    "vla.lerobot_absolute": {
        "zh": "绝对模式",
        "en": "Absolute"
    },

    # Hand mode
    "vla.hand_mode": {
        "zh": "手部模式",
        "en": "Hand Mode"
    },
    "vla.hand_binary": {
        "zh": "二值 (开/闭)",
        "en": "Binary (open/close)"
    },
    "vla.hand_full_dof": {
        "zh": "全自由度 (6DOF)",
        "en": "Full DOF (6DOF)"
    },

    # Export folder
    "vla.open_export_folder": {
        "zh": "打开导出目录",
        "en": "Open Export Folder"
    },
    "vla.label_tcp": {
        "zh": "TCP",
        "en": "TCP"
    },
    "vla.label_quat": {
        "zh": "四元数",
        "en": "Quat"
    },
    "vla.label_joints": {
        "zh": "关节",
        "en": "Joints"
    },
    "vla.label_hand": {
        "zh": "手部",
        "en": "Hand"
    },
    "vla.label_delta_pos": {
        "zh": "Δ 位置",
        "en": "Δ Pos"
    },
    "vla.label_delta_rot": {
        "zh": "Δ 旋转",
        "en": "Δ Rot"
    },
    "vla.label_target": {
        "zh": "目标",
        "en": "Target"
    },

    # Streaming LeRobot recording
    "vla.config_title": {
        "zh": "录制配置",
        "en": "Recording Configuration"
    },
    "vla.control_title": {
        "zh": "录制控制",
        "en": "Recording Controls"
    },
    "vla.output": {
        "zh": "输出目录",
        "en": "Output"
    },
    "vla.start_recording": {
        "zh": "开始录制",
        "en": "Start Recording"
    },
    "vla.stop_recording": {
        "zh": "停止录制",
        "en": "Stop Recording"
    },
    "vla.new_trial": {
        "zh": "新建试验",
        "en": "New Trial"
    },
    "vla.new_trial_created": {
        "zh": "已创建新试验",
        "en": "New trial created"
    },
    "vla.robot_state": {
        "zh": "机器人状态",
        "en": "Robot State"
    },
    "vla.action": {
        "zh": "动作",
        "en": "Action"
    },
    "vla.camera_preview": {
        "zh": "摄像头预览",
        "en": "Camera Preview"
    },
    "vla.episode_list": {
        "zh": "回合列表",
        "en": "Episode List"
    },
    "vla.format_lerobot": {
        "zh": "LeRobot 格式",
        "en": "LeRobot Format"
    },
    "vla.no_camera_warning": {
        "zh": "未检测到摄像头！",
        "en": "No camera detected!"
    },
    "vla.continue_without_camera": {
        "zh": "是否继续录制（不包含视频）？",
        "en": "Continue recording without video?"
    },
    "vla.desk_camera_missing": {
        "zh": "桌面摄像头未启动",
        "en": "Desk camera not running"
    },
    "vla.wrist_camera_missing": {
        "zh": "腕部摄像头未启动",
        "en": "Wrist camera not running"
    },
    "vla.start_failed": {
        "zh": "启动录制失败",
        "en": "Failed to start recording"
    },
    "vla.discarded": {
        "zh": "已丢弃当前回合",
        "en": "Current episode discarded"
    },
    "vla.cannot_new_trial_while_recording": {
        "zh": "录制中无法新建试验",
        "en": "Cannot create new trial while recording"
    },
    "vla.select_to_delete": {
        "zh": "请选择要删除的回合",
        "en": "Please select episodes to delete"
    },
    "vla.confirm_delete_count": {
        "zh": "删除 {count} 个回合？",
        "en": "Delete {count} episode(s)?"
    },

    # ==========================================================================
    # Dexhand / 灵巧手
    # ==========================================================================
    "dexhand.title": {
        "zh": "灵巧手控制",
        "en": "Dexhand Control"
    },
    "dexhand.joint_control": {
        "zh": "关节控制",
        "en": "Joint Control"
    },
    "dexhand.force_grab": {
        "zh": "力控抓取",
        "en": "Force Grab"
    },
    "dexhand.touch_sensor": {
        "zh": "触摸传感器",
        "en": "Touch Sensor"
    },
    "dexhand.hand_type": {
        "zh": "手型",
        "en": "Hand Type"
    },
    "dexhand.open_hand": {
        "zh": "张开",
        "en": "Open"
    },
    "dexhand.close_hand": {
        "zh": "握拳",
        "en": "Close"
    },
    "dexhand.grasp": {
        "zh": "抓取",
        "en": "Grasp"
    },

    # ==========================================================================
    # Recording / 数据录制
    # ==========================================================================
    "recording.title": {
        "zh": "RL数据录制",
        "en": "RL Data Recording"
    },
    "recording.start": {
        "zh": "开始录制",
        "en": "Start Recording"
    },
    "recording.stop": {
        "zh": "停止录制",
        "en": "Stop Recording"
    },
    "recording.episode": {
        "zh": "回合",
        "en": "Episode"
    },
    "recording.points": {
        "zh": "数据点",
        "en": "Points"
    },
    "recording.export": {
        "zh": "导出",
        "en": "Export"
    },
    "recording.clear": {
        "zh": "清除",
        "en": "Clear"
    },

    # ==========================================================================
    # Panels / 面板
    # ==========================================================================
    "panel.camera": {
        "zh": "摄像头",
        "en": "Camera"
    },
    "panel.logs": {
        "zh": "操作日志",
        "en": "Operation Logs"
    },
    "panel.capture": {
        "zh": "拍照",
        "en": "Capture"
    },
    "panel.record": {
        "zh": "录像",
        "en": "Record"
    },
    "panel.clear_logs": {
        "zh": "清空日志",
        "en": "Clear Logs"
    },

    # ==========================================================================
    # Remote Control / 远程控制
    # ==========================================================================
    "remote.title": {
        "zh": "远程控制",
        "en": "Remote Control"
    },
    "remote.server_status": {
        "zh": "服务器状态",
        "en": "Server Status"
    },
    "remote.connected_clients": {
        "zh": "已连接客户端",
        "en": "Connected Clients"
    },
    "remote.panel_title": {
        "zh": "远程控制面板",
        "en": "Remote Control Panel"
    },
    "remote.connection": {
        "zh": "连接状态",
        "en": "Connection Status"
    },
    "remote.latency": {
        "zh": "延迟",
        "en": "Latency"
    },

    # ==========================================================================
    # Poses / 点位
    # ==========================================================================
    "pose.save": {
        "zh": "保存点位",
        "en": "Save Pose"
    },
    "pose.load": {
        "zh": "加载点位",
        "en": "Load Pose"
    },
    "pose.delete": {
        "zh": "删除点位",
        "en": "Delete Pose"
    },
    "pose.name": {
        "zh": "点位名称",
        "en": "Pose Name"
    },
    "pose.list": {
        "zh": "点位列表",
        "en": "Pose List"
    },
    "pose.move_to": {
        "zh": "移动到点位",
        "en": "Move to Pose"
    },

    # ==========================================================================
    # Teach Mode Recording / 示教录制
    # ==========================================================================
    "tab.teach_record": {
        "zh": "示教录制",
        "en": "Teach Record"
    },
    "teach.title": {
        "zh": "示教模式录制",
        "en": "Teach Mode Recording"
    },
    "teach.teach_mode": {
        "zh": "示教模式",
        "en": "Teach Mode"
    },
    "teach.teach_mode_on": {
        "zh": "示教模式 ON",
        "en": "Teach Mode ON"
    },
    "teach.teach_mode_off": {
        "zh": "示教模式 OFF",
        "en": "Teach Mode OFF"
    },
    "teach.start_record": {
        "zh": "开始录制 (50Hz)",
        "en": "Start Record (50Hz)"
    },
    "teach.stop_record": {
        "zh": "停止录制",
        "en": "Stop Record"
    },
    "teach.save_json": {
        "zh": "保存 JSON",
        "en": "Save JSON"
    },
    "teach.reset_recording": {
        "zh": "重置录制",
        "en": "Reset Recording"
    },
    "teach.replay_last": {
        "zh": "回放上次录制",
        "en": "Replay Last"
    },
    "teach.replay_selected": {
        "zh": "回放选中文件",
        "en": "Replay Selected"
    },
    "teach.refresh_files": {
        "zh": "刷新文件列表",
        "en": "Refresh Files"
    },
    "teach.stop_replay": {
        "zh": "停止回放",
        "en": "Stop Replay"
    },
    "teach.resume_replay": {
        "zh": "继续回放",
        "en": "Resume Replay"
    },
    "teach.reset_replay": {
        "zh": "重置回放",
        "en": "Reset Replay"
    },
    "teach.recording_status": {
        "zh": "录制状态",
        "en": "Recording Status"
    },
    "teach.replay_status": {
        "zh": "回放状态",
        "en": "Replay Status"
    },
    "teach.log_folder": {
        "zh": "日志文件夹",
        "en": "Log Folder"
    },
    "teach.select_file": {
        "zh": "选择文件",
        "en": "Select File"
    },
    "teach.idle": {
        "zh": "空闲",
        "en": "Idle"
    },
    "teach.recording": {
        "zh": "录制中...",
        "en": "Recording..."
    },
    "teach.replaying": {
        "zh": "回放中...",
        "en": "Replaying..."
    },
    "teach.stopped": {
        "zh": "已停止",
        "en": "Stopped"
    },
    "teach.saved": {
        "zh": "已保存",
        "en": "Saved"
    },
    "teach.joint_display": {
        "zh": "关节位置 (rad)",
        "en": "Joint Positions (rad)"
    },
    "teach.records_count": {
        "zh": "录制点数",
        "en": "Records Count"
    },
    "teach.operation_log": {
        "zh": "操作日志",
        "en": "Operation Log"
    },
    "teach.clear_log": {
        "zh": "清空日志",
        "en": "Clear Log"
    },
    "teach.recording_controls": {
        "zh": "录制控制",
        "en": "Recording Controls"
    },
    "teach.replay_controls": {
        "zh": "回放控制",
        "en": "Replay Controls"
    },
    "teach.hint_enable_teach": {
        "zh": "请在录制前启用示教模式",
        "en": "Enable teach mode before recording"
    },
    "teach.err_not_connected": {
        "zh": "机器人未连接！",
        "en": "Robot not connected!"
    },
    "teach.err_teach_on_fail": {
        "zh": "进入示教模式失败",
        "en": "Failed to enter teach mode"
    },
    "teach.err_teach_off_fail": {
        "zh": "退出示教模式失败",
        "en": "Failed to exit teach mode"
    },
    "teach.warn_enable_teach": {
        "zh": "请先启用示教模式！",
        "en": "Please enable teach mode first!"
    },
    "teach.warn_disable_teach": {
        "zh": "请在回放前关闭示教模式！",
        "en": "Please disable teach mode before replay!"
    },
    "teach.no_data": {
        "zh": "没有录制数据！",
        "en": "No data recorded!"
    },
    "teach.no_saved": {
        "zh": "没有可用的已保存录制！",
        "en": "No saved recording available!"
    },
    "teach.no_file_selected": {
        "zh": "未选择文件！",
        "en": "No file selected!"
    },
    "teach.file_not_found": {
        "zh": "文件未找到",
        "en": "File not found"
    },
    "teach.no_records_in_file": {
        "zh": "选中文件没有录制数据！",
        "en": "Selected file has no records!"
    },
    "teach.replay_running": {
        "zh": "回放已在运行！",
        "en": "Replay already running!"
    },
    "teach.log_cleared": {
        "zh": "日志已清空",
        "en": "Log cleared"
    },
    "teach.teach_enabled": {
        "zh": "示教模式已启用",
        "en": "Teach mode enabled"
    },
    "teach.teach_disabled": {
        "zh": "示教模式已关闭",
        "en": "Teach mode disabled"
    },
    "teach.recording_started": {
        "zh": "录制已开始",
        "en": "Recording started"
    },
    "teach.recording_stopped": {
        "zh": "录制已停止",
        "en": "Recording stopped"
    },
    "teach.memory_reset": {
        "zh": "录制内存已重置",
        "en": "Recording memory reset"
    },
    "teach.replay_started": {
        "zh": "回放已开始",
        "en": "Replay started"
    },
    "teach.replay_stop_requested": {
        "zh": "回放停止请求已发送",
        "en": "Replay stop requested"
    },
    "teach.replay_finished": {
        "zh": "回放完成",
        "en": "Replay finished"
    },
    "teach.save_failed": {
        "zh": "保存失败",
        "en": "Save failed"
    },
    "teach.load_failed": {
        "zh": "加载失败",
        "en": "Failed to load"
    },
    "teach.teach_auto_detected": {
        "zh": "物理按钮触发：自动进入示教模式",
        "en": "Physical button: auto-entered teach mode"
    },
    "teach.teach_auto_exited": {
        "zh": "物理按钮触发：自动退出示教模式",
        "en": "Physical button: auto-exited teach mode"
    },
    "teach.starting_robot_for_replay": {
        "zh": "正在为回放启动机器人系统...",
        "en": "Starting robot system for replay..."
    },
    "teach.start_sys_failed": {
        "zh": "启动机器人系统失败",
        "en": "Failed to start robot system"
    },
    "teach.replay_failed_state": {
        "zh": "回放失败：机器人状态为",
        "en": "Replay failed: robot state is"
    },
    "teach.replay_speed": {
        "zh": "回放速度",
        "en": "Replay Speed"
    },
    "teach.events_saved": {
        "zh": "关键帧事件已保存",
        "en": "Keyframe events saved"
    },
    "teach.gripper_control": {
        "zh": "夹爪和吸盘控制",
        "en": "Gripper & Suction Control"
    },
    "teach.gripper": {
        "zh": "夹爪",
        "en": "Gripper"
    },
    "teach.gripper_set": {
        "zh": "设置",
        "en": "Set"
    },
    "teach.gripper_open": {
        "zh": "全开",
        "en": "Open"
    },
    "teach.gripper_close": {
        "zh": "全关",
        "en": "Close"
    },
    "teach.gripper_current": {
        "zh": "当前",
        "en": "Current"
    },
    "teach.suction_on": {
        "zh": "吸盘开",
        "en": "Suction ON"
    },
    "teach.suction_off": {
        "zh": "吸盘关",
        "en": "Suction OFF"
    },
    "teach.err_not_running": {
        "zh": "请先启动机械臂系统！",
        "en": "Please start robot system first!"
    },
    "teach.gripper_set_to": {
        "zh": "夹爪已设置为",
        "en": "Gripper set to"
    },
    "teach.gripper_set_failed": {
        "zh": "夹爪设置失败",
        "en": "Gripper set failed"
    },
    "teach.suction_enabled": {
        "zh": "吸盘已启用",
        "en": "Suction enabled"
    },
    "teach.suction_disabled": {
        "zh": "吸盘已禁用",
        "en": "Suction disabled"
    },
    "teach.suction_failed": {
        "zh": "吸盘操作失败",
        "en": "Suction operation failed"
    },
    "teach.enter_gripper_value": {
        "zh": "请输入夹爪开合度值",
        "en": "Please enter gripper value"
    },
    "teach.gripper_range_error": {
        "zh": "夹爪开合度必须在 0-100 之间",
        "en": "Gripper value must be between 0 and 100"
    },

    # ==========================================================================
    # Messages / 消息
    # ==========================================================================
    "msg.connecting": {
        "zh": "正在连接...",
        "en": "Connecting..."
    },
    "msg.connected": {
        "zh": "连接成功",
        "en": "Connected successfully"
    },
    "msg.disconnected": {
        "zh": "已断开连接",
        "en": "Disconnected"
    },
    "msg.connection_failed": {
        "zh": "连接失败",
        "en": "Connection failed"
    },
    "msg.emergency_stop_active": {
        "zh": "紧急停止已激活！",
        "en": "Emergency stop activated!"
    },
    "msg.emergency_stop_released": {
        "zh": "紧急停止已释放",
        "en": "Emergency stop released"
    },
    "msg.operation_success": {
        "zh": "操作成功",
        "en": "Operation successful"
    },
    "msg.operation_failed": {
        "zh": "操作失败",
        "en": "Operation failed"
    },
    "msg.confirm_emergency_stop": {
        "zh": "确定要紧急停止所有设备吗？",
        "en": "Are you sure you want to emergency stop all devices?"
    },

    # ==========================================================================
    # Connection Check Dialog / 连接检查对话框
    # ==========================================================================
    "control.check_connections": {
        "zh": "连接检查",
        "en": "Check Connections"
    },
    "conn.title": {
        "zh": "硬件连接检查",
        "en": "Hardware Connection Check"
    },
    "conn.check_all": {
        "zh": "检查全部",
        "en": "Check All"
    },
    "conn.connect_reachable": {
        "zh": "连接可达设备",
        "en": "Connect Reachable"
    },
    "conn.checking": {
        "zh": "检查中...",
        "en": "Checking..."
    },
    "conn.reachable": {
        "zh": "可达",
        "en": "Reachable"
    },
    "conn.unreachable": {
        "zh": "不可达",
        "en": "Unreachable"
    },
    "conn.connecting": {
        "zh": "连接中...",
        "en": "Connecting..."
    },
    "conn.connected": {
        "zh": "已连接",
        "en": "Connected"
    },
    "conn.connect_failed": {
        "zh": "连接失败",
        "en": "Connect Failed"
    },
    "conn.disconnected": {
        "zh": "未连接",
        "en": "Disconnected"
    },
    "conn.unchecked": {
        "zh": "未检查",
        "en": "Unchecked"
    },
    "conn.type_tcp": {
        "zh": "TCP",
        "en": "TCP"
    },
    "conn.type_serial": {
        "zh": "串口",
        "en": "Serial"
    },
    "conn.type_can": {
        "zh": "CAN",
        "en": "CAN"
    },
    "conn.type_ws": {
        "zh": "WebSocket",
        "en": "WebSocket"
    },
    "conn.edit": {
        "zh": "编辑",
        "en": "Edit"
    },
    "conn.save_addr": {
        "zh": "保存",
        "en": "Save"
    },
    "conn.retry": {
        "zh": "重试",
        "en": "Retry"
    },
    "hardware.dexhand_left": {
        "zh": "灵巧手(左)",
        "en": "Dexhand(L)"
    },
    "hardware.dexhand_right": {
        "zh": "灵巧手(右)",
        "en": "Dexhand(R)"
    },
}


class I18n:
    """
    Internationalization manager.
    国际化管理器。

    Singleton pattern implementation.
    单例模式实现。
    """

    _instance: Optional['I18n'] = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._language = Language.CHINESE
        self._callbacks: List[Callable[[Language], None]] = []
        self._initialized = True

    @property
    def language(self) -> Language:
        """Get current language / 获取当前语言"""
        return self._language

    @language.setter
    def language(self, lang: Language):
        """Set language and notify callbacks / 设置语言并通知回调"""
        if self._language != lang:
            self._language = lang
            for callback in self._callbacks:
                try:
                    callback(lang)
                except Exception:
                    pass

    def set_language(self, lang_code: str):
        """
        Set language by code.
        通过代码设置语言。

        Args:
            lang_code: "zh" or "en"
        """
        if lang_code == "zh":
            self.language = Language.CHINESE
        elif lang_code == "en":
            self.language = Language.ENGLISH

    def add_callback(self, callback: Callable[[Language], None]):
        """Add language change callback / 添加语言变化回调"""
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[Language], None]):
        """Remove language change callback / 移除语言变化回调"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def t(self, key: str, **kwargs) -> str:
        """
        Get translation for key.
        获取键的翻译。

        Args:
            key: Translation key
            **kwargs: Format arguments

        Returns:
            Translated string
        """
        if key not in TRANSLATIONS:
            return key

        lang_code = self._language.value
        translation = TRANSLATIONS[key].get(lang_code, key)

        if kwargs:
            try:
                translation = translation.format(**kwargs)
            except KeyError:
                pass

        return translation

    def get(self, key: str, default: str = None) -> str:
        """
        Get translation with default fallback.
        获取翻译，带默认值回退。
        """
        if key in TRANSLATIONS:
            return self.t(key)
        return default or key

    def toggle_language(self):
        """Toggle between Chinese and English / 切换中英文"""
        if self._language == Language.CHINESE:
            self.language = Language.ENGLISH
        else:
            self.language = Language.CHINESE


# Global i18n instance / 全局国际化实例
_i18n: Optional[I18n] = None


def get_i18n() -> I18n:
    """Get the global i18n instance / 获取全局国际化实例"""
    global _i18n
    if _i18n is None:
        _i18n = I18n()
    return _i18n


def t(key: str, **kwargs) -> str:
    """
    Shortcut for translation.
    翻译的快捷方式。

    Usage:
        from config.i18n import t
        label = t("common.connect")
    """
    return get_i18n().t(key, **kwargs)
