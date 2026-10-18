"""Fixed, read-only lighting inventory. No settings evaluation or GPIO request."""
from __future__ import annotations

import hashlib
import json
import platform
import re
import subprocess
from pathlib import Path

USER_DIR = "/mnt/dietpi_userdata/node-red"
PAIR_PYTHON = "/opt/freeze-protect-paired-gpio/venv-2.3.0/bin/python3"
GPIO_PROBE = """
import gpiod, json
with gpiod.Chip('/dev/gpiochip0') as chip:
    lines = {}
    for pin in (20, 21, 26):
        info = chip.get_line_info(pin)
        lines[str(pin)] = {'used': bool(info.used),
                          'paired_owner': info.consumer == 'freeze-protect-pair',
                          'name_matches': info.name == 'GPIO' + str(pin)}
    print(json.dumps({'chip_name_matches': chip.get_info().name == 'gpiochip0',
                      'lines': lines}))
"""
COMMANDS = (
    ("/usr/bin/systemctl", "show", "node-red.service", "--property=ActiveState,MainPID,User"),
    ("/usr/bin/journalctl", "-u", "node-red.service", "-b", "-n", "500", "--no-pager", "-o", "cat"),
    (PAIR_PYTHON, "-I", "-B", "-c", GPIO_PROBE),
)


def read(path: Path, limit: int) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("FILE_TOO_LARGE")
    return data


def run(args: tuple[str, ...]) -> str:
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            timeout=15, check=True, cwd="/",
                            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C"})
    if len(result.stdout) > 1024 * 1024:
        raise ValueError("OUTPUT_TOO_LARGE")
    return result.stdout.decode("utf-8", errors="replace")


def flow_summary(rows: object) -> dict:
    if not isinstance(rows, list) or any(not isinstance(n, dict) for n in rows):
        raise ValueError("INVALID_FLOW")
    for n in rows:
        if any(k in n and not isinstance(n[k], str) for k in ("id", "z", "type")):
            raise ValueError("INVALID_FLOW")
    disabled = {n.get("id") for n in rows if n.get("type") == "tab" and n.get("disabled") is True}
    active = [n for n in rows if n.get("z") not in disabled and n.get("d") is not True]
    return {"nodes": len(rows), "disabled_tabs": len(disabled),
            "enabled_light_routes": sum(n.get("type") == "http in" and n.get("url") == "/lighting/unifi" for n in active),
            "gpio_output_nodes_present": any(n.get("type") == "rpi-gpio out" for n in active),
            "function_nodes": sum(n.get("type") == "function" for n in active)}


def startup_summary(text: str) -> dict:
    result = {}
    for label, key in (("Node-RED", "node_red_version"), ("Node.js", "node_version")):
        versions = re.findall(re.escape(label) + r" version:\s*v?(\d+\.\d+\.\d+)(?=\s|$)", text)
        result[key] = versions[-1] if versions else "NOT_OBSERVED"
    for label, key, expected in (("Settings file", "settings_path_matches", USER_DIR + "/settings.js"),
                                 ("User directory", "user_dir_matches", USER_DIR),
                                 ("Flows file", "flow_path_matches", USER_DIR + "/flows.json")):
        values = re.findall(re.escape(label) + r"\s*:\s*([^\r\n]+)", text)
        result[key] = values[-1].strip() == expected if values else None
    result["evidence"] = "RECENT_STARTUP_LOG_ONLY_NOT_EFFECTIVE_CONFIGURATION"
    return result


def collect() -> dict:
    model = read(Path("/proc/device-tree/model"), 256).rstrip(b"\0\n")
    if model != b"Raspberry Pi 4 Model B Rev 1.1":
        raise ValueError("WRONG_HOST")
    result = {"mode": "READ_ONLY_INVENTORY", "model": model.decode(),
              "kernel": platform.release(), "files": {},
              "runtime_settings": "NOT_EVALUATED", "physical_acceptance": "NOT_VERIFIED"}
    for name in ("settings.js", "flows.json", "package.json", "package-lock.json", ".config.projects.json"):
        try:
            raw = read(Path(USER_DIR) / name, 8 * 1024 * 1024)
            result["files"][name] = {"sha256": hashlib.sha256(raw).hexdigest()}
            if name == "flows.json":
                result["flow"] = flow_summary(json.loads(raw))
        except (OSError, ValueError):
            result["files"][name] = {"result": "UNAVAILABLE_OR_INVALID"}
    for index, args in enumerate(COMMANDS):
        key = ("node_red_service", "startup_log", "gpio_metadata")[index]
        try:
            text = run(args)
            if index == 0:
                props = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
                state = props.get("ActiveState", "")
                result[key] = {"active": state == "active",
                               "MainPID": int(props.get("MainPID", "0")),
                               "user_is_nodered": props.get("User") == "nodered"}
            elif index == 1:
                result[key] = startup_summary(text)
            else:
                data = json.loads(text)
                values = [data["chip_name_matches"]] + [data["lines"][str(pin)][field]
                    for pin in (20, 21, 26) for field in ("used", "paired_owner", "name_matches")]
                if any(type(value) is not bool for value in values):
                    raise ValueError("INVALID_GPIO_PROBE")
                result[key] = {"chip_name_matches": data.get("chip_name_matches") is True,
                               "lines": {str(pin): {field: data["lines"][str(pin)].get(field) is True
                                          for field in ("used", "paired_owner", "name_matches")}
                                         for pin in (20, 21, 26)}}
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, AttributeError):
            result[key] = {"result": "NOT_OBSERVED"}
    return result


def main() -> int:
    try:
        print(json.dumps(collect(), sort_keys=True))
        return 0
    except (OSError, ValueError) as error:
        code = "WRONG_HOST" if isinstance(error, ValueError) and str(error) == "WRONG_HOST" else "INVENTORY_UNAVAILABLE"
        print(json.dumps({"result": code}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
