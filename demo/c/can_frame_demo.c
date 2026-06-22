/*
 * can_frame_demo.c — OneroArm 纯 C ABI：原始 CAN 帧收发最小示例
 *
 * 演示原始 CAN 帧四个接口：
 *   - onero_register_can_frame_callback：注册接收回调（仅非保留 ID 派发）
 *   - onero_send_can_frame              ：向**非保留** ID 发送一帧
 *   - onero_pump_can_bus                ：主动驱动一次串口 rx，把帧从 SLCAN 缓冲取出
 *   - onero_clear_can_frame_callback    ：清回调
 *
 * 注意：
 *   - 本 demo **不调用 enable_motors** —— 串口在 onero_create_robot 时已打开，
 *     收发原始帧不需要电机使能。
 *   - 选用 CAN ID = 0x100，不在 SDK 保留集 (0x01-0x08, 0x11-0x17, 0x7FF) 内，
 *     不会被 ONERO_ERR_RAW_FRAME_RESERVED_ID 拦截。
 *   - 总线上若**没有**接听该 ID 的节点，回调可能不会触发；这是预期行为。
 */
#include "onero_interface_c.h"
#include <stdio.h>
#include <string.h>

/* === 测试帧 ============================== */
static const uint16_t TEST_CAN_ID  = 0x100;                       /* 非保留 */
static const uint8_t  TEST_PAYLOAD[] = {0xDE, 0xAD, 0xBE, 0xEF};
static const int      PUMP_TIMES     = 5;
static const int      PUMP_TIMEOUT_MS = 50;
/* ========================================= */

static onero_config_t build_config(void) {
    onero_config_t cfg;
    memset(&cfg, 0, sizeof(cfg));
    strncpy(cfg.device,      "/dev/ttyACM0", sizeof(cfg.device)      - 1);
    strncpy(cfg.robot_model, "a1_l",         sizeof(cfg.robot_model) - 1);
    strncpy(cfg.version,     "A1",           sizeof(cfg.version)     - 1);
    strncpy(cfg.mount_orientation, "vertical", sizeof(cfg.mount_orientation) - 1);
    cfg.dof = 7;
    cfg.baud_rate = 921600;
    return cfg;
}

static void on_can_frame(uint16_t can_id,
                         const uint8_t* data, uint8_t len,
                         void* user_data) {
    (void)user_data;
    printf("[RX] id=0x%03X len=%u data=", can_id, (unsigned)len);
    for (uint8_t i = 0; i < len; ++i) printf("%02X ", data[i]);
    printf("\n");
}

int main(void) {
    onero_config_t cfg = build_config();
    onero_handle h = onero_create_robot(&cfg);
    if (!h) {
        fprintf(stderr, "create_robot failed\n");
        return 1;
    }

    int rc = onero_register_can_frame_callback(h, on_can_frame, NULL);
    if (rc != 0) {
        fprintf(stderr, "register_can_frame_callback failed, ret=%d\n", rc);
    } else {
        printf("[OK] register_can_frame_callback\n");
    }

    printf("[TX] id=0x%03X len=%zu data=", TEST_CAN_ID, sizeof(TEST_PAYLOAD));
    for (size_t i = 0; i < sizeof(TEST_PAYLOAD); ++i) printf("%02X ", TEST_PAYLOAD[i]);
    printf("\n");
    rc = onero_send_can_frame(h, TEST_CAN_ID, TEST_PAYLOAD, sizeof(TEST_PAYLOAD));
    if (rc != 0) {
        fprintf(stderr, "[X] send_can_frame failed, ret=%d (无硬件预期 -13)\n", rc);
    } else {
        printf("[OK] send_can_frame\n");
    }

    /* 主动驱动 rx，让总线上的回帧（如有）经回调派发 */
    for (int i = 0; i < PUMP_TIMES; ++i) {
        onero_pump_can_bus(h, PUMP_TIMEOUT_MS);
    }

    onero_clear_can_frame_callback(h);
    onero_destroy_robot(h);
    return 0;
}
