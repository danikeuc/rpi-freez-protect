#!/bin/sh
set -eu

PATH=/usr/sbin:/usr/bin
export PATH

service_account=freezeprotect
commission_account=freezeprotect-commission
nodered_account=nodered
commission_home=/home/freezeprotect-commission

if [ "$#" -ne 1 ]; then
  echo "usage: $0 /path/to/public-key" >&2
  exit 64
fi

public_key_file=$1

if [ "$(id -u)" -ne 0 ]; then
  echo "bootstrap must be run as root" >&2
  exit 1
fi

if [ ! -f "$public_key_file" ] || [ ! -r "$public_key_file" ]; then
  echo "public-key file must be a readable regular file: $public_key_file" >&2
  exit 66
fi

nonempty_lines=$(awk 'NF { count++ } END { print count + 0 }' "$public_key_file")
if [ "$nonempty_lines" -ne 1 ]; then
  echo "public-key file must contain exactly one nonempty line" >&2
  exit 65
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
helper_source=$script_dir/freeze-protect-commission
sudoers_source=$script_dir/freeze-protect-commission.sudoers
sshd_policy_source=$script_dir/60-freezeprotect-commission.conf
ssh_dispatch_source=$script_dir/freeze-protect-commission-ssh-dispatch
client_source=$script_dir/../node-red/paired_gpio_client.py

if [ ! -f "$helper_source" ] || [ ! -f "$sudoers_source" ] || \
   [ ! -f "$sshd_policy_source" ] || [ ! -f "$ssh_dispatch_source" ] || \
   [ ! -f "$client_source" ]; then
  echo "bootstrap assets are missing from $script_dir" >&2
  exit 66
fi

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
    if printf '%s\n' "$commission_actual_groups" | grep -Fx "$prohibited_group" >/dev/null; then
      echo "freezeprotect-commission must not have direct $prohibited_group access; remediate at the trusted local console" >&2
      exit 1
    fi
  done
  if ! { [ "$commission_uid" -ne 0 ] &&
         [ "$commission_primary_gid" -ne 0 ] &&
         [ "$commission_home_actual" = "$commission_home" ] &&
         [ "$commission_shell" = /bin/bash ] &&
         [ "$commission_actual_groups" = "$commission_expected_groups" ]; }; then
    echo "incompatible freezeprotect-commission account; remediate at the trusted local console; no automatic migration" >&2
    exit 1
  fi
}

require_root_protected() {
  path=$1
  if [ -L "$path" ] || [ ! -d "$path" ] ||
     [ "$(stat -c %u "$path")" -ne 0 ] ||
     [ "$((0$(stat -c %a "$path") & 022))" -ne 0 ]; then
    echo "unsafe root execution/key ancestor: $path; remediate at the trusted local console" >&2
    exit 1
  fi
}

# Never migrate either identity: service data and its environment stay isolated.
validate_service_account
validate_nodered_account
if id "$commission_account" >/dev/null 2>&1; then
  validate_commission_account
fi

require_root_protected /
require_root_protected /home
require_root_protected /usr
require_root_protected /usr/bin
require_root_protected /usr/sbin
require_root_protected /usr/local
require_root_protected /usr/local/bin
require_root_protected /usr/local/lib
require_root_protected /usr/local/sbin
require_root_protected /etc
require_root_protected /etc/ssh
require_root_protected /etc/sudoers.d
if [ -e /etc/ssh/sshd_config.d ]; then
  require_root_protected /etc/ssh/sshd_config.d
fi
if [ -e /usr/local/lib/freeze-protect-commission ]; then
  require_root_protected /usr/local/lib/freeze-protect-commission
fi
for path in "$commission_home" "$commission_home/.ssh" \
  "$commission_home/.ssh/authorized_keys" \
  /etc/ssh/sshd_config.d/60-freezeprotect-commission.conf \
  /usr/local/lib/freeze-protect-commission \
  /usr/local/lib/freeze-protect-commission/paired_gpio_client.py \
  /usr/local/lib/freeze-protect-commission/ssh-dispatch \
  /usr/local/sbin/freeze-protect-commission \
  /etc/sudoers.d/freeze-protect-commission; do
  if [ -L "$path" ]; then
    echo "refusing symlink installation target: $path" >&2
    exit 1
  fi
done

if ! id "$commission_account" >/dev/null 2>&1; then
  useradd --system --create-home --user-group --home-dir "$commission_home" --shell /bin/bash "$commission_account"
fi
validate_commission_account
commission_primary_gid=$(id -g "$commission_account")

# Protect the home itself: a writable parent would let the user replace .ssh.
chown root:"$commission_primary_group" "$commission_home"
chmod 0750 "$commission_home"
require_root_protected "$commission_home"
install -d -o root -g "$commission_primary_group" -m 0710 "$commission_home/.ssh"

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

install -d -o root -g root -m 0755 /etc/ssh/sshd_config.d
require_root_protected /etc/ssh/sshd_config.d
install -o root -g root -m 0644 "$sshd_policy_source" \
  /etc/ssh/sshd_config.d/60-freezeprotect-commission.conf
sshd -t -f /etc/ssh/sshd_config
effective_ssh_policy=$(sshd -T -f /etc/ssh/sshd_config -C user=freezeprotect-commission,host=localhost,addr=192.168.114.1)
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
    echo "commissioning SSH policy is ineffective: expected $expected_setting" >&2
    exit 1
  fi
done
if ! printf '%s\n' "$effective_ssh_policy" | grep -Fx 'allowusers freezeprotect-commission@192.168.114.0/24' >/dev/null; then
  echo "SSH policy does not restrict logins to the commissioning account on the private LAN" >&2
  exit 1
fi
service_ssh_policy=$(sshd -T -f /etc/ssh/sshd_config -C user=freezeprotect,host=localhost,addr=192.168.114.1)
if ! printf '%s\n' "$service_ssh_policy" | grep -Fx 'denyusers freezeprotect' >/dev/null; then
  echo "freezeprotect service account is not denied SSH access" >&2
  exit 1
fi
if systemctl is-active --quiet ssh.service; then
  systemctl reload ssh.service
elif systemctl is-active --quiet sshd.service; then
  systemctl reload sshd.service
else
  echo "SSH service is not active; validate and reload it at the trusted local console" >&2
  exit 1
fi

# The SSH policy is active before any new key or sudo grant is provisioned.
install -o root -g root -m 0440 "$sudoers_source" \
  /etc/sudoers.d/freeze-protect-commission
visudo -cf /etc/sudoers.d/freeze-protect-commission
install -o root -g "$commission_primary_group" -m 0640 "$public_key_file" \
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

echo "freezeprotect commissioning access installed"
