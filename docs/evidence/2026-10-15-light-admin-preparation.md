# Light admin deployment preparation — 2026-10-15

Owner requested installation of the existing approved Luč tab.
Existing Pi runtime/camera activation is recorded separately. Fresh restricted
SSH status returned allthree services active and GPIO20/26 outputHIGH. No GPIO
command was sent. Dial HTTP173 is reachable but installed admin lacks panel-light.
USB enumeration returned no serial ports; no flash has been attempted.

## Candidate

Dial source70bc5b5bebafd69ab2222178d269ba17dd991c9d, ESP-IDF5.5.5
b774170ff46c393eeb5e495ea37936038d3f4f4f. Existing build had a different hash,
so build-light-admin was generated fresh, preserving16MB flash, octal80MHzPSRAM,
PERFoptimization and NimBLE. BuildPASS, size0x22c400,13%appspacefree.
AppSHA256:72f78a6f3a2507647e7af71893314bb2903b791cc2870bc2231a5a2a9ce74ca9.
Native light tests and generated-admin equalityPASS. No installed firmware claim.

## Additive Pi step

See deployment/lighting/admin/README.md. Separateprivate8082 routes are limited
to exact Dial/Pi IPs; existing light credentials are provisioned once via hidden
PIN login. Camera8443, shower8081, services and existing tokens are preserved.
No settings or actuator request is sent. Uses the existing HTTP-only Dial client
and privateLAN trust model; does not claim TLS for this path.

Fresh independent review found getpass could fall back to echo despiteisatty.
Regression reproduced that failure, thenPASS after GetPassWarning became fatal
before any fallback read. Existing configured connections, odd/bool generations,
redirects and automatic repeated writes are rejected. Seven focused testsPASS;
RuffPASS. Final fullsuite1033PASS including the added fallback regression.

Prepared files are in the workstation delivery directory light-admin-20261015.
Installation pending physicalUSB and trusted Pi root-console execution because
the active restricted SSH allowlist does not permit this new package. Do not run
the Pi provisioning step until the reviewed firmware exposes light/config.
No release, merge or remote publication occurred.

## USB follow-up

Owner reported attachment. Serial inventory exposed onlyCOM4, VID1a86/PID7523.
Esptool4.12.0 chip-gated flash_id identified ESP32 rather than requiredESP32-S3
and exited1 before any flash write. No backup or firmware upload occurred.
Requested the exact Waveshare1.8-inch Dial connection; never bypass chip check.

## Hardware follow-up — 2026-10-16

Correct Dial attached onCOM3, USB303a:1001, MACd0:cf:13:1e:15:44, ESP32S3rev0.2,
16MBflash/8MBPSRAM. Initial full16MB read failed at6.66MB with corruptUSBpayload;
no write had occurred. Smaller115200baud chunks were read twice independently.
All11chunks matched. Verified backup covers0x0..0x290000 (all altered regions
and NVS); partition table matches candidate. Private backup:
C:/Users/danik/.codex/private/light-admin-20261015-f8391fb2.

Candidate72f78a6f was written and all4segmentdigests verified. NVS readback
matched before firstboot. Hardware acceptance FAILED: 8interrupt-watchdogpanics
in60seconds, backtrace in r_lld_core_init/r_lld_init/r_rwble_init/r_rwip_reset,
btdm_controller_on_reset/task. No Pi actuation was requested.

Immediately restored verified backup prefix with keepflashsettings and verified
its digest. Baselinev1.3.0-shower.3 (ELF e9a435f81f39c6be48e47c46049e7b5bb0f26dc1a3cdf49d77fcefdf88f03abb)
returned adminHTTP200. Further60secondcapture: zero panic/overflow/brownout/reset
markers. Fresh Pi status all3servicesactive, GPIO20/26HIGH.

Clean CI-default generation identifies two actual config differences:
LV_MEM_SIZE_KILOBYTES local24 vs accepted8;
LV_MEM_POOL_EXPAND_SIZE_KILOBYTES local72 vs accepted88.
Current rejected candidate was built using retained ignoredsdkconfig. New build
uses explicit isolatedSDKCONFIG from defaults and must pass the full release
profile before another flash. Rebuild and hardware acceptance remain pending.

## Clean-profile installation verified — 2026-10-16

A fresh isolated SDKCONFIG passed all 15 ESP32-S3 release configuration checks,
the real NimBLE source/link checks, and a complete ESP-IDF v5.5.5 build.
App SHA256: `2f547d5cd9f6b39aa296c2f113c4ffc7d31efb59f32b8c3c3841988f7375f0e9`.
Source remains `70bc5b5bebafd69ab2222178d269ba17dd991c9d`.

Flashed the correct COM3 ESP32-S3; all four segment digests matched and NVS
matched the original backup byte for byte before boot. A 60-second observation
reported zero panics, stack overflows, brownouts or new boot markers. Admin HTTP
200 contains the light panel; session is configured and unauthenticated; light
configuration correctly rejects unauthenticated access with 401. This resolves
the reproduced watchdog loop in this observation window, not a long-term BLE
acceptance claim. No actuator command was issued.

Fresh Pi status: all three existing services active, GPIO20/26 high.
Package b3031dd445952547c09aef696a20d37316174a21867dcfadbc377ffc5c5210ee
remains reachable on workstation port8782 with no timed expiry.
The DietPi gateway and private Dial credential provisioning are still pending
the authorized trusted-console installer. End-to-end light admin installation
and functional acceptance must not yet be claimed.

## Admin request memory failure — 2026-10-16

The owner's trusted-console diagnostic verified controller loopback and private
LAN gateway status/settings/history: all six requests HTTP 200. Dial login,
session and saved configuration also passed, but the three Dial proxy reads
returned HTTP 503 within 32–44 ms. The provisioning marker and save-started
receipt exist; success.json does not. Do not rerun provisioning or erase the
marker. This establishes partial installation, not end-to-end acceptance.

A bounded device diagnostic subsequently observed `admin_task_failed`: allocation
of the 4096-byte light_admin task stack failed after allocating admin_job_t with
its response buffer larger than 8 KB. The release configuration preferentially
allocates blocks below 16384 bytes from internal RAM. The patch moves this job
to explicit PSRAM, preserving cleanup and request/reference ownership.

The regression reproduces HTTP 503 on the original allocator under internal
memory pressure and passes with explicit PSRAM. It also verifies PSRAM allocation
failure sends no upstream request and releases admission for the next request.
All four native light test executables pass; git diff --check passes. Independent
review found no actionable issues, including exact-build PSRAM atomic support:
CONFIG_STDATOMIC_S32C1I_SPIRAM_WORKAROUND=1 and -mdisable-hardware-atomics.
ESP-IDF v5.5.5 build completed successfully.

Candidate app SHA256:
`9ccc7f84e1a9d6737e2b05fa453cf0d92da08f16c8b4bcc5ff06253b0b1d3aae`.
Source is 70bc5b5bebafd69ab2222178d269ba17dd991c9d plus the reviewed allocator
and regression changes. COM3 chip and MAC identity were checked. Current NVS
was read twice and compared before application-only flashing; flash verification
passed and NVS remained byte-identical after flashing. No actuator request,
Pi service change, credential write, release or remote publication occurred.
Device boot observation and authenticated end-to-end reads are recorded below
when available; they must not be inferred from build/flash success.

Post-flash 40-second serial observation: zero Guru Meditation panics.
Admin HTTP 200 contains panel-light; public session reports setup_required=false
and authenticated=false. Protected light/config correctly returns HTTP 401
without a session. Authenticated status/settings/history acceptance is pending
the owner refreshing the page; no claim that the displayed state is fixed yet.

## Remaining failure and bounded phase diagnostic

Owner supplied another screenshot showing unknown state after the memory fix;
end-to-end acceptance FAILED. No further functional fix was guessed.
A temporary phase-logging build includes the reviewed allocator fix and logs
only kind/stage/numeric HTTP status/length/currentness, never credentials or
response bodies. Native tests and build pass. App SHA256:
`9e8c2966ddc5d4cf0798e2a58db0e7a66f102ca5c7c6d6b5aaec3de2e9e62fac`.
Application-only write verified and current NVS matched byte-for-byte.

Automatic device polls on this build repeatedly receive HTTP 200 and pass DTO
validation for status (238 bytes) and settings (55 bytes). Thus the live Dial to
Pi connection works during this capture. The first 40-second capture counted one
Guru Meditation marker without retaining its backtrace; its cause is unknown
and stability acceptance is NOT claimed. A follow-up capture retains bounded
panic/backtrace lines for diagnosis. Authenticated admin requests have not yet
been observed in that capture. Browser automation failed at sandbox helper
initialization; owner was asked to reload/login and click Refresh once.
Temporary diagnostic source is retained pending that observation; clean fixed
source is backed up in delivery/memory-fixed-source. No relay command issued.

## Confirmed remaining admin failure and static worker correction

The owner refreshed the authenticated admin. The bounded serial capture recorded
12 further `admin_task_failed` events while automatic status/settings polls
continued returning validated HTTP 200. Moving admin_job_t into PSRAM did not
eliminate the runtime stack-allocation failure. The remaining root cause is the
per-request internal stack allocation; authentication and the Pi link are not
shown to be failing in this observation.

A stronger regression makes dynamic task creation fail under memory pressure
regardless of response-buffer allocation; the previous fix fails with exit134.
The corrected implementation reserves one 4096-byte, 16-byte-aligned internal
stack plus static task and queue metadata at link time. Lazy initialization is
serialized by admission; a persistent worker handles async requests through a
single-pointer queue. Existing six-second waits, per-job semaphores/refcounts,
configuration/session guards and late-callback cancellation are preserved.
No dynamic task is created or deleted per request. Queue failure closes the
async request and releases ownership. A test exercises busy admission, repeated
requests using one static task, and static-init/PSRAM/queue failure recovery.
All four native test executables and git diff --check pass. Independent code
review found no actionable correctness findings. Build completed successfully.

Candidate app SHA256:
`e0876060e4fe55d38819d547e49a0d9e8b2f38758c2456d1bea7f8560e7b68a5`.
This candidate removes temporary phase logging. Device acceptance is pending;
the static reservation reduces available boot heap and requires actual boot and
admin confirmation, not merely a build result.

Static-worker application flash and NVS preservation verified. The 60-second
boot capture counted one interrupt-watchdog panic on CPU0; decoded exact ELF
frames include r_lld_core_init, r_lld_init, r_rwble_init, r_rwip_reset,
btdm_controller_on_reset and btdm_controller_task. This is Bluetooth controller
startup, not evidence of admin response completion. Additional captured frames
include the light HTTP client's initialization on another stack; no causal
conclusion is drawn. A following serial capture and owner admin readback are
pending. Stability and complete installation remain unaccepted.

Owner follow-up after static worker installation: "deluje sedaj" (works now).
The supplied screenshot contains configured light durations and history of
manual commands and camera events. This is owner-reported functional acceptance
of admin operation; its status card also shows stale/unknown data at capture
time. It does not establish continuous fresh status or resolve the separate
Bluetooth startup watchdog observation. No physical lamp/contact test by the
agent is claimed. Owner requested a modern Dial icon, explicit AUTO/duration
and confirmed ON/OFF plus a changed manual-to-AUTO grace interval; that behavior
change is tracked separately from this memory/worker correction.
