#!/bin/sh
set -eu

PATH=/usr/sbin:/usr/bin
export PATH

service_account=freezeprotect
commission_account=freezeprotect-commission
nodered_account=nodered
commission_home=/home/freezeprotect-commission
commission_linger_dir=/var/lib/systemd/linger
commission_runtime_dir=/run/user
commission_crontab=/usr/bin/crontab
commission_atq=/usr/bin/atq
commission_atrm=/usr/bin/atrm
commission_awk=/usr/bin/awk
key_snapshot=
commission_grant_pending=false

require_root_protected() {
  path=$1
  if [ -L "$path" ] || [ ! -d "$path" ] ||
     [ "$(stat -c %u "$path")" -ne 0 ] ||
     [ "$((0$(stat -c %a "$path") & 022))" -ne 0 ]; then
    echo "unsafe root execution/key ancestor: $path; remediate at the trusted local console" >&2
    exit 1
  fi
}

require_root_protected_ancestors() {
  path=$1
  while :; do
    require_root_protected "$path"
    if [ "$path" = / ]; then
      return
    fi
    path=$(dirname -- "$path")
  done
}

require_root_owned_file() {
  path=$1
  if [ -L "$path" ] || [ ! -f "$path" ] ||
     [ "$(stat -c %u "$path")" -ne 0 ] ||
     [ "$((0$(stat -c %a "$path") & 022))" -ne 0 ]; then
    echo "unsafe root-controlled source file: $path; remediate at the trusted local console" >&2
    exit 1
  fi
}

cleanup_key_snapshot() {
  status=$1
  trap - 0 HUP INT TERM
  if [ "$commission_grant_pending" = true ]; then
    /usr/bin/rm -f /etc/sudoers.d/freeze-protect-commission || :
    /usr/bin/rm -f "$commission_home/.ssh/authorized_keys" || :
  fi
  if [ -n "$key_snapshot" ] && [ -x /usr/bin/rm ]; then
    /usr/bin/rm -f "$key_snapshot" || :
  fi
  exit "$status"
}

revoke_legacy_commission_grants() {
  /usr/bin/rm -f /etc/sudoers.d/freeze-protect-commission
  /usr/bin/rm -f "$commission_home/.ssh/authorized_keys"
}

trap 'cleanup_key_snapshot $?' 0
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

terminate_commission_processes() {
  commission_uid=$1
  if [ ! -x /usr/bin/pgrep ] || [ ! -x /usr/bin/pkill ] || \
     [ ! -x /usr/bin/sleep ]; then
    echo "missing required process-control utility; remediate at the trusted local console" >&2
    exit 1
  fi

  commission_processes_present() {
    if /usr/bin/pgrep -u "$commission_uid" >/dev/null; then
      return 0
    else
      status=$?
    fi
    if [ "$status" -eq 1 ]; then
      return 1
    fi
    echo "could not inspect commissioning processes; remediate at the trusted local console" >&2
    exit 1
  }

  if ! commission_processes_present; then
    return
  fi
  if ! /usr/bin/pkill -TERM -u "$commission_uid"; then
    echo "could not terminate existing commissioning processes" >&2
    exit 1
  fi
  for _ in 1 2 3 4 5; do
    if ! commission_processes_present; then
      return
    fi
    /usr/bin/sleep 1
  done
  if ! /usr/bin/pkill -KILL -u "$commission_uid"; then
    echo "could not force-terminate existing commissioning processes" >&2
    exit 1
  fi
  /usr/bin/sleep 1
  if commission_processes_present; then
    echo "commissioning processes remain after termination; refusing remote grants" >&2
    exit 1
  fi
}

sshd_policy_denies_user() {
  policy=$1
  denied_user=$2
  printf '%s\n' "$policy" | "$commission_awk" -v user="$denied_user" '
    $1 == "denyusers" {
      for (field = 2; field <= NF; field++) {
        if ($field == user) {
          found = 1
        }
      }
    }
    END { exit !found }
  '
}

reload_active_ssh_service() {
  policy_name=$1
  if systemctl is-active --quiet ssh.service; then
    systemctl reload ssh.service
  elif systemctl is-active --quiet sshd.service; then
    systemctl reload sshd.service
  else
    echo "SSH service is not active; validate and reload the $policy_name policy at the trusted local console" >&2
    exit 1
  fi
}

verify_commission_user_service_state_absent() {
  commission_account=$1
  commission_uid=$2
  if [ ! -x /usr/bin/find ]; then
    echo "missing required user-service inspection utility; remediate at the trusted local console" >&2
    exit 1
  fi
  if [ -e "$commission_linger_dir" ]; then
    require_root_protected "$commission_linger_dir"
  fi
  if [ -L "$commission_linger_dir/$commission_account" ] || \
     [ -e "$commission_linger_dir/$commission_account" ]; then
    echo "commissioning-user lingering remains enabled; refusing remote grants" >&2
    exit 1
  fi
  for deferred_state_dir in \
    "$commission_home/.config/systemd/user.control" \
    "$commission_home/.config/systemd/user" \
    "$commission_home/.config/systemd/user-generators" \
    "$commission_home/.config/systemd/user-environment-generators" \
    "$commission_home/.config/environment.d" \
    "$commission_home/.local/share/systemd/user" \
    "$commission_home/.local/share/systemd/user-generators" \
    "$commission_home/.local/share/systemd/user-environment-generators" \
    "$commission_home/.local/share/systemd/environment.d" \
    "$commission_runtime_dir/$commission_uid/systemd/user.control" \
    "$commission_runtime_dir/$commission_uid/systemd/user" \
    "$commission_runtime_dir/$commission_uid/systemd/transient" \
    "$commission_runtime_dir/$commission_uid/systemd/generator" \
    "$commission_runtime_dir/$commission_uid/systemd/generator.early" \
    "$commission_runtime_dir/$commission_uid/systemd/generator.late" \
    "$commission_runtime_dir/$commission_uid/systemd/user-generators" \
    "$commission_runtime_dir/$commission_uid/systemd/user-environment-generators" \
    "$commission_runtime_dir/$commission_uid/systemd/environment.d"; do
    if [ -L "$deferred_state_dir" ]; then
      echo "refusing symlinked commissioning user-service state: $deferred_state_dir" >&2
      exit 1
    fi
    if [ -e "$deferred_state_dir" ] && [ ! -d "$deferred_state_dir" ]; then
      echo "invalid commissioning user-service state: $deferred_state_dir" >&2
      exit 1
    fi
    if [ -d "$deferred_state_dir" ]; then
      if ! deferred_state_entry=$(/usr/bin/find "$deferred_state_dir" -mindepth 1 -print -quit); then
        echo "could not inspect commissioning user-service state" >&2
        exit 1
      fi
      if [ -n "$deferred_state_entry" ]; then
        echo "commissioning user-service state must be cleared at the trusted local console" >&2
        exit 1
      fi
    fi
  done
}

require_deferred_job_tools() {
  for deferred_job_tool in "$commission_crontab" "$commission_atq" \
    "$commission_atrm" "$commission_awk"; do
    if [ ! -x "$deferred_job_tool" ]; then
      echo "missing required deferred-job utility: $deferred_job_tool" >&2
      exit 1
    fi
  done
}

commission_crontab_present() {
  commission_account=$1
  if crontab_output=$(LC_ALL=C "$commission_crontab" -u "$commission_account" -l 2>&1); then
    return 0
  else
    status=$?
  fi
  if [ "$status" -eq 1 ] && \
     [ "$crontab_output" = "no crontab for $commission_account" ]; then
    return 1
  fi
  echo "could not inspect the commissioning crontab" >&2
  exit 1
}

clear_commission_deferred_jobs() {
  commission_account=$1
  commission_uid=$2
  if [ ! -x /usr/bin/loginctl ]; then
    echo "missing required user-session utility; remediate at the trusted local console" >&2
    exit 1
  fi
  if ! /usr/bin/loginctl disable-linger "$commission_account"; then
    echo "could not disable commissioning-user lingering" >&2
    exit 1
  fi
  verify_commission_user_service_state_absent "$commission_account" "$commission_uid"
  require_deferred_job_tools

  if commission_crontab_present "$commission_account"; then
    if ! "$commission_crontab" -u "$commission_account" -r; then
      echo "could not remove the commissioning crontab" >&2
      exit 1
    fi
  fi

  if ! at_queue=$("$commission_atq"); then
    echo "could not inspect queued at jobs" >&2
    exit 1
  fi
  at_jobs=$(printf '%s\n' "$at_queue" | "$commission_awk" \
    -v user="$commission_account" '$1 ~ /^[0-9]+$/ && $NF == user { print $1 }')
  for job_id in $at_jobs; do
    if ! "$commission_atrm" "$job_id"; then
      echo "could not remove queued commissioning at job: $job_id" >&2
      exit 1
    fi
  done
  if ! at_queue=$("$commission_atq"); then
    echo "could not verify queued at jobs" >&2
    exit 1
  fi
  if printf '%s\n' "$at_queue" | "$commission_awk" \
    -v user="$commission_account" '$1 ~ /^[0-9]+$/ && $NF == user { found = 1 } END { exit !found }'; then
    echo "commissioning at jobs remain after cleanup; refusing remote grants" >&2
    exit 1
  fi
}

verify_commission_deferred_jobs_absent() {
  commission_account=$1
  require_deferred_job_tools
  if commission_crontab_present "$commission_account"; then
    echo "commissioning crontab remains after cleanup; refusing remote grants" >&2
    exit 1
  fi

  if ! at_queue=$("$commission_atq"); then
    echo "could not verify queued at jobs" >&2
    exit 1
  fi
  if printf '%s\n' "$at_queue" | "$commission_awk" \
    -v user="$commission_account" '$1 ~ /^[0-9]+$/ && $NF == user { found = 1 } END { exit !found }'; then
    echo "commissioning at jobs remain after cleanup; refusing remote grants" >&2
    exit 1
  fi
}

if [ "$#" -ne 1 ]; then
  echo "usage: $0 /path/to/public-key" >&2
  exit 64
fi

if [ "$(id -u)" -ne 0 ]; then
  echo "bootstrap must be run as root" >&2
  exit 1
fi

public_key_file=$1
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
helper_source=$script_dir/freeze-protect-commission
sudoers_source=$script_dir/freeze-protect-commission.sudoers
sshd_policy_source=$script_dir/60-freezeprotect-commission.conf
quarantine_ssh_policy_source=$script_dir/60-freezeprotect-commission-quarantine.conf
legacy_ssh_policy_target=/etc/ssh/sshd_config.d/60-freezeprotect-commission.conf
quarantine_ssh_policy_target=/etc/ssh/sshd_config.d/60-freezeprotect-commission-quarantine.conf
final_ssh_policy_target=/etc/ssh/sshd_config.d/70-freezeprotect-commission.conf
ssh_dispatch_source=$script_dir/freeze-protect-commission-ssh-dispatch
client_source=$script_dir/../node-red/paired_gpio_client.py

validate_service_account() {
  if ! id "$service_account" >/dev/null 2>&1; then
    echo "missing freezeprotect service account; install the service first at the trusted local console" >&2
    exit 1
  fi
  service_home=$(getent passwd "$service_account" | cut -d: -f6)
  service_shell=$(getent passwd "$service_account" | cut -d: -f7)
  case "$service_shell" in
    /usr/sbin/nologin|/sbin/nologin) ;;
    *)
      echo "freezeprotect must remain a non-login service account; remediate at the trusted local console" >&2
      exit 1
      ;;
  esac
  service_uid=$(id -u "$service_account")
  service_gid=$(id -g "$service_account")
  if ! { [ "$service_uid" -ne 0 ] &&
         [ "$service_gid" -ne 0 ] &&
         [ "$service_home" = /var/lib/rpi-freeze-protect ]; }; then
    echo "incompatible freezeprotect service account; remediate at the trusted local console" >&2
    exit 1
  fi
}

validate_nodered_account() {
  if ! id "$nodered_account" >/dev/null 2>&1; then
    echo "missing nodered account; install the paired GPIO service first at the trusted local console" >&2
    exit 1
  fi
  nodered_uid=$(id -u "$nodered_account")
  nodered_gid=$(id -g "$nodered_account")
  if ! { [ "$nodered_uid" -ne 0 ] && [ "$nodered_gid" -ne 0 ]; }; then
    echo "incompatible nodered account; remediate at the trusted local console" >&2
    exit 1
  fi
}

validate_commission_account() {
  commission_home_actual=$(getent passwd "$commission_account" | cut -d: -f6)
  commission_shell=$(getent passwd "$commission_account" | cut -d: -f7)
  commission_uid=$(id -u "$commission_account")
  commission_primary_gid=$(id -g "$commission_account")
  commission_primary_group=$(id -gn "$commission_account")
  commission_actual_groups=$(id -nG "$commission_account" | tr ' ' '\n' | LC_ALL=C sort -u)
  commission_expected_groups=$commission_primary_group
  if [ "$commission_primary_group" != "$commission_account" ] ||
     [ "$commission_primary_gid" -eq "$service_gid" ] ||
     [ "$commission_primary_gid" -eq "$nodered_gid" ]; then
    echo "freezeprotect-commission must have a dedicated primary group; remediate at the trusted local console" >&2
    exit 1
  fi
  if [ "$commission_uid" -eq "$service_uid" ] ||
     [ "$commission_uid" -eq "$nodered_uid" ]; then
    echo "freezeprotect-commission must have a dedicated UID; remediate at the trusted local console" >&2
    exit 1
  fi
  for prohibited_group in gpio dialout nodered; do
    if ! prohibited_group_entry=$(getent group "$prohibited_group"); then
      echo "missing required $prohibited_group group; remediate at the trusted local console" >&2
      exit 1
    fi
    prohibited_group_gid=$(printf '%s\n' "$prohibited_group_entry" | cut -d: -f3)
    case "$prohibited_group_gid" in
      ''|*[!0-9]*)
        echo "invalid $prohibited_group GID; remediate at the trusted local console" >&2
        exit 1
        ;;
    esac
    if [ "$commission_primary_gid" -eq "$prohibited_group_gid" ]; then
      echo "freezeprotect-commission must not share its numeric GID with $prohibited_group; remediate at the trusted local console" >&2
      exit 1
    fi
    if printf '%s\n' "$commission_actual_groups" | grep -Fx "$prohibited_group" >/dev/null; then
      echo "freezeprotect-commission must not have direct $prohibited_group access; remediate at the trusted local console" >&2
      exit 1
    fi
  done
  if ! { [ "$commission_uid" -ne 0 ] &&
         [ "$commission_primary_gid" -ne 0 ] &&
         [ "$commission_home_actual" = "$commission_home" ] &&
         [ "$commission_shell" = /bin/sh ] &&
         [ "$commission_actual_groups" = "$commission_expected_groups" ]; }; then
    echo "incompatible freezeprotect-commission account; remediate at the trusted local console; no automatic migration" >&2
    exit 1
  fi
}

# Validate the fixed legacy grant paths before any account identity.  This is
# deliberately limited to root-controlled paths, so a malformed account entry
# cannot redirect cleanup; after this point a failed identity check cannot
# leave the previous key or sudo grant usable.
require_root_protected /home
if [ -e "$commission_home" ]; then
  require_root_protected "$commission_home"
fi
if [ -e "$commission_home/.ssh" ]; then
  require_root_protected "$commission_home/.ssh"
fi
for path in "$commission_home/.ssh" \
  "$commission_home/.ssh/authorized_keys"; do
  if [ -L "$path" ]; then
    echo "refusing symlink legacy commissioning grant path: $path" >&2
    exit 1
  fi
done
require_root_protected /etc
require_root_protected /etc/sudoers.d
if [ -L /etc/sudoers.d/freeze-protect-commission ]; then
  echo "refusing symlink legacy commissioning sudoers grant" >&2
  exit 1
fi
revoke_legacy_commission_grants

# Validate any existing commissioning identity before using its UID in a
# signal.  This rejects UID 0 and service-account collisions before they can
# affect the administrator recovery session or the actuator service.
validate_service_account
validate_nodered_account
existing_commission_account=false
if id "$commission_account" >/dev/null 2>&1; then
  validate_commission_account
  require_root_protected /home
  require_root_protected "$commission_home"
  if [ -e "$commission_home/.ssh" ]; then
    require_root_protected "$commission_home/.ssh"
  fi
  for path in "$commission_home/.ssh" \
    "$commission_home/.ssh/authorized_keys"; do
    if [ -L "$path" ]; then
      echo "refusing symlink installation target: $path" >&2
      exit 1
    fi
  done
  existing_commission_account=true
  terminate_commission_processes "$(id -u "$commission_account")"
fi

# Validate the root-controlled quarantine asset before blocking previous
# commissioning access.  A failure before the quarantine is active leaves the
# existing SSH service untouched; a failure afterwards leaves the quarantine
# file active and the administrator's root session available for recovery.
require_root_protected_ancestors "$(dirname -- "$quarantine_ssh_policy_source")"
require_root_owned_file "$quarantine_ssh_policy_source"
require_root_protected /etc
require_root_protected /etc/ssh
if [ -e /etc/ssh/sshd_config.d ]; then
  require_root_protected /etc/ssh/sshd_config.d
fi
for ssh_policy_target in "$legacy_ssh_policy_target" \
  "$quarantine_ssh_policy_target" "$final_ssh_policy_target"; do
  if [ -L "$ssh_policy_target" ]; then
    echo "refusing symlink installation target: $ssh_policy_target" >&2
    exit 1
  fi
done

# Deny new SSH logins for both service-related identities while deployment
# cleanup and final-policy validation run.
install -d -o root -g root -m 0755 /etc/ssh/sshd_config.d
require_root_protected /etc/ssh/sshd_config.d
install -o root -g root -m 0644 "$quarantine_ssh_policy_source" \
  "$quarantine_ssh_policy_target"
sshd -t -f /etc/ssh/sshd_config
quarantine_ssh_policy=$(sshd -T -f /etc/ssh/sshd_config -C user=freezeprotect-commission,host=localhost,addr=192.168.114.1)
if ! sshd_policy_denies_user "$quarantine_ssh_policy" "$service_account" ||
   ! sshd_policy_denies_user "$quarantine_ssh_policy" "$commission_account"; then
  echo "commissioning SSH quarantine is ineffective" >&2
  exit 1
fi
reload_active_ssh_service "quarantine"

# Never migrate either identity: service data and its environment stay isolated.
require_root_protected /
require_root_protected /home
require_root_protected /usr
require_root_protected /usr/bin
require_root_protected /usr/sbin
require_root_protected /usr/local
require_root_protected /usr/local/bin
require_root_protected /usr/local/lib
require_root_protected /usr/local/sbin
require_root_protected /etc/sudoers.d
if [ -e /usr/local/lib/freeze-protect-commission ]; then
  require_root_protected /usr/local/lib/freeze-protect-commission
fi
for path in /usr/local/lib/freeze-protect-commission \
  /usr/local/lib/freeze-protect-commission/paired_gpio_client.py \
  /usr/local/lib/freeze-protect-commission/ssh-dispatch \
  /usr/local/sbin/freeze-protect-commission \
  /etc/sudoers.d/freeze-protect-commission; do
  if [ -L "$path" ]; then
    echo "refusing symlink installation target: $path" >&2
    exit 1
  fi
done

for source_asset in "$helper_source" "$sudoers_source" "$sshd_policy_source" \
  "$ssh_dispatch_source" "$client_source"; do
  require_root_protected_ancestors "$(dirname -- "$source_asset")"
  require_root_owned_file "$source_asset"
done

case "$public_key_file" in
  /*) ;;
  *)
    echo "public-key file must use an absolute, root-controlled path" >&2
    exit 66
    ;;
esac
require_root_protected_ancestors "$(dirname -- "$public_key_file")"
require_root_owned_file "$public_key_file"
key_snapshot=$(mktemp /root/freezeprotect-commission-key.XXXXXX)
install -o root -g root -m 0600 "$public_key_file" "$key_snapshot"
nonempty_lines=$(awk 'NF { count++ } END { print count + 0 }' "$key_snapshot")
if [ "$nonempty_lines" -ne 1 ]; then
  echo "public-key file must contain exactly one nonempty line" >&2
  exit 65
fi

for path in "$commission_home" "$commission_home/.ssh" \
  "$commission_home/.ssh/authorized_keys"; do
  if [ -L "$path" ]; then
    echo "refusing symlink installation target: $path" >&2
    exit 1
  fi
done
if ! id "$commission_account" >/dev/null 2>&1; then
  useradd --system --create-home --user-group --home-dir "$commission_home" --shell /bin/sh "$commission_account"
fi
validate_commission_account
commission_primary_gid=$(id -g "$commission_account")

# Protect the home itself: a writable parent would let the user replace .ssh.
chown root:"$commission_primary_group" "$commission_home"
chmod 0750 "$commission_home"
require_root_protected "$commission_home"
install -d -o root -g "$commission_primary_group" -m 0710 "$commission_home/.ssh"
# The quarantine was reloaded before this point; now that the path is
# root-controlled, remove any key from an earlier revision before cleanup.
/usr/bin/rm -f "$commission_home/.ssh/authorized_keys"

clear_commission_deferred_jobs "$commission_account" "$(id -u "$commission_account")"
terminate_commission_processes "$(id -u "$commission_account")"
verify_commission_deferred_jobs_absent "$commission_account"
verify_commission_user_service_state_absent "$commission_account" \
  "$(id -u "$commission_account")"

# This client has standard-library imports only. Do not execute a writable
# checkout as root; Python isolated mode also excludes that checkout.
install -d -o root -g root -m 0755 /usr/local/lib/freeze-protect-commission
require_root_protected /usr/local/lib/freeze-protect-commission
install -o root -g root -m 0644 "$client_source" \
  /usr/local/lib/freeze-protect-commission/paired_gpio_client.py
install -o root -g root -m 0755 "$ssh_dispatch_source" \
  /usr/local/lib/freeze-protect-commission/ssh-dispatch
install -o root -g root -m 0755 "$helper_source" \
  /usr/local/sbin/freeze-protect-commission

# Retire the legacy single-file policy while quarantine remains active, then
# prepare the final policy in a distinct file.  The old daemon keeps the
# quarantine configuration until the final reload succeeds.
/usr/bin/rm -f "$legacy_ssh_policy_target"
install -o root -g root -m 0644 "$sshd_policy_source" \
  "$final_ssh_policy_target"
sshd -t -f /etc/ssh/sshd_config
for commission_source_address in 192.168.111.30 192.168.114.1; do
  effective_ssh_policy=$(sshd -T -f /etc/ssh/sshd_config -C user=freezeprotect-commission,host=localhost,addr="$commission_source_address")
  for expected_setting in \
    'passwordauthentication no' \
    'kbdinteractiveauthentication no' \
    'authenticationmethods publickey' \
    'forcecommand /usr/local/lib/freeze-protect-commission/ssh-dispatch' \
    'allowtcpforwarding no' \
    'allowstreamlocalforwarding no' \
    'allowagentforwarding no' \
    'x11forwarding no' \
    'permittunnel no' \
    'permittty no' \
    'gatewayports no' \
    'permituserrc no' \
    'permituserenvironment no'; do
    if ! printf '%s\n' "$effective_ssh_policy" | grep -Fx "$expected_setting" >/dev/null; then
      echo "commissioning SSH policy is ineffective for $commission_source_address: expected $expected_setting" >&2
      exit 1
    fi
  done
done
service_ssh_policy=$(sshd -T -f /etc/ssh/sshd_config -C user=freezeprotect,host=localhost,addr=192.168.114.1)
if ! printf '%s\n' "$service_ssh_policy" | grep -Fx 'denyusers freezeprotect' >/dev/null; then
  echo "freezeprotect service account is not denied SSH access" >&2
  exit 1
fi

# Validate the exact post-handover configuration before replacing quarantine.
# The commissioning key and sudoers file are still absent, so even a reload
# failure cannot create new remote access for that account.
mv -f "$quarantine_ssh_policy_target" \
  "$quarantine_ssh_policy_target.disabled"
sshd -t -f /etc/ssh/sshd_config
for commission_source_address in 192.168.111.30 192.168.114.1; do
  effective_ssh_policy=$(sshd -T -f /etc/ssh/sshd_config -C user=freezeprotect-commission,host=localhost,addr="$commission_source_address")
  for expected_setting in \
    'passwordauthentication no' \
    'kbdinteractiveauthentication no' \
    'authenticationmethods publickey' \
    'forcecommand /usr/local/lib/freeze-protect-commission/ssh-dispatch' \
    'allowtcpforwarding no' \
    'allowstreamlocalforwarding no' \
    'allowagentforwarding no' \
    'x11forwarding no' \
    'permittunnel no' \
    'permittty no' \
    'gatewayports no' \
    'permituserrc no' \
    'permituserenvironment no'; do
    if ! printf '%s\n' "$effective_ssh_policy" | grep -Fx "$expected_setting" >/dev/null; then
      echo "post-handover commissioning SSH policy is ineffective for $commission_source_address: expected $expected_setting" >&2
      exit 1
    fi
  done
done
off_lan_commission_ssh_policy=$(sshd -T -f /etc/ssh/sshd_config -C user=freezeprotect-commission,host=localhost,addr=192.168.115.1)
if ! printf '%s\n' "$off_lan_commission_ssh_policy" | grep -E \
  '^denyusers .*freezeprotect-commission([ ,]|$)' >/dev/null; then
  echo "off-LAN commissioning SSH policy is ineffective" >&2
  exit 1
fi
service_ssh_policy=$(sshd -T -f /etc/ssh/sshd_config -C user=freezeprotect,host=localhost,addr=192.168.114.1)
if ! printf '%s\n' "$service_ssh_policy" | grep -Fx 'denyusers freezeprotect' >/dev/null; then
  echo "freezeprotect service account is not denied SSH access" >&2
  exit 1
fi
reload_active_ssh_service "commissioning"

# The restrictive SSH policy is active and all old grants/deferred state have
# been removed before either new remote grant is installed.
commission_grant_pending=true
install -o root -g root -m 0440 "$sudoers_source" \
  /etc/sudoers.d/freeze-protect-commission
visudo -cf /etc/sudoers.d/freeze-protect-commission
install -o root -g "$commission_primary_group" -m 0640 "$key_snapshot" \
  "$commission_home/.ssh/authorized_keys"

[ "$(stat -c %u:%g:%a "$commission_home")" = "0:$commission_primary_gid:750" ]
[ "$(stat -c %u:%g:%a "$commission_home/.ssh")" = "0:$commission_primary_gid:710" ]
[ "$(stat -c %u:%g:%a "$commission_home/.ssh/authorized_keys")" = "0:$commission_primary_gid:640" ]
runuser -u "$commission_account" -- test -r "$commission_home/.ssh/authorized_keys"
for path in "$commission_home" "$commission_home/.ssh" \
  "$commission_home/.ssh/authorized_keys"; do
  if runuser -u "$commission_account" -- test -w "$path"; then
    echo "freezeprotect-commission must not be able to replace its authorized key: $path" >&2
    exit 1
  fi
done

commission_grant_pending=false
echo "freezeprotect commissioning access installed"
