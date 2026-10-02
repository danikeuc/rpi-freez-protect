# Shower interruption safety implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reject old renewal after daemon DRAIN/restart and expire unsent Dial START at ten seconds.
**Architecture:** Explicit begin/renew through the existing paired actuator path, plus monotonic client admission. Keep the display API and single GPIO owner.
**Tech Stack:** Python, Node-RED Function JavaScript/JSON, C/ESP-IDF5.5.5 ESP32-S3.
**Spec:** docs/superpowers/specs/2026-10-02-shower-interruption-safety-design.md

## Global Constraints

- Existing isolated branches codex/dial-admin-settings; Pi base c2b353be6e882448b182205cda7baf2abbbe98da, Dial base f7107b78c96c1489e120507321ac164ffe90435c.
- Repository/simulated I/O only. No live API, GPIO, SSH, deployment, flash, merge, release, or credential disclosure.
- DRAIN/SUPPLY coupled pair invariant; keep Pi timer and independent daemon lease owners.
- All old and new delivery states distinguished; no test result implies physical behavior.

## Review Focus

- Bridge startup DRAIN must not authorize an old renew; Task1 tests expiry and daemon restart followed by startup DRAIN.
- An old downstream component must not energize before protocol mismatch discovery; Task1 verifies startup DRAIN capability and mixed versions before first SUPPLY.
- Repeated begin or fallback after rejected renew must not create a new timer; Task1 command traces assert absence of low writes and cleared Hub timer.
- Expiry during preflight versus a late response after an already-sent POST; Task2 separates admission from callback delivery.
- Lost receipts/readback failure and clock boundary must preserve fail-closed state; Task1 failure fixtures and Task2 exact boundary/backwards clock cases.

### Task 1: Strict paired lease protocol end to end

**Files:** src/freeze_protect/domain/models.py, application/ports.py, application/service.py, adapters/node_red.py, adapters/simulation.py, api/app.py; deployment/node-red/paired_gpio_daemon.py, paired_gpio_client.py, freeze-protect-paired-relay.json; relevant tests/unit/test_m1_service.py, test_node_red.py, integration/test_paired_gpio_daemon.py, test_node_red_flow.py and new executable flow/service-daemon fixtures; docs/operations/dial-admin-settings.md and deployment/COMMISSIONING.md when needed.
**Interfaces:** Add SupplyAction BEGIN/RENEW enum with wire values begin/renew, protocol_version2 receipt field, and command(command, *, supply_action=None) port. DRAIN carries no action. Simulation and all test adapters use the actual new signature. The stand-alone daemon/client duplicate protocol literals deliberately at their deployment boundary and cross-contract tests verify agreement.
- [ ] Write behavioral failing tests against current real service/daemon/flow functions for expired/restarted lease renewal and compatibility rejection.
- [ ] Implement the strict spec across service, port, driver, bridge/client/daemon; preserve automatic semantics and authenticated DRAIN availability.
- [ ] Run targeted tests then full .venv/bin/python -m pytest -q, Ruff, mypy; commissioning assets test for changed deployment files, syntax-check modified scripts/JSON/Function code and execute actual Function handlers with faked Node context.
- [ ] Document coordinated drained upgrade/rollback and four fault limits, preserving historical evidence.
- [ ] Commit and report exact SHA, RED/GREEN commands/traces and limitations; independent task review before Task2.

### Task 2: Dial START age admission

**Files:** /mnt/c/users/danik/projects/roon-knob-valves/idf_app/main/valve_client_dial.c and .h; tests/valve_dial/test_valve_logic.c and integration fixture as required; docs/operations/dial-admin-settings.md.
**Interfaces:** work item captures uint64_t monotonic enqueue time; production esp_timer_get_time and test clock injection. Preserve existing public routes, result enums and callback session/config IDs. A timeout completion indicates rejection before transport. Existing work_allowed remains session/config validity, not response-age filtering.
- [ ] Write failing real-worker/transport tests for9999/10000ms, preflightcrossing, backwardsclock, DRAIN unaffected, late POST response and disconnect/reconnect.
- [ ] Implement expiry checks at dispatch and postpreflight; no retries or Pi cancellation, preserve request reconciliation.
- [ ] Run canonical valve/admin suites and full local shared block if dependency inventory changes, exact ESP-IDF5.5.5 build; update only exact legitimate dependency edges if a new include appears.
- [ ] Document admission/network limits and commit; independent task review.

### Task 3: Combined review and candidate delivery

- [ ] Review both safety diffs and test reports once, including negative evidence and mixed-version rollout; fix concrete findings with focused tests.
- [ ] Refresh Pi packages and exact Dial build/artifact manifest after final sources, preserve baseline hashes, record source identities separately from physical evidence.
- [ ] Update existing draft PR22 and PR10 with review/dissent, exact heads, verification and remaining external/hardware gates; no merge or deployment.
