# Continuous Protect MCP adapter — 2026-10-15

## Scope and source
Owner authorized implementation after choosing G4 Pro/person. Implemented a
standalone VM adapter, tests and user service; Pi control logic, paired GPIO,
Dial firmware and Protect configuration are unchanged.
[Source contract](../../deployment/protect-mcp/README.md).

## Executed VM evidence

Host linuxvm172.17.178.227, userdanik. One-shot observation through the installed
MCP launcher succeeded. Installed script SHA256:
`d5e2e6bb617a78134e2d161907983c1d9df281ccfcf3591d85e9ee22702173b0`.
User unit SHA256:
`a9feea4bce6c39c73bfaf51c944d0d8d30de89af1a007b0e64fe7197c30842af`.

`protect-light-adapter.service`: enabled, active/running, PID66631, NRestarts0.
A separate SSH connection verified the same PID and successful observing records
at14:24:32,14:24:37,14:24:42,14:24:47,14:24:52 UTC. Linger=yes and
NTPSynchronized=yes. This validates independent user-service execution and polling;
VM reboot was not tested. The observed interval contained zero admitted fresh
persons; no new person walkthrough or camera-to-light activation is claimed.

Mode=observe, no sink endpoint, no token_file. All files are private under danik's
home. The prior staged observer is saved as before-deadline-fix.py. MCP credentials
and its scoped TLS exception are unchanged. Service startup/stop does not send
commands to the Pi. No images, relay writes or playlist operations were requested.

## Verification

27 focused tests pass: admission, malformed/source/subtype/UTC/future/stale events,
startup/reconnect/clock boundaries, duplicate ID updates, saturated pages, private
file permissions, redirects, original payload delivery, manual-inhibited receipts,
observer behavior, ambiguous POST disarming, both response envelope formats and
total deadline interrupting a trickling operation with timer cleanup.

Independent fresh review found two important issues: structured replies bypassed
the size limit; HTTP inactivity timeout was not a total deadline. Both were
reproduced by failing tests and fixed. Dedicated-main-thread POSIX deadline avoids
abandoned HTTP threads. Final full-suite run: 929 tests passed (one existing Starlette/httpx deprecation
warning); Ruff passed; configured mypy passed for34 source modules; git diff
--check passed. The standalone adapter is covered by executed tests, not the
src-only mypy target. These are software checks, not physical acceptance.

## Remaining boundary

The unattended source is installed, but the light controller/gateway/GPIO21 are
not activated. HTTPS event ingress and camera-role credential are not provisioned.
Existing disconnected coexistence/executor and physical acceptance gates remain
open. The observer cannot itself complete those target-side prerequisites.
