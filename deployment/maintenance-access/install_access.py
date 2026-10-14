"""One trusted-console installation; extends only three exact remote commands."""
import hashlib
import importlib.util
import json
import os
import pwd
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DISPATCH = Path('/usr/local/lib/freeze-protect-commission/ssh-dispatch')
SUDO = Path('/etc/sudoers.d/freeze-protect-maintenance')
LAUNCHER = Path('/usr/local/sbin/freeze-protect-maintenance')
BASE = Path('/usr/local/lib/freeze-protect-maintenance-v1')
STATE = Path('/var/lib/freeze-protect-maintenance')
ORIGINALS = {
    'original-dispatch': DISPATCH,
    'original-sudoers': Path('/etc/sudoers.d/freeze-protect-commission'),
    'original-helper': Path('/usr/local/sbin/freeze-protect-commission'),
}
SUDO_BYTES = b'''Cmnd_Alias FREEZE_PROTECT_MAINTENANCE = \
  /usr/local/sbin/freeze-protect-maintenance status, \
  /usr/local/sbin/freeze-protect-maintenance prepare, \
  /usr/local/sbin/freeze-protect-maintenance install
freezeprotect-commission ALL=(root) NOPASSWD: FREEZE_PROTECT_MAINTENANCE
'''
LAUNCHER_BYTES = b'''#!/bin/sh
set -eu
exec /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin /usr/bin/python3 -I -B /usr/local/lib/freeze-protect-maintenance-v1/maintenance.py "$@"
'''


def require(value, code):
    if not value:
        raise RuntimeError(code)


def secure(path):
    for item in (path, *path.parents):
        info = item.lstat()
        require(not stat.S_ISLNK(info.st_mode) and info.st_uid == 0
                and not info.st_mode & 0o022, 'UNTRUSTED_PATH')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def sync(directory):
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write(path, data, mode):
    secure(path.parent)
    require(not path.is_symlink(), 'SYMLINK_DESTINATION')
    fd, temporary = tempfile.mkstemp(prefix='.maintenance-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            os.fchmod(stream.fileno(), mode)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync(path.parent)
        require(path.read_bytes() == data, 'WRITE_READBACK')
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def extended_dispatch(original):
    anchor = b'  *)\n'
    require(original.count(anchor) == 1, 'DISPATCH_LAYOUT')
    additions = b''
    for command in ('status', 'prepare', 'install'):
        exact = 'sudo -n /usr/local/sbin/freeze-protect-maintenance ' + command
        additions += ('  "' + exact + '")\n    exec /usr/bin/' + exact + '\n    ;;\n').encode()
    return original.replace(anchor, additions + anchor)


CHECK_NAMES = frozenset({'SSHD_SYNTAX', 'SUDOERS_SYNTAX', 'SSHD_EFFECTIVE',
                         'SYSTEMD_RUN', 'DISPATCH_SYNTAX', 'SUDOERS_CANDIDATE',
                         'MAINTENANCE_STATUS'})
CHECK_REASON_PATTERNS = {
    'missing_privsep': b'Missing privilege separation directory',
    'syntax_error': b'syntax error',
    'bad_permissions': b'bad permissions',
    'bad_owner': b'bad ownership',
    'bad_option': b'Bad configuration option',
    'host_keys': b'no hostkeys available',
    'permission_denied': b'Permission denied',
}


def check_name(args):
    if args == ['/usr/sbin/sshd', '-t']:
        return 'SSHD_SYNTAX'
    if args == ['/usr/sbin/visudo', '-c']:
        return 'SUDOERS_SYNTAX'
    if args[:2] == ['/usr/sbin/sshd', '-T']:
        return 'SSHD_EFFECTIVE'
    if args == ['/usr/bin/systemd-run', '--version']:
        return 'SYSTEMD_RUN'
    if args[:2] == ['/bin/sh', '-n']:
        return 'DISPATCH_SYNTAX'
    if args[:2] == ['/usr/sbin/visudo', '-cf']:
        return 'SUDOERS_CANDIDATE'
    if args == [str(LAUNCHER), 'status']:
        return 'MAINTENANCE_STATUS'
    raise RuntimeError('UNKNOWN_CONFIGURATION_CHECK')


def call(args):
    name = check_name(args)
    try:
        r = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, timeout=15, check=False,
                           env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C'}, cwd='/')
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({'check': name, 'error_type': type(exc).__name__}), flush=True)
        raise RuntimeError('CHECK_FAILED_' + name) from None
    if r.returncode != 0:
        output = (r.stdout + r.stderr).lower()
        reasons = [key for key, value in CHECK_REASON_PATTERNS.items() if value.lower() in output]
        print(json.dumps({'check': name, 'exit': r.returncode, 'reasons': reasons}), flush=True)
        raise RuntimeError('CHECK_FAILED_' + name)
    return r.stdout


def validate_manifest():
    secure(HERE)
    secure(HERE / 'manifest.json')
    value = json.loads((HERE / 'manifest.json').read_text())
    expected = {'maintenance.py', 'install_access.py', 'migration.tar.gz',
                'original-dispatch', 'original-helper', 'original-sudoers', 'README.md'}
    require(set(value) == {'files'} and set(value['files']) == expected, 'MANIFEST_FILES')
    for name, identity in value['files'].items():
        secure(HERE / name)
        require((HERE / name).is_file() and sha((HERE / name).read_bytes()) == identity, 'MANIFEST_HASH')


def main():
    require(os.geteuid() == 0 and sys.argv[1:] == ['--loads-disconnected'], 'ROOT_AND_LOAD_CONFIRMATION_REQUIRED')
    os.umask(0o077)
    require(Path('/proc/device-tree/model').read_bytes().rstrip(b'\0') ==
            b'Raspberry Pi 4 Model B Rev 1.1', 'WRONG_HOST')
    validate_manifest()
    for target in (BASE, STATE, SUDO, LAUNCHER):
        require(not target.exists() and not target.is_symlink(), 'EXISTING_INSTALLATION_REVIEW_REQUIRED')
        secure(target.parent)
    for source, target in ORIGINALS.items():
        secure(target)
        require(target.is_file() and target.read_bytes() == (HERE / source).read_bytes(), 'ORIGINAL_CHANGED')
    account = pwd.getpwnam('freezeprotect-commission')
    require(account.pw_uid != 0, 'ACCOUNT_IDENTITY')
    call(['/usr/sbin/sshd', '-t'])
    call(['/usr/sbin/visudo', '-c'])
    policy = call(['/usr/sbin/sshd', '-T', '-C',
                   'user=freezeprotect-commission,host=localhost,addr=192.168.111.30']).decode().splitlines()
    for setting in ('forcecommand ' + str(DISPATCH), 'passwordauthentication no',
                    'permittty no', 'allowtcpforwarding no'):
        require(setting in policy, 'SSH_POLICY_MISMATCH')
    require(Path('/run/systemd/system').is_dir(), 'SYSTEMD_REQUIRED')
    call(['/usr/bin/systemd-run', '--version'])
    spec = importlib.util.spec_from_file_location('maintenance_installer', HERE / 'maintenance.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    raw = (HERE / 'migration.tar.gz').read_bytes()
    members = m.bundle_members(raw)
    dispatch = extended_dispatch((HERE / 'original-dispatch').read_bytes())
    call(['/bin/sh', '-n', str(HERE / 'original-dispatch')])
    backup = Path(tempfile.mkdtemp(prefix='freeze-maintenance-access.', dir='/root'))
    sync(backup.parent)
    inventory = {}
    for index, target in enumerate(ORIGINALS.values()):
        saved = backup / ('before-' + str(index))
        info = target.stat()
        write(saved, target.read_bytes(), 0o600)
        inventory[str(target)] = {'file': saved.name, 'sha256': sha(saved.read_bytes()),
                                 'mode': stat.S_IMODE(info.st_mode), 'uid': info.st_uid, 'gid': info.st_gid}
    # SSH policy remains untouched. Save effective settings privately for recovery.
    write(backup / 'effective-ssh.txt', '\n'.join(policy).encode(), 0o600)
    write(backup / 'backup.json', json.dumps(inventory, sort_keys=True).encode(), 0o600)
    print('BACKUP_COMPLETE=' + str(backup), flush=True)
    try:
        BASE.mkdir(mode=0o700)
        STATE.mkdir(mode=0o700)
        sync(BASE.parent)
        sync(STATE.parent)
        write(BASE / 'maintenance.py', (HERE / 'maintenance.py').read_bytes(), 0o600)
        write(BASE / 'migration.tar.gz', raw, 0o600)
        package = BASE / 'package'
        package.mkdir(mode=0o700)
        sync(BASE)
        for name, data in members.items():
            write(package / name, data, 0o600)
        write(STATE / 'approval.json', json.dumps({
            'package_sha256': m.PACKAGE_SHA, 'boot_id': m.boot(),
            'loads_disconnected': True, 'expires_monotonic': time.monotonic() + 8 * 3600,
        }).encode(), 0o600)
        write(STATE / 'access-backup.json', json.dumps({'backup': str(backup)}).encode(), 0o600)
        write(LAUNCHER, LAUNCHER_BYTES, 0o755)
        write(backup / 'sudoers.new', SUDO_BYTES, 0o600)
        write(backup / 'dispatch.new', dispatch, 0o600)
        call(['/usr/sbin/visudo', '-cf', str(backup / 'sudoers.new')])
        call(['/bin/sh', '-n', str(backup / 'dispatch.new')])
        write(SUDO, SUDO_BYTES, 0o440)
        call(['/usr/sbin/visudo', '-c'])
        # Dispatcher is the final gate. Existing four command forms remain intact.
        write(DISPATCH, dispatch, stat.S_IMODE(DISPATCH.stat().st_mode))
        call(['/usr/sbin/sshd', '-t'])
        result = json.loads(call([str(LAUNCHER), 'status']))
        require(result.get('access_version') == 1, 'STATUS_FAILED')
        write(backup / 'INSTALLED.json', json.dumps({
            'dispatcher_sha256': sha(dispatch), 'package_sha256': m.PACKAGE_SHA,
            'second_ssh_login': 'PENDING', 'migration': 'NOT_REQUESTED',
        }).encode(), 0o600)
        print('MAINTENANCE_ACCESS_INSTALLED; migration NOT_REQUESTED; second SSH login pending', flush=True)
    except BaseException:
        write(backup / 'STOPPED', b'No automatic retry or rollback; inspect installed paths.\n', 0o600)
        print('ACCESS_INSTALL_STOPPED; backup=' + str(backup), flush=True)
        raise


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - redact all unexpected failures at CLI boundary
        # Only our literal labels are exposed, never subprocess output or exception payloads.
        safe = {'ROOT_AND_LOAD_CONFIRMATION_REQUIRED', 'WRONG_HOST', 'UNTRUSTED_PATH',
                'EXISTING_INSTALLATION_REVIEW_REQUIRED', 'ORIGINAL_CHANGED', 'ACCOUNT_IDENTITY',
                'SSH_POLICY_MISMATCH', 'SYSTEMD_REQUIRED', 'MANIFEST_FILES', 'MANIFEST_HASH',
                'CONFIGURATION_CHECK_FAILED', 'STATUS_FAILED', 'WRITE_READBACK', 'DISPATCH_LAYOUT',
                'UNKNOWN_CONFIGURATION_CHECK'} | {'CHECK_FAILED_' + name for name in CHECK_NAMES}
        code = str(exc) if isinstance(exc, RuntimeError) and str(exc) in safe else 'INSPECT_LOCAL_STATE'
        print('ACCESS_INSTALL_STOPPED code=' + code)
        sys.exit(1)
