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

Task review is closed; final integration review is pending. No installer package has been
handed to the operator for execution. No target dependency preparation,
service replacement, SUPPLY, GPIO21 activation, firmware flash, release or
physical acceptance occurred. Actual prepare/install receipts and subsequent
separately authorized disconnected-load acceptance remain mandatory.
