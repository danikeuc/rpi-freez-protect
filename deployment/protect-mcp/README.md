# Protect MCP person-to-light adapter

Standalone Linux Python 3.12+ process. Installed Protect MCP/SDK environment:
`unifi-protect-mcp==0.9.2`, `mcp==2.x` snake_case SDK fields. The VM's captured
requirements.lock pins actual dependencies. This script adds no dependencies to
the Raspberry Pi package and owns no GPIO. The Pi remains the only authority for
AUTO/manual modes, default 300-second hold, persisted deduplication and expiry.

## Installed checkpoint

The Pi light runtime is installed with initialOFF confirmed by the owner receipt.
Camera credential and PiTLS identity were verified directly fromVM. The adapter
now runs in **forward** mode for G4Pro/person only; startup creates a new boundary.
Fresh-person delivery/relay acceptance remains pending. See
[activation evidence](../../docs/evidence/2026-10-15-light-runtime-activation.md).
The earlier [observe-mode evidence](../../docs/evidence/2026-10-15-protect-mcp-adapter.md)
records the preparation stage.

## Admission contract

- Exact G4 Pro ID `6797d43f03968103e40003f1`, type smartDetectZone AND subtype person.
  Other cameras, plain motion, vehicle-only and animal-only events are ignored.
- Read up to100 original smart detections from the last60s via protect_execute /
  protect_list_smart_detections. A full or inconsistent page disarms admission;
  no blind pagination of an old backlog. Query min_confidence=0 adds no threshold
  on top of Protect's person classification; camera false positives remain possible.
- Use original ID/start, canonical UTC. Never substitute arrival time or a new ID.
  Future events are rejected (stricter than the Pi's five-second clock allowance).
- First successful poll after startup/reconnect establishes a boundary and sends
  nothing. A clock discontinuity or gap over20s also establishes a new boundary.
  Older detections, including an ongoing detection that started before that
  boundary, are discarded. A new detection is required.
- Consume IDs before sending. In-memory dedup retains120s; restart has a new
  boundary; Pi also retains durable identities. Duplicate updates do not renew
  the hold. This is detection-triggered lighting, not continuous occupancy sensing.
- MCP init20s / request15s deadlines. Failures reconnect with bounded5–60s backoff.
  Responses over128KiB or malformed batches are rejected.
- One POST attempt per admitted event; no queued/retried POST after ambiguity.
  Delivery socket inactivity5s, total8s using POSIX SIGALRM in the dedicated main
  process. No abandoned background HTTP worker can send later. API receipt can
  say accepted, inhibited (e.g.manual mode), or duplicate; logging distinguishes them.
- No redirect, proxy, or TLS-verification bypass for the Pi sink. The approved
  Protect-specific certificate exception is confined to its existing MCP launcher.
- Private config/token regular files must belong to the service user and be0600.
  Logging contains aggregate counts/state only, never credentials/event payloads.

## Installation and operation

Copy the script and example to a private directory
`~/.local/share/protect-light-adapter/` and example as mode0600
`~/.config/protect-light-adapter/config.json`. Copy the service to
`~/.config/systemd/user/protect-light-adapter.service`. Inspect the example's
launcher path against the installed host before installation. Existing config
must be preserved, not silently overwritten. This user service requires the
existing read-only MCP launcher and venv. A second MCP process is independent of
the one Codex starts over SSH; neither exposes an HTTP listener.

```sh
systemctl --user daemon-reload
systemctl --user enable --now protect-light-adapter.service
systemctl --user show protect-light-adapter.service -p ActiveState -p NRestarts
loginctl show-user "$USER" -p Linger
journalctl --user -u protect-light-adapter.service -n 10 --no-pager
```

Linger must be enabled for unattended user-manager lifetime; it is verified on
linuxvm. Boot configuration is enabled; a VM reboot test has not been performed.
Stop with `systemctl --user disable --now protect-light-adapter.service`. No Pi
state change is issued when starting or stopping this observer.

## Forward activation contract (software activation completed; device acceptance pending)

1. Complete existing disconnected GPIO21/paired-output coexistence and executor
   acceptance. Install/provision the independent light service through a reviewed
   Pi maintenance procedure. Do not widen the forced-command SSH allowlist.
2. Provision a camera-only token distinct from Dial/settings/shower credentials.
   Allow only the exact selected camera ID at Pi. Do not export existing secrets.
3. Provide a verified HTTPS route for POST `/api/v1/lights/events/unifi`, to the
   loopback light controller8002. This route was installed and its certificate/authentication verified on2026-10-15.
   Existing disabled Node-RED webhook templates remain disabled; MCP uses the
   normalized camera-role API, not a fabricated Protect webhook payload.
4. Review concrete config with mode=forward, endpoint, absolute token_file and
   optional trusted ca_file. No other mode or API action is supported. Restart
   creates a new boundary and never replays observer history.
5. Perform separately authorized bounded disconnected-load acceptance: new person,
   duplicate, manual inhibition, return to AUTO, expiry, link loss and recovery.
   Record controller history, GPIO and physical observations separately. The owner authorized connection to the disconnected light relay; new-detection
   acceptance is now pending.

The user requested implementation, not an unreviewed substitute for open device
gates. Software forwarding is active; this does not establish physical acceptance.
