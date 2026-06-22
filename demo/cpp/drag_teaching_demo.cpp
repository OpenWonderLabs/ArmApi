// drag_teaching_demo.cpp — OneroArm C++ RAII：拖动示教（零力录制 + 回放）
//
// 演示 OneroDragTeaching 的核心 API：
//   - initialize / set_hardware
//   - timer_callback   ：控制循环 tick（demo 用后台线程按 100Hz 调用）
//   - handle_command   ：0=Stop  1=StartRec  2=StopRec  3=Replay
//   - set_replay_file  ：切换回放数据源
//
// 不含 ROS 节点 / 话题 / 参数；纯线程 + stdin 驱动。
// 录制文件落在 ./trajectory_log/drag_record_<YYYYmmdd_HHMMSS>.dat，
// 命令 4 会列出该目录下所有 .dat 供选择回放。
//
// 注意：
//   - OneroDragTeaching::set_hardware() 自行打开串口，不需要额外 OneroArm 实例。
//   - 同一实例的方法不是线程安全的；demo 与 ROS 节点行为一致：tick 线程跑
//     timer_callback，主线程读 stdin 调 handle_command，未额外加锁。
#include "onero_interface_cpp.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <ctime>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

namespace fs = std::filesystem;

namespace {

// === 配置 =================================
constexpr const char* DEVICE            = "/dev/ttyACM0";
constexpr const char* ROBOT_MODEL       = "a1_l";
constexpr const char* MOUNT_ORIENTATION = "vertical";
constexpr int         DOF               = 7;
constexpr double      TIME_STEP_S       = 0.01;     // 100 Hz
constexpr const char* LOG_DIR           = "./trajectory_log";
// =========================================

std::string make_record_file_path() {
    auto t = std::chrono::system_clock::to_time_t(std::chrono::system_clock::now());
    std::stringstream ss;
    ss << LOG_DIR << "/drag_record_"
       << std::put_time(std::localtime(&t), "%Y%m%d_%H%M%S") << ".dat";
    return ss.str();
}

std::vector<fs::path> list_trajectory_files() {
    std::vector<fs::path> files;
    if (!fs::exists(LOG_DIR)) return files;
    for (const auto& e : fs::directory_iterator(LOG_DIR)) {
        if (e.is_regular_file() && e.path().extension() == ".dat") {
            files.push_back(e.path());
        }
    }
    std::sort(files.begin(), files.end(),
              [](const fs::path& a, const fs::path& b) {
                  return a.filename().string() > b.filename().string();
              });
    return files;
}

void print_menu() {
    std::cout << "\n>>> 命令: 0=停止 1=开始录制 2=停止录制 3=回放当前 4=回放历史 5=退出\n>>> "
              << std::flush;
}

int select_and_replay(onero_api::OneroDragTeaching& dt) {
    auto files = list_trajectory_files();
    if (files.empty()) {
        std::cout << "[X] 未找到轨迹文件 (" << LOG_DIR << ")，先用命令 1/2 录一段再回放。\n";
        return -1;
    }
    std::cout << "找到 " << files.size() << " 个轨迹文件:\n";
    for (size_t i = 0; i < files.size(); ++i) {
        std::cout << "  [" << (i + 1) << "] " << files[i].filename().string() << "\n";
    }
    std::cout << "输入编号 (1-" << files.size() << ")，0 取消: " << std::flush;

    std::string line;
    if (!std::getline(std::cin, line)) return -1;
    size_t idx = 0;
    try { idx = std::stoul(line); } catch (...) { idx = 0; }
    if (idx < 1 || idx > files.size()) {
        std::cout << "已取消\n";
        return -1;
    }
    dt.set_replay_file(files[idx - 1].string());
    int rc = dt.handle_command(3);
    std::cout << (rc == 0 ? "[OK]" : "[X]") << " 回放: "
              << files[idx - 1].filename().string() << " ret=" << rc << "\n";
    return rc;
}

}  // namespace

int main() {
    fs::create_directories(LOG_DIR);
    const std::string record_file = make_record_file_path();

    onero_api::OneroDragTeaching dt;
    if (!dt.valid() || !dt.initialize(DOF, record_file, TIME_STEP_S)) {
        std::cerr << "[X] OneroDragTeaching::initialize failed\n";
        return 1;
    }
    if (!dt.set_hardware(DEVICE, /*urdf_path=*/"", ROBOT_MODEL, MOUNT_ORIENTATION)) {
        std::cerr << "[X] set_hardware failed (device=" << DEVICE
                  << ", model=" << ROBOT_MODEL << ")\n";
        return 1;
    }
    std::cout << "[OK] DragTeaching ready. record_file=" << record_file << "\n";

    std::atomic<bool> running{true};
    std::thread tick_thread([&] {
        const auto period = std::chrono::microseconds(static_cast<long>(TIME_STEP_S * 1e6));
        auto next = std::chrono::steady_clock::now();
        while (running.load(std::memory_order_relaxed)) {
            dt.timer_callback();
            next += period;
            std::this_thread::sleep_until(next);
        }
    });

    print_menu();
    std::string line;
    while (std::getline(std::cin, line)) {
        int cmd = -1;
        try { cmd = std::stoi(line); } catch (...) { cmd = -1; }

        if (cmd == 5) break;
        if (cmd == 4) { select_and_replay(dt); print_menu(); continue; }
        if (cmd < 0 || cmd > 3) {
            std::cout << "[X] 无效命令: " << line << "\n";
            print_menu();
            continue;
        }
        int rc = dt.handle_command(cmd);
        std::cout << (rc == 0 ? "[OK]" : "[X]")
                  << " handle_command(" << cmd << ") ret=" << rc << "\n";
        print_menu();
    }

    running.store(false);
    if (tick_thread.joinable()) tick_thread.join();
    std::cout << "[OK] 退出\n";
    return 0;
}
