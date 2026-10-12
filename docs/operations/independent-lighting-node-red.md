# Planned UniFi lighting adapter in Node-RED

Design-only, 2026-10-12. Canonical behavior is in the
[lighting specification](../superpowers/specs/2026-10-12-independent-lighting-design.md).
No flow has been added or deployed. Existing paired-relay export has 11 nodes;
the skill inspector found zero structural issues, not runtime verification.

## Existing runtime boundary

Recorded host: DietPi RPi, node-red.service, loopback port 1880, user nodered,
flow file /mnt/dietpi_userdata/node-red/flows.json. Exact current Node-RED/Node.js,
settings path, palette versions and Projects status were not captured in this
documentation pass. The separate broken alias nodered.service is historically
disabled. Preserve the one existing paired bridge route and its fixed client.

## Planned flow model

A separate tab, Light - UniFi ingress, handles only authenticated camera events.
It owns no GPIO node, trigger timer, persistent mode or global context policy.

| Boundary | Contract |
| --- | --- |
| HTTP In | POST through a new exact Nginx route; validate sender/auth, content type and size |
| Validation | Schema/profile from actual Protect sample; reject stale/unknown camera/type |
| Normalization | Versioned event with stable event key, camera/rule identity and original occurrence time |
| Local controller call | Bounded request to separate light controller, fixed destination; retain event identity on any safe retry |
| Response | One bounded HTTP response after classification; distinguish accepted, duplicate, ignored_manual, rejected and unavailable |
| Catch / Status | Sanitized cause/correlation only; propagate unavailable, no full msg debug and no GPIO fallback |

Keep msg.req, msg.res and _msgid through transformations. Keep the validated
normalized event separate from the upstream response payload. An asynchronous
Function must finish through node.done and avoid sending multiple responses.
Avoid shell/exec nodes and dynamic command construction from camera payloads.

Do not call the shower start/stop/drain, paired socket, Roon bridge or shared
playlist API. Do not add GPIO21 to paired_gpio_daemon.py. The separate light
executor is the only eventual owner of that line. The controller, not Node-RED
context, deduplicates events, enforces mode and deadlines, and writes history.

## Security and runtime constraints

HTTP In authorization is separate from editor/adminAuth. Keep the editor and
port1880 loopback-only. Use dedicated external secret storage; do not share
shower display/weather tokens, log raw headers or put keys in URL query strings.
Verify authenticated POST support on the actual Protect build before choosing
its credential profile. Reject incompatible setup rather than silently accepting
unauthenticated traffic. The future exact reverse-proxy routes and limits need
contract review; do not broadly expose /api or the entire Node-RED runtime.

## Verification and rollout boundary

Before future deployment, export the actual flow and matching credential/settings
backup privately. Capture versions and preserve unrelated tabs, node IDs and
credential references. Add the light tab using the smallest safe deployment
scope supported by that runtime. Review new routes without relaxing the existing
paired-flow preflight. Separately validate light ingress/owner constraints.

Tests must cover preserved HTTP context, single replies, duplicate retries,
malformed/oversize requests, unauthorized sources, delayed delivery after manual
mode, upstream timeout and Node-RED restart. Ingress success is not lamp feedback.
Start with a recording/simulated controller and disconnected load. No ON command
on flow startup/redeploy. Rollback disables light ingress, requests/verifies OFF
through its owner, then stops the lighting services and restores only their
artifacts. It must not reset the shower DB or rewrite unrelated flow tabs.

Official references:
[HTTP endpoint security](https://nodered.org/docs/user-guide/runtime/securing-node-red),
[message contract](https://nodered.org/docs/user-guide/messages),
[Function lifecycle](https://nodered.org/docs/user-guide/writing-functions).
The security page was verified 2026-10-12; lifecycle details must be checked
against the captured deployed version before implementation.
