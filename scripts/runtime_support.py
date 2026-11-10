"""Lifecycle helpers for the two local run scenarios."""
import os
from pathlib import Path
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]

def interrupt(signum, frame):
    raise KeyboardInterrupt

def install_signals():
    signal.signal(signal.SIGTERM, interrupt)

def start(command, **kwargs):
    return subprocess.Popen(command, start_new_session=True, **kwargs)

def stop(process, timeout=8):
    if process is None or process.poll() is not None:
        return
    for signum, delay in [(signal.SIGINT, timeout), (signal.SIGTERM, 3), (signal.SIGKILL, 3)]:
        try:
            os.killpg(process.pid, signum)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=delay)
            return
        except subprocess.TimeoutExpired:
            pass

def wait_ready(predicate, processes, description, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for process in processes:
            if process.poll() is not None:
                raise RuntimeError(f'{description}: процесс завершился с кодом {process.returncode}')
        if predicate():
            return
        time.sleep(0.1)
    raise RuntimeError(f'{description}: превышено ожидание {timeout} с')
