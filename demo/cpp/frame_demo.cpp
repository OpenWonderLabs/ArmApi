#include "onero_interface_cpp.h"
#include <iostream>

int main() {
    onero_api::Pose base{}; base.x=0.2; base.z=0.3; base.qw=1.0;
    onero_api::FrameSnapshot frames{};
    frames.has_world_from_base=true;
    frames.world_from_base.x=1.0; frames.world_from_base.qw=1.0;
    frames.flange_from_tool.z=0.1; frames.flange_from_tool.qw=1.0;
    auto out=onero_api::transform_pose(base, onero_api::CartesianFrame::BASE,
        onero_api::CartesianFrame::WORLD, frames);
    std::cout << "world xyz=(" << out.x << ", " << out.y << ", " << out.z << ")\n";
}
