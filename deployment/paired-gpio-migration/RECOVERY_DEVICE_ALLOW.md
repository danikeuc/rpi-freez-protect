# DeviceAllow ordering recovery, 2026-10-14

The operator supplied DevicePolicy=closed and precisely two DeviceAllow entries:
/dev/gpiochip0 rw and /dev/gpiomem rw. Systemd returned the entries in reverse
order from the original installer expectation. Exact ordered-list comparison
incorrectly rejected equivalent permissions. The revised verifier compares sorted
lines, retaining rejection of missing/extra/duplicate entries or altered rights.

This one-time trusted-root-console continuation is bound to
/root/paired-gpio-migration.xj0q8tgi and the pinned migration archive
f4c87e6439650f80c02b2d1b17c76661c5e3d74bbf7c672eab28edadc9883513.
Both valve24V and lamp mains must remain disconnected. No SUPPLY, light activation,
flow change, database restore or firmware action is performed. No SSH grants change.

Verify the supplied outer SHA256 and SHA256SUMS, then run:

```sh
/usr/bin/python3 -I -B recover_device_allow.py --loads-disconnected
```

The package imports verified operator checks and the revised migration module
explicitly under isolated Python. Original installed package bytes, preparation,
boot/venv identity, exact original failure, durable backups, stopped services,
installed candidate, systemd permissions, data/settings/history, line metadata,
flow and high/high readback must all pass before any service starts. The script
does not replace installed files or rerun the original install. It starts only the
paired service, verifies protocol2 DRAIN and kernel ownership, then starts Hub
through its existing readiness gate and revalidates USER_OFF, services, preserved
state and both GPIO levels. These remain software/electronic observations.

The new device-allow-recovery directory within original evidence is single-use.
A failure is retained privately, with Hub stopped after startup was armed and
best-effort DRAIN only when no receipt/readback already failed. There is no retry,
automatic rollback or independent physical cutoff. Keep the root session open.
Original FAILURE.json and maintenance failed-job receipt remain untouched; later
success is recorded separately as device-allow-recovery/SUCCESS.json and printed
as PAIRED_RECOVERY_VERIFIED. The old job status is historical, not the recovery
result. Do not interpret wrapper exit0 as migration acceptance.
