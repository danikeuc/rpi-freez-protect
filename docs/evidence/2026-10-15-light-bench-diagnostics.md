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
