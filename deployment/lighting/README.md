# Independent lighting deployment assets

## Current installation path — 2026-10-15

The reviewed first-install package is under [install/README](install/README).
It uses the VM Protect MCP adapter, a camera-only HTTPS endpoint on port8443,
and separate light services/venv. Node-RED lighting templates below remain
inactive alternatives; they are not part of this installation. Package preparation
is not target installation or physical acceptance. Camera forwarding stays in
observe mode until credential handoff is verified.

The disconnected GPIO21 bench proved normal ON/OFF and unchanged paired HIGH
samples, but detected retained output LOW immediately after executor SIGKILL.
The owner accepted unbounded retained ON after crash/hang for this independent
light; see [acceptance](../../docs/evidence/2026-10-15-light-retained-on-acceptance.md).
The original failed bench receipt is retained. No external watchdog is required
for this accepted case. Startup OFF, ordinary leases and physical load checks
remain requirements; shower safety is unchanged.

## Original inactive template path

The following describes the original 2026-10-13 templates, not the selected
`install/` package. Canonical behavior:
[specification](../../docs/superpowers/specs/2026-10-12-independent-lighting-design.md).

## Disabled defaults and separation

The flow tab is disabled. Include the additive Nginx snippet manually inside
the existing port 8081 server after review; every exact route starts with deny all.
Replace deny all with reviewed sender/client allow rules followed by deny all.
Keep 1880/editor and 8002 loopback-only, secure editor/adminAuth and use TLS or a
commissioned trusted transport. Configure a bounded Nginx limit_req zone/rate
matched to observed Protect bursts/retries before activation; that rate is
unknown today. Review nginx -t against the actual server.

Units have no Install section and require /etc/independent-light/commissioned.
They restart on failure after 2 seconds, at most 3 starts per 60 seconds; stop budget 5 seconds.
They have no shower dependencies and cannot restart shower services.
Dedicated independent-light account/DB/socket/environment files are required.
Controller PrivateDevices=true prevents device access. Executor DevicePolicy=closed
has no DeviceAllow: a reviewed override must permit only the verified gpiochip.
Kernel gpiochip permissions do not isolate individual lines. The executor's
fixed GPIO21 API limits its requested line; it does not establish whole-system
configuration or physical isolation. Both processes share the account because socket mode 0600
is the trust boundary. Runtime directory mode 0700 must exist before controller start.
RuntimeDirectoryPreserve=restart preserves sockets; an existing socket refuses
startup, requiring verified OFF/recovery before removing a stale socket.

Provision once as the dedicated account:
LIGHT_DB_PATH=<new path> python -m freeze_protect.lighting.main --provision-new-db.
Provisioning exits without GPIO. Runtime refuses missing DB/watermark; data loss
requires explicit repair and credential rotation. Missing executor is UNAVAILABLE.
No installer or automatic service startup is provided.

Use separate mode 0600 controller.env, executor.env and Node-RED secret files.
Controller needs display/settings/camera tokens, source allowlist, DB and socket.
Executor needs socket/hardware settings, never UI/camera tokens. Node-RED needs
camera/ingress tokens, profile and allowed sources, never UI/settings tokens.
Protect gets ingress token only. environment.example lists fields for reference;
do not use it as a shared secret file. All tokens are distinct ASCII 32..512 chars;
controller verifies its three tokens and adapter verifies ingress versus camera.
Do not put tokens in URLs, browser data, logs or flow exports.

WatchdogSec is absent: processes do not emit sd_notify watchdog messages, so
that setting would falsely imply supervision or cause a restart loop. Controller
renews executor's 3 second lease every 0.25 seconds. Executor hang/crash line release,
reset before software ownership and separate power restoration need hardware
proof; unit restart/stop budgets are not contact-release guarantees.

### GPIO_SHARED_FSEL2_COEXISTENCE

**Installed migration verified on 2026-10-14; lighting acceptance remains open.**
The exact kernel-ownership daemon and paired dropin are installed on the Pi.
Restricted SSH confirmed the separate Hub-recovery success marker, all three
services active and paired output/high readback. See the
[dated recovery evidence](../../docs/evidence/2026-10-14-device-allow-recovery.md).

The legacy userspace FSEL writer is no longer the recorded installed backend.
The source repair and installed migration close that part of
GPIO_SHARED_FSEL2_COEXISTENCE. They do not close the disconnected-load
startup/request/release/crash trace or physical acceptance requirements.
Keep the original templates and flow disabled. The dedicated `install/` package
checks the recorded disconnected bench and owner exception before creating its
commissioned marker and narrowly scoped DeviceAllow. Physical acceptance remains open.
Kernel-only configuration does not establish atomic initial direction changes,
crash protection, physical independence or valve position. Actual Protect
profile, Node-RED runtime and lamp/wiring gates remain open.


## Explicit profile and exact contract

Private Node-RED POST /lighting/unifi receives exact gateway
/api/v1/lights/events/unifi. Status/actions/settings/history route straight to
loopback 8002 with original Bearer roles. Adapter authenticates separate
LIGHT_UNIFI_INGRESS_TOKEN, then forwards only {event_id,source_id,occurred_at} using
LIGHT_CAMERA_TOKEN to fixed loopback 8002 /api/v1/lights/events/unifi.
No caller URL, method or header controls the upstream destination.

LIGHT_UNIFI_ENABLED must equal commissioned. LIGHT_UNIFI_PROFILE is JSON with
exactly seven fields. This synthetic example is **not an actual Protect profile**:

    {"version":1,"event_id_path":["id"],"source_id_path":["camera"],"occurred_at_path":["at"],"event_type_path":["type"],"allowed_event_types":["motion"],"occurred_at_format":"utc"}

Paths select 1..8 own-property keys; string keys may select array indexes.
No expressions/wildcards/prototype traversal. occurred_at_format is utc
(UTC ISO8601 Z/+00:00,20..40 chars) or unix_ms (safe nonnegative integer converted
to UTC). IDs are 1..128 ASCII [A-Za-z0-9_.:-]. No fresh UUID, receive-time timestamp
or fingerprint fallback. Allowed types and comma-separated stable
LIGHT_ALLOWED_SOURCES (no spaces) are required. JSON max 4096 bytes, age<=60s,
future<=5s. Real payload may have other metadata; none is forwarded.

Adapter retains req/res/_msgid and sends one HTTP response. HTTP 200 returns
only {accepted,duplicate}, including accepted=false for ignored events. It makes
no mode/illumination inference. Upstream 401/403/409/413/422/429/503 are sanitized;
other failures become 503. Response max 8192 bytes and absolute request/stream
budget 1500 ms. No transport retry, dedup, hold, GPIO or flow/global policy context.
Controller persists identity and owns all timing. Transient node-local memory
context stores transport cancellers only; On Stop cancels requests. Cancellation
cannot retract an already accepted event; fresh status resolves uncertainty.

## Actual Protect and runtime activation gates

The official [Protect webhook page](https://help.ui.com/hc/en-us/articles/25478744592023-Send-UniFi-Protect-Alerts-to-Web-Services-using-Webhooks)
checked 2026-10-13 documents GET custom headers and POST alarm data/timestamp.
Its example guarantees no stable unique event ID or custom POST authentication.
Installed version, sanitized payload, original identity/time, source/type paths
and retry/auth capability remain unknown. The official example alone is
incompatible with this strict adapter.

Capture sanitized actual samples/retries without secrets, demonstrate stable
event ID/time/source/type and authenticated POST, review/freeze explicit profile.
If unsupported, leave disabled and review a compatible authenticated local
adapter. Do not enable unsigned GET, token URLs or guessed event identities.

Record actual Node-RED/Node.js versions, palette, Projects, userDir/settings and
active flow. Back up flow/credentials privately and preserve other node IDs.
Export uses built-in HTTP/Function/Response plus built-in http/crypto Function
libraries; review functionExternalModules=true and named memory-only context
store memory. Never store canceller Set in persistent context. These settings
can affect shared runtime; review before restart. Import only the disabled tab.
Inspector/tests prove structure/simulation, not deployed runtime.

## Fault outcomes and rollback

Ordinary-light OFF is proposed; lamp role/load/contact suitability is unverified.
Legal energized (valve1,valve2,light) states: (0,0,0),(0,0,1),(1,1,0),(1,1,1);
mixed valve states forbidden, lighting never writes GPIO26/20.

| Fault | Required enforcement | Still unverified |
| --- | --- | --- |
| Camera/LAN or Node-RED loss | Local controller deadlines; no queued replay | Offline trace/shared shower bridge impact |
| Controller crash/hang | Executor lease expiry 3 seconds | Measured readback/contact cutoff |
| Executor crash/hang | Owner accepts retained ON; restart may recover | No guaranteed cutoff; physical contact behavior unverified |
| Pi reset/reboot | Bias/startup OFF; never restore ON | Pre-software boot trace |
| Pi, relay, lamp power loss/restoration | Verify each independent domain | Bias/contacts; active-command lamp restoration acceptance |

Rollback closes light ingress, requests/verifies OFF through light owner with
fresh state, then stops only light units/restores only light assets. If OFF cannot
be verified use the commissioned physical isolation path; none established here.
Never reset shower DB/flow or issue shower commands. Future live tests require
an observer, bounded duration/cutoff and stop path surviving the injected fault.
No live test is authorized.
