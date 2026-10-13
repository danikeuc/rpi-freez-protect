# Independent lighting deployment templates

Task 2 repository assets,2026-10-13. Nothing here installs, enables, deploys or
accesses GPIO. Canonical behavior:
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

**Activation remains blocked with the installed legacy paired mmap daemon.**
GPIO20/21/26 share FSEL2; the legacy configure path can overwrite a concurrent
kernel GPIO21 update using its stale register snapshot. The separately
authorized repair now removes userspace FSEL access from candidate source:
exclusive kernel reservation/configuration for GPIO26/20 surrounds restricted
single-mask GPSET0/GPCLR0 writes and readback. See the
[ownership migration runbook](../../docs/operations/paired-gpio-migration.md) for exact profile, interpreter,
dependency, device mapping, lifecycle and rollback requirements.

This is a source repair, not an installed migration or physical acceptance.
Keep lighting templates, flow and gateway disabled. Do not create
/etc/independent-light/commissioned, set LIGHT_GPIO21_ENABLED=commissioned or
grant light DeviceAllow until exact installed paired migration plus disconnected
startup/request/release/crash acceptance is recorded. Kernel-only configuration
resolves the source FSEL writer race; it does not establish atomic initial
direction changes, crash protection, physical independence or valve position.
The current installed Pi/Dial records and all lamp/wiring/Protect gates remain.
Initial ordering or a userspace lock alone cannot repair the legacy writer.

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
| Executor crash/hang | Surviving supervisor/hardware releases | Release behavior/maximum cutoff |
| Pi reset/reboot | Bias/startup OFF; never restore ON | Pre-software boot trace |
| Pi, relay, lamp power loss/restoration | Verify each independent domain | Bias/contacts; active-command lamp restoration acceptance |

Rollback closes light ingress, requests/verifies OFF through light owner with
fresh state, then stops only light units/restores only light assets. If OFF cannot
be verified use the commissioned physical isolation path; none established here.
Never reset shower DB/flow or issue shower commands. Future live tests require
an observer, bounded duration/cutoff and stop path surviving the injected fault.
No live test is authorized.
