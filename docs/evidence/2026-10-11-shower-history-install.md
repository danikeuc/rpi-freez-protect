# Pi shower history installation - 2026-10-11

Operator reported successful trusted-console installation with 24 V disconnected.

- Package: 1.3.0
- Source: b1e244758553b10052909804d7ddca4610b3a207
- Wheel SHA256: 96b91ce525394d25183473ee6116474c64e411138a1236b06396f1135a99f982
- History rows returned on ports 8000 and 8081: 2 and 2
- Operation/command: USER_OFF / DRAIN
- GPIO26 / GPIO20: high / high (electrical readback, not valve position)
- Backup: /root/freeze-before-history-a258zuv0
- Deployed checkout preserved: d0dfeac61856e0ff716e700348be61709dc68505

Installed wheel identity and deployed checkout identity are intentionally distinct.
No flash, live AUTO transition, energized valve or power-loss test is established
by this Pi receipt. Companion Dial tag v1.3.0-shower.3 was subsequently installed as recorded below;
authenticated UI acceptance remains pending. Existing release tags are preserved.

## Startup failure discovered before installation

Hub and Node-RED both entered active state at 14:00:40 UTC. The event database
recorded both DRAIN attempts refused at 14:00:45 UTC. Hub latched
startup_drain_failed and weather STOP returned controller not ready. A systemd
active process did not mean the Node-RED HTTP bridge was ready.

The restricted paired-GPIO diagnostic confirmed the expected P1 daemon hash and
active service. The operator issued authenticated CLEAR_FAULT through the local
API: DRAIN confirmation succeeded, USER_OFF was durably restored, then the
history installer completed. The permanent startup readiness repair is prepared in package 1.3.1; its Pi
installation is pending.
the history update must not be described as fixing this pre-existing boot race.

## Companion Dial installation

At 15:40 UTC, the exact CI application from run 38151787261 was installed on the
Waveshare ESP32-S3 connected at COM3. Tag v1.3.0-shower.3 resolves to
69cab63b252fca2a1dc25e2c3aaf9153badceb37. Application SHA256:
50ce9f7518f8227ef576e3807e647cb64c53ecc7488ab2e868c4c2a0caf6163b.

The full private 16 MiB backup was verified, application readback matched, and
NVS/bootloader/partition/OTA metadata remained unchanged before first boot.
A 60-second boot observation recorded one app boot and no panic/BLE init failure
markers. A subsequent GET /admin returned HTTP200 with history markup. This
establishes network/admin availability; authenticated user-visible history and
new AUTO/manual transitions have not yet been directly accepted by the operator.

## Publication checkpoint

Pi [v1.3.0](https://github.com/danikeuc/rpi-freez-protect/releases/tag/v1.3.0)
was published on 2026-10-11 at 16:50:56 UTC with the installed wheel and verified
trusted-console archive. Its tag still resolves to b1e244758553b10052909804d7ddca4610b3a207.

Pi v1.3.1 remains a draft, source d89827d7e0ea8963f5ed00984c3c0070286e2831.
Archive SHA256: a45de392ad6ec0548c72b22c44d271e96dec7702793b430c53270c7925ffde9f.
Wheel SHA256: 90b0faa89b9afcc6304d3f8b978428da0056533c34d813e40ac7e22d4279a812.
Trusted-console installation output has been requested; no success is assumed.
The live restricted status check before publication showed all three services
active and GPIO26/20 output/high. This does not establish the installed patch.

Dial v1.3.0-shower.3 remains a draft pending authenticated history UI acceptance.
The PR's optional preview hosting failed with Pages HTTP404 in run 38152469624;
all six build/test jobs passed, as did the exact tagged firmware CI run. No
preview deployment success is claimed. The PRs remain unmerged.

## Operator history acceptance and Dial publication

On 2026-10-11 the operator repeated the existing HISTORY_INSTALLED receipt for
Pi 1.3.0 and reported "zgodovina je" (history is visible). This confirms the
admin history rendering check for the installed Dial artifact. It is not a new
Pi installation receipt, a 1.3.1 receipt, or an AUTO/manual actuation test.

[Dial v1.3.0-shower.3](https://github.com/danikeuc/roon-knob/releases/tag/v1.3.0-shower.3)
was published at 17:05:18 UTC with the same verified application SHA256. This
supersedes the earlier pending UI/draft statements in this dated record.
Pi 1.3.1 is still pending installation; no current software state is inferred
from repeating the 1.3.0 receipt. Existing tags and installed settings remain unchanged.

## Pi 1.3.1 publication

The operator explicitly requested publication after the distinction between
installed 1.3.0 and prepared 1.3.1 was explained.
[Pi v1.3.1](https://github.com/danikeuc/rpi-freez-protect/releases/tag/v1.3.1)
was published at 2026-10-11T17:09:14Z, with the unchanged tag/source and artifact
hashes recorded above. This supersedes earlier draft status only. Installation
and delayed-Node-RED cold-boot acceptance remain unconfirmed, explicitly stated
in release notes. No device mutation was performed during publication.

## Pi 1.3.1 installed

The operator supplied STARTUP_READINESS_INSTALLED with version 1.3.1, source
`d89827d7e0ea8963f5ed00984c3c0070286e2831`, wheel SHA256
`90b0faa89b9afcc6304d3f8b978428da0056533c34d813e40ac7e22d4279a812`,
and seven history rows through each of ports 8000 and 8081. USER_OFF/DRAIN and
GPIO26/20 high were verified. Backup: `/root/freeze-before-startup-psoa_xgm`.
The deployed checkout remains `d0dfeac61856e0ff716e700348be61709dc68505`.

The subsequent restricted remote status check confirmed all three services
active and both GPIO outputs high. This closes the pending package installation
gate, superseding earlier pending-installation entries. It establishes the
ordinary service start with the readiness drop-in; it does not establish a
cold boot with deliberately delayed Node-RED or physical valve positions.
