# Paired GPIO ownership migration candidate

2026-10-13. Source repair only; no installation, service action or hardware test
has been performed. The installed Pi 1.3.1 record is unchanged. Its old paired
mmap configure path remains incompatible with lighting GPIO21. Keep lighting
units, marker, hardware opt-in, flow and gateway disabled until exact installed
migration and the acceptance below are separately approved and recorded.

## Source behavior

The paired daemon now reserves BCM26 and BCM20 exclusively through libgpiod
with Direction.AS_IS and no edges or bias changes. Only after reservation does
it map the verified BCM register bank and preload HIGH using one GPSET0 write
with mask 68157440. Kernel reconfiguration sets both lines OUTPUT,
active_low=false, output_value=ACTIVE (physical HIGH); paired DRAIN readback
must pass before serving. Kernel-only FSEL configuration shares driver locking
with GPIO21. Every normal DRAIN/SUPPLY retains one GPSET0/GPCLR0 mask store and
one GPLEV0 readback. No userspace FSEL access or sequential fallback remains.

Reservation requests no direction change; this is not a promise about physical
request timing or every installed driver. The reviewed rpi-6.12.y BCM driver
has no gpio_request_enable callback and no set_multiple callback. Therefore a
grouped gpiod set_values call alone would not establish the paired latch write.
The chosen hybrid keeps the existing paired store. Initial direction changes,
release and partial failures can still affect lines sequentially. Preloading
does not prove simultaneous electrical initialization or valve movement.

Ownership remains held through DRAIN cleanup and unmapping, then releases.
Map failures close the descriptor and release the request; startup/service
errors retain their original exception even if cleanup also fails. An
unexpected unmap failure retains the request until process exit rather than
explicitly releasing it while raw access exists. Process teardown, SIGKILL,
hang, boot and power failure remain unverified electrical behavior.

Protocol2, 60-second SUPPLY lease, socket, receipts and controller/Node-RED
policy are unchanged. GPIO21 retains its separate owner. Kernel requests
exclude other cooperating requests; they cannot exclude unrelated raw-MMIO
programs, privileged debug tools or legacy installed writers.

## Explicit supported profile

Both PAIRED_GPIO_PROFILE=bcm2835-gpiomem-v1 and an inventoried
PAIRED_GPIO_CHIP=/dev/gpiochipN are mandatory. There are no defaults/fallbacks.
The daemon validates libgpiod Python >=2.3,<3, chip name, label/count
pinctrl-bcm2835/54 or pinctrl-bcm2711/58, GPIO26/GPIO20 names and unused status.
It then validates character-device identities against sysfs/device tree:
Raspberry Pi BCM2835/2836/2837/2711 platform, pinctrl-bcm2835 driver, appropriate
brcm,bcm2835-gpio or brcm,bcm2711-gpio node and the common 0x7e200000 bank.
The opened gpiochip character-device identity resolves to a GPIO bus device
with its own dev number, subsystem and direct of_node. Its structural platform
parent must expose the same of_node and be bound to the exact pinctrl-bcm2835
driver. No class-device device link is required; a conflicting parent link,
firmware node, driver binding or bus identity is rejected before reservation.

The gpiomem profile intentionally supports only the legacy
brcm,bcm2835-gpiomem binding, one bound rpi-gpiomem platform instance, and the
matching /sys/class/gpiomem/gpiomem/dev character device. The class device has
no parent; it is not assumed to expose device/of_node. Both DT nodes must
share a parent with one address/size cell and matching register base. The
legacy 4096-byte mapping must cover the runtime page size. Pi5/RP1, alternate
bindings/layouts, missing metadata, different line names, busy lines and
ambiguous devices fail before request or MMIO mutation. Missing gpiomem
permissions fail after reservation and release it without a fallback.

These checks identify a narrowly supported mapping, not installed-driver
version attestation. Record/review the actual kernel version, driver source,
model/revision and DT/sysfs inventory before accepting this profile. Never
edit live line names or relax validation merely to pass commissioning.

## Reviewed future migration sequence

This is a planning record, not an executable installer. Trusted-console
deployment remains outside the restricted SSH helper allowlist.

1. Keep 24 V valve supply disconnected and lighting disabled. Record exact
   source revision, hashes of installed paired script/unit/drop-ins, active
   interpreter, Python/libgpiod versions, device ownership/permissions, kernel
   version and verified model/revision. Capture the existing rollback artifacts
   privately. Source checkout and installed artifacts are separate evidence.
2. Review the active DT/sysfs mapping and GPIO consumers against the profile.
   Confirm no legacy GPIO26/20 nodes or other raw/configuration writers remain.
   Confirm GPIO21 belongs to the expected separate BCM bank and owner.
3. Prepare the reviewed source and compatible dependencies in a root-controlled
   Python >=3.12 environment. The new optional extra is paired-gpio; lighting-gpio
   retains the same dependency range. Import/version/API-check libgpiod with the
   exact service interpreter. A package in the Hub venv does not make
   /usr/bin/python3 (the historical paired unit interpreter) able to import it.
4. Review [candidate override](../../deployment/lighting/paired-gpio-migration.conf.example)
   and [configuration](../../deployment/lighting/paired-gpio.environment.example).
   Both are disabled examples. Verify the absolute venv/script paths, root
   ownership, protected environment file, nodered identity, existing gpio-group
   permissions, /dev/gpiomem and only the verified gpiochip access. The template
   deliberately has no chip DeviceAllow; supply that exact entry only after
   inventory. Validate the resulting unit with systemd-analyze verify.
5. A separately authorized trusted-console cutover must place the paired
   controller in confirmed DRAIN, prevent requests during replacement and
   restart only the reviewed paired service. Missing config/dependency will
   stop the new daemon; do not overwrite the installed script in isolation or
   assume the historical unit can start it. The candidate override requires a
   separate paired-gpio-migration-approved marker; it grants no lighting approval.
6. Verify exact running artifact/interpreter, exclusive line ownership,
   protocol2 and DRAIN receipt/readback, then the existing deployed-flow,
   socket and startup gates. On any failure stop, retain requested DRAIN, keep
   loads disconnected and investigate. Do not retry SUPPLY.
7. Under a separately approved disconnected-load test envelope, capture GPIO
   and relay traces during request/preload/configure, normal paired writes,
   shutdown/release, partial errors, both services' restart and light
   request/release/crash interleavings. Observe all intermediate pair states;
   no mixed valve states are accepted. Measure light changes independently.
   Exact driver behavior and timing are not demonstrated by workstation tests.
8. Record the complete acceptance before considering lighting marker,
   DeviceAllow or GPIO opt-in. Actual Protect authenticated POST identity/time
   profile, Node-RED runtime, board/jumper/load/contact suitability, Dial
   artifact and mains acceptance remain separate gates.

Legal energized (valve1,valve2,light) states are
(0,0,0),(0,0,1),(1,1,0),(1,1,1). Physical active-low valve DRAIN levels are
(HIGH,HIGH); GPIO readback does not establish plumbing position.

| Fault domain | Required safe outcome and surviving mechanism | Evidence/limit |
| --- | --- | --- |
| Communication loss | Paired local 60s lease requests DRAIN; light executor 3s lease requests OFF while its process runs | Existing simulated lease checks; observed cutoff/contact timing unverified |
| Paired or light process crash/hang | DRAIN/OFF via an independent supervisor or hardware mechanism | No proven surviving cutoff; cleanup and same-process lease cannot establish it; maximum time unknown |
| Controller reset/reboot | Preserve paired constraint and light OFF before/during ownership | Boot circuitry/bias and kernel request/release traces unverified; time bound unknown |
| Pi power loss/restoration | Reach/retain safe hydraulic state and avoid unintended light activation | Independent hardware/passive behavior unverified; time bound unknown |
| Relay/valve supply loss/restoration | Safe actual valve position and paired contact constraints | 24 V behavior, retained position and recovery unverified |
| Lamp supply loss/restoration | Safe lamp behavior, including return while a command is active | Actual driver/contact/inrush behavior and recovery unverified |

Any later physical test needs an observer, bounded cutoff, verified stop path
that survives the injected fault, and explicit approval. None is authorized here.

## Rollback

Close lighting ingress, request and verify OFF using its owner, then stop and
disable lighting before any restoration of the old paired daemon. If OFF or
DRAIN cannot be established, use the commissioned physical isolation path;
none is newly proven here. Restoring an old raw FSEL writer while GPIO21 can
request/release is prohibited. Restore the exact saved paired script,
interpreter/unit/config only through the separately approved trusted-console
procedure with loads disconnected, then verify paired startup DRAIN and
protocol receipts. Do not restore shower databases, enable legacy individual
GPIO flows or use SUPPLY as a diagnostic. Keep lighting disabled after rollback.

## Primary references

Reviewed 2026-10-13; these do not identify the installed kernel:
[BCM pinctrl driver](https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.12.y/drivers/pinctrl/bcm/pinctrl-bcm2835.c),
[gpiomem driver](https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.12.y/drivers/char/raspberrypi-gpiomem.c),
[legacy DT binding](https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.12.y/arch/arm/boot/dts/broadcom/bcm270x-rpi.dtsi),
[GPIO v2 request](https://docs.kernel.org/userspace-api/gpio/gpio-v2-get-line-ioctl.html),
[libgpiod2.3 Chip](https://libgpiod.readthedocs.io/en/v2.3/python_chip.html),
[LineRequest](https://libgpiod.readthedocs.io/en/v2.3/python_line_request.html),
[LineSettings source](https://raw.githubusercontent.com/brgl/libgpiod/v2.3/bindings/python/gpiod/line_settings.py).

## Inventoried two-stage package - 2026-10-13

For the actual Pi4/BCM2711, kernel6.18.39 and Python3.13.5 inventory, use the
[reviewed trusted-console package](../../deployment/paired-gpio-migration/README.md).
It pins gpiod2.3.0 in an isolated paired-service venv and canonical gpiochip0.
Preparation does not replace services; installation is a separate receipt-gated
step. The concrete override uses Restart=no during disconnected migration;
automatic paired-process recovery is disabled and operator recovery is required
after a crash. The generic future template above is not an installation recipe.
[Package verification](../evidence/2026-10-13-paired-gpio-migration-package.md)
records815 tests and final review PASS. Actual target preparation/install and
all subsequent physical/light activation acceptance remain pending.
