# Roon playlist favorites on the Waveshare dial

Status: **APPROVED FOR IMPLEMENTATION PLANNING**, 2026-10-03. The owner
approved this written design after confirming replace-queue-and-play behavior.
The implementation plan and its exact additive API contracts require review
before execution. This feature is not implemented or deployed.

## 1. Intent and independent delivery scope

Start music in the Sauna Roon zone from the Waveshare ESP32-S3 dial even when
its queue is empty. In the existing phone admin page choose up to five existing
Roon playlists. On the dial hold for two seconds, rotate to choose, and tap to
play. This complements the approved weather-assisted shower design but has
separate code, contracts, tests and deployment dependencies. BLE remotes remain
excluded. Preserve the paired v1.1.0 release and its rollback artifacts.

Tracking remains in GitHub, not in a parallel document task list:

- [Dial issue #11](https://github.com/danikeuc/roon-knob/issues/11)
- [Bridge issue #7](https://github.com/danikeuc/roon-control/issues/7)

## 2. Evidence and limits

The bridge source at `b4ba5acc3a199b5f5bd94a143dea700ff0de3017` has
`POST /roon/browse`, explicit zone targeting and browse session keys. Its
handler loads at most 50 items and does not expose full catalog pagination
in the inspected request. These are source observations, not a fresh claim
about the running Synology container or the owner's playlist catalog.

Official [Roon Browse documentation](https://roonlabs.github.io/node-roon-api/RoonApiBrowse.html)
lists a `playlists` hierarchy, paginated loading, session state and required
zone/output identity for playback. The [Item contract](https://roonlabs.github.io/node-roon-api/Item.html)
provides `item_key`, title and optional subtitle, but does not establish durable
playlist identity across reconnects. Do not promote an opaque browse key or
playlist title into a guaranteed permanent identifier. Sources checked 2026-10-03.

Dial source inspected in `common/ui.c`,
`idf_app/main/platform_display_idf.c` and
`idf_app/main/controller_input_profile_dial.c` already uses a long press on the
zone header for settings, encoder movement for volume or zone selection, and
separate shower gestures. Those existing paths must be preserved.

## 3. Admin experience

Add a Roon playlists section to the existing PIN-protected mobile admin.
The user selects up to five playlists from the actual Roon catalog and changes
their order or removes them. Fewer than five, including zero, are valid.
No manual URL entry, music download, playlist editing, or cloud account login
is introduced. Only saved shortcuts and display metadata are sent to the dial;
Roon continues to obtain and play the music.

The section shows the target zone (Sauna), connection/error state, and only
reports Saved after authoritative persistence and read-back. Merely browsing,
saving or reordering favorites never changes playback. Preserve the existing
PIN/CSRF/Host/Origin protections and existing duration/rotation settings.

List the complete available playlist catalog, with pagination/search as needed;
a playlist beyond item 50 must remain selectable. Titles are plain escaped text.
Truncate long display labels without destroying the identity or full admin name.
An empty catalog or unavailable Core is an explicit state, not an empty success
that overwrites the saved favorites.

## 4. Dial interaction

On the Roon page, holding the central artwork area for 2,000 ms opens the
playlist picker. Keep a usable central placeholder area when there is no
artwork, current track or queued music. The zone header keeps its existing
settings/zone gestures; transport buttons keep their current short actions.
The shower page retains its existing deliberate start/stop interaction.

A stationary touch is required; movement beyond the existing gesture tolerance
cancels the hold. Wake-only touches, screen changes, rotation changes and open
settings/zone dialogs do not open the playlist picker. Opening the picker consumes
the entire touch through release and clears pending tap/double-tap recognition.
A distinct new short tap is required to start playback.

While the picker is open:

- Show the target zone and up to five favorites in saved order, with an obvious
  highlighted choice. Include a Back item.
- Rotate one selection step at a time, without volume acceleration or volume
  commands. Selection stops at the list ends.
- Tap a favorite to request playback; tap Back to exit without playback.
- Exit after 15 seconds without interaction and discard any pending gesture.
- Exiting restores normal encoder volume behavior after consuming old events.
- Changing the selected zone or losing current zone identity cancels the picker;
  never silently apply a captured request to a different zone.

The first increment targets the configured Sauna zone identity. Other selected
zones do not inherit permission to play Sauna favorites silently; the picker
shows its target and is available only when that zone is selected. Renaming a
zone does not authorize matching an unrelated zone by display name.

## 5. Playback semantics

Confirmed owner decision: selecting a favorite **replaces the zone queue and
starts from the first playlist track**. It must also work with an empty queue.
No append, shuffle-selection or automatic fallback to an arbitrary song is
introduced. Validate the exact Roon play action and any existing shuffle-state
interaction before claiming first-track behavior. Do not change volume or any
other zone as part of this operation.

The bridge resolves and validates the favorite and target before requesting
Roon's queue-replacing play action. Do not issue a standalone queue clear followed
by an uncertain lookup. A failed lookup must leave current playback untouched.
An action timeout after dispatch may have an unknown outcome: display that fact,
refresh actual zone status, and require a fresh user action instead of replaying.
Disable repeated confirmation while a request is pending. Correlate completion
with the request, selected zone, Core connection generation and favorites revision.
Use a bounded command lifetime and idempotent handling; implementation planning
must specify exact values and restart semantics before adding a play endpoint.

Show Loading after accepted dispatch and Playing only after zone status confirms
playback. A 200/accepted response alone is not proof that audio is playing.
Errors remain visible and retryable by a new deliberate tap.

## 6. Architecture and persistence

Selected architecture: the existing Synology bridge owns the playlist catalog,
browse sessions, favorite resolution and media requests. The Dial owns its UI
and proxies its PIN-protected admin requests. The Pi weather/valve service has
no playlist or media-command responsibility.

Alternatives considered: implementing the entire browse traversal on the ESP32
would increase firmware complexity and couple saved favorites to transient Roon
navigation state. Direct cloud-service playlist integration would require new
accounts and duplicate Roon's existing sources. Neither is selected.

Persist at most five favorites per dial/configured target in the bridge's existing
persistent data area, using versioned additive records and atomic writes. Use
stable internal favorite IDs plus Core/target provenance, selection identity
and display metadata. The dial may cache labels/order, but playback requires
fresh bridge resolution and target validation. Admin updates carry an expected
revision; stale concurrent writes fail without overwriting a newer selection.

A read-only protocol probe must establish how to re-resolve exact playlist
identity across reconnects. If a durable native identity is unavailable, the
implementation must expose unresolved/reselection state rather than fall back
to fuzzy title matching or silently choose among duplicate names. Preserve saved
entries through outages; renamed/deleted/ambiguous entries cannot play a substitute.
This identity boundary is an implementation-readiness condition, not an assumption
that the current browse API already supplies the needed guarantees.

Admin listing and playback use distinct, serialized browse sessions so navigation
in the phone cannot move the playback request's browse stack. Paginate using
Roon's actual load API, not repeated reads of the first page. Reconnect invalidates
all transient browse keys and in-flight generations.

Plan the smallest additive bridge API needed for catalog, favorite read/write and
explicit favorite play, including capability/version and request/result schemas.
Under bridge AGENTS.md, obtain explicit approval of those exact API contracts
before implementation. Existing endpoint behavior remains compatible. Scope the
admin/play access using the actual bridge authentication model; no new public
unauthenticated management surface or credentials in browser HTML/logs.

## 7. Verification and delivery boundaries

Required checks cover zero/one/five favorites and rejection of six, long/Unicode
names, duplicate titles, entries beyond 50, admin persistence/concurrent saves,
Core loss/reconnect, renamed/deleted playlists, missing target zone, empty and
populated queues, late/duplicate requests, unknown post-dispatch results and
first-track behavior including preexisting shuffle settings.

Gesture tests exercise 1,999/2,000 ms, movement cancellation, opening-release
consumption, a new confirmation tap, no volume adjustment in picker, Back/timeout,
wake suppression, normal play/pause, zone/settings gestures, horizontal page
swipes, and rotations 0/90/180/270 degrees. Playlist gestures must never issue
shower requests; Roon errors must never alter the weather policy or paired outputs.

A live playback test is separate from repository verification and uses an explicitly
approved target/operation. This design does not authorize live playback, changing
volume, GPIO, flashing, deployment, merge or release. Firmware and bridge changes
require exact-revision tests and rollback evidence before publication.

Weather implementation planning can proceed from its separately approved spec.
The [playlist implementation plan](../plans/2026-10-03-roon-playlist-favorites.md)
is ready for review alongside the independently approved weather specification.
Neither new feature is currently implemented by these documents.
