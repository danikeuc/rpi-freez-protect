# Paired GPIO migration package verification

Scope: two-stage trusted-console migration of the existing paired daemon;
independent lighting remains disabled. User confirmed both valve24V and lamp
loads disconnected. [Inventory evidence](2026-10-13-gpio-migration-preflight.md)
separates current observations from historical Hub1.3.1 installation.

## Implementation and initial verification

Implementation25508828ed95e434c10a0d3d57b39b2d6fdee23b adds the narrow installer,
reviewed service override/environment, private evidence and regression tests.
A separately pinned gpiod2.3.0 cp313/aarch64 wheel prepares an isolated venv;
the existing Hub environment is preserved.

RED:13 missing-feature failures; later2 metadata/lifecycle regressions.
GREEN:26 focused tests; full804 tests pass in18.67s; Ruff passes;
commissioning asset suite110 passes. One existing FastAPI/Starlette httpx
warning remains. No shell scripts changed. These are workstation tests with
substituted system/device boundaries, not installed or physical evidence.

## Independent task review

Initial review found a historical INSTALL_STARTED marker could incorrectly
arm cleanup after a rejected repeated install, stopping a healthy Hub. It also
required missing backup-durability and partial-replacement fault tests.
Repair01d65ff3ef505c453da7094b60e0cf8a75889099 arms cleanup only in the current
invocation after durable cutover evidence and rejects historical used evidence
without changing it. New real file/SQLite fault-injection tests cover backup
fsync/hash, marker durability, partial replacement and baseline rejection.
Focused37 tests and Ruff pass. Scoped independent re-review approved both
repairs with no new findings. Review also noted bounded
operator diagnostic codes would improve failure handling; private tracebacks
already preserve diagnostic detail without exposing secrets.

## Current verification

At source01d65ff, the required final full Python suite passes815 tests in18.15s,
with the same existing Starlette/httpx warning. Ruff and git diff --check pass.
The commissioning110 suite passed in initial verification and is also included
in the final full run. No shell script changed.

## Decisions and scope

- Use canonicalgpiochip0 and an isolated root-controlled venv. No dependency
  or package changes to the existing Hubvenv.
- Metadata-only preparation prohibits candidate owner creation, line requests,
  candidate MMIO and writes. Existing read-only pinctrl get remains required
  for high/high observation; its own internal register reading is not excluded.
- Candidate paired override uses Restart=no during this disconnected migration.
  It prevents repeated automatic acquisitions after failure, but removes the
  previous automatic process recovery; later crashes need operator recovery.
  This does not establish crash-safe physical behavior.

## Delivery boundary

Task review and [final integration review](2026-10-13-paired-gpio-migration-final-review.md)
are closed: specification and quality PASS. The reviewed package is ready for
trusted-console prepare; target execution receipts remain pending. No target dependency preparation,
service replacement, SUPPLY, GPIO21 activation, firmware flash, release or
physical acceptance occurred. Actual prepare/install receipts and subsequent
separately authorized disconnected-load acceptance remain mandatory.

## Package and controller disposition

Artifact: paired-gpio-migration-20261013.tar.gz,125443 bytes,14 regular members.
SHA256:afd651cd13d8b088a5dea31e427ee9844062981ef52a436e49b7d79f27e2b45a.
Runtime manifest contains exactly11 fixed filenames and their hashes; outer
SHA256SUMS also covers README and manifest. Text assets use LF. Archive member
names/type and bytes match the staged files; HTTP download returned200 and the
same exact hash. Delivery server binds workstation LAN192.168.111.30:8780,
serves only this exact filename and has no directory listing or timed expiry.
The workstation must remain running. No firewall or Pi access permissions changed.
Installer source01d65ff; paired daemon source44091d6 (SHAef96336ec9fd299459adb4bc751aac4ef5bf7f992fb0757886e496851c73b51f).

Controller disposition of final review exclusions: actual runtime, installation,
rollback and physical/fault acceptance remain required operator gates. Archive
identity is separately verified above. Unrelated lighting/Protect/Dial behavior
retains its prior evidence and disabled-activation boundary. Unsupported profiles
and privileged competing writers remain excluded from this narrow support
contract. Existing final test evidence is sufficient; no additional broad suite
or physical test is inferred. The two P3 follow-ups (bounded diagnostics and
existing dependency warning) are tracked, not silently treated as fixed.

Decisions: an isolated pinned environment preserves Hub dependencies (risk if
wrong: service interpreter compatibility/access must fail the metadata gate).
Read-only pinctrl get is permitted for the required level observation while
candidate GPIO ownership and writes are prohibited during prepare (risk if wrong:
an unexpected tool side effect would violate no-write preparation). The reviewed
Restart=no migration limitation remains explicitly disclosed before install.

## Operator preparation attempt - awaiting diagnosis

Operator verified outer archive and all listed checksummed package assets, then
reported PAIRED_MIGRATION_STOPPED phase=prepare with evidence
/root/paired-gpio-migration.__qcivrj. The generic code does not identify the
failed guard. Preparation was not accepted and install is not authorized to
proceed from this failed receipt. No automatic retry or rollback. Prepare
contains no service replacement; partial isolated dependency files are not
ruled out until bounded read-only diagnosis. Both loads remain disconnected
per the current operator confirmation.

Operator bounded diagnostic: migrate.py416/243/136/92 and operator_checks.py31,
RuntimeError; PREPARED/INSTALL_STARTED/SUCCESS and isolated VENV all false.
This identifies the Hub base-unit byte comparison in preflight as the failing
guard. Current packaged hub.service is7ba8f1d0a42eea506325b11c2457e07191dc4978c8618358fe76919fd12a9469.
Historical baseline atd0dfeac and52c0815 is9b5efc26fbee6fdfbb9d50bc1895470c046e667e2e28618134067d801c863718.
The installed startup-readiness updater preserved the base and added the
30-node-red-readiness.conf dropin, so selecting current inline-readiness source
for the package baseline was inappropriate. Live unit/dropin hashes and
effective paths are requested to confirm the exact target combination before
issuing a corrected package. The exact byte guard remains in force; no live
unit replacement or validation bypass is proposed.

Correction327d8b8cb7cce256a824513bab032d6683f9cfff adds a tracked historical
Hub baseline and packaging provenance; runtime guards remain unchanged.
Independent scoped review independently matched git source bytes and approved
the correction. Tests38 focused/816 full/110 commissioning and Ruff pass, with
the existing Starlette warning. One initial documentation-link test failed
because a scratch quoted diff had Markdown extension; renaming it to.txt
resolved that artifact-only failure before the final full gate.

Corrected v2 archive staged locally (not issued to operator):
paired-gpio-migration-20261013-v2.tar.gz; SHA256f4c87e6439650f80c02b2d1b17c76661c5e3d74bbf7c672eab28edadc9883513; 125765bytes.
Exact11 manifest entries,14 safe regular archive members and all staged bytes
verified. Await live unit/dropin hashes and effective paths before handoff.
