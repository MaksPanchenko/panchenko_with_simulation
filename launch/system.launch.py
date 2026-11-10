"""One entry point for a physical serial controller or the bundled MSP emulator."""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, EmitEvent, OpaqueFunction, RegisterEventHandler
from launch.event_handlers import OnProcessExit, OnProcessIO
from launch.events import Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

def start(context):
    value = lambda key: LaunchConfiguration(key).perform(context)
    mode = value('mode')
    if mode not in ('emulator', 'hardware'):
        raise RuntimeError('mode must be emulator or hardware')
    parameters = [value('config'), {'baudrate': int(value('baudrate'))}]

    def driver(device):
        return Node(package='multiwii', executable='multiwii_node', name='multiwii',
                    output='screen', parameters=parameters + [{'device': device}])

    if mode == 'hardware':
        node = driver(value('device'))
        return [RegisterEventHandler(OnProcessExit(target_action=node,
                    on_exit=[EmitEvent(event=Shutdown(reason='Driver exited'))])), node]

    from launch.actions import ExecuteProcess
    from ament_index_python.packages import get_package_prefix
    emulator = ExecuteProcess(cmd=[os.path.join(get_package_prefix('multiwii'),
        'lib', 'multiwii', 'msp_emulator'), '--cycle-seconds', value('cycle_seconds')],
        output='screen')
    pending = bytearray()
    started = False

    def ready(event):
        nonlocal started
        pending.extend(event.text)
        if started or b'\n' not in pending:
            return []
        for line in bytes(pending).splitlines():
            if line.startswith(b'EMULATOR_DEVICE='):
                started = True
                node = driver(line.decode('ascii').split('=', 1)[1])
                return [RegisterEventHandler(OnProcessExit(target_action=node,
                            on_exit=[EmitEvent(event=Shutdown(reason='Driver exited'))])), node]
        return []

    return [RegisterEventHandler(OnProcessIO(target_action=emulator, on_stdout=ready)),
            RegisterEventHandler(OnProcessExit(target_action=emulator,
                on_exit=[EmitEvent(event=Shutdown(reason='Emulator exited'))])), emulator]

def generate_launch_description():
    share = get_package_share_directory('multiwii')
    return LaunchDescription([
        DeclareLaunchArgument('mode', default_value='emulator', description='emulator or hardware'),
        DeclareLaunchArgument('config', default_value=os.path.join(share, 'cfg', 'sbc.yaml')),
        DeclareLaunchArgument('device', default_value='/dev/ttyUSB0'),
        DeclareLaunchArgument('baudrate', default_value='115200'),
        DeclareLaunchArgument('cycle_seconds', default_value='3.0'),
        OpaqueFunction(function=start),
    ])
