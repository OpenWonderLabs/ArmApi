class GripperStatus:
    position: float
    velocity: float
    force: float
    error: int
    valid: bool

class GripperTactileValue:
    point_id: int
    fx: float
    fy: float
    fz: float
    valid: bool

class GripperTactileSensorStatus:
    sensor_id: int
    total_force: GripperTactileValue
    points: list[GripperTactileValue]
    valid: bool

class GripperTactileStatus:
    sensors: list[GripperTactileSensorStatus]
    valid: bool

class OneroGripper:
    def __init__(self, device: str) -> None: ...
    def valid(self) -> bool: ...
    def enable(self) -> int: ...
    def disable(self) -> int: ...
    def status(self) -> GripperStatus: ...
    def get_tactile(self) -> GripperTactileStatus: ...
    def set_position(self, percent: float) -> int: ...
    def move_position(self, percent: float, max_vel: float = 100.0,
                      max_acc: float = 250.0, max_jerk: float = 1000.0) -> int: ...
    def force_control(self, torque: float) -> int: ...
    def request_stop(self) -> None: ...
    def clear_stop(self) -> None: ...
