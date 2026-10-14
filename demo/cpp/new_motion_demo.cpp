#include "onero_interface_cpp.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>

int main(int argc, char **argv) {
    const char *gate=std::getenv("WOANARM_RUN_MOTION");
    if (argc != 2 || !gate || std::strcmp(gate,"YES") != 0) {
        std::cerr << "Safety gate: WOANARM_RUN_MOTION=YES " << argv[0] << " /dev/serial/by-id/...\n";
        return 2;
    }
    onero_api::onero_config_t cfg{};
    std::snprintf(cfg.device, sizeof cfg.device, "%s", argv[1]);
    std::snprintf(cfg.robot_model, sizeof cfg.robot_model, "a1_l");
    std::snprintf(cfg.version, sizeof cfg.version, "A1");
    std::snprintf(cfg.mount_orientation, sizeof cfg.mount_orientation, "vertical");
    cfg.dof=7; cfg.baud_rate=921600; cfg.with_gripper=true;
    onero_api::OneroArm arm(cfg); if (!arm.valid()) return 1;
    int rc=arm.enable_motors();
    if (rc==0) {
        auto start=arm.get_end_effector_pose(), via=start, target=start;
        via.x+=0.005; via.z+=0.002; target.x+=0.010;
        rc=arm.movec(via,target,0.1,0);
    }
    arm.disable_motors(); return rc==0 ? 0 : 1;
}
