import shlex
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]


def test_workstation_commissioning_has_no_runner_or_root_ssh_path() -> None:
    guide = (ROOT / "deployment/WORKSTATION_CODEX_COMMISSIONING.md").read_text(
        encoding="utf-8"
    )

    assert "freezeprotect" in guide
    assert "GitHub self-hosted runner" not in guide
    assert "24 V valve supply disconnected" in guide
    assert "root SSH" not in guide
    assert "Keep Pi SSH private-LAN-only; do not expose it publicly." in guide


def test_codex_prompt_has_explicit_stop_gate_before_24v() -> None:
    prompt = (
        ROOT / "deployment/workstation-codex/CODEX_COMMISSIONING_PROMPT.md"
    ).read_text(encoding="utf-8")

    assert "Keep the 24 V valve supply disconnected" in prompt
    assert "Do not run SUPPLY" in prompt
    assert "Stop and ask Danijel" in prompt
    assert "sudo -n /usr/local/sbin/freeze-protect-commission drain" in prompt


def test_acceptance_uses_copy_safe_fixed_commands_and_batch_mode() -> None:
    prompt = (
        ROOT / "deployment/workstation-codex/CODEX_COMMISSIONING_PROMPT.md"
    ).read_text(encoding="utf-8")
    guide = (ROOT / "deployment/WORKSTATION_CODEX_COMMISSIONING.md").read_text(
        encoding="utf-8"
    )

    assert "{inventory|usb|status}" not in prompt
    assert "{inventory|usb|status|drain}" not in prompt
    for subcommand in ("inventory", "usb", "status", "drain"):
        assert (
            f"sudo -n /usr/local/sbin/freeze-protect-commission {subcommand}" in prompt
        )

    for subcommand in ("inventory", "usb", "status"):
        assert (
            "ssh -o BatchMode=yes freezeprotect@<Pi-LAN-IP> "
            f"sudo -n /usr/local/sbin/freeze-protect-commission {subcommand}"
        ) in guide
    assert (
        "cd /opt/rpi-freez-protect/firmware/crowpanel && pio run --target upload"
        in guide
    )


def test_privileged_helper_has_only_fixed_subcommands() -> None:
    helper = (
        ROOT / "deployment/workstation-codex/freeze-protect-commission"
    ).read_text(encoding="utf-8")

    assert 'case "${1:-}" in' in helper
    assert "inventory)" in helper
    assert "usb)" in helper
    assert "status)" in helper
    assert "drain)" in helper
    assert "eval " not in helper
    assert "bash -c" not in helper
    assert "pinctrl get 26" in helper
    assert "pinctrl get 20" in helper


def test_privileged_helper_clears_inherited_environment() -> None:
    helper = (
        ROOT / "deployment/workstation-codex/freeze-protect-commission"
    ).read_text(encoding="utf-8")

    assert 'exec /usr/bin/env -i PATH="$PATH" /bin/sh -s -- "$1"' in helper


def test_usb_inventory_does_not_dereference_links() -> None:
    helper = (
        ROOT / "deployment/workstation-codex/freeze-protect-commission"
    ).read_text(encoding="utf-8")

    assert "find /dev/serial/by-id -maxdepth 1 -type l" in helper
    assert "find -L /dev/serial/by-id" not in helper


def test_bootstrap_requires_one_public_key_file_and_installs_exact_sudoers_rule() -> (
    None
):
    root = ROOT / "deployment/workstation-codex"
    bootstrap = (root / "bootstrap-freezeprotect-access.sh").read_text(encoding="utf-8")
    sudoers = (root / "freeze-protect-commission.sudoers").read_text(encoding="utf-8")

    assert "usage: $0 /path/to/public-key" in bootstrap
    assert "--home-dir /home/freezeprotect --shell /bin/bash" in bootstrap
    assert (
        'install -d -o root -g "$primary_group" -m 0710 /home/freezeprotect/.ssh'
        in bootstrap
    )
    assert 'install -o root -g "$primary_group" -m 0640 "$public_key_file"' in bootstrap
    assert "NOPASSWD:" in sudoers
    assert "/usr/local/sbin/freeze-protect-commission inventory" in sudoers
    assert "/usr/local/sbin/freeze-protect-commission usb" in sudoers
    assert "/usr/local/sbin/freeze-protect-commission status" in sudoers
    assert "/usr/local/sbin/freeze-protect-commission drain" in sudoers
    assert "ALL" not in sudoers.replace("ALL=(root)", "")


def test_bootstrap_checks_required_groups_before_account_or_key_changes() -> None:
    bootstrap = (
        ROOT / "deployment/workstation-codex/bootstrap-freezeprotect-access.sh"
    ).read_text(encoding="utf-8")

    group_check = bootstrap.index("for required_group in dialout gpio; do")
    mutations = (
        bootstrap.index("useradd --system --create-home"),
        bootstrap.index("/home/freezeprotect/.ssh/authorized_keys"),
    )

    assert all(group_check < mutation for mutation in mutations)


def test_bootstrap_stops_for_incompatible_account_before_any_install() -> None:
    bootstrap = (
        ROOT / "deployment/workstation-codex/bootstrap-freezeprotect-access.sh"
    ).read_text()
    assert "account_home=$(getent passwd freezeprotect | cut -d: -f6)" in bootstrap
    assert "account_shell=$(getent passwd freezeprotect | cut -d: -f7)" in bootstrap
    assert '[ "$account_home" = /home/freezeprotect ]' in bootstrap
    assert '[ "$account_shell" = /bin/bash ]' in bootstrap
    assert '[ "$actual_groups" = "$expected_groups" ]' in bootstrap
    assert bootstrap.index("validate_account_profile\n") < bootstrap.index("install -")
    assert "usermod" not in bootstrap
    assert "trusted local console" in bootstrap


def test_bootstrap_protects_key_path_and_validates_access_before_success() -> None:
    bootstrap = (
        ROOT / "deployment/workstation-codex/bootstrap-freezeprotect-access.sh"
    ).read_text()
    assert "primary_group=$(id -gn freezeprotect)" in bootstrap
    assert 'chown root:"$primary_group" /home/freezeprotect' in bootstrap
    assert "chmod 0750 /home/freezeprotect" in bootstrap
    assert "require_root_protected /home" in bootstrap
    assert '[ -L "$path" ]' in bootstrap
    assert "stat -c %u:%g:%a /home/freezeprotect/.ssh)" in bootstrap
    assert "stat -c %u:%g:%a /home/freezeprotect/.ssh/authorized_keys)" in bootstrap
    assert (
        "runuser -u freezeprotect -- test -r /home/freezeprotect/.ssh/authorized_keys"
        in bootstrap
    )
    assert bootstrap.index("runuser -u freezeprotect") < bootstrap.index(
        'echo "freezeprotect access installed"'
    )


def test_root_client_copy_and_interpreter_do_not_trust_the_checkout() -> None:
    bootstrap = (
        ROOT / "deployment/workstation-codex/bootstrap-freezeprotect-access.sh"
    ).read_text()
    helper = (
        ROOT / "deployment/workstation-codex/freeze-protect-commission"
    ).read_text()
    assert (
        "/usr/bin/python3 -I /usr/local/lib/freeze-protect-commission/paired_gpio_client.py DRAIN"
        in helper
    )
    assert (
        "/opt/rpi-freez-protect/deployment/node-red/paired_gpio_client.py" not in helper
    )
    assert 'install -o root -g root -m 0644 "$client_source"' in bootstrap
    assert "require_root_protected /usr/local/lib" in bootstrap
    assert "require_root_protected /usr/local/sbin" in bootstrap
    assert (
        "require_root_protected /usr/local/lib/freeze-protect-commission" in bootstrap
    )


SUCCESS = '{"ok": true, "command": "DRAIN", "gpio": {"26": 1, "20": 1}}'


def run_drain_branch(
    receipt: str, gpio_26: str, gpio_20: str, client_exit: int = 0
) -> subprocess.CompletedProcess[str]:
    """Run only the real drain branch with no socket, pinctrl or root operations.

    Substitute the fixed external client invocation; leave receipt parsing and
    pin validation untouched. Production keeps its fixed clean environment.
    """
    helper = (
        ROOT / "deployment/workstation-codex/freeze-protect-commission"
    ).read_text()
    branch = helper.split("  drain)\n", 1)[1].split("    ;;", 1)[0]
    for client in (
        "/usr/bin/python3 -I /usr/local/lib/freeze-protect-commission/paired_gpio_client.py DRAIN",
        "/opt/rpi-freez-protect/deployment/node-red/paired_gpio_client.py DRAIN",
    ):
        branch = branch.replace(client, "fake_client")
    script = f"""set -eu
fake_client() {{ printf '%s\\n' {shlex.quote(receipt)}; return {client_exit}; }}
pinctrl() {{
  case "$*" in
    'get 26') printf '%s\\n' {shlex.quote(gpio_26)} ;;
    'get 20') printf '%s\\n' {shlex.quote(gpio_20)} ;;
    *) return 99 ;;
  esac
}}
{branch}
"""
    return subprocess.run(
        ["/bin/sh", "-s"],
        input=script,
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )


@pytest.mark.parametrize(
    "receipt",
    [
        '{"ok": false}',
        '{"ok": "true", "command": "DRAIN"}',
        '{"ok": 1, "command": "DRAIN"}',
        "{}",
        "[]",
        "not json",
        "",
        SUCCESS + "\n" + SUCCESS,
        '{"ok": true, "command": "SUPPLY", "gpio": {"26": 1, "20": 1}}',
        '{"ok": true, "command": "DRAIN", "gpio": {"26": 1, "20": 0}}',
    ],
)
def test_drain_rejects_unsuccessful_or_malformed_receipt(receipt: str) -> None:
    result = run_drain_branch(
        receipt,
        "26: op dh pn | hi // GPIO26 = output",
        "20: op dh pn | hi // GPIO20 = output",
    )
    assert result.returncode != 0, result.stdout


@pytest.mark.parametrize("pin", [26, 20])
@pytest.mark.parametrize(
    "record", ["ip pu | hi", "op pn | lo", "noop pn | hi", "op pn | high"]
)
def test_drain_requires_standalone_output_and_high_tokens(
    pin: int, record: str
) -> None:
    records = {26: "26: op dh pn | hi", 20: "20: op dh pn | hi"}
    records[pin] = f"{pin}: {record}"
    assert run_drain_branch(SUCCESS, records[26], records[20]).returncode != 0


def test_drain_rejects_client_process_failure_even_with_success_json() -> None:
    assert (
        run_drain_branch(
            SUCCESS, "26: op | hi", "20: op | hi", client_exit=1
        ).returncode
        != 0
    )


def test_drain_accepts_success_receipt_and_both_output_high_records() -> None:
    result = run_drain_branch(
        SUCCESS,
        "26: op dh pn | hi // GPIO26 = output",
        "20: op dh pn | hi // GPIO20 = output",
    )
    assert result.returncode == 0, result.stderr
