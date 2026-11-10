#!/usr/bin/env python3
"""Display actual ROS controller state changes in the launch terminal."""
import time
import rclpy
from rclpy.node import Node
from mavros_msgs.msg import State

rclpy.init()
node = Node('multiwii_console')
last = None

def show(message):
    global last
    current = (message.connected, message.armed, message.mode)
    if current != last:
        last = current
        state = 'ARMED' if message.armed else 'DISARMED'
        print(f'[СОСТОЯНИЕ] связь={message.connected}  {state}  режим={message.mode}', flush=True)

subscription = node.create_subscription(State, '/multiwii/state', show, 10)
deadline = time.monotonic() + 45
try:
    while rclpy.ok():
        rclpy.spin_once(node, timeout_sec=0.2)
        if last is None and time.monotonic() > deadline:
            raise RuntimeError('Нет данных /multiwii/state в течение 45 секунд')
except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
    pass
finally:
    node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()
