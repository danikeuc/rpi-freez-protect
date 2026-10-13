"""Fixed trusted-console checks; subprocess output stays in private evidence."""
# ruff: noqa: BLE001, S110
# Private logging failures must not prevent safety cleanup.
import hashlib
import json
import os
import re
import shlex
import sqlite3
import stat
import subprocess
import urllib.request
from contextlib import closing
from pathlib import Path

REPO = Path('/opt/rpi-freez-protect')
VENV = REPO / '.venv'
ENV = Path('/etc/rpi-freeze-protect/environment')
DB = Path('/var/lib/rpi-freeze-protect/freeze-protect.db')
UNIT = Path('/etc/systemd/system/freeze-protect.service')
HUB = 'freeze-protect.service'
PAIR = 'freeze-protect-pair-gpio.service'
SERVICES = (HUB, PAIR, 'node-red.service', 'nginx.service')
LOG = None
CLIENT = Path(__file__).parent / 'paired_gpio_client.py'
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

def run(args, timeout=30, ok=(0,), child_umask=-1, input_data=None):
    result = subprocess.run(args, check=False, capture_output=True, input=input_data, timeout=timeout, cwd='/', umask=child_umask,
                            env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C', 'HOME': '/root', 'GIT_TERMINAL_PROMPT': '0', 'PIP_CONFIG_FILE': '/dev/null',
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

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RuntimeError('unexpected redirect rejected')

def flow():
    # Deployed flow preflight may print tokens: command output goes only to private log.
    run(['sudo', '-u', 'nodered', 'node', str(REPO / 'deployment/node-red/preflight-no-legacy-gpio.js'),
         '/mnt/dietpi_userdata/node-red/flows.json'], timeout=20)

def venv_info():
    code = "import importlib.metadata as m,json; print(json.dumps({d.metadata['Name'].lower().replace('_','-'):d.version for d in m.distributions()}))"
    return json.loads(run([str(VENV / 'bin/python'), '-I', '-c', code]))


def config():
    secure(ENV)
    require(not ENV.stat().st_mode & 0o007, "ENV_WORLD_READABLE")
    entries = {}
    for line in ENV.read_text().splitlines():
        parts = shlex.split(line, comments=True)
        if not parts:
            continue
        require(len(parts) == 1 and "=" in parts[0], "ENV_SYNTAX")
        key, value = parts[0].split("=", 1)
        require(key not in entries, "DUPLICATE_ENV_KEY")
        entries[key] = value
    require(entries.get("FREEZE_PROTECT_CONTROL_MODE") == "weather_assisted", "WRONG_MODE")
    require(entries.get("FREEZE_PROTECT_DB_PATH") == str(DB), "WRONG_DB")
    require(entries.get("FREEZE_PROTECT_DEVELOPMENT_MODE", "").lower()
            not in ("1", "true", "yes", "on"), "DEVELOPMENT_MODE")
    require(bool(entries.get("FREEZE_PROTECT_DISPLAY_TOKEN")), "MISSING_DISPLAY_TOKEN")
    return entries

def persistent_stop():
    require(DB.is_file() and not DB.is_symlink(), "DB_INVALID")
    sentinel = DB.with_name(DB.name + ".weather-identity")
    require(sentinel.is_file() and not sentinel.is_symlink(), "IDENTITY_INVALID")
    with closing(sqlite3.connect(DB.as_uri() + "?mode=ro", uri=True, timeout=3)) as db:
        require(db.execute("PRAGMA quick_check").fetchone() == ("ok",), "DB_INTEGRITY")
        require(db.execute("SELECT version, store_identity FROM weather_metadata WHERE singleton=1").fetchone()
                == ("1", sentinel.read_text("ascii")), "IDENTITY_MISMATCH")
        row = db.execute("SELECT payload_json FROM weather_control WHERE singleton=1").fetchone()
    record = json.loads(row[0]) if row else {}
    require(record.get("user_off") is True and record.get("active_marker") is None
            and record.get("fault_inhibited") is False, "DURABLE_STOP_REQUIRED")
    return record["settings"]


def validate_status(result):
    require(isinstance(result, dict), 'INVALID_STATUS')
    require(result.get('mode') == 'weather_assisted'
            and result.get('operation') == 'USER_OFF'
            and result.get('state') == 'MANUAL_DRAIN'
            and result.get('command') == 'DRAIN'
            and type(result.get('remaining_seconds')) is int
            and result['remaining_seconds'] == 0, 'USER_OFF_REQUIRED')
    return result


def status(entries):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    results = []
    for port in (8000, 8081):
        req = urllib.request.Request(
            f'http://127.0.0.1:{port}/api/v1/display/status',
            headers={'X-Display-Token': entries['FREEZE_PROTECT_DISPLAY_TOKEN']})
        with opener.open(req, timeout=5) as response:
            require(response.status == 200 and response.geturl() == req.full_url, 'HTTP_REJECTED')
            raw = response.read(32769)
        require(len(raw) <= 32768, 'OVERSIZE_STATUS')
        results.append(validate_status(json.loads(raw)))
    return results[0]


def drain():
    global DRAIN_OR_READBACK_FAILED
    require(not DRAIN_OR_READBACK_FAILED, 'PRIOR_RECEIPT_FAILURE')
    try:
        value = json.loads(run(['/usr/bin/python3', '-I', str(CLIENT), 'DRAIN'], timeout=5))
        require(isinstance(value, dict) and value.get('ok') is True
                and type(value.get('protocol_version')) is int
                and value['protocol_version'] == 2 and value.get('command') == 'DRAIN'
                and value.get('supply_action') is None, 'DRAIN_RECEIPT')
        gpio = value.get('gpio')
        require(isinstance(gpio, dict) and all(type(gpio.get(pin)) is int
                and gpio[pin] == 1 for pin in ('26', '20')), 'DRAIN_READBACK')
        pair_high()
    except BaseException:
        DRAIN_OR_READBACK_FAILED = True
        raise


def database_snapshot():
    """Preserve every existing durable row except runtime weather-control bookkeeping."""
    persistent_stop()
    with closing(sqlite3.connect(DB.as_uri() + '?mode=ro', uri=True, timeout=3)) as db:
        tables = db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        result = {}
        for (name,) in tables:
            if name == 'weather_control':
                continue
            require(re.fullmatch('[A-Za-z_][A-Za-z_0-9]*', name), 'UNKNOWN_TABLE_NAME')
            rows = db.execute('SELECT * FROM "' + name + '"').fetchall()
            result[name] = sorted(repr(row) for row in rows)
    return result


def history_preserved(before):
    after = database_snapshot()
    require(set(before) == set(after), 'DATABASE_SCHEMA_CHANGED')
    for name, rows in before.items():
        # New audit/status history rows are allowed; existing rows cannot disappear or change.
        require(all(after[name].count(row) >= rows.count(row) for row in set(rows)), 'DATABASE_HISTORY_CHANGED')
