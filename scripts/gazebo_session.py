#!/usr/bin/env python3
"""Launch the local Gazebo world, Betaflight, TCP/PTY adapter and ROS driver."""
import argparse
import fcntl
import os
import selectors
import shutil
import socket
import subprocess
import sys
import time

from runtime_support import ROOT, install_signals, start, stop, wait_ready

def main():
    parser = argparse.ArgumentParser(description='Gazebo Harmonic + Betaflight SITL + ROS 2')
    parser.add_argument('--headless', action='store_true', help='запустить без графического окна')
    parser.add_argument('--check', action='store_true', help='проверить ROS-телеметрию и завершить запуск')
    args = parser.parse_args()
    install_signals()
    state = ROOT / '.runtime' / 'gazebo'
    state.mkdir(parents=True, exist_ok=True)
    logs = state / 'logs'
    logs.mkdir(exist_ok=True)
    binary = state / 'bin' / 'betaflight_SITL.elf'
    bridge_binary = state / 'bin' / 'msp_tcp_bridge'
    for required in [binary, bridge_binary, state / 'lib' / 'libBetaflightPlugin.so']:
        if not required.is_file():
            raise RuntimeError('Сначала выполни ./scripts/build_gazebo.sh')
    if shutil.which('gz') is None:
        raise RuntimeError('Не установлен Gazebo Harmonic')
    if not args.headless and not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
        raise RuntimeError('Нет графического дисплея. Используй --headless')
    env = dict(os.environ, ROS_LOG_DIR=str(logs / 'ros'),
        GZ_PARTITION=f'multiwii_gazebo_{os.getuid()}',
        GZ_SIM_SYSTEM_PLUGIN_PATH=str(state / 'lib'),
        GZ_SIM_RESOURCE_PATH=str(ROOT / 'simulation' / 'models'),
        GSETTINGS_SCHEMA_DIR='/usr/share/glib-2.0/schemas')
    with (state / 'session.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Gazebo-сценарий уже запущен')
        for kind, port in [(socket.SOCK_STREAM, 5761), (socket.SOCK_DGRAM, 9002),
                           (socket.SOCK_DGRAM, 9003), (socket.SOCK_DGRAM, 9004)]:
            with socket.socket(socket.AF_INET, kind) as available:
                available.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    available.bind(('0.0.0.0', port))
                except OSError:
                    raise RuntimeError(f'Порт {port} занят. Останови предыдущий SITL/Gazebo')
        children, files = [], []
        try:
            def spawn(command, filename, **kwargs):
                stream = (logs / filename).open('w')
                files.append(stream)
                process = start(command, cwd=state, env=env, stdout=stream,
                                stderr=subprocess.STDOUT, **kwargs)
                children.append(process)
                return process

            if not (state / 'configured').is_file():
                config = state / 'startup.cli'
                config.write_text('feature -RX_SERIAL\nfeature -RX_MSP\nfeature RX_UDP\n'
                                  'map AETR1234\naux 0 0 0 1700 2100\nsave\n')
                configured = spawn([str(binary), '--config', str(config)], 'configure.log')
                if configured.wait(timeout=20):
                    raise RuntimeError('Не удалось настроить SITL; см. configure.log')
                if any(word in (logs / 'configure.log').read_text()
                       for word in ['### ERROR', 'Unknown command', 'Invalid']):
                    raise RuntimeError('SITL отверг настройки; см. configure.log')
                (state / 'configured').touch()

            print('Запускаю Betaflight SITL и Gazebo…', flush=True)
            sitl = spawn(['stdbuf', '-oL', '-eL', str(binary), '--ip', '127.0.0.1'], 'sitl.log')

            def tcp_ready():
                try:
                    with socket.create_connection(('127.0.0.1', 5761), timeout=0.1):
                        return True
                except OSError:
                    return False

            wait_ready(tcp_ready, [sitl], 'MSP TCP 5761', timeout=30)
            command = ['gz', 'sim', '-r', '-v', '3']
            if args.headless:
                command.append('-s')
            command.append(str(ROOT / 'simulation' / 'world.sdf'))
            gazebo = spawn(command, 'gazebo.log')
            wait_ready(lambda: 'new fdm' in (logs / 'sitl.log').read_text(errors='replace'),
                       [sitl, gazebo], 'Обмен Gazebo ↔ SITL', timeout=60)
            bridge = start([str(bridge_binary)], stdout=subprocess.PIPE, stderr=sys.stderr, env=env)
            children.append(bridge)
            with selectors.DefaultSelector() as selector:
                selector.register(bridge.stdout, selectors.EVENT_READ)
                if not selector.select(timeout=10):
                    raise RuntimeError('Мост TCP–PTY не открыл serial-порт')
                line = bridge.stdout.readline().decode().strip()
            if not line.startswith('BRIDGE_DEVICE='):
                raise RuntimeError('Ошибка запуска моста TCP–PTY')
            device = line.split('=', 1)[1]
            print(f'Gazebo ↔ Betaflight ↔ {device} ↔ ROS 2. Остановка: Ctrl+C.', flush=True)
            print(f'Логи: {logs}', flush=True)
            driver = start([str(ROOT / 'scripts' / 'run.sh'), 'mode:=hardware', f'device:={device}'],
                           cwd=ROOT, env=env)
            children.append(driver)
            watcher = start([sys.executable, str(ROOT / 'scripts' / 'watch_state.py')], env=env)
            children.append(watcher)
            check = None
            if args.check:
                check = start([sys.executable, str(ROOT / 'test' / 'check_gazebo.py')], env=env)
                children.append(check)
            while True:
                if any(child.poll() is not None for child in [sitl, gazebo, bridge, driver, watcher]):
                    raise RuntimeError('Один из компонентов завершился; см. логи Gazebo/SITL')
                if check is not None and check.poll() is not None:
                    if check.returncode:
                        raise RuntimeError('Проверка Gazebo/ROS 2 не пройдена')
                    break
                time.sleep(0.2)
        except KeyboardInterrupt:
            pass
        finally:
            for child in reversed(children):
                stop(child)
            for stream in files:
                stream.close()
            print('Gazebo, SITL и ROS 2 остановлены.', flush=True)

if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, subprocess.SubprocessError) as error:
        print(f'Ошибка: {error}', file=sys.stderr)
        sys.exit(1)
