# Roon Playlist Favorites Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Configure up to five playlists in the mobile admin and start one in Sauna through a two-second touch, encoder selection and a new confirmation tap, including from an empty queue.

**Architecture:** The Synology Roon bridge owns complete catalog browsing, exact favorite resolution, persistence and explicitly targeted playback. The Dial provides a PIN-protected admin proxy and a shared selection state machine with a Waveshare presentation. The Pi weather service receives no music commands.

**Tech Stack:** Existing Rust 2021/Axum/Tokio/roon-api/serde bridge and C/LVGL firmware, ESP-IDF 5.5.5; existing Rust, host C, browser and firmware CI gates.

**Spec:** [Approved playlist design](../specs/2026-10-03-roon-playlist-favorites-design.md).

**Status:** Owner approved execution, the proposed API contracts and recovery refinement on 2026-10-03 and selected subagent-driven development. Implementation is in progress; approval is not deployment evidence.

## Global Constraints

- **0–5 existing Roon playlists**, saved order; no downloaded music, playlist editing, cloud-service login or BLE work.
- Confirmed selection **replaces the queue and starts from the first track**, with unchanged volume and no action on another zone.
- Target the configured **Sauna zone identity**, not a fallback zone or fuzzy display-name match.
- **2,000 ms** stationary touch on central artwork/empty-artwork area, Roon page only; title long press remains settings; shower gestures remain separate.
- Opening touch is consumed through release. A **new short tap** plays; encoder moves selection without volume changes. Back or **15 seconds** inactivity exits without playback.
- Saving/browsing/reordering never starts playback. Unknown command effect is visible and never retried automatically.
- Preserve selections across device restarts, but never substitute a title match for unproven identity after Core reconnect. Unresolved choices need explicit re-selection.
- Persistent settings live in the bridge data volume, not in the Pi valve database. Keep existing PIN/CSRF/Host/Origin protections.
- No runtime deployment, physical/relay command, live playback, automatic firmware updates, merge, release or tag mutation in code tasks.

## Review Focus

- Two playlists with identical names or deletion/recreation must not play a substitute: P1/P2 exact-resolution tests.
- A favorite beyond the first 50 catalog entries must remain selectable: P2 pagination tests.
- Opening-release, wake touch or encoder backlog must not start music/change volume: P4 gesture tests.
- Core restart or timeout after queue replacement must not cause a second replacement: P3 durable request/generation tests.
- Roon artwork/network delays must not block the existing shower input or weather UI: P4/P5 isolation and combined regression tests.

## Baselines and ordered delivery

Bridge inspected revision: `b4ba5acc3a199b5f5bd94a143dea700ff0de3017`. Dial baseline: paired v1.1.0 merge `9bd5fc062d91f9ca7b3c6bd4c54dc60481129007`. Reconcile each with current fork branches before execution; do not assume a fresh device attestation. The old `roon-control` checkout contains unrelated modifications and the Windows-created companion worktree has a Windows Git pointer: neither should be reset or repaired merely for convenience. Use an attached suitable clean worktree or managed creation.

Track implementation under [Bridge #7](https://github.com/danikeuc/roon-control/issues/7) and [Dial #11](https://github.com/danikeuc/roon-knob/issues/11). Extend these issues instead of creating a competing task database. Base bridge changes on its approved v3 lineage; preserve the shipped play/pause fix. Dial changes use the custom valve branch lineage and fork remote, not upstream master.

P1 -> P2 -> P3 -> P4 -> P5. P1/P2 may proceed independently of weather backend W1–W4. Apply Dial admin/CMake/common UI changes serially after weather W5 or on a reconciled branch; never let two workers edit those files concurrently.

## Public contracts proposed for explicit approval

Prefix: `/roon/dial/v1`. These are **new** routes requiring the bridge AGENTS.md API approval and `api-change-approved` PR label. Existing `/roon/browse`, `/roon/play` and transport routes retain their contracts. Owner approval of this plan must explicitly include this table before P2/P3 route implementation.

| Method/path | Input/output |
| --- | --- |
| GET `/roon/dial/v1/capabilities` | `{version:1,max_favorites:5,replace_queue:true}` |
| GET `/roon/dial/v1/playlists?cursor=...` | `{core_epoch,catalog_revision,items:[{selection_token,title,subtitle}],next_cursor}`; pages of <=50; opaque cursor bound to session/Core |
| GET `/roon/dial/v1/favorites` | `{revision,core_epoch,zone_id,zone_name,favorites:[{id,title,available,reason}]}` |
| PUT `/roon/dial/v1/favorites` | `{expected_revision,core_epoch,items:[{favorite_id}] or items:[{selection_token}]}`; each item has exactly one selector; mixing the two item kinds is permitted in one ordered array |
| POST `/roon/dial/v1/play-intents` | `{favorite_id,expected_revision,core_epoch}` -> `{intent_id,expires_in_ms:10000}`; validates/resolves only, never playback |
| POST `/roon/dial/v1/play` | `{request_id,intent_id}` -> `{request_id,status,zone_id}`; exactly one deliberate queue-replacing action |
| GET `/roon/dial/v1/requests/{request_id}` | `{request_id,status,zone_id,error}`; status accepted/playing/failed/unknown; no side effect |
| GET `/admin/api/roon/playlists?cursor=...` on Dial | protected proxy to catalog |
| GET/PUT `/admin/api/roon/favorites` on Dial | protected proxy to favorite configuration |

All bridge routes require `Authorization: Bearer <scoped-device-token>`, provisioned privately on bridge and Dial; missing credential disables this feature. `UHC_DIAL_TOKEN_SHA256`, `UHC_DIAL_ID` and `UHC_DIAL_ZONE_ID` bind one token to this dial/configured target for the first increment. Compare token hashes without timing-dependent early exit. The token authorizes only the new namespace, never valve/admin access. This does not claim to secure existing legacy bridge routes; retain the existing trusted-LAN deployment boundary.

New Dial proxy calls require the current PIN session; PUT requires the existing CSRF and Host/Origin checks. Tokens are never returned to browser HTML/JS/status or placed in URLs/logs. Provision through a protected setup path following existing private device-credential conventions. Do not store a credential in an artifact or require posting it to chat.

Strict bodies <=4 KiB; zero-to-five unique favorites; unknown/duplicate JSON fields rejected. Favorite/request/intent IDs are opaque; request IDs are UUIDs. Title/subtitle are UTF-8 strings capped to 256 bytes at bridge response boundary, escaped as text in admin. Firmware displays bounded labels with UTF-8-safe truncation while retaining exact opaque ID. No unbounded list allocation on the ESP32.

HTTP 401 unauthorized, 409 revision/generation/expired-intent conflict, 413 oversize body, 422 invalid request, 503 Core/storage unavailable. No partial save when any selector is invalid. A full favorites write is atomic CAS, with authoritative read-back before Saved.

## Task 1 (P1): Establish exact playlist selection and playback semantics

**Files:** add `tests/fixtures/roon_playlists/PROVENANCE.md` and sanitized recorded/synthetic fixtures in bridge; add `tests/playlist_protocol_probe.rs` against existing mock server/adapter. Inspect `src/adapters/roon.rs`, pinned roon-api sources and official Browse/Item contracts.

**Interfaces produced:** `PlaylistLocator::Stable { core_id: String, provider_key: String }` only when supported by evidence; otherwise `PlaylistLocator::Reselect { core_id: String, saved_title: String }`. A process-local `ResolvedPlaylist { core_epoch: u64, item_key: String, session_key: String }` is never serialized as a permanent locator. Define these in the P2 model, with the probe fixing actual adapter navigation and action expectations.

- [ ] Add fixtures with empty queue, populated queue, duplicate names, renamed/deleted/recreated playlist, >50 entries and Core reconnect. Label synthetic fixtures as synthetic. Write assertions that the adapter reaches the explicitly selected playlist and requests its actual queue-replacing play action without a standalone queue-clear call or first-title search.
- [ ] Run `cargo test --test playlist_protocol_probe`; confirm the new contract assertions fail or expose a missing capability, rather than asserting only the mock's behavior.
- [ ] Trace existing Roon browse/load/action behavior using pinned code and official docs. If a live read-only catalog probe is needed, restrict it to list/load navigation and avoid all `action`/play entries. Never issue playback, change shuffle or restart the Core as part of a read-only probe. Store no Roon tokens or private full catalog in public fixtures.
- [ ] Record whether an exact persistent provider key is supported, and how the explicit first-track action interacts with preexisting shuffle. If no durable identity is established, use Reselect on reconnect/restart: favorites stay saved but unavailable until reselected in admin. Do not invent guaranteed title-based identity. If the actual API cannot express queue replacement + first-track semantics without extra playback changes, stop the playlist implementation for a scoped design decision; weather work can continue.
- [ ] Commit the evidence/tests with `test(roon): characterize exact playlist selection`. This task produces a verified contract or a documented blocker, not permission to fake unavailable behavior.

## Task 2 (P2): Catalog, favorite store and protected read/write routes

**Files:** create bridge `src/playlist_favorites/{mod.rs,model.rs,store.rs,catalog.rs,routes.rs}`; modify `src/lib.rs`, `src/main.rs`, `src/adapters/roon.rs`, `tests/fixtures/api_routes.txt`; create `tests/playlist_catalog.rs`, `tests/playlist_store.rs`, `tests/playlist_api.rs`.

**Interfaces:** model types `Favorite { id: String, locator: PlaylistLocator, title: String, subtitle: Option<String> }`, `FavoriteSet { schema_version: u32, revision: u64, dial_id: String, zone_id: String, entries: Vec<Favorite> }`, `CatalogPage { core_epoch: u64, catalog_revision: u64, items: Vec<CatalogItem>, next_cursor: Option<String> }`, `CatalogItem { selection_token: String, title: String, subtitle: Option<String> }`. `FavoriteStore::load() -> Result<FavoriteSet, FavoriteError>` and `replace(expected_revision: u64, entries: Vec<Favorite>) -> Result<FavoriteSet, FavoriteError>`; `PlaylistCatalog::page(cursor: Option<String>) -> Result<CatalogPage, FavoriteError>`; `resolve_selection(token: &str) -> Result<(PlaylistLocator, ResolvedPlaylist), FavoriteError>`. Use existing project Result/error conventions when defining `FavoriteError` in `model.rs` with typed Invalid/Conflict/Unavailable/Io variants.

- [ ] Write tests that exhaust pages 0–49/50–99/final page, return unique entries and reject a stale Core-bound cursor. Catalog navigation/session use must not race a playback session. Selection tokens expire after **300 seconds**, are bound to Core/catalog revision and cannot resolve another item after reconnect.
- [ ] Write store/API tests: 0/1/5 entries pass, 6/duplicates/unknown selectors fail atomically; disk-full/rename failure keeps prior version; stale CAS preserves newer order; labels escaped; corrupt established store is unavailable, not silently emptied. Reselect entries persist but do not acquire fake availability after restart. Bad/missing token cannot browse/write any new route.
- [ ] Run `cargo test --test playlist_catalog --test playlist_store --test playlist_api`; observe required FAIL before adding routes/store behavior.
- [ ] Implement P1 exact resolution, paginated catalog and the approved GET/PUT/capabilities routes. Persist `dial-playlist-favorites-v1.json` under `config::get_data_dir()` with same-filesystem temporary file, flush/fsync, atomic replacement and parent-directory fsync; a failure is not acknowledged as Saved. Serialize writes. Keep requested target zone immutable to this credential. Reuse existing dependencies; do not alter global authentication or upstream firmware settings.
- [ ] Rerun focused tests plus `cargo test --test api_contract`; PASS includes exact new route fixtures. Commit `feat(roon): add scoped playlist catalog and favorite storage`.

## Task 3 (P3): Fresh, deduplicated playlist playback

**Files:** create `src/playlist_favorites/playback.rs`, extend `routes.rs`, `model.rs`, `store.rs` and `src/adapters/roon.rs`; create `tests/playlist_playback.rs`; extend `tests/playlist_api.rs` and API route fixture.

**Interfaces:** `PlayIntent { id: String, core_epoch: u64, favorites_revision: u64, zone_id: String, favorite_id: String, expires_mono: Instant }`; `PlaylistPlayback::prepare(favorite_id: &str, expected_revision: u64, core_epoch: u64) -> Result<PlayIntent, FavoriteError>` and `.play(request_id: &str, intent_id: &str) -> Result<PlayReceipt, FavoriteError>`; `.receipt(request_id: &str) -> Option<PlayReceipt>`. `PlayReceipt { request_id: String, status: PlayStatus, zone_id: String, error: Option<String> }`, PlayStatus Accepted/Playing/Failed/Unknown. Calls use immutable captures; no network await while holding the store lock.

- [ ] Write tests proving queue replacement works when empty/populated and begins with the selected first track under the P1 semantics. Verify no volume calls, other-zone calls, standalone clears or fuzzy name lookup. Missing/replaced zone, deleted/ambiguous playlist and Core epoch changes fail before playback dispatch.
- [ ] Write replay/unknown-outcome tests: intent TTL **10 seconds**, <=16 pending intents, serialized per-zone dispatch, same request ID/body returns prior receipt, changed body conflicts, accepted request persisted before sending, crash after send -> Unknown after reboot with no replay, expiry/cancellation -> no command. Timeout after possible effect -> Unknown and status read-back only.
- [ ] Run `cargo test --test playlist_playback --test playlist_api` and observe FAIL. Bind existing zone projection/status events to correlated requests: Playing requires a post-dispatch target-zone observation correlated to the resolved first track under P1 evidence, not HTTP 200 or a preexisting unrelated playing state. If those observations cannot establish the effect, retain Accepted until the deadline and then report Unknown.
- [ ] Implement prepare/play/receipt routes and an atomic durable request journal `dial-playlist-requests-v1.json` containing the last **128** requests; do not evict pending requests to admit another. Reset unresolved Accepted receipts to Unknown after restart; all intents expire on restart. Total pre-dispatch resolution deadline **8 seconds**, existing per-RPC bounded waits retained; after dispatch, **15 seconds** without sufficient correlated observation becomes Unknown. Never automatically resend after timeout, restart or reconnect.
- [ ] Rerun suites plus `cargo test --test roon_protocol --test client_harness --test api_contract`; PASS required. Commit `feat(roon): start saved playlists with replay-safe requests`.

## Task 4 (P4): Shared picker, Dial presentation and mobile admin

**Files:** create Dial `common/controller_playlist.[ch]`, `idf_app/main/playlist_client_dial.[ch]`, `playlist_ui_dial.[ch]`, `playlist_admin_dial.[ch]`; modify `common/controller_action.h`, `controller_action_router.c`, `controller_input_profile.h`, `common/ui.c`, `idf_app/main/controller_input_profile_dial.c`, `platform_display_idf.c`, `admin_server_dial.c`, `admin_page_dial.h`, `main_idf.c`, `idf_app/main/CMakeLists.txt`; add `tests/test_controller_playlist.c`, `tests/playlist_dial/test_playlist_client.c`, `test_playlist_ui.c`, `test_playlist_admin.c`, `scripts/test_playlist_dial.sh` and extend admin browser fixtures.

**Interfaces:** `common/controller_playlist.h` defines bounded `playlist_favorites_t` (count <=5, fixed-size opaque IDs/UTF-8 labels, revision and Core epoch), `controller_playlist_t` state Idle/Picking/Preparing/Pending/Error with a Back entry, and `playlist_action_t` None/Render/PreparePlay/Cancel with an immutable selected ID/revision/epoch when applicable. IDs received from the bridge must fit their declared buffers or fail closed; never truncate identity. Shared functions return `playlist_action_t`: `controller_playlist_open(controller_playlist_t *state, const playlist_favorites_t *favorites, const char *zone_id, uint64_t now_ms)`, `controller_playlist_rotate(controller_playlist_t *state, int delta)`, `controller_playlist_confirm(controller_playlist_t *state, uint64_t now_ms)`, `controller_playlist_cancel(controller_playlist_t *state)`, `controller_playlist_tick(controller_playlist_t *state, uint64_t now_ms)`. They never call LVGL/network. Define `playlist_ui_touch(x,y,pressed,moved,now_ms)`, `playlist_ui_visible()`, `playlist_ui_cancel()`, `playlist_ui_process()` and `playlist_client_request_favorites()`, `playlist_client_request_play(favorite_id,revision,core_epoch)`. Host tests inject clocks/transports, not a duplicate picker implementation.

- [ ] Write state/gesture tests for 1,999/2,000 ms, >20-pixel movement, opening-release consumption, new tap confirmation, all five entries/Back/list-end clamping, 15-second timeout, blocked header/transport/shower/settings contexts, wake suppression, all display rotations, clear pending double-tap on open and close. Assert zero volume actions while selecting and zero valve actions in every playlist trace.
- [ ] Write client/admin tests for bounded UTF-8 labels, malicious HTML names, stale/old bridge capability, offline/Core reconnect, full mailbox, expired intent, zone change while pending, bounded unsent action age **10 seconds**, HTTP timeout read-back without replay, saved favorite read-back and unchanged PIN/duration/rotation. PIN/CSRF/Host/Origin apply to new routes on both AP and station servers.
- [ ] Create `scripts/test_playlist_dial.sh` compiling the real shared/client/admin code with host fakes and `-std=c11 -Wall -Wextra -Werror`; run it and the affected shared/admin tests, confirming FAIL for missing behavior.
- [ ] Implement selected-file interfaces and host fixtures. Obtain a fresh play intent only after the new user confirmation tap, then send once if still within the captured gesture lifetime and correct screen/zone/session generation. Store the device credential privately; no blocking HTTP, NVS or JSON parsing in display callbacks. Network requests use a dedicated bounded worker, separate from valve work. Gate the feature to this custom Dial presentation while preserving shared controller conventions and other targets.
- [ ] Add matching host/fake builds to the existing CI jobs, rerun playlist/admin/valve runners to PASS, then commit `feat(dial): add admin playlist favorites and touch picker`.

## Task 5 (P5): Combined verification, artifacts and rollback record

**Files:** add bridge `docs/dial-playlist-favorites.md`, Dial `docs/operations/playlist-favorites.md`; update API documentation, associated GitHub issues and the Pi integration evidence ledger with links only. Artifact manifests remain revision-specific; never include tokens, full private catalog or account state.

**Interfaces:** consumes P1–P4 pinned revisions and actual commands/results; produces repository verification and explicit remaining runtime tests.

- [ ] Run bridge `cargo fmt --all -- --check`, `cargo test --features server`, `cargo clippy --all-targets --features server -- -D warnings`, `cargo build --release --features server`. Compare failures with baseline before fixing unrelated code. Record any existing failure as a limitation, never as a pass.
- [ ] Run `sh scripts/test_playlist_dial.sh`, `sh scripts/test_admin_dial.sh`, `sh scripts/test_valve_dial.sh` with ESP-IDF 5.5.5 and all commands from `.github/workflows/docker.yml` `test-shared`. Build exact target with `idf.py -C idf_app build`; no flash. Preserve disabled upstream OTA and bound background traffic to avoid starvation.
- [ ] Run integrated fixtures combining weather AUTO/manual/USER_OFF, playlist loading/error and screen swipes. Confirm no media task holds the valve/control lock, no playlist tap leaks into a shower action, and Roon errors do not change weather state. This is code-level evidence, not physical relay proof.
- [ ] Document staged deployment with original Synology image digest/compose/network/restart policy/data backup and firmware/NVS backup. Preserve `network=host`, the inspected running restart policy and current data mount exactly; do not repeat the previous restart-policy mismatch. Rollback uses reviewed original image/config/data and exact prior firmware. Actual backup/restore and container recreation require later deployment authorization.
- [ ] Independently review pinned combined branch evidence via Independent Engineering Reviewer under the selected method; fix material defects and rerun affected gates. Keep PRs draft until exact-artifact checks cover: empty queue start, populated queue replacement, first track, five favorites/restart, long-touch/encoder/new tap, all rotations and no shower regression. Live playback test must be explicitly scoped to Sauna; do not combine it with valve tests. Commit documentation with `docs: document playlist favorites and verification evidence`.

## Deployment prerequisites and evidence gaps

P1 resolves native identity and shuffle interaction before playback implementation claims. The current host inspection did not find a prepared ESP-IDF 5.5.5 directory at the previous `/tmp` location; use the pinned official toolchain/CI environment and record actual version before build. No current Synology container or Roon catalog was queried during planning. Owner's configured zone ID and protected credentials are supplied privately during deployment, never inferred from display name.

Read the companion [weather plan](2026-10-03-weather-assisted-shower.md) for its independent actuator/deployment gates. A successful playlist build neither enables weather nor proves valve behavior. Both features remain off/unavailable until compatible server capability and private configuration are present.
