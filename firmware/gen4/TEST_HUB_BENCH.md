# Isolated 28CT test-Hub bench — 2026-10-19

The operator identified the USB-connected module as gen4-ESP32-28CT; PCB
revision is unverified. This is an isolated touch/network fixture test on the
workstation. The fixture has no Pi, GPIO, relay, valve or real Hub connection.
The existing Hub's deployed mode was observed separately as
`weather_assisted`; it was not changed for this test.

## Source and build gates

The dedicated `gen4_28ct_test_hub` target fixes the destination to the
verified workstation LAN address on port 18081 and replaces the real Hub token
with a test token after local Wi-Fi configuration is included. It accepts only
responses containing typed `simulated:true`. The screen carries a simulation
banner. An independent source review found no critical or important defect
after the endpoint was fixed; a response marker is not cryptographic identity.

The Node fixture tests passed: **2/2**. The C++ host suite passed:
**24 tests, zero failures**. The final provisioned read-only and CT test-target
PlatformIO builds passed. A local preflight scanner reported that the real Hub
URL and token were absent from the CT test app; the fixed test URL, response
marker and simulation banner were present. The new factory image's boot,
partition and OTA slices matched the accepted read-only image, and its
application region matched the generated app binary. The final CT test app
is 1,089,776 bytes, SHA-256
`61c4d23e02154e90fc4883ef4a0cf5a993b7fe1095ce9577e8bb14c0ff775fe4`.
The provisioned binaries and logs remain in ignored `.pio` only.

## Device gates and initial observation

COM7 was the same ESP32-S3 USB device (303A:1001). Before replacement, ROM
verification independently matched the accepted boot, partition, OTA and
read-only application slices. Only the app at `0x10000` was written; the
write digest passed, followed by four independent ROM digest matches and a
successful hard reset. Mutable NVS was preserved. Recovery copies and
write/verify receipts are in ignored `.pio/recovery`.

The fixture on workstation port 18081 returned authenticated HTTP 200,
`simulated:true`, `manual_timed` and logical `DRAIN`. The flashed display
reported Wi-Fi connected and fresh status on its own serial telemetry at
uptime 30357 ms, with zero generated START/DRAIN actions and zero invalid
touch samples. The fixture trace showed repeated GET polls and no POST at
this point. The cumulative touch-sample gap was 2109 ms; its timing within
startup is not isolated, so it cannot yet prove or disprove a continuous
two-second hold.

An injected 9-second 401 status-response window left Wi-Fi connected but
cleared freshness by uptime 411199 ms. The normal fixture mode was restored;
fresh status returned by uptime 419337 ms. During the capture there were
zero generated START or DRAIN actions and zero invalid samples. This is a
device-side stale/recovery observation, not a visible-screen confirmation.

The operator confirmed the visible simulation banner, logical DRAIN and
enabled start button. After one short tap and an approximately three-second
hold, the operator reported no change. During a 60-second whitelisted serial
capture, pressed samples rose from 5 to 772, invalid samples from 0 to 4,
fresh status remained true, and generated START/DRAIN counts stayed at zero.
The fixture trace contained no POST. This localizes the failure before the
request queue; the samples alone do not prove they were in the START zone or
uninterrupted. The cumulative maximum gap was 2128 ms, but the capture does
not identify when it occurred. A later diagnostic build added zone,
permission, gap and render timing counters.

## Diagnostic follow-up and restoration

The operator confirmed that tapping the lower IZPUST button produced a visible
response. The second fixture instance logged two DRAIN POSTs and no START
POST; these are simulated in-memory actions only. The operator again reported
that an approximately three-second START hold left the screen at logical
DRAIN. A no-touch diagnostic capture measured full-render latency up to
123 ms, including 22 renders over the gesture's 100 ms sample lease; USB
reporting also once took 4001 ms. These measurements motivated deferring the
full render during a valid START hold, bounding USB diagnostic writes, and
using a post-touch timestamp for the render decision. The 100 ms sample lease
was retained. A regression covers a stalled GT touch frame and verifies that
rendering resumes while START stays disarmed.

The final fixed test app above was flashed app-only at `0x10000`, independently
ROM-verified for boot, partitions, OTA and app (four digest matches), and hard
reset. The fresh fixture returned authenticated logical DRAIN throughout two
90/120-second serial captures. Both captures had zero pressed samples, zero
START/DRAIN actions and zero fixture POSTs; they therefore **do not confirm**
the hold fix on the device. The latest fixture trace ended at `starts=0`,
`drains=0`. The capture's maximum full-render duration was 122 ms; this was
seen without touch and does not exercise the deferral path. The operator's
later answer to the test-window prompt arrived after the test image had been
replaced; it cannot be attributed to the simulated hold test.

The fixture listener was stopped. The accepted provisioned read-only app,
SHA-256 `a1acb69ed589ee5b8406e16b3c44878da28ae3a9b90beea7610f50334b8bf797`,
was restored at `0x10000`; the write, four independent ROM digest matches and
hard reset succeeded. A later independent ROM verification again matched all
four slices and reset the board. The operator confirmed the restored screen
shows `UKAZ: DRAIN`, `Nacin samo za prikaz` and `SAMO PRIKAZ`. No simulated
SUPPLY was observed, and no real Hub action, GPIO or valve test occurred.
Neither fixture state nor a display message proves physical valve position.

## Repeat bounded test window — 2026-10-19

After the operator confirmed the restored `UKAZ: DRAIN` / `SAMO PRIKAZ`
screen, the same hash-checked test app was again uploaded app-only, verified
against all four immutable slices and reset. The fixture returned fresh
simulated DRAIN. The 120-second serial capture ended with zero pressed samples,
zero generated actions and no fixture POST (`starts=0`, `drains=0`). The test
window therefore supplied no additional evidence for the START hold fix.
The accepted read-only app was again restored app-only; write, four ROM digest
matches and reset passed. The exact test-Hub listener was stopped. A new
touch test should begin only when the operator is ready to interact during the
capture window.

## Operator-synchronized touch acceptance — 2026-10-19

With the operator present, the hash-checked test image was uploaded app-only,
independently ROM-verified across boot, partitions, OTA and app (four digest
matches), and reset. The fixture remained isolated on workstation port 18081.
The 120-second diagnostic capture recorded 839 pressed samples, 831 in the
START zone, eight in the DRAIN zone, six invalid samples, and exactly one
locally generated START followed by one DRAIN. The fixture trace recorded
exactly one accepted POST start (`SUPPLY`, 600 seconds) and one accepted POST
drain (`DRAIN`, zero remaining); the final fixture state was DRAIN. The
operator confirmed seeing SUPPLY followed by DRAIN on the screen. An earlier
answer of "different display or no button" was superseded by that explicit
SUPPLY/DRAIN observation; it is not used as evidence for the gesture result.
This accepts the isolated simulated hold-and-drain path on the connected 28CT,
not any live Hub, relay, GPIO or valve behavior.

After the capture, the accepted read-only app was restored app-only; write,
four independent ROM digest matches and hard reset passed. The exact test-Hub
listener was stopped. The operator subsequently confirmed the restored screen
shows both `SAMO PRIKAZ` and `UKAZ: DRAIN`.
