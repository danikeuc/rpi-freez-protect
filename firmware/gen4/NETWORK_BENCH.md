# Read-only Hub connection — 2026-10-19

## Scope and credential boundary

After accepting the offline application, the operator populated the ignored
local credential header and confirmed completion. Presence checks reported all
four fields populated; values were not printed. The Hub address matched the
previously selected existing Hub. No service changes, SSH access, POSTs,
GPIO requests or physical valve tests are part of this stage.

The initial network target is `gen4_28` (`GEN4_TOUCH=0`), using the same LCD
path already verified on this unit. This intentionally disables touch input
and shows `SAMO PRIKAZ`. The only action-queue producer in the shared application
is compiled out. The network worker can only poll status in this target.
Independent source review confirmed that boundary; it does not apply to CT builds.
Enabled touch controls still require isolated fake-Hub acceptance and the
separate commissioning approval/gates before any actual actuator request.

## API compatibility finding

Four bounded workstation GET requests to `/api/v1/display/status` used the
locally entered display token, with no redirects or raw-body logging.
The Hub accepted authentication (HTTP 200); Content-Length framing matched
the firmware's constraints. The first checks rejected the status because the
mode was `weather_assisted`, absent from this checkout's initial firmware parser.
Local historical commit `c13adea` defines that mode and the corresponding
payload. This is contract evidence, not proof of the deployed commit.

A regression was added first and failed as expected (19 tests, one failure).
The parser now explicitly accepts `weather_assisted` as non-manual and never
grants START for it. Unknown modes remain rejected. All 19 Unity host tests
then passed with zero failures/ignored tests using Zig and the actual sources.
Logs: `.pio/weather-mode-red.log`, `.pio/weather-mode-green.log`.

The final read-only preflight returned HTTP 200, compatible framing and a valid
schema: mode `weather_assisted`, logical command `DRAIN`, remaining seconds 0.
Log: `.pio/hub-readonly-preflight.log`, containing only sanitized status fields.
This current HTTP observation differs from the older manual_timed installation
snapshot. No Hub mode was changed, and no GPIO or valve position was inferred.

## Firmware evidence

Both updated builds passed: provisioned `gen4_28` (56.938 s) and
`gen4_28ct_offline` (52.512 s). Before replacement, the original full recovery
and accepted offline application hashes were rechecked; ROM verification of
the running offline image matched, on MAC `cc:8d:a2:0c:f0:b8` / COM7.

The provisioned factory image is preserved only in ignored
`.pio/recovery/application-readonly-v1.bin` (1133120 bytes), SHA-256
`bd0d03299b7daa52a840967e99b7e5c0ce9d16388c6d715516c8c1e55eb4799f`.
It was written using esptool 5.3.0 ROM mode (`--no-stub`, keep flash settings,
no compression) at offset 0 in 15.0 seconds. Write digest and a separate
`verify-flash` digest both matched. Logs in `.pio/recovery/`:
`application-readonly-write.log`, `application-readonly-verify.log`.

The ROM hard-reset command completed successfully. A subsequent bounded
15-second serial capture did not see the single startup banner
(`FIXED_STARTUP_BANNER_SEEN=False`); this does not confirm or disprove boot.
No arbitrary serial output was retained. The operator subsequently answered
"da" to the explicit check for `UKAZ: DRAIN`, `Preostalo 00:00` and
`SAMO PRIKAZ`. This confirms human-observed startup, Wi-Fi/Hub status reception
and the read-only layout on this device. It does not establish reconnect,
fault handling, touch controls, GPIO state or physical valve position.
The accepted offline application remains the recovery image recorded in
[APPLICATION_BENCH.md](APPLICATION_BENCH.md). All provisioned build outputs
must remain ignored and private because they contain embedded credentials.
