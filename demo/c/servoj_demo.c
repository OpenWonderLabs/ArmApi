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
    onero_joint_array_t target = onero_get_arm_state_from_motor(arm).positions;
    onero_joint_servo_limits_t limits = {0};
    if (!feedback(target)) goto cleanup;
    target.data[0] += 0.01; /* 0.01 rad relative to checked feedback; SDK enforces joint limits. */
    limits.max_velocity.count = limits.max_acceleration.count = limits.max_jerk.count = 7;
    for (i = 0; i < 7; ++i) {
        limits.max_velocity.data[i] = 0.1;
        limits.max_acceleration.data[i] = 0.2;
        limits.max_jerk.data[i] = 0.05;
    }
    const double validity_s = 0.5; /* Refresh every 10 ms; expiry requests controlled braking. */
    start_attempted = 1;
    if (!check(onero_start_servoj(arm, &limits), "start_servoj")) goto cleanup;
    onero_servoj_status_t initial = onero_get_servoj_status(arm);
    deadline = now_seconds() + 20.0;
    while (!interrupted && now_seconds() < deadline) {
        rc = onero_servoj(arm, &target, NULL, validity_s);
        onero_servoj_status_t status = onero_get_servoj_status(arm);
        onero_joint_array_t q = onero_get_arm_state_from_motor(arm).positions;
        if (!feedback(q)) { fprintf(stderr, "Feedback invalid\n"); goto cleanup; }
        double error = 0.0;
        for (i = 0; i < q.count; ++i) error = fmax(error, fabs(q.data[i] - target.data[i]));
        if (cycles++ % 100 == 0 || rc || status.last_error || status.state == ONERO_SERVOJ_STATE_FAULT) {
            printf("rc=%d state=%d accepted=%llu applied=%llu flags=%u last_error=%d error=%g sent=%llu age_s=%g feedback=",
                   rc, (int)status.state, (unsigned long long)status.accepted_sequence,
                   (unsigned long long)status.applied_sequence, status.limit_flags, status.last_error, error, (unsigned long long)status.sent_frame_count, status.command_age_s);
            for (i = 0; i < q.count; ++i) printf("%g,", q.data[i]);
            putchar('\n');
        }
        if (!check(rc, "servoj update") || !check(status.last_error, "servoj status")
            || status.state == ONERO_SERVOJ_STATE_FAULT) goto cleanup;
        settled = status.applied_sequence > initial.accepted_sequence && status.sent_frame_count >= 5 && status.state == ONERO_SERVOJ_STATE_HOLDING && error < 1e-3 ? settled + 1 : 0;
        if (settled >= 3) { result = 0; break; }
        next_cycle();
    }
    if (interrupted) result = 130;
    else if (result) fprintf(stderr, "servoj timeout: target not confirmed applied and settled\n");
cleanup:
    /* A failed update/start, FAULT, timeout or Ctrl+C reaches the same cleanup. */
    if (arm && start_attempted) {
        rc = onero_stop_servoj(arm);
        printf("stop_servoj rc=%d state=%d\n", rc, (int)onero_get_servoj_status(arm).state);
        if (!check(rc, "stop_servoj")) result = 1;
    }
    if (arm && enable_attempted) {
        rc = onero_disable_motors(arm);
        printf("disable_motors rc=%d\n", rc);
        if (!check(rc, "disable_motors")) result = 1;
    }
    if (arm) onero_destroy_robot(arm);
    if (!result) puts("servoj: target applied and feedback within example tolerance; not a hardware performance certification");
    return result;
}
