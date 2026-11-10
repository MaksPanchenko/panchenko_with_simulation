#!/usr/bin/env python3
"""Run the MSP demo inside the guest, with visible state and reliable SSH cleanup."""
import argparse
import json
import os
from pathlib import Path
import signal
import sys
import time

from runtime_support import ROOT, install_signals, start, stop

pid_file = ROOT / '.runtime' / 'guest-session.json'

def birth(pid):
    return Path(f'/proc/{pid}/stat').read_text().split(') ', 1)[1].split()[19]

parser = argparse.ArgumentParser()
parser.add_argument('--stop', action='store_true')
parser.add_argument('--check', action='store_true')
args = parser.parse_args()
if args.stop:
    try:
        saved = json.loads(pid_file.read_text())
        if birth(saved['pid']) == saved['birth']:
            os.kill(saved['pid'], signal.SIGTERM)
    except (FileNotFoundError, ProcessLookupError):
        pass
    sys.exit(0)

install_signals()
pid_file.parent.mkdir(exist_ok=True)
pid_file.write_text(json.dumps({'pid': os.getpid(), 'birth': birth(os.getpid())}))
children = []
try:
    children.append(start([str(ROOT / 'scripts' / 'run.sh')], cwd=ROOT))
    children.append(start([sys.executable, str(ROOT / 'scripts' / 'watch_state.py')]))
    if args.check:
        children.append(start([sys.executable, str(ROOT / 'scripts' / 'smoke.py'), '--timeout', '90']))
    while True:
        if any(child.poll() is not None for child in children[:2]):
            raise RuntimeError('ROS-стенд неожиданно завершился')
        if args.check and children[-1].poll() is not None:
            if children[-1].returncode:
                raise RuntimeError('Проверка ARM64 не пройдена')
            break
        time.sleep(0.2)
except KeyboardInterrupt:
    pass
finally:
    for child in reversed(children):
        stop(child)
    pid_file.unlink(missing_ok=True)
