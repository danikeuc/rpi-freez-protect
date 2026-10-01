# rpi-freez-protect — Project Operating Instructions

Use `danikeuc/rpi-freez-protect` as the canonical engineering history for this project. Work autonomously on routine engineering tasks; do not stop for step-by-step approval. Escalate only for physical intervention, credentials/access, unsafe live hardware action, irreversible action, or a material architecture decision.

## Mandatory specialist routing

Before substantive work, use the most specific available specialist guidance:

- `Embedded & Edge Systems Engineer` for ESP32/ESP32-S3, Raspberry Pi, DietPi, GPIO, SPI/I2C/UART/1-Wire, PT100/MAX31865, relays, valves, firmware, device integration and commissioning.
- `Node-RED Engineer` for Node-RED flows, Function nodes, message contracts, context, runtime/security configuration, Projects/Git, custom nodes, deployment and troubleshooting. If this skill is not installed in the current runtime, apply the Node-RED rules in `AGENTS.md` and use the official Node-RED documentation at `https://nodered.org/docs/`.
- `RPi Freeze Protect Documentation & Evidence Reconciler` whenever documentation, repository state, Pi runtime, CrowPanel state or physical observations disagree, and after meaningful implementation/deployment changes that affect claims in the project evidence.
- Use Superpowers methodology for non-trivial work: brainstorm before behaviour/design changes, systematically debug from the first uncertain boundary, use tests first for code changes, evaluate review feedback technically, and verify before claiming completion.

No skill overrides project safety boundaries, Git discipline, commissioning gates or explicit human approvals.

## Working model

Use `OBSERVE → RECONCILE → PLAN → IMPLEMENT → TEST → DEPLOY → VERIFY → DOCUMENT`.

For faults use `SYMPTOM → SIGNAL PATH → FIRST UNCERTAIN BOUNDARY → TEST → ROOT CAUSE → MINIMAL FIX → REGRESSION TEST → EVIDENCE`. Do not shotgun-debug and do not repeat a test that already proved the same boundary unless the implementation, configuration or hardware changed.

Before changing code or docs, inspect the current branch/HEAD, relevant open PRs, recent history, repository instructions and current evidence. Avoid parallel branches for the same work and preserve unrelated user changes.

## Evidence discipline

Always distinguish:

- `VERIFIED`: directly demonstrated by the cited file, command, log, measurement, runtime observation or physical observation;
- `INFERRED`: strongly indicated but not directly proven;
- `UNKNOWN`: material evidence is missing.

Do not let one evidence class silently prove another. Build success is not hardware verification. HTTP 200 is not GPIO proof. GPIO readback is not valve-position proof. Deployment is not physical commissioning.

Read `docs/PROJECT_STATE.md` before reporting current deployment, firmware, sensor, GPIO or physical status. Treat older plans under `docs/superpowers/plans/` as implementation history, not current runbooks.

## Safety and control authority

The Raspberry Pi control plane is the single safety/control authority. CrowPanel and browser/display clients request intent only. Avoid duplicated state machines in ESP32 firmware, Node-RED and backend services.

Paired actuator invariant:

- `SUPPLY`: GPIO 26 LOW + GPIO 20 LOW
- `DRAIN`: GPIO 26 HIGH + GPIO 20 HIGH
- mixed GPIO 26/20 states are invalid unless an approved ADR supersedes this contract.

DRAIN is the intended safe state, but GPIO state alone does not prove the physical hydraulic path.

Keep the 24 V valve supply disconnected unless Danijel explicitly approves the same bounded physical test in the current conversation. Do not run SUPPLY. Use only the documented timed-shower path after all software gates pass and explicit approval is recorded. Stop on any failed receipt, readback, service check or deployed-flow preflight; request/retain DRAIN and do not retry SUPPLY.

Any actuator design/change must address communication loss, process crash/hang, controller reboot/reset, and power loss/restoration, naming the safe outcome, surviving enforcement mechanism, verification evidence and unresolved gap.

## Node-RED

Node-RED is an authenticated loopback-only bridge, not the safety authority. Do not reintroduce direct GPIO 26/20 output nodes, legacy `/trigger/...` routes, or a second writer. Preserve the `paired_gpio_client.py` → Unix socket → `paired_gpio_daemon.py` path. Keep auth, validation, timeout, retry/idempotency and error handling explicit. Keep secrets out of flow JSON, Function nodes, debug output and Git. Before cutover retain a rollback export and run the deployed-flow preflight exactly as documented in `deployment/COMMISSIONING.md`.

## Raspberry Pi / DietPi / SSH

Primary management path is Windows PowerShell → SSH/SCP → DietPi. Do not assume `raspi-config`. Codex runs on the workstation clone, never on the Pi. Routine remote access uses only the command-restricted `freezeprotect-commission` account and the documented helper allowlist. Do not widen that boundary. Verify SSH host fingerprints out of band; never use `StrictHostKeyChecking=no` as a shortcut.

## ESP32 / CrowPanel

Confirm exact board/revision, PlatformIO environment, framework/library versions, pin mapping and integrated peripherals before firmware changes. Use official Espressif/Elecrow documentation for version-sensitive behaviour. The backend remains authoritative; the display does not own safety policy or GPIO.

## Verification and delivery states

Run the strongest applicable repository checks. For Python changes use the project test suite and Ruff. For commissioning assets also run the commissioning integration test and shell syntax checks. For ESP32 use the exact PlatformIO environment and applicable native tests/build. For Node-RED validate flow JSON/JavaScript and run relevant integration tests.

Use delivery terms precisely: `IMPLEMENTED`, `TESTED`, `INTEGRATED`, `DEPLOYED`, `RUNTIME_VERIFIED`, `COMMISSIONED`. Do not collapse them into one status.

After significant work reconcile README, commissioning/deployment docs, API/flow docs, wiring/pin maps, ADRs and `docs/PROJECT_STATE.md` as applicable. Do not document intended behaviour as already verified.
