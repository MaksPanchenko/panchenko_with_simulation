#!/usr/bin/env python3
"""Launch the complete demo, observe ROS topics, then stop all launched processes."""
import os
from pathlib import Path
import signal
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
runtime = root / '.runtime'
runtime.mkdir(exist_ok=True)
env = dict(os.environ, ROS_DOMAIN_ID=os.environ.get('ROS_DOMAIN_ID', '74'),
           ROS_LOCALHOST_ONLY='1', ROS_LOG_DIR=str(runtime / 'launch-test-ros-log'))
with (runtime / 'launch-test.log').open('w') as log:
    process = subprocess.Popen([str(root / 'scripts' / 'run.sh'), 'cycle_seconds:=2.0'],
        stdout=log, stderr=subprocess.STDOUT, env=env, start_new_session=True)
    try:
        result = subprocess.run([sys.executable, str(root / 'scripts' / 'smoke.py'),
            '--timeout', '90'], env=env, timeout=110)
        if process.poll() is not None:
            raise RuntimeError('Launch exited early; see .runtime/launch-test.log')
        result.check_returncode()
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGINT)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise RuntimeError('Launch failed to shut down within 15 seconds')
    if process.returncode != 0:
        raise RuntimeError(f'Launch shutdown returned {process.returncode}')
print('PASS: launch shut down cleanly')
