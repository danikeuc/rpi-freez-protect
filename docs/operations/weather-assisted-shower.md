# Weather-assisted shower operation

Repository candidate verified on 2026-10-03. This runbook is a later operator procedure, not deployment or live-test authorization. Read [current evidence](../PROJECT_STATE.md) and [validation](../evidence/2026-10-03-weather-plan-validation.md). Published v1.0.0/v1.1.0 artifacts remain immutable.

## Policy and ownership

The Pi owns preferences, inhibition, timer and valve decisions. The paired daemon alone writes BCM 26+20: high/high DRAIN or low/low SUPPLY; mixed states are prohibited. Logical receipt/readback is not valve position. PT100 is informational in this mode; existing safe_drain, manual_timed and legacy seven-day automatic remain available under their existing gates.

`weather_assisted` and the saved enabled preference must both be selected. Fresh settings are disabled. Eligibility needs today plus four consecutive local dates, five finite minima >=5.0 C (equality qualifies), matching location/settings revision and default Europe/Ljubljana timezone. Refresh cadence is 900 monotonic seconds; accepted fetch deadline 5 seconds; total snapshot lifetime <1,200 seconds; control processing bound 30 seconds. Latest-fetch failure invalidates warm cache. Missing/cold/invalid/stale data gives manual fallback and idle DRAIN. Local date/clock changes invalidate unsuitable observations; successful new acquisition is needed to recover an invalid time basis.

A deliberate START chooses AUTO if eligible, otherwise a whole-minute 60–600-second manual interval. Settings changes, forecast changes and duplicate commands never extend an accepted manual deadline. At expiry the controller confirms DRAIN before a later cycle can enter AUTO. AUTO has remaining_seconds=0 and the Dial displays AUTO. STOP durably inhibits reopening until a fresh deliberate START. Weather recovery cannot clear FAULT or inhibition. Interrupted manual or AUTO markers after an unclean stop also require deliberate START. Failed or ambiguous receipts request DRAIN/FAULT; failed RENEW never becomes BEGIN. The existing daemon lease is 60 seconds while that daemon runs.

## Compatible interfaces and credentials

| Route | Credential / behavior |
| --- | --- |
| GET display/status | Display token; additive version, operation, revision, nonce and weather fields; GET does not enable AUTO |
| GET/PUT display/weather-settings | Distinct restricted weather settings token; exact saved schema and revision CAS |
| POST display/actions/start or stop | Display token; UUID request ID, expected control revision, single-use nonce; start also requires duration_seconds |
| POST display/actions/timed-shower | Legacy bounded action; cannot clear weather USER_OFF/FAULT; AUTO transition confirms DRAIN first |
| POST display/actions/drain | Legacy unconditional operator DRAIN; inhibits weather |

All Pi routes above start with `/api/v1/`. Weather credentials use `FREEZE_PROTECT_WEATHER_SETTINGS_TOKEN`, separate from display/general admin tokens. Dial PIN-session GET/PUT `/admin/api/weather` proxies settings, with existing CSRF/Host/Origin protection on PUT. Browser responses contain no credential. Provision secrets only through protected existing setup; never use URLs, chat, artifacts, logs or screenshots for credentials or private coordinates.

New bodies are strict <=4 KiB, reject unknown/duplicate fields, bool-as-int and nonfinite values. Nonces live 10 seconds and bind one revision; stale revision/nonce conflicts require fresh status plus a new deliberate gesture. Matching request replay returns its recorded result revision with fresh status and performs no I/O. HTTP timeout means uncertain effect: do not automatically retry START. An operator STOP conflict can be followed by a new deliberate legacy DRAIN. Errors: 401 credential, 409 conflict/not-ready/replay, 413 size, 422 invalid, 503 storage/controller unavailable.

## Staged later deployment

1. Obtain separate deployment authorization. Keep 24 V disconnected and water isolated according to the existing [commissioning guide](../../deployment/COMMISSIONING.md). Complete software gates, current service/flow preflight and exact source/artifact identification first. Do not use this procedure to enable weather while dependency/integration/physical gates remain open.
2. Protect a consistent pre-migration SQLite snapshot with matching configs, service assets and exact prior Pi/Dial v1.1.0 artifacts. For a candidate database that already has weather identity, preserve `<database filename>.weather-identity` with the matching database. Preserve permissions and fsync/backup verification. The identity sentinel and SQLite identity must match; never delete the sentinel to bypass a fault. A live SQLite file copy without a consistent backup method is insufficient. Record verified hashes privately; retain any WAL/SHM needed by the selected consistent snapshot procedure.
3. Deploy compatible Pi/Dial source through the documented trusted-console route. Retain `manual_timed` and saved weather disabled. Retain one GPIO writer and validate the deployed Node-RED flow, not only repository JSON. Provision the distinct restricted token privately. Read back saved settings and authenticated status; confirm service state, DRAIN and paired output/high. Stop on any failed receipt/readback/service/preflight.
4. Review continuous-duty suitability, relay/supply ratings, independent enforcement and the fault evidence below before separately authorizing weather enablement. Successful simulation/build neither supplies this review nor permits 24 V connection. Any future disconnected timed test still needs its own explicit bounded approval; live valve tests require a separate approved water-isolated envelope.

## Rollback

With later operator authorization, disable weather, request DRAIN and verify logical receipt/output levels while keeping physical position unknown until observed. Stop the new stack before restoration. Restore the protected complete pre-migration database/config snapshot and exact v1.1.0 Pi/Dial artifacts. For any weather-enabled snapshot restore its matching weather-identity file together. No automated restore against a running database is provided. Recheck service/flow, manual_timed, zero remaining time and high/high output; never treat a failed readback as physical DRAIN.

## Surviving enforcement and unresolved physical gates

| Fault | Required outcome / mechanism | Remaining evidence |
| --- | --- | --- |
| Provider or Dial communication loss | Local policy/manual expiry; no replay; DRAIN on lost eligibility | Deployed timing and physical return unverified |
| Hub crash/hang | Daemon expires unrenewed lease within 60 seconds while daemon runs | Daemon crash/hang needs independent enforcement proof |
| Pi reboot | Startup DRAIN; durable interruption/revision recovery | Pre-application GPIO and valve timing unverified |
| Pi power loss/restoration | Required DRAIN in this separate domain | Passive hydraulic return/timing/restoration unverified |
| Relay supply loss/restoration | Required DRAIN in this separate domain | Relay contacts and surviving return mechanism unverified |
| Valve 24 V loss/restoration | Required DRAIN in this separate domain | Valve passive return/timing/restoration unverified |

No live fault, flash, deployment or energized valve test was performed for this candidate. GPIO memory tests establish software logic only. The historical physical gate remains open.

## Repaired source and remaining gates

The current candidate includes the four consolidated source repairs: final local START admission after durable writes, actual picker swipe access to shower STOP, read-only weather observations/rules and identity-bound target label. [Current exact evidence](../evidence/2026-10-03-weather-plan-validation.md) replaces the original W6/P5 candidate; scoped source repairs are verified; final documentation review remains pending. The mandatory 36-edge Dial inventory approval remains unresolved, so full acceptance stays NOT_READY. Bridge expanded strict lint remains a documented baseline limitation under approved P5 scope.

START nonce freshness is checked again immediately before local driver dispatch, after inhibition/active-marker persistence; automatic eligibility and manual deadline are also reevaluated there. Expired deliberate admission faults/inhibits without issuing BEGIN. No such check proves the eventual remote/physical dispatch time.

## Private phone observation contract

Existing authenticated Dial `GET /admin/api/weather` retains `revision`, `enabled`, `latitude`, `longitude`, `timezone` and adds `observation`. This optional object contains only `operation`, `enabled`, `available`, `eligible`, `reason`, `dates`, `minima_c`, `last_successful_check`; null means current observation is unknown. Exact PUT request/response and Pi settings schema are unchanged. Dial reads the already approved Pi display/status route with its display credential and filters out nonce/credentials. No new public route or privilege is introduced.

The browser displays saved preference separately from actual Pi operation. Minima/check metadata are labeled as the last successful forecast; latest failure or stale reason cannot imply AUTO eligibility. Visible rules remain today+four local days, inclusive 5 C, refresh every 15 minutes. Observation-only polling is every 15 seconds while the page is visible/authenticated; unknown/error/hide/logout stops polling until a deliberate refresh or visible-page resume. Polls send GET only and do not save settings or send control actions.

Both settings and optional status share the existing five-second admitted job. A confirmed settings GET is published to an immutable per-job snapshot before status I/O; generation/session validation fences both normal results and timeout fallback. An optional stalled read can return saved settings plus null observation within the original caller deadline. It retains the one worker slot until cleanup and never converts an uncertain PUT into Saved. Old clients that only consume the five original GET fields remain compatible.
