cmake_minimum_required(VERSION 3.10)
project(lbot_move LANGUAGES CXX)  # 明确指定为 C++ 项目

# 设置 C++ 标准
set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 设置源文件
set(SOURCES
    src/main.cpp
)

# 添加可执行文件
add_executable(lbot_move ${SOURCES})

# 定义库和头文件的路径
set(ROBOTIC_ARM_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../../C++")
# 检测当前系统架构
if(CMAKE_SYSTEM_PROCESSOR MATCHES "x86_64" OR CMAKE_SYSTEM_PROCESSOR MATCHES "AMD64")
    set(TARGET_ARCH "linux_x64")
    message(STATUS "检测到x64架构，使用linux_x64目录")
elseif(CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64" OR CMAKE_SYSTEM_PROCESSOR MATCHES "arm64")
    set(TARGET_ARCH "linux_arm64")
    message(STATUS "检测到ARM64架构，使用linux_arm64目录")
else()
    message(WARNING "未知架构: ${CMAKE_SYSTEM_PROCESSOR}，默认使用linux_x64目录")
    set(TARGET_ARCH "linux_x64")
endif()

# 设置库目录
set(ROBOTIC_ARM_LIB_DIR "${ROBOTIC_ARM_DIR}/libs/linux/${TARGET_ARCH}")
set(ROBOTIC_ARM_INCLUDE_DIR "${ROBOTIC_ARM_DIR}/include")

# 查找 C++ 库（优先查找 C++ 版本）
find_library(RMAN_API_LIB NAMES lbot_api_cpp lbot_api PATHS "${ROBOTIC_ARM_LIB_DIR}")

if(NOT RMAN_API_LIB)
    message(FATAL_ERROR "lbot_api library not found in ${ROBOTIC_ARM_LIB_DIR}")
else()
    message(STATUS "Found library: ${RMAN_API_LIB}")

    # 包含目录
    target_include_directories(lbot_move PUBLIC "${ROBOTIC_ARM_INCLUDE_DIR}")

    # 链接库
    target_link_libraries(lbot_move ${RMAN_API_LIB})

    # 如果是 Windows 平台，拷贝 DLL 文件到可执行文件的目录
    if(WIN32)
        add_custom_command(TARGET lbot_move POST_BUILD
            COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${ROBOTIC_ARM_LIB_DIR}/lbot_api_cpp.dll"
            $<TARGET_FILE_DIR:lbot_move>)
    endif()

    # 如果是 UNIX 平台，确保动态库文件可以在运行时被找到
    if(UNIX)
        add_custom_command(TARGET lbot_move POST_BUILD
            COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${ROBOTIC_ARM_LIB_DIR}/liblbot_api_cpp.so"
            $<TARGET_FILE_DIR:lbot_move>)
    endif()

endif()

# 启用详细输出
set(CMAKE_VERBOSE_MAKEFILE ON)