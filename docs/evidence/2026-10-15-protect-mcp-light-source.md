# Protect MCP and selected lighting source — 2026-10-15

## Owner decisions

- Use sirkirby/unifi-mcp on linuxvm for Protect access.
- Selected camera: G4 Pro, exact Protect ID `6797d43f03968103e40003f1`.
- Selected detection: **person** only. Motion, vehicle and animal detections
  alone do not qualify.
- Existing light contract remains: AUTO hold 300 seconds after the last distinct
  accepted detection; manual ON/OFF suspends camera control until return to AUTO.

## Verified read-only installation

Protect MCP 0.9.2 is installed in a dedicated Python 3.13 environment on linuxvm.
Codex connects by SSH stdio. No MCP HTTP listener is exposed. The existing SSH
key restrict option prohibits PTY; private credential input was repaired to use
local PowerShell and encrypted stdin. No SSH restriction was removed.

Private controller credentials are stored on the VM in mode 0600 files. The
owner explicitly accepted a TLS verification exception for this Protect MCP
because the console presents a self-signed unifi.local certificate at its IP.
This exception does not establish authenticated certificate identity and does
not change global TLS settings. CREATE, UPDATE and DELETE are blocked by policy.

Direct tools in the restarted Codex chat read four connected cameras and the
selected G4 Pro details. The camera advertises person, vehicle and animal smart
detections. A bounded read with camera_id fixed to the selected ID,
detection_type=person, limit=3, min_confidence=0 and compact=true returned three
smartDetectZone events, each with smart_detect_types=[person], the exact camera
ID, an original event ID, original UTC start/end, and a confidence score.
The zero threshold was a diagnostic query choice, not an approved new automation
confidence threshold. No images were read.

## Integration boundary

These are MCP API observations, **not Protect webhook payload captures**. Event
identity stability across retries/reconnects remains to be tested. No historical
sample may be replayed into the lighting controller.

An unattended integration must continue independently of Codex and enforce:

1. Exact camera ID and person subtype filtering; smartDetectZone alone is too broad.
2. Original event ID and original start time (never a generated UUID or receive time).
3. Existing age/future bounds, persistent deduplication and mode arbitration at Pi.
4. No replay of old detections after startup, reconnect or return from manual.
5. Separate lighting credentials and local expiry when Protect/VM/network fails.

The existing Node-RED webhook profile cannot be declared commissioned from these
MCP samples. Continuous MCP consumption needs its own bounded adapter and service;
the installed on-demand Codex MCP connection alone does not automate the lamp.
No light service/flow/GPIO activation, Protect alarm mutation or energized test
was performed. Existing disconnected commissioning requirements remain open.

## Subsequent authorized implementation

The owner then requested implementation. The continuous VM observer is now
installed; see [adapter evidence](2026-10-15-protect-mcp-adapter.md). Source behavior
uses Protect's person classification without an additional confidence threshold.
This supersedes the pending-consumer wording above for observation only; no
camera-to-relay activation has occurred.
