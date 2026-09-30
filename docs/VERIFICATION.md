# Repository verification

These checks validate the repository checkout. They do not prove which revision
is deployed, the current GPIO state or physical valve movement.

## Supported environment

Use Python 3.12 and Node.js 22 or newer. Create a virtual environment and install
the declared development dependencies:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

## Complete repository checks

Run from the repository root:

```bash
python -m pytest -q
python -m ruff check .
python -m mypy src
python -m build
python -m json.tool deployment/node-red/freeze-protect-paired-relay.json >/dev/null
node --check deployment/node-red/preflight-no-legacy-gpio.js
sh -n deployment/workstation-codex/bootstrap-freezeprotect-access.sh
sh -n deployment/workstation-codex/freeze-protect-commission
sh -n deployment/workstation-codex/freeze-protect-commission-ssh-dispatch
git diff --check "$(git merge-base origin/main HEAD)" HEAD
```

`pytest` includes an internal Markdown file/anchor check and structural
assertions for the Node-RED/Nginx/systemd/commissioning assets. The local Git
command checks the complete branch delta against `origin/main`; substitute the
actual base branch when needed. CI fetches full history and checks the PR range
or every commit in the pushed range rather than the clean checkout's empty
working-tree diff.

Display telemetry contract checks cover the two display fields, mode-specific
single-reader ownership, five-second sampler cadence, 15-second freshness,
unavailable readings, and exclusion of administrator diagnostics. Passing
repository checks validates the implementation in this checkout only; it does
not verify a deployed Pi, SPI wiring, sensor accuracy, dial presentation, relays,
valves, or water routing.

## Firmware checks

The retired CrowPanel source has separate PlatformIO environments:

```bash
cd firmware/crowpanel
pio test -e native
pio run -e crowpanel
```

A successful build proves source compatibility only. It does not prove that an
artifact was flashed or that the device, network, API, GPIO or valves work.
Active Waveshare firmware must be built and verified in the `roon-knob`
repository at the exact release revision being commissioned.

## Node-RED checks

The repository JSON can be inspected structurally, but the deployed runtime
still requires separate evidence:

- Node-RED and Node.js versions;
- effective user directory, settings and active flow file;
- installed palette dependencies;
- loopback listener and editor security boundary;
- service logs and deterministic request/response behavior;
- the deployed legacy-flow preflight.

Run the deployed preflight exactly as documented in
[`deployment/COMMISSIONING.md`](../deployment/COMMISSIONING.md). A source JSON
pass does not prove the Pi loaded that flow.

## Evidence labels

Use these labels in reviews and release notes:

- **VERIFIED (repository):** observed in the current checkout or a fresh check.
- **VERIFIED (deployed):** observed on the named host/revision with command output.
- **VERIFIED (physical):** directly observed at the installation.
- **INFERRED:** strongly suggested but not directly observed.
- **UNKNOWN / NOT_VERIFIED:** evidence is missing or insufficient.
