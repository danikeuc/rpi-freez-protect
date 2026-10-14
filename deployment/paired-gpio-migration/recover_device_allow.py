"""One console-only continuation of the inventoried DeviceAllow ordering stop."""
# ruff: noqa: BLE001, S110
import fcntl
import hashlib
import importlib.util
import io
import json
import os
import re
import signal
import stat
import sys
import tarfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKAGE = Path('/usr/local/lib/freeze-protect-maintenance-v1/package')
ARCHIVE = PACKAGE.parent / 'migration.tar.gz'
PACKAGE_SHA = 'f4c87e6439650f80c02b2d1b17c76661c5e3d74bbf7c672eab28edadc9883513'
EVIDENCE = Path('/root/paired-gpio-migration.xj0q8tgi')
RECOVERY = EVIDENCE / 'device-allow-recovery'
FILES = {'recover_device_allow.py', 'migrate.py', 'operator_checks.py', 'paired_gpio_client.py', 'README.md'}


def require(value, code):
    if not value:
        raise RuntimeError(code)


def secure(path):
    for part in (path, *path.parents):
        info = part.lstat()
        require(not stat.S_ISLNK(info.st_mode) and info.st_uid == 0
                and not info.st_mode & 0o022, 'UNTRUSTED_PATH')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    secure(path)
    require(path.is_file() and path.stat().st_size < 4 * 1024 * 1024, 'INVALID_RECORD')
    return json.loads(path.read_bytes())


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_verified():
    secure(HERE)
    manifest = read_json(HERE / 'manifest.json')
    require(set(manifest) == {'files'} and set(manifest['files']) == FILES, 'MANIFEST_FILES')
    for name, identity in manifest['files'].items():
        secure(HERE / name)
        require(digest((HERE / name).read_bytes()) == identity, 'MANIFEST_HASH')
    secure(ARCHIVE)
    raw = ARCHIVE.read_bytes()
    require(digest(raw) == PACKAGE_SHA, 'ORIGINAL_PACKAGE_HASH')
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
        members = archive.getmembers()
        require(len(members) == 14 and len({p.name for p in members}) == 14, 'ORIGINAL_MEMBERS')
        for member in members:
            require(member.isfile() and re.fullmatch(r'[A-Za-z0-9_.-]+', member.name)
                    and member.name not in ('.', '..') and member.size <= 1024 * 1024, 'ORIGINAL_MEMBER')
            path = PACKAGE / member.name
            secure(path)
            require(path.read_bytes() == archive.extractfile(member).read(), 'ORIGINAL_PACKAGE_CHANGED')
    for name in ('operator_checks.py', 'paired_gpio_client.py'):
        require((HERE / name).read_bytes() == (PACKAGE / name).read_bytes(), 'CHECKS_CHANGED')
    c = load_module('operator_checks', HERE / 'operator_checks.py')
    m = load_module('recovery_migration', HERE / 'migrate.py')
    m.HERE = PACKAGE
    c.CLIENT = PACKAGE / 'paired_gpio_client.py'
    return m


def preflight(m, *, pair_running=False):
    c = m.c
    prepared = read_json(EVIDENCE / 'PREPARED.json')
    require(prepared['bundle'] == m.verify_bundle(), 'PREPARED_PACKAGE_CHANGED')
    require(prepared['host'] == m.host_identity(), 'PREPARED_HOST_CHANGED')
    require(prepared['venv'] == m.validate_venv(), 'PREPARED_VENV_CHANGED')
    require(prepared['daemon_before'] == m.OLD and prepared['unit_before'] == m.UNIT_SHA
            and prepared['readiness_before'] == c.digest(m.READINESS)
            and prepared['source_head'] == m.BASE, 'PREPARED_BASELINE_CHANGED')
    failure = read_json(EVIDENCE / 'FAILURE.json')
    require(failure == {'phase': 'install', 'code': 'STOP_INSPECT_PRIVATE_EVIDENCE'}, 'FAILURE_PHASE')
    secure(EVIDENCE / 'failure-private.log')
    trace = (EVIDENCE / 'failure-private.log').read_text()
    require(re.findall(r'^RuntimeError: (.*)$', trace, re.MULTILINE) == ['EFFECTIVE_DEVICE_ALLOW'], 'FAILURE_CAUSE')
    secure(EVIDENCE / 'INSTALL_STARTED')
    require(not (EVIDENCE / 'SUCCESS.json').exists(), 'ALREADY_COMPLETED')
    backup = read_json(EVIDENCE / 'BACKUP_COMPLETE.json')
    paths = (m.DEST, *m.PRESERVED)
    require(set(backup['files']) == {str(p) for p in paths}, 'BACKUP_FILE_SET')
    for index, path in enumerate(paths):
        saved = backup['files'][str(path)]
        require(saved['file'] == f'before-{index:02d}', 'BACKUP_NAME')
        secure(EVIDENCE / saved['file'])
        require(c.digest(EVIDENCE / saved['file']) == saved['sha256'], 'BACKUP_HASH')
    require(backup['files'][str(m.DEST)]['sha256'] == m.OLD, 'BACKUP_DAEMON')
    secure(EVIDENCE / 'database.sqlite3')
    require(c.digest(EVIDENCE / 'database.sqlite3') == backup['database'], 'BACKUP_DATABASE')
    sentinel = c.DB.with_name(c.DB.name + '.weather-identity')
    secure(EVIDENCE / 'database.weather-identity')
    require((EVIDENCE / 'database.weather-identity').read_bytes() == sentinel.read_bytes(), 'DATABASE_IDENTITY_CHANGED')
    for path, source in ((m.DEST, 'paired_gpio_daemon.py'), (m.DROPIN, 'paired-gpio.conf'),
                         (m.PAIR_ENV, 'paired-gpio.env')):
        secure(path)
        require(path.read_bytes() == (PACKAGE / source).read_bytes(), 'INSTALLED_ARTIFACT_CHANGED')
    secure(m.MARKER)
    require(m.MARKER.read_bytes() == b'paired migration only; lighting remains disabled\n', 'MARKER_CHANGED')
    for service in ((c.HUB,) if pair_running else (c.HUB, m.PAIR)):
        require(not c.active(service) and m.show(service, 'MainPID') == '0', 'SERVICES_NOT_STOPPED')
    if pair_running:
        require(c.active(m.PAIR), 'PAIR_NOT_ACTIVE')
    require(c.active('node-red.service') and c.active('nginx.service')
            and not c.active('nodered.service'), 'DEPENDENCIES_NOT_READY')
    m.unit_check(m.PAIR, m.PAIR_UNIT, 'pair.service', [m.DROPIN])
    m.unit_check(c.HUB, c.UNIT, 'hub.service', [m.READINESS])
    m.verify_effective_pair()
    require(backup['source_head'] == m.BASE, 'BACKUP_SOURCE_CHANGED')
    state = {'entries': c.config(), 'settings': backup['settings'],
             'packages': backup['packages'], 'history': backup['history'],
             'preserved': {str(p): backup['files'][str(p)]['sha256'] for p in m.PRESERVED}}
    m.preserved(state)
    c.flow()
    c.pair_high()
    if pair_running:
        m.verify_running()
    else:
        m.metadata_check(owned=False)
    return state


def continue_startup(m, state):
    c = m.c
    c.run(['systemctl', 'start', m.PAIR], timeout=45)
    m.wait_pair()
    c.drain()
    m.verify_running()
    m.preserved(state)
    c.run(['systemctl', 'start', c.HUB], timeout=85)
    m.wait_hub_status(state['entries'])
    m.live_environment(state['entries'])
    require(all(c.active(name) for name in c.SERVICES), 'FINAL_SERVICES')
    c.pair_high()
    c.flow()
    m.verify_running()
    m.preserved(state)


def execute(m):
    c = m.c
    secure(EVIDENCE)
    require(not RECOVERY.exists() and not RECOVERY.is_symlink(), 'RECOVERY_ALREADY_ATTEMPTED')
    RECOVERY.mkdir(mode=0o700)
    m.sync_directory(EVIDENCE)
    c.LOG = RECOVERY / 'private.log'
    armed = False
    try:
        state = preflight(m)
        c.durable(RECOVERY / 'STARTED', 'Reviewed continuation after DeviceAllow order-only failure.\n')
        armed = True
        continue_startup(m, state)
        receipt = {'daemon_sha256': c.digest(m.DEST), 'operation': 'USER_OFF',
                   'command': 'DRAIN', 'gpio26': 'high', 'gpio20': 'high',
                   'lighting': 'disabled', 'physical_position': 'NOT_VERIFIED',
                   'evidence': str(RECOVERY), 'original_failure_preserved': True}
        c.durable(RECOVERY / 'SUCCESS.json', json.dumps(receipt, sort_keys=True) + '\n')
        print('PAIRED_RECOVERY_VERIFIED; ' + json.dumps(receipt), flush=True)
        return 0
    except BaseException:
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
        print('RECOVERY_STOPPED; evidence=' + str(RECOVERY), flush=True)
        return 1


def main():
    require(os.geteuid() == 0 and sys.argv[1:] == ['--loads-disconnected'], 'ROOT_AND_ISOLATION_REQUIRED')
    os.umask(0o077)
    m = load_verified()
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
        return execute(m)
    finally:
        for fd in descriptors:
            os.close(fd)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print('RECOVERY_BOOTSTRAP_STOPPED type=' + type(exc).__name__)
        sys.exit(1)
