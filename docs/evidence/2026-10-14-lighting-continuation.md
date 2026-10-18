# Lighting continuation — 2026-10-14

Owner requested completion using Superpowers. Direct restricted SSH maintenance
status and inventory succeeded again. Current installed paired daemon/dropin
match the successful recovery hashes; Hub, paired daemon and Node-RED are
active, and the separate Hub recovery success marker remains present. Original
failed receipts remain historical. Inventory identifies DietPi kernel6.18.39,
ARM64 and preserved checkout d0dfeac. No new service/GPIO operation was run.

The light implementation remains the previously reviewed source candidate.
Companion Dial branch is clean at70bc5b5bebafd69ab2222178d269ba17dd991c9d.
No Dial flash, third-relay activation or Protect profile acceptance occurred.

A fixed [read-only inventory](../../deployment/lighting/INVENTORY.md) now
collects bounded metadata and sanitized projections for the next deployment.
Thirteen focused tests pass after RED: absent implementation, then a malformed
boolean GPIO projection falsely reporting a free line. The projection now
requires all expected values to be booleans and otherwise reports NOT_OBSERVED.
No settings JavaScript is evaluated; no GPIO lines are requested. These are
workstation tests, not a target inventory receipt.

Current operational GPIO gate paragraphs now distinguish the installed paired
migration from pending disconnected interleaving/physical acceptance. Historical
2026-10-13 review reports are retained unchanged. Actual Protect version,
authenticated POST capability and sample were requested from the operator;
no response is recorded yet. No camera identifiers or field paths were invented.

Completion is pending target inventory and commissioning evidence. This record
is neither a release nor a claim that the light already works on hardware.

## Final local verification and delivery

Full pytest: 902 passed, one existing Starlette/httpx deprecation warning.
Ruff passed; strict mypy passed over34 source files; git diff --check passed.
[Fresh independent review](2026-10-14-maintenance-final-review.md):
PASS_WITH_ADVISORIES, no P0/P1/P2. One deferred P3: an older activation-history
paragraph in PROJECT_STATE still uses present-tense pending language; the current
top checkpoint is authoritative. No functional fix was requested by review.

Read-only package lighting-inventory-20261014-v1.tar.gz,4155 bytes, SHA256
4ca46df66b03556292d74b1b41b66de3585451f7d0672edb024ad675258c904f.
Three regular members: inventory.py, README.md, SHA256SUMS. Inner hashes, exact
source equality and compilation verified. Workstation HTTP delivery returned200
and matching full SHA256. The delivery server has no automatic expiry timer;
workstation sleep/network interruption can still make it unavailable.

The operator was given one trusted-console inventory block because the installed
remote allowlist has no lighting operation. No automatic privilege expansion
or new command was installed. The target inventory result remains pending.
