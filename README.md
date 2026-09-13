# RPi Freeze Protect

RPi Freeze Protect is a local safety controller for the outdoor shower. It runs on the DietPi Raspberry Pi, keeps two 24 V motorized valves paired, uses Node-RED only as the authenticated HTTP bridge, and uses a local atomic paired-GPIO daemon for the relay outputs.

## Safe physical model

| Logical state | BCM GPIO 26 / V1 | BCM GPIO 20 / V2 | Plumbing result |
| --- | --- | --- | --- |
| `DRAIN` | high / relay released | high / relay released | `Tuš` ↔ `Izpust` |
| `SUPPLY` | low / relay energized | low / relay energized | `Dovod` ↔ `Tuš` |

`DRAIN` is the safe state. On Hub or Node-RED restart, a failed bridge request, configuration error, missing sensor, stale sensor, or unsafe forecast, the controller requests `DRAIN`. It never commands a single valve.

## M1 capabilities

- Strict seven-day Open-Meteo minimum-temperature cache; all minima must be strictly above the configured threshold.
- Prepared Linux DS18B20 reader, disabled for automatic operation until an administrator commissions the installed probe.
- Server-controlled `TIMED_SHOWER`: 10 minutes by default, with a hard 30-minute maximum. The display cannot submit a duration.
- Authenticated local APIs: administrator settings/status and a separate minimal display API.
- Loopback-only, token-protected Node-RED paired-valve bridge at `POST /internal/freeze-protect/actuator`, backed by a serialized `/dev/gpiomem` daemon that atomically writes and reads back GPIO 26+20.
- CrowPanel firmware source and flash procedure under `firmware/crowpanel`.

## Local development verification

Python 3.12 and the development dependencies are required:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q
python -m ruff check .
python -m mypy src
python -m build
```

The M1 deployment never uses the development simulation. For a local software-only demonstration, set distinct temporary tokens and enable it explicitly:

```bash
export FREEZE_PROTECT_ADMIN_TOKEN='local-admin-token'
export FREEZE_PROTECT_DISPLAY_TOKEN='local-display-token'
export FREEZE_PROTECT_DEVELOPMENT_MODE=true
export FREEZE_PROTECT_DB_PATH='./data/freeze-protect.db'
uvicorn freeze_protect.main:app --host 127.0.0.1 --port 8000
```

In a separate terminal, the safe startup status is available only with the administrator token:

```bash
curl -H 'X-Admin-Token: local-admin-token' http://127.0.0.1:8000/api/v1/status
```

The status is `FROST_PROTECTION` with reason `sensor_pending` until the DS18B20 is installed and commissioned. A development-only simulation route exists only when `FREEZE_PROTECT_DEVELOPMENT_MODE=true`.

## DietPi and hardware commissioning

Follow [deployment/COMMISSIONING.md](deployment/COMMISSIONING.md) in order. It contains the Node-RED import, systemd environment boundary, GPIO-only test, isolated-water valve test, and delayed DS18B20 commissioning procedure.

For the CrowPanel, use [firmware/crowpanel/README.md](firmware/crowpanel/README.md) and [deployment/CROWPANEL_COMMISSIONING.md](deployment/CROWPANEL_COMMISSIONING.md). The first display test must be run with the 24 V valve supply disconnected.

## Workstation Codex commissioning

Follow [deployment/WORKSTATION_CODEX_COMMISSIONING.md](deployment/WORKSTATION_CODEX_COMMISSIONING.md) for the workstation-led procedure. It supersedes the proposed runner approach.

## Security boundary

- The Hub and Node-RED bridge are bound to loopback; do not reverse-proxy their control routes to the internet.
- Set `FREEZE_PROTECT_ADMIN_TOKEN`, `FREEZE_PROTECT_DISPLAY_TOKEN`, and `FREEZE_PROTECT_NODE_RED_TOKEN` to independent secrets stored outside Git.
- The display never receives a Node-RED address, relay pin, weather credential, or automatic safety policy.
- Never use the legacy unauthenticated Node-RED timer/GET trigger flow after cutover.
