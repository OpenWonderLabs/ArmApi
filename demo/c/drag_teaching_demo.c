/*
 * drag_teaching_demo.c — OneroArm 纯 C ABI：拖动示教（零力录制 + 回放）
 *
 * 演示 onero_drag_teaching_* 的核心 API：
 *   - onero_drag_teaching_create / destroy
 *   - onero_drag_teaching_initialize  / set_hardware
 *   - onero_drag_teaching_timer_callback：100Hz tick（demo 用 pthread 后台驱动）
 *   - onero_drag_teaching_handle_command：0=Stop 1=StartRec 2=StopRec 3=Replay
 *   - onero_drag_teaching_set_replay_file：切换回放数据源
 *
 * 不含 ROS / Pthread 之外的依赖；纯 stdin 命令循环 + 后台线程驱动控制循环。
 * 录制文件落在 ./trajectory_log/drag_record_<YYYYmmdd_HHMMSS>.dat，
 * 命令 4 会列出该目录下所有 .dat 供选择回放。
 *
 * 注意：
 *   - set_hardware() 自行打开串口；不需要再创建 onero_handle。
 *   - 同一句柄上的方法不是线程安全的；demo 与 ROS 节点行为一致：tick 线程跑
 *     timer_callback，主线程读 stdin 调 handle_command，未额外加锁。
 */
#include "onero_interface_c.h"

/* 该 demo 使用 dirent.h / pthread.h / sys/stat::mkdir(0755) / localtime_r /
 * usleep 等 POSIX-only API，没有 Windows 适配。CMakeLists.txt 已在 Windows
 * 下跳过 drag_teaching_demo_c target；此处再加一道 #error 防止有人绕开
 * cmake 直接编。Windows 用户请使用 drag_teaching_demo_cpp（基于 C++17
 * std::filesystem / std::thread / std::chrono，跨平台无碍）。 */
#if defined(_WIN32)
#  error "drag_teaching_demo.c is POSIX-only; use drag_teaching_demo_cpp on Windows."
#endif

#include <dirent.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

/* === 配置 ================================ */
#define DEVICE             "/dev/ttyACM0"
#define ROBOT_MODEL        "a1_l"
#define MOUNT_ORIENTATION  "vertical"
#define DOF                7
#define TIME_STEP_S        0.01            /* 100 Hz */
#define LOG_DIR            "./trajectory_log"
#define MAX_FILES          128
#define MAX_PATH_LEN       256
/* ======================================== */

static atomic_bool g_running = ATOMIC_VAR_INIT(true);
static onero_drag_teaching_handle g_dt = NULL;

static void make_record_path(char* out, size_t cap) {
    time_t t = time(NULL);
    struct tm tm_buf;
    localtime_r(&t, &tm_buf);
    snprintf(out, cap,
             LOG_DIR "/drag_record_%04d%02d%02d_%02d%02d%02d.dat",
             tm_buf.tm_year + 1900, tm_buf.tm_mon + 1, tm_buf.tm_mday,
             tm_buf.tm_hour,        tm_buf.tm_min,     tm_buf.tm_sec);
}

static void* timer_thread(void* arg) {
    (void)arg;
    const long period_us = (long)(TIME_STEP_S * 1e6);
    while (atomic_load(&g_running)) {
        if (g_dt) onero_drag_teaching_timer_callback(g_dt);
        usleep((useconds_t)period_us);
    }
    return NULL;
}

/* 把 LOG_DIR 下所有 .dat 文件名收集到 files，按文件名倒序（最新在前）。 */
static int list_dat_files(char files[][MAX_PATH_LEN], int max_n) {
    DIR* d = opendir(LOG_DIR);
    if (!d) return 0;
    int n = 0;
    struct dirent* e;
    while (n < max_n && (e = readdir(d)) != NULL) {
        size_t len = strlen(e->d_name);
        if (len > 4 && strcmp(e->d_name + len - 4, ".dat") == 0) {
            snprintf(files[n++], MAX_PATH_LEN, "%s/%s", LOG_DIR, e->d_name);
        }
    }
    closedir(d);
    /* 简单选择排序：n 通常很小 */
    for (int i = 0; i < n; ++i) {
        for (int j = i + 1; j < n; ++j) {
            if (strcmp(files[i], files[j]) < 0) {
                char tmp[MAX_PATH_LEN];
                strcpy(tmp, files[i]);
                strcpy(files[i], files[j]);
                strcpy(files[j], tmp);
            }
        }
    }
    return n;
}

static void print_menu(void) {
    printf("\n>>> 命令: 0=停止 1=开始录制 2=停止录制 3=回放当前 4=回放历史 5=退出\n>>> ");
    fflush(stdout);
}

static int read_int_line(int* out_cmd) {
    char line[64];
    if (!fgets(line, sizeof(line), stdin)) return -1;   /* EOF */
    char* p = line;
    while (*p == ' ' || *p == '\t') ++p;
    if (*p == '\0' || *p == '\n') { *out_cmd = -1; return 0; }
    *out_cmd = (int)strtol(p, NULL, 10);
    return 0;
}

static void select_and_replay(void) {
    static char files[MAX_FILES][MAX_PATH_LEN];
    int n = list_dat_files(files, MAX_FILES);
    if (n == 0) {
        printf("[X] 未找到轨迹文件 (%s)，先用命令 1/2 录一段再回放。\n", LOG_DIR);
        return;
    }
    printf("找到 %d 个轨迹文件:\n", n);
    for (int i = 0; i < n; ++i) {
        const char* base = strrchr(files[i], '/');
        printf("  [%d] %s\n", i + 1, base ? base + 1 : files[i]);
    }
    printf("输入编号 (1-%d)，0 取消: ", n);
    fflush(stdout);

    int idx = 0;
    if (read_int_line(&idx) != 0) return;
    if (idx < 1 || idx > n) {
        printf("已取消\n");
        return;
    }
    onero_drag_teaching_set_replay_file(g_dt, files[idx - 1]);
    int rc = onero_drag_teaching_handle_command(g_dt, 3);
    const char* base = strrchr(files[idx - 1], '/');
    printf("%s 回放: %s ret=%d\n",
           rc == 0 ? "[OK]" : "[X]",
           base ? base + 1 : files[idx - 1],
           rc);
}

int main(void) {
    mkdir(LOG_DIR, 0755);   /* 已存在则忽略 */
    char record_file[MAX_PATH_LEN];
    make_record_path(record_file, sizeof(record_file));

    g_dt = onero_drag_teaching_create();
    if (!g_dt) {
        fprintf(stderr, "[X] onero_drag_teaching_create failed\n");
        return 1;
    }
    if (!onero_drag_teaching_initialize(g_dt, DOF, record_file, TIME_STEP_S)) {
        fprintf(stderr, "[X] initialize failed\n");
        onero_drag_teaching_destroy(g_dt);
        return 1;
    }
    if (!onero_drag_teaching_set_hardware(g_dt, DEVICE, "", ROBOT_MODEL, MOUNT_ORIENTATION)) {
        fprintf(stderr, "[X] set_hardware failed (device=%s, model=%s)\n", DEVICE, ROBOT_MODEL);
        onero_drag_teaching_destroy(g_dt);
        return 1;
    }
    printf("[OK] DragTeaching ready. record_file=%s\n", record_file);

    pthread_t tick;
    if (pthread_create(&tick, NULL, timer_thread, NULL) != 0) {
        fprintf(stderr, "[X] pthread_create failed\n");
        onero_drag_teaching_destroy(g_dt);
        return 1;
    }

    print_menu();
    int cmd = -1;
    while (read_int_line(&cmd) == 0) {
        if (cmd == 5) break;
        if (cmd == 4) { select_and_replay(); print_menu(); continue; }
        if (cmd < 0 || cmd > 3) {
            printf("[X] 无效命令\n");
            print_menu();
            continue;
        }
        int rc = onero_drag_teaching_handle_command(g_dt, cmd);
        printf("%s handle_command(%d) ret=%d\n", rc == 0 ? "[OK]" : "[X]", cmd, rc);
        print_menu();
    }

    atomic_store(&g_running, false);
    pthread_join(tick, NULL);
    onero_drag_teaching_destroy(g_dt);
    printf("[OK] 退出\n");
    return 0;
}
