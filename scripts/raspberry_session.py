#!/usr/bin/env python3
"""Own a QEMU ARM64 guest and start the ROS demonstration inside it."""
import argparse
import fcntl
import os
import socket
import subprocess
import sys
import time

from runtime_support import ROOT, install_signals, start, stop

def ssh(command, **kwargs):
    return subprocess.run([str(ROOT / 'emulation' / 'ssh.sh'), command], **kwargs)

def main():
    parser = argparse.ArgumentParser(description='QEMU ARM64 + ROS 2 + MSP-эмулятор внутри VM')
    parser.add_argument('--build', action='store_true', help='пересобрать пакет внутри VM')
    parser.add_argument('--check', action='store_true', help='проверить состояния и завершить запуск')
    args = parser.parse_args()
    install_signals()
    vm = ROOT / '.runtime' / 'qemu'
    vm.mkdir(parents=True, exist_ok=True)
    with (vm / 'session.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Сценарий QEMU уже запущен')
        if not (vm / 'disk.qcow2').is_file():
            subprocess.run([str(ROOT / 'emulation' / 'prepare.sh')], check=True)
        with socket.socket() as check_port:
            try:
                check_port.bind(('127.0.0.1', int(os.environ.get('VM_SSH_PORT', '2233'))))
            except OSError:
                raise RuntimeError('SSH-порт занят. Сначала останови другой экземпляр QEMU')
        qemu = remote = None
        ready = False
        with (vm / 'console.log').open('w') as console:
            try:
                print('Запускаю QEMU ARM64. Загрузка Ubuntu может занять несколько минут.', flush=True)
                print(f'Консоль VM: {vm / "console.log"}', flush=True)
                qemu = start([str(ROOT / 'emulation' / 'start.sh')], stdin=subprocess.DEVNULL,
                             stdout=console, stderr=subprocess.STDOUT)
                deadline = time.monotonic() + float(os.environ.get('VM_BOOT_TIMEOUT', '600'))
                notice = time.monotonic() + 20
                while time.monotonic() < deadline:
                    if qemu.poll() is not None:
                        raise RuntimeError('QEMU завершился; см. .runtime/qemu/console.log')
                    result = ssh('true', stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if result.returncode == 0:
                        ready = True
                        break
                    if time.monotonic() > notice:
                        print('Ожидаю загрузку ARM64 Ubuntu и SSH…', flush=True)
                        notice = time.monotonic() + 20
                    time.sleep(1)
                if not ready:
                    raise RuntimeError('Не удалось дождаться SSH в QEMU')
                print('VM готова. Архитектура гостя:', flush=True)
                ssh('uname -m', check=True)
                subprocess.run([str(ROOT / 'emulation' / 'copy-source.sh')], check=True)
                available = ssh('test -x ~/temporary/install/multiwii/lib/multiwii/multiwii_node',
                                stdout=subprocess.DEVNULL).returncode == 0
                if args.build or not available:
                    print('Готовлю зависимости и собираю ROS 2 внутри VM…', flush=True)
                    ssh('cd ~/temporary && ./emulation/guest-setup.sh && '
                        './scripts/build.sh -DMULTIWII_EMULATION_BUILD=ON', check=True)
                if args.check:
                    ssh('cd ~/temporary && ./scripts/test.sh', check=True)
                ssh('cd ~/temporary && python3 scripts/demo_session.py --stop', check=True)
                command = ('cd ~/temporary && source /opt/ros/humble/setup.bash && '
                           'source install/setup.bash && exec python3 scripts/demo_session.py')
                if args.check:
                    command += ' --check'
                print('Запускаю ROS 2 и MSP-эмулятор ВНУТРИ ARM64 VM. Остановка: Ctrl+C.', flush=True)
                remote = start([str(ROOT / 'emulation' / 'ssh.sh'), command])
                while remote.poll() is None:
                    if qemu.poll() is not None:
                        raise RuntimeError('QEMU неожиданно завершился')
                    time.sleep(0.2)
                if remote.returncode:
                    raise RuntimeError(f'Гостевой ROS-стенд завершился с кодом {remote.returncode}')
            except KeyboardInterrupt:
                pass
            finally:
                if ready and qemu is not None and qemu.poll() is None:
                    print('Останавливаю ROS 2 и выключаю свою VM…', flush=True)
                    ssh('cd ~/temporary && python3 scripts/demo_session.py --stop',
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if remote is not None:
                        try:
                            remote.wait(timeout=15)
                        except subprocess.TimeoutExpired:
                            stop(remote)
                    ssh('sudo systemctl poweroff --force', stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL)
                    try:
                        qemu.wait(timeout=45)
                    except subprocess.TimeoutExpired:
                        stop(qemu)
                else:
                    stop(remote)
                    stop(qemu)

if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(f'Ошибка: {error}', file=sys.stderr)
        sys.exit(1)
