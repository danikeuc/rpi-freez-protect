# CrowPanel Dial and PT100/MAX31865 Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the CrowPanel encoder electrical-mode correction and replace the production DS18B20 source with a fail-safe PT100/MAX31865 source.

**Architecture:** The existing ESP32 UI remains an intent client and the Raspberry Pi remains the sole safety authority. The two device changes are separate commits and verification gates. The Hub uses an injected SPI boundary so the complete MAX31865 transaction is deterministic under unit tests before any physical commissioning.

**Tech Stack:** C++17/Arduino/PlatformIO, Python 3.12, FastAPI, pytest, Linux spidev 3.8, systemd.

**Spec:** `docs/superpowers/specs/2026-09-21-pt100-max31865-design.md`

## Global Constraints

- `/dev/spidev0.0`, SPI mode 1, maximum 500 kHz, 8 bits per word.
- PT100, three-wire compensation, 430 ohm reference, 50 Hz filter.
- One-shot conversion with VBIAS disabled after every attempt.
- Run the MAX31865 automatic fault-detection cycle before every accepted sample
  and reject timeout or any nonzero fault register.
- Use that automatic cycle only for a verified module input-filter RC time
  constant of at most 100 microseconds; otherwise commissioning stops until
  manual fault-cycle timing is implemented for the exact module.
- `sensor_commissioned=false` after deployment and automatic `NORMAL` remains impossible until explicit commissioning.
- Bind commissioning approval to `MAX31865_PT100_SPI0_CE0` so approval from the
  replaced sensor cannot transfer silently.
- The CrowPanel receives no PT100-specific diagnostics.
- No live valve actuation is part of repository implementation or automated verification.

## Review Focus

- A short SPI response must be `INVALID` and must still disable VBIAS.
- An OS/SPI exception must be `STALE`, never a reused prior temperature.
- An uncommissioned but healthy reading must remain visible to administrators while policy stays in `DRAIN`.
- Legacy settings payloads containing `sensor_device_id` must still load and round-trip.
- Production construction must not access SPI until the first sample.

---

### Task 1: Stabilize the CrowPanel dial regression boundary

**Files:**
- Modify: `tests/integration/test_node_red_flow.py`
- Verify: `firmware/crowpanel/src/hardware.cpp`

**Interfaces:**
- Consumes: vendor encoder pins GPIO 45/42 and the current dial UI strings.
- Produces: regression coverage requiring unbiased A/B inputs and no obsolete forecast-refresh label.

- [ ] Replace the obsolete `POSODOBLJENO` assertion with assertions for the current forecast page and dedicated action labels.
- [ ] Run `pytest tests/unit/test_crowpanel_encoder_config.py tests/integration/test_node_red_flow.py -q`; expect all selected tests to pass.
- [ ] Run the complete Python suite to establish that the existing dial commit and current UI agree.
- [ ] Commit the test alignment separately from the PT100 implementation.

### Task 2: Implement the MAX31865 adapter by TDD

**Files:**
- Create: `tests/unit/test_max31865.py`
- Create: `src/freeze_protect/adapters/max31865.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: `TemperatureReading`, `SensorHealth`, a clock callable, a sleep callable, and an injected `Callable[[], SpiDevice]`.
- Produces: `Max31865TemperatureSource.read() -> TemperatureReading`, `LinuxSpiDevice`, and the administrator-only `diagnostics()` mapping.

- [ ] Write failing tests for the exact `0x13 -> 0x91 -> 0x95 -> bounded
  completion/fault check -> 0xB1 -> RTD read -> 0x11` sequence and a healthy
  positive conversion.
- [ ] Run the focused test and confirm failure because the adapter is absent.
- [ ] Implement the injected SPI protocol, Linux `open_path`, register helpers, one-shot sequence, and positive CVD branch.
- [ ] Run the focused test and confirm green.
- [ ] Add failing tests for a negative temperature, on-demand cable faults,
  fault-cycle timeout, RTD fault bit and flags, zero/full-scale ratios, short
  transfer, SPI exception, application range, and VBIAS cleanup.
- [ ] Implement numerical negative conversion and fail-safe classifications without caching readings.
- [ ] Run the adapter tests, then the complete suite, ruff, and mypy.
- [ ] Commit the adapter independently.

### Task 3: Select PT100 in production and preserve safe compatibility

**Files:**
- Modify: `src/freeze_protect/api/app.py`
- Modify: `tests/integration/test_m1_api.py`
- Modify: `tests/integration/test_m1_sqlite.py`
- Modify: `deployment/systemd/freeze-protect.service`
- Modify: `deployment/COMMISSIONING.md`
- Modify: `tests/integration/test_node_red_flow.py`

**Interfaces:**
- Consumes: `Max31865TemperatureSource` from Task 2 and existing `SafetySettings`/SQLite schemas.
- Produces: production composition using MAX31865, admin commissioning visibility, unchanged legacy settings acceptance, explicit SPI service permissions, and PT100 commissioning instructions.

- [ ] Write failing tests proving production selects MAX31865 lazily, display
  status omits sensor diagnostics, uncommissioned healthy values appear in
  admin status while state remains `sensor_pending`, legacy `sensor_device_id`
  loads, replacement-source commissioning is reset exactly once, and the
  service declares `SupplementaryGroups=spi`.
- [ ] Run the focused tests and verify the expected failures.
- [ ] Replace only the production composition-root selection, narrow the display payload, and update service/deployment documentation; retain the DS18B20 adapter as rollback code.
- [ ] Run focused tests and confirm green.
- [ ] Run the complete suite, ruff, mypy, package build, and any available PlatformIO native/target builds.
- [ ] Commit production integration and commissioning documentation.

### Task 4: Whole-branch verification and handoff

**Files:**
- Verify: all files changed since `origin/codex/crowpanel-dial-ui`.

**Interfaces:**
- Consumes: all prior commits.
- Produces: verified branch state and a hardware commissioning handoff without push, deployment, or live actuation.

- [ ] Review the complete diff for authority, stale-data, exception, secret, and rollback regressions.
- [ ] Run the complete Python test/lint/type/build commands from a clean working tree.
- [ ] Record whether PlatformIO is available; never claim a firmware target build without its output.
- [ ] Report exact commits, test evidence, remaining physical gates, and the explicit push/deployment command requiring user authorization.
