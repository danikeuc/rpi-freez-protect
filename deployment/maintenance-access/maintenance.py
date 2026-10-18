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


def controller_diagnostic():
    """Fixed local GETs and categorized service journal; no actuation interface."""
    import json
    import re
    import urllib.error
    import urllib.request
    from datetime import datetime
    LABELS = frozenset(['AUTO', 'AUTO_SUPPLY', 'Accept', 'BEGIN', 'CALIBRATION_REQUIRED', 'CLEAR_FAULT', 'CLOSE_NOW', 'DRAIN', 'DRAIN_RECEIPT_INVALID', 'FAULT', 'FREEZE_PROTECT_ADMIN_TOKEN', 'FREEZE_PROTECT_CONTROL_MODE', 'FREEZE_PROTECT_DB_PATH', 'FREEZE_PROTECT_DEVELOPMENT_MODE', 'FREEZE_PROTECT_DISPLAY_TOKEN', 'FREEZE_PROTECT_NODE_RED_TOKEN', 'FREEZE_PROTECT_NODE_RED_URL', 'FREEZE_PROTECT_WEATHER_SETTINGS_TOKEN', 'FROST_PROTECTION', 'HEALTHY', 'INVALID', 'LIGHT_ALLOWED_SOURCES', 'LIGHT_CAMERA_TOKEN', 'LIGHT_DB_PATH', 'LIGHT_DISPLAY_TOKEN', 'LIGHT_EXECUTOR_SOCKET', 'LIGHT_GPIO21_ACTIVE_LOW', 'LIGHT_GPIO21_ENABLED', 'LIGHT_GPIO_CHIP', 'LIGHT_SETTINGS_TOKEN', 'MANUAL_ACTIVE', 'MANUAL_DRAIN', 'MANUAL_IDLE', 'MANUAL_OFF', 'MANUAL_ON', 'MAX31865_PT100', 'MAX31865_PT100_SPI0_CE0', 'NODE_RED_DRAIN_READINESS_FAILED', 'NODE_RED_DRAIN_READY', 'NODE_RED_NOT_READY', 'NORMAL', 'OFF', 'OK', 'ON', 'OVER_UNDERVOLTAGE', 'POST', 'REFIN_HIGH', 'REFIN_LOW', 'RTDIN_LOW', 'RTD_HIGH_THRESHOLD', 'RTD_LOW_THRESHOLD', 'SAFE_DRAIN', 'SHUTDOWN', 'STALE', 'STARTING', 'SUPPLY', 'TIMED_SHOWER', 'UNAVAILABLE', 'USER_OFF', 'YES', 'action', 'action_enabled', 'action_nonce', 'action_storage_or_output_fault', 'active_marker', 'actuator_failure', 'after', 'ascii', 'at', 'attempt', 'authentication_failed', 'authentication_required', 'authorization', 'auto', 'automatic', 'automatic_decision', 'automatic_normal', 'available', 'before', 'begin', 'body_too_large', 'bridge_flow_revision', 'camera', 'camera_hold', 'celsius', 'clock_or_lease_fault', 'cold_forecast', 'command', 'commissioned', 'commissioned_sensor_source_id', 'commissioned_settings_version', 'control_revision', 'coverage_invalid', 'daily', 'daily_minima_c', 'daily_units', 'dates', 'deadline', 'deadline_exceeded', 'desired_on', 'detail', 'device', 'disabled', 'display', 'display_drain_requested', 'drain_requested', 'duplicate', 'duration_seconds', 'eligible', 'enabled', 'error', 'event', 'event_storage_or_output_fault', 'event_time_invalid', 'event_type', 'expected_control_revision', 'expected_revision', 'expiry', 'fault', 'fault_cleared', 'fault_inhibited', 'fault_register', 'faults', 'fetch_failed', 'fetched_at', 'flow_revision', 'forbid', 'forecast', 'forecast_days', 'forecast_not_eligible', 'forecast_refresh_failed', 'forecast_refresh_skipped', 'forecast_refreshed', 'forecast_stale_after_s', 'forecast_threshold_c', 'fresh', 'generation', 'gpio', 'gpiod', 'has_more', 'health', 'history_bounds', 'history_storage_fault', 'hold_expired', 'http', 'id', 'identity_capacity', 'identity_reused', 'independent_light_v1', 'intent_unconfirmed', 'invalid_measurement', 'iso8601', 'item', 'items', 'last_error', 'last_reading', 'last_successful_check', 'latest_attempt_failed', 'latitude', 'light_fault', 'light_unavailable', 'light_unconfigured', 'limit', 'location_missing', 'longitude', 'manual', 'manual_cooldown', 'manual_duration_exceeds_settings_limit', 'manual_duration_requires_manual_mode', 'manual_expired', 'manual_idle', 'manual_off', 'manual_on', 'manual_timed', 'manual_transition', 'minima_c', 'minimum', 'mode', 'now', 'observed_at', 'occurred_at', 'off', 'offset', 'ok', 'on', 'operating_mode_not_configured', 'operation', 'other', 'payload', 'payload_json', 'pending', 'persistence_error', 'pipe_below_protection_threshold', 'pipe_not_above_release_threshold', 'pipe_temperature_c', 'protection_threshold_c', 'protocol_version', 'provenance_mismatch', 'reason', 'received_mono', 'reference_resistor_ohm', 'rejected', 'relay_driver_error', 'release_threshold_c', 'remaining_seconds', 'renew', 'request_id', 'restart_clock_or_state_fault', 'restart_manual_inhibited', 'revision', 'revision_exhausted', 'role_forbidden', 'rw', 'rwc', 'safe_drain', 'sensor_commissioned', 'sensor_device_id', 'sensor_diagnostics', 'sensor_health', 'sensor_pending', 'sensor_source_error', 'sensor_source_id', 'sensor_stale_after_s', 'sensor_unhealthy', 'service', 'settings', 'settings_changed', 'settings_mismatch', 'settings_revision', 'settings_storage_fault', 'settings_version', 'shower_transition', 'shutdown', 'shutdown_drain', 'simulation', 'source', 'source_generated_at', 'source_not_allowed', 'spi_error', 'spidev', 'stale_revision', 'stale_settings_revision', 'start', 'starting', 'startup', 'startup_drain', 'startup_drain_failed', 'startup_off', 'startup_storage_or_executor_fault', 'state', 'status', 'stop', 'storage_unavailable', 'store', 'store_true', 'success', 'supply_action', 'temperature_2m_min', 'temperature_unit', 'time', 'time_basis_invalid', 'timed_on', 'timed_shower_active', 'timed_shower_deadline', 'timed_shower_default_s', 'timed_shower_duration_supported', 'timed_shower_expired', 'timed_shower_max_s', 'timed_shower_started', 'timezone', 'true', 'unknown', 'user_off', 'value', 'value_c', 'version', 'w1_slave', 'weather', 'weather_action_expired', 'weather_assistance_version', 'weather_assisted', 'weather_code', 'weather_codes', 'weather_coordinator_unavailable', 'weather_eligible', 'weather_fault_inhibited', 'weather_marker_mismatch', 'weather_missing', 'weather_stale', 'weather_start_required', 'wiring', 'yes'])
    FIELDS = {"event_type", "source", "mode", "operation", "state", "command", "reason", "health"}
    NUMBERS = {"remaining_seconds", "manual_remaining_seconds", "attempt", "status_code", "control_revision", "revision"}
    FLAGS = {"desired_on", "gpio_on", "fault_inhibited", "user_off", "success"}
    rows = []
    def emit(**data):
        rows.append(data)

    def selected(data):
        if not isinstance(data, dict):
            return {}
        clean = {}
        for key, value in data.items():
            if key in FIELDS:
                clean[key] = value if isinstance(value, str) and value in LABELS else "UNCLASSIFIED"
            elif (key in NUMBERS and type(value) is int and 0 <= value <= 2**53 - 1) or (
                key in FLAGS and (value is None or type(value) is bool)
            ):
                clean[key] = value
            elif key in ("at", "occurred_at") and isinstance(value, str) and len(value) <= 40:
                try:
                    clean[key] = datetime.fromisoformat(value).isoformat()
                except ValueError:
                    pass
        return clean

    def env(path):
        p = Path(path)
        for item in (p, *p.parents):
            s = item.lstat()
            if s.st_uid != 0 or stat.S_ISLNK(s.st_mode) or s.st_mode & 0o022:
                raise RuntimeError("untrusted_environment")
        info = p.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > 32768 or info.st_mode & 0o077:
            raise RuntimeError("environment_permissions")
        out = {}
        for line in p.read_text().splitlines():
            if not line or line.lstrip().startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
        return out

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            raise RuntimeError("redirect_rejected")

    def get(url, header, token):
        if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,512}", token):
            raise RuntimeError("token_format")
        client = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        value = "Bearer " + token if header == "Authorization" else token
        request = urllib.request.Request(url, headers={header: value}, method="GET")
        with client.open(request, timeout=2) as response:
            body = response.read(1048577)
            if response.status != 200 or len(body) > 1048576:
                raise RuntimeError("response_invalid")
        return json.loads(body)

    def api_checks():
        specs = [
            ("SHOWER", "/etc/rpi-freeze-protect/environment", "X-Admin-Token",
             "FREEZE_PROTECT_ADMIN_TOKEN", "http://127.0.0.1:8000/api/v1/", "events?limit=1000"),
            ("LIGHT", "/etc/independent-light/controller.env", "Authorization",
             "LIGHT_SETTINGS_TOKEN", "http://127.0.0.1:8002/api/v1/lights/", "history?limit=100"),
        ]
        for label, path, header, key, base, history in specs:
            try:
                token = env(path).get(key)
                emit(check=label + "_STATUS", **selected(get(base + "status", header, token)))
                result = get(base + history, header, token)
                items = result.get("items", [])
                if label == "LIGHT":
                    for offset in range(100, 300, 100):
                        if len(items) < offset or any(row.get("source") == "fault" for row in items):
                            break
                        page = get(base + history + "&offset=" + str(offset), header, token)
                        items.extend(page.get("items", []))
                indices = set(range(min(10, len(items))))
                for i, row in enumerate(items):
                    if isinstance(row, dict) and any(word in json.dumps(row).lower() for word in
                                                    ("fault", "failed", "failure", "startup", "clock")):
                        indices.update(range(max(0, i - 1), min(len(items), i + 3)))
                emit(check=label + "_HISTORY", inspected=len(items), selected=min(len(indices), 60))
                for i in sorted(indices)[:60]:
                    row = items[i]
                    if not isinstance(row, dict):
                        continue
                    clean = selected(row)
                    if isinstance(row.get("payload"), dict):
                        clean["details"] = selected(row["payload"])
                    emit(check=label + "_EVENT", **clean)
            except Exception as error:  # noqa: BLE001 - export only exception class, never payload
                emit(check=label, error_type=type(error).__name__,
                     http=error.code if isinstance(error, urllib.error.HTTPError) and 100 <= error.code <= 599 else None)

    def journal_checks():
        patterns = {"clock_jump": ("clock discontinuity", "time jumped", "clock was stepped", "time has been changed"),
                    "connection_refused": ("connection refused",),
                    "timeout": ("timed out", "timeouterror"),
                    "lease": ("lease_expired", "uncertain renewal", "lease_mismatch"),
                    "storage": ("database is locked", "disk i/o error", "no space left"),
                    "oom": ("out of memory", "oom-kill"),
                    "process_exit": ("main process exited", "failed with result"),
                    "startup_drain": ("startup_drain_failed",),
                    "actuator_failure": ("actuator_failed", "actuator_failure", "drain_failed")}
        args = ["/usr/bin/journalctl", "--no-pager", "-o", "json", "--since", "2 days ago", "-n", "3000"]
        for unit in ("freeze-protect.service", "node-red.service", "light-controller.service",
                     "light-gpio.service", "freeze-protect-pair-gpio.service", "systemd-timesyncd.service"):
            args.extend(["-u", unit])
        result = subprocess.run(args, capture_output=True, timeout=5, check=False,
                                env=ENV, cwd="/", stdin=subprocess.DEVNULL)
        if len(result.stdout) > 4 * 1024 * 1024:
            emit(check="JOURNAL_SUMMARY", code="OUTPUT_LIMIT")
            return
        count = 0
        for line in result.stdout.splitlines():
            try:
                row = json.loads(line)
                message = str(row.get("MESSAGE", "")).lower()
                tags = [tag for tag, values in patterns.items() if any(v in message for v in values)]
                if tags:
                    timestamp = row.get("__REALTIME_TIMESTAMP", "")
                    emit(check="JOURNAL", time_us=str(timestamp) if str(timestamp).isdigit() and len(str(timestamp)) <= 20 else None, categories=tags)
                    count += 1
            except (ValueError, TypeError):
                pass
        emit(check="JOURNAL_SUMMARY", exit=result.returncode, matches=count, max_entries=3000)

    api_checks()
    try:
        journal_checks()
    except Exception:  # noqa: BLE001 - unavailable diagnostics must not break legacy status
        emit(check="JOURNAL_SUMMARY", code="UNAVAILABLE")
    return {"diagnostic_version": 1, "actuator_commands": 0, "configuration_writes": 0, "checks": rows}


def diagnostic():
    result = {'access_version': 1, 'package_sha256': PACKAGE_SHA,
              'jobs': [phase_status(p) for p in ('prepare', 'install')],
              'recovery': recovery_diagnostic(),
              'hub_recovery': recovery_diagnostic('hub-readiness-recovery'),
              'light_gpio21_bench': light_bench_diagnostic(),
              'controllers': controller_diagnostic(),
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
