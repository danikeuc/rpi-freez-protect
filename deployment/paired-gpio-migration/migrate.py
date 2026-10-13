"""Two-stage trusted-console migration. Never invoke through the SSH helper."""
# ruff: noqa: BLE001, S110
# Interrupts enter best-effort safety cleanup; failed diagnostics cannot prevent it.
import fcntl
import json
import os
import platform
import re
import signal
import socket
import sqlite3
import stat
import sys
import tempfile
import time
import traceback
from contextlib import closing
from pathlib import Path

import operator_checks as c

HERE = Path(__file__).resolve().parent
PAIR = c.PAIR
DEST = c.REPO / 'deployment/node-red/paired_gpio_daemon.py'
PAIR_UNIT = Path('/etc/systemd/system') / PAIR
READINESS = Path('/etc/systemd/system/freeze-protect.service.d/30-node-red-readiness.conf')
DROPIN = Path('/etc/systemd/system/freeze-protect-pair-gpio.service.d/40-paired-gpio.conf')
PAIR_ENV = Path('/etc/freeze-protect/paired-gpio.env')
MARKER = Path('/etc/freeze-protect/paired-gpio-migration-approved')
PAIR_ROOT = Path('/opt/freeze-protect-paired-gpio')
PAIR_VENV = PAIR_ROOT / 'venv-2.3.0'
OLD = '33088ea9e6ccf8d327e226bab1602c6a2b3ba2423de7dcab408b1d06f2233d2f'
UNIT_SHA = '0ce0b112ae54783846784ccb1fb77f17748c830392deb612391047d22da840ff'
BASE = 'd0dfeac61856e0ff716e700348be61709dc68505'
WHEEL = 'gpiod-2.3.0-cp313-cp313-manylinux_2_17_aarch64.manylinux2014_aarch64.whl'
WHEEL_SHA = '7fdc3f63a277f8ae193f0c9b565bbd48e525e94c39cd463acd7b06250bf26507'
BUNDLE_FILES = frozenset({'migrate.py', 'operator_checks.py', 'paired_gpio_daemon.py',
                        'paired_gpio_client.py', 'paired-gpio.conf', 'paired-gpio.env',
                        'pair.service', 'hub.service', 'hub-readiness.conf',
                        'preflight-no-legacy-gpio.js', WHEEL})
PRESERVED = (c.ENV, c.UNIT, PAIR_UNIT, READINESS,
             Path('/mnt/dietpi_userdata/node-red/flows.json'),
             Path('/etc/nginx/sites-available/freeze-protect-display.conf'))
require = c.require


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def verify_bundle():
    c.secure(HERE, private=True)
    c.secure(HERE / 'manifest.json')
    value = json.loads((HERE / 'manifest.json').read_text())
    require(isinstance(value, dict) and set(value) == {'files'}
            and isinstance(value['files'], dict)
            and set(value['files']) == BUNDLE_FILES, 'BUNDLE_FILE_SET')
    for name in sorted(BUNDLE_FILES):
        expected = value['files'][name]
        require(isinstance(expected, str) and re.fullmatch('[0-9a-f]{64}', expected), 'BUNDLE_HASH_FORMAT')
        c.secure(HERE / name)
        require((HERE / name).is_file() and c.digest(HERE / name) == expected, 'BUNDLE_HASH')
    require(c.digest(HERE / WHEEL) == WHEEL_SHA, 'WHEEL_PIN')
    require(c.digest(HERE / 'pair.service') == UNIT_SHA, 'BASE_UNIT_PIN')
    compile((HERE / 'paired_gpio_daemon.py').read_bytes(), 'candidate', 'exec')
    return value


def host_identity():
    model = Path('/proc/device-tree/model').read_bytes().rstrip(b'\0').decode('ascii')
    require(model == 'Raspberry Pi 4 Model B Rev 1.1', 'HOST_MODEL')
    require(platform.machine() == 'aarch64' and platform.release() == '6.18.39+rpt-rpi-v8', 'HOST_KERNEL')
    require(sys.version_info[:3] == (3, 13, 5) and os.sysconf('SC_PAGE_SIZE') == 4096, 'HOST_RUNTIME')
    chip = Path('/dev/gpiochip0')
    require(not chip.is_symlink() and stat.S_ISCHR(chip.stat().st_mode), 'CANONICAL_CHIP_REQUIRED')
    require(Path('/sys/class/gpio/gpiochip0').exists() or Path('/sys/bus/gpio/devices/gpiochip0').exists(), 'CHIP_IDENTITY')
    return {'model': model, 'kernel': platform.release(), 'machine': platform.machine(),
            'python': platform.python_version(), 'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'chip_rdev': chip.stat().st_rdev}


def show(service, field):
    return c.run(['systemctl', 'show', service, '--property=' + field, '--value'])


def unit_check(service, path, bundled, dropins):
    c.secure(path)
    require(path.read_bytes() == (HERE / bundled).read_bytes(), 'UNIT_CHANGED')
    require(show(service, 'FragmentPath') == str(path)
            and show(service, 'DropInPaths').split() == [str(p) for p in dropins]
            and show(service, 'NeedDaemonReload') == 'no', 'UNKNOWN_EFFECTIVE_UNIT')
    directory = path.with_name(path.name + '.d')
    if directory.exists():
        c.secure(directory)
        require(set(directory.iterdir()) == set(dropins), 'UNKNOWN_UNIT_FILES')
    for item in dropins:
        c.secure(item)


def lighting_disabled():
    for service in ('light-gpio.service', 'light-controller.service', 'freeze-protect-light-gpio.service', 'freeze-protect-light-gateway.service'):
        require(not c.active(service) and show(service, 'MainPID') in ('', '0'), 'LIGHTING_ACTIVE')
        enabled = c.run(['systemctl', 'is-enabled', service], ok=(0, 1, 3, 4))
        require(enabled in ('disabled', 'masked', 'not-found'), 'LIGHTING_ENABLED_OR_UNKNOWN')
    require(not Path('/etc/independent-light/commissioned').exists()
            and not Path('/etc/freeze-protect/lighting-commissioned').exists()
            and not Path('/etc/freeze-protect/lighting-hardware-approved').exists(), 'LIGHTING_MARKER')
    for path in (Path('/etc/independent-light/executor.env'), Path('/etc/independent-light/controller.env'),
                 Path('/etc/freeze-protect/light-gpio.env'), Path('/etc/freeze-protect/lighting.env')):
        require(not path.exists() and not path.is_symlink(), 'LIGHTING_CONFIG_REQUIRES_REVIEW')


def live_environment(entries):
    pid = int(show(c.HUB, 'MainPID'))
    require(pid > 0, 'HUB_PID')
    values = dict(part.split(b'=', 1) for part in Path(f'/proc/{pid}/environ').read_bytes().split(b'\0') if b'=' in part)
    keys = {key for key in entries if key.startswith('FREEZE_PROTECT_')} | {
        key.decode() for key in values if key.startswith(b'FREEZE_PROTECT_')}
    require(all(values.get(key.encode()) == (entries[key].encode() if key in entries else None)
                for key in keys), 'LIVE_ENVIRONMENT_CHANGED')


def preflight(*, prepared):
    require(os.geteuid() == 0, 'ROOT_CONSOLE_REQUIRED')
    host_identity()
    for path in (DEST, c.REPO, c.VENV, c.ENV):
        c.secure(path)
    require(c.digest(DEST) == OLD, 'BASELINE_DAEMON_CHANGED')
    require(c.git('rev-parse', 'HEAD') == BASE, 'SOURCE_HEAD_CHANGED')
    require(c.digest(PAIR_UNIT) == UNIT_SHA, 'BASELINE_UNIT_CHANGED')
    unit_check(PAIR, PAIR_UNIT, 'pair.service', [])
    unit_check(c.HUB, c.UNIT, 'hub.service', [READINESS])
    require(READINESS.read_bytes() == (HERE / 'hub-readiness.conf').read_bytes(), 'READINESS_CHANGED')
    require(show(PAIR, 'User') == 'nodered' and show(PAIR, 'Group') == 'nodered', 'PAIR_IDENTITY')
    require(show(PAIR, 'Environment') == '' and show(PAIR, 'EnvironmentFiles') == '', 'PAIR_ENVIRONMENT_OVERRIDE')
    require(all(c.active(service) for service in c.SERVICES) and not c.active('nodered.service'), 'SERVICE_PREFLIGHT')
    lighting_disabled()
    for path in (DROPIN, PAIR_ENV, MARKER):
        require(not path.exists() and not path.is_symlink(), 'MIGRATION_ALREADY_PRESENT')
        parent = path.parent if path.parent.exists() else path.parent.parent
        c.secure(parent)
    entries = c.config()
    live_environment(entries)
    c.status(entries)
    settings = c.persistent_stop()
    c.pair_high()
    script = c.REPO / 'deployment/node-red/preflight-no-legacy-gpio.js'
    c.secure(script)
    require(script.read_bytes() == (HERE / script.name).read_bytes(), 'FLOW_VALIDATOR_CHANGED')
    c.flow()
    packages = c.venv_info()
    require(packages.get('rpi-freeze-protect') == '1.3.1', 'HUB_VERSION')
    if prepared:
        validate_venv()
    return {'entries': entries, 'settings': settings, 'packages': packages,
            'preserved': {str(path): c.digest(path) for path in PRESERVED},
            'history': c.database_snapshot()}


def validate_venv():
    c.secure(PAIR_VENV)
    files = {}
    for path in sorted(PAIR_VENV.rglob('*')):
        c.secure(path)
        if path.is_file():
            files[str(path.relative_to(PAIR_VENV))] = c.digest(path)
    require(bool(files), 'EMPTY_VENV')
    require((PAIR_VENV / 'bin/python3').is_file(), 'VENV_INTERPRETER')
    return files


def build_venv():
    c.secure(PAIR_ROOT.parent)
    require(not PAIR_VENV.exists() and not PAIR_VENV.is_symlink(), 'VENV_ALREADY_EXISTS')
    if not PAIR_ROOT.exists():
        PAIR_ROOT.mkdir(mode=0o755)
        PAIR_ROOT.chmod(0o755)
        sync_directory(PAIR_ROOT.parent)
    c.secure(PAIR_ROOT)
    c.run(['/usr/bin/python3', '-I', '-m', 'venv', '--copies', str(PAIR_VENV)], timeout=120, child_umask=0o022)
    # CPython creates this redundant alias even with --copies; no service path uses it.
    alias = PAIR_VENV / 'lib64'
    if alias.is_symlink():
        require(os.readlink(alias) == 'lib', 'UNKNOWN_VENV_ALIAS')
        alias.unlink()
    c.run([str(PAIR_VENV / 'bin/python3'), '-I', '-m', 'pip', '--isolated', 'install',
           '--no-index', '--no-deps', '--no-compile', str(HERE / WHEEL)], timeout=120, child_umask=0o022)
    c.run([str(PAIR_VENV / 'bin/python3'), '-I', '-m', 'pip', '--isolated', 'check'])
    validate_venv()
    sync_directory(PAIR_VENV)


METADATA_CODE = r"""
import sys, types, importlib.metadata, os, stat
import gpiod
from gpiod.line import Direction, Bias, Edge, Value
assert importlib.metadata.version('gpiod') == '2.3.0'
assert callable(gpiod.Chip.request_lines)
assert callable(gpiod.LineRequest.reconfigure_lines)
settings = gpiod.LineSettings(direction=Direction.AS_IS, bias=Bias.AS_IS, edge_detection=Edge.NONE)
assert settings.direction == Direction.AS_IS
module = types.ModuleType('reviewed_pair_candidate')
sys.modules[module.__name__] = module
exec(compile(sys.stdin.buffer.read(), '<reviewed-candidate>', 'exec'), module.__dict__)
with gpiod.Chip('/dev/gpiochip0') as chip:
    info = chip.get_info()
    assert info.name == 'gpiochip0' and info.label == 'pinctrl-bcm2711' and info.num_lines == 58
    assert module.validate_platform(chip.fd, info.label) == os.stat('/dev/gpiomem').st_rdev
    for pin in (20, 26):
        line = chip.get_line_info(pin)
        assert line.offset == pin and line.name == 'GPIO' + str(pin)
        if sys.argv[1] == 'owned':
            assert line.used and line.consumer == 'freeze-protect-pair'
            assert line.direction == Direction.OUTPUT and line.active_low is False
        else:
            assert not line.used
    light = chip.get_line_info(21)
    assert light.name == 'GPIO21' and not light.used
assert os.access('/dev/gpiomem', os.R_OK | os.W_OK)
print('METADATA_VERIFIED')
"""


def metadata_check(*, owned):
    require(c.run(['runuser', '-u', 'nodered', '--', str(PAIR_VENV / 'bin/python3'),
                   '-I', '-B', '-c', METADATA_CODE, 'owned' if owned else 'unused'],
                  input_data=(HERE / 'paired_gpio_daemon.py').read_bytes(), timeout=15)
            == 'METADATA_VERIFIED', 'METADATA_RESULT')


def prepared_identity(package):
    return {'bundle': package, 'host': host_identity(), 'venv': validate_venv(),
            'daemon_before': c.digest(DEST), 'unit_before': c.digest(PAIR_UNIT),
            'readiness_before': c.digest(READINESS), 'source_head': c.git('rev-parse', 'HEAD')}


def prepare(evidence):
    package = verify_bundle()
    preflight(prepared=False)
    build_venv()
    metadata_check(owned=False)
    c.durable(evidence / 'PREPARED.json', json.dumps(prepared_identity(package), sort_keys=True) + '\n')


def verify_prepared(directory, package):
    c.secure(directory, private=True)
    c.secure(directory / 'PREPARED.json', private=True)
    require(json.loads((directory / 'PREPARED.json').read_text()) == prepared_identity(package),
            'PREPARED_IDENTITY_CHANGED')
    require(not (directory / 'INSTALL_STARTED').exists(), 'PREPARED_ALREADY_USED')


def backup(evidence, state):
    inventory = {}
    for index, source in enumerate((DEST, *PRESERVED)):
        target = evidence / f'before-{index:02d}'
        with target.open('xb') as stream:
            stream.write(source.read_bytes())
            stream.flush()
            os.fsync(stream.fileno())
        require(c.digest(target) == c.digest(source), 'BACKUP_READBACK')
        info = source.stat()
        inventory[str(source)] = {'file': target.name, 'sha256': c.digest(target),
                                 'mode': stat.S_IMODE(info.st_mode), 'uid': info.st_uid, 'gid': info.st_gid}
    sentinel = c.DB.with_name(c.DB.name + '.weather-identity')
    c.durable(evidence / 'database.weather-identity', sentinel.read_text('ascii'))
    with (closing(sqlite3.connect(c.DB.as_uri() + '?mode=ro', uri=True)) as source,
          closing(sqlite3.connect(evidence / 'database.sqlite3')) as target):
        source.backup(target)
        require(target.execute('PRAGMA quick_check').fetchone() == ('ok',), 'BACKUP_DATABASE')
    with (evidence / 'database.sqlite3').open('rb') as stream:
        os.fsync(stream.fileno())
    c.durable(evidence / 'BACKUP_COMPLETE.json', json.dumps({'files': inventory,
        'database': c.digest(evidence / 'database.sqlite3'), 'packages': state['packages'],
        'history': state['history'], 'settings': state['settings'], 'source_head': BASE}, sort_keys=True) + '\n')


def atomic_write(destination, data, mode):
    c.secure(destination.parent)
    require(not destination.is_symlink(), 'DESTINATION_SYMLINK')
    fd, name = tempfile.mkstemp(prefix='.paired-migration-', dir=destination.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
        os.replace(name, destination)
        sync_directory(destination.parent)
        require(destination.read_bytes() == data, 'REPLACEMENT_READBACK')
    finally:
        if os.path.exists(name):
            os.unlink(name)


def install_files():
    require(c.digest(DEST) == OLD, 'BASELINE_CHANGED_BEFORE_REPLACE')
    for path in (DROPIN.parent, PAIR_ENV.parent):
        if not path.exists():
            path.mkdir(mode=0o755)
            path.chmod(0o755)
            sync_directory(path.parent)
        c.secure(path)
    atomic_write(DEST, (HERE / 'paired_gpio_daemon.py').read_bytes(), stat.S_IMODE(DEST.stat().st_mode))
    atomic_write(PAIR_ENV, (HERE / 'paired-gpio.env').read_bytes(), 0o600)
    atomic_write(DROPIN, (HERE / 'paired-gpio.conf').read_bytes(), 0o644)
    atomic_write(MARKER, b'paired migration only; lighting remains disabled\n', 0o600)
    c.run(['systemd-analyze', 'verify', str(PAIR_UNIT), str(c.UNIT)])
    c.run(['systemctl', 'daemon-reload'])
    unit_check(PAIR, PAIR_UNIT, 'pair.service', [DROPIN])
    unit_check(c.HUB, c.UNIT, 'hub.service', [READINESS])
    require(show(PAIR, 'User') == 'nodered' and show(PAIR, 'Group') == 'nodered'
            and show(PAIR, 'Restart') == 'no' and show(PAIR, 'DevicePolicy') == 'closed', 'EFFECTIVE_PAIR_CONFIG')
    require(show(PAIR, 'DeviceAllow').splitlines() == ['/dev/gpiomem rw', '/dev/gpiochip0 rw'], 'EFFECTIVE_DEVICE_ALLOW')
    start = show(PAIR, 'ExecStart')
    require('path=' + str(PAIR_VENV / 'bin/python3') + ' ;' in start
            and 'argv[]=' + str(PAIR_VENV / 'bin/python3') + ' -I -B ' + str(DEST) + ' ;' in start, 'EFFECTIVE_EXECSTART')


def wait_pair():
    deadline = time.monotonic() + 15
    while True:
        require(c.active(PAIR), 'PAIR_NOT_ACTIVE')
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
                probe.settimeout(1)
                probe.connect('/run/freeze-protect/paired-gpio.sock')
            return
        except (FileNotFoundError, ConnectionRefusedError):
            require(time.monotonic() < deadline, 'PAIR_SOCKET_TIMEOUT')
            time.sleep(0.1)


def verify_running():
    pid = int(show(PAIR, 'MainPID'))
    require(pid > 0, 'PAIR_PID')
    args = Path(f'/proc/{pid}/cmdline').read_bytes().rstrip(b'\0').split(b'\0')
    require(args == [str(PAIR_VENV / 'bin/python3').encode(), b'-I', b'-B', str(DEST).encode()], 'RUNNING_COMMAND')
    require(c.digest(Path(f'/proc/{pid}/exe')) == c.digest(PAIR_VENV / 'bin/python3'), 'RUNNING_INTERPRETER')
    metadata_check(owned=True)


def preserved(state):
    require(all(c.digest(Path(path)) == digest for path, digest in state['preserved'].items()), 'PRESERVED_FILE_CHANGED')
    require(c.persistent_stop() == state['settings'], 'DURABLE_SETTINGS_CHANGED')
    require(c.venv_info() == state['packages'], 'HUB_DEPENDENCIES_CHANGED')
    require(c.git('rev-parse', 'HEAD') == BASE, 'SOURCE_HEAD_CHANGED')
    c.history_preserved(state['history'])
    lighting_disabled()


def cutover(state, evidence):
    backup(evidence, state)
    c.status(state['entries'])
    preserved(state)
    c.durable(evidence / 'INSTALL_STARTED', 'one attempt; no automatic rollback\n')
    c.run(['systemctl', 'stop', c.HUB], timeout=45)
    c.stopped()
    c.drain()
    require(c.persistent_stop() == state['settings'], 'DURABLE_STOP_CHANGED')
    c.run(['systemctl', 'stop', PAIR], timeout=45)
    require(not c.active(PAIR) and show(PAIR, 'MainPID') == '0', 'PAIR_NOT_STOPPED')
    c.pair_high()
    time.sleep(2)  # Expire pre-stop requests; Hub authority is stopped and USER_OFF is durable.
    metadata_check(owned=False)
    install_files()
    c.run(['systemctl', 'start', PAIR], timeout=45)
    wait_pair()
    c.drain()
    verify_running()
    preserved(state)
    c.run(['systemctl', 'start', c.HUB], timeout=85)
    # Existing readiness ExecStartPre completes before systemctl start returns.
    c.status(state['entries'])
    live_environment(state['entries'])
    require(all(c.active(service) for service in c.SERVICES), 'FINAL_SERVICES')
    c.pair_high()
    c.flow()
    verify_running()
    preserved(state)
    require(c.digest(DEST) == c.digest(HERE / 'paired_gpio_daemon.py'), 'FINAL_DAEMON_HASH')
    c.durable(evidence / 'SUCCESS.json', json.dumps({'daemon_sha256': c.digest(DEST),
        'interpreter': str(PAIR_VENV / 'bin/python3'), 'chip': '/dev/gpiochip0',
        'operation': 'USER_OFF', 'command': 'DRAIN', 'gpio26': 'high', 'gpio20': 'high',
        'lighting': 'disabled', 'physical_position': 'NOT_VERIFIED'}) + '\n')


def install(evidence):
    package = verify_bundle()
    verify_prepared(evidence, package)
    state = preflight(prepared=True)
    metadata_check(owned=False)
    cutover(state, evidence)


def execute(stage, evidence):
    c.LOG = evidence / 'private.log'
    try:
        (prepare if stage == 'prepare' else install)(evidence)
        print(f'PAIRED_MIGRATION_{stage.upper()}_VERIFIED evidence={evidence}', flush=True)
        return 0
    except BaseException:
        if (evidence / 'INSTALL_STARTED').exists():
            try:
                c.run(['systemctl', 'stop', c.HUB], timeout=45)
                c.stopped()
            except BaseException:
                pass
            try:
                if c.active(PAIR) and not c.DRAIN_OR_READBACK_FAILED:
                    c.drain()
            except BaseException:
                pass
        try:
            with (evidence / 'failure-private.log').open('a') as stream:
                traceback.print_exc(file=stream)
            if not (evidence / 'FAILURE.json').exists():
                c.durable(evidence / 'FAILURE.json', json.dumps({'phase': stage, 'code': 'STOP_INSPECT_PRIVATE_EVIDENCE'}) + '\n')
        except BaseException:
            pass
        print(f'PAIRED_MIGRATION_STOPPED phase={stage} code=STOP_INSPECT_PRIVATE_EVIDENCE evidence={evidence}', flush=True)
        print('Keep both loads disconnected. No automatic retry or rollback.', flush=True)
        return 1


def main():
    require(os.geteuid() == 0, 'ROOT_CONSOLE_REQUIRED')
    require(len(sys.argv) in (4, 5) and sys.argv[1] in ('prepare', 'install')
            and sys.argv[2:4] == ['--24v-disconnected', '--mains-lamp-disconnected'], 'EXPLICIT_LOAD_FLAGS_REQUIRED')
    stage = sys.argv[1]
    require((stage == 'prepare' and len(sys.argv) == 4) or (stage == 'install' and len(sys.argv) == 5), 'STAGE_ARGUMENTS')
    os.umask(0o077)
    lock_path = Path('/root/.paired-gpio-migration.lock')
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    c.secure(lock_path, private=True)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    def interrupted(*_):
        raise RuntimeError('INTERRUPTED')
    signal.signal(signal.SIGINT, interrupted)
    signal.signal(signal.SIGTERM, interrupted)
    if stage == 'prepare':
        evidence = Path(tempfile.mkdtemp(prefix='paired-gpio-migration.', dir='/root'))
        sync_directory(evidence.parent)
    else:
        evidence = Path(sys.argv[4])
        require(evidence.parent == Path('/root') and evidence.name.startswith('paired-gpio-migration.'), 'EVIDENCE_PATH')
        c.secure(evidence, private=True)
        require(not (evidence / 'FAILURE.json').exists(), 'FAILED_ATTEMPT_REQUIRES_REVIEW')
    try:
        return execute(stage, evidence)
    finally:
        os.close(fd)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        print('PAIRED_MIGRATION_STOPPED code=INVALID_INVOCATION_OR_TRUST_BOUNDARY', flush=True)
        raise SystemExit(1) from None
