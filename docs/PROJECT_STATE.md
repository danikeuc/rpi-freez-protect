# Project state and evidence register

**Evidence snapshot:** 2026-09-30 (repository branch and read-only Pi check);
physical observations remain unverified unless stated otherwise.

This is the canonical index of what is implemented, what has actually been
observed, and what remains unknown. Repository content, deployed Raspberry Pi
state, workstation observations, and physical behavior are separate evidence
classes. Never promote one class into another without a new observation.

## Current system contract

- The Raspberry Pi is the only safety authority. The source branch's
  deployment example selects explicit `manual_timed` mode for the proposed
  Waveshare dial. In that mode, only a
  deliberate authenticated dial action may request one 600-second `SUPPLY`
  interval; absent or invalid mode holds `DRAIN`. The old CrowPanel is to be
  retired after display-token rotation. Its previously reported installation
  is historical, not evidence that retirement has occurred.
- The narrow display API remains on trusted-LAN Nginx port `8081` with only
  GET status and POST timed-shower/drain routes; the Hub remains loopback-only
  on `127.0.0.1:8000`. Installed gateway configuration is not yet verified.
- Production pipe temperature uses a three-wire PT100 through MAX31865 on SPI0
  CE0, source ID `MAX31865_PT100_SPI0_CE0`. DS18B20 is rollback code only.
- GPIO 26 and GPIO 20 are one paired actuator. The only legal requests are
  `DRAIN` = high/high and `SUPPLY` = low/low. Mixed states are illegal.
- Every accepted `SUPPLY` has a 60-second daemon lease. Missing renewal requests
  `DRAIN`; this software contract is not evidence of physical valve movement.
- Workstation commissioning uses the command-only
  `freezeprotect-commission` SSH account. Its allowlist is exactly
  `inventory`, `status`, `diagnose-pair-gpio`, and `drain`.
  `diagnose-pair-gpio` is a fixed read-only service diagnostic that omits
  journal messages; the account has no USB or firmware command.
- The CrowPanel cable is on the Windows workstation. The operator-confirmed
  port for this installation is `COM6`; both upload and monitor commands must
  name it explicitly. Reflashing is not a connectivity diagnostic.

## Evidence ledger

| Evidence class | Verified evidence | Limits / unresolved state |
| --- | --- | --- |
| Git repository | GitHub `main` and the Pi checkout were both observed at `432ff9e007bad2efc423a96862d0a5d230034c3b` on 2026-09-22 before this reconciliation. The reconciled checkout passed 178 Python tests, Ruff, shell syntax, Node-RED JSON/JavaScript syntax, relative-link validation and `git diff --check`. | A matching commit does not prove matching installed packages, unit files, secrets, processes, GPIO, or hardware. PlatformIO is unavailable in the reconciliation environment, so no current firmware build is claimed. This reconciliation is not deployed until separately installed and observed. |
| Manual timed Pi source branch (2026-09-29) | At source revision `5ae3c3ea53feae37147b72782308770605113fde`, simulated service and API tests cover mode selection, fixed 600-second timing, expiry, drain, failure handling, authorization, and paired daemon lease. The complete Python suite passed: 223 tests, 1 dependency deprecation warning. The focused Node-RED/Nginx/commissioning asset set previously passed: 118 tests. Ruff passed. The example selects `manual_timed` and names distinct admin, display, and Node-RED token placeholders; the source Nginx allowlist has exactly the three display routes. | These are repository checks with simulated adapters. This branch has not been shown deployed on the Pi. Installed mode, rotated token, retired CrowPanel copy, active Nginx/Node-RED configuration, relay state, 24 V status, and physical valve behavior remain **NOT_VERIFIED**. No Pi deployment or actuator command was performed for this source change. |
| Raspberry Pi inventory (2026-09-22) | Restricted `inventory` succeeded. A later restricted `status` returned `active` for `node-red.service`, then `activating` for `freeze-protect-pair-gpio.service` and exit code 3 before checking the Hub or GPIO. The Pi reported DietPi, kernel `6.18.39+rpt-rpi-v8`, `aarch64`, service account UID `999` and GID `984`, and commit `432ff9e007bad2efc423a96862d0a5d230034c3b`. | This is historical evidence; the later read-only check below supersedes its service and GPIO observations. Installed unit/helper contents, SPI transactions, Node-RED flow, and sensor state remain **UNKNOWN**. |
| Raspberry Pi read-only check (2026-09-30) | With the dedicated `freezeprotect-commission` key and strict host-key checking, `inventory` again reported installed commit `432ff9e007bad2efc423a96862d0a5d230034c3b`. Restricted `status` exited zero: `node-red.service`, `freeze-protect-pair-gpio.service`, and `freeze-protect.service` all reported `active`; `pinctrl get` reported GPIO 26 and 20 both output/low. | Low/low is the software `SUPPLY` signal, not the required high/high `DRAIN` readback for commissioning. The installed commit predates this source branch. The cause, effective mode, 24 V supply state, relay contacts, and valve positions are **UNKNOWN**. The check stopped at this readback; no actuator command, service change, deployment, or further Pi command was issued. A trusted-console operator must establish the physical/electrical state before commissioning continues. |
| SSH boundary | A restricted `freezeprotect-commission` inventory call succeeded with the dedicated key. | This proves that one allowed command worked at that time, not that every installed commissioning asset matches this source tree. |
| Windows / CrowPanel | On 2026-09-22 the operator stated the CrowPanel was attached to the PC as `COM6` and firmware had previously been uploaded many times. | This is historical context. Current connection, installed revision, token removal, and retirement are **NOT_VERIFIED**. The boot message contains no commit/version identifier. Do not infer revision from prior upload count. |
| Physical installation | No actuator command or 24 V operation was performed during this reconciliation or the 2026-09-30 read-only check. | Current 24 V connection, water isolation, valve position, paired physical movement, return-capacitor behavior and PT100 terminal mapping are **UNKNOWN / NOT_VERIFIED**. GPIO readback does not prove valve position. |

The failed remote `usb` call on 2026-09-22 returned
`find: '/dev/serial/by-id': No such file or directory`. That result is explained
by the cable being on the Windows workstation; it was not evidence that the
CrowPanel was absent. The Pi helper no longer exposes this misleading command.

## Failure claims and proof level

| Failure | Implemented response | Proof currently available | Remaining proof |
| --- | --- | --- | --- |
| Hub-to-daemon communication loss | The daemon expires `SUPPLY` after at most 60 seconds and requests paired `DRAIN`. | Repository unit/integration tests of lease behavior. | Timed deployed observation and physical valve confirmation. |
| Hub crash or hang | Renewal stops; the same daemon lease requests paired `DRAIN`. | Repository logic and tests. | Deployed process-failure test with timestamps and physical observation. |
| Controller/service restart | Paired-GPIO daemon startup requests high/high `DRAIN`; Hub starts conservatively. | Repository code, unit definitions and tests. | Current deployed unit/readback capture and physical observation. |
| Power loss and restoration | Software is designed to start conservatively and request `DRAIN`. | Repository design/code only. | Electrical output behavior through loss/restore, valve behavior, supply/capacitor timing and safe plumbing outcome are **NOT_VERIFIED**. |

## Authoritative documents

Use these for current work:

1. [`../AGENTS.md`](../AGENTS.md) — mandatory safety and access boundaries.
2. [`../deployment/WORKSTATION_CODEX_COMMISSIONING.md`](../deployment/WORKSTATION_CODEX_COMMISSIONING.md) — workstation/SSH handoff.
3. [`../deployment/COMMISSIONING.md`](../deployment/COMMISSIONING.md) — Pi, PT100/MAX31865 and valve commissioning.
4. [`../deployment/CROWPANEL_COMMISSIONING.md`](../deployment/CROWPANEL_COMMISSIONING.md) — current Waveshare cutover gate and superseded Windows `COM6` CrowPanel procedure.
5. [`superpowers/specs/2026-09-21-pt100-max31865-design.md`](superpowers/specs/2026-09-21-pt100-max31865-design.md) — current sensor design.
6. [`superpowers/specs/2026-09-29-waveshare-roon-valve-control-design.md`](superpowers/specs/2026-09-29-waveshare-roon-valve-control-design.md) — manual timed dial design and evidence boundaries.

Files under `docs/superpowers/plans/` are historical implementation records,
not runbooks. Earlier design specifications remain decision history where
marked and may describe superseded hardware or access arrangements.

## Next safe observation

The 2026-09-30 read-only check found GPIO 26/20 output/low. Stop commissioning
and have the trusted-console operator establish the present 24 V, relay, and
valve state and the reason for the low/low command. Do not infer physical
position from GPIO readback. Do not issue another Pi command, deploy the new
mode, restart services, or flash firmware to resolve this observation. Once the
cause and safe state are established, plan a bounded 24 V disconnected
software/GPIO validation with explicit same-conversation approval under
`AGENTS.md`; a live valve test requires separate approval.
