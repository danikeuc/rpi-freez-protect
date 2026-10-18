# GPIO21 Bench Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Let the existing restricted maintenance status command report sanitized GPIO21 bench evidence without operator copy/paste of private diagnostics.

**Architecture:** Add a read-only field to the current maintenance helper. Select evidence only through the existing root-owned bench marker; validate and project fixed schemas. A separately reviewed root-console updater replaces only helper code; existing dispatcher, sudoers, migration authority and GPIO behavior remain unchanged.

**Tech Stack:** Python standard library, pytest, existing restricted OpenSSH helper.

**Spec:** `deployment/maintenance-access/LIGHT_BENCH_DIAGNOSTICS.md`

## Global Constraints

- Implementation prepared; no deployment or expanded access is claimed.
- Exact remote command remains `sudo -n /usr/local/sbin/freeze-protect-maintenance status` with no extra arguments.
- Evidence marker: `/root/light-gpio21-commissioning.started`.
- Evidence directory format: `/root/light-gpio21-bench.[A-Za-z0-9_]+`.
- Fixed members only: `receipt.json`, `samples.json`, `diagnostic.json`.
- No raw logs, arbitrary paths, exception payloads, environment values or credentials in public output.
- No GPIO access, actuation, marker deletion, test rerun, service restart, package migration, SSH policy or sudoers mutation.
- Stored samples are historical point observations, not current hardware or physical acceptance.

## Review Focus

1. Interrupted bench with marker but missing receipt: report INCOMPLETE, not success (Task 1).
2. Symlink, FIFO, unsafe ownership or path substitution: refuse without reading unrelated content or hanging (Task 1).
3. Huge, malformed or secret-bearing JSON fields: bounded parse and allowlisted projection, no raw echo (Task 1).
4. Failed new section: preserve existing status fields and old command semantics (Task 1).
5. Interrupted updater or unexpected deployed baseline: stop with backup/phase evidence, never silently broaden or retry (Task 2).

## Task 1: Bounded evidence projection and status integration

**Files:** Modify `deployment/maintenance-access/maintenance.py`; create `tests/unit/test_light_bench_diagnostics.py`.

**Interfaces:** `light_bench_diagnostic() -> dict` produces `diagnostic()['light_gpio21_bench']`. Production paths are constants, never SSH arguments or environment overrides. Internal pure function `summarize_light_bench(receipt: dict, rows: list, diagnostic: dict | None) -> dict` supports fixture testing.

- [x] Write failing fixture tests `test_level_mismatch_preserves_first_failure_and_final_off`, `test_missing_marker_not_requested`, `test_marker_without_receipt_incomplete`, `test_untrusted_paths_rejected`, `test_nonregular_and_oversize_files_rejected`, `test_malformed_or_extra_fields_never_echo_payload`, `test_invalid_section_preserves_existing_status`.
- [x] Run `.venv/bin/python -m pytest -q tests/unit/test_light_bench_diagnostics.py`; require failure from absent behavior.
- [x] Implement descriptor-based bounded reads using O_NOFOLLOW/O_NONBLOCK, fstat regular-file/root-owner/non-group-or-world-writable validation, anchored directory descriptors and root-controlled ancestors. Reject links, traversal and paths outside the fixed directory pattern. Limits: marker 256 bytes, receipt/diagnostic 32 KiB each, samples 2 MiB and 10,000 rows. Read at most limit+1; do not trust stat size alone. In-progress/changing evidence returns INCOMPLETE rather than a conclusive result.
- [x] Validate phase names from the bench: startup_off, on, command_off, normal_release, on_before_crash, crash_release, final_owned_off, final_released_off. Pin keys exactly20,21,26; levels exact integers0/1 and functions0..7 (reject bool). Pair expectation output/high; GPIO21 expected low only in on/on_before_crash. Release phases allow function0/1; other phases require1. First failing sample retains phase and all three pins.
- [x] Return only fixed status codes, allowlisted bench result, exact boolean receipt fields, evidence basename, sample count, first failure and at most eight phase summaries (first/last pins and mismatch count). Unknown results/types become UNCLASSIFIED. Exception frames only known basenames commission_gpio21.py/operator_checks.py and positive integer lines, at most12; no arbitrary exception message. Missing diagnostic is normal for a success receipt. Never elevate physical_acceptance above NOT_VERIFIED or imply forwarding enabled.
- [x] Add tests for success, each expected phase, paired mismatch, missing phases, interrupted evidence, invalid booleans, NaN/nonfinite time, overflow/truncation and arbitrary frame/phase/result strings. Diagnostic reads must issue no subprocess or device calls. Existing overall status subprocess calls remain unchanged.
- [x] Run focused tests and existing maintenance tests; require pass. Commit only tested helper and test changes.

## Task 2: Reviewed root-console updater

**Files:** Create `deployment/maintenance-access/update_light_diagnostics.py`, `tests/unit/test_light_diagnostic_update.py`; use `update_diagnostics.py` as historical reference, not as a ready installer.

**Interfaces:** No-argument root-only updater consumes fixed manifest/files beside itself and emits a backup path and `LIGHT_DIAGNOSTICS_UPDATED` only after verification. Target remains `/usr/local/lib/freeze-protect-maintenance-v1/maintenance.py`.

- [x] Write failing tests for wrong host/root/baseline, changed candidate, symlink paths, busy operation lock, failed preview, replacement failure and failed post-check. Assert no GPIO/service/policy mutations and backup precedes replacement.
- [x] Obtain deployed helper hash through a trusted source before pinning the update; previous source hashes are insufficient. If unavailable through allowed diagnostics, the root console must provide this one baseline hash. Do not bypass forced-command access or accept an arbitrary baseline silently.
- [x] Implement a root-owned hash-verified bundle using the existing private backup, operation lock, candidate preview, atomic replace and file/directory fsync patterns. Validate baseline again under lock immediately before replacement. Record before/after SHA256 and phases; catch errors with fixed codes only. Preserve target mode/owner. No automatic rollback or rerun; after any post-replacement failure retain explicit changed/unknown status.
- [x] Preview checks existing fields plus light_gpio21_bench; post-check invokes only the exact installed status helper. Include the helper hash in its fixed artifact list so subsequent remote checks can verify deployment. Validate outcome via current actual files after interruption.
- [x] Run new tests, full `.venv/bin/python -m pytest -q`, `.venv/bin/python -m ruff check .`, and `git diff --check`. Review independently before preparing a package. Build checksum/manifest only from the reviewed version; provide exact transfer command and digest, not placeholders.

## Task 3: Operator handoff and remote acceptance

**Files:** Update `deployment/maintenance-access/LIGHT_BENCH_DIAGNOSTICS.md`, `deployment/maintenance-access/README.md`, `docs/PROJECT_STATE.md`, `deployment/WORKSTATION_CODEX_COMMISSIONING.md`, `deployment/workstation-codex/CODEX_COMMISSIONING_PROMPT.md`; create `docs/evidence/2026-10-15-light-bench-diagnostics.md` when deployment evidence exists.

**Interfaces:** Owner executes the reviewed root-console update once; Codex uses the existing restricted status command from a separate SSH connection.

- [x] Before deployment, mark package as prepared, not installed; keep old permissions and instructions truthful. Preserve existing unrelated working-tree changes.
- [x] Supply one verified operator command block for package retrieval/check/install. Keep the root recovery console open.
- [x] After the operator receipt, fetch status remotely with the existing dedicated key, BatchMode and StrictHostKeyChecking=yes. Verify helper hash, legacy fields, bench outcome and first failed phase. Verify harmless extra-argument status rejection; never invoke prepare/install as a connectivity test.
- [x] Record live acceptance separately from software tests; update docs only to demonstrated capability. If rejected or missing, diagnose the update without guessing GPIO behavior or retrying the bench.
- [x] Use the retrieved evidence to continue the separate GPIO21 root-cause task. This access update does not satisfy relay commissioning or enable camera forwarding.

## Execution status

Tasks1 and2 complete; review fixes verified,993 tests pass. Task3 complete: package installed by owner, new helper hash and READ evidence verified via separate restricted SSH; extra arguments rejected. GPIO21 crash_release failure localized. Physical acceptance and camera forwarding remain unverified/disabled.
