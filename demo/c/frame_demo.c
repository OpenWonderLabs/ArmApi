#include "onero_interface_c.h"
#include <stdio.h>

int main(void) {
    onero_pose_t base = {.x=0.2, .z=0.3, .qw=1.0};
    onero_frame_snapshot_t frames = {0};
    frames.has_world_from_base = true;
    frames.world_from_base.x = 1.0;
    frames.world_from_base.qw = 1.0;
    frames.flange_from_tool.z = 0.1;
    frames.flange_from_tool.qw = 1.0;
    onero_pose_t out = {0};
    int rc = onero_transform_pose(&base, ONERO_FRAME_BASE, ONERO_FRAME_WORLD,
                                  &frames, NULL, &out);
    printf("rc=%d world xyz=(%.3f, %.3f, %.3f)\n", rc, out.x, out.y, out.z);
    return rc == 0 ? 0 : 1;
}
