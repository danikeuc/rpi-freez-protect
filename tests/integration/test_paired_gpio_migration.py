"""Operator migration tests use files and fake service boundaries, never GPIO."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / "deployment/paired-gpio-migration"


@pytest.fixture
def migration(monkeypatch):
    if not (DIRECTORY / "migrate.py").is_file():
        return None
    monkeypatch.syspath_prepend(str(DIRECTORY))
    monkeypatch.delitem(sys.modules, "operator_checks", raising=False)
    spec = importlib.util.spec_from_file_location("migration_under_test", DIRECTORY / "migrate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_prepare_cannot_mutate_services_or_request_lines(migration, monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(migration, "verify_bundle", lambda: {"files": {"candidate": "abc"}})
    monkeypatch.setattr(migration, "preflight", lambda **kw: calls.append(("preflight", kw)) or {})
    monkeypatch.setattr(migration, "build_venv", lambda: calls.append("build"))
    monkeypatch.setattr(migration, "metadata_check", lambda **kw: calls.append(("metadata", kw)))
    monkeypatch.setattr(migration, "prepared_identity", lambda package: {"verified": True})
    migration.prepare(tmp_path)
    assert calls == [("preflight", {"prepared": False}), "build", ("metadata", {"owned": False})]
    assert json.loads((tmp_path / "PREPARED.json").read_text()) == {"verified": True}


@pytest.mark.parametrize("receipt", [{}, {"ok": True}, {"ok": True, "protocol_version": 2, "command": "DRAIN", "gpio": {"26": 1, "20": 0}}, {"ok": True, "protocol_version": 2, "command": "DRAIN", "gpio": {"26": True, "20": 1}}])
def test_malformed_drain_receipt_latches_stop(migration, monkeypatch, receipt):
    calls = []
    monkeypatch.setattr(migration.c, "run", lambda *a, **k: calls.append(a) or json.dumps(receipt))
    with pytest.raises(RuntimeError):
        migration.c.drain()
    with pytest.raises(RuntimeError):
        migration.c.drain()
    assert len(calls) == 1
    assert migration.c.DRAIN_OR_READBACK_FAILED


@pytest.mark.parametrize("change", [{"operation": "SHOWER"}, {"remaining_seconds": True}, {"command": "SUPPLY"}, {"mode": "manual_timed"}])
def test_rejects_non_user_off(migration, change):
    data = {"mode": "weather_assisted", "operation": "USER_OFF", "state": "MANUAL_DRAIN", "command": "DRAIN", "remaining_seconds": 0}
    data.update(change)
    with pytest.raises(RuntimeError):
        migration.c.validate_status(data)


def test_unknown_manifest_name_rejected_before_file_access(migration, monkeypatch, tmp_path):
    monkeypatch.setattr(migration, "HERE", tmp_path)
    monkeypatch.setattr(migration.c, "secure", lambda *a, **k: None)
    (tmp_path / "manifest.json").write_text(json.dumps({"files": {"../../etc/passwd": "0" * 64}}))
    with pytest.raises(RuntimeError, match="BUNDLE_FILE_SET"):
        migration.verify_bundle()


def test_stale_prepare_receipt_rejected(migration, monkeypatch, tmp_path):
    monkeypatch.setattr(migration.c, "secure", lambda *a, **k: None)
    monkeypatch.setattr(migration, "prepared_identity", lambda _: {"daemon": "new"})
    (tmp_path / "PREPARED.json").write_text('{"daemon":"old"}')
    with pytest.raises(RuntimeError, match="PREPARED_IDENTITY_CHANGED"):
        migration.verify_prepared(tmp_path, {})


def test_atomic_write_failure_keeps_original(migration, monkeypatch, tmp_path):
    target = tmp_path / "daemon"
    target.write_bytes(b"old")
    monkeypatch.setattr(migration.c, "secure", lambda *a, **k: None)
    monkeypatch.setattr(migration.os, "replace", lambda *a: (_ for _ in ()).throw(OSError("disk failed")))
    with pytest.raises(OSError):
        migration.atomic_write(target, b"new", 0o644)
    assert target.read_bytes() == b"old"


def test_failure_output_does_not_disclose_exception(migration, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(migration, "prepare", lambda _: (_ for _ in ()).throw(ValueError("TOKEN_secret")))
    assert migration.execute("prepare", tmp_path) == 1
    assert "TOKEN_secret" not in capsys.readouterr().out
    assert (tmp_path / "FAILURE.json").is_file()



def test_metadata_validator_uses_device_identity_without_requesting_lines(migration, monkeypatch):
    import importlib.metadata
    import io
    import types
    class Chip:
        fd = 7
        def __init__(self, path):
            assert path == '/dev/gpiochip0'
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def get_info(self):
            return types.SimpleNamespace(name='gpiochip0', label='pinctrl-bcm2711', num_lines=58)
        def get_line_info(self, pin):
            return types.SimpleNamespace(name=f'GPIO{pin}', offset=pin, used=False)
        def request_lines(self, **_):
            pytest.fail('prepare requested GPIO lines')
    line = types.ModuleType('gpiod.line')
    for name in ['Direction', 'Bias', 'Edge', 'Value']:
        setattr(line, name, types.SimpleNamespace(AS_IS=1, NONE=0, OUTPUT=2, ACTIVE=1))
    gpio = types.ModuleType('gpiod')
    gpio.Chip = Chip
    gpio.LineRequest = types.SimpleNamespace(reconfigure_lines=lambda: None)
    gpio.LineSettings = lambda **kw: types.SimpleNamespace(**kw)
    monkeypatch.setitem(sys.modules, 'gpiod', gpio)
    monkeypatch.setitem(sys.modules, 'gpiod.line', line)
    monkeypatch.setattr(importlib.metadata, 'version', lambda _: '2.3.0')
    monkeypatch.setattr(sys, 'argv', ['check', 'unused'])
    source = b'def validate_platform(fd, label):\n assert fd == 7 and label == "pinctrl-bcm2711"\n return 123\nclass KernelOwnedPair:\n def __init__(self,*a): raise AssertionError("NO CONSTRUCTION")\n'
    monkeypatch.setattr(sys, 'stdin', types.SimpleNamespace(buffer=io.BytesIO(source)))
    monkeypatch.setattr(migration.os, 'access', lambda *a: True)
    original_stat = migration.os.stat
    monkeypatch.setattr(migration.os, 'stat', lambda path, *a, **kw: types.SimpleNamespace(st_rdev=123) if str(path) == '/dev/gpiomem' else original_stat(path, *a, **kw))
    exec(migration.METADATA_CODE, {})  # noqa: S102 - execute reviewed probe against fake hardware


def test_real_lighting_units_block_migration(migration, monkeypatch):
    seen = []
    monkeypatch.setattr(migration.c, 'active', lambda name: seen.append(name) or name == 'light-gpio.service')
    monkeypatch.setattr(migration, 'show', lambda *a: '0')
    monkeypatch.setattr(migration.c, 'run', lambda *a, **kw: 'disabled')
    with pytest.raises(RuntimeError, match='LIGHTING_ACTIVE'):
        migration.lighting_disabled()
    assert 'light-gpio.service' in seen


def test_cutover_orders_authority_backup_and_restart(migration, monkeypatch, tmp_path):
    calls = []
    state = {'entries': {}, 'settings': {'enabled': True}}
    def action(name, result=None):
        return lambda *a, **kw: calls.append(name) or result
    monkeypatch.setattr(migration, 'backup', action('backup'))
    monkeypatch.setattr(migration.c, 'status', action('status'))
    monkeypatch.setattr(migration, 'preserved', action('preserved'))
    monkeypatch.setattr(migration.c, 'run', lambda args, **kw: calls.append(' '.join(args)))
    monkeypatch.setattr(migration.c, 'stopped', action('hub-stopped'))
    monkeypatch.setattr(migration.c, 'drain', action('drain'))
    monkeypatch.setattr(migration.c, 'persistent_stop', lambda: state['settings'])
    monkeypatch.setattr(migration.c, 'active', lambda service: service != migration.PAIR or 'systemctl start ' + migration.PAIR in calls)
    monkeypatch.setattr(migration, 'show', lambda *a: '0')
    monkeypatch.setattr(migration.c, 'pair_high', action('high'))
    monkeypatch.setattr(migration.time, 'sleep', action('expire'))
    monkeypatch.setattr(migration, 'metadata_check', action('metadata'))
    monkeypatch.setattr(migration, 'install_files', action('replace'))
    monkeypatch.setattr(migration, 'wait_pair', action('socket'))
    monkeypatch.setattr(migration, 'verify_running', action('owner'))
    monkeypatch.setattr(migration, 'live_environment', action('live-env'))
    monkeypatch.setattr(migration.c, 'flow', action('flow'))
    monkeypatch.setattr(migration.c, 'digest', lambda *a: 'abc')
    migration.cutover(state, tmp_path, {})
    assert calls[:14] == ['backup', 'status', 'preserved', 'systemctl stop freeze-protect.service',
        'hub-stopped', 'drain', 'systemctl stop freeze-protect-pair-gpio.service', 'high', 'expire',
        'metadata', 'replace', 'systemctl start freeze-protect-pair-gpio.service', 'socket', 'drain']
    assert calls.index('owner') < calls.index('systemctl start freeze-protect.service')
    assert (tmp_path / 'SUCCESS.json').is_file()


def test_receipt_failure_stops_cutover_without_retry(migration, monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(migration, 'backup', lambda *a: None)
    monkeypatch.setattr(migration.c, 'status', lambda *a: None)
    monkeypatch.setattr(migration, 'preserved', lambda *a: None)
    monkeypatch.setattr(migration.c, 'stopped', lambda: None)
    monkeypatch.setattr(migration.c, 'active', lambda *a: True)
    def run(args, **kw):
        calls.append(args)
        return '{}' if 'DRAIN' in args else ''
    monkeypatch.setattr(migration.c, 'run', run)
    monkeypatch.setattr(migration, 'install', lambda evidence, attempt: migration.cutover({'entries': {}}, evidence, attempt))
    assert migration.execute('install', tmp_path) == 1
    assert sum('DRAIN' in command for command in calls) == 1
    assert calls.count(['systemctl', 'stop', migration.c.HUB]) == 2
    assert not any('start' in command for command in calls)
    assert not (tmp_path / 'SUCCESS.json').exists()



def test_readiness_dropin_is_accepted_and_unknown_override_rejected(migration, monkeypatch, tmp_path):
    unit = tmp_path / 'hub.service'
    unit.write_text('[Service]\nUser=freezeprotect\n')
    dropdir = tmp_path / 'hub.service.d'
    dropdir.mkdir()
    ready = dropdir / '30-node-red-readiness.conf'
    ready.write_text('[Service]\nExecStartPre=/reviewed/startup_ready\n')
    monkeypatch.setattr(migration, 'HERE', tmp_path)
    monkeypatch.setattr(migration.c, 'secure', lambda *a, **kw: None)
    fields = {'FragmentPath': str(unit), 'DropInPaths': str(ready), 'NeedDaemonReload': 'no'}
    monkeypatch.setattr(migration, 'show', lambda _, field: fields[field])
    migration.unit_check('hub.service', unit, 'hub.service', [ready])
    extra = dropdir / 'unknown.conf'
    extra.write_text('[Service]\nUser=root\n')
    with pytest.raises(RuntimeError, match='UNKNOWN_UNIT_FILES'):
        migration.unit_check('hub.service', unit, 'hub.service', [ready])


def test_dependency_failure_does_not_write_prepared_receipt(migration, monkeypatch, tmp_path):
    monkeypatch.setattr(migration, 'verify_bundle', dict)
    monkeypatch.setattr(migration, 'preflight', lambda **kw: {})
    monkeypatch.setattr(migration, 'build_venv', lambda: (_ for _ in ()).throw(RuntimeError('NO_OFFLINE_DEPENDENCY')))
    assert migration.execute('prepare', tmp_path) == 1
    assert not (tmp_path / 'PREPARED.json').exists()
    assert not (tmp_path / 'INSTALL_STARTED').exists()


@pytest.mark.parametrize('arguments', [[], ['prepare', '--24v-disconnected'], ['install', '--24v-disconnected', '--mains-lamp-disconnected'], ['prepare', '--mains-lamp-disconnected']])
def test_explicit_both_load_flags_are_required_before_work(migration, monkeypatch, arguments):
    monkeypatch.setattr(sys, 'argv', ['migrate.py', *arguments])
    monkeypatch.setattr(migration.os, 'geteuid', lambda: 0)
    with pytest.raises(RuntimeError):
        migration.main()


def test_install_checks_receipt_before_preflight_or_cutover(migration, monkeypatch, tmp_path):
    monkeypatch.setattr(migration, 'verify_bundle', dict)
    monkeypatch.setattr(migration, 'verify_prepared', lambda *a: (_ for _ in ()).throw(RuntimeError('STALE_RECEIPT')))
    monkeypatch.setattr(migration, 'preflight', lambda **kw: pytest.fail('preflight ran after bad receipt'))
    monkeypatch.setattr(migration, 'cutover', lambda *a: pytest.fail('cutover ran after bad receipt'))
    with pytest.raises(RuntimeError, match='STALE_RECEIPT'):
        migration.install(tmp_path, {})


def test_metadata_unknown_chip_is_rejected_before_request(migration, monkeypatch):
    # The canonical device must not be replaced by a gpiochip4 symlink alias.
    monkeypatch.setattr(migration.platform, 'machine', lambda: 'aarch64')
    monkeypatch.setattr(migration.platform, 'release', lambda: '6.18.39+rpt-rpi-v8')
    monkeypatch.setattr(sys, 'version_info', (3, 13, 5))
    monkeypatch.setattr(Path, 'read_bytes', lambda p: b'Raspberry Pi 4 Model B Rev 1.1\0')
    monkeypatch.setattr(Path, 'is_symlink', lambda p: str(p) == '/dev/gpiochip0')
    with pytest.raises(RuntimeError, match='CANONICAL_CHIP_REQUIRED'):
        migration.host_identity()


def test_unknown_host_is_rejected(migration, monkeypatch):
    monkeypatch.setattr(Path, 'read_bytes', lambda p: b'Raspberry Pi 5 Model B\0')
    with pytest.raises(RuntimeError, match='HOST_MODEL'):
        migration.host_identity()



@pytest.mark.parametrize('markers', [('INSTALL_STARTED', 'SUCCESS.json'), ('INSTALL_STARTED',), ('SUCCESS.json',)])
def test_historical_evidence_rejected_without_commands_or_evidence_changes(migration, monkeypatch, tmp_path, markers):
    (tmp_path / 'PREPARED.json').write_text('{"daemon":"old"}')
    for name in markers:
        (tmp_path / name).write_text('historical evidence\n')
    original = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    calls = []
    monkeypatch.setattr(migration, 'verify_bundle', dict)
    monkeypatch.setattr(migration.c, 'secure', lambda *a, **kw: None)
    monkeypatch.setattr(migration, 'prepared_identity', lambda _: {'daemon': 'changed'})
    monkeypatch.setattr(migration.c, 'run', lambda args, **kw: calls.append(args) or '')
    monkeypatch.setattr(migration.c, 'active', lambda _: True)
    monkeypatch.setattr(migration.c, 'stopped', lambda: None)
    monkeypatch.setattr(migration.c, 'drain', lambda: calls.append(['DRAIN']))
    assert migration.execute('install', tmp_path) == 1
    assert calls == []
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == original


@pytest.fixture
def cutover_files(migration, monkeypatch, tmp_path):
    """Real backup/SQLite/replacement operations; only host and service boundaries fake."""
    import sqlite3
    bundle = tmp_path / 'bundle'
    bundle.mkdir()
    live = tmp_path / 'live'
    live.mkdir()
    evidence = tmp_path / 'evidence'
    evidence.mkdir()
    daemon = live / 'daemon.py'
    daemon.write_bytes(b'old daemon')
    (bundle / 'paired_gpio_daemon.py').write_bytes(b'new daemon')
    (bundle / 'paired-gpio.env').write_bytes(b'fixed environment')
    (bundle / 'paired-gpio.conf').write_bytes(b'fixed unit override')
    db = live / 'database.sqlite3'
    with sqlite3.connect(db) as connection:
        connection.execute('CREATE TABLE preserved (value TEXT)')
        connection.execute("INSERT INTO preserved VALUES ('history')")
    db.with_name(db.name + '.weather-identity').write_text('a' * 32)
    preserved = live / 'environment'
    preserved.write_bytes(b'private preserved environment')
    state = {'entries': {}, 'settings': {'enabled': True}, 'packages': {'rpi-freeze-protect': '1.3.1'}, 'history': {}}
    monkeypatch.setattr(migration, 'HERE', bundle)
    monkeypatch.setattr(migration, 'DEST', daemon)
    monkeypatch.setattr(migration, 'OLD', migration.c.digest(daemon))
    monkeypatch.setattr(migration, 'PRESERVED', (preserved,))
    monkeypatch.setattr(migration, 'DROPIN', live / '40-paired-gpio.conf')
    monkeypatch.setattr(migration, 'PAIR_ENV', live / 'paired-gpio.env')
    monkeypatch.setattr(migration, 'MARKER', live / 'paired-approved')
    monkeypatch.setattr(migration.c, 'DB', db)
    monkeypatch.setattr(migration.c, 'secure', lambda *a, **kw: None)
    monkeypatch.setattr(migration, 'verify_bundle', dict)
    monkeypatch.setattr(migration, 'prepared_identity', lambda _: {'prepared': True})
    (evidence / 'PREPARED.json').write_text('{"prepared":true}')
    monkeypatch.setattr(migration, 'preflight', lambda **kw: state)
    monkeypatch.setattr(migration, 'metadata_check', lambda **kw: None)
    monkeypatch.setattr(migration, 'preserved', lambda _: None)
    monkeypatch.setattr(migration.c, 'status', lambda _: None)
    monkeypatch.setattr(migration.c, 'persistent_stop', lambda: state['settings'])
    monkeypatch.setattr(migration.c, 'pair_high', lambda: None)
    monkeypatch.setattr(migration.time, 'sleep', lambda _: None)
    commands = []
    services = {migration.c.HUB: True, migration.PAIR: True}
    def run(args, **kw):
        commands.append(args)
        if args[0] == 'systemctl':
            assert args[1] == 'stop', 'failure path restarted a service'
            services[args[2]] = False
            return ''
        assert args[-1] == 'DRAIN', 'unexpected operator command'
        return '{"ok":true,"protocol_version":2,"command":"DRAIN","gpio":{"26":1,"20":1}}'
    monkeypatch.setattr(migration.c, 'run', run)
    monkeypatch.setattr(migration.c, 'active', lambda name: services[name])
    def stopped():
        assert services[migration.c.HUB] is False
    monkeypatch.setattr(migration.c, 'stopped', stopped)
    monkeypatch.setattr(migration, 'show', lambda service, field: '0' if not services[service] else '1')
    return evidence, daemon, commands, services


@pytest.mark.parametrize('fault', ['backup_file_fsync', 'backup_hash', 'backup_directory_fsync', 'marker_directory_fsync'])
def test_durability_failure_before_cutover_never_mutates_services(migration, monkeypatch, cutover_files, fault):
    import stat
    evidence, daemon, commands, services = cutover_files
    fsync = migration.os.fsync
    digest = migration.c.digest
    failed = False
    def fail_fsync(fd):
        nonlocal failed
        is_directory = stat.S_ISDIR(migration.os.fstat(fd).st_mode)
        current = Path('/proc/self/fd/' + str(fd)).resolve()
        trigger = ((fault == 'backup_file_fsync' and current.name == 'before-00')
                   or (fault == 'backup_directory_fsync' and is_directory and current == evidence)
                   or (fault == 'marker_directory_fsync' and is_directory and current == evidence
                       and (evidence / 'INSTALL_STARTED').exists()))
        if trigger and not failed:
            failed = True
            raise OSError('injected durability failure')
        fsync(fd)
    def fail_digest(path):
        nonlocal failed
        if fault == 'backup_hash' and Path(path).name == 'before-00' and not failed:
            failed = True
            return 'wrong hash'
        return digest(path)
    monkeypatch.setattr(migration.os, 'fsync', fail_fsync)
    monkeypatch.setattr(migration.c, 'digest', fail_digest)
    assert migration.execute('install', evidence) == 1
    assert failed
    assert commands == []
    assert services[migration.c.HUB] and services[migration.PAIR]
    assert daemon.read_bytes() == b'old daemon'
    assert (evidence / 'before-00').read_bytes() == b'old daemon'
    assert (evidence / 'FAILURE.json').is_file()
    assert not (evidence / 'SUCCESS.json').exists()


@pytest.mark.parametrize('fault', ['daemon_directory_fsync', 'environment_replace', 'environment_readback'])
def test_partial_replacement_keeps_hub_stopped_and_recovery_evidence(migration, monkeypatch, cutover_files, fault):
    import stat
    evidence, daemon, commands, services = cutover_files
    replace = migration.os.replace
    fsync = migration.os.fsync
    read_bytes = Path.read_bytes
    failed = False
    def fail_replace(source, destination):
        nonlocal failed
        if fault == 'environment_replace' and destination == migration.PAIR_ENV:
            failed = True
            raise OSError('injected environment replacement failure')
        return replace(source, destination)
    def fail_fsync(fd):
        nonlocal failed
        if (fault == 'daemon_directory_fsync' and not failed
                and stat.S_ISDIR(migration.os.fstat(fd).st_mode)
                and Path('/proc/self/fd/' + str(fd)).resolve() == daemon.parent
                and read_bytes(daemon) == b'new daemon'):
            failed = True
            raise OSError('injected directory fsync failure after daemon replace')
        fsync(fd)
    def fail_readback(path):
        nonlocal failed
        if fault == 'environment_readback' and path == migration.PAIR_ENV and path.exists():
            failed = True
            return b'corrupt environment'
        return read_bytes(path)
    monkeypatch.setattr(migration.os, 'replace', fail_replace)
    monkeypatch.setattr(migration.os, 'fsync', fail_fsync)
    monkeypatch.setattr(Path, 'read_bytes', fail_readback)
    assert migration.execute('install', evidence) == 1
    assert failed
    assert not services[migration.c.HUB] and not services[migration.PAIR]
    assert daemon.read_bytes() == b'new daemon'  # No automatic rollback.
    assert not migration.DROPIN.exists() and not migration.MARKER.exists()
    assert (evidence / 'before-00').read_bytes() == b'old daemon'
    assert (evidence / 'BACKUP_COMPLETE.json').is_file()
    assert (evidence / 'database.sqlite3').is_file()
    assert (evidence / 'INSTALL_STARTED').is_file()
    assert (evidence / 'FAILURE.json').is_file()
    assert sum('DRAIN' in command for command in commands) == 1
    assert commands.count(['systemctl', 'stop', migration.c.HUB]) == 2
    assert (evidence / 'database.weather-identity').read_text() == 'a' * 32
    assert not any('start' in command for command in commands)
    assert not (evidence / 'SUCCESS.json').exists()


def test_actual_baseline_mismatch_through_execute_does_not_mutate_services(migration, monkeypatch, tmp_path):
    daemon = tmp_path / 'daemon.py'
    daemon.write_bytes(b'unexpected installed daemon')
    evidence = tmp_path / 'evidence'
    evidence.mkdir()
    (evidence / 'PREPARED.json').write_text('{"prepared":true}')
    monkeypatch.setattr(migration, 'DEST', daemon)
    monkeypatch.setattr(migration, 'verify_bundle', dict)
    monkeypatch.setattr(migration, 'prepared_identity', lambda _: {'prepared': True})
    monkeypatch.setattr(migration, 'host_identity', dict)
    monkeypatch.setattr(migration.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(migration.c, 'secure', lambda *a, **kw: None)
    commands = []
    monkeypatch.setattr(migration.c, 'run', lambda args, **kw: commands.append(args))
    assert migration.execute('install', evidence) == 1
    assert commands == []
    assert daemon.read_bytes() == b'unexpected installed daemon'
    assert 'BASELINE_DAEMON_CHANGED' in (evidence / 'failure-private.log').read_text()
    assert not (evidence / 'INSTALL_STARTED').exists()
