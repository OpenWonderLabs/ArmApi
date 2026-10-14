"""
Onero Robot Arm API Python Bindings via pybind11
"""
from enum import IntEnum
from typing import overload, Any, Callable, Optional, TypeAlias

JointArray: TypeAlias = list[float]

class OneroConfig:
    """
    Configuration structure for the Onero Robot Arm.
    """
    device: str
    robot_model: str
    dof: int
    baud_rate: int
    urdf_path: str
    version: str
    mount_orientation: str
    """Installation orientation: "horizontal" or "vertical" (default "vertical")."""
    mit_kp: list[float]
    """MIT-mode PD proportional gains (length up to 7, one per joint)."""
    mit_kd: list[float]
    """MIT-mode PD derivative gains (length up to 7, one per joint)."""
    model_description_path: str
    """onero_description 资源根目录。留空 -> 走 SDK 内置；非空时优先级最高，可被 ONERO_DESCRIPTION_PATH/DIR 环境变量覆盖。"""
    with_gripper: bool
    """Enable the optional arm-owned gripper on the same CAN bus."""
    simulation_mode: bool
    """Enable deterministic no-hardware mode for API/testing only."""

    def __init__(self) -> None: ...

class Pose:
    """
    Represents a Cartesian pose (Position + Orientation).
    """
    x: float
    y: float
    z: float
    qw: float
    qx: float
    qy: float
    qz: float

    def __init__(self) -> None: ...

class CartesianFrame(IntEnum):
    BASE = 0
    WORLD = 1
    TOOL = 2

class RigidTransform:
    """Rigid parent_T_child transform in metres and quaternion wxyz."""
    x: float
    y: float
    z: float
    qw: float
    qx: float
    qy: float
    qz: float

    def __init__(self) -> None: ...

class CartesianDelta:
    x: float
    y: float
    z: float
    qw: float
    qx: float
    qy: float
    qz: float

    def __init__(self) -> None: ...

class FrameSnapshot:
    """Immutable-by-convention frame calibration captured per operation."""
    has_world_from_base: bool
    world_from_base: RigidTransform
    flange_from_tool: RigidTransform

    def __init__(self) -> None: ...

def transform_pose(
    pose: Pose,
    from_frame: CartesianFrame,
    to_frame: CartesianFrame,
    frames: FrameSnapshot,
    current_base_from_tool: Optional[Pose] = None,
) -> Pose:
    """Transform a pose; WORLD/TOOL requests fail if required data is absent."""
    ...

def apply_cartesian_delta(
    current_base_from_tool: Pose,
    delta: CartesianDelta,
    delta_frame: CartesianFrame,
    frames: FrameSnapshot,
) -> Pose: ...

def flange_pose_to_tool(
    base_from_flange: Pose,
    flange_from_tool: RigidTransform,
) -> Pose: ...

def tool_pose_to_flange(
    base_from_tool: Pose,
    flange_from_tool: RigidTransform,
) -> Pose: ...

class CartesianServoLimits:
    """Runtime Cartesian soft limits requested by a ServoP command."""
    max_linear_velocity: float
    """Maximum translational speed in m/s (default 0.1)."""
    max_angular_velocity: float
    """Maximum rotational speed in rad/s (default 0.5)."""
    max_linear_acceleration: float
    """Maximum translational acceleration in m/s^2 (default 0.2)."""
    max_angular_acceleration: float
    """Maximum rotational acceleration in rad/s^2 (default 1.0)."""

    def __init__(self) -> None: ...

class ServoPState(IntEnum):
    IDLE = 0
    RUNNING = 1
    LIMIT_TRANSITION = 2
    BRAKING = 3
    HOLDING = 4
    FAULT = 5

class ServoPLimitFlag(IntEnum):
    NONE = 0
    CARTESIAN_VELOCITY = 1
    CARTESIAN_ACCELERATION = 2
    JOINT_POSITION = 4
    JOINT_VELOCITY = 8
    JOINT_ACCELERATION = 16
    SINGULARITY = 32
    COMMAND_TIMEOUT = 64
    FEEDBACK_STALE = 128

class ServoPStatus:
    """Thread-safe snapshot of the active ServoP session."""
    state: ServoPState
    accepted_sequence: int
    applied_sequence: int
    command_age_s: float
    requested_limits: CartesianServoLimits
    effective_limits: CartesianServoLimits
    joint_feasibility_scale: float
    limit_flags: int
    last_error: int
    target_pose: Pose
    actual_pose: Pose

    def __init__(self) -> None: ...

class JointServoLimits:
    """Optional symmetric per-joint ServoJ soft limits; empty lists use SDK limits."""
    max_velocity: JointArray
    max_acceleration: JointArray
    max_jerk: JointArray

    def __init__(self) -> None: ...

class ServoJState(IntEnum):
    IDLE = 0
    RUNNING = 1
    BRAKING = 2
    HOLDING = 3
    FAULT = 4

class ServoJLimitFlag(IntEnum):
    NONE = 0
    COMMAND_TIMEOUT = 1
    FEEDBACK_STALE = 2
    JOINT_POSITION = 4
    OTG_INFEASIBLE = 8
    DEADLINE_MISS = 16

class ServoJStatus:
    """Thread-safe snapshot of the SDK-owned ServoJ session."""
    state: ServoJState
    accepted_sequence: int
    applied_sequence: int
    sent_frame_count: int
    deadline_miss_count: int
    otg_update_count: int
    otg_replan_count: int
    command_age_s: float
    limit_flags: int
    last_error: int
    target_q: JointArray
    commanded_q: JointArray
    commanded_dq: JointArray
    commanded_ddq: JointArray

    def __init__(self) -> None: ...

class ArmStateFromMotor:
    """
    Arm state read from motors.
    """
    positions: JointArray
    velocities: JointArray
    torques: JointArray

    def __init__(self) -> None: ...

class GripperStatus:
    """
    Optional gripper state. Position and velocity are expressed in percent units.
    """
    position: float
    velocity: float
    force: float
    error: int
    valid: bool

    def __init__(self) -> None: ...

class GripperTactileValue:
    """
    One tactile force value. fx/fy/fz are expressed in N.
    """
    point_id: int
    fx: float
    fy: float
    fz: float
    valid: bool

    def __init__(self) -> None: ...

class GripperTactileSensorStatus:
    """
    Tactile status for one gripper-mounted sensor.
    """
    sensor_id: int
    total_force: GripperTactileValue
    points: list[GripperTactileValue]
    valid: bool

    def __init__(self) -> None: ...

class GripperTactileStatus:
    """
    Two-sensor gripper tactile snapshot.
    """
    sensors: list[GripperTactileSensorStatus]
    valid: bool

    def __init__(self) -> None: ...

class TrajectoryPoint:
    """
    Trajectory point with joint position, velocity and acceleration.
    """
    position: JointArray
    velocity: JointArray
    acceleration: JointArray

    def __init__(self) -> None: ...

class DragTeachingState(IntEnum):
    """
    Drag-teaching state machine values.
    """
    IDLE      = 0
    RECORDING = 1
    REPLAYING = 2

class GripperTeachingMode(IntEnum):
    """Gripper behavior used while recording a drag-teaching trajectory."""
    DISABLED  = 0
    POSITION  = 1
    BACKDRIVE = 2

class MoveResult(IntEnum):
    """
    Motion API result codes.
    """
    SUCCESS              = 0
    INVALID_PARAMS       = -1
    IK_FAILED            = -2
    COLLISION_DETECTED   = -3
    EXECUTION_FAILED     = -4
    TIMEOUT              = -5
    INTERRUPTED          = -6
    JOINT_LIMIT_EXCEEDED = -7
    BUSY                 = -8

ONERO_OK: int = 0
ONERO_ERR_INVALID_PARAMS: int = -1
ONERO_ERR_IK_FAILED: int = -2
ONERO_ERR_COLLISION_DETECTED: int = -3
ONERO_ERR_EXECUTION_FAILED: int = -4
ONERO_ERR_TIMEOUT: int = -5
ONERO_ERR_INTERRUPTED: int = -6
ONERO_ERR_JOINT_LIMIT_EXCEEDED: int = -7
ONERO_ERR_BUSY: int = -8

ONERO_CAN_OK: int = 0
ONERO_ERR_RAW_FRAME_INVALID_LEN: int = -10
ONERO_ERR_RAW_FRAME_INVALID_ID: int = -11
ONERO_ERR_RAW_FRAME_RESERVED_ID: int = -12
ONERO_ERR_RAW_FRAME_PORT_NOT_OPEN: int = -13
ONERO_ERR_RAW_FRAME_SEND_FAILED: int = -14

class OneroGripper:
    """
    Arm-owned optional gripper controller. Created as OneroArm.gripper.
    force_control torque is limited to +/-40 N.
    """
    def enable(self) -> bool: ...
    def disable(self) -> bool: ...
    def status(self) -> GripperStatus: ...
    def get_tactile(self) -> GripperTactileStatus: ...
    def set_position(self, percent: float) -> int: ...
    def move_position(
        self,
        percent: float,
        max_vel: float = 100.0,
        max_acc: float = 250.0,
        max_jerk: float = 1000.0,
    ) -> int: ...
    def force_control(self, torque: float) -> int: ...

class OneroArm:
    """
    Main interface for controlling the Onero Robot Arm.
    """
    gripper: Optional[OneroGripper]

    def __init__(self, config: OneroConfig, with_gripper: bool = False) -> None:
        """
        Initialize the OneroArm with the given configuration.
        """
        ...

    def has_gripper(self) -> bool:
        """
        Whether this arm was initialized with the optional gripper.
        """
        ...

    def enable_motors(self) -> bool:
        """
        Enable the robot motors. Returns True on success.
        """
        ...

    def disable_motors(self) -> bool:
        """
        Disable the robot motors. Returns True on success.
        """
        ...

    @overload
    def restore_arm(self) -> int:
        """
        Move the robot back to its default zero pose at a safe speed.
        """
        ...

    @overload
    def restore_arm(self, target: JointArray | list[float]) -> int:
        """
        Move the robot to a specific joint target at a safe speed.
        """
        ...

    def movej(self,
              target: JointArray | list[float],
              speed_scale: float = 1.0,
              trajectory_connect: int = 0) -> int:
        """
        Move joints to target positions.
        """
        ...

    def movel(self,
              pose: Pose,
              speed_scale: float = 1.0,
              trajectory_connect: int = 0) -> int:
        """
        Move end-effector linearly to target pose.
        """
        ...

    def movep(self,
              pose: Pose,
              speed_scale: float = 1.0,
              trajectory_connect: int = 0) -> int:
        """
        Move via point (Path movement).
        """
        ...

    def movec(self,
              via_pose: Pose,
              target_pose: Pose,
              speed_scale: float = 1.0,
              trajectory_connect: int = 0) -> int:
        """
        Follow the circular arc from fresh feedback through ``via_pose``.

        Poses are absolute ``base_T_link7`` transforms. Full circles and
        buffered mode are unsupported.
        """
        ...

    def start_servop(self) -> int:
        """Start the SDK-owned Cartesian pose servo loop."""
        ...

    def servop(self,
               pose: Pose,
               limits: CartesianServoLimits) -> int:
        """
        Atomically replace the latest ServoP target and runtime soft limits.

        A zero return means the command was accepted, not that the target pose
        has already been reached. ``pose`` is absolute ``base_T_link7`` in
        metres with a wxyz quaternion; ServoP v1 applies no TCP offset. All
        four limit values must be finite and strictly positive.
        """
        ...

    def stop_servop(self) -> int:
        """Controlled software stop and hold; this is not an emergency stop."""
        ...

    def get_servop_status(self) -> ServoPStatus:
        """Return the latest ServoP status snapshot."""
        ...

    def start_servoj(self, limits: JointServoLimits = ...) -> int:
        """Start the SDK-owned 100 Hz jerk-limited joint servo."""
        ...

    def servoj(self,
               target_q: JointArray | list[float],
               target_dq: JointArray | list[float] = ...,
               valid_for_seconds: float = 0.10) -> int:
        """
        Atomically replace the latest joint target.

        Each control tick samples the latest valid target (no waypoint queue).
        Moving replacements replan from continuous commanded q/dq/ddq under
        velocity/acceleration/jerk limits. Same targets refresh validity only.
        A nonzero terminal velocity continues in RUNNING until a new target,
        expiry or stop; a zero-velocity endpoint reaches HOLDING.
        Planned path/braking-envelope position violations report JOINT_POSITION
        and last_error=-7 asynchronously; inspect get_servoj_status().
        A zero return means accepted, not reached. Expiration starts a
        jerk-limited controlled stop while keeping the session available for
        a later fresh target.
        """
        ...

    def stop_servoj(self) -> int:
        """Wait for a jerk-limited brake from current q/dq/ddq and end the session.

        Success (0) means IDLE with zero commanded dq/ddq and a released arm
        command resource; a brake fault returns its negative error code.
        """
        ...

    def get_servoj_status(self) -> ServoJStatus:
        """Return the latest ServoJ status snapshot."""
        ...

    def estimate_movej_duration(self,
                                target: JointArray | list[float],
                                speed_scale: float = 1.0) -> float:
        """
        Estimate the MoveJ duration without executing motion.
        """
        ...

    def get_joint_positions(self) -> JointArray:
        """
        Get the current calculated joint positions.
        """
        ...

    def get_joint_positions_from_motors(self) -> JointArray:
        """
        Get the actual joint positions read from motors.
        """
        ...

    def get_joint_velocities(self) -> JointArray:
        """
        Get the current joint velocities.
        """
        ...

    def get_arm_state_from_motor(self) -> ArmStateFromMotor:
        """
        Get joint positions, velocities and torques from motors.
        """
        ...

    def get_arm_state_cached(self) -> ArmStateFromMotor:
        """
        Get the latest cached arm state without triggering CAN I/O.

        The cache is refreshed by the active control loop after every command,
        so upper-level scripts can poll state without contending on the motor
        bus. If the cache has never been written, this returns an empty state.
        """
        ...

    def get_end_effector_pose(self) -> Pose:
        """
        Get the current Cartesian pose of the end effector.
        """
        ...

    def get_end_effector_pose_cached(self) -> Pose:
        """
        Get the latest cached end-effector pose without triggering CAN I/O.
        """
        ...

    def send_trajectory_point(self, q: JointArray, dq: JointArray) -> int:
        """
        Send a single trajectory point (position and velocity) to the buffer.
        """
        ...

    def control_mit(self,
                    kp: JointArray,
                    kd: JointArray,
                    q: JointArray,
                    dq: JointArray,
                    tau: JointArray) -> int:
        """
        MIT force-position (impedance) control, one frame per call:
        tau_motor = kp*(q - q_act) + kd*(dq - dq_act) + tau.

        Call enable_motors() first; every array length must equal dof. q uses the
        same "SDK joint space" as get_arm_state_from_motor(); tau may be the value
        returned by compute_gravity_torque() to realise gravity-compensated
        zero-force / impedance behaviour. Resend at >=100 Hz.

        Returns 0 on success, -1 on array size mismatch, -2 if hardware is not
        initialised, -3 if a CAN write failed on at least one joint.
        """
        ...

    def compute_gravity_torque(self, q: JointArray) -> JointArray:
        """
        Compute the gravity-compensation torque (including robot_model calibration
        scaling) for joint configuration q. The result can be fed directly into
        control_mit's tau argument. Raises ValueError if len(q) != dof or the
        dynamics model is not ready.
        """
        ...

    def execute_buffered_trajectory(self) -> int:
        """
        Execute the trajectory currently stored in the buffer.
        """
        ...

    def clear_trajectory_buffer(self) -> int:
        """
        Clear the trajectory buffer.
        """
        ...

    def reset_stop_signal(self) -> None:
        """
        Clear a previously latched stop/interruption signal before issuing a new command.
        """
        ...

    def send_trajectory(self, trajectory: list[TrajectoryPoint]) -> int:
        """
        Submit a list of trajectory points (position/velocity/acceleration)
        for execution. Returns 0 on success.
        """
        ...

    def cancel_trajectory(self) -> int:
        """
        Request cancellation of Move/trajectory execution or ServoP.
        Returns 0 when the request is recorded (also when no motion is active),
        not when stopping has completed. An active ServoJ session returns
        BUSY(-8) without changing its state; use stop_servoj() instead.
        """
        ...

    def is_hardware_connected(self) -> bool:
        """
        Whether the underlying motor bus is currently online.
        """
        ...

    # ---------------- Raw CAN Frame API ---------------- #

    def send_can_frame(self, can_id: int, payload: bytes) -> int:
        """
        Send a custom CAN frame. payload is any bytes-like object
        (bytes / bytearray / memoryview), length must be <= 8.
        Returns 0 on success or a negative error code.
        """
        ...

    def register_can_frame_callback(
        self,
        callback: Optional[Callable[[int, bytes], None]],
    ) -> int:
        """
        Register a callback(can_id, payload_bytes) for non-reserved inbound
        frames. Re-registering replaces the previous callback; passing None
        clears it (equivalent to clear_can_frame_callback()).

        The callback runs on a dedicated DeviceSession callback worker and
        does not occupy the BusExecutor. payload_bytes is an owning Python
        copy. The bounded 64-event queue drops the oldest pending user frame
        when full. Re-registering from another thread fences the callback in
        flight when the call begins; a new-generation callback does not extend
        that fence. Self-register only affects later dispatch. Inside the
        callback only register/clear callback is part of the v1 re-entrant
        contract.
        """
        ...

    def clear_can_frame_callback(self) -> int:
        """Clear the callback; external clear fences the callback in flight when the call begins."""
        ...

    def pump_can_bus(self, timeout_ms: int) -> int:
        """
        Drive inbound frame dispatch for up to timeout_ms ms
        (0 means a single non-blocking poll). Returns 0 on success.
        """
        ...


class OneroDragTeaching:
    """
    Drag-teaching helper. Records joint trajectories from physical
    back-driving and replays them.
    """
    def __init__(self) -> None: ...

    def initialize(self,
                   dof: int,
                   record_file: str,
                   time_step: float = 0.01) -> bool:
        """
        Configure recording dof, output file path and sampling step.
        """
        ...

    def set_hardware(self,
                     device: str,
                     urdf_path: str,
                     robot_model: str,
                     mount_orientation: str = "horizontal",
                     with_gripper: bool = False) -> bool:
        """
        Bind the drag-teaching session to a hardware device. Set with_gripper=True
        to attach the arm-owned gripper on the shared bus and use the matching
        gravity-compensation scaling. This only makes the gripper available; it
        does not enable recording or move the gripper automatically.
        """
        ...

    def set_gripper_teaching_mode(self,
                                  mode: GripperTeachingMode) -> int:
        """
        Select gripper behavior while recording.

        DISABLED records an arm-only V1 trajectory. POSITION records a V2
        gripper channel while following targets supplied by
        set_gripper_target(). BACKDRIVE records the measured opening while the
        gripper is commanded with zero effort. This setting controls recording
        only; replaying a V2 file automatically replays its gripper channel.
        """
        ...

    def set_gripper_target(self, percent: float) -> int:
        """Queue a [0, 100] percent opening target for POSITION recording."""
        ...

    def get_gripper_status(self) -> GripperStatus:
        """Return current gripper feedback; valid is False when unavailable."""
        ...

    def enable_motors(self) -> int:
        """
        Enable motors for drag teaching without moving the arm.
        """
        ...

    @overload
    def restore_arm(self) -> int:
        """
        Move the arm back to its zero pose at a safe speed.
        """
        ...

    @overload
    def restore_arm(self, target: JointArray | list[float]) -> int:
        """
        Move the arm to a specific joint target at a safe speed.
        """
        ...

    def start_recording(self) -> int:
        """Start recording joint trajectory."""
        ...

    def stop_recording(self) -> int:
        """Stop recording and finalize the output file."""
        ...

    def set_replay_file(self, replay_file: str) -> None:
        """Select the file used by start_replay()."""
        ...

    def start_replay(self) -> int:
        """Start replaying the previously selected file."""
        ...

    def stop_replay(self) -> int:
        """Stop replay if it is running."""
        ...

    def handle_command(self, cmd: int) -> int:
        """Forward a UI command code to the drag-teaching state machine."""
        ...

    @staticmethod
    def handle_command_dual(left: "OneroDragTeaching",
                            right: "OneroDragTeaching",
                            cmd: int) -> int:
        """
        Forward a UI command code to two drag-teaching sessions.
        cmd=1/3 uses the SDK-side synchronized dual-arm path.
        """
        ...

    def timer_callback(self) -> None:
        """Periodic tick to advance recording or replay."""
        ...

    def get_state(self) -> DragTeachingState:
        """Return the current drag-teaching state."""
        ...

    def is_initialized(self) -> bool:
        """Whether initialize()/set_hardware() have been called successfully."""
        ...

    def update_joint_state(self,
                           position: JointArray,
                           velocity: JointArray,
                           effort: JointArray) -> None:
        """
        Push the latest measured joint state to the drag-teaching pipeline.
        Typically called from the control loop's sensor callback.
        """
        ...
