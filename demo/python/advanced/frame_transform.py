"""Frame：不连接硬件的坐标变换示例。"""

import oneroarm


def identity_pose(x: float = 0.0, y: float = 0.0, z: float = 0.0) -> oneroarm.Pose:
    pose = oneroarm.Pose()
    pose.x, pose.y, pose.z = x, y, z
    pose.qw, pose.qx, pose.qy, pose.qz = 1.0, 0.0, 0.0, 0.0
    return pose


def print_pose(name: str, pose: oneroarm.Pose) -> None:
    print(
        f"{name}: xyz=({pose.x:.3f}, {pose.y:.3f}, {pose.z:.3f}), "
        f"wxyz=({pose.qw:.3f}, {pose.qx:.3f}, {pose.qy:.3f}, {pose.qz:.3f})"
    )


def main() -> None:
    frames = oneroarm.FrameSnapshot()
    frames.has_world_from_base = True
    frames.world_from_base.x = 1.0  # world_T_base
    frames.flange_from_tool.z = 0.10  # flange_T_tool

    base_pose = identity_pose(x=0.20, z=0.30)
    world_pose = oneroarm.transform_pose(
        base_pose,
        oneroarm.CartesianFrame.BASE,
        oneroarm.CartesianFrame.WORLD,
        frames,
    )
    tool_relative = oneroarm.transform_pose(
        base_pose,
        oneroarm.CartesianFrame.BASE,
        oneroarm.CartesianFrame.TOOL,
        frames,
        current_base_from_tool=base_pose,
    )

    delta = oneroarm.CartesianDelta()
    delta.x = 0.01
    shifted = oneroarm.apply_cartesian_delta(
        base_pose,
        delta,
        oneroarm.CartesianFrame.TOOL,
        frames,
    )
    tool_pose = oneroarm.flange_pose_to_tool(base_pose, frames.flange_from_tool)
    flange_pose = oneroarm.tool_pose_to_flange(tool_pose, frames.flange_from_tool)

    print_pose("world pose", world_pose)
    print_pose("tool-relative pose", tool_relative)
    print_pose("shifted pose", shifted)
    print_pose("tool pose", tool_pose)
    print_pose("flange pose", flange_pose)


if __name__ == "__main__":
    main()
