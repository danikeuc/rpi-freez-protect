"""Trusted local Pi console installer; no remote shell or SUPPLY commands."""
# ruff: noqa: BLE001, S110, SIM117
# Cleanup must attempt stop/DRAIN even for interrupts; no automatic restoration.
import fcntl
import hashlib
import json
import os
import shlex
import sqlite3
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from contextlib import closing
from pathlib import Path

import operator_checks as c

HERE = Path(__file__).resolve().parent
NGINX = Path('/etc/nginx/sites-available/freeze-protect-display.conf')
DAEMON = c.REPO / 'deployment/node-red/paired_gpio_daemon.py'
DAEMON_SHA = '33088ea9e6ccf8d327e226bab1602c6a2b3ba2423de7dcab408b1d06f2233d2f'
WHEEL = HERE / 'rpi_freeze_protect-1.3.0-py3-none-any.whl'
require = c.require

def config():
    c.secure(c.ENV)
    require(not c.ENV.stat().st_mode & 0o007, "ENV_WORLD_READABLE")
    entries = {}
    for line in c.ENV.read_text().splitlines():
        parts = shlex.split(line, comments=True)
        if not parts:
            continue
        require(len(parts) == 1 and "=" in parts[0], "ENV_SYNTAX")
        key, value = parts[0].split("=", 1)
        require(key not in entries, "DUPLICATE_ENV_KEY")
        entries[key] = value
    require(entries.get("FREEZE_PROTECT_CONTROL_MODE") == "weather_assisted", "WRONG_MODE")
    require(entries.get("FREEZE_PROTECT_DB_PATH") == str(c.DB), "WRONG_DB")
    require(entries.get("FREEZE_PROTECT_DEVELOPMENT_MODE", "").lower()
            not in ("1", "true", "yes", "on"), "DEVELOPMENT_MODE")
    require(bool(entries.get("FREEZE_PROTECT_DISPLAY_TOKEN")), "MISSING_DISPLAY_TOKEN")
    return entries

def status(entries):
    req = urllib.request.Request(
        "http://127.0.0.1:8000/api/v1/display/status",
        headers={"X-Display-Token": entries["FREEZE_PROTECT_DISPLAY_TOKEN"]},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), c.NoRedirect())
    with opener.open(req, timeout=8) as response:
        require(response.status == 200 and response.geturl() == req.full_url, "HTTP_REJECTED")
        raw = response.read(32769)
    require(len(raw) <= 32768, "OVERSIZE_STATUS")
    result = json.loads(raw)
    require(isinstance(result, dict), "INVALID_STATUS")
    require(result.get("mode") == "weather_assisted"
            and result.get("operation") == "USER_OFF"
            and result.get("state") == "MANUAL_DRAIN"
            and result.get("command") == "DRAIN"
            and type(result.get("remaining_seconds")) is int
            and result["remaining_seconds"] == 0, "USER_OFF_REQUIRED")
    return result

def persistent_stop():
    require(c.DB.is_file() and not c.DB.is_symlink(), "DB_INVALID")
    sentinel = c.DB.with_name(c.DB.name + ".weather-identity")
    require(sentinel.is_file() and not sentinel.is_symlink(), "IDENTITY_INVALID")
    with closing(sqlite3.connect(c.DB.as_uri() + "?mode=ro", uri=True, timeout=3)) as db:
        require(db.execute("PRAGMA quick_check").fetchone() == ("ok",), "DB_INTEGRITY")
        require(db.execute("SELECT version, store_identity FROM weather_metadata WHERE singleton=1").fetchone()
                == ("1", sentinel.read_text("ascii")), "IDENTITY_MISMATCH")
        row = db.execute("SELECT payload_json FROM weather_control WHERE singleton=1").fetchone()
    record = json.loads(row[0]) if row else {}
    require(record.get("user_off") is True and record.get("active_marker") is None
            and record.get("fault_inhibited") is False, "DURABLE_STOP_REQUIRED")
    return record["settings"]

def history(entries, port):
    request = urllib.request.Request(
        f'http://127.0.0.1:{port}/api/v1/display/history?offset=0',
        headers={'X-Weather-Settings-Token': entries['FREEZE_PROTECT_WEATHER_SETTINGS_TOKEN']},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), c.NoRedirect())
    with opener.open(request, timeout=8) as response:
        raw = response.read(4097)
        require(response.status == 200 and len(raw) <= 4096, 'HISTORY_RESPONSE')
    result = json.loads(raw)
    require(result.get('offset') == 0 and isinstance(result.get('items'), list)
            and bool(result['items']) and len(result['items']) <= 10, 'HISTORY_NOT_READY')
    require(result['items'][0]['operation'] == 'USER_OFF'
            and result['items'][0]['command'] == 'DRAIN', 'HISTORY_CURRENT_STATE')
    return len(result['items'])


def verify_package():
    manifest = json.loads((HERE / 'manifest.json').read_text())
    require(manifest['version'] == '1.3.0', 'PACKAGE_VERSION')
    for name, digest in manifest['files'].items():
        require(Path(name).name == name, 'MANIFEST_PATH')
        c.secure(HERE / name)
        require(c.digest(HERE / name) == digest, 'PACKAGE_HASH')
    return manifest


def archive_backup(directory):
    # Hub is stopped before this coherent software/database backup.
    paths = [c.VENV, c.ENV, c.UNIT, NGINX]
    with tarfile.open(directory / 'software-before.tar.gz', 'x:gz') as archive:
        for path in paths:
            archive.add(path, arcname=str(path).lstrip('/'), recursive=True)
    with tarfile.open(directory / 'software-before.tar.gz') as archive:
        for member in archive:
            if member.isfile():
                source = Path('/') / member.name
                stream = archive.extractfile(member)
                require(stream is not None and hashlib.sha256(stream.read()).hexdigest()
                        == c.digest(source), 'BACKUP_READBACK')
    sentinel = c.DB.with_name(c.DB.name + '.weather-identity')
    c.durable(directory / 'database.weather-identity', sentinel.read_text('ascii'))
    with closing(sqlite3.connect(c.DB.as_uri() + '?mode=ro', uri=True)) as source:
        with closing(sqlite3.connect(directory / 'database.sqlite3')) as target:
            source.backup(target)
            require(target.execute('PRAGMA quick_check').fetchone() == ('ok',), 'BACKUP_DB')
    for name in ('software-before.tar.gz', 'database.sqlite3'):
        with (directory / name).open('rb') as stream:
            os.fsync(stream.fileno())
    c.durable(directory / 'BACKUP_COMPLETE', json.dumps({
        'software_sha256': c.digest(directory / 'software-before.tar.gz'),
        'database_sha256': c.digest(directory / 'database.sqlite3'),
        'git_head': c.git('rev-parse', 'HEAD'),
    }) + '\n')


def main():
    require(os.geteuid() == 0, 'ROOT_LOCAL_CONSOLE_REQUIRED')
    require(sys.argv[1:] == ['--valves-disconnected'], 'PHYSICAL_CONFIRMATION_REQUIRED')
    os.umask(0o077)
    c.secure(HERE, private=True)
    package = verify_package()
    require(b'Raspberry Pi' in Path('/proc/device-tree/model').read_bytes(), 'WRONG_HOST')
    with Path('/root/.shower-history-install.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        directory = Path(tempfile.mkdtemp(prefix='freeze-before-history-', dir='/root'))
        parent_fd = os.open(directory.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
        install(package, directory)


def install(package, directory):
    c.LOG = directory / 'private.log'
    stopped = False
    installed = False
    try:
        c.secure(c.REPO); c.secure(c.VENV); c.secure(c.UNIT); c.secure(NGINX); c.secure(DAEMON)
        require(c.digest(DAEMON) == DAEMON_SHA, 'P1_DAEMON_REQUIRED')
        require(all(c.active(s) for s in c.SERVICES) and not c.active('nodered.service'), 'SERVICE_PREFLIGHT')
        entries = config()
        require(bool(entries.get('FREEZE_PROTECT_WEATHER_SETTINGS_TOKEN')), 'WEATHER_CREDENTIAL_REQUIRED')
        status(entries); before_settings = persistent_stop(); c.pair_high(); c.flow()
        c.run(['nginx', '-t'])
        before_env = c.digest(c.ENV)
        before_packages = c.venv_info()
        require(before_packages.get('rpi-freeze-protect') != '1.3.0', 'ALREADY_INSTALLED')
        stopped = True  # Stop may take effect even when the command reply fails.
        c.run(['systemctl', 'stop', c.HUB])
        c.stopped(); c.drain()
        archive_backup(directory)
        c.durable(directory / 'INSTALL_STARTED', 'verified backup before package update\n')
        installed = True
        c.run([str(c.VENV / 'bin/python'), '-m', 'pip', 'install', '--no-index', '--no-deps',
               '--force-reinstall', str(WHEEL)], timeout=120, child_umask=0o022)
        c.run([str(c.VENV / 'bin/python'), '-m', 'pip', 'check'])
        c.installed_bytes(WHEEL)
        c.service_readable()
        after_packages = c.venv_info()
        expected = dict(before_packages); expected['rpi-freeze-protect'] = '1.3.0'
        require(after_packages == expected, 'DEPENDENCY_SET_CHANGED')
        c.replace_file(HERE / 'freeze-protect-display.conf', NGINX)
        c.run(['nginx', '-t']); c.run(['systemctl', 'reload', 'nginx.service'])
        require(c.digest(c.ENV) == before_env and persistent_stop() == before_settings, 'SETTINGS_CHANGED')
        c.pair_high(); c.run(['systemctl', 'start', c.HUB])
        deadline = time.monotonic() + 30
        while True:
            try:
                status(entries)
                break
            except urllib.error.HTTPError:
                raise RuntimeError('HUB_HTTP_REJECTED') from None
            except (urllib.error.URLError, OSError):
                require(time.monotonic() < deadline, 'HUB_READINESS_TIMEOUT')
                time.sleep(.5)
        require(all(c.active(s) for s in c.SERVICES), 'SERVICES_NOT_ACTIVE')
        require(persistent_stop() == before_settings, 'DURABLE_SETTINGS_CHANGED')
        require(c.digest(c.ENV) == before_env and c.digest(DAEMON) == DAEMON_SHA, 'PRESERVED_FILES_CHANGED')
        c.pair_high()
        counts = [history(entries, port) for port in (8000, 8081)]
        receipt = {'version':'1.3.0', 'source_commit':package['source_commit'],
                   'wheel_sha256':c.digest(WHEEL), 'history_rows':counts,
                   'command':'DRAIN', 'operation':'USER_OFF', 'gpio26':'high', 'gpio20':'high',
                   'backup':str(directory), 'repo_head_preserved':c.git('rev-parse', 'HEAD')}
        c.durable(directory / 'SUCCESS.json', json.dumps(receipt) + '\n')
        print('HISTORY_INSTALLED; ' + json.dumps(receipt))
    except BaseException as error:
        if stopped:
            try:
                c.run(['systemctl', 'stop', c.HUB]); c.stopped()
                if not c.DRAIN_OR_READBACK_FAILED: c.drain()
            except BaseException:
                pass
        c.durable(directory / 'STOP.json', json.dumps({'error_type':type(error).__name__,
                  'hub_stop_requested':stopped, 'install_started':installed}) + '\n')
        print('HISTORY_INSTALL_STOPPED; backup=' + str(directory) + '; type=' + type(error).__name__)
        if isinstance(error, RuntimeError):
            text = str(error)
            if text.replace('_', '').isalnum() and text.isupper(): print('CODE=' + text)
        print('Keep24V disconnected. No automatic rollback; inspect private evidence.')
        raise SystemExit(1) from None

if __name__ == '__main__':
    main()
