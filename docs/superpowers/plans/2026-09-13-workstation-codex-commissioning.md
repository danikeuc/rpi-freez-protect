# Workstation Codex Commissioning Implementation Plan

> **Historical implementation record.** The current account, SSH and USB
> contract is in
> [`../../../deployment/WORKSTATION_CODEX_COMMISSIONING.md`](../../../deployment/WORKSTATION_CODEX_COMMISSIONING.md).
> See [`../../PROJECT_STATE.md`](../../PROJECT_STATE.md) for current evidence.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable a workstation-hosted Codex session to build, flash and safely commission the DietPi Freeze Protect installation through a dedicated non-root SSH account.

**Architecture:** The workstation remains the interactive Codex and Git client. DietPi exposes only a `freezeprotect` SSH account with a dedicated key and tightly enumerated `sudo` entry points. Root-owned helper commands provide read-only inventory and explicit safe `DRAIN`; they do not run caller-provided shell text or expose configuration secrets. No GitHub runner or automatic hardware trigger is used.

**Tech Stack:** Debian/DietPi, OpenSSH, POSIX shell, `sudo`, systemd, `pinctrl`, Python/pytest, PlatformIO Core.

**Spec:** `docs/superpowers/specs/2026-09-13-workstation-codex-commissioning-design.md`

**Final-review amendment (2026-09-13):** The secure functional key contract is
root:<account-primary-group> `0710` for `.ssh` and `0640` for `authorized_keys`,
inside a root-controlled `0750` home. The earlier root-only `0700`/`0600`
contract prevented target-user OpenSSH access and is superseded. Bootstrap
must verify read/non-write access and stop before key/group mutations for an
existing incompatible home, shell, or group profile; no automatic migration.
The privileged client is a root-owned copy under
`/usr/local/lib/freeze-protect-commission/`, invoked with `/usr/bin/python3 -I`;
its ancestors and outer helper are protected independently of writable builds.
The helper code below is only a command-shape sketch: the implemented DRAIN
path must validate its single structured receipt and both output/high records.

## Global Constraints

- The Pi remains reachable only on its private LAN; do not open public SSH or install a GitHub self-hosted runner.
- The dedicated account is `freezeprotect`; persistent `root` SSH access is not part of the solution.
- Never print, commit, or copy Wi-Fi, administrator, display, or Node-RED tokens.
- Helper commands accept no caller-controlled command, path, environment variable, or serial-port argument.
- GPIO 26 and 20 must be high/high after startup and after every `DRAIN` command.
- The 24 V valve supply stays disconnected through inventory, build, flash, deployment and GPIO-only tests. A 24 V test requires Danijel's explicit in-session approval.
- A CrowPanel serial port is used only when exactly one matching `/dev/serial/by-id` entry is discovered; otherwise flashing stops.

---

## File structure

```text
deployment/workstation-codex/bootstrap-freezeprotect-access.sh
    # root-run setup: account, authorized key, limited groups, helper install
deployment/workstation-codex/freeze-protect-commission
    # root-owned, argument-free helper with inventory, usb, service-status and drain subcommands
deployment/workstation-codex/freeze-protect-commission.sudoers
    # exact sudo command allowlist for the dedicated account
deployment/WORKSTATION_CODEX_COMMISSIONING.md
    # human/operator setup, local Codex prompt and staged acceptance procedure
tests/integration/test_workstation_commissioning_assets.py
    # static contract tests for the deployment boundaries and safety wording
README.md
    # link to the workstation procedure as the preferred commissioning route
```

### Task 1: Define testable workstation commissioning assets

**Files:**
- Create: `tests/integration/test_workstation_commissioning_assets.py`
- Create: `deployment/WORKSTATION_CODEX_COMMISSIONING.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: `deployment/COMMISSIONING.md`, `deployment/CROWPANEL_COMMISSIONING.md` and the approved workstation design.
- Produces: documented asset paths and a static test contract used by the installation and helper tasks.

- [ ] **Step 1: Write the failing contract test**

```python
from pathlib import Path


ROOT = Path(__file__).parents[2]


def test_workstation_commissioning_has_no_runner_or_root_ssh_path() -> None:
    guide = (ROOT / "deployment/WORKSTATION_CODEX_COMMISSIONING.md").read_text(
        encoding="utf-8"
    )

    assert "freezeprotect" in guide
    assert "GitHub self-hosted runner" not in guide
    assert "24 V valve supply disconnected" in guide
    assert "root SSH" not in guide
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `python -m pytest -q tests/integration/test_workstation_commissioning_assets.py`

Expected: FAIL with `FileNotFoundError` for `deployment/WORKSTATION_CODEX_COMMISSIONING.md`.

- [ ] **Step 3: Add the minimal operator guide and README route**

Create the guide with these fixed sections and commands:

```markdown
## 1. Workstation prerequisites
Install Codex CLI, Git, OpenSSH client and PlatformIO Core on the workstation.

## 2. Pi bootstrap
Copy the repository to `/opt/rpi-freez-protect` and run the root bootstrap script once from a trusted local Pi console.

## 3. Local Codex session
Start Codex from the cloned repository on the workstation. Give it the fixed instruction: inspect first, keep 24 V disconnected, and stop before a physical valve test until Danijel explicitly approves.

## 4. Staged acceptance
Inventory -> one USB serial device -> build/flash -> high/high GPIO `DRAIN` -> disconnected timed-shower test -> explicitly approved 24 V test.
```

Add a README link headed `Workstation Codex commissioning`; it must point to `deployment/WORKSTATION_CODEX_COMMISSIONING.md` and state that the procedure supersedes the proposed runner approach.

- [ ] **Step 4: Run the focused test to verify it passes**

Run: `python -m pytest -q tests/integration/test_workstation_commissioning_assets.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add README.md deployment/WORKSTATION_CODEX_COMMISSIONING.md tests/integration/test_workstation_commissioning_assets.py
git commit -m "docs: add workstation Codex commissioning guide"
```

### Task 2: Add an argument-free privileged commissioning helper

**Files:**
- Create: `deployment/workstation-codex/freeze-protect-commission`
- Modify: `tests/integration/test_workstation_commissioning_assets.py`

**Interfaces:**
- Consumes: fixed Raspberry Pi pins BCM 26 and 20, `freeze-protect-pair-gpio.service`, `freeze-protect.service`, and `node-red.service`.
- Produces: `/usr/local/sbin/freeze-protect-commission {inventory|usb|status|drain}`; unknown or missing subcommands exit nonzero without changing GPIO.

- [ ] **Step 1: Extend the test with the wished-for helper contract**

```python
def test_privileged_helper_has_only_fixed_subcommands() -> None:
    helper = (ROOT / "deployment/workstation-codex/freeze-protect-commission").read_text(
        encoding="utf-8"
    )

    assert 'case "${1:-}" in' in helper
    assert "inventory)" in helper
    assert "usb)" in helper
    assert "status)" in helper
    assert "drain)" in helper
    assert "eval " not in helper
    assert 'bash -c' not in helper
    assert "pinctrl get 26" in helper
    assert "pinctrl get 20" in helper
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `python -m pytest -q tests/integration/test_workstation_commissioning_assets.py::test_privileged_helper_has_only_fixed_subcommands`

Expected: FAIL with `FileNotFoundError` for `deployment/workstation-codex/freeze-protect-commission`.

- [ ] **Step 3: Implement the helper with fixed behavior**

Use `#!/bin/sh`, `set -eu`, and this command shape:

```sh
case "${1:-}" in
  inventory)
    uname -a
    id freezeprotect
    git -C /opt/rpi-freez-protect rev-parse HEAD
    ;;
  usb)
    find -L /dev/serial/by-id -maxdepth 1 -type l -printf '%f -> %l\n'
    ;;
  status)
    systemctl is-active node-red.service
    systemctl is-active freeze-protect-pair-gpio.service
    systemctl is-active freeze-protect.service
    pinctrl get 26
    pinctrl get 20
    ;;
  drain)
    /usr/bin/python3 -I /usr/local/lib/freeze-protect-commission/paired_gpio_client.py DRAIN
    pinctrl get 26
    pinctrl get 20
    ;;
  *)
    echo "usage: freeze-protect-commission {inventory|usb|status|drain}" >&2
    exit 64
    ;;
esac
```

`drain` must require one well-formed JSON DRAIN receipt with boolean `ok` true and both reported GPIO levels high, then require standalone `op` and `hi` tokens for both GPIO 26 and 20. Any unsuccessful/malformed receipt, process failure, or failed output/high readback returns nonzero. It must not invoke `SUPPLY`, edit Node-RED flows, read any environment file, or accept extra arguments.

- [ ] **Step 4: Run the static test and shell syntax check**

Run: `python -m pytest -q tests/integration/test_workstation_commissioning_assets.py && sh -n deployment/workstation-codex/freeze-protect-commission`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deployment/workstation-codex/freeze-protect-commission tests/integration/test_workstation_commissioning_assets.py
git commit -m "feat: add restricted Pi commissioning helper"
```

### Task 3: Bootstrap dedicated SSH access and exact sudo permissions

**Files:**
- Create: `deployment/workstation-codex/bootstrap-freezeprotect-access.sh`
- Create: `deployment/workstation-codex/freeze-protect-commission.sudoers`
- Modify: `tests/integration/test_workstation_commissioning_assets.py`
- Modify: `deployment/WORKSTATION_CODEX_COMMISSIONING.md`

**Interfaces:**
- Consumes: a single public-key file path supplied by the trusted local Pi operator at bootstrap time.
- Produces: `freezeprotect` account, `/home/freezeprotect/.ssh/authorized_keys`, installed root-owned helper at `/usr/local/sbin/freeze-protect-commission`, and a sudo allowlist for its four exact subcommands.

- [ ] **Step 1: Add failing safety assertions**

```python
def test_bootstrap_requires_one_public_key_file_and_installs_exact_sudoers_rule() -> None:
    root = ROOT / "deployment/workstation-codex"
    bootstrap = (root / "bootstrap-freezeprotect-access.sh").read_text(encoding="utf-8")
    sudoers = (root / "freeze-protect-commission.sudoers").read_text(encoding="utf-8")

    assert 'usage: $0 /path/to/public-key' in bootstrap
    assert "--home-dir /home/freezeprotect --shell /bin/bash" in bootstrap
    assert 'install -d -o root -g "$primary_group" -m 0710 /home/freezeprotect/.ssh' in bootstrap
    assert 'install -o root -g "$primary_group" -m 0640 "$public_key_file"' in bootstrap
    assert "NOPASSWD:" in sudoers
    assert "/usr/local/sbin/freeze-protect-commission inventory" in sudoers
    assert "/usr/local/sbin/freeze-protect-commission usb" in sudoers
    assert "/usr/local/sbin/freeze-protect-commission status" in sudoers
    assert "/usr/local/sbin/freeze-protect-commission drain" in sudoers
    assert "ALL" not in sudoers.replace("ALL=(root)", "")
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `python -m pytest -q tests/integration/test_workstation_commissioning_assets.py::test_bootstrap_requires_one_public_key_file_and_installs_exact_sudoers_rule`

Expected: FAIL with `FileNotFoundError` for `bootstrap-freezeprotect-access.sh`.

- [ ] **Step 3: Implement bootstrap and sudoers assets**

The bootstrap script must require exactly one readable public-key file, reject any file with more than one nonempty line, install only its contents as `authorized_keys`, and use the amended key modes above. It must use `install -o root -g root -m 0755` for the helper, `0644` for the isolated standard-library client copy, and `install -o root -g root -m 0440` for sudoers, then run `visudo -cf /etc/sudoers.d/freeze-protect-commission` before completing. Require `dialout` and `gpio` to exist before account/key mutations. A new account receives only those supplementary groups; an existing account must already have the exact dedicated-login profile or bootstrap stops for trusted-console remediation without changing keys/groups.

The sudoers file contains exactly:

```sudoers
Cmnd_Alias FREEZE_PROTECT_COMMISSION = \
  /usr/local/sbin/freeze-protect-commission inventory, \
  /usr/local/sbin/freeze-protect-commission usb, \
  /usr/local/sbin/freeze-protect-commission status, \
  /usr/local/sbin/freeze-protect-commission drain
freezeprotect ALL=(root) NOPASSWD: FREEZE_PROTECT_COMMISSION
```

Add a guide section that shows the one trusted-console command:

```bash
sudo /opt/rpi-freez-protect/deployment/workstation-codex/bootstrap-freezeprotect-access.sh \
  /tmp/freezeprotect-workstation.pub
```

It also instructs the operator to remove the temporary `root` key after `ssh freezeprotect@<Pi-LAN-IP> sudo -n /usr/local/sbin/freeze-protect-commission inventory` succeeds.

- [ ] **Step 4: Run tests and syntax validation**

Run: `python -m pytest -q tests/integration/test_workstation_commissioning_assets.py && sh -n deployment/workstation-codex/bootstrap-freezeprotect-access.sh && visudo -cf deployment/workstation-codex/freeze-protect-commission.sudoers`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deployment/workstation-codex tests/integration/test_workstation_commissioning_assets.py deployment/WORKSTATION_CODEX_COMMISSIONING.md
git commit -m "feat: provision restricted workstation Codex access"
```

### Task 4: Add explicit Codex operating prompt and staged local acceptance

**Files:**
- Create: `deployment/workstation-codex/CODEX_COMMISSIONING_PROMPT.md`
- Modify: `deployment/WORKSTATION_CODEX_COMMISSIONING.md`
- Modify: `tests/integration/test_workstation_commissioning_assets.py`

**Interfaces:**
- Consumes: the `freezeprotect` SSH account and `freeze-protect-commission` helper from Tasks 2–3.
- Produces: a copyable local Codex prompt and a deterministic operator acceptance sequence.

- [ ] **Step 1: Add the failing prompt/acceptance test**

```python
def test_codex_prompt_has_explicit_stop_gate_before_24v() -> None:
    prompt = (ROOT / "deployment/workstation-codex/CODEX_COMMISSIONING_PROMPT.md").read_text(
        encoding="utf-8"
    )

    assert "Keep the 24 V valve supply disconnected" in prompt
    assert "Do not run SUPPLY" in prompt
    assert "Stop and ask Danijel" in prompt
    assert "sudo -n /usr/local/sbin/freeze-protect-commission drain" in prompt
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `python -m pytest -q tests/integration/test_workstation_commissioning_assets.py::test_codex_prompt_has_explicit_stop_gate_before_24v`

Expected: FAIL with `FileNotFoundError` for `CODEX_COMMISSIONING_PROMPT.md`.

- [ ] **Step 3: Write the fixed local Codex prompt and acceptance sequence**

The prompt must direct local Codex to use `ssh -o BatchMode=yes freezeprotect@<Pi-LAN-IP>` for read-only checks and `sudo -n /usr/local/sbin/freeze-protect-commission {inventory|usb|status|drain}` for privileged fixed operations. It must require exactly one USB serial-by-id device before `pio run --target upload`, collect `pio device monitor --baud 115200` boot output, and prohibit `SUPPLY` until Danijel explicitly approves the 24 V stage in the current conversation.

The guide acceptance sequence must include these commands in order:

```bash
ssh freezeprotect@<Pi-LAN-IP> sudo -n /usr/local/sbin/freeze-protect-commission inventory
ssh freezeprotect@<Pi-LAN-IP> sudo -n /usr/local/sbin/freeze-protect-commission usb
ssh freezeprotect@<Pi-LAN-IP> sudo -n /usr/local/sbin/freeze-protect-commission status
ssh freezeprotect@<Pi-LAN-IP> sudo -n /usr/local/sbin/freeze-protect-commission drain
```

Then document the two USB-location branches: direct local `pio` commands when the cable is on the workstation, or the same `pio` commands prefixed with `ssh freezeprotect@<Pi-LAN-IP>` when it is on the Pi. Each branch stops when serial discovery returns zero or more than one matching device.

- [ ] **Step 4: Run the focused test and full suite**

Run: `python -m pytest -q tests/integration/test_workstation_commissioning_assets.py && python -m pytest -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deployment/workstation-codex/CODEX_COMMISSIONING_PROMPT.md deployment/WORKSTATION_CODEX_COMMISSIONING.md tests/integration/test_workstation_commissioning_assets.py
git commit -m "docs: add staged local Codex acceptance prompt"
```

## Plan self-review

| Design requirement | Plan coverage |
| --- | --- |
| Workstation Codex rather than runner | Tasks 1 and 4 |
| Dedicated non-root SSH account | Task 3 |
| Fixed, non-arbitrary privileged operations | Task 2 and Task 3 |
| USB location is checked, never guessed | Task 2 and Task 4 |
| No secret disclosure or public SSH | Global constraints and Tasks 1–4 |
| 24 V remains a human-approved final stage | Global constraints and Task 4 |
| Testable deployment assets | Tasks 1–4 |
