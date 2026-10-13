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
