# AGENTS.md — rpi-freez-protect

## Mission

Maintain `rpi-freez-protect` as a safe, deterministic, reproducible, documented and evidence-backed freeze-protection and outdoor-shower control system.

The goal is not merely to produce code. Keep the deployed system aligned across:

`repository ↔ documentation ↔ CI/build ↔ Raspberry Pi runtime ↔ ESP32 runtime ↔ physical hardware`

## Mandatory working model

Use this lifecycle for non-trivial work:

`OBSERVE → RECONCILE → PLAN → IMPLEMENT → TEST → DEPLOY → VERIFY → DOCUMENT`

For faults:

`SYMPTOM → SIGNAL PATH → FIRST UNCERTAIN BOUNDARY → TEST → ROOT CAUSE → MINIMAL FIX → REGRESSION TEST → EVIDENCE`

Do not use shotgun debugging. Reuse existing evidence and do not repeat a test that already proved the same boundary unless the relevant implementation, configuration or hardware changed.

## Specialist skill routing

When the runtime exposes specialist skills, use the most specific one before acting:

- `embedded-edge-systems-engineer` for ESP32/ESP32-S3, Raspberry Pi, DietPi, GPIO, SPI/I2C/UART/1-Wire, sensors, relays, valves, firmware, device integration, commissioning and live-hardware safety.
- `node-red-engineer` for Node-RED flow design, Function nodes, message contracts, context, runtime configuration, security, Projects/Git, custom nodes, deployment and Node-RED troubleshooting.
- `rpi-freez-protect-documentation-evidence-reconciler` after meaningful changes or whenever repository documentation, deployed state, evidence claims or physical observations diverge.
- Use the applicable Superpowers workflow for non-trivial work: brainstorming before behaviour/design changes, systematic debugging for faults, test-driven development for code changes, receiving-code-review for review feedback, and verification-before-completion before any success claim.

Skills are specialist guidance, not authority to bypass this repository's safety gates, access boundaries, approval requirements, source-of-truth rules or commissioning procedures.

## Evidence classification

Always distinguish:

- **VERIFIED** — directly demonstrated by files, commands, logs, measurements, runtime or physical observation.
- **INFERRED** — strongly indicated but not directly proven.
- **UNKNOWN** — material evidence is missing.

Never promote an inference to VERIFIED.

Examples:

- HTTP 200 proves the endpoint responded; it does not prove physical valve movement.
- GPIO readback proves GPIO state; it does not prove valve position.
- A successful build does not prove hardware behaviour.
- A merge does not prove deployment.
- Deployment does not prove physical commissioning.

## Read before acting

- Treat this repository as control software for physical water valves.
- Review `deployment/WORKSTATION_CODEX_COMMISSIONING.md` and `deployment/workstation-codex/CODEX_COMMISSIONING_PROMPT.md` before any deployment, commissioning, SSH-policy, firmware-upload, GPIO, relay or actuator task.
- Read `docs/PROJECT_STATE.md` before reporting deployment, firmware, sensor, GPIO or physical status.
- For ChatGPT project sessions, keep `docs/PROJECT_INSTRUCTIONS.md` aligned with the Project Instructions field.
- Repository files, deployed Pi state and observed physical behaviour are separate evidence sources. Do not claim one proves another.

## Repository discipline

Before making changes:

1. inspect the current branch;
2. inspect HEAD;
3. inspect `git status`;
4. fetch current remote state;
5. inspect relevant open PRs;
6. inspect recent relevant history;
7. inspect current documentation and configuration.

Do not create unnecessary parallel branches. Do not duplicate work already present in another active branch or PR. Keep changes bounded and traceable. Preserve unrelated local changes. Never silently reset, overwrite or discard user work.

Repository:

`danikeuc/rpi-freez-protect`

GitHub is the canonical engineering history. Runtime and physical observations are stronger evidence than stale documentation. If documentation, implementation and runtime disagree, reconcile them explicitly.

## System architecture and control authority

The system contains, as applicable:

- Raspberry Pi 4 running DietPi;
- Node-RED;
- Python/backend services;
- paired GPIO relay/valve control;
- motorized 24 V valves;
- temperature sensors;
- weather forecast integration;
- ESP32-S3 CrowPanel rotary display;
- nginx;
- systemd services;
- REST/API communication.

Preserve one authoritative safety/control policy on the Raspberry Pi control plane. The display may request actions but must not independently override safety policy.

Avoid duplicated state machines across ESP32 firmware, Node-RED and backend services.

## Paired valve control invariant

Current paired control semantics:

### SUPPLY

- GPIO 26 = LOW
- GPIO 20 = LOW

### DRAIN

- GPIO 26 = HIGH
- GPIO 20 = HIGH

Legal combinations:

| GPIO 26 | GPIO 20 | Meaning |
|---|---|---|
| LOW | LOW | SUPPLY |
| HIGH | HIGH | DRAIN |

Mixed output states are invalid and must be treated as a fault unless superseded by an approved ADR.

The intended safe state is **DRAIN**.

Do not infer physical valve position from GPIO alone.

## Safety boundary

This system controls water and freeze protection and is safety-critical.

- Keep the 24 V valve supply disconnected unless Danijel explicitly approves the same bounded physical test in the current conversation.
- Do not run SUPPLY. Use only the documented timed-shower path after all software gates pass and explicit approval is recorded.
- Preserve the paired-output invariant: GPIO 26 and GPIO 20 move together.
- GPIO readback does not prove valve position.
- Stop on any failed receipt, readback, service check or deployed-flow preflight.
- Leave the requested state at DRAIN and do not retry SUPPLY after a failed safety gate.

Any actuator-related design or implementation must explicitly address:

1. communication loss;
2. controlling-process crash or hang;
3. Raspberry Pi reboot/reset;
4. power loss and restoration.

For each case define:

- expected safe outcome;
- enforcing mechanism;
- verification evidence;
- unresolved gap.

Commands that enable water supply must be bounded by controller/server-side timeout. Do not rely on the ESP32 display alone to stop water flow.

## Test order and live hardware

Use the lowest-risk useful test first:

1. repository/static inspection;
2. schema/config validation;
3. unit tests and static checks;
4. clean build;
5. simulated or mocked I/O;
6. API/integration tests;
7. read-only Raspberry Pi diagnostics;
8. GPIO verification without hazardous load where possible;
9. bounded relay test;
10. bounded valve test;
11. physical commissioning;
12. communication-loss, crash/hang, reboot and power-cycle recovery tests.

Do not energize actuators merely to diagnose a software-layer issue that can be isolated earlier.

Live hardware actuation requires:

- bounded duration;
- known safe state;
- verified stop method;
- recovery method;
- physical observation where needed.

## Workstation and Raspberry Pi boundary

- Raspberry Pi uses DietPi. Do not assume Raspberry Pi OS tooling such as `raspi-config`.
- Primary management path is Windows PowerShell → SSH/SCP → DietPi.
- Run Codex on the workstation clone. Do not install Codex on the Pi.
- Routine remote access uses only the key-based `freezeprotect-commission` account and the exact helper commands documented in the commissioning prompt. Do not use `freezeprotect` for SSH.
- Do not widen the commissioning allowlist, grant a shell, add device groups, expose TCP 22 publicly or bypass the forced-command dispatcher.
- Root SSH is only the documented, human-supervised bootstrap/recovery path. Keep the recovery session open until a second restricted login succeeds.
- Never print or commit private keys, tokens, Wi-Fi credentials, environment values or `firmware/crowpanel/include/secrets.h`.

Use runtime evidence such as `systemctl`, `journalctl`, sockets, ports, service files, logs, direct API calls and filesystem state to establish actual deployment state.

## SSH trust and diagnostics

- A first-contact `The authenticity of host ... can't be established` prompt is not an authentication failure.
- Verify the displayed ED25519 fingerprint out of band at a trusted local console with `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub -E sha256`, then let the human operator accept that exact fingerprint interactively.
- Do not use `StrictHostKeyChecking=no` or silently replace `known_hosts`.
- Use `ssh-keygen -R` only for a verified changed-host-key event, never for normal first contact.
- Treat PowerShell and the remote POSIX shell as separate interpreters. Prefer reviewed files or simple documented commands over nested one-liners.
- Diagnose from evidence before changing SSH policy, accounts, permissions or services. Preserve unrelated local and deployed changes.

## Node-RED engineering boundary

Node-RED is an authenticated, loopback-only integration bridge. It is not the safety authority and must not become a second control state machine.

For Node-RED work:

- keep the editor and HTTP runtime bound to loopback unless an approved architecture change explicitly says otherwise;
- never reintroduce direct `rpi-gpio out` ownership of GPIO 26/20, legacy `/trigger/...` control routes, or any second process that can independently write the paired outputs;
- route paired-valve intent through the fixed `paired_gpio_client.py` → Unix socket → `paired_gpio_daemon.py` path;
- keep authentication, validation, timeout, idempotency and error behaviour explicit at the Node-RED/API boundary;
- do not store safety-critical desired state only in volatile Node-RED context or make context persistence the mechanism that restores actuator state after restart;
- keep Function-node work bounded and observable; handle errors explicitly and avoid blocking work that can starve the event loop;
- keep secrets in approved environment/credential mechanisms, never in exported flow JSON, Function-node source, debug output or Git;
- export/retain a rollback copy before replacing an active flow and reconcile the deployed active flow separately from repository JSON.

For repository Node-RED changes, at minimum validate the flow JSON/JavaScript and run the relevant integration coverage, including `tests/integration/test_node_red_flow.py`. For commissioning/cutover, run `deployment/node-red/preflight-no-legacy-gpio.js` against the deployed active `flows.json` exactly as documented in `deployment/COMMISSIONING.md`.

A successful deploy, HTTP response or Node-RED receipt proves only its own layer. It does not prove GPIO state, relay state, valve movement or plumbing outcome.

Use the official Node-RED documentation at `https://nodered.org/docs/` as the primary external reference for version-sensitive Node-RED behaviour.

## ESP32 / CrowPanel

Target hardware is the Elecrow CrowPanel 1.28-inch ESP32-S3 rotary round display.

Before firmware changes verify:

- exact board and chip target;
- PlatformIO environment;
- Arduino/ESP-IDF version;
- display driver;
- encoder/button pins;
- Wi-Fi/API configuration.

Do not use generic ESP32-S3 pin assumptions. Use official Espressif and Elecrow documentation for version-sensitive behaviour.

Unless superseded by an approved change, the intended interaction model is:

- rotate: switch between main screen and forecast;
- short press on main screen:
  - inactive shower → request timed shower;
  - active shower → request stop/safe state;
- short press on forecast → return to main screen;
- long press about 2 seconds → request DRAIN.

Backend remains authoritative.

## Network and status evidence

If logs prove:

`ESP32HTTPClient → GET /api/v1/display/status → HTTP 200`

then basic ESP32 → Raspberry Pi HTTP connectivity is VERIFIED for that observation.

Do not later restart diagnosis from “maybe ESP32 cannot reach the hub” unless newer contradictory evidence exists. Move to the first still-uncertain boundary.

Serial monitoring is not automatically authoritative. If useful serial output is known to be unavailable, prefer nginx logs, backend logs, API responses, UI behaviour, network evidence, GPIO state and physical observation.

## Sensors

Possible/current sensor paths include DS18B20 and PT100 + MAX31865.

Do not assume sensor wiring mode or calibration.

For PT100/MAX31865 verify:

- 2/3/4-wire topology;
- reference resistor;
- SPI bus;
- chip select;
- PT100/PT1000 configuration;
- calibration;
- cable resistance impact.

Missing or stale sensor data must never be silently converted into a valid normal reading.

## API discipline

Every control API must define:

- endpoint and method;
- authentication;
- request and response schema;
- units;
- timeout;
- retry behaviour;
- idempotency;
- validation;
- stale-data handling;
- failure behaviour.

UI labels must not be the only enforcement mechanism.

## Secrets

Never commit passwords, Wi-Fi credentials, API tokens, private keys or access secrets. Use approved environment/configuration mechanisms. If a secret enters Git history, treat it as compromised and rotate it.

## Verification

For Python changes, run:

`python -m pytest -q`

and:

`python -m ruff check .`

For commissioning-asset changes, also run:

`python -m pytest -q tests/integration/test_workstation_commissioning_assets.py`

and syntax-check changed shell scripts with `sh -n`.

For ESP32 changes, use the exact repository PlatformIO environment and native/unit tests that apply to the changed layer.

Do not describe repository tests as live hardware verification.

## Documentation and ADRs

After significant changes, reconcile as applicable:

- README;
- architecture documentation;
- ADRs;
- wiring and pin maps;
- commissioning docs;
- deployment docs;
- API docs;
- ESP32 docs;
- evidence/status records.

Do not document intended behaviour as if it were already verified. Mark superseded architecture clearly.

Create or update an ADR for changes involving:

- control authority;
- valve semantics;
- safe state;
- sensor policy;
- protocol boundaries;
- ownership between processes;
- recovery semantics;
- security model;
- architecture-level component responsibility.

Do not use ADRs for trivial implementation details.

## Definition of done

Use these terms precisely:

- **IMPLEMENTED** — code exists.
- **TESTED** — relevant tests pass.
- **INTEGRATED** — works across required software/device boundaries.
- **DEPLOYED** — intended version is running on target.
- **RUNTIME_VERIFIED** — target runtime evidence confirms the expected deployed behaviour.
- **COMMISSIONED** — physical behaviour and required failure/recovery cases are verified.

Do not collapse these states into one.

## External references

Prefer primary sources:

- Espressif documentation;
- Elecrow documentation;
- Raspberry Pi documentation;
- component datasheets;
- official library/framework documentation.

External GitHub projects may be used as references and design-pattern sources, but must not be copied blindly. Reconcile external patterns with this project's actual hardware, software versions and safety requirements.

## Reporting and escalation

Report concise engineering status in this order:

1. current state;
2. evidence;
3. finding;
4. change made;
5. verification;
6. remaining gap / next step.

Do not ask for confirmation for routine engineering work.

Escalate only for:

- physical intervention;
- credentials/access;
- unsafe live hardware action;
- irreversible action;
- material architecture decision.
