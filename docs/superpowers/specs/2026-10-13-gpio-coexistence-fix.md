# Kernel-owned GPIO configuration with atomic paired latch writes

User authorized resolving the GPIO_SHARED_FSEL2_COEXISTENCE blocker, 2026-10-13.
Scope: source repair, regression tests, deployment documentation; no live device
access, install, service restart, SUPPLY, flashing, push, merge or release.

## Root cause and chosen repair

Current paired configure_outputs directly reads/modifies/writes FSEL2 while new
GPIO21 uses gpiod/kernel configuration. Kernel FSEL locking cannot serialize an
uncoordinated raw-memory writer. Initial service ordering or a userspace lock
cannot cover kernel cleanup/restarts. Remove ALL userspace FSEL reads/writes from
the paired production path; do not merely add a lock.

Use libgpiod 2.x to exclusively request/hold GPIO26 and20 as outputs initially
physical HIGH (DRAIN), active_low=false, through the same kernel configuration
path as light21. Preserve the existing SINGLE GPSET0/GPCLR0 PAIR_MASK write and
GPLEV0 readback for normal paired DRAIN/SUPPLY; no sequential line writes or
fallback. Raw register access is a deliberately restricted latch/readback backend,
not configuration. The kernel request stays alive until all raw access is closed.
A single grouped gpiod set_values call is NOT a substitute for the known paired
latch behavior without driver evidence: reviewed Raspberry Pi rpi-6.12.y
pinctrl-bcm2835.c exposes per-line set and no set_multiple callback.

Require explicit verified chip/profile configuration and supported BCM283x/2711
platform/driver mapping before hardware access; reject Pi5/RP1/unknown chips,
wrong line identities, busy lines, missing gpiod/config and invalid profile. No
legacy fallback. Read metadata before request; acquire both lines before raw MMIO.
No ability to write other masks/registers or GPIO21 in the paired backend. Release
resources on partial failure. Preserve original exception and attempt DRAIN only
while ownership remains established; best-effort cleanup is not a crash guarantee.

Keep paired protocol2, socket, lease60s, readback semantics and controller/NodeRED
policy unchanged. Keep light policy/executor separate; no new shared process or
new light-to-shower command path. Unsupported activation remains blocked.

## Evidence limits

Kernel ownership resolves this source-level FSEL writer race only after migrating
and verifying the installed paired artifact. Old installed mmap backend still
blocks light activation. Grouped initial request/direction changes and release
can be sequential; boot/request/partial failure/crash electrical timing must be
measured with disconnected loads. No kernel GPIO request promises hardware
watchdog behavior. Required logical energized states remain (0,0,0),(0,0,1),
(1,1,0),(1,1,1); contact/valve simultaneity is unverified.

Primary references checked2026-10-13:
- https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.12.y/drivers/pinctrl/bcm/pinctrl-bcm2835.c
- https://docs.kernel.org/userspace-api/gpio/gpio-v2-line-set-values-ioctl.html
- https://libgpiod.readthedocs.io/en/v2.3/python_chip.html
- https://libgpiod.readthedocs.io/en/v2.3/python_line_request.html
These are source/API evidence, not installed kernel identification.
