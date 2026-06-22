// can_frame_demo.cpp — OneroArm C++ RAII：原始 CAN 帧收发最小示例
//
// 演示原始 CAN 帧四个接口：
//   - register_can_frame_callback：注册接收回调（仅非保留 ID 派发）
//   - send_can_frame              ：向**非保留** ID 发送一帧
//   - pump_can_bus                ：主动驱动一次串口 rx，把帧从 SLCAN 缓冲取出
//   - clear_can_frame_callback    ：清回调
//
// 注意：
//   - 本 demo **不调用 enable_motors** —— 串口在 OneroArm 构造时已打开，
//     收发原始帧不需要电机使能。
//   - 选用 CAN ID = 0x100，不在 SDK 保留集 (0x01-0x08, 0x11-0x17, 0x7FF) 内，
//     不会被 ONERO_ERR_RAW_FRAME_RESERVED_ID 拦截。
//   - 总线上若**没有**接听该 ID 的节点，回调可能不会触发；这是预期行为。
#include "onero_interface_cpp.h"

#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <iostream>

namespace {

// === 测试帧 ===============================
constexpr uint16_t TEST_CAN_ID = 0x100;  // 非保留
constexpr std::array<uint8_t, 4> TEST_PAYLOAD = {0xDE, 0xAD, 0xBE, 0xEF};
constexpr int PUMP_TIMES      = 5;
constexpr int PUMP_TIMEOUT_MS = 50;
// =========================================

onero_api::onero_config_t build_config() {
    onero_api::onero_config_t cfg{};
    std::strncpy(cfg.device,      "/dev/ttyACM0", sizeof(cfg.device)      - 1);
    std::strncpy(cfg.robot_model, "a1_l",         sizeof(cfg.robot_model) - 1);
    std::strncpy(cfg.version,     "A1",           sizeof(cfg.version)     - 1);
    std::strncpy(cfg.mount_orientation, "vertical", sizeof(cfg.mount_orientation) - 1);
    return cfg;
}

void on_can_frame(uint16_t can_id, const uint8_t* data, uint8_t len) {
    std::printf("[RX] id=0x%03X len=%u data=", can_id, static_cast<unsigned>(len));
    for (uint8_t i = 0; i < len; ++i) std::printf("%02X ", data[i]);
    std::printf("\n");
}

}  // namespace

int main() {
    const auto cfg = build_config();
    onero_api::OneroArm arm(cfg);

    int rc = arm.register_can_frame_callback(&on_can_frame);
    if (rc != 0) {
        std::cerr << "register_can_frame_callback failed, ret=" << rc << "\n";
    } else {
        std::cout << "[OK] register_can_frame_callback\n";
    }

    std::printf("[TX] id=0x%03X len=%zu data=", TEST_CAN_ID, TEST_PAYLOAD.size());
    for (auto b : TEST_PAYLOAD) std::printf("%02X ", b);
    std::printf("\n");
    rc = arm.send_can_frame(TEST_CAN_ID,
                            TEST_PAYLOAD.data(),
                            static_cast<uint8_t>(TEST_PAYLOAD.size()));
    if (rc != 0) {
        std::cerr << "[X] send_can_frame failed, ret=" << rc
                  << " (无硬件预期 -13)\n";
    } else {
        std::cout << "[OK] send_can_frame\n";
    }

    // 主动驱动 rx，让总线上的回帧（如有）经回调派发
    for (int i = 0; i < PUMP_TIMES; ++i) {
        arm.pump_can_bus(PUMP_TIMEOUT_MS);
    }

    arm.clear_can_frame_callback();
    return 0;
}
