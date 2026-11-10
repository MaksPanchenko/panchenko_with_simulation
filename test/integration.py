from pathlib import Path
from ament_index_python.packages import get_package_prefix
import collections
import math
import os
import pty
import select
import signal
import struct
import subprocess
import threading
import time
import tty
from functools import reduce
from operator import xor

import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from rcl_interfaces.srv import SetParametersAtomically, GetParameters
from sensor_msgs.msg import Imu, MagneticField, BatteryState
from std_msgs.msg import Float64, Bool, String
from mavros_msgs.msg import State
from geometry_msgs.msg import PoseStamped, Vector3
from mavros_msgs.msg import RCIn, RCOut, OverrideRCIn, ActuatorControl
from tf2_msgs.msg import TFMessage
from multiwii.msg import MSPRawMessage
from multiwii.srv import ReceiveMSPRawMessage, SendMSPRawMessage

master, slave = pty.openpty()
tty.setraw(slave)
device = os.ttyname(slave)
requests = collections.Counter()
commands = {}
stop = threading.Event()
responses = {
    1: bytes([0, 1, 42]),
    2: b'CLFL',
    4: b'TEST' + struct.pack('<HBBB', 1, 0, 0, 4) + b'QEMU',
    64: bytes([1, 2, 3, 0]),
    100: struct.pack('<BBBI', 230, 3, 1, 4),
    101: struct.pack('<HHHIB', 1000, 0, 7, 0, 0),
    102: struct.pack('<9h', 0, 0, 512, 10, 20, 30, 100, 0, 0),
    103: struct.pack('<8H', *range(1000, 1008)),
    104: struct.pack('<8H', *range(1100, 1108)),
    105: struct.pack('<8H', *range(1200, 1208)),
    108: struct.pack('<3h', 100, 200, 30),
    109: struct.pack('<ih', 1234, 0),
    110: struct.pack('<BHHh', 120, 100, 500, 25),
    116: ('HORIZON;ARM;FAILSAFE;ANGLE;BEEPER;' + ''.join(
        f'EXTRA_{i:02}_' + 'x' * 32 + ';' for i in range(27))).encode(),
    119: bytes([2, 0, 27, 1, 13] + list(range(100, 127))),
    58: struct.pack('<i', 150),
    200: b'',
    214: b'',
}

def serve():
    buf = bytearray()
    while not stop.is_set():
        if not select.select([master], [], [], 0.05)[0]:
            continue
        try:
            buf.extend(os.read(master, 8192))
        except OSError:
            break
        while len(buf) >= 6:
            pos = buf.find(b'$M<')
            if pos < 0:
                buf.clear()
                break
            if pos:
                del buf[:pos]
            if len(buf) < 6:
                break
            size, mid = buf[3:5]
            if len(buf) < size + 6:
                break
            packet = bytes(buf[:size + 6])
            del buf[:size + 6]
            assert reduce(xor, packet[3:], 0) == 0, 'bad MSP checksum'
            requests[mid] += 1
            if mid in (200, 214):
                commands[mid] = packet[5:-1]
            payload = responses.get(mid, b'')
            if payload is None:
                continue
            body = (bytes([255, mid]) + struct.pack('<H', len(payload)) if len(payload) >= 255
                    else bytes([len(payload), mid])) + payload
            response = b'$M>' + body + bytes([reduce(xor, body, 0)])
            if mid == 116:
                # Fragment the Jumbo header and a payload larger than Asio's first read buffer.
                os.write(master, response[:4])
                time.sleep(0.005)
                os.write(master, response[4:7])
                time.sleep(0.005)
                os.write(master, response[7:])
            else:
                os.write(master, response)

worker = threading.Thread(target=serve, daemon=True)
worker.start()
rclpy.init()
probe = Node('multiwii_integration_check')
received = {}
state_received = {}
armed_samples = []
transforms = {}
attitude_transforms = {}
subscriptions = []


def receive_transforms(message):
    for transform in message.transforms:
        transforms[(transform.header.frame_id, transform.child_frame_id)] = transform
        if transform.child_frame_id == 'multiwii':
            stamp = transform.header.stamp
            attitude_transforms[(stamp.sec, stamp.nanosec)] = transform
    while len(attitude_transforms) > 128:
        del attitude_transforms[next(iter(attitude_transforms))]


for topic, kind in {
    'imu/data': Imu,
    'imu/mag': MagneticField,
    'local_position/pose': PoseStamped,
    'rpy': Vector3,
    'rc/in': RCIn,
    'rc/servo': RCOut,
    'motors': RCOut,
    'battery': BatteryState,
    'global_position/compass_hdg': Float64,
    'global_position/rel_alt': Float64,
    'global_position/sonar_alt': Float64,
}.items():
    subscriptions.append(probe.create_subscription(kind, '/multiwii/' + topic,
        lambda msg, topic=topic: received.__setitem__(topic, msg), 10))
subscriptions.append(probe.create_subscription(TFMessage, '/tf',
    receive_transforms, 10))
for name, kind in {'armed': Bool, 'flight_mode': String, 'state': State}.items():
    subscriptions.append(probe.create_subscription(kind, '/multiwii/' + name,
        lambda msg, name=name: state_received.__setitem__(name, msg), 10))
subscriptions.append(probe.create_subscription(Bool, '/multiwii/armed',
    lambda msg: armed_samples.append(msg.data), 10))
rc_pub = probe.create_publisher(OverrideRCIn, '/multiwii/rc/override', 1)
raw_pub = probe.create_publisher(OverrideRCIn, '/multiwii/rc/override/raw', 1)
motor_pub = probe.create_publisher(ActuatorControl, '/multiwii/actuator_control', 1)
class ParameterClient:
    def __init__(self):
        self.setter = probe.create_client(SetParametersAtomically, '/multiwii/set_parameters_atomically')
        self.getter = probe.create_client(GetParameters, '/multiwii/get_parameters')

    def wait_for_services(self, timeout_sec):
        return self.setter.wait_for_service(timeout_sec=timeout_sec) and self.getter.wait_for_service(timeout_sec=timeout_sec)

    def set_parameters_atomically(self, parameters):
        return self.setter.call_async(SetParametersAtomically.Request(parameters=[p.to_parameter_msg() for p in parameters]))

    def get_parameters(self, names):
        return self.getter.call_async(GetParameters.Request(names=names))

client = ParameterClient()
root = Path(__file__).resolve().parents[1]
(root / '.runtime').mkdir(exist_ok=True)
log = (root / '.runtime' / 'integration-node.log').open('w')
node_args = [get_package_prefix('multiwii') + '/lib/multiwii/multiwii_node',
    '--ros-args', '--params-file', str(root / 'cfg' / 'sbc.yaml'),
    '-p', 'device:=' + device,
    '-p', 'MSP_ANALOG:=10.0', '-p', 'MSP_SONAR_ALTITUDE:=10.0',
    '-p', 'status_timeout:=0.6']
process = subprocess.Popen(node_args, stdout=log, stderr=subprocess.STDOUT)

def until(predicate, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        assert process.poll() is None, 'node exited; see .runtime/integration-node.log'
        rclpy.spin_once(probe, timeout_sec=0.03)
    raise AssertionError('timed out; received=' + str(sorted(received)))

def set_params(values):
    future = client.set_parameters_atomically([
        Parameter(name, value=value) for name, value in values.items()])
    until(future.done)
    return future.result().result

try:
    until(lambda: len(received) == 11 and len(transforms) == 2)
    assert math.isclose(received['imu/data'].linear_acceleration.z, 9.80665, rel_tol=1e-6)
    assert math.isclose(received['imu/data'].angular_velocity.x, math.radians(10 * 0.244140625), rel_tol=1e-6)
    assert math.isfinite(received['imu/data'].orientation.w)
    assert math.isclose(received['imu/mag'].magnetic_field.x, 100 * 0.092e-6, rel_tol=1e-6)
    assert received['rpy'].x == 10 and received['rpy'].y == 20 and received['rpy'].z == 30
    assert list(received['rc/in'].channels) == list(range(1200, 1208))
    assert list(received['rc/servo'].channels) == list(range(1000, 1008))
    assert list(received['motors'].channels) == list(range(1100, 1108))
    assert received['battery'].voltage == 12.0
    assert math.isclose(received['global_position/rel_alt'].data, 12.34, abs_tol=1e-5)
    assert received['global_position/sonar_alt'].data == 1.5
    assert set(transforms) == {('map', 'multiwii_cartesian'), ('multiwii_cartesian', 'multiwii')}
    print('PASS: all 11 telemetry topics, data conversions, private topic names, both TF transforms', flush=True)

    def attitude_matches(expected):
        pose = received['local_position/pose']
        stamp = pose.header.stamp
        transform = attitude_transforms.get((stamp.sec, stamp.nanosec))
        if transform is None or pose.header.frame_id != 'multiwii_cartesian':
            return False
        if pose.header.frame_id != transform.header.frame_id:
            return False
        q = pose.pose.orientation
        actual = (q.x, q.y, q.z, q.w)
        rotation = transform.transform.rotation
        if actual != (rotation.x, rotation.y, rotation.z, rotation.w):
            return False
        if not math.isclose(sum(v * v for v in actual), 1.0, abs_tol=1e-12):
            return False
        position = pose.pose.position
        translation = transform.transform.translation
        if (position.x, position.y, position.z) != (translation.x, translation.y, translation.z):
            return False
        return math.isclose(abs(sum(a * b for a, b in zip(actual, expected))), 1.0, abs_tol=1e-12)

    half_sqrt = math.sqrt(0.5)
    for angles, quaternion in [
        ((0, 0, 0), (0.0, 0.0, 0.0, 1.0)),
        ((90, 0, 90), (0.5, 0.5, 0.5, 0.5)),
        ((0, 90, 90), (-0.5, 0.5, 0.5, 0.5)),
        ((45, 90, 45), (0.0, half_sqrt, 0.0, half_sqrt)),
        ((10, 20, 30), (0.03813457647485015, 0.189307857412,
                       0.2392983377447303, 0.9515485246437885)),
    ]:
        roll, pitch, yaw = angles
        responses[108] = struct.pack('<3h', roll * 10, pitch * 10, yaw)
        until(lambda: attitude_matches(quaternion))
    print('PASS: PoseStamped/TF orientation, parent frame, shared timestamp and quaternion norm', flush=True)

    until(lambda: 'state' in state_received and state_received['state'].connected)
    assert state_received['flight_mode'].data == 'ACRO'
    assert not state_received['armed'].data
    for flags, expected_armed, expected_mode in [(10, True, 'ANGLE'), (3, True, 'HORIZON'),
                                               (15, True, 'FAILSAFE'), (16, False, 'ACRO')]:
        responses[101] = struct.pack('<HHHIB', 1000, 0, 7, flags, 0)
        until(lambda: state_received['armed'].data == expected_armed and
              state_received['flight_mode'].data == expected_mode)
    responses[101] = struct.pack('<HHHIB', 1000, 0, 7, 10, 0)
    until(lambda: state_received['armed'].data and state_received['flight_mode'].data == 'ANGLE')
    # Truncated STATUS must not publish fabricated disarm or refresh validity.
    responses[101] = b'\0\0'
    until(lambda: not state_received['state'].connected and
          state_received['flight_mode'].data == 'UNKNOWN')
    assert state_received['state'].armed
    assert state_received['flight_mode'].data == 'UNKNOWN'
    assert state_received['armed'].data
    responses[101] = None
    until(lambda: state_received['flight_mode'].data == 'UNKNOWN')
    responses[101] = struct.pack('<HHHIB', 1000, 0, 7, 0, 0)
    until(lambda: state_received['state'].connected and not state_received['armed'].data)
    print('PASS: fragmented MSP Jumbo boxes, reordered indices, arm/disarm, modes, malformed/status timeout, recovery', flush=True)

    # Zero magnetometer occurs in SITL: orientation must be marked unavailable, never NaN.
    responses[102] = struct.pack('<9h', 0, 0, 512, 0, 0, 0, 0, 0, 0)
    until(lambda: received['imu/data'].orientation_covariance[0] == -1.0)
    assert math.isfinite(received['imu/data'].orientation.w)

    assert client.wait_for_services(timeout_sec=3)
    assert not set_params({'acc_1g': 100.0}).successful
    assert set_params({'MSP_STATUS': 0.0}).successful
    until(lambda: not state_received['state'].connected)
    assert set_params({'MSP_STATUS': 10.0}).successful
    until(lambda: state_received['state'].connected)
    assert set_params({'MSP_RAW_IMU': 0.0}).successful
    # A later serial command marks the boundary after all queued IMU requests.
    until(lambda: raw_pub.get_subscription_count() > 0)
    barrier = requests[200]
    raw_pub.publish(OverrideRCIn(channels=[1500] * 18))
    until(lambda: requests[200] > barrier)
    baseline = requests[102]
    time.sleep(0.3)
    assert requests[102] == baseline, 'rate zero did not stop requests'
    assert set_params({'MSP_RAW_IMU': 20.0}).successful
    baseline = requests[102]
    started = time.monotonic()
    time.sleep(0.7)
    elapsed = time.monotonic() - started
    assert 8 / 0.7 <= (requests[102] - baseline) / elapsed <= 20 / 0.7
    assert not set_params({'MSP_RAW_IMU': -1.0}).successful
    assert not set_params({'MSP_RAW_IMU': float('nan')}).successful
    assert not set_params({'MSP_RAW_IMU': 10.0, 'MSP_RC': 101.0}).successful
    future = client.get_parameters(['MSP_RAW_IMU'])
    until(future.done)
    assert future.result().values[0].double_value == 20.0
    print('PASS: runtime rate changes, stop/restart at zero, invalid/atomic parameter rejection', flush=True)

    until(lambda: rc_pub.get_subscription_count() and raw_pub.get_subscription_count() and motor_pub.get_subscription_count())
    rc = OverrideRCIn()
    rc.channels = list(range(1400, 1418))
    commands.pop(200, None)
    rc_pub.publish(rc)
    until(lambda: 200 in commands)
    assert struct.unpack('<8H', commands[200]) == (1403, 1400, 1401, 1402, 1404, 1405, 1406, 1407)
    commands.pop(200, None)
    raw_pub.publish(rc)
    until(lambda: 200 in commands)
    assert struct.unpack('<18H', commands[200]) == tuple(rc.channels)
    motors = ActuatorControl()
    motors.controls = [0.0, 0.25, -0.5, 1.0, 0.0, 0.25, -0.5, 1.0]
    motor_pub.publish(motors)
    until(lambda: 214 in commands)
    assert struct.unpack('<8H', commands[214]) == (1000, 1250, 1500, 2000, 1000, 1250, 1500, 2000)
    print('PASS: RC remapping, raw RC, motor commands over MSP', flush=True)

    assert MSPRawMessage(id=101).id == 101
    assert ReceiveMSPRawMessage.Request(id=101).id == 101
    assert SendMSPRawMessage.Request(msg=MSPRawMessage(id=101)).msg.id == 101
    print('PASS: generated message/service interfaces', flush=True)
finally:
    if process.poll() is None:
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            print('FAIL: node failed to stop on SIGINT', flush=True)
    log.close()
    stop.set()
    worker.join(timeout=2)
    os.close(master)
    os.close(slave)
    probe.destroy_node()
    rclpy.shutdown()
assert process.returncode == 0, 'node exit code ' + str(process.returncode)
print('PASS: clean node shutdown', flush=True)
