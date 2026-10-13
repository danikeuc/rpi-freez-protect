# Independent Lighting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the approved independent relay-3 light, camera AUTO and Dial/admin control with a visible timed manual override.

**Architecture:** A separate Python light service owns policy and durable state; a separate bounded-lease GPIO21 executor owns I/O. Node-RED only validates/forwards camera events. Dial supplies intent and renders confirmed state through light-scoped credentials.

**Tech Stack:** Python 3.12, FastAPI/Pydantic2/SQLite, Unix sockets, optional Linux libgpiod2, Node-RED JavaScript, ESP-IDF5.5.5 C/LVGL and existing PIN admin HTML.

**Spec:** ../specs/2026-10-12-independent-lighting-design.md

## Authorization and implementation boundary

2026-10-13 owner requested implementation after approving the recorded product behavior. Continue implementation and software review in the existing isolated worktrees; no deploy, GPIO access, flash, merge or release. Track delivery in roon-knob issue15. The physical and Protect-specific unknowns in the spec are commissioning/profile gates, not permission to guess wiring or accept unauthenticated events. Defaults remain unavailable until explicitly configured. A tested normalized adapter is provided; actual Protect field paths/auth capability must be commissioned before accepting its events.

## Global Constraints

- Independent light: never write or release GPIO26/20; paired shower service/protocol stays unchanged.
- AUTO camera hold defaults to 300 seconds after last distinct accepted event; admin configurable whole minutes 1..120. Dial timed ON uses the same duration.
- MANUAL_ON/OFF default 3600 seconds; configurable whole minutes 1..120. Camera ignored and deduplicated in manual mode. No queued/replayed activation on return.
- Return to AUTO clears holds and requests OFF. Reboot never restores energized intent; valid manual remainder recovers inhibited, uncertain clock/state faults visibly.
- Monotonic running deadlines, UTC persisted deadlines/event freshness, serialized mutations, strict revisions and stable IDs.
- Exact Slovenian manual copy: ROČNO — kamera začasno izključena; AUTO čez 42 min; Nazaj na AUTO. Small bulb+M on both other pages; stale status remains explicitly unknown.
- Separate SQLite/light credentials. No browser-exposed tokens, raw event logging, BLE command changes, Roon changes, firmware upload or physical actuation.
- Readback describes GPIO only, never lamp illumination. Hardware boot/power/crash timings remain unverified until commissioning.

## Review Focus

1. A retransmitted event or lost HTTP response must not extend ON: persist idempotency and reject ID reuse with different content (Task 1/2).
2. An OFF/mode change racing with camera or stale UI must not replay old intent: generation/revision and original event time fences (Task 1/3).
3. Manual timer expiry during offline UI must not silently claim AUTO: stale badge remains and fresh status required (Task 3).
4. Persist/write/readback/clock failures must not silently recover or confirm ON: force requestedOFF and explicit fault recovery (Task 1).
5. Existing shower/Roon/BLE input and credentials must remain isolated, including disabled-capability older installations (Task 2/3).

## Shared wire contract

Dedicated light controller loopback 127.0.0.1:8002; public exact API prefix /api/v1/lights via gateway 8081. Schemas use extra=forbid, strict integers, bounded strings and bodies; JSON numeric revisions limited to 2^53-1.

GET status returns {capability:"independent_light_v1", revision:int, mode:"AUTO"|"MANUAL_ON"|"MANUAL_OFF", desired_on:bool, gpio_on:bool|null, health:"OK"|"FAULT"|"UNAVAILABLE", reason:string, remaining_seconds:int, manual_remaining_seconds:int, observed_at:stringUTC}. Auth: display OR settings token.
POST actions body {request_id:string, expected_revision:int, action:"timed_on"|"off"|"manual_on"|"manual_off"|"auto"}; display token only. Return matching status; HTTP409 conflicts;503 unavailable/uncertain. Never silently retry actions.
GET settings returns {revision:int, hold_seconds:int, manual_seconds:int}; PUT {request_id:string,expected_revision:int,hold_seconds:int,manual_seconds:int}; settings token only. Settings changes do not alter existing deadlines. Separate settings/control revisions.
GET history?limit=20&offset=0 returns {items:[{id:int,at:stringUTC,source:string,mode:string,desired_on:bool,reason:string}],limit:int,offset:int}; settings token only. Limit1..100, offset0..1000000, bounded storage1000history entries.
POST events/unifi normalized body {event_id:string,source_id:string,occurred_at:stringUTC}; camera token only. Original stable ID, allowlisted source, event age<=60seconds/future skew<=5seconds, no control actions. Return {accepted:bool,duplicate:bool,status:<statusDTO>}. Reject duplicates with changed content; preserve IDs at least 120 seconds, bound 4096 entries with rejection when full. API private tokens distinct >=32characters, constant-time compare, no echoes. Unconfigured service refuses activation.
Controller/executor protocol: Unix stream bounded JSON <=2048 bytes, requests with protocol_version=1, command=OFF|ON, action=begin|renew for ON, request_id, deadline_unix_ms at most 1000 ms ahead. Executor returns matching request_id/command/protocol_version, gpio21 and lease identity. OFF revokes lease even when acknowledgement fails. ON lease maximum 3 seconds, renew from a separate service every <=1 second; renewal cannot revive expired/unknown lease or executor generation. Controller loss turnsOFF by executor expiry; executor fault forces explicit new intent after freshOFF. No safety claim for executor hang/power until measured.

## Task 1: Separate Pi controller, durable policy/API and GPIO executor

**Files:** create src/freeze_protect/lighting/{__init__,models,store,controller,executor,api,main}.py; tests/unit/test_lighting*.py and tests/integration/test_lighting*.py; modify pyproject.toml only for optional backend dependency if needed.
**Interfaces:** create_app(database_path, display_token, settings_token, camera_token, executor, allowed_sources, clock) for test injection; production python -m freeze_protect.lighting.main binds8002. LightController owns tick/status/actions/settings/events/history. ExecutorClient exposes off/begin/renew with validated receipts; real GPIO backend requests only line 21 initializedinactive atomically; fake backend injectable. Main executor invoked as python -m freeze_protect.lighting.executor. Optional gpiod2 imports never required by ordinary shower/tests.
- [x] Write failing policy/API tests for AUTO overlap,300-second default, one-hour manual,ignored and duplicate camera events,60-second freshness, stale/conflicting revision and ID reuse.
- [x] Run focused tests, record red result; implement policy, SQLite durable transaction/idempotency, strictauth/DTOs and independent lifespan worker.
- [x] Add restart/manualUTC/clockrollback, diskfault, uncertain/mismatchedreceipt, leasedexecutorrestart/expiry/fault tests; implement handling. Keep database locking short; no asyncblocking network on common shower process.
- [x] Implement separately gated GPIO21 executor and socketclient, test fake line ownership, initialOFF, generation, stale/fragmented/oversized socket requests and bounded slow client handling. No arbitrary pin argument and no mmap shared FSEL read-modify-write.
- [x] Run .venv/bin/python -m pytest -q plus ruff check . and mypy src; report exact commands/results. Commit task files and report interfaces/deviations for Task 2/3.

## Task 2: Node-RED adapter and disabled deployment assets

**Files:** create deployment/lighting/{README.md,unifi-adapter.js,lighting-flow.json,light-gateway.conf,light-controller.service,light-gpio.service,environment.example}; tests/integration/test_lighting_assets.py and tests/node-red/test_lighting_adapter.cjs (or existing test convention); update docs/operations/independent-lighting-node-red.md.
**Interfaces:** match Task 1 API exactly; separate LIGHT_* environment tokens private. Existing paired flow and nginx file untouched; new light-gateway is reviewed additive include, not auto-enabled. Service files have no dependencies that restart shower services. Node-RED adapter keeps req/res/_msgid and exactlyonebounded response; localcontroller solepolicy.
- [x] Test missing authentication, wrong method, source/body/schema rejection, repeated originalevent identity, no GPIO or global context, bounded upstream timeout and sanitized failure.
- [x] Implement normalized-profile adapter with explicit configured field paths for actual Protect payload, reject missing profile/identity/time; separate ingress credential vs forwardedcamera token, no URL tokens or caller-controlled upstream URL.
- [x] Create flow export and additive nginx/systemd examples disabled by default. Service sandbox separation, restart/watchdog bounds and unresolved GPIOrelease behavior clearly documented; no installer autoactivation.
- [x] Inspect flow with node-red-engineer inspect_flow.py; run adapter and integration asset tests. Document actual Protect sample/version still pending and exact profile activation requirements. Commit and review.

## Task 3: Dial page, worker and PIN admin

**Files:** create idf_app/main/light_{client,ui,admin,config}_dial.{c,h}; modify idf_app/main/CMakeLists.txt, main_idf.c, common/ui.c and relevant existing page/input hooks; admin_server_dial.c, web/admin_dial.html and generated admin_page_dial.h; create scripts/test_light_dial.sh and tests/light_dial/* plus admin browser regressions.
**Interfaces:** use Task 1wirecontract; separate persistedlight URL/display/settings credentials, tokens writeonly adminconfiguration and never rendered. Existing PIN/session/CSRF networkauth applies. light worker polls independently offLVGL/HTTPserver threads with boundedHTTP, invalidates stale/sessionconfig replies and actiongeneration. Third page onlycapable/configured; unsupported/unconfigured page disabled with setup explanation. NormalAUTOtap timed_on/off; explicit manual ON/OFF/BackAUTO controls; rotation/swipes consistentexisting pages. Simplevectorbulb rendering no new binary assets.
- [x] Write failing native fixtures for status strictparse,3modes,staleclock, requestrevision/body, workerqueue/cancellation and noactionautoreties; implement client/config/privatecredential storage.
- [x] Add lightpage and small manualreminder onTuš/Roon. Test entering/leavingpage,three-page horizontal navigation,vertical Roon zone gesture untouched, rotaryRoon/playlist andQGSQunchanged.
- [x] Add PINadmin lightsection with hold/manual sliders,modecountdown,explicitactions/history,privateconfiguration. Tests assert secretredaction,CSRF,stalesession,adminsave noON,olderPicapability andhistorysideeffectfree.
- [x] Run test_light_dial.sh plus existing admin/valve/playlist/weather native/browser suites. Build exact Waveshare ESP-IDF target with existing toolchain if available; report missing toolchain asbuildunverified, neverflash.
- [x] Update bothrepositorydocs currentimplementationvscommissioning,commit and taskreview.
- [ ] Finish wholebranchreview with exactSHA and allopenhardware/profilegates.

## Delivery

Implementation is source/software-verification delivery. Hardware deployment, real Protect profile acceptance, observation of GPIO/contacts and mains connection require a separate reviewed commissioning envelope. Do not mark hardware or installed UI passed from simulation/build. Publish neither a release nor a merge in this task.

## Implementation record

Task 1 passed review at `8425087`; task 2 passed at `1c63837`.
Full Pi checks: 739 tests, Ruff, strict mypy (34 source files) and package build.
Nine adapter tests passed; exported flow inspection found zero structural issues.
Task 3 adds the Dial integration and wires new tests into existing CI in both
repositories. Detailed results and remaining commissioning gates are in the
[implementation evidence](../../evidence/2026-10-13-independent-lighting-implementation.md).

Task 3 implementation and scoped fix review complete at Dial `8e6a9b8`;
focused native/browser checks and exact ESP-IDF 5.5.5 build passed.
