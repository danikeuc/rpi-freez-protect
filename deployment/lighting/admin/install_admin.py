"""Add a private-LAN Dial gateway and provision existing light roles once.
No GPIO, light actions/settings, camera configuration or service restart.
Run only at the trusted Pi root console after reviewed Dial firmware is installed.
"""
# Percent templates keep nginx braces literal; boundary exceptions redact secrets.
# ruff: noqa: UP031, BLE001
import argparse
import getpass
import hashlib
import http.cookiejar
import json
import os
import re
import socket
import stat
import subprocess
import tempfile
import urllib.error
import urllib.request
import warnings
from pathlib import Path

PI = "192.168.114.192"
DIAL = "192.168.114.173"
BASE = "http://" + PI + ":8082"
ENV = Path("/etc/independent-light/controller.env")
AVAILABLE = Path("/etc/nginx/sites-available/light-dial.conf")
ENABLED = Path("/etc/nginx/sites-enabled/light-dial.conf")
MARKER = Path("/root/light-admin-install.started")
PAIR = Path("/opt/rpi-freez-protect/deployment/node-red/paired_gpio_daemon.py")
PAIR_SHA = "ef96336ec9fd299459adb4bc751aac4ef5bf7f992fb0757886e496851c73b51f"


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def secure(path):
    for item in (path, *path.parents):
        s = item.lstat()
        require(not stat.S_ISLNK(s.st_mode) and s.st_uid == 0
                and not s.st_mode & 0o022, "UNTRUSTED_PATH")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def private(path, value):
    with path.open("x", encoding="utf-8") as f:
        os.fchmod(f.fileno(), 0o600)
        f.write(value)
        f.flush()
        os.fsync(f.fileno())


def run(*args):
    p = subprocess.run(args, capture_output=True, timeout=20, check=False,
                       env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C"})
    require(p.returncode == 0, "COMMAND_FAILED_" + Path(args[0]).name.upper())
    return p.stdout.decode().strip()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RuntimeError("HTTP_REDIRECT_REJECTED")


def opener(cookies=False):
    handlers = [urllib.request.ProxyHandler({}), NoRedirect()]
    if cookies:
        handlers.append(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    return urllib.request.build_opener(*handlers)


def request(client, url, method="GET", body=None, headers=None, expected=200):
    headers = dict(headers or {})
    raw = None
    if body is not None:
        raw = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=raw, method=method, headers=headers)
    try:
        response = client.open(req, timeout=30)
    except urllib.error.HTTPError as e:
        response = e
    with response:
        require(response.status == expected, "HTTP_STATUS_" + str(response.status))
        data = response.read(131073)
        require(len(data) <= 131072, "RESPONSE_TOO_LARGE")
    return json.loads(data) if expected == 200 else None


def tokens():
    secure(ENV)
    require(ENV.stat().st_mode & 0o077 == 0, "ENV_PERMISSIONS")
    values = {}
    for line in ENV.read_text().splitlines():
        key, sep, value = line.partition("=")
        require(sep and key not in values, "ENV_FORMAT")
        values[key] = value
    result = {role: values.get("LIGHT_" + role.upper() + "_TOKEN", "")
              for role in ("display", "settings", "camera")}
    require(len(set(result.values())) == 3 and all(
        re.fullmatch(r"[A-Za-z0-9_-]{32,512}", value) for value in result.values()),
        "TOKEN_FORMAT")
    return result


def gateway():
    locations = []
    for name, methods in (("status", "GET"), ("actions", "POST"),
                          ("settings", "GET|PUT"), ("history", "GET")):
        locations.append("""
    location = /api/v1/lights/%s {
        if ($request_method !~ ^(%s)$) { return 405; }
        proxy_pass http://127.0.0.1:8002;
        proxy_pass_request_headers off;
        proxy_set_header Authorization $http_authorization;
        proxy_set_header Content-Type $http_content_type;
        proxy_set_header Host 127.0.0.1;
        proxy_connect_timeout 1s;
        proxy_send_timeout 2s;
        proxy_read_timeout 2s;
    }
""" % (name, methods))
    return """# Light-only private LAN gateway for the existing HTTP Dial transport.
# Camera HTTPS8443 and shower8081 remain independent.
server {
    listen %s:8082;
    server_name %s;
    allow %s;
    allow %s;
    deny all;
    access_log off;
    error_log /dev/null crit;
    client_max_body_size 4096;
    client_body_timeout 3s;
    send_timeout 5s;
%s
    location / { return 404; }
}
""" % (PI, PI, DIAL, PI, "".join(locations))


def guarded_config(value):
    require(isinstance(value, dict) and type(value.get("generation")) is int
            and 0 <= value["generation"] <= 4294967295 and value["generation"] % 2 == 0,
            "DIAL_CONFIG_INVALID")
    require(value.get("configured") is False, "DIAL_ALREADY_CONFIGURED_REVIEW_REQUIRED")


def private_pin():
    require(os.isatty(0), "PRIVATE_TERMINAL_REQUIRED")
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        return getpass.getpass("Existing Dial admin PIN (hidden): ")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--loads-disconnected", action="store_true")
    args = parser.parse_args()
    require(args.loads_disconnected, "LOADS_DISCONNECTED_REQUIRED")
    require(os.geteuid() == 0, "ROOT_CONSOLE_REQUIRED")
    os.umask(0o077)
    require(Path("/proc/device-tree/model").read_bytes().rstrip(b"\0\n")
            == b"Raspberry Pi 4 Model B Rev 1.1", "WRONG_HOST")
    secure(PAIR)
    require(sha(PAIR) == PAIR_SHA, "PAIRED_BASELINE_CHANGED")
    for path in (AVAILABLE, ENABLED, MARKER):
        secure(path.parent)
        require(not os.path.lexists(path), "PRIOR_ATTEMPT_REVIEW_REQUIRED")
    for service in ("light-gpio.service", "light-controller.service", "nginx.service",
                    "freeze-protect.service", "freeze-protect-pair-gpio.service"):
        require(run("systemctl", "is-active", service) == "active", "SERVICE_INACTIVE")
    for pin in ("20", "26"):
        require("| hi" in run("pinctrl", "get", pin), "PAIRED_DRAIN_REQUIRED")
    with socket.socket() as sock:
        sock.bind((PI, 8082))
    run("nginx", "-t")
    creds = tokens()
    direct, dial = opener(), opener(True)
    status = request(direct, "http://127.0.0.1:8002/api/v1/lights/status",
                     headers={"Authorization": "Bearer " + creds["display"]})
    require(status.get("capability") == "independent_light_v1"
            and status.get("health") == "OK", "LIGHT_NOT_READY")
    dialbase = "http://" + DIAL + "/admin/api/"
    session = request(dial, dialbase + "session")
    require(session.get("setup_required") is False, "DIAL_PIN_NOT_CONFIGURED")
    pin = private_pin()
    require(re.fullmatch(r"[0-9]{4}", pin), "PIN_FORMAT")
    request(dial, dialbase + "login", "POST", {"pin": pin},
            {"Origin": "http://" + DIAL})
    pin = None
    session = request(dial, dialbase + "session")
    require(session.get("authenticated") is True and session.get("csrf"), "LOGIN_FAILED")
    headers = {"Origin": "http://" + DIAL, "X-CSRF-Token": session["csrf"]}
    evidence = None
    try:
        config = request(dial, dialbase + "light/config")
        guarded_config(config)
        evidence = Path(tempfile.mkdtemp(prefix="light-admin-install.", dir="/root"))
        os.chmod(evidence, 0o700)
        camera = Path("/etc/nginx/sites-available/light-camera.conf")
        secure(camera)
        baseline = {"camera": sha(camera), "environment": sha(ENV), "pair": sha(PAIR)}
        private(evidence / "before.json", json.dumps(baseline))
        private(MARKER, str(evidence))
        private(AVAILABLE, gateway())
        os.chmod(AVAILABLE, 0o644)
        ENABLED.symlink_to(AVAILABLE)
        run("nginx", "-t")
        run("systemctl", "reload", "nginx")
        for endpoint, role in (("status", "display"), ("settings", "settings"),
                               ("history", "settings")):
            url = BASE + "/api/v1/lights/" + endpoint
            request(direct, url, expected=401)
            request(direct, url, headers={"Authorization": "Bearer " + creds[role]})
        private(evidence / "save-started.json", '{"single_attempt":true}')
        request(dial, dialbase + "light/config", "PUT",
                {"url": BASE, "display_token": creds["display"],
                 "settings_token": creds["settings"]}, headers)
        config = request(dial, dialbase + "light/config")
        require(config.get("configured") is True and config.get("url") == BASE,
                "DIAL_SAVE_UNCONFIRMED")
        binding = {"X-Light-Config-Generation": str(config["generation"])}
        st = request(dial, dialbase + "light/status", headers=binding)
        settings = request(dial, dialbase + "light/settings", headers=binding)
        history = request(dial, dialbase + "light/history?offset=0", headers=binding)
        require(st.get("capability") == "independent_light_v1" and st.get("health") == "OK",
                "DIAL_STATUS_UNCONFIRMED")
        require({"camera": sha(camera), "environment": sha(ENV), "pair": sha(PAIR)} == baseline,
                "BASELINE_CHANGED")
        result = {"result": "LIGHT_ADMIN_CONNECTED", "mode": st["mode"],
                  "hold_seconds": settings["hold_seconds"],
                  "manual_seconds": settings["manual_seconds"],
                  "history_rows": len(history["items"]), "evidence": str(evidence),
                  "actions_issued": False}
        private(evidence / "success.json", json.dumps(result))
        print(json.dumps(result))
    finally:
        try:
            request(dial, dialbase + "logout", "POST", {}, headers)
        except Exception:
            print("LOGOUT_UNCONFIRMED; session will expire")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Never print HTTP bodies, request headers or arbitrary exception messages.
        code = str(exc) if type(exc) is RuntimeError and re.fullmatch(
            r"[A-Z_0-9]+", str(exc)) else type(exc).__name__
        print("LIGHT_ADMIN_STOPPED=" + code + "; no automatic retry or rollback")
        raise SystemExit(1) from None
