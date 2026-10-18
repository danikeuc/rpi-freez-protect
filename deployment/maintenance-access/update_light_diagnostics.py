"""Root-console, status-only GPIO21 evidence-reader update."""
import fcntl
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TARGET = Path('/usr/local/lib/freeze-protect-maintenance-v1/maintenance.py')
LOCK = Path('/var/lib/freeze-protect-maintenance/operation.lock')
MODEL = Path('/proc/device-tree/model')
BACKUP_ROOT = Path('/root')
OLD = 'df06b46bd206dbadbbbd201aeb80529df9deb790b7df448b29e1ff2ba15c6a9c'


def require(value):
    if not value:
        raise RuntimeError('LIGHT_DIAGNOSTIC_UPDATE_CHECK_FAILED')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def secure(path):
    for part in (path, *path.parents):
        info = part.lstat()
        require(not stat.S_ISLNK(info.st_mode) and info.st_uid == 0
                and not info.st_mode & 0o022)
    require(path.is_file() or path.is_dir())


def sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def save(path, data):
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    sync(path.parent)


def preview(candidate):
    namespace = {"__name__": "light_diagnostic_candidate", "__file__": str(HERE / "maintenance.py")}
    exec(compile(candidate, str(HERE / "maintenance.py"), "exec"), namespace)  # noqa: S102 - root-controlled, hash-verified snapshot
    return namespace['diagnostic']()


def validate_status(value, expected_helper_hash):
    require(isinstance(value, dict) and value.get('access_version') == 1
            and isinstance(value.get('light_gpio21_bench'), dict))
    require(value.get('package_sha256') ==
            'f4c87e6439650f80c02b2d1b17c76661c5e3d74bbf7c672eab28edadc9883513')
    require(isinstance(value.get('jobs'), list))
    for key in ('recovery', 'hub_recovery', 'units', 'artifacts'):
        require(isinstance(value.get(key), dict))
    for unit in ('freeze-protect.service', 'freeze-protect-pair-gpio.service',
                 'node-red.service', 'freeze-protect-maintenance-prepare.service',
                 'freeze-protect-maintenance-install.service'):
        require(isinstance(value['units'].get(unit), dict))
    for path in (
        '/etc/systemd/system/freeze-protect.service',
        '/etc/systemd/system/freeze-protect.service.d/30-node-red-readiness.conf',
        '/etc/systemd/system/freeze-protect-pair-gpio.service',
        '/etc/systemd/system/freeze-protect-pair-gpio.service.d/40-paired-gpio.conf',
        '/opt/rpi-freez-protect/deployment/node-red/paired_gpio_daemon.py',
    ):
        require(isinstance(value['artifacts'].get(path), dict))
    require(value['artifacts'].get(str(TARGET), {}).get('sha256') == expected_helper_hash)


def install():
    require(os.geteuid() == 0)
    require(MODEL.read_bytes().rstrip(b'\0\n') == b'Raspberry Pi 4 Model B Rev 1.1')
    os.umask(0o077)
    for path in (HERE, HERE / 'manifest.json', TARGET, LOCK, BACKUP_ROOT):
        secure(path)
    require((HERE / 'manifest.json').stat().st_size <= 32768)
    manifest = json.loads((HERE / 'manifest.json').read_bytes())
    names = {'maintenance.py', 'update_light_diagnostics.py'}
    require(set(manifest) == {'files'} and set(manifest['files']) == names)
    snapshots = {}
    for name in names:
        path = HERE / name
        secure(path)
        require(path.is_file() and path.stat().st_size <= 262144)
        snapshots[name] = path.read_bytes()
        require(sha(snapshots[name]) == manifest['files'][name])
    candidate = snapshots['maintenance.py']
    compile(candidate, 'maintenance.py', 'exec')
    require(TARGET.is_file() and TARGET.stat().st_size <= 262144)
    fd = os.open(LOCK, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
    backup, changed, phase = None, False, 'preflight'
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode))
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        original = TARGET.read_bytes()
        require(sha(original) == OLD)
        metadata = TARGET.stat()
        phase = 'preview'
        validate_status(preview(candidate), OLD)
        # Detect out-of-band changes before preparing a replacement.
        secure(TARGET)
        require(TARGET.read_bytes() == original)
        backup = Path(tempfile.mkdtemp(prefix='freeze-light-diagnostics.', dir=BACKUP_ROOT))
        sync(BACKUP_ROOT)
        save(backup / 'maintenance-before.py', original)
        save(backup / 'STARTED.json', json.dumps({
            'before': OLD, 'after': sha(candidate),
            'target': str(TARGET), 'mode': stat.S_IMODE(metadata.st_mode),
            'uid': metadata.st_uid, 'gid': metadata.st_gid
        }).encode())
        print('DIAGNOSTIC_BACKUP=' + str(backup), flush=True)
        phase = 'replace'
        temporary_fd, temporary = tempfile.mkstemp(prefix='.light-diagnostic-', dir=TARGET.parent)
        try:
            with os.fdopen(temporary_fd, 'wb') as stream:
                stream.write(candidate)
                os.fchown(stream.fileno(), metadata.st_uid, metadata.st_gid)
                os.fchmod(stream.fileno(), stat.S_IMODE(metadata.st_mode))
                stream.flush()
                os.fsync(stream.fileno())
            secure(TARGET)
            require(TARGET.read_bytes() == original)
            os.replace(temporary, TARGET)
            changed = True
            sync(TARGET.parent)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        require(TARGET.read_bytes() == candidate)
        phase = 'postcheck'
        response = subprocess.run(
            ['/usr/local/sbin/freeze-protect-maintenance', 'status'],
            capture_output=True, timeout=30, check=False, stdin=subprocess.DEVNULL,
            env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C',
                 'PYTHONDONTWRITEBYTECODE': '1'}, cwd='/')
        require(response.returncode == 0 and len(response.stdout) <= 131072)
        public = json.loads(response.stdout)
        validate_status(public, sha(candidate))
        require(public.get('artifacts', {}).get(str(TARGET), {}).get('sha256') == sha(candidate))
        result = {'changed': True, 'backup': str(backup),
                  'before_sha256': OLD, 'helper_sha256': sha(candidate),
                  'gpio_commands_issued': False, 'remote_acceptance': 'PENDING'}
        save(backup / 'SUCCESS.json', json.dumps(result).encode())
        return result
    except BaseException:
        if backup is not None:
            save(backup / 'STOPPED.json', json.dumps({
                'changed': changed, 'phase': phase, 'automatic_rollback': False
            }).encode())
        raise
    finally:
        os.close(fd)


def main():
    require(len(sys.argv) == 1)
    result = install()
    print('LIGHT_DIAGNOSTICS_UPDATED; ' + json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except Exception:  # noqa: BLE001 - never export private exception payloads
        print('LIGHT_DIAGNOSTICS_UPDATE_STOPPED; inspect backup if printed; no automatic retry')
        sys.exit(1)
