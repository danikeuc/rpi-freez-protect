# Final review archive — independent lighting

The initial findings below were closed by the scoped verdict at the end.
The final approval covers disabled source delivery only; hardware activation
remains blocked by the named shared-register gate.

# Whole-branch final review

Reviewed Pi `20dd5ef..ee1ba94c0a5f7785f65cea195baf91fe80ae5551` and Dial `6ecb45a..8e6a9b8c00ea9c004169714bf8fad5b40bfcf152`. Both working trees were clean at the final inspection. Read-only review of production policy/storage/executor/API, ingress assets, native client/admin/UI and input integration, browser source, focused regressions, CI and the supplied review/evidence records. Generated admin HTML and embedded adapter source are mirrors, not independent implementations.

## Findings

### P2 — Browser settings failure removes fresh OFF and return-to-AUTO controls

**Location:** Dial `web/admin_dial.html:207` (`lightRefresh`), with `lightUnknown` at line202 and control admission at line201. Generated counterpart: `idf_app/main/admin_page_dial.h`.

**Scenario:** The display credential is valid and status returns a fresh AUTO/ON or manual observation, while the distinct settings credential fails (or only the settings request times out). The combined try/catch first confirms status, then catches the settings error and calls `lightUnknown()`. This clears `lightRevision` and disables every action, including OFF and Back to AUTO. Every subsequent refresh repeats this. The prior fix corrected the native Dial scheduler, but this separate browser path remains affected.

**Evidence:** A focused Node fixture evaluated the exact production JS block, with only API and DOM dependencies faked. Config returned generation2; status returned revision7, AUTO, desired/gpio ON, healthy; settings returned503. Observed result: `lightStatus.revision=7`, `lightRevision=null`, OFF disabled=true, AUTO disabled=true. No source changes or broad tests were needed to reproduce.

**Fix:** Separate settings failure handling from status failure. Preserve fresh status/revision and permit OFF/Back to AUTO using it. Clear settings revision and confirmed durations when settings become unknown, and disable controls that need those durations. Preserve session/config generation fences and the ten-second status freshness bound. Add a browser regression for valid status plus settings503 in AUTO/ON and manual mode, proving deliberate OFF/BackAUTO reaches the actions route and manual activation stays gated. Regenerate the embedded page.

### P2 — Explicit GPIO coexistence blocker is missing from commissioning instructions

**Location:** Pi `deployment/lighting/README.md:18-25` and canonical spec `docs/superpowers/specs/2026-10-12-independent-lighting-design.md:240-242`. Source evidence: existing `deployment/node-red/paired_gpio_daemon.py:65-70`; new `src/freeze_protect/lighting/executor.py:391-401,412-419`.

**Scenario:** The paired daemon reads all of FSEL2 and later writes its modified snapshot during startup/restart. GPIO20,21,26 share this register. New GPIO21 kernel configuration, or release on close/crash, can occur between that read and write. The stale paired snapshot can restore GPIO21's previous function; conversely a concurrent kernel update can preserve a stale view of the paired pin fields. Requesting only line21 in the new API does not synchronize the existing raw mmap writer. This is a concrete source-level race, even though its exact electrical manifestation has not been tested.

**Fix within this software-only scope:** Add a named, explicit commissioning blocker across the canonical spec, deployment/runbooks, evidence and activation-marker instructions: do not enable the candidate GPIO21 executor alongside the current mmap paired daemon until a separately reviewed architecture eliminates uncoordinated shared-register updates and the required regression/physical acceptance evidence exists. Keep templates disabled and describe per-line API ownership accurately, without claiming it establishes whole-system physical isolation. Initial service ordering alone cannot cover later restarts or crash release; a userspace lock alone cannot cover uncoordinated kernel cleanup. Do not silently rewrite the paired backend in this fix: that needs separate review of paired atomic output/lease behavior and exceeds this additive implementation's safe scope.

The disabled flow, deny-all gateway and opt-in service/hardware configuration prevent current deployment. Therefore this is a missing explicit source-delivery gate, not a claim that installed shower behavior has already regressed. Merely repeating a generic hardware-test prerequisite is insufficient to record this known architectural conflict.

## Strengths and verification assessment

- Pi serializes mutations, persists replay identity before ON, separates control/settings fences, preserves uncertain outcomes, clears old holds on recovery and requires a new deliberate intent. Existing closed OFF-fence/revision findings remain closed on source inspection.
- The lease executor uses bounded frames, client budgets, generation/lease/OFF fences and no automatic ON retry. Storage/history and camera/display/settings credentials are separate from shower state.
- Camera ingress retains original identity/time, uses a distinct authenticated ingress role and fixed loopback destination, sanitizes responses and provides disabled profile-specific assets. Actual Protect compatibility remains explicitly unclaimed.
- Native Dial and admin worker have bounded admission, captured generation/session fencing, a pre-body expiry check and late-result disposal. Reference ownership of asynchronous request jobs survives timeout/callback ordering. The native settings failure scheduling correction is present and its regression exercises production UI scheduling.
- Browser configuration/action binding now preserves the observed host identity. Native page/input changes contain light touch and encoder handling, while Roon and QGSQ routing are unchanged in the reviewed delta. History is rendered as text. Private credentials are not returned to the browser.
- Reported Pi739 tests/Ruff/mypy34/package build, nine adapter tests, native/browser/BLE checks and exact ESP-IDF5.5.5 build are consistent with the inspected test/source paths. These broad PASS results are implementation evidence, not independent reruns. Existing browser tests do not cover the settings-failure finding above.

## Ready-to-merge verdict

**CHANGES REQUIRED** for the two P2 findings. After their focused fixes and scoped review, this can be approved as disabled software/source delivery, with explicit commissioning blockers retained. This review authorizes no merge, deployment, flash, GPIO access or release. No additional blocking implementation defect was identified in the reviewed integration paths.

## Declined to judge

- Actual lamp/driver/contact rating, mains wiring, board revision, bias and electrical safety.
- GPIO crash/boot/reset/power behavior, mixed-valve transients, contact cutoff bounds or physical independence. Fake line tests and source inspection cannot establish them.
- Whether a future paired-backend replacement preserves simultaneous paired output behavior; no such replacement is included or approved here.
- Actual installed Protect payload/identity/retry/authentication profile, Node-RED runtime inventory or commissioned network rate/allowlist/TLS policy.
- Actual LVGL display geometry, touch/encoder usability, on-device resource headroom and exact-artifact flashing acceptance.
- Hosted CI execution, deployment readiness or release approval. Broad verification claims were reviewed from reports rather than rerun.

Only this review report was written. No production/test source, index, HEAD, service, device or release was changed.


---

# Scoped final fix review

Verdict: **APPROVED for disabled software/source delivery only.** Both final-review P2 findings are closed within the requested fix scope. No remaining blocking source defect or fix-caused regression was identified in this review. Hardware activation remains blocked by design.

Reviewed exact clean source HEADs: Pi `26a22ec67081a5e352a80d6c24059e8b91b9f0db` against `ee1ba94`; Dial `6a5e03ed3a1b26a61536d602c697795f2444bccb` against `8e6a9b8`. Scope was the two findings in `final-review.md`, their `final-fix.diff`, completed `final-fix-report.md`, final source and directly affected evidence. No broad suites were rerun.

## Finding 1 — browser settings failure: CLOSED

Dial `web/admin_dial.html:201,208` now handles settings errors separately after confirmed status. Settings503 and malformed settings DTOs clear the settings revision and both confirmed duration caches. Timed/manual controls and settings save are gated, while fresh AUTO/ON status retains revision and deliberate OFF; fresh manual status retains Back to AUTO. Action requests still capture the observed revision and configuration generation (`:211`). The settings catch does not refresh the receipt time or restore a status that has expired (`:204-208`). Epoch/session checks remain in place (`:207-208`); production API401 invokes `authLost`, which resets light state (`:22-23`).

Committed browser regressions at `tests/admin_dial/test_light_admin.cjs:25-26` cover AUTO/ON plus settings503, deliberate OFF reaching the actions route, manual plus settings503, deliberate BackAUTO, cache clearing and activation gating at desktop/mobile widths. Their reported RED/GREEN evidence was inspected, not repeated as a broad suite.

Independent focused in-memory Node fixture evaluated the exact production lighting JavaScript with fake DOM/API/clock dependencies. PASS: valid settings followed by malformed settings clears both cached durations and settings revision; OFF/BackAUTO each reach the actions route with revision7 and the observed generation; timed/manual controls remain disabled; a pending settings failure after ten seconds leaves the expired status disabled without changing its receipt; a session reset rejects a late settings failure; a new configuration generation is bound to subsequent requests. No live service was contacted. The fixture used settings503, not status503; status failure handling remains the original outer path.

Generated `idf_app/main/admin_page_dial.h` ADMIN_PAGE decodes exactly to canonical `web/admin_dial.html` (81,466 characters). No firmware/native source beyond the embedded page changed in this wave.

## Finding 2 — GPIO_SHARED_FSEL2_COEXISTENCE: CLOSED as a source-delivery gate

Canonical spec `docs/superpowers/specs/2026-10-12-independent-lighting-design.md:232-238,248`, deployment `deployment/lighting/README.md:51-57`, Pi operations `docs/operations/independent-lighting-node-red.md:57-61`, evidence `docs/evidence/2026-10-13-independent-lighting-implementation.md:110-114` and state `docs/PROJECT_STATE.md:430-434` explicitly prohibit enabling candidate GPIO21 alongside the current paired mmap backend. Companion Dial operations `docs/operations/independent-lighting.md:33-37` repeats the prohibition.

Environment activation comments (`deployment/lighting/environment.example:8-13`) and both service marker comments (`light-controller.service:3-7`, `light-gpio.service:3-7`) name the blocker. The main instructions explicitly forbid creating the commissioned marker, setting GPIO21 enabled or granting DeviceAllow while it is open. Closure requires a separately reviewed architecture removing uncoordinated shared-register updates plus startup/restart/request/release/crash regressions and physical acceptance preserving paired atomic output/lease behavior.

Inspected source confirms the recorded basis: paired daemon reads/writes a complete FSEL2 snapshot (`deployment/node-red/paired_gpio_daemon.py:65-70`), while gpiod requests/releases GPIO21 (`src/freeze_protect/lighting/executor.py:391-401,412-419`). Wording distinguishes requested-line ownership from whole-system isolation and explicitly rejects initial ordering or userspace locking alone as sufficient to coordinate kernel cleanup. No physical manifestation is claimed verified and no paired backend rewrite is included.

Both service markers remain required, neither unit has an Install section, environment activation fields remain empty, the exported flow tab remains disabled, and gateway locations retain deny-all admission.

## Verification and limits

Both scoped patches pass `git diff --check`. Independently read binary SHA256 matches the reported exact Dial build: `78c0280d7f8af62f7e529c239e110c3972b2f5901db5a153a62743f940610f47`. ESP-IDF5.5.5 build PASS is supplied build evidence; this review did not rebuild firmware.

Residual activation blockers remain: the named GPIO coexistence architecture/regression/physical acceptance gate and existing wiring/power/GPIO/Protect and device acceptance requirements. This verdict establishes source-candidate readiness only. It authorizes no installation, activation, deployment, GPIO access, flash, merge, push or release.

Only this review report was written. No source, test, Git index/HEAD, service or device was changed; no subagents were spawned.
