"""Console continuation after the exact refused-HTTP startup failure."""
# ruff: noqa: BLE001, S110
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import signal
import stat
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVIDENCE = Path('/root/paired-gpio-migration.xj0q8tgi')
PREVIOUS = EVIDENCE / 'device-allow-recovery'
RECOVERY = EVIDENCE / 'hub-readiness-recovery'
FILES = {'recover_hub_readiness.py', 'recover_device_allow.py', 'migrate.py',
         'operator_checks.py', 'paired_gpio_client.py', 'maintenance.py', 'README.md'}


def require(value, label):
    if not value:
        raise RuntimeError(label)


def secure(path):
    for part in (path, *path.parents):
        info = part.lstat()
        require(not stat.S_ISLNK(info.st_mode) and info.st_uid == 0
                and not info.st_mode & 0o022, 'UNTRUSTED_PATH')


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_verified():
    secure(HERE)
    secure(HERE / 'manifest.json')
    manifest = json.loads((HERE / 'manifest.json').read_bytes())
    require(set(manifest) == {'files'} and set(manifest['files']) == FILES, 'MANIFEST_FILES')
    for name, identity in manifest['files'].items():
        secure(HERE / name)
        require(hashlib.sha256((HERE / name).read_bytes()).hexdigest() == identity, 'MANIFEST_HASH')
    prior = load('recover_device_allow')
    # Reuse the immutable original-package verification with this package's exact file set.
    prior.FILES = FILES
    m = prior.load_verified()
    return prior, m


def verify_previous():
    secure(PREVIOUS)
    for name in ('STARTED', 'FAILED', 'failure-private.log'):
        secure(PREVIOUS / name)
        require((PREVIOUS / name).is_file(), 'PREVIOUS_EVIDENCE')
    require(not (PREVIOUS / 'SUCCESS.json').exists(), 'PREVIOUS_SUCCESS')
    trace = (PREVIOUS / 'failure-private.log').read_text()
    require('ConnectionRefusedError: [Errno 111] Connection refused' in trace,
            'PREVIOUS_FAILURE_CHANGED')
    require(not re.findall(r'^RuntimeError:', trace, re.MULTILINE), 'PREVIOUS_FAILURE_CHANGED')
    # Bind the diagnostic to the archived v1 recovery source's observed call path.
    require(re.search(r'File "[^"\n]*/recover_device_allow.py", line 146, in continue_startup', trace)
            and re.search(r'File "[^"\n]*/operator_checks.py", line 163, in status', trace),
            'PREVIOUS_FAILURE_LOCATION')


def start_hub(m, state):
    c = m.c
    c.run(['systemctl', 'start', c.HUB], timeout=85)
    m.wait_hub_status(state['entries'])
    m.live_environment(state['entries'])
    require(all(c.active(name) for name in c.SERVICES), 'FINAL_SERVICES')
    c.pair_high()
    c.flow()
    m.verify_running()
    m.preserved(state)


def update_diagnostic(m):
    target = Path('/usr/local/lib/freeze-protect-maintenance-v1/maintenance.py')
    secure(target)
    before = target.read_bytes()
    require(hashlib.sha256(before).hexdigest() ==
            '07eae1c9181f3910cd50e1873f278355c5c0941c450778b5afab1b9b05c4d77c',
            'DIAGNOSTIC_BASELINE_CHANGED')
    candidate = (HERE / 'maintenance.py').read_bytes()
    compile(candidate, 'maintenance.py', 'exec')
    m.c.durable(RECOVERY / 'maintenance-before.py', before.decode())
    module = load('maintenance')
    preview = module.diagnostic()
    require(preview.get('access_version') == 1 and 'hub_recovery' in preview,
            'DIAGNOSTIC_PREVIEW_FAILED')
    m.atomic_write(target, candidate, stat.S_IMODE(target.stat().st_mode))


def execute(prior, m):
    c = m.c
    verify_previous()
    secure(EVIDENCE)
    require(not RECOVERY.exists() and not RECOVERY.is_symlink(), 'RECOVERY_ALREADY_ATTEMPTED')
    RECOVERY.mkdir(mode=0o700)
    m.sync_directory(EVIDENCE)
    c.LOG = RECOVERY / 'private.log'
    armed = False
    try:
        update_diagnostic(m)
        state = prior.preflight(m, pair_running=True)
        c.durable(RECOVERY / 'STARTED', 'Start only Hub after verified paired ownership/DRAIN.\n')
        armed = True
        start_hub(m, state)
        receipt = {'daemon_sha256': c.digest(m.DEST), 'command': 'DRAIN',
                   'operation': 'USER_OFF', 'gpio26': 'high', 'gpio20': 'high',
                   'lighting': 'disabled', 'physical_position': 'NOT_VERIFIED',
                   'evidence': str(RECOVERY), 'previous_failures_preserved': True}
        c.durable(RECOVERY / 'SUCCESS.json', json.dumps(receipt, sort_keys=True) + '\n')
        print('PAIRED_RECOVERY_VERIFIED; ' + json.dumps(receipt), flush=True)
        return 0
    except BaseException as exc:
        if armed:
            try:
                c.run(['systemctl', 'stop', c.HUB], timeout=45)
                c.stopped()
            except BaseException:
                pass
            try:
                if c.active(m.PAIR) and not c.DRAIN_OR_READBACK_FAILED:
                    c.drain()
            except BaseException:
                pass
        with (RECOVERY / 'failure-private.log').open('a') as stream:
            traceback.print_exc(file=stream)
        c.durable(RECOVERY / 'FAILED', 'Inspect private evidence. Do not retry.\n')
        safe = {'HUB_HTTP_STARTUP_TIMEOUT', 'HUB_STARTUP_EXITED', 'USER_OFF_REQUIRED',
                'DURABLE_STOP_REQUIRED', 'FINAL_SERVICES', 'RUNNING_COMMAND', 'RUNNING_INTERPRETER'}
        code = str(exc) if isinstance(exc, RuntimeError) and str(exc) in safe else type(exc).__name__
        print('RECOVERY_STOPPED code=' + code + '; evidence=' + str(RECOVERY), flush=True)
        return 1


def main():
    require(os.geteuid() == 0 and sys.argv[1:] == ['--loads-disconnected'], 'ROOT_AND_ISOLATION_REQUIRED')
    os.umask(0o077)
    prior, m = load_verified()
    descriptors = []
    try:
        for path in (Path('/var/lib/freeze-protect-maintenance/operation.lock'),
                     Path('/root/.paired-gpio-migration.lock')):
            secure(path)
            fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
            descriptors.append(fd)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        def interrupted(*_):
            raise RuntimeError('INTERRUPTED')
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            signal.signal(sig, interrupted)
        return execute(prior, m)
    finally:
        for fd in descriptors:
            os.close(fd)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print('RECOVERY_BOOTSTRAP_STOPPED type=' + type(exc).__name__)
        sys.exit(1)
