"""Fixed diagnostics and one pinned two-stage GPIO migration; no shell interface."""
import fcntl
import hashlib
import io
import json
import math
import os
import re
import stat
import subprocess
import sys
import tarfile
import time
from pathlib import Path

BASE = Path('/usr/local/lib/freeze-protect-maintenance-v1')
STATE = Path('/var/lib/freeze-protect-maintenance')
PACKAGE_SHA = 'f4c87e6439650f80c02b2d1b17c76661c5e3d74bbf7c672eab28edadc9883513'
ENV = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C', 'HOME': '/root',
       'PYTHONDONTWRITEBYTECODE': '1'}
UNITS = ('freeze-protect.service', 'freeze-protect-pair-gpio.service', 'node-red.service')
ARTIFACTS = (
    '/usr/local/lib/freeze-protect-maintenance-v1/maintenance.py',
    '/etc/systemd/system/freeze-protect.service',
    '/etc/systemd/system/freeze-protect.service.d/30-node-red-readiness.conf',
    '/etc/systemd/system/freeze-protect-pair-gpio.service',
    '/etc/systemd/system/freeze-protect-pair-gpio.service.d/40-paired-gpio.conf',
    '/opt/rpi-freez-protect/deployment/node-red/paired_gpio_daemon.py',
)


def require(value, label):
    if not value:
        raise RuntimeError(label)


def secure(path):
    path = Path(path)
    for part in (path, *path.parents):
        info = part.lstat()
        require(not stat.S_ISLNK(info.st_mode) and info.st_uid == 0
                and not info.st_mode & 0o022, 'UNTRUSTED_PATH')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def record(path, value):
    secure(path.parent)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, sort_keys=True)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    sync(path.parent)


def read_json(path, limit=32768):
    secure(path)
    require(path.is_file() and path.stat().st_size < limit, 'INVALID_RECORD')
    return json.loads(path.read_text())


def run(args, timeout=10):
    return subprocess.run(args, env=ENV, cwd='/', stdin=subprocess.DEVNULL,
                          capture_output=True, timeout=timeout, check=False)


def bundle_members(raw):
    require(digest(raw) == PACKAGE_SHA, 'PACKAGE_HASH')
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
        result = {}
        for member in archive.getmembers():
            require(member.isfile() and re.fullmatch(r'[A-Za-z0-9_.-]+', member.name)
                    and member.name not in ('.', '..') and member.name not in result
                    and 0 <= member.size <= 1024 * 1024, 'PACKAGE_MEMBER')
            result[member.name] = archive.extractfile(member).read()
    require(len(result) == 14, 'PACKAGE_MEMBER_SET')
    return result


def verified_package():
    secure(BASE)
    secure(BASE / 'migration.tar.gz')
    members = bundle_members((BASE / 'migration.tar.gz').read_bytes())
    target = BASE / 'package'
    secure(target)
    require({p.name for p in target.iterdir()} == set(members), 'PACKAGE_FILE_SET')
    for name, data in members.items():
        secure(target / name)
        require((target / name).is_file() and (target / name).read_bytes() == data,
                'PACKAGE_CHANGED')
    return target


def boot():
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def approval():
    value = read_json(STATE / 'approval.json')
    require(value == {**value, 'package_sha256': PACKAGE_SHA, 'boot_id': boot(),
                      'loads_disconnected': True}, 'APPROVAL_CHANGED')
    require(type(value.get('expires_monotonic')) in (float, int)
            and time.monotonic() < value['expires_monotonic'], 'APPROVAL_EXPIRED')


def request(phase):
    require(phase in ('prepare', 'install'), 'COMMAND_REJECTED')
    approval()
    verified_package()
    if phase == 'install':
        previous = read_json(STATE / 'prepare-result.json')
        require(previous.get('verified') is True, 'PREPARE_NOT_VERIFIED')
        evidence_path(previous['evidence'])
    claim = STATE / (phase + '-request.json')
    record(claim, {'phase': phase, 'boot_id': boot(), 'package_sha256': PACKAGE_SHA})
    # Durable claim precedes dispatch. Never retry an ambiguous or failed start.
    command = ['/usr/bin/systemd-run', '--quiet', '--no-block',
               '--unit=freeze-protect-maintenance-' + phase,
               '--property=Type=oneshot', '--property=RemainAfterExit=yes',
               '--property=Restart=no', '--property=TimeoutStartSec=infinity',
               '--property=UMask=0077', '--property=StandardOutput=null',
               '--property=StandardError=null',
               '/usr/bin/python3', '-I', '-B', str(BASE / 'maintenance.py'), '_' + phase]
    result = run(command)
    require(result.returncode == 0, 'JOB_DISPATCH_UNCONFIRMED')
    return {'phase': phase, 'submitted': True, 'verified': False}


def evidence_path(value):
    require(isinstance(value, str) and re.fullmatch(
        r'/root/paired-gpio-migration\.[A-Za-z0-9_]+', value), 'EVIDENCE_PATH')
    path = Path(value)
    secure(path)
    return path


def classify(phase, returncode, output):
    matches = re.findall(r'PAIRED_MIGRATION_' + phase.upper()
                         + r'_VERIFIED evidence=(/root/paired-gpio-migration\.[A-Za-z0-9_]+)\s*$',
                         output, re.MULTILINE)
    if returncode != 0 or len(matches) != 1:
        return {'phase': phase, 'verified': False, 'code': 'MIGRATION_FAILED'}
    evidence = evidence_path(matches[0])
    receipt = evidence / ('PREPARED.json' if phase == 'prepare' else 'SUCCESS.json')
    read_json(receipt, limit=4 * 1024 * 1024)
    require(not (evidence / 'FAILURE.json').exists(), 'MIGRATION_FAILED')
    return {'phase': phase, 'verified': True, 'evidence': str(evidence)}


def worker(phase):
    # Workers are root-only and are not in sudoers or the SSH dispatcher.
    approval()
    require(read_json(STATE / (phase + '-request.json')) == {
        'phase': phase, 'boot_id': boot(), 'package_sha256': PACKAGE_SHA}, 'INVALID_REQUEST')
    record(STATE / (phase + '-worker.json'), {'started': True})
    output_file = STATE / (phase + '-private.log')
    result = {'phase': phase, 'verified': False, 'code': 'WORKER_INTERRUPTED'}
    try:
        target = verified_package()
        args = ['/usr/bin/python3', '-E', '-s', '-B', str(target / 'migrate.py'), phase,
                '--24v-disconnected', '--mains-lamp-disconnected']
        if phase == 'install':
            prepared = read_json(STATE / 'prepare-result.json')
            require(prepared.get('verified') is True, 'PREPARE_NOT_VERIFIED')
            args.append(str(evidence_path(prepared['evidence'])))
        with output_file.open('xb') as log:
            child = subprocess.run(args, env=ENV, cwd=target, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=log, check=False)
            log.flush()
            os.fsync(log.fileno())
        # Only match the fixed receipt; raw process output is never returned.
        with output_file.open('rb') as log:
            log.seek(max(0, output_file.stat().st_size - 65536))
            result = classify(phase, child.returncode, log.read().decode('utf-8', 'replace'))
    finally:
        record(STATE / (phase + '-result.json'), result)


def failure_detail(phase):
    log = STATE / (phase + '-private.log')
    if not log.exists():
        return {}
    secure(log)
    with log.open('rb') as stream:
        stream.seek(max(0, log.stat().st_size - 65536))
        text = stream.read().decode('utf-8', 'replace')
    matches = re.findall(r'evidence=(/root/paired-gpio-migration\.[A-Za-z0-9_]+)', text)
    if not matches:
        return {}
    evidence = evidence_path(matches[-1])
    failure = evidence / 'failure-private.log'
    if not failure.exists():
        return {'evidence': str(evidence)}
    secure(failure)
    with failure.open('rb') as stream:
        stream.seek(max(0, failure.stat().st_size - 65536))
        trace = stream.read().decode('utf-8', 'replace')
    # Export only literal error labels present in the pinned package, never a raw traceback.
    labels = set()
    for data in bundle_members((BASE / 'migration.tar.gz').read_bytes()).values():
        labels.update(re.findall(rb"['\"]([A-Z][A-Z0-9_]{2,80})['\"]", data))
    codes = re.findall(r'^RuntimeError: ([A-Z][A-Z0-9_]{2,80})$', trace, re.MULTILINE)
    safe = [code for code in codes if code.encode() in labels]
    return {'evidence': str(evidence), 'failure_code': safe[-1] if safe else 'PRIVATE_REVIEW_REQUIRED'}


def phase_status(phase):
    result = STATE / (phase + '-result.json')
    if result.exists():
        value = read_json(result)
        public = {key: value[key] for key in ('phase', 'verified', 'code', 'evidence') if key in value}
        if value.get('verified') is not True:
            public.update(failure_detail(phase))
        return public
    if (STATE / (phase + '-request.json')).exists():
        return {'phase': phase, 'verified': False, 'code': 'PENDING_OR_INTERRUPTED'}
    return {'phase': phase, 'verified': False, 'code': 'NOT_REQUESTED'}


def recovery_diagnostic(kind='device-allow-recovery'):
    """Read only the fixed reviewed recovery evidence, never unrestricted logs."""
    require(kind in ('device-allow-recovery', 'hub-readiness-recovery'), 'COMMAND_REJECTED')
    directory = Path('/root/paired-gpio-migration.xj0q8tgi/' + kind)
    if not directory.exists():
        return {'code': 'NOT_PRESENT'}
    secure(directory)
    result = {'evidence': str(directory), 'markers': {}}
    for name in ('STARTED', 'FAILED', 'SUCCESS.json'):
        path = directory / name
        if path.exists():
            secure(path)
            require(path.is_file(), 'INVALID_RECORD')
        result['markers'][name] = path.exists()
    path = directory / 'failure-private.log'
    if path.exists():
        secure(path)
        require(path.is_file(), 'INVALID_RECORD')
        with path.open('rb') as stream:
            stream.seek(max(0, path.stat().st_size - 65536))
            trace = stream.read().decode('utf-8', 'replace')
        # Print no exception message, source line, arbitrary file path or payload.
        types = re.findall(r'^([A-Za-z][A-Za-z0-9_]*Error|AssertionError):?', trace, re.MULTILINE)
        result['error_type'] = types[-1] if types else 'UNCLASSIFIED'
        allowed_files = {'recover_device_allow.py', 'recover_hub_readiness.py', 'migrate.py', 'operator_checks.py'}
        frames = re.findall(r'^  File "([^"\n]+)", line ([0-9]+)', trace, re.MULTILINE)
        result['frames'] = [{'file': Path(name).name, 'line': int(line)}
                            for name, line in frames if Path(name).name in allowed_files][-12:]
        # Codes are matched only against literal labels in the immutable pinned package.
        labels = {b'HUB_HTTP_STARTUP_TIMEOUT', b'HUB_STARTUP_EXITED'}
        for data in bundle_members((BASE / 'migration.tar.gz').read_bytes()).values():
            labels.update(re.findall(rb"['\"]([A-Z][A-Z0-9_]{2,80})['\"]", data))
        codes = re.findall(r'^RuntimeError: ([A-Z][A-Z0-9_]{2,80})$', trace, re.MULTILINE)
        result['failure_code'] = next((code for code in reversed(codes) if code.encode() in labels),
                                      'PRIVATE_REVIEW_REQUIRED')
        if re.search(r'^RuntimeError: command failed; private log retained$', trace, re.MULTILINE):
            result['failure_code'] = 'SUBPROCESS_FAILED'
    log = directory / 'private.log'
    if log.exists():
        secure(log)
        require(log.is_file(), 'INVALID_RECORD')
        with log.open('rb') as stream:
            stream.seek(max(0, log.stat().st_size - 65536))
            text = stream.read().decode('utf-8', 'replace')
        patterns = {'permission_denied': 'Permission denied',
                    'operation_not_permitted': 'Operation not permitted',
                    'read_only_filesystem': 'Read-only file system',
                    'missing_module': 'ModuleNotFoundError',
                    'assertion_failed': 'AssertionError',
                    'connection_refused': 'Connection refused',
                    'missing_path': 'No such file or directory'}
        result['subprocess_categories'] = [key for key, value in patterns.items() if value in text]
        result['probe_lines'] = [int(line) for line in re.findall(
            r'^  File "<(?:string|reviewed-candidate)>", line ([0-9]+)', text, re.MULTILINE)][-12:]
    return result



LIGHT_ROOT = Path('/root')
_ROOT_UID = 0
LIGHT_PHASES = (
    'startup_off', 'on', 'command_off', 'normal_release',
    'on_before_crash', 'crash_release', 'final_owned_off', 'final_released_off',
)
LIGHT_RESULTS = {
    'GPIO21_DISCONNECTED_DRIVER_PASS', 'LIGHT_LEVEL_MISMATCH',
    'LIGHT_FUNCTION_MISMATCH', 'PAIRED_DRAIN_CHANGED', 'WORKER_TIMEOUT',
    'WORKER_FRAME', 'WORKER_ACK', 'WORKER_EXIT_TIMEOUT', 'WORKER_EXIT',
    'INITIAL_OFF_READBACK', 'WORKER_READBACK', 'INSPECT_PRIVATE_EVIDENCE',
    'PREFLIGHT', 'PAIRED_BASELINE_CHANGED', 'SERVICES_REQUIRED',
    'PAIRED_OWNERSHIP', 'GPIO21_BUSY_OR_UNKNOWN',
}


def _valid(value):
    if not value:
        raise ValueError('INVALID_LIGHT_EVIDENCE')


def _trusted_info(info, directory=False):
    _valid(info.st_uid == _ROOT_UID and not info.st_mode & 0o022)
    _valid(stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))


def _light_root_fd():
    """Walk trusted directory descriptors; never resolve symlinks."""
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        _trusted_info(os.fstat(fd), True)
        for part in LIGHT_ROOT.parts[1:]:
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW |
                          os.O_CLOEXEC, dir_fd=fd)
            os.close(fd)
            fd = new
            _trusted_info(os.fstat(fd), True)
        return fd
    except BaseException:
        os.close(fd)
        raise


def _light_read(directory, name, limit):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK |
                 os.O_CLOEXEC, dir_fd=directory)
    try:
        before = os.fstat(fd)
        _trusted_info(before)
        _valid(before.st_size <= limit)
        data = bytearray()
        while len(data) <= limit:
            chunk = os.read(fd, min(65536, limit + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        _valid(len(data) <= limit)
        after = os.fstat(fd)
        signature = lambda info: (info.st_dev, info.st_ino, info.st_size,
                                  info.st_mtime_ns, info.st_ctime_ns)
        _valid(signature(before) == signature(after))
        return bytes(data)
    finally:
        os.close(fd)


def summarize_light_bench(receipt, rows, diagnostic):
    _valid(isinstance(receipt, dict) and isinstance(rows, list) and len(rows) <= 10000)
    _valid(all(type(receipt.get(key)) is bool
               for key in ('attempted_gpio21', 'final_off_readback')))
    _valid(receipt.get('automation_enabled') is False)
    result = receipt.get('result')
    result = result if isinstance(result, str) and result in LIGHT_RESULTS else 'UNCLASSIFIED'
    summary, first = {}, None
    last_time = -1
    for row in rows:
        _valid(isinstance(row, dict))
        phase, pins, stamp = row.get('phase'), row.get('pins'), row.get('monotonic')
        _valid(isinstance(phase, str) and phase in LIGHT_PHASES)
        _valid(type(stamp) in (int, float) and math.isfinite(stamp) and stamp >= 0 and stamp >= last_time)
        last_time = stamp
        _valid(isinstance(pins, dict) and set(pins) == {'20', '21', '26'})
        for pin in pins.values():
            _valid(isinstance(pin, dict) and set(pin) == {'level', 'function'})
            _valid(type(pin['level']) is int and pin['level'] in (0, 1))
            _valid(type(pin['function']) is int and pin['function'] in range(8))
        # Reconstruct, never emit original dictionaries with unvalidated fields.
        safe = {p: {'level': pins[p]['level'], 'function': pins[p]['function']}
                for p in ('20', '21', '26')}
        failure = None
        if any(safe[p] != {'level': 1, 'function': 1} for p in ('20', '26')):
            failure = 'PAIRED_DRAIN_CHANGED'
        elif safe['21']['level'] != (0 if phase in ('on', 'on_before_crash') else 1):
            failure = 'LIGHT_LEVEL_MISMATCH'
        elif safe['21']['function'] not in ((0, 1) if phase.endswith('release') or
                                           phase == 'final_released_off' else (1,)):
            failure = 'LIGHT_FUNCTION_MISMATCH'
        if failure and first is None:
            first = {'phase': phase, 'code': failure, 'pins': safe}
        if phase not in summary:
            summary[phase] = {'phase': phase, 'first': safe, 'samples': 0, 'mismatches': 0}
        summary[phase].update(last=safe)
        summary[phase]['samples'] += 1
        summary[phase]['mismatches'] += int(failure is not None)
    frames, error_type = [], 'UNCLASSIFIED'
    if diagnostic is not None:
        _valid(isinstance(diagnostic, dict) and isinstance(diagnostic.get('frames', []), list))
        if diagnostic.get('error_type') in ('RuntimeError', 'ValueError', 'OSError',
                                            'TimeoutError', 'KeyboardInterrupt'):
            error_type = diagnostic['error_type']
        for frame in diagnostic.get('frames', [])[-12:]:
            if (isinstance(frame, dict) and frame.get('file') in
                    ('commission_gpio21.py', 'operator_checks.py')
                    and type(frame.get('line')) is int and 0 < frame['line'] <= 100000):
                frames.append({'file': frame['file'], 'line': frame['line']})
    # A partial sequence must not be promoted to driver acceptance.
    if result == 'GPIO21_DISCONNECTED_DRIVER_PASS':
        _valid(set(summary) == set(LIGHT_PHASES) and first is None
               and receipt['attempted_gpio21'] and receipt['final_off_readback'])
    return {'code': 'READ', 'result': result,
            'attempted_gpio21': receipt['attempted_gpio21'],
            'final_off_readback': receipt['final_off_readback'],
            'physical_acceptance': 'NOT_VERIFIED', 'automation_enabled': False,
            'observation': 'HISTORICAL_SAMPLES',
            'sample_count': len(rows), 'first_failure': first,
            'phase_summary': list(summary.values()), 'error_type': error_type,
            'frames': frames}


def light_bench_diagnostic():
    root_fd, evidence_fd = None, None
    try:
        root_fd = _light_root_fd()
        try:
            marker = _light_read(root_fd, 'light-gpio21-commissioning.started', 256)
        except FileNotFoundError:
            return {'code': 'NOT_REQUESTED'}
        value = marker.decode('ascii')
        path = Path(value)
        _valid(path.parent == LIGHT_ROOT and
               re.fullmatch(r'light-gpio21-bench\.[A-Za-z0-9_]+', path.name))
        evidence_fd = os.open(path.name, os.O_RDONLY | os.O_DIRECTORY |
                              os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=root_fd)
        _trusted_info(os.fstat(evidence_fd), True)
        try:
            raw = _light_read(evidence_fd, 'receipt.json', 32768)
            samples = _light_read(evidence_fd, 'samples.json', 2 * 1024 * 1024)
        except FileNotFoundError:
            return {'code': 'INCOMPLETE'}
        try:
            detail = _light_read(evidence_fd, 'diagnostic.json', 32768)
        except FileNotFoundError:
            detail = None
        receipt = json.loads(raw)
        _valid(isinstance(receipt, dict) and receipt.get('evidence') == value)
        result = summarize_light_bench(receipt, json.loads(samples),
                                      json.loads(detail) if detail is not None else None)
        # Detect a changed marker/receipt or rewritten samples during collection.
        _valid(marker == _light_read(root_fd, 'light-gpio21-commissioning.started', 256)
               and raw == _light_read(evidence_fd, 'receipt.json', 32768)
               and samples == _light_read(evidence_fd, 'samples.json', 2 * 1024 * 1024))
        result['evidence'] = path.name
        return result
    except FileNotFoundError:
        return {'code': 'INCOMPLETE'}
    except (OSError, ValueError, TypeError, RecursionError, OverflowError):
        return {'code': 'UNAVAILABLE_OR_INVALID'}
    finally:
        for fd in (evidence_fd, root_fd):
            if fd is not None:
                os.close(fd)


def diagnostic():
    result = {'access_version': 1, 'package_sha256': PACKAGE_SHA,
              'jobs': [phase_status(p) for p in ('prepare', 'install')],
              'recovery': recovery_diagnostic(),
              'hub_recovery': recovery_diagnostic('hub-readiness-recovery'),
              'light_gpio21_bench': light_bench_diagnostic(),
              'units': {}, 'artifacts': {}}
    for unit in (*UNITS, 'freeze-protect-maintenance-prepare.service',
                 'freeze-protect-maintenance-install.service'):
        r = run(['/usr/bin/systemctl', 'show', unit, '--no-pager',
                 '--property=ActiveState,SubState,Result,ExecMainStatus,MainPID,NeedDaemonReload'])
        properties = {}
        for line in r.stdout.decode('ascii', 'replace').splitlines():
            key, sep, value = line.partition('=')
            if sep and key in ('ActiveState', 'SubState', 'Result', 'ExecMainStatus',
                              'MainPID', 'NeedDaemonReload') and re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', value):
                properties[key] = value
        result['units'][unit] = properties
    for name in ARTIFACTS:
        path = Path(name)
        try:
            secure(path)
            require(path.is_file() and path.stat().st_size < 1024 * 1024, 'INVALID_ARTIFACT')
            result['artifacts'][name] = {'sha256': digest(path.read_bytes())}
        except (OSError, RuntimeError):
            result['artifacts'][name] = {'code': 'MISSING_OR_UNTRUSTED'}
    return result


def main():
    require(os.geteuid() == 0, 'ROOT_REQUIRED')
    require(len(sys.argv) == 2 and sys.argv[1] in
            ('status', 'prepare', 'install', '_prepare', '_install'), 'COMMAND_REJECTED')
    os.umask(0o077)
    secure(STATE)
    secure(BASE)
    command = sys.argv[1]
    if command == 'status':
        print(json.dumps(diagnostic(), sort_keys=True))
        return
    fd = os.open(STATE / 'operation.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        secure(STATE / 'operation.lock')
        fcntl.flock(fd, fcntl.LOCK_EX | (0 if command.startswith("_") else fcntl.LOCK_NB))
        if command.startswith('_'):
            worker(command[1:])
        else:
            print(json.dumps(request(command), sort_keys=True))
    finally:
        os.close(fd)


if __name__ == '__main__':
    try:
        main()
    except Exception:  # noqa: BLE001 - never export arbitrary exception payloads
        # Error details stay private. No arbitrary exception text crosses SSH.
        print('{"error":"MAINTENANCE_STOPPED","retry":false}')
        sys.exit(1)
