/*
 * movel_demo.c — OneroArm 纯 C ABI：单一 movel 笛卡尔直线运动示例
 *
 * 序列：enable → restore_arm()(zero) → movel(target) → restore_arm()(zero) → disable
 */
#include "onero_interface_c.h"
#include <stdio.h>
#include <string.h>

/* 跨平台 sleep shim：unistd.h / sleep() 是 POSIX，Windows MSVC 没有；
 * Windows 走 windows.h::Sleep(ms)。各 demo 统一用 onero_sleep_s(秒)。 */
#if defined(_WIN32)
#  include <windows.h>
#  define onero_sleep_s(s) Sleep((unsigned long)(s) * 1000UL)
#else
#  include <unistd.h>
#  define onero_sleep_s(s) sleep((unsigned int)(s))
#endif

/* === 笛卡尔目标位姿（右臂可达） =========== */
static const double TARGET_X  =  0.30;
static const double TARGET_Y  =  0.30;
static const double TARGET_Z  =  0.40;
static const double TARGET_QW =  1.00;
static const double TARGET_QX =  0.00;
static const double TARGET_QY =  0.00;
static const double TARGET_QZ =  0.00;
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

static onero_pose_t make_target(void) {
    onero_pose_t p;
    memset(&p, 0, sizeof(p));
    p.x  = TARGET_X;  p.y  = TARGET_Y;  p.z  = TARGET_Z;
    p.qw = TARGET_QW; p.qx = TARGET_QX; p.qy = TARGET_QY; p.qz = TARGET_QZ;
    return p;
}

static int checked(const char* name, int ret) {
    if (ret != 0) {
        fprintf(stderr, "[X] %s failed, ret=%d\n", name, ret);
        return ret;
    }
    printf("[OK] %s\n", name);
    return 0;
}

int main(void) {
    onero_config_t cfg = build_config();
    onero_handle h = onero_create_robot(&cfg);
    if (!h) {
        fprintf(stderr, "create_robot failed\n");
        return 1;
    }

    int rc = 0;
    int enabled = (onero_enable_motors(h) == 0);
    if (!enabled) fprintf(stderr, "[!] enable_motors failed (无硬件预期)\n");
    onero_sleep_s(1);

    onero_pose_t target = make_target();

    rc |= checked("restore_arm() -> zero", onero_restore_arm(h));
    onero_sleep_s(1);
    rc |= checked("movel(target)", onero_movel(h, &target, 1.0, 0));
    onero_sleep_s(1);
    rc |= checked("restore_arm() -> zero", onero_restore_arm(h));

    if (enabled) onero_disable_motors(h);
    onero_destroy_robot(h);
    return rc == 0 ? 0 : 1;
}
