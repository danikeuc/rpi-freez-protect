# RPi Freeze Protect

RPi Freeze Protect is a local, safety-first control service for a vulnerable
water installation. The Raspberry Pi is the control authority; M0 supplies a
fully simulated service with a local API, persistent settings and an
append-only audit trail.

> **M0 must not be connected to physical relays, an actuator, GPIO, or an
> ESP32.** It is a software and safety-policy baseline only.

## What M0 does

- Evaluates a pipe-temperature reading through an explicit safety state model.
- Latches a fault after startup, restart, stale/invalid sensor input, or a
  relay-adapter failure; an administrator must clear a healthy fault.
- Requires a forecast with all seven daily minima strictly above +5 °C before
  an automatic logical `OPEN` command can follow protection.
- Applies the configured minimum protection dwell before automatic release.
- Provides only simulated sensor, forecast and relay adapters.
- Writes settings and audit events to one local SQLite file.

## Local installation

Use Python 3.12 or later. On the intended Pi or development computer:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
```

Run the full verification suite:

```bash
python -m pytest -v
python -m ruff check .
python -m mypy src
python -m build
```

## Safe local demonstration

The service binds only to loopback. Set a non-empty administrator token and
enable the simulator explicitly:

```bash
export FREEZE_PROTECT_ADMIN_TOKEN='use-a-long-unique-local-secret'
export FREEZE_PROTECT_DEVELOPMENT_MODE=true
export FREEZE_PROTECT_DB_PATH='./data/freeze-protect.db'
uvicorn freeze_protect.main:app --host 127.0.0.1 --port 8000
```

In a second local terminal, inspect state:

```bash
curl http://127.0.0.1:8000/api/v1/status
```

M0 starts in `STARTING`; its first control cycle latches `FAULT` without
issuing a relay action. This is deliberate. To demonstrate a low-temperature
protection decision, first inject a healthy simulation value, clear the fault,
then inject the low value:

```bash
token='use-a-long-unique-local-secret'
curl -X POST http://127.0.0.1:8000/api/v1/simulation/temperature \
  -H "X-Admin-Token: $token" \
  -H 'Content-Type: application/json' \
  -d '{"value_c":6.0,"health":"HEALTHY"}'
curl -X POST http://127.0.0.1:8000/api/v1/commands/clear-fault \
  -H "X-Admin-Token: $token" \
  -H 'X-Confirm-Command: CLEAR_FAULT'
curl -X POST http://127.0.0.1:8000/api/v1/simulation/temperature \
  -H "X-Admin-Token: $token" \
  -H 'Content-Type: application/json' \
  -d '{"value_c":0.5,"health":"HEALTHY"}'
```

The `simulated` endpoint does not exist unless
`FREEZE_PROTECT_DEVELOPMENT_MODE=true`. Administrative settings, commands and
audit history all require `X-Admin-Token`; movement commands additionally
require the matching `X-Confirm-Command` header.

## Backup and commissioning boundary

The SQLite database is stored at `FREEZE_PROTECT_DB_PATH`, by default
`./data/freeze-protect.db`. Stop the service before copying this file to a
secured backup location. It contains configuration and the audit trail, but
never stores the administrator token.

Before M1 can connect any hardware, record the exact Pi, sensor, relay module,
fusing, electrical isolation, safe de-energized state, actuator travel time and
end-stop feedback. M0 intentionally contains no GPIO library, relay polarity,
weather-provider credential, remote access or ESP32 firmware.
