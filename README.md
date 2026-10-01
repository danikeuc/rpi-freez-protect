# RPi Freeze Protect

RPi Freeze Protect is the Raspberry Pi safety controller for an outdoor shower.
It owns one paired two-valve actuator, keeps the default state at `DRAIN`, and
allows a fixed ten-minute `SUPPLY` interval from the Waveshare dial when the
explicit `manual_timed` mode is selected.

Start with the dated [project evidence register](docs/PROJECT_STATE.md). It
separates repository results, deployed observations, device behavior and facts
that still require physical confirmation.

## Safety contract

| Logical state | BCM GPIO 26 / V1 | BCM GPIO 20 / V2 | Intended plumbing result |
| --- | --- | --- | --- |
| `DRAIN` (`0` on the dial) | high / relay released | high / relay released | `Tuš` to `Izpust` |
| `SUPPLY` (`1` on the dial) | low / relay energized | low / relay energized | `Dovod` to `Tuš` |

`DRAIN` is the requested safe state. The paired GPIO daemon is the only GPIO
writer and gives every accepted `SUPPLY` a 60-second lease that the Hub must
renew. Loss of renewal requests paired `DRAIN`. Mixed GPIO states and
single-valve commands are illegal.

A GPIO receipt or readback proves output levels only. It does not prove relay
contacts, valve movement or the plumbing path.

## Active installation

The active display is a Waveshare ESP32-S3 Knob 1.8-inch dial. It switches
between two independent functions:

- **Valve:** trusted-LAN display API to this Pi controller.
- **Roon:** separate integration in
  [`roon-knob`](https://github.com/danikeuc/roon-knob) and
  [`roon-control`](https://github.com/danikeuc/roon-control).

The Pi path is:

`Waveshare -> Nginx :8081 -> Hub 127.0.0.1:8000 -> Node-RED 127.0.0.1:1880 -> paired GPIO daemon -> BCM 26+20`

The source under `firmware/crowpanel` is historical/rollback material. The
CrowPanel is retired from this installation and must not receive the active
display token.

## Operating modes

- `safe_drain` is the default for an absent or invalid setting. It refuses
  `SUPPLY`.
- `manual_timed` is the active installation mode. Only an authenticated
  deliberate display action starts a fixed 600-second interval. Weather and
  temperature cannot start it.
- `automatic` is a separately commissioned legacy/future mode. Missing, stale,
  invalid or unsafe sensor/forecast inputs keep that mode at `DRAIN`.

The PT100/MAX31865 reader on SPI0 CE0 and the seven-day Open-Meteo policy remain
implemented for `automatic`. DS18B20 support is rollback code only.

The authenticated display status also reports informational pipe telemetry in
every mode. In `manual_timed` and `safe_drain`, a single display sampler reads
the sensor every five seconds; in `automatic`, the display uses the reading
already owned by `ControlService`. These readers never run together. Telemetry
does not control valves or the timed shower, and this feature does not commission
the sensor: keep `sensor_commissioned=false` until the separate
automatic-mode commissioning is complete.

## Display API

Nginx exposes exactly three token-protected paths on the trusted LAN:

```text
GET  /api/v1/display/status
POST /api/v1/display/actions/timed-shower
POST /api/v1/display/actions/drain
```

The action requests have no body and cannot submit a duration. In idle
`manual_timed` mode, status is shaped like:

```json
{
  "mode": "manual_timed",
  "state": "MANUAL_DRAIN",
  "command": "DRAIN",
  "remaining_seconds": 0,
  "reason": "manual_idle",
  "forecast": {"available": false, "fresh": false, "dates": [], "minima_c": []},
  "timed_shower_deadline": null,
  "action": "TIMED_SHOWER",
  "action_enabled": true,
  "pipe_temperature_c": null,
  "sensor_health": "STALE"
}
```

`pipe_temperature_c` is a number only for a fresh healthy reading. Otherwise it
is `null`; `sensor_health` is one of `HEALTHY`, `STALE`, `INVALID`, or
`CALIBRATION_REQUIRED`. Samples are taken every five seconds in non-automatic
modes, and a reading is considered stale after 15 seconds. Failed reads clear
the displayed value instead of reusing an earlier temperature. SPI/MAX31865
diagnostics remain administrator-only and are not part of display status.

`command` is the accepted logical command, not physical position. The Hub and
Node-RED control route stay loopback-only.

## Development

Python 3.12 is required:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
python -m pytest -q
python -m ruff check .
python -m mypy src
python -m build
```

The complete local and CI gates, including deployment-asset syntax, are in
[docs/VERIFICATION.md](docs/VERIFICATION.md).

For a software-only demonstration, use distinct placeholder secrets and enable
simulation explicitly. Never reuse deployed tokens:

```bash
export FREEZE_PROTECT_ADMIN_TOKEN='local-admin-token'
export FREEZE_PROTECT_DISPLAY_TOKEN='local-display-token'
export FREEZE_PROTECT_DEVELOPMENT_MODE=true
export FREEZE_PROTECT_DB_PATH='./data/freeze-protect.db'
uvicorn freeze_protect.main:app --host 127.0.0.1 --port 8000
```

## Documentation map

| Document | Purpose |
| --- | --- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Active components, authority and failure boundaries |
| [docs/PROJECT_STATE.md](docs/PROJECT_STATE.md) | Canonical dated evidence and unresolved gaps |
| [docs/VERIFICATION.md](docs/VERIFICATION.md) | Reproducible repository checks and their limits |
| [deployment/COMMISSIONING.md](deployment/COMMISSIONING.md) | Pi, Node-RED, GPIO, PT100 and physical commissioning |
| [deployment/DISPLAY_COMMISSIONING.md](deployment/DISPLAY_COMMISSIONING.md) | Active Waveshare/Roon/valve display acceptance |
| [deployment/WORKSTATION_CODEX_COMMISSIONING.md](deployment/WORKSTATION_CODEX_COMMISSIONING.md) | Restricted workstation-to-Pi access and handoff |
| [deployment/CROWPANEL_COMMISSIONING.md](deployment/CROWPANEL_COMMISSIONING.md) | Superseded CrowPanel procedure retained for history |

Files below `docs/superpowers/specs/` and `docs/superpowers/plans/` record design
and implementation history. They are not current runbooks.

## Secret and network boundary

- Keep admin, display and Node-RED tokens independent and outside Git.
- Never commit `firmware/crowpanel/include/secrets.h`.
- Do not expose ports 8000, 1880 or 8081 to the internet.
- Do not restore the legacy unauthenticated Node-RED trigger flow.
- Keep 24 V disconnected until the applicable commissioning gate explicitly
  authorizes a bounded physical test.
