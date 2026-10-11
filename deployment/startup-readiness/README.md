# Pi startup readiness update

Trusted root console on DietPi only; 24 V disconnected; USER_OFF/DRAIN required.
Installs package 1.3.1 and an additive systemd drop-in without replacing the
existing service unit, settings, daemon, Node-RED flow or source checkout.
The readiness gate uses the normal paired-v2 DRAIN driver. Only connection
refusal is retried in a 60-second retry/acceptance window. A synchronous request
can outlast that window: the driver uses a 3-second socket inactivity timeout,
and systemd enforces the outer 75-second startup limit. A receipt arriving after
the acceptance window is rejected. Malformed/failed receipts fail the invocation. Existing systemd restart policy can retry the service. The Hub still
performs its own startup DRAIN and keeps its fault latch. No fault is cleared.

Before modification, software and SQLite/sentinel backups are verified. Existing
ExecStartPre or readiness drop-in stops installation for review. Failure after
service stop keeps Hub stopped/DRAIN; no automatic rollback. A new drop-in is
explicitly recorded as absent in the backup. Rollback requires removal of that
exact newly installed drop-in in addition to restoring the verified package,
unit/config and matching DB/sentinel, then daemon-reload.

Success verifies service startup (including ExecStartPre), history routes,
USER_OFF/DRAIN and GPIO26/20 high. A reboot with delayed Node-RED remains a
separate acceptance test; no physical valve position or energized test is claimed.
