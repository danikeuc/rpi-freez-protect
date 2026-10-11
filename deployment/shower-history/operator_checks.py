# ruff: noqa: I001, PLW1510, S110, BLE001
# Preserve these reviewed predecessor helpers verbatim; safety cleanup must survive logging errors.
"""Read-only validation and bounded process helpers from the reviewed 2026-10-03 installer.
Old install/rollback/main entrypoints deliberately excluded. No actions at import.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import sqlite3
import stat
import subprocess
import time
import urllib.request
import urllib.error

REPO = Path('/opt/rpi-freez-protect')
VENV = REPO / '.venv'
ENV = Path('/etc/rpi-freeze-protect/environment')
DB = Path('/var/lib/rpi-freeze-protect/freeze-protect.db')
UNIT = Path('/etc/systemd/system/freeze-protect.service')
HUB = 'freeze-protect.service'
SERVICES = (HUB, 'freeze-protect-pair-gpio.service', 'node-red.service', 'nginx.service')
LOG = None
DRAIN_OR_READBACK_FAILED = False

def require(value, label):
    if not value:
        raise RuntimeError(label)


def secure(path, private=False):
    """Root-controlled fixed inputs, never follow a path through a symlink."""
    path = Path(path)
    for item in (path, *path.parents):
        info = item.lstat()
        require(not stat.S_ISLNK(info.st_mode), 'symlink input requires local review')
        require(info.st_uid == 0 and not info.st_mode & 0o022, 'input ownership/mode requires local review')
    if private:
        require(not path.stat().st_mode & 0o077, 'private evidence permissions required')


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def durable(path, content):
    with Path(path).open('x', encoding='utf-8') as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(Path(path).parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def run(args, timeout=30, ok=(0,), child_umask=-1):
    result = subprocess.run(args, capture_output=True, timeout=timeout, cwd='/', umask=child_umask,
                            env={**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'PIP_CONFIG_FILE': '/dev/null',
                                 'PIP_DISABLE_PIP_VERSION_CHECK': '1', 'PYTHONDONTWRITEBYTECODE': '1'})
    try:
        if LOG:
            with LOG.open('ab') as log:
                log.write(result.stdout + result.stderr)
    except BaseException:
        pass  # Diagnostics must never prevent stop/DRAIN or receipt validation.
    require(result.returncode in ok, 'command failed; private log retained')
    return result.stdout.decode('utf-8', errors='strict').strip()


def git(*args):
    return run(['git', '-C', str(REPO), *args], timeout=60,
               child_umask=0o022 if args and args[0] == 'checkout' else -1)


def active(service):
    return run(['systemctl', 'is-active', service], ok=(0, 3, 4)) == 'active'


def stopped():
    require(not active(HUB), 'Hub still active')
    require(run(['systemctl', 'show', HUB, '--property=MainPID', '--value']) == '0', 'Hub process remains')


def pair_high():
    global DRAIN_OR_READBACK_FAILED
    try:
        for pin in (26, 20):
            value = run(['pinctrl', 'get', str(pin)], timeout=5)
            require(re.fullmatch(rf'{pin}: op [^\n]*\| hi // GPIO{pin} = output\s*', value),
                    'paired output/high readback failed')
    except BaseException:
        DRAIN_OR_READBACK_FAILED = True
        raise


def drain():
    global DRAIN_OR_READBACK_FAILED
    require(not DRAIN_OR_READBACK_FAILED, 'prior failed receipt/readback; no retry')
    try:
        run(['/usr/local/sbin/freeze-protect-commission', 'drain'], timeout=10)
        pair_high()
    except BaseException:
        DRAIN_OR_READBACK_FAILED = True
        raise


def config(live):
    secure(ENV)
    require(not ENV.stat().st_mode & 0o007, 'environment world access rejected')
    entries = {}
    for line in ENV.read_text().splitlines():
        parts = shlex.split(line, comments=True)
        if not parts:
            continue
        require(len(parts) == 1 and '=' in parts[0], 'environment syntax needs local review')
        key, value = parts[0].split('=', 1)
        require(key not in entries, 'duplicate environment key')
        entries[key] = value
    require(entries.get('FREEZE_PROTECT_CONTROL_MODE') == 'manual_timed', 'manual_timed required')
    require(entries.get('FREEZE_PROTECT_DB_PATH') == str(DB), 'unexpected database path')
    require(entries.get('FREEZE_PROTECT_DEVELOPMENT_MODE', '').lower() not in ('1','true','yes','on'),
            'production configuration required')
    require(bool(entries.get('FREEZE_PROTECT_DISPLAY_TOKEN')), 'display credential required')
    if live:
        pid = int(run(['systemctl', 'show', HUB, '--property=MainPID', '--value']))
        require(pid > 0, 'missing Hub process')
        values = dict(item.split(b'=', 1) for item in Path(f'/proc/{pid}/environ').read_bytes().split(b'\0') if b'=' in item)
        keys = {k for k in entries if k.startswith('FREEZE_PROTECT_')} | {
            k.decode() for k in values if k.startswith(b'FREEZE_PROTECT_')}
        require(all(values.get(k.encode()) == (entries[k].encode() if k in entries else None) for k in keys),
                'live process differs from preserved environment')
    return entries


def validate_status(status, candidate):
    require(isinstance(status, dict), 'invalid status object')
    require(status.get('mode') == 'manual_timed' and status.get('state') == 'MANUAL_DRAIN'
            and status.get('command') == 'DRAIN' and status.get('reason') == 'manual_idle'
            and type(status.get('remaining_seconds')) is int and status['remaining_seconds'] == 0,
            'idle manual DRAIN not confirmed')
    require(status.get('timed_shower_duration_supported') is True, 'duration capability missing')
    if candidate:
        require(status.get('weather_assistance_version') == 1 and status.get('operation') == 'MANUAL_IDLE',
                'weather capability/idle operation missing')
        weather = status.get('weather')
        require(isinstance(weather, dict) and weather.get('enabled') is False, 'weather must remain disabled')
        require(type(status.get('control_revision')) is int, 'durable weather state unavailable')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RuntimeError('unexpected redirect rejected')


def status_check(entries, candidate):
    # Credentials stay in memory; no raw body, headers, or nonce are logged.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    for port in (8000, 8081):
        request = urllib.request.Request(f'http://127.0.0.1:{port}/api/v1/display/status',
                                        headers={'X-Display-Token': entries['FREEZE_PROTECT_DISPLAY_TOKEN']})
        with opener.open(request, timeout=5) as response:
            require(response.status == 200 and response.geturl() == request.full_url, 'status response mismatch')
            body = response.read(32769)
        require(len(body) <= 32768, 'oversize status')
        validate_status(json.loads(body), candidate)


def storage(candidate):
    require(DB.is_file() and not DB.is_symlink(), 'database missing or linked')
    sentinel = DB.with_name(DB.name + '.weather-identity')
    connection = sqlite3.connect(DB.as_uri() + '?mode=ro', uri=True, timeout=3)
    try:
        require(connection.execute('PRAGMA quick_check').fetchone() == ('ok',), 'database integrity failed')
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not candidate:
            require(not sentinel.exists() and not {'weather_control', 'weather_metadata', 'weather_action_receipts'} & tables,
                    'unexpected pre-existing weather state; do not reset it')
        else:
            require(sentinel.is_file() and not sentinel.is_symlink(), 'weather identity missing')
            identity = sentinel.read_text('ascii')
            require(re.fullmatch('[0-9a-f]{32}', identity), 'invalid weather identity')
            require(connection.execute('SELECT version, store_identity FROM weather_metadata WHERE singleton=1').fetchone() == ('1', identity),
                    'weather database/identity mismatch')
            row = connection.execute('SELECT payload_json FROM weather_control WHERE singleton=1').fetchone()
            require(row and json.loads(row[0])['settings']['enabled'] is False, 'persisted weather enabled or invalid')
    finally:
        connection.close()


def flow():
    # Deployed flow preflight may print tokens: command output goes only to private log.
    run(['sudo', '-u', 'nodered', 'node', str(REPO / 'deployment/node-red/preflight-no-legacy-gpio.js'),
         '/mnt/dietpi_userdata/node-red/flows.json'], timeout=20)


def ready(candidate):
    # Only connection readiness is retried; a received failed health/state is terminal.
    deadline = time.monotonic() + 30
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    while True:
        try:
            with opener.open('http://127.0.0.1:8000/health', timeout=2) as response:
                body = response.read(4097)
            break
        except urllib.error.HTTPError:
            raise RuntimeError('Hub health HTTP failure') from None
        except (OSError, urllib.error.URLError):
            require(time.monotonic() < deadline, 'Hub readiness timeout')
            time.sleep(0.5)
    health = json.loads(body)
    require(health.get('service') == 'ok' and health.get('state') == 'MANUAL_DRAIN', 'Hub failed idle readiness')
    require(all(active(service) for service in SERVICES), 'service not active')
    status_check(config(live=True), candidate)
    storage(candidate)
    pair_high()


def venv_info():
    code = "import importlib.metadata as m,json; print(json.dumps({d.metadata['Name'].lower().replace('_','-'):d.version for d in m.distributions()}))"
    return json.loads(run([str(VENV / 'bin/python'), '-I', '-c', code]))


def installed_bytes(wheel):
    code = r'''import importlib.util,json,pathlib,sysconfig,zipfile
root=pathlib.Path(sysconfig.get_path('purelib'))
spec=importlib.util.find_spec('freeze_protect')
assert spec and pathlib.Path(spec.origin).parent == root/'freeze_protect'
with zipfile.ZipFile(__import__('sys').argv[1]) as wheel:
    expected={n:wheel.read(n) for n in wheel.namelist() if n.startswith('freeze_protect/') and not n.endswith('/')}
    assert expected
    actual={str(p.relative_to(root)):p.read_bytes() for p in (root/'freeze_protect').rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
    assert actual == expected
    print(json.dumps({'files':len(actual)}))
'''
    return json.loads(run([str(VENV / 'bin/python'), '-I', '-c', code, str(wheel)]))['files']


def installed_source_bytes():
    code = r'''import importlib.util,json,pathlib,sysconfig,sys
root=pathlib.Path(sysconfig.get_path('purelib'))
spec=importlib.util.find_spec('freeze_protect')
assert spec and pathlib.Path(spec.origin).parent == root/'freeze_protect'
source=pathlib.Path(sys.argv[1])
def files(base):
    return {str(p.relative_to(base)):p.read_bytes() for p in base.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
expected=files(source)
assert expected and files(root/'freeze_protect') == expected
print(json.dumps({'files':len(expected)}))
'''
    return json.loads(run([str(VENV / 'bin/python'), '-I', '-c', code, str(REPO / 'src/freeze_protect')]))['files']


def service_readable():
    # Run under the exact unit identity, without importing application main.
    code = r'''import importlib.metadata as m,importlib.util,pathlib,sysconfig
root=pathlib.Path(sysconfig.get_path('purelib'))/'freeze_protect'
spec=importlib.util.find_spec('freeze_protect')
assert spec and pathlib.Path(spec.origin).parent == root
files=[p for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc']
assert files
for path in files:
    path.read_bytes()
metadata=m.distribution('rpi-freeze-protect')
assert metadata.read_text('METADATA') and metadata.read_text('RECORD')
print('service-readable')
'''
    run(['sudo','-u','freezeprotect','--',str(VENV/'bin/python'),'-I','-c',code], timeout=15)


def start_verified(candidate):
    service_readable()
    run(['systemctl','start',HUB], timeout=45)
    ready(candidate)


def replace_file(source, destination):
    info = destination.stat()
    temporary = destination.with_name(destination.name + '.weather-install-new')
    require(not temporary.exists() and not temporary.is_symlink(), 'replacement temp already exists')
    with temporary.open('xb') as stream:
        stream.write(source.read_bytes())
        os.fchmod(stream.fileno(), stat.S_IMODE(info.st_mode))
        os.fchown(stream.fileno(), info.st_uid, info.st_gid)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, destination)
    fd = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
