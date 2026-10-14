cmake_minimum_required(VERSION 3.15)
project(onero_arm_demos LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

# Threads（drag_teaching demo 需要 pthread / std::thread；其他 demo 链上无副作用）
set(THREADS_PREFER_PTHREAD_FLAG ON)
find_package(Threads REQUIRED)

# 极简分发：不再 find_package(oneroarm)，直接以 IMPORTED target 引入 ../c/ 与
# ../c++/ 两个 SDK 包。两包的二进制 (liboneroarm.so / oneroarm.dll) 完全一致，
# 差异仅在公开头：
#   ../c/include/   → 纯 C ABI (onero_*)
#   ../c++/include/ → C++ namespace onero_api + 自动 #include <onero_define.h>
# C demo 链 oneroarm_c，C++ demo 链 oneroarm_cpp，分别覆盖两个分发形态。

string(TOLOWER "${CMAKE_SYSTEM_PROCESSOR}" ONERO_SYSTEM_PROCESSOR)

if(WIN32 AND ONERO_SYSTEM_PROCESSOR MATCHES "^(x86_64|amd64)$")
    set(ONERO_ARCH_DIR "windows/windows-x86_64")
    set(ONERO_LIB_FILE "oneroarm.dll")
    set(ONERO_IMP_FILE "oneroarm.lib")
elseif(UNIX AND ONERO_SYSTEM_PROCESSOR MATCHES "^(x86_64|amd64)$")
    set(ONERO_ARCH_DIR "linux/linux-x86_64")
    set(ONERO_LIB_FILE "liboneroarm.so")
    set(ONERO_RUNTIME_ROOT "${CMAKE_CURRENT_LIST_DIR}/../runtime/linux-x86_64/lib")
elseif(UNIX AND ONERO_SYSTEM_PROCESSOR MATCHES "^(aarch64|arm64)$")
    set(ONERO_ARCH_DIR "linux/linux-arm64")
    set(ONERO_LIB_FILE "liboneroarm.so")
elseif(UNIX AND ONERO_SYSTEM_PROCESSOR STREQUAL "riscv64")
    set(ONERO_ARCH_DIR "linux/linux-riscv64")
    set(ONERO_LIB_FILE "liboneroarm.so")
    set(ONERO_RUNTIME_ROOT "${CMAKE_CURRENT_LIST_DIR}/../runtime/linux-riscv64/lib")
else()
    message(FATAL_ERROR
        "No SDK binary for ${CMAKE_SYSTEM_NAME}/${CMAKE_SYSTEM_PROCESSOR}."
    )
endif()

if(UNIX)
    if(ONERO_RUNTIME_ROOT AND EXISTS "${ONERO_RUNTIME_ROOT}")
        set(ONERO_DEPS_DEFAULT "${ONERO_RUNTIME_ROOT}")
    elseif(DEFINED ENV{CONDA_PREFIX})
        set(ONERO_DEPS_DEFAULT "$ENV{CONDA_PREFIX}/lib")
    endif()
    set(ONERO_DEPENDENCY_DIR "${ONERO_DEPS_DEFAULT}" CACHE PATH "Matching SDK dependency library directory")
    if(NOT IS_DIRECTORY "${ONERO_DEPENDENCY_DIR}")
        message(FATAL_ERROR "Set ONERO_DEPENDENCY_DIR to the matching SDK runtime directory.")
    endif()
endif()

message(STATUS "Using OneroArm SDK binary directory: ${ONERO_ARCH_DIR}")

set(ONERO_C_ROOT   "${CMAKE_CURRENT_LIST_DIR}/../c")
set(ONERO_CPP_ROOT "${CMAKE_CURRENT_LIST_DIR}/../c++")
add_library(oneroarm_c SHARED IMPORTED)
set_target_properties(oneroarm_c PROPERTIES
    IMPORTED_LOCATION             "${ONERO_C_ROOT}/${ONERO_ARCH_DIR}/${ONERO_LIB_FILE}"
    INTERFACE_INCLUDE_DIRECTORIES "${ONERO_C_ROOT}/include"
)
if(WIN32)
    set_target_properties(oneroarm_c PROPERTIES
        IMPORTED_IMPLIB "${ONERO_C_ROOT}/${ONERO_ARCH_DIR}/${ONERO_IMP_FILE}"
    )
endif()

add_library(oneroarm_cpp SHARED IMPORTED)
set_target_properties(oneroarm_cpp PROPERTIES
    IMPORTED_LOCATION             "${ONERO_CPP_ROOT}/${ONERO_ARCH_DIR}/${ONERO_LIB_FILE}"
    INTERFACE_INCLUDE_DIRECTORIES "${ONERO_CPP_ROOT}/include"
)
if(WIN32)
    set_target_properties(oneroarm_cpp PROPERTIES
        IMPORTED_IMPLIB "${ONERO_CPP_ROOT}/${ONERO_ARCH_DIR}/${ONERO_IMP_FILE}"
    )
endif()

# ---------------------------------------------------------------------------
# Demos：每个名字下都有 C 与 C++ 两份源码（python/${name}_demo.py 由用户
# 直接 `python ...` 运行，无需 cmake 介入）。
#
# ---------------------------------------------------------------------------
set(ONERO_DEMO_NAMES
    full
    movej
    movep
    movel
    buffered_traj
    can_frame
    drag_teaching
    frame
    new_motion
    servoj
    servop
)

foreach(name IN LISTS ONERO_DEMO_NAMES)
    if(NOT WIN32 OR NOT name STREQUAL "drag_teaching")
        add_executable(${name}_demo_c c/${name}_demo.c)
        target_link_libraries(${name}_demo_c PRIVATE oneroarm_c Threads::Threads)
        if(MSVC)
            target_compile_options(${name}_demo_c PRIVATE /utf-8)
        endif()
    endif()

    add_executable(${name}_demo_cpp cpp/${name}_demo.cpp)
    target_link_libraries(${name}_demo_cpp PRIVATE oneroarm_cpp Threads::Threads)
    if(MSVC)
        target_compile_options(${name}_demo_cpp PRIVATE /utf-8)
    endif()
    if(UNIX)
        target_link_libraries(${name}_demo_c PRIVATE m)
        target_link_directories(${name}_demo_c BEFORE PRIVATE "${ONERO_DEPENDENCY_DIR}")
        target_link_directories(${name}_demo_cpp BEFORE PRIVATE "${ONERO_DEPENDENCY_DIR}")
        target_link_libraries(${name}_demo_cpp PRIVATE "${ONERO_DEPENDENCY_DIR}/libstdc++.so.6")
        target_link_options(${name}_demo_c PRIVATE "-Wl,-rpath-link,${ONERO_DEPENDENCY_DIR}")
        target_link_options(${name}_demo_cpp PRIVATE "-Wl,-rpath-link,${ONERO_DEPENDENCY_DIR}")
        set_target_properties(${name}_demo_c PROPERTIES
            BUILD_RPATH "${ONERO_C_ROOT}/${ONERO_ARCH_DIR};${ONERO_DEPENDENCY_DIR}"
        )
        set_target_properties(${name}_demo_cpp PROPERTIES
            BUILD_RPATH "${ONERO_CPP_ROOT}/${ONERO_ARCH_DIR};${ONERO_DEPENDENCY_DIR}"
        )
    endif()
endforeach()

# No-device consumer used by target-platform validation, not a motion example.
set(GRIPPER_ROOT "${CMAKE_CURRENT_LIST_DIR}/../gripper")
add_library(onerogripper_cpp SHARED IMPORTED)
if(WIN32)
    set_target_properties(onerogripper_cpp PROPERTIES
        IMPORTED_LOCATION "${GRIPPER_ROOT}/c++/${ONERO_ARCH_DIR}/onerogripper.dll"
        IMPORTED_IMPLIB "${GRIPPER_ROOT}/c++/${ONERO_ARCH_DIR}/onerogripper.lib")
else()
    set_target_properties(onerogripper_cpp PROPERTIES
        IMPORTED_LOCATION "${GRIPPER_ROOT}/c++/${ONERO_ARCH_DIR}/libonerogripper.so")
endif()
set_target_properties(onerogripper_cpp PROPERTIES INTERFACE_INCLUDE_DIRECTORIES "${GRIPPER_ROOT}/c++/include")
add_executable(gripper_offline_check_cpp "${GRIPPER_ROOT}/demo/cpp_offline_check.cpp")
target_link_libraries(gripper_offline_check_cpp PRIVATE onerogripper_cpp)
if(MSVC)
    target_compile_options(gripper_offline_check_cpp PRIVATE /utf-8)
else()
    target_link_libraries(gripper_offline_check_cpp PRIVATE "${ONERO_DEPENDENCY_DIR}/libstdc++.so.6")
    target_link_options(gripper_offline_check_cpp PRIVATE "-Wl,-rpath-link,${ONERO_DEPENDENCY_DIR}")
    set_target_properties(gripper_offline_check_cpp PROPERTIES BUILD_RPATH "${ONERO_DEPENDENCY_DIR}")
endif()
