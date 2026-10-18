"""Root-console status-only helper upgrade; no permissions or service changes."""
import fcntl
import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TARGET = Path('/usr/local/lib/freeze-protect-maintenance-v1/maintenance.py')
OLD = '9db99b22e1f332289cbe8a9305f033e86bfe46da09f5058c8d13d3b6981339eb'


def require(value):
    if not value:
        raise RuntimeError('DIAGNOSTIC_UPDATE_CHECK_FAILED')


def secure(path):
    for item in (path, *path.parents):
        info = item.lstat()
        require(not stat.S_ISLNK(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
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


def main():
    require(os.geteuid() == 0 and len(sys.argv) == 1)
    os.umask(0o077)
    secure(HERE)
    secure(HERE / 'manifest.json')
    manifest = json.loads((HERE / 'manifest.json').read_bytes())
    require(set(manifest) == {'files'} and set(manifest['files']) == {'maintenance.py', 'update_diagnostics.py'})
    for name, digest in manifest['files'].items():
        secure(HERE / name)
        require(sha((HERE / name).read_bytes()) == digest)
    secure(TARGET)
    require(sha(TARGET.read_bytes()) == OLD)
    lock = Path('/var/lib/freeze-protect-maintenance/operation.lock')
    secure(lock)
    fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        candidate = (HERE / 'maintenance.py').read_bytes()
        compile(candidate, 'maintenance.py', 'exec')
        backup = Path(tempfile.mkdtemp(prefix='freeze-diagnostic-update.', dir='/root'))
        sync(backup.parent)
        save(backup / 'maintenance-before.py', TARGET.read_bytes())
        print('DIAGNOSTIC_BACKUP=' + str(backup), flush=True)
        # Evaluate the new read-only diagnostic before replacing its entrypoint.
        spec = importlib.util.spec_from_file_location('diagnostic_candidate', HERE / 'maintenance.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        preview = module.diagnostic()
        require(preview.get('access_version') == 1 and 'recovery' in preview)
        temporary_fd, temporary = tempfile.mkstemp(prefix='.diagnostic-', dir=TARGET.parent)
        try:
            with os.fdopen(temporary_fd, 'wb') as stream:
                stream.write(candidate)
                os.fchmod(stream.fileno(), stat.S_IMODE(TARGET.stat().st_mode))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, TARGET)
            sync(TARGET.parent)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        require(TARGET.read_bytes() == candidate)
        result = subprocess.run(['/usr/local/sbin/freeze-protect-maintenance', 'status'],
                                capture_output=True, timeout=30, check=False,
                                env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C'}, cwd='/')
        require(result.returncode == 0)
        parsed = json.loads(result.stdout)
        require(parsed.get('access_version') == 1 and 'recovery' in parsed)
        save(backup / 'SUCCESS.json', json.dumps({'before': OLD, 'after': sha(candidate)}).encode())
        print('DIAGNOSTIC_UPDATE_VERIFIED', flush=True)
        print(json.dumps(parsed, sort_keys=True), flush=True)
    finally:
        os.close(fd)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - redact unexpected failures at console boundary
        print('DIAGNOSTIC_UPDATE_STOPPED type=' + type(exc).__name__)
        sys.exit(1)
