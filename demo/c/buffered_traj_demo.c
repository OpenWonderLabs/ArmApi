/*
 * buffered_traj_demo.c — OneroArm 纯 C ABI：trajectory_connect 缓冲轨迹示例
 *
 * 演示 movej / movep / movel 的最后一个参数 trajectory_connect：
 *   - trajectory_connect = 1 → 把当前段塞进内部 trajectory_buffer_，**不立即执行**；
 *   - 末尾调一次 onero_execute_buffered_trajectory，把所有累积段串成一条
 *     平滑轨迹下发。
 *
 * ⚠ 注意：onero_send_trajectory / onero_send_trajectory_point 走的是
 *        另一条路径 —— 直接给每个关节电机下发 MIT 力矩控制，**不做规划、
 *        不入此 buffer**。本 demo 不演示该接口。
 *
 * 序列：enable
 *      → restore_arm()                 # 显式归零；enable 不自动回零
 *      → movej(joint_target, 1.0, 1)   # 入 buffer：段 1
 *      → movep(pose_target,  1.0, 1)   # 入 buffer：段 2
 *      → movej(zero,         1.0, 1)   # 入 buffer：段 3
 *      → execute_buffered_trajectory   # 三段串成一条轨迹平滑执行
 *      → disable
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

/* === 笛卡尔目标位姿（右臂可达） =========== */
static const double TARGET_X  =  0.30;
static const double TARGET_Y  =  0.30;
static const double TARGET_Z  =  0.30;
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

    onero_joint_array_t zero;
    memset(&zero, 0, sizeof(zero));
    zero.count = cfg.dof;

    onero_joint_array_t joint_target = zero;
    joint_target.data[JOINT_INDEX] = JOINT_VALUE_RAD;

    onero_pose_t pose_target = make_target();

    /* 显式归零；新版 enable_motors() 不再自动回零。 */
    rc |= checked("restore_arm() -> zero", onero_restore_arm(h));
    onero_sleep_s(1);

    /* 三段累积入 trajectory_buffer_，**此时不会运动** */
    rc |= checked("movej(joint4=0.3, tc=1)",   onero_movej(h, &joint_target, 1.0, 1));
    rc |= checked("movep(target,    tc=1)",    onero_movep(h, &pose_target,  1.0, 1));
    rc |= checked("movej(zero,      tc=1)",    onero_movej(h, &zero,         1.0, 1));

    /* 串成一条平滑轨迹一次性下发 */
    rc |= checked("execute_buffered_trajectory",
                  onero_execute_buffered_trajectory(h));

    if (enabled) onero_disable_motors(h);
    onero_destroy_robot(h);
    return rc == 0 ? 0 : 1;
}
