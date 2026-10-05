# Pending DRAIN recovery - local P1 fix, 2026-10-05

## Scope and acceptance

The GPIO daemon must retry an unsuccessful DRAIN independently of Hub traffic.
It must reject SUPPLY while DRAIN remains unverified, and an expired RENEW must
not reopen the pair after recovery. Protocol v2, the 60-second supply lease,
paired GPIO mask, request deadlines and normal BEGIN/RENEW behavior are unchanged.

The old implementation cleared its lease before attempting DRAIN. A failed
write/readback left no deadline for the next enforce() call to act on. The fix
retains a pending DRAIN flag until write_and_verify("DRAIN") succeeds. Existing
socket-loop enforcement retries it; the loop keeps its 0.1-second accept timeout
and one-second accepted-socket timeout. This is not a guaranteed physical cutoff
latency, and permanent hardware failures cannot be repaired by retries.

The same pending state covers expiry, explicit DRAIN and emergency DRAIN after a
failed SUPPLY operation. No new SUPPLY retry mechanism is introduced. Once DRAIN
is verified, RENEW remains rejected; a fresh valid BEGIN retains its existing
meaning. Shutdown DRAIN remains best effort, outside the running-loop repair.

## Fresh verification

- Before production changes: six regression cases failed because a later
  enforce() did not retry DRAIN; eight other cases in that file passed.
- After changes: 37 affected daemon/protocol/service/weather integration cases
  passed. Tests use real lease and paired GPIO logic with fake register I/O.
- Full `python -m pytest -q`: **654 passed**, one existing Starlette deprecation
  warning, exit 0.
- `python -m ruff check .`: PASS, exit 0.
- `python -m mypy src`: PASS, 26 source files, exit 0. This configured mypy scope
  does not cover the standalone deployment daemon.
- Regression cases cover register-write failure, incorrect readback, repeated
  failure, recovery without Hub traffic, rejection of BEGIN/RENEW during failure,
  stale RENEW rejection and new BEGIN after confirmed DRAIN.

## Independent review

A separate read-only reviewer found no material issue in the patch. An additional
in-memory exercise of the actual serve() loop injected two consecutive DRAIN
failures after BEGIN and then recovered without more Hub requests. The trace was
DRAIN, SUPPLY, DRAIN failed, DRAIN failed, DRAIN verified (exit 0). This checks loop
integration with simulated sockets/GPIO, not real socket timing or hardware.

## Artifact and deployment boundary

Local daemon SHA-256: `33088ea9e6ccf8d327e226bab1602c6a2b3ba2423de7dcab408b1d06f2233d2f`.

This record confirms an offline source fix, not a Pi installation or physical
valve test. No device command, service restart, firmware upload, deployment,
commit, push or release was performed for this repair. The installed daemon must
be updated through the documented trusted-console deployment procedure before
this fix can be claimed on the device. A Hub wheel-only update does not replace
this separately installed daemon. Keep physical acceptance distinct from tests.


## Installer handoff correction

The first operator attempt passed archive/file checksums but returned
`INSTALL_STOPPED code=SEE_PRIVATE_DIAGNOSTIC type=RuntimeError`, with
`backup=None`. No cutover marker or file replacement was reached. Independent
restricted status then confirmed the three services active and GPIO26/20 high.

Archive entries carry the development owner's UID/GID 1000. The original root
`tar -xzf` command preserves those owners and conflicts with the installer's
root-ownership guard. Keep this guard. The corrected handoff extracts in a fresh
root-only directory using `tar --no-same-owner --no-same-permissions -xzf` under
umask 077. A fresh local-root extraction verified all nine regular files owned
by root, private modes, and all checksums. No installer or hardware action was
executed in that test. Archive SHA remains
`ff632c88b38cccf4969a23089c5c5e09ae93fdbe0decc9557dfd6385a29aabb9`.

This corrects packaging ownership at extraction, not production access rules.
The corrected operator attempt and actual deployment remain pending.


## Installed on Pi - 2026-10-05

This section supersedes the earlier local-only and pending-installation status.
The corrected root extraction completed and the operator returned
`PAIRED_DRAIN_FIX_INSTALLED` with the exact candidate SHA, weather_assisted,
USER_OFF, DRAIN and GPIO26/20 high. Backup:
`/root/freeze-paired-drain-fix._j1g92ni`.

Independent restricted SSH `status` and `diagnose-pair-gpio` both exited zero:
all three checked services active; both GPIO lines output/high; installed daemon
SHA matches the candidate; paired daemon running, MainPID 400948, NRestarts 0,
active since 2026-10-05 19:36:52 UTC. The daemon is root-owned mode 0755.
See [installation receipt](2026-10-05-pending-drain-installation.json).

P1 source repair is now installed, with exact file identity and service/output
checks confirmed. Recovery from injected GPIO failure was demonstrated offline;
no physical valve operation or live hardware fault injection is claimed. The
operator confirmed 24 V disconnected before this installation. No START/SUPPLY
or release publication was performed.
