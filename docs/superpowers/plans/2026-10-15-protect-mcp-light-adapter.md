# Protect MCP light adapter implementation

Approved input: G4 Pro (6797d43f03968103e40003f1), person only.
Execute inline with Superpowers. Existing lighting spec remains authoritative.

## Interfaces and scope
Read-only MCP stdio child -> bounded smart detection poll -> validated event
{event_id, source_id, occurred_at} -> existing Pi camera-role API. VM holds no
GPIO or shower credential. Pi owns AUTO/manual policy, 300s default hold and expiry.
Default observe mode has no sink or credential. Forward mode requires an explicit
HTTPS event endpoint with certificate verification and private camera token.
No new unencrypted listener, general Pi SSH grant, or GPIO activation.

## Task 1: admission and delivery
Write failing tests, implement exact source/person filters, strict UTC timestamps,
60s freshness, startup/reconnect boundaries, duplicate suppression, overload and
clock failure handling. Keep original event identity and start time. Never replay
an ambiguous POST. Require verified HTTPS, no redirects/proxies; bound response.
Tests: tests/unit/test_protect_light_adapter.py. Expected: targeted tests pass.

## Task 2: MCP runner and deployment
Separate standalone script (MCP SDK only on VM), 5s poll, deadlines, private
configuration, sanitized aggregate logging and user systemd service. Read-only
observation can be installed now. Forward activation depends on commissioned Pi
light API and separate least-privilege credential/verified TLS transport.
Verify actual MCP envelope with one-shot observe, then service readiness and
logout persistence. Verify linger; do not claim reboot readiness without it.

## Task 3: evidence and review
Full pytest, Ruff, configured mypy. Fresh independent review of adapter and
service, fix important findings with reproducing tests. Update project state,
source evidence and installation limits. Do not call observer a working lamp.

## Review Focus
Partial and oversized pages, ID reuse, delayed first observation, time jumps,
MCP cancellation, HTTP ambiguity, credential leakage, service restart replay,
user service survival after logout, separation from paired shower output.
