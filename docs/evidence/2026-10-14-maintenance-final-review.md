# Independent final review

## Verdict and scope

PASS_WITH_ADVISORIES. No actionable P0, P1 or P2 finding in the reviewed maintenance/recovery and lighting-inventory integration.

Reviewed 2026-10-14 in `/home/danik/.codex/worktrees/knob-valves-design/rpi-freez-protect`: HEAD/base `d19cf89599ce10d32f26e6344223dc56b3d99845`, plus all 29 tracked/untracked delivery files present in the current delta. The sorted JSON mapping of those paths to SHA256 hashes has SHA256 `edbfac648fd5c5a8a5a1db54e5993662c9e9575a9f1e70c3a47eefbff2a29eea`. This report and the ignored progress ledger are outside that delivery snapshot. Important reviewed source identities: inventory `c804f9d2114570b164bfaa57905d69a96f287076ce17a4309b8e4f1009a6e179`, maintenance `df06b46bd206dbadbbbd201aeb80529df9deb790b7df448b29e1ff2ba15c6a9c`, migration `e2e741857ed62bc69af229239b93dc234795e3d13d8792831f7ea64f1b97c8d8`.

Authoritative inputs: root AGENTS.md; both workstation commissioning instructions; current PROJECT_STATE.md; lighting continuation plan and progress ledger; independent-lighting design specification. Applied independent-engineering-reviewer skill. The prior complete lighting-policy review was not repeated.

## Material findings

None. No new blocker, P1 or P2 is asserted.

## Requirements and evidence checked

| Requirement | Executable path and test evidence inspected | Assessment |
| --- | --- | --- |
| Exact restricted maintenance authority | install_access.extended_dispatch, fixed SUDO_BYTES, isolated launcher, maintenance.main/request/verified_package; test_maintenance_access exact-command, extra-argument, package-mismatch, baseline and installer-failure cases | No arbitrary caller-controlled command, package, service or path reaches privileged execution. Original dispatcher forms preserved. Root-controlled manifests are operator trust inputs, not remote authorization. |
| Durable one-shot submission and worker | record uses exclusive creation and fsync before dispatch; worker claim precedes child execution; operation lock serializes submitter/worker; boot/expiry checks; concurrency and failed-dispatch tests | Ambiguous or failed work stays consumed; status distinguishes submission from verification. No remote renewal/reset. |
| Evidence-preserving recovery | Both recovery execute/preflight paths; original archive/artifact/backup/boot/venv/failure validation; separate exclusive recovery directory; tests for replay, modified baseline, failed preflight, historical receipts and DRAIN failure | No original failure is rewritten. Hub continuation starts only Hub after verifying the running pair. Failed receipt/readback suppresses subsequent cleanup DRAIN. |
| DeviceAllow normalization | migrate.verify_effective_pair and both-order/duplicate/extra/missing/permission tests | Sorting preserves exact multiset equality and does not permit widened access. |
| Readiness retry boundary | wait_hub_status plus actual operator_checks.status GET producer; refusal, timeout, DNS, HTTP, invalid-state, deadline and exit tests | Only ECONNREFUSED transport errors retry while Hub remains active with a positive PID. The retry body repeats status reads, not startup or actuation. |
| Read-only, sanitized inventory | fixed COMMANDS/GPIO_PROBE, flow_summary, startup_summary, collect; all inventory tests | No GPIO line request/value change, settings execution or flow mutation. Untrusted text becomes hashes, counts, fixed booleans or numeric versions; malformed/missing GPIO fields become NOT_OBSERVED. |
| Source/runtime/physical boundaries | Current state, evidence records, migration/access/recovery runbooks, lighting spec/runbook and inventory handoff | Installed paired prerequisite is distinct from lighting deployment and physical acceptance. Historical failures remain visible. Settings, active project, camera profile and physical gates remain open. |

Plan/spec/ledger references resolve. Plan tasks 2 and 3 have concrete source/tests/docs. Target inventory, effective configuration and physical commissioning remain future gates; the inventory report explicitly cannot establish those by evaluating settings or inferring free hardware from unknown metadata. A used=false observation is not a reservation.

## Minor advisory

P3 / STALE_DOCUMENTATION / PROJECT_CONTRACT — `docs/PROJECT_STATE.md:69-78` narrates earlier migration and Hub-recovery checkpoints using present-tense “remains unconfirmed” and “target continuation and acceptance remain pending”, below the current successful recovery section. A reader following that subsection alone can mistake preserved history for the latest status. Mark this paragraph explicitly as historical through the readiness failure, or change those sentences to past tense and link to the successful checkpoint. This is non-blocking because the canonical top checkpoint clearly records the success, preserves failed evidence and keeps physical/lighting acceptance open.

## Verification and limits

This review inspected source, surrounding operator checks, regression assertions and current documentary evidence. It did not modify production/test files, contact devices, run SSH, execute privileged helpers, or repeat the root agent's broad test suite. The root agent reported fresh full pytest: 902 passed, one existing Starlette/httpx deprecation warning (16.15 seconds); Ruff passed; configured mypy passed for 34 source files; focused inventory tests: 13 passed. A trailing blank line in the Node-RED operations document was corrected, followed by clean git diff --check. These current executions are root-agent evidence, not independent reruns; no source change after the suite was reported. Historical suite counts were not substituted for current results.

Python project floor is >=3.12; target migration pins Python 3.13.5/aarch64 and the reviewed gpiod wheel. Checked explicit boolean validation, exception redaction, subprocess argument/environment isolation, file/lock lifecycle, durable write ordering, cancellation cleanup and process-level serialization. No GIL-dependent assumption supports this verdict.

## Declined judgments

- No fresh target or physical attestation: restricted-SSH observations are recorded evidence supplied by the parent workflow, not independently repeated by this reviewer. Private SUCCESS.json content was not exported; its existence and the reviewed producer's gates are the documented evidence boundary.
- No assertion that GPIO high means valve position, or that line-21 metadata proves wiring/readiness, independence through crash/reboot, or a safe live load.
- No new full lighting-policy, companion Dial firmware or Protect-provider assessment; those are outside this final integration review.
- No speculative blocker for root changing a trusted package/manifest, a theoretical hostile hardware driver, or style issues already covered by project tooling.

Only this requested review artifact was written. No git staging, commit, release or device action was performed.
