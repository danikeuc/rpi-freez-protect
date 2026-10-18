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

## Trusted-console inventory and isolation confirmation

The user subsequently confirmed both valve 24 V supply and lamp load are
physically disconnected and supplied READ_ONLY_INVENTORY_COMPLETE. This is
operator evidence of isolation, not an observed relay/contact test.

- Model: Raspberry Pi 4 Model B Rev 1.1; compatible raspberrypi,4-model-b and
  brcm,bcm2711. Kernel as above; page size 4096.
- Canonical /dev/gpiochip0, owner 0:990, mode 0660, resolves to
  /sys/devices/platform/soc/fe200000.gpio/gpiochip0 on /sys/bus/gpio.
  Parent driver pinctrl-bcm2835; direct and parent firmware nodes agree at
  /sys/firmware/devicetree/base/soc/gpio@7e200000.
- GPIO node compatible brcm,bcm2711-gpio; reg 7e200000000000b4;
  parent address and size cells each 1. Lines20/21/26 are named GPIO20/21/26.
- /dev/gpiochip4 resolves to the same sysfs device and is an alias; use the
  canonical /dev/gpiochip0. The firmware expander gpiochip1 is not the target.
- /dev/gpiomem owner 0:990, mode 0660; legacy virtual gpiomem class device;
  platform firmware node soc/gpiomem, compatible brcm,bcm2835-gpiomem,
  reg 7e20000000001000, parent address and size cells each 1.
- System /usr/bin/python3 and Hub .venv/bin/python3 both report Python3.13.5;
  neither reports installed gpiod distribution metadata.

This resolves the model/mapping/dependency inventory unknowns. Fresh exact
chip API metadata, unused lines, service interpreter access and current
USER_OFF remain installer gates. No ownership request or MMIO write was part
of this inventory. The [console inventory block](../operations/paired-gpio-readonly-inventory.md)
returned the complete receipt despite garbled command echo in the pasted text.

## Dependency artifact verified on workstation

Choose an isolated paired-service environment, preserving the existing Hub
venv. The official PyPI2.3.0 artifact metadata provides a compatible prebuilt
wheel; no source build or system package upgrade is needed.

- gpiod-2.3.0-cp313-cp313-manylinux_2_17_aarch64.manylinux2014_aarch64.whl
- SHA256:7fdc3f63a277f8ae193f0c9b565bbd48e525e94c39cd463acd7b06250bf26507
- Size:103244 bytes; uploaded2025-02-19.
- Downloaded bytes matched SHA256; archive entries have no absolute/traversal
  paths; WHEEL tags match cp313/aarch64 and native extension ELF machine183
  is AArch64. No target wheel was installed or executed on the workstation.
- Source metadata: https://pypi.org/pypi/gpiod/2.3.0/json

## Next boundary

The two-stage migration package is under implementation and independent review.
The first stage prepares an isolated dependency environment and reads metadata;
the second stage requires the first receipt plus fresh baseline/state checks,
verified backup and DRAIN before service replacement. Neither stage enables
lighting. Retain all [runbook](../operations/paired-gpio-migration.md) gates.
No device installation, service change, firmware flash or physical acceptance
has occurred in this task.
