# Independent light runtime preparation — 2026-10-15

## Status

Prepared for a trusted root@DietPi console installation. **NOT_INSTALLED**;
physical acceptance **NOT_VERIFIED**. Both loads remain disconnected by the
owner's maintenance-window confirmation. There were no new GPIO commands,
service changes or package installation on the Pi during preparation.

The owner accepted retained light ON after executor crash/hang. This changes
only GPIO21's crash-cutoff requirement. The original LIGHT_LEVEL_MISMATCH
receipt remains unchanged; the shower pair's safety policy is unchanged.

## Fresh read-only observations

Restricted maintenance status returned installed paired daemon
`ef96336ec9fd299459adb4bc751aac4ef5bf7f992fb0757886e496851c73b51f`,
active Hub/pair/Node-RED and the existing diagnostic helper
`2697465c2d98ab3b34be8da17f145411e900dc50765f02ff3e3a51ceb326364b`.
It returned the historical931-sample bench; this is not a new GPIO21 trace.

On VM172.17.178.227, the Protect adapter is active and config mode is `observe`,
with no endpoint or token file configured. A dedicated RSA4096 recipient key
was created privately on that VM; only its public key was copied into the
installation package. No camera event was forwarded.

## Installation contract

- Separate light-only distribution/venv, dedicated non-login account and DB.
- Executor alone has GPIO device access; controller has PrivateDevices.
- Normal startup is explicitly OFF. Bounded socket readiness precedes controller.
- Fixed camera-only HTTPS ingress8443; existing8081 and Node-RED are preserved.
- Three distinct credentials generated onPi, never printed. Camera credential
  encrypted OAEP SHA256 toVM; generated SAN certificate is the pinned trust anchor.
- Ordinary lease/freshness/dedup remain enforced. Restart cannot guarantee
  physical cutoff after crash/hang; retainedON is owner-accepted.
- No automatic retry/rollback. Failed activation revokes only new startup/ingress
  gates and stops only newlightservices, preserving private evidence.
- SSH authority is unchanged. Current helper cannot install arbitrary packages;
  the reviewed bundle therefore needs one trusted rootconsole execution.

## Verification record

Package and installer task reviews completed after correcting boot readiness,
umask-related executable traversal and canonical masked-unit handling.
Final integrated review found late-failure startup/ingress inhibition gaps;
fixed in47cfb1d and scoped re-review clear. No remaining actionable findings.
Full pytest: **1026 passed**, one existing Starlette deprecation warning.
Ruff and diff-check clean. Tests ran on workstation Python3.12, notPi hardware.
Actual CPython3.13/aarch64 offline dependency closure was resolved/hash-verified;
all16 selected wheels and unchanged light source files were checked.

Final bundle:27 regular safe-path members,3318554bytes, independently retrieved
from the privateLAN HTTP server with matching hash.

- Source through `47cfb1d`; packaging assets `acf635c`.
- Archive SHA256 `aaadadd366c92b465eb475ba98e8becdf64d920e11f13cb926dedcdbefd923ea`.
- Manifest SHA256 `5775a540d700639f49317933a7dd21ec85ad771dd2e5f19c0d7fa894dd0bdd1f`.
- Delivery: `http://192.168.111.30:8781/light-runtime-20261015.tar.gz`.
- [Operator block](../operations/independent-light-install.md).

Target install, TLS verification onPi, encrypted credential handoff and camera
forwarding acceptance remain pending. No release/publication is claimed.
