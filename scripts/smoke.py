#!/usr/bin/env python3
"""Check the one-launch emulator demo, including all four scripted states."""
import argparse
import time

import rclpy
from rclpy.node import Node
from mavros_msgs.msg import State
from sensor_msgs.msg import Imu
from std_msgs.msg import Bool, String

parser = argparse.ArgumentParser()
parser.add_argument('--timeout', type=float, default=45.0)
args = parser.parse_args()
rclpy.init()
node = Node('multiwii_smoke')
seen, armed, modes = set(), set(), set()
imus = []
subscriptions = [
    node.create_subscription(State, '/multiwii/state',
        lambda msg: seen.add((msg.armed, msg.mode)) if msg.connected else None, 10),
    node.create_subscription(Bool, '/multiwii/armed', lambda msg: armed.add(msg.data), 10),
    node.create_subscription(String, '/multiwii/flight_mode', lambda msg: modes.add(msg.data), 10),
    node.create_subscription(Imu, '/multiwii/imu/data', lambda msg: imus.append(msg), 10),
]
expected = {(False, 'ACRO'), (True, 'ANGLE'), (True, 'HORIZON'), (False, 'FAILSAFE')}
deadline = time.monotonic() + args.timeout
try:
    while time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
        if expected <= seen and armed == {False, True} and {'ACRO', 'ANGLE', 'HORIZON', 'FAILSAFE'} <= modes and imus:
            print('PASS: emulator launch, ARM/DISARM, ACRO/ANGLE/HORIZON/FAILSAFE, IMU')
            break
    else:
        raise SystemExit(f'FAIL: observed states={seen}, armed={armed}, modes={modes}, imu={len(imus)}')
finally:
    node.destroy_node()
    rclpy.shutdown()
