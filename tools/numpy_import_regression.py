#!/usr/bin/env python3
"""Check NumPy/arm/gripper loading in fresh simulated processes, never hardware."""
import argparse
import hashlib
import importlib
import itertools
import json
import math
import platform
import subprocess
import sys
import tempfile
from pathlib import Path


def run(order):
    modules = {name: importlib.import_module(name) for name in order}
    np, oa = modules['numpy'], modules['oneroarm']
    with tempfile.TemporaryDirectory(prefix='sdk-numpy-offline-') as temp:
        device = str(Path(temp) / 'nonexistent-device')
        assert not Path(device).exists()
        cfg = oa.OneroConfig()
        cfg.device, cfg.simulation_mode = device, True
        cfg.robot_model, cfg.version, cfg.dof = 'a1_l', 'A1', 7
        cfg.mount_orientation = 'vertical'
        arm = oa.OneroArm(cfg)
        try:
            assert not arm.is_hardware_connected()
            assert arm.enable_motors()
            zeros = np.zeros(7)
            q = np.array([-0.158, 1.0, 1.2, -0.8, 0.1, 0.8, -1.0])
            assert arm.control_mit(zeros, zeros, q, zeros, zeros) == 0
            feedback = arm.get_joint_positions()
            assert len(feedback) == 7 and max(abs(a-b) for a,b in zip(q,feedback)) < 1e-4
            pose = arm.get_end_effector_pose()
            assert all(math.isfinite(getattr(pose,n)) for n in ('x','y','z','qw','qx','qy','qz'))
            assert all(math.isfinite(t) for t in arm.compute_gravity_torque(q.tolist()))
            if 'onerogripper' in modules:
                gripper = modules['onerogripper'].OneroGripper(device)
                assert not gripper.valid() and not gripper.status().valid
                del gripper
            providers = []
            if Path('/proc/self/maps').is_file():
                providers = sorted({line.split()[-1] for line in Path('/proc/self/maps').read_text().splitlines()
                                    if 'libstdc++' in line})
                if platform.machine().lower() in ('x86_64','aarch64'):
                    assert len(providers) <= 1, f'duplicate C++ runtimes: {providers}'
            print(json.dumps({'check':'NumPy SDK import order','result':'passed','order':order,
                              'numpy':np.__version__, 'python':platform.python_version(),
                              'modules':{n:{'path':m.__file__, 'sha256':hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest()}
                                         for n,m in modules.items()}, 'cpp_runtime_providers':providers,
                              'simulation_mode':True, 'hardware_connected':False}), flush=True)
        finally:
            assert arm.disable_motors()
            del arm


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm-only', action='store_true')
    parser.add_argument('--order', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.order:
        run(args.order.split(','))
    else:
        names = ('numpy','oneroarm') if args.arm_only else ('numpy','oneroarm','onerogripper')
        for order in itertools.permutations(names):
            subprocess.run([sys.executable,'-X','faulthandler',str(Path(__file__).resolve()),
                            '--order',','.join(order)], check=True, timeout=30)
