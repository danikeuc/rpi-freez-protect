# PT100 display commissioning — partial evidence, 2026-10-01

Status: Pi deployment and authenticated temperature response observed; reviewed dial candidate flashed and boot checked. The operator confirmed a live shower-page value and no temperature on the Roon page. One room-temperature reference comparison was reported; repeated/cold-point comparisons and sensor-fault tests remain pending. Both PRs remain draft.

## Observation sources and boundary

- Operator supplied the Pi console output and authenticated JSON in this conversation. Their exact measurement timestamps were not included.
- Operator explicitly confirmed that 24 V valve power is physically disconnected and that MAX31865 and PT100 are connected. This is an operator observation, not an electrical measurement.
- Workstation diagnostics used the existing restricted SSH identity with strict host-key checking. No access policy was expanded.
- Operator confirmed COM3 and requested using it without a new disconnect/reconnect cycle. Before writing, esptool identified ESP32-S3 revision v0.2, MAC `d0:cf:13:1e:15:44`, matching the previously recorded Waveshare.
- No SUPPLY or timed-shower command was issued in this session.

## Raspberry Pi

Operator preflight evidence:

- `/dev/spidev0.0`: character device, root:spi, mode 0660.
- systemd: `User=freezeprotect`, `Group=freezeprotect`, `SupplementaryGroups=spi`.
- `FREEZE_PROTECT_CONTROL_MODE=manual_timed`.
- Legacy GPIO/trigger preflight passed with one paired bridge route.
- Existing Python environment imported `spidev` successfully.

Operator deployment evidence:

- Previous checkout: `dab832f4dd98095db8e68d2189d7f159abc93183`.
- Installed checkout: `7a24387efbbe0772ae88646d1d98182feca43369`.
- Existing virtual environment reinstalled the project with `--no-deps --force-reinstall`; `pip check` reported no broken requirements.
- Two DRAIN helper calls returned `ok=true` and high/high readback before installation.
- Two initial connection attempts during startup failed; the bounded retry subsequently returned `{"service":"ok","state":"MANUAL_DRAIN"}`.
- Node-RED, paired GPIO daemon and Hub reported active; GPIO26 and GPIO20 remained output/high.
- The authenticated local display response contained `pipe_temperature_c=24.212243310943986` and `sensor_health=HEALTHY`, together with `manual_timed`, `MANUAL_DRAIN`, `DRAIN`, `remaining_seconds=0`, `timed_shower_deadline=null`, `reason=manual_idle` and `action_enabled=true`.
- Credentials were read locally into memory and were not printed or recorded.

This proves a reported live telemetry response after deployment, not calibrated temperature accuracy or sensor fault detection. The commissioning flag was not modified during this session; its persisted value was not independently read back.

## Waveshare flash and boot

- Reviewed source: `385979069a20c2a9f11ab7d02ef656563cd7855e`.
- Pre-flash documentation head: `a91cce1f7ca18a0e3410849378477d39a3d86502`; working tree clean.
- Application size: 2,102,064 bytes.
- Application SHA-256: `c2abd6d1168cac05d3eeb1581fd11d7c64c6e91a43644878584f148c8f4e4b00`.
- Windows esptool 4.12.0 wrote the build-defined bootloader at 0x0, partition table at 0x8000, initial OTA data at 0xd000 and application at 0x10000, with DIO / 80 MHz / 16 MB settings.
- A separate `verify_flash` operation reported `digest matched` for all four regions using the same flash settings.
- The NVS region 0x9000..0xcfff was outside the written/erased regions. No whole-chip erase was performed.

The bounded serial observation ran from `2026-10-01T01:30:05.738586+00:00` to `2026-10-01T01:30:55.974698+00:00` (50 seconds, 274 lines examined in memory). Only allowlisted metadata and fault-marker names were emitted; raw serial lines were not retained.

Observed metadata:

- One project startup marker: `hiphi_dial`.
- ESP-IDF `v5.5.5`.
- Application version string `2.5.3-valve.1` is inherited from the base; it does **not** identify this development binary as the immutable release.
- ELF hash prefix: `0ac107ac3`.
- Acquired IP: `192.168.114.173`.
- `valve_http` stack watermark: `5896/12288` bytes free.
- No matched panic, stack-overflow, assertion, brownout or task-watchdog fault markers.
- HTTP root subsequently returned 200.
- Post-flash restricted Pi status again reported all three services active and GPIO26/GPIO20 output/high.

This bounded observation is not a long-duration reliability test or proof of temperature visibility and Roon control.

## Operator visual acceptance

After the verified flash and boot, the operator reported: `24,3 zdaj, ni pri roon-u, zgleda kot da dela` (24.3 now, absent on Roon, appears to work). This is user-observed evidence of a one-decimal, decimal-comma temperature on the shower page and its absence on the Roon page. No screenshot or exact observation timestamp was supplied. The earlier API value and later display value were not simultaneous samples.

Signed/extreme values, the degree glyph in isolation, `---` during a real sensor fault, calibrated accuracy and Roon transport/volume interaction were not independently verified by this report.

## One-point reference comparison

Asked for the independent thermometer reading near PT100, the operator reported `24,4` degrees C, following the dial observation of `24,3`. The reported difference is approximately 0.1 degree C (dial lower). This is consistent with the room-temperature acceptance tolerance of 1.0 degree C for this pair, but the readings were reported sequentially. Reference instrument identity, uncertainty, stabilization duration and three settled pairs were not captured. This does not establish calibration, cold-point accuracy or sensor fault detection.

## Rollback readiness

Pi rollback source is the previous installed SHA above. Published `v2.5.3-valve.1` firmware files were present under `/tmp/v2.5.3-valve.1-published` and were preserved. Their hashes were read before completing this session:

- application: `5abc36f8be14e53eebe6bb0034940aa229b93bd536f8f79baeb6730ec3b109b9`;
- bootloader: `6b0b257ee71472fbc6bfa0e7513b317403ba1ccf4a69c75995de9728206e0c8a`;
- partition table: `a1ab6444806fcaf52c8b03b6a07404625644a15853bd8945622c102e46c95853`;
- initial OTA data: `7d2c7ac4888bfd75cd5f56e8d61f69595121183afc81556c876732fd3782c62f`;
- merged image: `8c014c72fd0288ae0f5a799fd321b6bc81bdaa74dda01136b142c28ec3bf70c6`.

Rollback was not performed.

## Remaining acceptance

- Visual fallback and signed/extreme-value legibility; operator confirmed the ordinary decimal-comma value and shower-only placement.
- Three settled reading pairs, reference instrument identity/uncertainty and cold-point comparisons; one room-temperature comparison is recorded above.
- Exact breakout/safeguard inspection and individual sensor-lead fault/recovery observations.
- Wi-Fi/Pi connection loss and recovery, stale fallback and non-actuating Roon regression on this exact candidate.
- No new energized valve test has been performed. Communication loss, process crash/hang, controller reboot and power loss/restoration remain unverified as physical fault outcomes for this candidate.
