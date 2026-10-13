# Paired GPIO migration package final integration review

Date: 2026-10-13. Reviewed b329a249cd8515ff3ae36508dd2dd8e0c8984388..723f6526c9169b9879f2612822b9cd71eb603b68 against the complete paired migration spec and plan.

## Strengths

- The preparation/install boundary is explicit: a fixed eleven-file manifest, exact wheel and base-unit pins, protected paths, isolated copied-interpreter venv, and an identity receipt bind the candidate to the host boot, reviewed baseline and prepared environment (`deployment/paired-gpio-migration/migrate.py:55`, `:176`, `:235`, `:254`). Hub dependencies remain separate.
- The service-account probe receives the candidate source through stdin and invokes its actual platform validator without constructing a GPIO owner or mapping candidate MMIO (`deployment/paired-gpio-migration/migrate.py:197`, `:228`). This avoids the inaccessible private staging-directory problem. The existing read-only pinctrl observation is explicitly reconciled in the spec and README.
- Exact base-unit/dropin validation accepts and preserves the Hub readiness gate, rejects unknown overrides and lighting configurations, verifies USER_OFF and durable settings, and checks actual environment, flow and package state before cutover (`deployment/paired-gpio-migration/migrate.py:90`, `:104`, `:127`).
- Durable file/database backup precedes current-attempt cleanup authority and service changes (`deployment/paired-gpio-migration/migrate.py:262`, `:360`). The ordering stops Hub, establishes paired DRAIN, stops the old owner, checks MainPID/high-high, expires the prior 1.5-second request window with a two-second wait, and only then replaces assets. Startup socket readiness follows the daemon's startup DRAIN; kernel consumers and process identity are checked before Hub restarts through its preserved readiness gate (`:374`, `:377`, `:382`; `deployment/node-red/paired_gpio_daemon.py:398`, `:420`).
- Historical evidence cannot authorize cleanup. Current-invocation state is armed only after durable INSTALL_STARTED completion, and used evidence is rejected without contamination (`deployment/paired-gpio-migration/migrate.py:364`, `:406`, `:467`). Failed receipts/readbacks latch against installer DRAIN retries (`deployment/paired-gpio-migration/operator_checks.py:171`).
- The new regressions cross real filesystem/SQLite boundaries and check preservation of old assets and recovery evidence after partial replacement, without executing real services or GPIO (`tests/integration/test_paired_gpio_migration.py:252`, `:332`, `:369`, `:417`). Both earlier Important findings are closed.
- The fixed service override adds only the inventoried chip permission and isolated interpreter. Restart=no and its loss of automatic process recovery are explicitly disclosed; the README preserves the distinction between GPIO readback and physical position (`deployment/paired-gpio-migration/paired-gpio.conf:7`, `:12`; `deployment/paired-gpio-migration/README.md:73`).

## Issues

### Critical / Important

None identified in the completed source/package-plan integration. No new blocker and no reopened task-review finding.

### Minor

1. **P3 - Bounded diagnostics remain a useful follow-up.** `deployment/paired-gpio-migration/migrate.py:437` and `:440` expose only prepare/install and STOP_INSPECT_PRIVATE_EVIDENCE for most failures. Private traceback retention and the explicit stop instruction make this acceptable for the trusted-console handoff, but a local operator must inspect private evidence to distinguish a guard rejection from backup, replacement or readiness failure. Add internal phase names and an explicit allowlist of safe diagnostic codes in a separate change; retain arbitrary exception text privately and extend `tests/integration/test_paired_gpio_migration.py:83`. This is nonblocking and is calibrated as P3, rather than the original note's P2 label.
2. **P3 - Existing dependency warning remains separate maintenance.** `docs/evidence/2026-10-13-paired-gpio-migration-package.md:38` honestly records the existing Starlette/httpx warning. It is not demonstrated to be a migration regression. Resolve its dependency compatibility separately; no installer repair or additional rerun is justified by this warning alone.

## Verification assessed

Read the spec, complete plan, final review package and all changed implementation/test content, fetching source separately where combined tool output was truncated. Read scratch progress, implementation report, initial task review and scoped fix review, the commissioning boundaries, project ledger, prior GPIO source final review and the unchanged daemon/systemd/readiness contracts relevant to this migration. Confirmed current HEAD is the requested 723f6526c9169b9879f2612822b9cd71eb603b68; the initial source working tree was clean.

The recorded final source checks are 815 pytest passes (including the commissioning 110), Ruff PASS and diff checks PASS, with one existing warning. The focused repair report records 37 passes. Inspection of the actual regression assertions supports the reported historical-cleanup and durability fixes. No suites were repeated and no new test-run claim is made. No shell script changed.

Controller reports the final refreshed eleven-entry manifest, fourteen-member archive, byte/membership checks and downloaded archive hash afd651cd13d8b088a5dea31e427ee9844062981ef52a436e49b7d79f27e2b45a. This review evaluates the source contracts; artifact assembly verification remains the controller's separate evidence, not an independent reviewer rerun.

## Declined to judge

- Actual target prepare/install receipts, installed interpreter/libgpiod behavior, DAC/cgroup/systemd runtime formatting and permissions, currently deployed hashes/flows/services, and rollback execution: no device or service access was allowed; operator gates remain mandatory.
- Final delivered archive identity and transport bytes: controller owns and reports the refreshed manifest/archive/download checks; the earlier staged installer was explicitly obsolete and was not treated as reviewed source.
- Electrical behavior, contact/valve position, simultaneity during acquire/reconfigure/release, process crash/hang/reset and each power-loss/restoration domain: source and fake-boundary tests cannot prove physical behavior; both loads remain disconnected and acceptance is separately authorized.
- A new full review of unrelated lighting, Protect/Dial/Roon/UI or firmware behavior: outside this migration plan; only the disabled-lighting and paired-service integration boundaries were assessed.
- Unsupported profiles, arbitrary privileged/raw-MMIO writers and concurrent trusted-root edits: this package supports the exact inventoried profile and protected-console envelope, not universal hardware support or isolation from a hostile root process.
- New pytest/Ruff/commissioning/firmware or live validation results: existing successful runs were assessed; no concrete unresolved source doubt required repeating them.

## Assessment

**Ready for trusted-console package handoff: YES. Specification compliance: PASS. Code quality/integration: PASS with the two nonblocking follow-ups above.**

The completed implementation matches the authorized two-stage migration plan and closes the earlier cleanup-replay and durability-test defects. The controller can close final-review status and complete the reviewed package handoff. Actual preparation and installation remain operator-run and receipt-gated; this verdict does not establish successful device migration, physical acceptance, lighting activation or release.

Only this requested scratch report was written. Source, index, HEAD and branch state were not changed. No device/network/service operation, actuation, dependency install, firmware task or subagent was performed.
