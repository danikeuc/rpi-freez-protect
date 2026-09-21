# Workstation Codex commissioning design

## Goal

Use Codex on Danijel's workstation as the interactive engineering control plane for the DietPi-based Freeze Protect installation and CrowPanel. The Pi must remain private on the LAN; no GitHub self-hosted runner, public SSH exposure, or autonomous valve-power test is introduced.

## Topology

```text
Workstation Codex -- SSH key --> DietPi (private LAN)
       |                              |
       | Git/GitHub                    +-- Hub, Node-RED and paired GPIO daemon
       +-- PlatformIO build/flash when USB is local
```

When the CrowPanel USB cable is connected to the Pi, Codex runs the PlatformIO discovery/build/flash commands through SSH. When it is connected to the workstation, Codex runs those commands locally and uses SSH only for the Pi-side Hub and GPIO checks. This location is explicitly checked before a flash command; no serial device path is guessed.

## Access boundary

- Use a dedicated Pi account named `freezeprotect` for Codex access; do not use persistent `root` SSH login.
- The account receives a dedicated SSH public key and only the Linux groups required for the approved commissioning work (`dialout` for the USB serial device and `gpio` for the paired GPIO client where required).
- Any `sudo` command is restricted to an explicit, root-owned commissioning helper or the existing named systemd units. It must not accept an arbitrary shell command or read `/etc/rpi-freeze-protect/environment` or `node-red.env`.
- GitHub is source control only. No GitHub Actions self-hosted runner is installed on the Pi.
- The temporary `root` key used during bootstrap is removed after the dedicated account is verified.

## Commissioning stages

1. **Inventory** — identify the Pi OS, active `node-red.service`, `/dev/serial/by-id` entries, platform tooling, GPIO 26/20 levels, and the repository revision. This stage only reads state.
2. **Build and flash** — build the CrowPanel firmware, require one unambiguous serial device, flash it, and collect the boot log. No relay or 24 V command is sent.
3. **Pi safe-state deployment** — deploy the paired GPIO daemon, Hub and constrained Node-RED bridge with the 24 V valve supply disconnected. The preflight must reject enabled legacy GPIO 26/20 or `/trigger` paths.
4. **GPIO-only test** — verify startup and explicit `DRAIN` are high/high on GPIO 26 and 20. A timed-shower request may only be exercised while valve power is disconnected; both pins must move together and return to high/high.
5. **Controlled valve test** — requires Danijel's explicit in-session approval after water isolation and physical confirmation that the 24 V supply is ready. The sequence is one minute `SUPPLY`, then immediate `DRAIN`, with observed plumbing paths recorded. A failed readback leaves the system in `DRAIN` and stops the procedure.
6. **DS18B20 later** — sensor wiring and commissioning remain a separate future stage. Before that, `sensor_pending` is a safe `DRAIN` condition.

## Guardrails

- The workstation Codex never prints or commits Wi-Fi, admin, display, or Node-RED tokens.
- Every remote action starts with a short status/readback command and stops on an unexpected result.
- Flash, systemd restart, Node-RED deploy, and 24 V tests are separate operator-visible commands; no background timer or Git event triggers them.
- The legacy Node-RED relay flow is exported and disabled before the paired bridge is deployed. The supplied preflight is the release gate before 24 V is connected.

## Acceptance evidence

- Python suite, JSON/JavaScript preflight and native display-state test pass on the selected repository revision.
- CrowPanel is detected on exactly one serial port, accepts the firmware, and displays its boot/status screen.
- The Pi reports `node-red.service` and the paired GPIO daemon active; GPIO 26 and 20 are high at startup and after `DRAIN`.
- With 24 V disconnected, the timed-shower and immediate-drain path changes both GPIO levels together and confirms high/high afterward.
- The 24 V and plumbing outcome is recorded only after Danijel explicitly permits stage 5.
