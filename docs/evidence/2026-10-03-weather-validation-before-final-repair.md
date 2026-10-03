# Historical pre-repair validation

This retained 2026-10-03 W6/P5 record is superseded by [current repaired-candidate validation](2026-10-03-weather-plan-validation.md). Its earlier readiness judgments and reproduced defects describe that earlier source only.

# Weather / playlist repository validation — 2026-10-03

Observed workstation checks on 2026-10-03; no new device, provider, Core, Synology, GPIO or physical session. Frozen Pi source `9ea6fd26165650fdd3d08185962a62e39133d69d`, Dial source `bf45eb615030411e6a8b2b73cd5d032170f6074b`, bridge source `9490cef370a17e83480431d1791303fd663abce6`. Later documentation commits do not change these build-source identities. Full history/accepted task reviews remain in task reports; this record states current verification limits.

## Actual gates

| Scope / exact command | Actual result / evidence |
| --- | --- |
| Pi `.venv/bin/python -m pytest -q` | 570 passed, one existing Starlette/httpx warning, 13.26 s; `/tmp/w6-pi-pytest.log` |
| Pi `.venv/bin/python -m ruff check .` | PASS; Ruff 0.16.9; `/tmp/w6-pi-ruff.log` |
| Pi `.venv/bin/python -m mypy src` | PASS, 26 source files; mypy 1.20.2; `/tmp/w6-pi-mypy.log` |
| Pi `.venv/bin/python -m build` | PASS, sdist/wheel; build 1.6.1, CPython 3.12.3; `/tmp/w6-pi-build.log` |
| Pi commissioning assets pytest | 110 passed in 0.62 s; `/tmp/w6-pi-commissioning.log` |
| Dial `sh scripts/test_playlist_dial.sh` | PASS, including linked real playlist worker / valve fixture; `/tmp/w6-dial-playlist.log` |
| Dial `sh scripts/test_admin_dial.sh` | PASS, PIN/settings/weather/HTTP workers; `/tmp/w6-dial-admin.log` |
| Dial `sh scripts/test_valve_dial.sh` | PASS; `/tmp/w6-dial-valve.log` |
| Dial `sh /tmp/p4-ci-shared.sh` | PASS for all unaffected commands extracted from docker.yml test-shared, including ASan/UBSan and checker self-test; `/tmp/w6-dial-shared.log`; inventory command separately recorded below |
| Dial `python3 scripts/check_controller_dependencies.py` | FAIL exit 1, same exact 36 unlisted permitted edges; `/tmp/w6-dial-dependencies.log`; proposed policy expansion remains unapplied pending human approval after automatic review rejected it |
| Dial `idf.py -C idf_app -B /tmp/freeze-build-tools/dial-build build` | PASS, ESP-IDF v5.5.5 / ESP32-S3; app 2,182,528 bytes (0x214d80), 17% partition free; `/tmp/w6-dial-build.log` |
| Bridge `cargo fmt --all -- --check` and exact production `cargo clippy --offline --locked -- -D warnings` | PASS at frozen 9490cef; `/tmp/p5-followup-format.log`, `/tmp/p5-followup-ci-clippy.log` |
| Bridge canonical-source `cargo test --offline --locked --manifest-path /tmp/p5-bridge-9490cef.CJ3oe8/Cargo.toml --features server --no-fail-fast -- --test-threads=1` | PASS exit 0, 1921 passed / 0 failed / 18 ignored across 50 result blocks; `/tmp/p5-followup-archive-server-tests.log`; 14 ignored doctests + four integration skips |
| Bridge `cargo clippy --offline --locked --all-targets --features server -- -D warnings` | FAIL on documented preexisting legacy test diagnostics; required broad strict gate is not PASS or waived |
| Bridge `UHC_GIT_SHA=9490cef370a17e83480431d1791303fd663abce6 cargo build --offline --locked --release --features server` | PASS, Rust 1.98.1, 2m51s; `/tmp/p5-followup-release-build.log`; unchanged zone_match_key warning |

Shell syntax and diff checks passed for changed fixture scripts. The bridge suite uses a canonical LF Git archive: the original checkout has unchanged HQPlayer CRLF bytes that fail a literal-LF test assertion. No checker/source rewrite was used to bypass that condition. Sole ignored archive build prerequisite was existing public/tailwind.css SHA256 `839e97b8c2f90288a44af5f53bb2fda7b43a47c35826acdb4daccf694733c7d4`. Bridge results were reused from its author without duplicating unchanged suites. No container/WASM build or installed-image claim follows.

## What the fixtures prove

Five added Pi cases exercise real app/actions/service/SQLite/NodeRedActuatorDriver wire/receipt validation and daemon lease/paired writes. Provider scheduling, HTTP/Node-RED envelope and registers are fake. They cover AUTO loss, STOP/revision/replay, manual expiry and legacy compatibility, expired RENEW, lost receipt and action mismatch. Every register trace preserves the whole pair; it is memory simulation rather than physical readback.

The combined Dial fixture links actual valve parser/UI/client with the production playlist RTOS/HTTP worker. Simulated RTOS/HTTP/LVGL clocks let it latch media HTTP open while valve refresh and a separate deliberate STOP progress in AUTO/manual/USER_OFF. Roon errors do not change shower state. It directly calls playlist UI touch/rotate handlers and classifies a page gesture before calling the page toggle; it does not execute the hardware touch callback or encoder router during that stall. Separate `test_driver_playlist.py` extracts the actual touch/encoder callback bodies and checks all four rotations, wake/overlay isolation, consumed opening release and stale encoder epochs, with client/valve stubs. These complementary tests are not one continuous physical-input-to-server test.

## Artifact and readiness boundaries

[Redacted artifact manifest](2026-10-03-weather-playlist-artifacts.json) records build sources, sizes and SHA256. Preserved local copies: `/tmp/freeze-build-tools/w6-p5-20261003/`. Pi wheel SHA256 `6297ba9e39b5f4328922532d5967c8fc711691b6725a589f30d61b9566ae7bb7`; Dial app SHA256 `ad614db53794080eb1e44048d2a4a99d1a68e4befaf0a3671993adcba1941995`; bridge server SHA256 `ccd3bcff2dcfcc5d5c8b1ce8d20eda3cd611c22fa9e4e8ad142f94177a46934f`.

Dial build is incremental at its frozen fixture HEAD; production inputs match reviewed 890e1fdb. Its fixed version label is not a Git attestation. Later evidence/documentation revisions are separate from these artifacts. None was published, deployed or flashed; v1.0.0/v1.1.0 remain untouched. No tokens/private coordinates/catalog/account state appear in the manifest.

At the original preflight, Python guardrails classified Pi as READY_FOR_INDEPENDENT_REVIEW for its implemented software scope, using standard CPython 3.12.3, serialized service locks and SQLite CAS; network/register substitutes and hardware gaps are explicit. Combined W6/P5 is NOT_READY for full required-gate acceptance: Dial inventory approval and bridge expanded strict test lint remain unresolved. Independent review subsequently reproduced two pending source findings: an 11-second Pi CAS delay after the last nonce check can issue late SUPPLY before DRAIN/503, and a 140-pixel Dial swipe after fresh playlist confirmation is consumed by the picker without a page switch. The combined fixture does not exercise the actual platform input dispatch, as stated above. These findings await consolidated repair and affected evidence updates; the candidate remains NOT_READY. Later exact-artifact runtime acceptance remains a separate gate.

For later operator procedure and physical fault limits see [weather operations](../operations/weather-assisted-shower.md). No current source/build/test result proves installed firmware, actual first track/queue replacement/volume, relay contact, valve position, continuous-duty rating or power-loss hydraulic return.
