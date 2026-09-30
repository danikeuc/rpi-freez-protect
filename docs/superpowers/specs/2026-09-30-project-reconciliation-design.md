# Project reconciliation design

**Date:** 2026-09-30
**Scope:** repository structure, current documentation, repeatable verification and evidence reconciliation for `rpi-freez-protect`.

## Objective

Make the repository a clear source for development and commissioning without turning source files into claims about deployed or physical state. Preserve the fail-safe valve contract and separate active Waveshare integration from historical CrowPanel material.

## Evidence boundary

The project uses four evidence classes:

1. **Repository:** files, commits, static checks and simulated tests.
2. **Deployed Raspberry Pi:** service state, effective configuration, listeners, installed files and GPIO readback observed on the Pi.
3. **Display/Roon device:** firmware identity, serial output and user-observed control behavior.
4. **Physical installation:** 24 V state, relay contacts, valve movement and plumbing path observed at the installation.

A result in one class never proves another class. In particular, GPIO readback proves output levels only and cannot establish physical valve position.

## Current system boundary

The active control path is:

`Waveshare dial -> trusted-LAN Nginx :8081 -> loopback Hub :8000 -> loopback Node-RED :1880 -> Unix-socket paired GPIO daemon -> BCM 26 + 20`

The active mode is `manual_timed`. Idle and failure behavior request `DRAIN`; one authenticated deliberate action permits a fixed 600-second `SUPPLY` interval. Node-RED does not own policy or timers. The paired daemon is the only GPIO writer and bounds every `SUPPLY` with a 60-second lease.

Roon control is a separate display function implemented by the `roon-knob` and `roon-control` repositories. It shares the physical dial but does not share the valve actuator path.

The CrowPanel firmware in this repository is retained as historical and rollback source. It is not the active display for this installation and must not receive the rotated display token.

## Repository organization

- `README.md`: short orientation, safety contract, active architecture and document index.
- `docs/ARCHITECTURE.md`: component ownership, trust boundaries and failure behavior.
- `docs/PROJECT_STATE.md`: dated evidence ledger with verified, inferred and unknown facts.
- `docs/VERIFICATION.md`: repeatable repository checks and the limits of each check.
- `deployment/COMMISSIONING.md`: current Pi and hardware runbook.
- `deployment/DISPLAY_COMMISSIONING.md`: current Waveshare cutover and acceptance boundary.
- `deployment/CROWPANEL_COMMISSIONING.md`: clearly historical CrowPanel procedure.
- `deployment/WORKSTATION_CODEX_COMMISSIONING.md`: restricted access and operator handoff.
- `docs/superpowers/specs` and `docs/superpowers/plans`: decision and implementation history, never current runbooks.

## Verification design

CI will run the same repository-only checks documented for local development:

- complete Python tests;
- Ruff and strict mypy;
- package build;
- Node-RED JSON structure and JavaScript syntax;
- POSIX shell syntax;
- internal Markdown-link validation;
- Git whitespace check.

The four SSH rollback tests will remain behavior tests but will simulate the expected privileged owner in their extracted shell snippets. Production code will continue to require UID 0 and use root-owned installation commands. Static assertions retain coverage of those production requirements.

## Safety and deployment boundary

This reconciliation changes repository files only. It does not connect 24 V, run `SUPPLY`, alter GPIO, restart a service, deploy to the Pi or flash firmware. Deployment remains a separate reviewed operation using the documented runbooks.
