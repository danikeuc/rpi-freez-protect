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
by this Pi receipt. Companion Dial tag v1.3.0-shower.3 is pending installation and
operator acceptance. Existing release tags are preserved.

## Startup failure discovered before installation

Hub and Node-RED both entered active state at 14:00:40 UTC. The event database
recorded both DRAIN attempts refused at 14:00:45 UTC. Hub latched
startup_drain_failed and weather STOP returned controller not ready. A systemd
active process did not mean the Node-RED HTTP bridge was ready.

The restricted paired-GPIO diagnostic confirmed the expected P1 daemon hash and
active service. The operator issued authenticated CLEAR_FAULT through the local
API: DRAIN confirmation succeeded, USER_OFF was durably restored, then the
history installer completed. A permanent startup readiness repair remains open;
the history update must not be described as fixing this pre-existing boot race.
