import os
import shlex
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]


def test_bootstrap_remains_executable_for_trusted_console_use() -> None:
    """Catch an asset replacement that makes the documented bootstrap unrunnable."""
    bootstrap = ROOT / "deployment/workstation-codex/bootstrap-freezeprotect-access.sh"
    assert bootstrap.stat().st_mode & 0o111


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
            "ssh -o BatchMode=yes freezeprotect-commission@<Pi-LAN-IP> "
            f"sudo -n /usr/local/sbin/freeze-protect-commission {subcommand}"
        ) in guide
    assert "cd /opt/rpi-freez-protect/firmware/crowpanel" in guide
    assert "/opt/freezeprotect-local-flash-tools/bin/pio run --target upload" in guide


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
    assert "commission_home=/home/freezeprotect-commission" in bootstrap
    assert (
        'install -d -o root -g "$commission_primary_group" -m 0710 "$commission_home/.ssh"'
        in bootstrap
    )
    assert (
        'install -o root -g "$commission_primary_group" -m 0640 "$key_snapshot"'
        in bootstrap
    )
    assert "NOPASSWD:" in sudoers
    assert "/usr/local/sbin/freeze-protect-commission inventory" in sudoers
    assert "/usr/local/sbin/freeze-protect-commission usb" in sudoers
    assert "/usr/local/sbin/freeze-protect-commission status" in sudoers
    assert "/usr/local/sbin/freeze-protect-commission drain" in sudoers
    assert "ALL" not in sudoers.replace("ALL=(root)", "")


def test_bootstrap_snapshots_only_a_root_controlled_public_key() -> None:
    bootstrap = (
        ROOT / "deployment/workstation-codex/bootstrap-freezeprotect-access.sh"
    ).read_text(encoding="utf-8")
    guide = (ROOT / "deployment/WORKSTATION_CODEX_COMMISSIONING.md").read_text(
        encoding="utf-8"
    )

    assert 'case "$public_key_file" in' in bootstrap
    assert (
        'require_root_protected_ancestors "$(dirname -- "$public_key_file")"'
        in bootstrap
    )
    assert 'require_root_owned_file "$public_key_file"' in bootstrap
    assert (
        "key_snapshot=$(mktemp /root/freezeprotect-commission-key.XXXXXX)" in bootstrap
    )
    assert (
        'install -o root -g root -m 0600 "$public_key_file" "$key_snapshot"'
        in bootstrap
    )
    assert "awk 'NF { count++ } END { print count + 0 }' \"$key_snapshot\"" in bootstrap
    assert "trap 'rm -f \"$key_snapshot\"' EXIT HUP INT TERM" in bootstrap
    assert "/root/.ssh/freezeprotect-commission-workstation.pub" in guide
    assert "/tmp/freezeprotect-commission-workstation.pub" not in guide


def test_bootstrap_requires_root_controlled_privileged_source_assets() -> None:
    bootstrap = (
        ROOT / "deployment/workstation-codex/bootstrap-freezeprotect-access.sh"
    ).read_text(encoding="utf-8")

    assert "require_root_owned_file()" in bootstrap
    assert "for source_asset in" in bootstrap
    assert (
        'require_root_protected_ancestors "$(dirname -- "$source_asset")"' in bootstrap
    )
    assert 'require_root_owned_file "$source_asset"' in bootstrap
    assert bootstrap.index("for source_asset in") < bootstrap.index(
        'install -o root -g root -m 0644 "$client_source"'
    )


def test_bootstrap_never_grants_device_groups_to_the_commissioning_login() -> None:
    bootstrap = (
        ROOT / "deployment/workstation-codex/bootstrap-freezeprotect-access.sh"
    ).read_text(encoding="utf-8")

    assert "for required_group" not in bootstrap
    assert '--groups dialout "$commission_account"' not in bootstrap
    assert "--groups" not in bootstrap
    assert "for prohibited_group in gpio dialout nodered; do" in bootstrap
    assert 'grep -Fx "$prohibited_group"' in bootstrap


def test_bootstrap_stops_for_incompatible_account_before_any_install() -> None:
    bootstrap = (
        ROOT / "deployment/workstation-codex/bootstrap-freezeprotect-access.sh"
    ).read_text()
    assert "validate_service_account()" in bootstrap
    assert "validate_commission_account()" in bootstrap
    assert '[ "$service_home" = /var/lib/rpi-freeze-protect ]' in bootstrap
    assert '[ "$commission_home_actual" = "$commission_home" ]' in bootstrap
    assert (
        '[ "$commission_actual_groups" = "$commission_expected_groups" ]' in bootstrap
    )
    account_validation = bootstrap.index("# Never migrate either identity")
    account_creation = bootstrap.index(
        'if ! id "$commission_account" >/dev/null 2>&1; then'
    )
    assert account_validation < account_creation
    assert "usermod" not in bootstrap
    assert "trusted local console" in bootstrap


def test_bootstrap_protects_key_path_and_validates_access_before_success() -> None:
    bootstrap = (
        ROOT / "deployment/workstation-codex/bootstrap-freezeprotect-access.sh"
    ).read_text()
    assert 'commission_primary_group=$(id -gn "$commission_account")' in bootstrap
    assert 'chown root:"$commission_primary_group" "$commission_home"' in bootstrap
    assert 'chmod 0750 "$commission_home"' in bootstrap
    assert "require_root_protected /home" in bootstrap
    assert '[ -L "$path" ]' in bootstrap
    assert 'stat -c %u:%g:%a "$commission_home/.ssh")' in bootstrap
    assert 'stat -c %u:%g:%a "$commission_home/.ssh/authorized_keys")' in bootstrap
    assert (
        'runuser -u "$commission_account" -- test -r "$commission_home/.ssh/authorized_keys"'
        in bootstrap
    )
    assert bootstrap.index('runuser -u "$commission_account"') < bootstrap.index(
        'echo "freezeprotect commissioning access installed"'
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


def test_commissioning_login_is_separate_from_the_non_login_service_identity() -> None:
    """Catch a change that gives the SSH user access to service tokens or GPIO."""
    bootstrap = (
        ROOT / "deployment/workstation-codex/bootstrap-freezeprotect-access.sh"
    ).read_text(encoding="utf-8")
    sudoers = (
        ROOT / "deployment/workstation-codex/freeze-protect-commission.sudoers"
    ).read_text(encoding="utf-8")
    service = (ROOT / "deployment/systemd/freeze-protect.service").read_text(
        encoding="utf-8"
    )

    assert "User=freezeprotect" in service
    assert "commission_account=freezeprotect-commission" in bootstrap
    assert "service_account=freezeprotect" in bootstrap
    assert "--groups" not in bootstrap
    assert "for required_group" not in bootstrap
    assert "for prohibited_group in gpio dialout nodered; do" in bootstrap
    assert 'grep -Fx "$prohibited_group"' in bootstrap
    assert "freezeprotect-commission ALL=(root) NOPASSWD:" in sudoers
    assert "freezeprotect ALL=(root) NOPASSWD:" not in sudoers


def test_commissioning_ssh_policy_is_key_only_and_disables_forwarding() -> None:
    """Catch password or forwarding paths that bypass the workstation-key boundary."""
    ssh_policy = (
        ROOT / "deployment/workstation-codex/60-freezeprotect-commission.conf"
    ).read_text(encoding="utf-8")

    assert ssh_policy.splitlines()[0] == "DenyUsers freezeprotect"
    assert (
        ssh_policy.splitlines()[1]
        == "AllowUsers freezeprotect-commission@192.168.114.0/24"
    )
    assert (
        ssh_policy.splitlines()[2]
        == "Match User freezeprotect-commission Address 192.168.114.0/24"
    )
    assert ssh_policy.splitlines()[-1] == "Match all"
    for setting in (
        "PasswordAuthentication no",
        "KbdInteractiveAuthentication no",
        "AuthenticationMethods publickey",
        "ForceCommand /usr/local/lib/freeze-protect-commission/ssh-dispatch",
        "AllowTcpForwarding no",
        "AllowStreamLocalForwarding no",
        "AllowAgentForwarding no",
        "X11Forwarding no",
        "PermitTunnel no",
        "PermitTTY no",
        "GatewayPorts no",
        "PermitUserRC no",
        "PermitUserEnvironment no",
    ):
        assert setting in ssh_policy


@pytest.mark.parametrize(
    "original_command",
    [
        "",
        "curl http://127.0.0.1:1880/admin",
        "sudo -n /usr/local/sbin/freeze-protect-commission supply",
        "sudo -n /usr/local/sbin/freeze-protect-commission SUPPLY",
        "sudo -n /usr/local/sbin/freeze-protect-commission drain --force",
        "sudo -n /usr/local/sbin/freeze-protect-commission drain; curl http://127.0.0.1:1880/admin",
        "sudo -n /usr/local/sbin/freeze-protect-commission drain\ncurl http://127.0.0.1:1880/admin",
    ],
)
def test_commissioning_ssh_dispatcher_rejects_unapproved_remote_commands(
    original_command: str, tmp_path: Path
) -> None:
    """Catch a dispatcher that lets an SSH session call localhost services."""
    result = run_ssh_dispatcher(original_command, tmp_path)

    assert result.returncode == 64
    assert "not an allowed commissioning command" in result.stderr


def run_ssh_dispatcher(
    original_command: str, tmp_path: Path
) -> subprocess.CompletedProcess[str]:
    """Run the production dispatcher with a local stand-in for absolute sudo."""
    dispatcher_source = (
        ROOT / "deployment/workstation-codex/freeze-protect-commission-ssh-dispatch"
    )
    fake_sudo = tmp_path / "sudo"
    fake_sudo.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\"\n", encoding="utf-8")
    fake_sudo.chmod(0o755)
    dispatcher = tmp_path / "ssh-dispatch"
    dispatcher.write_text(
        dispatcher_source.read_text(encoding="utf-8").replace(
            "/usr/bin/sudo", str(fake_sudo)
        ),
        encoding="utf-8",
    )
    dispatcher.chmod(0o755)
    result = subprocess.run(
        [str(dispatcher)],
        env={**os.environ, "SSH_ORIGINAL_COMMAND": original_command},
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )

    return result


@pytest.mark.parametrize(
    ("original_command", "expected_argv"),
    [
        (
            "sudo -n /usr/local/sbin/freeze-protect-commission inventory",
            ["-n", "/usr/local/sbin/freeze-protect-commission", "inventory"],
        ),
        (
            "sudo -n /usr/local/sbin/freeze-protect-commission usb",
            ["-n", "/usr/local/sbin/freeze-protect-commission", "usb"],
        ),
        (
            "sudo -n /usr/local/sbin/freeze-protect-commission status",
            ["-n", "/usr/local/sbin/freeze-protect-commission", "status"],
        ),
        (
            "sudo -n /usr/local/sbin/freeze-protect-commission drain",
            ["-n", "/usr/local/sbin/freeze-protect-commission", "drain"],
        ),
    ],
)
def test_commissioning_ssh_dispatcher_passes_only_exact_helper_argv(
    original_command: str, expected_argv: list[str], tmp_path: Path
) -> None:
    """Catch a dispatcher that mutates or broadens a documented helper call."""
    result = run_ssh_dispatcher(original_command, tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == expected_argv


def run_commission_account_validation(
    *,
    service_uid: int,
    service_gid: int,
    nodered_uid: int,
    nodered_gid: int,
    gpio_gid: int,
    dialout_gid: int,
    commission_uid: int,
    commission_gid: int,
    commission_primary_group: str,
) -> subprocess.CompletedProcess[str]:
    """Run the bootstrap's real account validation with controlled Unix IDs."""
    bootstrap = (
        ROOT / "deployment/workstation-codex/bootstrap-freezeprotect-access.sh"
    ).read_text(encoding="utf-8")
    function_body = bootstrap.split("validate_commission_account() {\n", 1)[1].split(
        "\n}\n\n# Never migrate either identity", 1
    )[0]
    function = "validate_commission_account() {\n" + function_body + "\n}"
    script = f"""set -eu
service_account=freezeprotect
commission_account=freezeprotect-commission
nodered_account=nodered
commission_home=/home/freezeprotect-commission
id() {{
  case "$*" in
    "-u freezeprotect") printf '%s\\n' {service_uid} ;;
    "-g freezeprotect") printf '%s\\n' {service_gid} ;;
    "-u nodered") printf '%s\\n' {nodered_uid} ;;
    "-g nodered") printf '%s\\n' {nodered_gid} ;;
    "-g gpio") printf '%s\\n' {gpio_gid} ;;
    "-g dialout") printf '%s\\n' {dialout_gid} ;;
    "-u freezeprotect-commission") printf '%s\\n' {commission_uid} ;;
    "-g freezeprotect-commission") printf '%s\\n' {commission_gid} ;;
    "-gn freezeprotect-commission") printf '%s\\n' {shlex.quote(commission_primary_group)} ;;
    "-nG freezeprotect-commission") printf '%s\\n' {shlex.quote(commission_primary_group)} ;;
    *) return 99 ;;
  esac
}}
getent() {{
  case "$*" in
    "group gpio") printf '%s\\n' 'gpio:x:{gpio_gid}:' ;;
    "group dialout") printf '%s\\n' 'dialout:x:{dialout_gid}:' ;;
    "group nodered") printf '%s\\n' 'nodered:x:{nodered_gid}:' ;;
    "passwd freezeprotect-commission")
      printf '%s\\n' 'freezeprotect-commission:x:{commission_uid}:{commission_gid}::/home/freezeprotect-commission:/bin/bash'
      ;;
    *) return 99 ;;
  esac
}}
service_uid=$(id -u "$service_account")
service_gid=$(id -g "$service_account")
nodered_uid=$(id -u "$nodered_account")
nodered_gid=$(id -g "$nodered_account")
{function}
validate_commission_account
"""
    return subprocess.run(
        ["/bin/sh", "-s"],
        input=script,
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )


def test_bootstrap_rejects_commissioning_uid_shared_with_service() -> None:
    """Catch a login identity that can read the service account's data."""
    result = run_commission_account_validation(
        service_uid=900,
        service_gid=900,
        nodered_uid=901,
        nodered_gid=901,
        gpio_gid=902,
        dialout_gid=903,
        commission_uid=900,
        commission_gid=902,
        commission_primary_group="freezeprotect-commission",
    )

    assert result.returncode != 0
    assert "must have a dedicated UID" in result.stderr


def test_bootstrap_rejects_commissioning_group_shared_with_nodered() -> None:
    """Catch a login identity that can write to the paired-GPIO socket."""
    result = run_commission_account_validation(
        service_uid=900,
        service_gid=900,
        nodered_uid=901,
        nodered_gid=901,
        gpio_gid=902,
        dialout_gid=903,
        commission_uid=902,
        commission_gid=901,
        commission_primary_group="nodered",
    )

    assert result.returncode != 0
    assert "must have a dedicated primary group" in result.stderr


@pytest.mark.parametrize(
    ("device_group", "device_gid"),
    [("gpio", 902), ("dialout", 903)],
)
def test_bootstrap_rejects_commissioning_gid_shared_with_device_group(
    device_group: str, device_gid: int
) -> None:
    """Catch a group-name alias that restores direct device access."""
    result = run_commission_account_validation(
        service_uid=900,
        service_gid=900,
        nodered_uid=901,
        nodered_gid=901,
        gpio_gid=902,
        dialout_gid=903,
        commission_uid=904,
        commission_gid=device_gid,
        commission_primary_group="freezeprotect-commission",
    )

    assert result.returncode != 0, device_group
    assert f"must not share its numeric GID with {device_group}" in result.stderr


def test_bootstrap_installs_and_validates_the_commissioning_ssh_policy() -> None:
    """Catch a bootstrap that creates a key but leaves password SSH enabled."""
    bootstrap = (
        ROOT / "deployment/workstation-codex/bootstrap-freezeprotect-access.sh"
    ).read_text(encoding="utf-8")

    assert (
        "sshd_policy_source=$script_dir/60-freezeprotect-commission.conf" in bootstrap
    )
    assert (
        "ssh_dispatch_source=$script_dir/freeze-protect-commission-ssh-dispatch"
        in bootstrap
    )
    assert 'install -o root -g root -m 0644 "$sshd_policy_source"' in bootstrap
    assert 'install -o root -g root -m 0755 "$ssh_dispatch_source"' in bootstrap
    assert "/etc/ssh/sshd_config.d/60-freezeprotect-commission.conf" in bootstrap
    assert "sshd -t -f /etc/ssh/sshd_config" in bootstrap
    assert (
        "sshd -T -f /etc/ssh/sshd_config -C user=freezeprotect-commission" in bootstrap
    )
    for setting in (
        "passwordauthentication no",
        "kbdinteractiveauthentication no",
        "authenticationmethods publickey",
        "forcecommand /usr/local/lib/freeze-protect-commission/ssh-dispatch",
        "allowtcpforwarding no",
        "allowstreamlocalforwarding no",
        "allowagentforwarding no",
        "x11forwarding no",
        "permittunnel no",
        "permittty no",
        "gatewayports no",
        "permituserrc no",
        "permituserenvironment no",
    ):
        assert f"'{setting}'" in bootstrap
    assert "-C user=freezeprotect,host=localhost,addr=192.168.114.1" in bootstrap
    assert "'denyusers freezeprotect'" in bootstrap
    assert "'allowusers freezeprotect-commission@192.168.114.0/24'" in bootstrap


def test_bootstrap_activates_ssh_policy_before_granting_remote_access() -> None:
    """Catch a bootstrap failure that leaves a newly installed key unrestricted."""
    bootstrap = (
        ROOT / "deployment/workstation-codex/bootstrap-freezeprotect-access.sh"
    ).read_text(encoding="utf-8")

    policy_install = bootstrap.index(
        'install -o root -g root -m 0644 "$sshd_policy_source"'
    )
    ssh_reload = bootstrap.index("systemctl reload ssh.service")
    sudoers_install = bootstrap.index(
        'install -o root -g root -m 0440 "$sudoers_source"'
    )
    key_install = bootstrap.index(
        'install -o root -g "$commission_primary_group" -m 0640 "$key_snapshot"'
    )

    assert policy_install < ssh_reload < sudoers_install < key_install


def test_node_red_editor_requires_trusted_local_console() -> None:
    """Catch documentation that asks the command-only account to open a tunnel."""
    guide = (ROOT / "deployment/COMMISSIONING.md").read_text(encoding="utf-8")

    assert "through that SSH tunnel" not in guide
    assert "trusted local Pi console" in guide


def test_helper_execution_path_excludes_unvalidated_usr_local_bin() -> None:
    """Catch a writable /usr/local/bin shadowing a root helper dependency."""
    helper = (
        ROOT / "deployment/workstation-codex/freeze-protect-commission"
    ).read_text(encoding="utf-8")
    bootstrap = (
        ROOT / "deployment/workstation-codex/bootstrap-freezeprotect-access.sh"
    ).read_text(encoding="utf-8")

    assert "PATH=/usr/sbin:/usr/bin" in helper
    assert "PATH=/usr/sbin:/usr/bin" in bootstrap
    assert "require_root_protected /usr/local/bin" in bootstrap
    assert "require_root_protected /usr/bin" in bootstrap
    assert "require_root_protected /usr/sbin" in bootstrap


def test_guide_provisions_secrets_and_captures_exactly_one_serial_device() -> None:
    """Catch an upload path that uses an empty port or tries to build without secrets."""
    guide = (ROOT / "deployment/WORKSTATION_CODEX_COMMISSIONING.md").read_text(
        encoding="utf-8"
    )

    assert "freezeprotect-commission@<Pi-LAN-IP>" in guide
    assert "cp include/secrets.example.h include/secrets.h" in guide
    assert "serial_device=$(find /dev/serial/by-id -maxdepth 1 -type l -print)" in guide
    pi_usb = guide.split("### USB cable on the Pi", 1)[1]
    assert "trusted-console-only" in pi_usb
    assert "freezeprotect-commission@<Pi-LAN-IP>" not in pi_usb
    assert "install -o root -g root -m 0600" in pi_usb
    assert "umask 077" in pi_usb
    assert "rm -rf .pio" in pi_usb


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
