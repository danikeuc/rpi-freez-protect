# Shower operation history

The Pi now records `shower_transition` events in the existing SQLite audit
database. History begins when this version is installed. Older audit messages
are not reconstructed into an invented timeline.

## Recorded events

Each row contains a UTC timestamp, configured mode, controller operation,
command (DRAIN or SUPPLY), and a bounded reason code. Operations are STARTING,
SHUTDOWN, FAULT, USER_OFF, MANUAL_ACTIVE, AUTO_SUPPLY, MANUAL_IDLE, SAFE_DRAIN
and FROST_PROTECTION. Legacy automatic NORMAL is shown as AUTO_SUPPLY.
Repeated identical operation/command pairs are omitted, including lease
renewals and the change from timed_shower_started to timed_shower_active.
A reason-only change within the same operation is not a new transition.

Startup first confirms the paired DRAIN receipt and records STARTING, then
records the evaluated operation. Each process startup is a new boundary.
Successful orderly shutdown records SHUTDOWN; an already faulted controller
remains FAULT. Unexpected power loss cannot record a shutdown. Timestamps use
the Pi clock; insertion order is authoritative when the clock moves backwards.
History reports controller commands, not independently measured valve position.

## Persistence and failure

Rows survive process restarts in the existing database and are included in its
normal backup. No automatic retention/deletion policy is added. New history rows
share the existing audit failure policy: a failed write latches a persistence
fault and attempts DRAIN. This adds one durable write per transition, not per
control cycle. A disk failure can itself prevent recording the fault; history
must not be treated as complete physical evidence. There is no recursive retry
of a failed history write.

## Read-only display API

`GET /api/v1/display/history?offset=0` requires the same
`X-Weather-Settings-Token` as weather administration. Admin and display tokens
are not substitutes. Offset is an integer from 0 through 1000000, default 0.
There are ten entries per page, newest insertion first:

```json
{"items":[{"occurred_at":"2026-10-11T12:00:00+00:00","mode":"weather_assisted","operation":"AUTO_SUPPLY","command":"SUPPLY","reason":"weather_eligible"}],"offset":0,"has_more":false}
```

The response projects only these five whitelisted fields from dedicated
history rows. Generic audit diagnostics, tokens and configuration are excluded.
Text bounds keep a ten-row response below 4096 bytes. Empty history returns
200 with an empty items list; unavailable or malformed storage returns 503.
Database reads use SQLite mode=ro and do not call live control status, expire a
timer, fetch weather, change settings, or operate relays. The nginx route exposes
GET only. Offset pagination is not a frozen snapshot: use refresh to restart
at offset zero if new transitions occur while viewing older pages.

## Verification boundary

Repository tests use simulated paired drivers, clocks, weather workers and
temporary SQLite files. Deployment and live device acceptance are separate
steps; adding this source does not establish that a running Pi has history.
