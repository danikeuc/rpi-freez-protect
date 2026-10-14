"""Prove fixed authority, fail-closed replay and retained current commissioning."""
import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'deployment/maintenance-access' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def maintenance(tmp_path, monkeypatch):
    m = load('maintenance')
    m.STATE = tmp_path / 'state'
    m.BASE = tmp_path / 'base'
    m.STATE.mkdir()
    m.BASE.mkdir()
    monkeypatch.setattr(m, 'secure', lambda _: None)
    return m


def test_dispatch_preserves_four_commands_and_adds_only_three(tmp_path):
    installer = load('install_access')
    original = (ROOT / 'deployment/workstation-codex/freeze-protect-commission-ssh-dispatch').read_bytes()
    rendered = installer.extended_dispatch(original)
    assert rendered.replace(rendered[rendered.index(b'  "sudo -n /usr/local/sbin/freeze-protect-maintenance'):rendered.index(b'  *)')], b'') == original
    stub = tmp_path / 'sudo'
    stub.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
    stub.chmod(0o755)
    script = tmp_path / 'dispatch'
    script.write_bytes(rendered.replace(b'/usr/bin/sudo', str(stub).encode()))
    for command in ('inventory', 'status', 'diagnose-pair-gpio', 'drain'):
        exact = 'sudo -n /usr/local/sbin/freeze-protect-commission ' + command
        assert subprocess.run(['/bin/sh', str(script)], env={'SSH_ORIGINAL_COMMAND': exact}, capture_output=True, check=False).returncode == 0
    for command in ('status', 'prepare', 'install'):
        exact = 'sudo -n /usr/local/sbin/freeze-protect-maintenance ' + command
        assert subprocess.run(['/bin/sh', str(script)], env={'SSH_ORIGINAL_COMMAND': exact}, capture_output=True, check=False).returncode == 0
        for invalid in (exact + ' extra', exact + '; id', exact + '\n', exact + ' --help'):
            assert subprocess.run(['/bin/sh', str(script)], env={'SSH_ORIGINAL_COMMAND': invalid}, capture_output=True, check=False).returncode == 64
    for invalid in ('', 'id', 'sudo -n /bin/sh', 'sudo -n /usr/local/sbin/freeze-protect-maintenance _install'):
        assert subprocess.run(['/bin/sh', str(script)], env={'SSH_ORIGINAL_COMMAND': invalid}, capture_output=True, check=False).returncode == 64
    assert b'ALL)' not in installer.SUDO_BYTES
    assert b' *' not in installer.SUDO_BYTES


def test_wrong_package_refused_before_extract(maintenance):
    with pytest.raises(RuntimeError, match='PACKAGE_HASH'):
        maintenance.bundle_members(b'not reviewed content')


def test_approval_bound_to_boot_package_disconnection_expiry(maintenance, monkeypatch):
    m = maintenance
    monkeypatch.setattr(m, 'boot', lambda: 'current')
    monkeypatch.setattr(m.time, 'monotonic', lambda: 100)
    valid = {'boot_id': 'current', 'package_sha256': m.PACKAGE_SHA,
             'loads_disconnected': True, 'expires_monotonic': 101}
    monkeypatch.setattr(m, 'read_json', lambda _: valid)
    m.approval()
    for key, value in [('boot_id', 'old'), ('package_sha256', 'different'),
                       ('loads_disconnected', False), ('expires_monotonic', 100)]:
        bad = {**valid, key: value}
        monkeypatch.setattr(m, 'read_json', lambda _, bad=bad: bad)
        with pytest.raises(RuntimeError):
            m.approval()


def test_request_is_one_shot_before_dispatch_even_on_failure(maintenance, monkeypatch):
    m = maintenance
    monkeypatch.setattr(m, 'approval', lambda: None)
    monkeypatch.setattr(m, 'verified_package', lambda: m.BASE)
    commands = []
    def failed(args):
        assert (m.STATE / 'prepare-request.json').is_file()
        commands.append(args)
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr(m, 'run', failed)
    with pytest.raises(RuntimeError, match='DISPATCH_UNCONFIRMED'):
        m.request('prepare')
    with pytest.raises(FileExistsError):
        m.request('prepare')
    assert len(commands) == 1
    assert '--property=Restart=no' in commands[0]
    assert '--no-block' in commands[0]
    assert commands[0][-1] == '_prepare'


def test_install_requires_successful_prepare(maintenance, monkeypatch):
    m = maintenance
    monkeypatch.setattr(m, 'approval', lambda: None)
    monkeypatch.setattr(m, 'verified_package', lambda: m.BASE)
    m.record(m.STATE / 'prepare-result.json', {'verified': False})
    with pytest.raises(RuntimeError, match='PREPARE_NOT_VERIFIED'):
        m.request('install')
    assert not (m.STATE / 'install-request.json').exists()


def test_malformed_evidence_rejected(maintenance):
    for value in ('/etc/shadow', '/root/paired-gpio-migration.x/../../etc', None):
        with pytest.raises(RuntimeError, match='EVIDENCE_PATH'):
            maintenance.evidence_path(value)


def test_receipt_needs_exit_zero_and_real_marker(maintenance, tmp_path, monkeypatch):
    m = maintenance
    evidence = tmp_path / 'evidence'
    evidence.mkdir()
    monkeypatch.setattr(m, 'evidence_path', lambda _: evidence)
    output = 'PAIRED_MIGRATION_PREPARE_VERIFIED evidence=/root/paired-gpio-migration.abc\n'
    assert m.classify('prepare', 1, output)['verified'] is False
    with pytest.raises(RuntimeError, match="INVALID_RECORD"):
        m.classify('prepare', 0, output)
    (evidence / 'PREPARED.json').write_text(json.dumps({'venv': {str(i): 'a' * 64 for i in range(2000)}}))
    assert m.classify('prepare', 0, output)['verified'] is True
    assert m.classify('prepare', 0, output + output)['verified'] is False
    (evidence / 'FAILURE.json').write_text('{}')
    with pytest.raises(RuntimeError, match='MIGRATION_FAILED'):
        m.classify('prepare', 0, output)


def test_status_omits_raw_subprocess_output(maintenance, monkeypatch):
    m = maintenance
    m.ARTIFACTS = ()
    monkeypatch.setattr(m, 'recovery_diagnostic', lambda *a: {})
    monkeypatch.setattr(m, 'run', lambda _: SimpleNamespace(stdout=b'ActiveState=active\nSECRET=token\nMainPID=1\nResult=bad secret\n'))
    result = json.dumps(m.diagnostic())
    assert 'active' in result
    assert 'SECRET' not in result and 'token' not in result and 'bad secret' not in result


def test_secure_rejects_symlink_and_world_write(tmp_path):
    m = load('maintenance')
    link = tmp_path / 'link'
    link.symlink_to('/etc/passwd')
    with pytest.raises(RuntimeError, match='UNTRUSTED_PATH'):
        m.secure(link)
    insecure = tmp_path / 'bad'
    insecure.write_text('x')
    insecure.chmod(0o666)
    with pytest.raises(RuntimeError, match='UNTRUSTED_PATH'):
        m.secure(insecure)


def test_worker_consumes_only_durable_request_and_records_failure(maintenance, monkeypatch):
    m = maintenance
    monkeypatch.setattr(m, 'approval', lambda: None)
    m.record(m.STATE / 'prepare-request.json', {'phase': 'prepare', 'boot_id': m.boot(), 'package_sha256': m.PACKAGE_SHA})
    def fail():
        raise RuntimeError('changed package')
    monkeypatch.setattr(m, 'verified_package', fail)
    with pytest.raises(RuntimeError):
        m.worker('prepare')
    assert m.read_json(m.STATE / 'prepare-result.json')['verified'] is False
    with pytest.raises(FileExistsError):
        m.worker('prepare')


def test_runtime_rejects_unexpected_arguments_before_action(maintenance, monkeypatch):
    m = maintenance
    monkeypatch.setattr(m.os, 'geteuid', lambda: 0)
    for args in (['maintenance.py'], ['maintenance.py', 'restart'], ['maintenance.py', 'install', '/evil']):
        monkeypatch.setattr(m.sys, 'argv', args)
        with pytest.raises(RuntimeError, match='COMMAND_REJECTED'):
            m.main()


@pytest.fixture
def installer_env(tmp_path, monkeypatch):
    import hashlib
    import io
    import tarfile
    inst = load('install_access')
    base = tmp_path / 'installed'
    state = tmp_path / 'state'
    stage = tmp_path / 'stage'
    stage.mkdir()
    inst.HERE, inst.BASE, inst.STATE = stage, base, state
    inst.DISPATCH = tmp_path / 'dispatch'
    inst.SUDO = tmp_path / 'sudoers-new'
    inst.LAUNCHER = tmp_path / 'launcher'
    inst.ORIGINALS = {
        'original-dispatch': inst.DISPATCH,
        'original-sudoers': tmp_path / 'sudoers-old',
        'original-helper': tmp_path / 'helper',
    }
    sources = {'original-dispatch': 'freeze-protect-commission-ssh-dispatch',
               'original-sudoers': 'freeze-protect-commission.sudoers',
               'original-helper': 'freeze-protect-commission'}
    for name, filename in sources.items():
        data = (ROOT / 'deployment/workstation-codex' / filename).read_bytes()
        (stage / name).write_bytes(data)
        inst.ORIGINALS[name].write_bytes(data)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as archive:
        for i in range(14):
            member = tarfile.TarInfo('item' + str(i))
            member.size = 1
            archive.addfile(member, io.BytesIO(b'x'))
    raw = buf.getvalue()
    m = load('maintenance')
    source = (ROOT / 'deployment/maintenance-access/maintenance.py').read_text()
    source = source.replace(m.PACKAGE_SHA, hashlib.sha256(raw).hexdigest())
    (stage / 'maintenance.py').write_text(source)
    (stage / 'migration.tar.gz').write_bytes(raw)
    (stage / 'install_access.py').write_bytes((ROOT / 'deployment/maintenance-access/install_access.py').read_bytes())
    (stage / 'README.md').write_text('fixture')
    (stage / 'manifest.json').write_text(json.dumps({'files': {
        f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in stage.iterdir()
    }}))
    original_read = Path.read_bytes
    monkeypatch.setattr(Path, 'read_bytes', lambda path: b'Raspberry Pi 4 Model B Rev 1.1\0'
                        if str(path) == '/proc/device-tree/model' else original_read(path))
    monkeypatch.setattr(inst, 'secure', lambda _: None)
    monkeypatch.setattr(inst.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(inst.sys, 'argv', ['install_access.py', '--loads-disconnected'])
    monkeypatch.setattr(inst.pwd, 'getpwnam', lambda _: SimpleNamespace(pw_uid=123))
    original_mkdtemp = inst.tempfile.mkdtemp
    monkeypatch.setattr(inst.tempfile, 'mkdtemp', lambda **kwargs: original_mkdtemp(
        prefix=kwargs['prefix'], dir=tmp_path))
    original_is_dir = Path.is_dir
    monkeypatch.setattr(Path, 'is_dir', lambda path: True if str(path) == '/run/systemd/system' else original_is_dir(path))
    calls = []
    def call(args):
        calls.append(args)
        if '-T' in args:
            return ('forcecommand ' + str(inst.DISPATCH) + '\npasswordauthentication no\npermittty no\nallowtcpforwarding no').encode()
        if args == [str(inst.LAUNCHER), 'status']:
            return b'{"access_version":1}'
        return b''
    monkeypatch.setattr(inst, 'call', call)
    return inst, calls


def test_access_install_stages_pinned_package_without_relay_or_service_actions(installer_env):
    inst, calls = installer_env
    original = inst.DISPATCH.read_bytes()
    inst.main()
    assert inst.DISPATCH.read_bytes() == inst.extended_dispatch(original)
    assert inst.SUDO.read_bytes() == inst.SUDO_BYTES
    assert inst.LAUNCHER.read_bytes() == inst.LAUNCHER_BYTES
    assert len(list((inst.BASE / 'package').iterdir())) == 14
    assert not (inst.STATE / 'prepare-request.json').exists()
    assert json.loads((inst.STATE / 'approval.json').read_text())['loads_disconnected'] is True
    assert not any('restart' in args or 'start' in args or 'stop' in args or 'drain' in args for args in calls)
    backups = list(inst.BASE.parent.glob('freeze-maintenance-access.*'))
    assert len(backups) == 1
    assert (backups[0] / 'before-0').read_bytes() == original
    assert (backups[0] / 'INSTALLED.json').is_file()
    with pytest.raises(RuntimeError, match='EXISTING_INSTALLATION'):
        inst.main()


def test_unknown_baseline_stops_before_writes(installer_env):
    inst, _ = installer_env
    inst.DISPATCH.write_bytes(b'changed')
    with pytest.raises(RuntimeError, match='ORIGINAL_CHANGED'):
        inst.main()
    assert not inst.BASE.exists() and not inst.STATE.exists() and not inst.SUDO.exists()


def test_failed_sudo_check_keeps_original_dispatch_and_private_backup(installer_env, monkeypatch):
    inst, _ = installer_env
    original = inst.DISPATCH.read_bytes()
    real_call = inst.call
    def call(args):
        if args[0] == '/usr/sbin/visudo' and inst.SUDO.exists():
            raise RuntimeError('CONFIGURATION_CHECK_FAILED')
        return real_call(args)
    monkeypatch.setattr(inst, 'call', call)
    with pytest.raises(RuntimeError, match='CONFIGURATION_CHECK_FAILED'):
        inst.main()
    assert inst.DISPATCH.read_bytes() == original
    backup = next(inst.BASE.parent.glob('freeze-maintenance-access.*'))
    assert (backup / 'STOPPED').is_file()
    assert (backup / 'before-0').read_bytes() == original


def test_after_dispatch_failure_retains_evidence_without_auto_rollback(installer_env, monkeypatch):
    inst, _ = installer_env
    original = inst.DISPATCH.read_bytes()
    real_call = inst.call
    def call(args):
        if args == [str(inst.LAUNCHER), 'status']:
            raise RuntimeError('CONFIGURATION_CHECK_FAILED')
        return real_call(args)
    monkeypatch.setattr(inst, 'call', call)
    with pytest.raises(RuntimeError):
        inst.main()
    assert inst.DISPATCH.read_bytes() == inst.extended_dispatch(original)
    backup = next(inst.BASE.parent.glob('freeze-maintenance-access.*'))
    assert (backup / 'STOPPED').is_file()
    assert not (backup / 'INSTALLED.json').exists()


def test_failure_detail_exports_only_pinned_labels(maintenance, tmp_path, monkeypatch):
    m = maintenance
    evidence = tmp_path / 'evidence'
    evidence.mkdir()
    (m.STATE / 'prepare-private.log').write_text('secret-token\nPAIRED_MIGRATION_STOPPED evidence=/root/paired-gpio-migration.abc\n')
    (evidence / 'failure-private.log').write_text('a-secret\nRuntimeError: NOT_A_KNOWN_LABEL\nRuntimeError: UNIT_CHANGED\n')
    (m.BASE / 'migration.tar.gz').write_bytes(b'fixture')
    monkeypatch.setattr(m, 'evidence_path', lambda _: evidence)
    monkeypatch.setattr(m, 'bundle_members', lambda _: {'migrate.py': b"require(ok, 'UNIT_CHANGED')"})
    result = m.failure_detail('prepare')
    assert result['failure_code'] == 'UNIT_CHANGED'
    assert 'secret' not in json.dumps(result) and 'NOT_A_KNOWN' not in json.dumps(result)



def test_worker_waits_for_submitter_lock_instead_of_losing_request(maintenance, monkeypatch, tmp_path):
    import fcntl
    import multiprocessing
    import os
    import time
    m = maintenance
    monkeypatch.setattr(m.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(m.sys, 'argv', ['maintenance.py', '_prepare'])
    marker = tmp_path / 'worker-ran'
    monkeypatch.setattr(m, 'worker', lambda _: marker.write_text('ran'))
    lock = os.open(m.STATE / 'operation.lock', os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(lock, fcntl.LOCK_EX)
    child = multiprocessing.get_context('fork').Process(target=m.main)
    try:
        child.start()
        time.sleep(0.1)
        assert child.is_alive() and not marker.exists()
        fcntl.flock(lock, fcntl.LOCK_UN)
        child.join(timeout=3)
        assert child.exitcode == 0 and marker.read_text() == 'ran'
    finally:
        os.close(lock)
        if child.is_alive():
            child.terminate()
            child.join(timeout=3)



@pytest.mark.parametrize(('args', 'name'), [
    (['/usr/sbin/sshd', '-t'], 'SSHD_SYNTAX'),
    (['/usr/sbin/visudo', '-c'], 'SUDOERS_SYNTAX'),
    (['/usr/sbin/sshd', '-T', '-C', 'fixed-context'], 'SSHD_EFFECTIVE'),
    (['/usr/bin/systemd-run', '--version'], 'SYSTEMD_RUN'),
    (['/bin/sh', '-n', '/private/candidate'], 'DISPATCH_SYNTAX'),
    (['/usr/sbin/visudo', '-cf', '/private/candidate'], 'SUDOERS_CANDIDATE'),
    (['/usr/local/sbin/freeze-protect-maintenance', 'status'], 'MAINTENANCE_STATUS'),
])
def test_failed_configuration_check_identifies_phase_without_exporting_output(args, name, monkeypatch, capsys):
    inst = load('install_access')
    monkeypatch.setattr(inst.subprocess, 'run', lambda *a, **k: SimpleNamespace(
        returncode=1, stdout=b'private-token', stderr=b'syntax error: private-config-line'))
    with pytest.raises(RuntimeError, match='CHECK_FAILED_' + name):
        inst.call(args)
    output = capsys.readouterr().out
    assert json.loads(output) == {'check': name, 'exit': 1, 'reasons': ['syntax_error']}
    assert 'private' not in output


def test_configuration_timeout_and_missing_executable_are_sanitized(monkeypatch, capsys):
    inst = load('install_access')
    for exc in (FileNotFoundError('private-path'), subprocess.TimeoutExpired('private-command', 15)):
        def failed(*_, exc=exc, **kwargs):
            raise exc
        monkeypatch.setattr(inst.subprocess, 'run', failed)
        with pytest.raises(RuntimeError, match='CHECK_FAILED_SSHD_SYNTAX'):
            inst.call(['/usr/sbin/sshd', '-t'])
        output = capsys.readouterr().out
        assert 'private' not in output
        assert json.loads(output)['error_type'] == type(exc).__name__


@pytest.mark.parametrize('error', ['RuntimeError: EFFECTIVE_DEVICE_ALLOW',
    'RuntimeError: command failed; private log retained', 'ValueError: SECRET_TOKEN'])
def test_recovery_diagnostic_redacts_payload_and_reads_only_fixed_paths(maintenance, monkeypatch, tmp_path, error):
    m = maintenance
    directory = tmp_path / 'fixed-recovery'
    directory.mkdir()
    monkeypatch.setattr(m, 'Path', lambda p: directory if p ==
        '/root/paired-gpio-migration.xj0q8tgi/device-allow-recovery' else Path(p))
    (directory / 'STARTED').write_text('started')
    (directory / 'FAILED').write_text('failed')
    (directory / 'failure-private.log').write_text('  File "/root/private/recover_device_allow.py", line 123\n' +
        '    SECRET_SOURCE_LINE\n  File "/etc/SECRET_PATH", line 10\n' + error + '\n')
    (directory / 'private.log').write_text('  File "<string>", line 18\nAssertionError: SECRET_OTHER\nPermission denied')
    (m.BASE / 'migration.tar.gz').write_bytes(b'package')
    monkeypatch.setattr(m, 'bundle_members', lambda raw: {'migrate.py': b"require(True, 'EFFECTIVE_DEVICE_ALLOW')"})
    result = m.recovery_diagnostic()
    encoded = json.dumps(result)
    assert 'SECRET' not in encoded and '/etc/' not in encoded
    assert result['markers'] == {'STARTED': True, 'FAILED': True, 'SUCCESS.json': False}
    assert result['frames'] == [{'file': 'recover_device_allow.py', 'line': 123}]
    assert result['probe_lines'] == [18]
    assert result['subprocess_categories'] == ['permission_denied', 'assertion_failed']
    expected = 'EFFECTIVE_DEVICE_ALLOW' if 'EFFECTIVE_DEVICE_ALLOW' in error else (
        'SUBPROCESS_FAILED' if 'command failed' in error else 'PRIVATE_REVIEW_REQUIRED')
    assert result['failure_code'] == expected


@pytest.mark.parametrize('changed', [False, True])
def test_diagnostic_update_exact_baseline_and_status_only(tmp_path, monkeypatch, changed):
    u = load('update_diagnostics')
    package = tmp_path / 'package'
    package.mkdir()
    target = tmp_path / 'installed.py'
    target.write_bytes(b'original helper')
    lock = tmp_path / 'operation.lock'
    lock.touch()
    candidate = b'def diagnostic():\n return {"access_version":1,"recovery":{}}\n'
    (package / 'maintenance.py').write_bytes(candidate)
    (package / 'update_diagnostics.py').write_bytes(b'installer')
    (package / 'manifest.json').write_text(json.dumps({'files': {
        name: u.sha((package / name).read_bytes()) for name in ('maintenance.py', 'update_diagnostics.py')}}))
    monkeypatch.setattr(u, 'HERE', package)
    monkeypatch.setattr(u, 'TARGET', target)
    monkeypatch.setattr(u, 'OLD', u.sha(b'original helper'))
    monkeypatch.setattr(u, 'secure', lambda p: None)
    monkeypatch.setattr(u.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(u.sys, 'argv', ['update_diagnostics.py'])
    monkeypatch.setattr(u, 'Path', lambda p: lock if p == '/var/lib/freeze-protect-maintenance/operation.lock' else Path(p))
    make = u.tempfile.mkdtemp
    monkeypatch.setattr(u.tempfile, 'mkdtemp', lambda **kw: make(prefix=kw['prefix'], dir=tmp_path))
    commands = []
    def run(args, **kw):
        commands.append(args)
        assert args == ['/usr/local/sbin/freeze-protect-maintenance', 'status']
        return SimpleNamespace(returncode=0, stdout=b'{"access_version":1,"recovery":{}}')
    monkeypatch.setattr(u.subprocess, 'run', run)
    if changed:
        target.write_bytes(b'changed helper')
        with pytest.raises(RuntimeError):
            u.main()
        assert target.read_bytes() == b'changed helper'
        assert commands == [] and not list(tmp_path.glob('freeze-diagnostic-update.*'))
    else:
        u.main()
        assert target.read_bytes() == candidate
        backups = list(tmp_path.glob('freeze-diagnostic-update.*'))
        assert len(backups) == 1
        assert (backups[0] / 'maintenance-before.py').read_bytes() == b'original helper'
        assert (backups[0] / 'SUCCESS.json').exists()
