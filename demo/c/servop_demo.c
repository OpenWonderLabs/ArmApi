#ifndef _WIN32
#define _POSIX_C_SOURCE 200809L
#endif
#include "onero_interface_c.h"
#include <math.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <time.h>
#endif

static volatile sig_atomic_t interrupted = 0;
static void on_signal(int sig) { (void)sig; interrupted = 1; }
static double now_seconds(void) {
#ifdef _WIN32
    return (double)GetTickCount64() / 1000.0;
#else
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (double)t.tv_sec + (double)t.tv_nsec / 1e9;
#endif
}
static void next_cycle(void) {
#ifdef _WIN32
    Sleep(10);
#else
    struct timespec t = {0, 10000000};
    nanosleep(&t, NULL);
#endif
}
static int check(int rc, const char *step) {
    if (rc) fprintf(stderr, "%s rc=%d\n", step, rc);
    return rc == 0;
}
static int feedback(onero_joint_array_t q) {
    int i;
    if (q.count != 7) return 0;
    for (i = 0; i < q.count; ++i) if (!isfinite(q.data[i])) return 0;
    return 1;
}
static int valid_pose(onero_pose_t p) {
    const double values[] = {p.x,p.y,p.z,p.qw,p.qx,p.qy,p.qz};
    int i;
    for (i = 0; i < 7; ++i) if (!isfinite(values[i])) return 0;
    return fabs(p.qw*p.qw+p.qx*p.qx+p.qy*p.qy+p.qz*p.qz-1.0) < 1e-3;
}
int main(int argc, char **argv) {
    onero_config_t cfg = {0};
    onero_handle arm = NULL;
    int result = 1, enable_attempted = 0, start_attempted = 0;
    int rc, cycles = 0, settled = 0, i;
    double deadline;
    if (argc != 4 || strcmp(argv[1], "--device") != 0 || !argv[2][0]
        || strlen(argv[2]) >= sizeof cfg.device || strcmp(argv[3], "--run") != 0) {
        fprintf(stderr, "Usage: %s --device DEVICE --run\nA1 left, vertical, no gripper; review configuration before hardware use.\nPure C has no simulation_mode. CI compiles/links this program only.\n", argv[0]);
        return 2; /* No device access without BOTH explicit arguments. */
    }
    signal(SIGINT, on_signal);
    signal(SIGTERM, on_signal);
    snprintf(cfg.device, sizeof cfg.device, "%s", argv[2]);
    snprintf(cfg.robot_model, sizeof cfg.robot_model, "a1_l");
    snprintf(cfg.version, sizeof cfg.version, "A1");
    snprintf(cfg.mount_orientation, sizeof cfg.mount_orientation, "vertical");
    cfg.dof = 7; cfg.baud_rate = 921600; cfg.with_gripper = false;
    arm = onero_create_robot(&cfg);
    if (!arm) { fprintf(stderr, "create failed\n"); goto cleanup; }
    if (!onero_is_hardware_connected(arm)
        || !feedback(onero_get_arm_state_from_motor(arm).positions)) {
        fprintf(stderr, "Connection/feedback check failed\n"); goto cleanup;
    }
    enable_attempted = 1;
    if (!check(onero_enable_motors(arm), "enable_motors")) goto cleanup;
    onero_pose_t target = onero_get_end_effector_pose(arm);
    if (!valid_pose(target)) { fprintf(stderr, "Invalid pose feedback\n"); goto cleanup; }
    target.x += 0.001; /* Absolute base_T_link7, metres/wxyz; no implicit tool/TCP offset. */
    onero_cartesian_servo_limits_t limits = {
        0.02, /* max_linear_velocity, m/s */
        0.10, /* max_angular_velocity, rad/s */
        0.05, /* max_linear_acceleration, m/s^2 */
        0.20  /* max_angular_acceleration, rad/s^2 */
    };
    start_attempted = 1;
    if (!check(onero_start_servop(arm), "start_servop")) goto cleanup;
    onero_servop_status_t initial = onero_get_servop_status(arm);
    deadline = now_seconds() + 20.0;
    while (!interrupted && now_seconds() < deadline) {
        rc = onero_servop(arm, &target, &limits);
        onero_servop_status_t status = onero_get_servop_status(arm);
        onero_joint_array_t q = onero_get_arm_state_from_motor(arm).positions;
        if (!feedback(q)) { fprintf(stderr, "Feedback invalid\n"); goto cleanup; }
        onero_pose_t actual = onero_get_end_effector_pose(arm);
        if (!valid_pose(actual)) { fprintf(stderr, "Invalid pose feedback\n"); goto cleanup; }
        double dx = actual.x-target.x, dy = actual.y-target.y, dz = actual.z-target.z;
        double error = sqrt(dx*dx+dy*dy+dz*dz);
        double dot = actual.qw*target.qw+actual.qx*target.qx+actual.qy*target.qy+actual.qz*target.qz;
        double norm = sqrt((actual.qw*actual.qw+actual.qx*actual.qx+actual.qy*actual.qy+actual.qz*actual.qz)
                         * (target.qw*target.qw+target.qx*target.qx+target.qy*target.qy+target.qz*target.qz));
        double angle = 2.0*acos(fmin(1.0, fabs(dot)/norm));
        if (cycles++ % 100 == 0 || rc || status.last_error || status.state == ONERO_SERVOP_STATE_FAULT) {
            printf("rc=%d state=%d accepted=%llu applied=%llu flags=%u last_error=%d error=%g angle_rad=%g feedback=",
                   rc, (int)status.state, (unsigned long long)status.accepted_sequence,
                   (unsigned long long)status.applied_sequence, status.limit_flags, status.last_error, error, angle);
            for (i = 0; i < q.count; ++i) printf("%g,", q.data[i]);
            putchar('\n');
        }
        if (!check(rc, "servop update") || !check(status.last_error, "servop status")
            || status.state == ONERO_SERVOP_STATE_FAULT) goto cleanup;
        settled = status.applied_sequence > initial.accepted_sequence && status.state == ONERO_SERVOP_STATE_HOLDING && error < 2e-4 && angle < 0.005 ? settled + 1 : 0;
        if (settled >= 3) { result = 0; break; }
        next_cycle();
    }
    if (interrupted) result = 130;
    else if (result) fprintf(stderr, "servop timeout: target not confirmed applied and settled\n");
cleanup:
    /* A failed update/start, FAULT, timeout or Ctrl+C reaches the same cleanup. */
    if (arm && start_attempted) {
        rc = onero_stop_servop(arm);
        printf("stop_servop rc=%d state=%d\n", rc, (int)onero_get_servop_status(arm).state);
        if (!check(rc, "stop_servop")) result = 1;
    }
    if (arm && enable_attempted) {
        rc = onero_disable_motors(arm);
        printf("disable_motors rc=%d\n", rc);
        if (!check(rc, "disable_motors")) result = 1;
    }
    if (arm) onero_destroy_robot(arm);
    if (!result) puts("servop: target applied and feedback within example tolerance; not a hardware performance certification");
    return result;
}
