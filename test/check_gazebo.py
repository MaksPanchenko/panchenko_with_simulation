"""Require real Betaflight state and sensor telemetry through the TCP/PTY bridge."""
import math
import time
import rclpy
from rclpy.node import Node
from mavros_msgs.msg import State
from sensor_msgs.msg import Imu
from std_msgs.msg import Float64

rclpy.init()
node = Node('gazebo_check')
received = {}
subscriptions = []
for suffix, kind in [('state', State), ('imu/data', Imu), ('global_position/rel_alt', Float64)]:
    subscriptions.append(node.create_subscription(kind, '/multiwii/' + suffix,
        lambda message, suffix=suffix: received.__setitem__(suffix, message), 10))
try:
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
        if len(received) == 3 and received['state'].connected:
            assert received['state'].mode != 'UNKNOWN'
            assert math.isfinite(received['imu/data'].linear_acceleration.z)
            assert math.isfinite(received['global_position/rel_alt'].data)
            print('PASS: Gazebo ↔ Betaflight SITL ↔ TCP/PTY ↔ ROS 2 (state, IMU, altitude)', flush=True)
            break
    else:
        raise RuntimeError(f'Нет телеметрии SITL: получено {list(received)}')
finally:
    node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()
