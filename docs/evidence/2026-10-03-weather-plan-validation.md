# Weather / playlist repository validation — 2026-10-03

Current repaired local source/build: Pi `31245c1ad66491d13e36d3201bae946d1fcdefef`, Dial `5eb4c4506b031558bfaa3951d10a98dadc09105a`, unchanged bridge `9490cef370a17e83480431d1791303fd663abce6`. Later documentation commits are distinct. No new device, provider, Core, Synology, GPIO or physical session was performed. Overall **NOT_READY** while the mandatory Dial dependency inventory remains unapproved.

## Actual repaired-source gates

| Scope / exact command | Result / evidence |
| --- | --- |
| Pi `.venv/bin/python -m pytest -q` | PASS 576, one existing Starlette/httpx warning,13.05s; actual task exec output |
| Pi `.venv/bin/python -m ruff check .` | PASS after formatting changed files; actual task output |
| Pi `.venv/bin/python -m mypy src` | PASS 26 source files; `/tmp/final-fix-pi-mypy.log` |
| Pi `.venv/bin/python -m build` | PASS sdist/wheel from frozen source; CPython3.12.3/build1.6.1; `/tmp/final-fix-pi-build.log` |
| Pi commissioning assets pytest | PASS 110,0.62s; `/tmp/final-fix-pi-commissioning.log` |
| Dial `sh scripts/test_playlist_dial.sh` | PASS actual callback/worker/valve navigation and target rendering; `/tmp/final-fix-playlist-full.log` |
| Dial `sh scripts/test_admin_dial.sh` | PASS proxy, auth, settings and bounded actual worker; `/tmp/final-fix-admin-amend.log` |
| Dial `sh scripts/test_valve_dial.sh` | PASS; `/tmp/final-fix-valve-full.log` |
| Dial Windows Node/Chrome Playwright browser fixture | PASS shipped HTML/JS with intercepted transport; `/tmp/final-fix-browser.log` |
| Dial `sh /tmp/p4-ci-shared.sh` | PASS unaffected docker.yml shared commands including ASan/UBSan and checker self-test; `/tmp/final-fix-shared.log` |
| Dial `python3 scripts/check_controller_dependencies.py` | FAIL exit1: exactly36 original proposed include edges, set equality checked; `/tmp/final-fix-dependencies.log`. Policy unchanged; human approval still required after automatic-review rejection |
| Dial `idf.py -C idf_app -B /tmp/freeze-build-tools/dial-build build` | PASS ESP-IDF5.5.5/ESP32-S3, app 2,188,928 bytes,16% free; `/tmp/final-fix-dial-amend-build.log` |
| Changed shell `sh -n`; both source `git diff --check` | PASS |

Bridge checks are reused unchanged: full canonical-LF serial suite 1921 passed/0 failed/18 ignored, workspace fmt and exact production CI Clippy PASS, verified-SHA release build PASS. Expanded all-target strict Clippy remains FAIL on baseline legacy test diagnostics; direct strict policy-target checks retain two unchanged unnecessary_map_or diagnostics. The approved P5 plan permits recording baseline failures without unrelated repair. This limitation is not a PASS, separate approval blocker, or waiver invented by this repair. Original checkout CRLF literal-source limitation remains documented; canonical archive build prerequisite and logs are in the [historical validation](2026-10-03-weather-validation-before-final-repair.md).

## Four consolidated review repairs

1. **WR-01:** nonce freshness reaches local driver admission after all pre-BEGIN durable work. Six observed RED→GREEN cross-layer regressions delay clear-inhibition/marker CAS for manual/AUTO START and expire AUTO forecast/manual lifetime in the marker write. No new BEGIN reaches the real driver/daemon simulation after expiry. Replay, STOP, durable inhibition and conservative restart remain covered. The check does not guarantee remote hydraulic timing.
2. **WR-02:** horizontal navigation cancels/fences the picker and uses the real deferred page switch. The combined fixture extracts the production callback and deferred processor and links actual picker/worker/valve client/UI. Loading, selection, preparing, pending and error × AUTO/manual/USER_OFF × four rotations produce 60 traces. STOP remains reachable while actual media HTTP work stalls; consumed release, zero stray START/media writes and no late replay are asserted. Separate encoder/wake/rotation fixtures remain passing.
3. **WR-03:** private weather GET adds an allowlisted read-only observation while preserving existing root saved-setting fields and strict PUT. Current operation, five minima, last successful check, failure reason and fixed five-day/5 C/15-minute rules are visible. Existing worker, five-second deadline and scoped credentials remain. Optional stalled status returns immutable per-job confirmed GET settings plus unknown observation, never a global cache or uncertain PUT success. Generation/session changes invalidate both normal results and timeout fallback. Scoped review additionally found a malformed weather-array crash; the narrow 5eb4c45 amendment rejects non-object containers before traversal. Registered proxy and actual worker regressions now return confirmed settings plus null observation for malformed values; `/tmp/final-fix-malformed-observation-red.log` records the crash before repair and `/tmp/final-fix-admin-amend.log` the passing full admin suite. Registered proxy, browser and actual worker tests cover these paths.
4. **WR-04:** picker renders bounded UTF-8 target label from the validated favorites identity. Exact opaque zone/revision/epoch remain authoritative; display label never supplies a playback fallback. Actual renderer covers empty/pending/error views and wrong-zone rejection.

RED logs: `/tmp/final-fix-pi-red.log`, `/tmp/final-fix-dial-red.log`, `/tmp/final-fix-zone-red.log`, `/tmp/final-fix-admin-red.log`, `/tmp/final-fix-browser-red.log`. Green focused Pi79 tests: `/tmp/final-fix-pi-focused.log`. Test scaffolding compile/count corrections are not represented as behavior REDs. These are workstation simulations with fake network/provider/register/LVGL/RTOS boundaries, not physical input or actuator observations.

## Artifact and readiness boundaries

[Current nine-artifact manifest](2026-10-03-weather-playlist-artifacts.json) records exact source, sizes and SHA256. Verified local copies: `/tmp/freeze-build-tools/final-fix-amend-20261003/`. Pi wheel 52,774 bytes SHA256 `f4fd05f46ef1e860369691d57707e270e7af35569b5f97f77dcb1352d8270a3b`; Dial app 2,188,928 bytes SHA256 `acb88426f83e532db3570909e4750126e31dab92e0e525a79c1afed133ac4d34`; unchanged bridge server SHA256 `ccd3bcff2dcfcc5d5c8b1ce8d20eda3cd611c22fa9e4e8ad142f94177a46934f`. Every copied artifact was read back and checked against its build output. Fixed version labels do not attest source. No artifact was published, deployed or flashed.

The [original W6/P5 manifest](2026-10-03-weather-playlist-artifacts-before-final-repair.json), original `/tmp/freeze-build-tools/w6-p5-20261003/` copies and [historical validation](2026-10-03-weather-validation-before-final-repair.md) remain intact. Scoped source re-review found all four repairs and the malformed-observation amendment addressed. Final documentation review is pending; implementation checks do not grant deployment acceptance. Full CI is not PASS while the 36-edge inventory gate fails. Exact-artifact runtime/playback, physical fault outcomes and continuous-duty suitability remain unverified.

For later authorized procedure see [weather operations](../operations/weather-assisted-shower.md). Legal simulated pair levels remain high/high DRAIN and low/low SUPPLY. A running independent daemon retains its 60-second lease for communication/Hub failure; daemon crash/hang, pre-application reboot and separate Pi/relay/24V power-loss physical behavior remain unverified. No source/build result proves GPIO voltage, relay contact, valve position or hydraulic routing.
