# GPIO21 remote evidence reader preparation — 2026-10-15

## Baseline and authority

Owner supplied deployed helper SHA256
df06b46bd206dbadbbbd201aeb80529df9deb790b7df448b29e1ff2ba15c6a9c;
it matches the original local maintenance.py bytes. The approved next step is a
reviewed root-console update, not arbitrary root SSH. No Pi mutations performed.

## Implementation ledger

- Task 1 RED: absent reader produced23 failures/8 fixture errors.
- Task 1 implementation: bounded descriptor reads, schema projection, fixed status
  field and artifact hash; original migration command paths unchanged.
- Task 2 RED: updater module absent; collection failed as expected.
- Task 2 implementation: exact baseline pin, root-console preview, private backup,
  atomic replacement and installed helper verification. All72 initial focused
  tests passed before additional coverage.
- Ruling: keep the existing helper file self-contained so this update needs no
  new executable, dispatcher or sudoers entry.
- Ruling: changed evidence returns UNAVAILABLE_OR_INVALID; missing final evidence
  returns INCOMPLETE. Neither outcome is acceptance.
- Ruling: retain the plan and evidence as operator documentation; no remote
  activation claim until a separate SSH status read verifies the new hash.
- Current hardware receipt remains LIGHT_LEVEL_MISMATCH with final_off_readback
  true. Phase/root cause still unknown; no bench retry or automation enablement.

## Final verification

Independent reviewer found two updater gaps: candidate bytes were reread between
hash/preview/install, and legacy status fields were not required. Eight new
regressions failed before the fix and passed after it. Preview now executes the
verified byte snapshot (no path import/cache), and postcheck requires the original
package hash, old fields/units/artifacts and the expected helper hash. Reviewer
rechecked both fixes and reported no remaining blockers.

Full suite:993 passed, one existing Starlette/httpx deprecation warning.
Ruff and git diff --check passed. Focused suite:85 passed.
No Pi or VM state was changed. Root-console installation and separate SSH
acceptance remain pending; this preparation is not a driver/physical pass.

## Live operator installation and restricted SSH acceptance

Operator installed the verified13,639-byte archive with SHA256
96e784fdd6a8e3b8c9e050a3eb09059cc17cc7c18a6ff58beee74d04725256a1.
Backup: /root/freeze-light-diagnostics.ux8w3j1v.
Before helper: df06b46bd206dbadbbbd201aeb80529df9deb790b7df448b29e1ff2ba15c6a9c.
After helper: 2697465c2d98ab3b34be8da17f145411e900dc50765f02ff3e3a51ceb326364b.
Receipt reports gpio_commands_issued=false.

A separate direct restricted SSH maintenance status call returned exit0 and
confirmed that exact new helper hash, retained legacy fields and the new section
code=READ. A separate harmless status-with-extra-argument command was rejected
with exit1 and "not an allowed commissioning command". Original SSH boundary
remains intact. Remote diagnostic acceptance is VERIFIED.

## Observed bench failure

The931 saved point observations identify crash_release as the first failure:
GPIO21 function1/output, level0/LOW; GPIO20 and26 both function1/output, level1/HIGH.
Startup OFF146 samples, normal ON234, commanded OFF72, normal release143,
ON before crash237, final owned OFF49 and final released OFF49 had zero
mismatches. crash_release had one failing sample, then the test stopped and
performed explicit OFF recovery. These counts do not prove a sustained duration
of LOW after death; they prove the first post-exit sample was not inactive.
All recorded paired outputs remain output/HIGH. This is historical readback,
not physical contacts or a fresh GPIO21 level measurement.

The failure is an invalid assumption that a killed GPIO owner automatically
returns its output to inactive. The Linux GPIO request documentation guarantees
requested state only while the request descriptor is open and explicitly leaves
post-close state uncontrolled from userspace:
https://docs.kernel.org/userspace-api/gpio/gpio-v2-get-line-ioctl.html

The existing light executor expires leases in its own process; it therefore
cannot itself enforce OFF after its process dies or hangs. Its current restart
unit also preserves the runtime socket directory, so restart success must not
be assumed after an unclean death. No code or service fix is claimed here.
Next engineering step: independent crash/hang supervision with explicit GPIO21
OFF and startup fence, then a separate disconnected test. Do not weaken the
failed raw-release test or claim internal pull bias fixes an actively driven LOW.

| Fault | Required outcome / enforcer | Current evidence |
| --- | --- | --- |
| Communication loss | Local lease expiry requests OFF within existing3s lease plus scheduling | Source logic; real light service not deployed |
| GPIO process crash/hang | An independent enforcer must drive GPIO21 HIGH; bounded timing must be designed/tested | Raw SIGKILL release failed; same-process expiry is insufficient |
| Pi reset/reboot | Safe light output before and through startup | Not tested; supervisor on the same Pi cannot establish pre-boot behavior |
| Pi/relay supply loss/restoration | Defined passive contact behavior for each supply domain | Physical wiring/contact behavior not verified |

Legal energized valve1/valve2/light combinations remain (0,0,0), (0,0,1),
(1,1,0), (1,1,1); the current isolated bench requires pair DRAIN/high-high.
Camera forwarding and physical light acceptance remain disabled/unverified.

## Owner decision: light may remain ON after process failure — 2026-10-15

The owner explicitly answered "da" after being asked whether the independent
light may remain ON after a process crash or hang until control is restored or
a manual intervention occurs. This accepts an unbounded ON duration for this
light failure case; the regular hold/override timer is not a guarantee while its
enforcing process is unavailable. No independent crash/hang cutoff is required
for this light under this decision.

This is a requirement change, not a successful fail-OFF test. The original
LIGHT_LEVEL_MISMATCH receipt and first crash_release output/LOW sample remain
unchanged. Normal ON/OFF, final OFF recovery and sampled paired HIGH/HIGH were
observed. Executor hang behavior is accepted as a possible retained ON state,
not claimed to have been tested.

The exception applies only to independent light GPIO21. Shower GPIO20/26 safety,
paired transitions, deadlines and fault requirements are unchanged. Keep normal
communication-loss expiry, explicit OFF behavior, startup OFF and prevention of
stale command replay. No new guarantee is made for reset/boot, power domains,
contact wiring, physical position, mains connection or remote actuation rights.
The existing no-repeat marker must not be deleted merely to turn the old failed
test into a pass.

Camera forwarding remains disabled until service, ingress, credential and
functional acceptance are actually completed. Crash-release automatic OFF is
no longer a blocker by itself under this recorded owner decision.
