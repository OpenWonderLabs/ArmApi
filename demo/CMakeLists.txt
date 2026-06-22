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

if(WIN32)
    set(ONERO_ARCH_DIR "windows/windows-x86_64")
    set(ONERO_LIB_FILE "oneroarm.dll")
    set(ONERO_IMP_FILE "oneroarm.lib")
elseif(ONERO_SYSTEM_PROCESSOR MATCHES "^(aarch64|arm64)$")
    set(ONERO_ARCH_DIR "linux/linux-arm64")
    set(ONERO_LIB_FILE "liboneroarm.so")
elseif(ONERO_SYSTEM_PROCESSOR MATCHES "^(riscv64|riscv64gc)$")
    set(ONERO_ARCH_DIR "linux/linux-riscv64")
    set(ONERO_LIB_FILE "liboneroarm.so")
elseif(ONERO_SYSTEM_PROCESSOR MATCHES "^(x86_64|amd64)$")
    set(ONERO_ARCH_DIR "linux/linux-x86_64")
    set(ONERO_LIB_FILE "liboneroarm.so")
else()
    message(FATAL_ERROR
        "Unsupported CMAKE_SYSTEM_PROCESSOR='${CMAKE_SYSTEM_PROCESSOR}'. "
        "Expected x86_64/amd64, aarch64/arm64, or riscv64."
    )
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
# Windows MSVC 注意事项：
#   1. /utf-8：SDK 头文件 (onero_define.h / onero_interface_cpp.h) 与 demo 源
#      码均为无 BOM UTF-8，含中文注释。MSVC 默认按当前系统 code page（中文
#      系统 = 936/GBK）解读源文件，会把 UTF-8 多字节序列误读成非法字符或
#      触发行接续（C2143/C2061/C4819），导致 onero_config_t / CanFrameCallback
#      在编译期"丢失"。/utf-8 等价 /source-charset:utf-8 /execution-charset:utf-8，
#      显式声明 UTF-8 解码，根除该问题。GCC/Clang 默认就按 UTF-8 解读，无需此选项。
#   2. drag_teaching_demo_c：使用 dirent.h / pthread.h / sys/stat::mkdir(0755)
#      / localtime_r / usleep 等 POSIX-only API，没有 Windows 适配，因此
#      Windows 下不构建该 c target。drag_teaching_demo_cpp 全用 C++17 标准库
#      （std::filesystem / std::thread / std::chrono），跨平台无碍。
# ---------------------------------------------------------------------------
set(ONERO_DEMO_NAMES
    full
    movej
    movep
    movel
    buffered_traj
    can_frame
    drag_teaching
)

# Windows MSVC 跳过纯 POSIX 的 c demo
set(ONERO_C_DEMO_SKIP_ON_WIN32
    drag_teaching
)

foreach(name IN LISTS ONERO_DEMO_NAMES)
    set(_skip_c FALSE)
    if(WIN32)
        list(FIND ONERO_C_DEMO_SKIP_ON_WIN32 ${name} _idx)
        if(NOT _idx EQUAL -1)
            set(_skip_c TRUE)
            message(STATUS "Skipping ${name}_demo_c on Windows (POSIX-only sources)")
        endif()
    endif()

    if(NOT _skip_c)
        add_executable(${name}_demo_c c/${name}_demo.c)
        target_link_libraries(${name}_demo_c PRIVATE oneroarm_c Threads::Threads)
        set_target_properties(${name}_demo_c PROPERTIES
            BUILD_RPATH "${ONERO_C_ROOT}/${ONERO_ARCH_DIR}"
        )
        if(MSVC)
            target_compile_options(${name}_demo_c PRIVATE /utf-8)
        endif()
    endif()

    add_executable(${name}_demo_cpp cpp/${name}_demo.cpp)
    target_link_libraries(${name}_demo_cpp PRIVATE oneroarm_cpp Threads::Threads)
    set_target_properties(${name}_demo_cpp PROPERTIES
        BUILD_RPATH "${ONERO_CPP_ROOT}/${ONERO_ARCH_DIR}"
    )
    if(MSVC)
        target_compile_options(${name}_demo_cpp PRIVATE /utf-8)
    endif()
endforeach()
