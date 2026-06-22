/*
 * movej_demo.c — OneroArm 纯 C ABI：单一 movej 关节空间运动示例
 *
 * 序列：enable → restore_arm()(zero) → movej(target) → restore_arm()(zero) → disable
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

/* === 关节空间目标（rad） ================== */
static const int    JOINT_INDEX     = 3;     /* 0-based: joint4 */
static const double JOINT_VALUE_RAD = 0.3;
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

    onero_joint_array_t zero;
    memset(&zero, 0, sizeof(zero));
    zero.count = cfg.dof;

    onero_joint_array_t target = zero;
    target.data[JOINT_INDEX] = JOINT_VALUE_RAD;

    rc |= checked("restore_arm() -> zero", onero_restore_arm(h));
    onero_sleep_s(1);
    rc |= checked("movej(target)", onero_movej(h, &target, 1.5, 0));
    onero_sleep_s(1);
    rc |= checked("restore_arm() -> zero", onero_restore_arm(h));

    if (enabled) onero_disable_motors(h);
    onero_destroy_robot(h);
    return rc == 0 ? 0 : 1;
}
