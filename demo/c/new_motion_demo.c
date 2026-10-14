#include "onero_interface_c.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv) {
    if (argc != 2 || strcmp(getenv("WOANARM_RUN_MOTION") ? getenv("WOANARM_RUN_MOTION") : "", "YES") != 0) {
        fprintf(stderr, "Safety gate: WOANARM_RUN_MOTION=YES %s /dev/serial/by-id/...\n", argv[0]);
        return 2;
    }
    onero_config_t cfg = {0};
    snprintf(cfg.device, sizeof cfg.device, "%s", argv[1]);
    snprintf(cfg.robot_model, sizeof cfg.robot_model, "a1_l");
    snprintf(cfg.version, sizeof cfg.version, "A1");
    snprintf(cfg.mount_orientation, sizeof cfg.mount_orientation, "vertical");
    cfg.dof = 7; cfg.baud_rate = 921600; cfg.with_gripper = true;
    onero_handle arm = onero_create_robot(&cfg);
    if (!arm) return 1;
    int rc = onero_enable_motors(arm);
    if (rc == 0) {
        onero_pose_t start = onero_get_end_effector_pose(arm);
        onero_pose_t via = start, target = start;
        via.x += 0.005; via.z += 0.002; target.x += 0.010;
        rc = onero_movec(arm, &via, &target, 0.1, 0);
    }
    onero_disable_motors(arm); onero_destroy_robot(arm);
    return rc == 0 ? 0 : 1;
}
