# Paired GPIO migration preflight — 2026-10-13

Read-only workstation checks used the dedicated freezeprotect-commission SSH
key and exact inventory, status, diagnose-pair-gpio allowlist commands, in order.
StrictHostKeyChecking=yes and BatchMode=yes; existing host trust succeeded.
No drain command, raw GPIO operation, service mutation or installation occurred.

## Current device evidence

- Target: DietPi at192.168.114.192.
- Kernel:6.18.39+rpt-rpi-v8, aarch64; Debian build1:6.18.39-1+rpt1 (2026-07-29).
- Reported source checkout:d0dfeac61856e0ff716e700348be61709dc68505.
- All three helper-reported services active; paired MainPID389, Resultsuccess,
  NRestarts0, active since2026-10-11T14:00:39UTC.
- GPIO26 andGPIO20 report output/high. This is not valve-position evidence.
- Installed paired daemon SHA256:
  33088ea9e6ccf8d327e226bab1602c6a2b3ba2423de7dcab408b1d06f2233d2f.
- Installed base unit SHA256:
  0ce0b112ae54783846784ccb1fb77f17748c830392deb612391047d22da840ff.
- Installed restricted helper SHA256:
  555ea7cdbbf3fc3d7369a894708452c4752f0b8b62f012e87eb0a21d937c2ac1.

The old paired source remains installed. Hub package version/control state and
live model/revision/DT/chip/dependencies were not returned by these helper calls.
No package version or USER_OFF state is inferred from the checkout or GPIO.

## Kernel-family reference check

Public Raspberry Pi rpi-6.18.y source still serializes FSEL writes under fsel_lock,
exposes per-line set with no set_multiple or gpio_request_enable callback,
creates legacy gpiomem class device with NULL parent, and attaches the GPIO bus
device to its platform parent with a direct firmware node. These observations
support the reviewed mapping design; moving branch source is not proof of the
exact installed kernel build or actual DT/sysfs layout.

References checked in this turn:
- https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.18.y/drivers/pinctrl/bcm/pinctrl-bcm2835.c
- https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.18.y/drivers/char/raspberrypi-gpiomem.c
- https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.18.y/drivers/gpio/gpiolib.c

## Next boundary

Physical disconnection confirmation requested: valve24V supply and lamp mains
load. No new physical acceptance is recorded. Detailed model/DT/sysfs and exact
interpreter/libgpiod metadata require a trusted-console read-only inventory;
the remote allowlist is not widened. Prepare exact installer only after that
inventory has resolved the supported mapping and dependency plan. Retain all
[runbook](../operations/paired-gpio-migration.md) gates, including USER_OFF/DRAIN,
backup, migration and disconnected-load acceptance. Nothing has been activated.

Prepared [trusted-console inventory block](../operations/paired-gpio-readonly-inventory.md).
Workstation syntax/non-Pi guard passed; remote execution/output remains pending.
