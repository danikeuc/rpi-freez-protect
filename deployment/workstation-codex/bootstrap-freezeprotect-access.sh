#!/bin/sh
set -eu

PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH

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
client_source=$script_dir/../node-red/paired_gpio_client.py

if [ ! -f "$helper_source" ] || [ ! -f "$sudoers_source" ] || [ ! -f "$client_source" ]; then
  echo "bootstrap assets are missing from $script_dir" >&2
  exit 66
fi

for required_group in dialout gpio; do
  if ! getent group "$required_group" >/dev/null; then
    echo "required group does not exist: $required_group" >&2
    exit 1
  fi
done

validate_account_profile() {
  account_home=$(getent passwd freezeprotect | cut -d: -f6)
  account_shell=$(getent passwd freezeprotect | cut -d: -f7)
  primary_group=$(id -gn freezeprotect)
  actual_groups=$(id -nG freezeprotect | tr ' ' '\n' | LC_ALL=C sort -u)
  expected_groups=$(printf '%s\n' "$primary_group" dialout gpio | LC_ALL=C sort -u)
  if ! { [ "$(id -u freezeprotect)" -ne 0 ] &&
         [ "$(id -g freezeprotect)" -ne 0 ] &&
         [ "$account_home" = /home/freezeprotect ] &&
         [ "$account_shell" = /bin/bash ] &&
         [ "$actual_groups" = "$expected_groups" ]; }; then
    echo "incompatible freezeprotect account; stop and remediate home, shell and groups at the trusted local console; no automatic migration" >&2
    exit 1
  fi
}

# Never change keys/groups for an incompatible pre-existing service account.
if id freezeprotect >/dev/null 2>&1; then
  validate_account_profile
fi

require_root_protected() {
  path=$1
  if [ -L "$path" ] || [ ! -d "$path" ] ||
     [ "$(stat -c %u "$path")" -ne 0 ] ||
     [ "$((0$(stat -c %a "$path") & 022))" -ne 0 ]; then
    echo "unsafe root execution/key ancestor: $path; remediate at the trusted local console" >&2
    exit 1
  fi
}

require_root_protected /
require_root_protected /home
require_root_protected /usr
require_root_protected /usr/local
require_root_protected /usr/local/lib
require_root_protected /usr/local/sbin
require_root_protected /etc
require_root_protected /etc/sudoers.d
if [ -e /usr/local/lib/freeze-protect-commission ]; then
  require_root_protected /usr/local/lib/freeze-protect-commission
fi
for path in /home/freezeprotect /home/freezeprotect/.ssh \
  /home/freezeprotect/.ssh/authorized_keys \
  /usr/local/lib/freeze-protect-commission \
  /usr/local/lib/freeze-protect-commission/paired_gpio_client.py \
  /usr/local/sbin/freeze-protect-commission \
  /etc/sudoers.d/freeze-protect-commission; do
  if [ -L "$path" ]; then
    echo "refusing symlink installation target: $path" >&2
    exit 1
  fi
done

if ! id freezeprotect >/dev/null 2>&1; then
  useradd --system --create-home --user-group \
    --home-dir /home/freezeprotect --shell /bin/bash --groups dialout,gpio freezeprotect
fi
validate_account_profile
primary_gid=$(id -g freezeprotect)

# Protect the home itself: a writable parent would let the user replace .ssh.
chown root:"$primary_group" /home/freezeprotect
chmod 0750 /home/freezeprotect
require_root_protected /home/freezeprotect
install -d -o root -g "$primary_group" -m 0710 /home/freezeprotect/.ssh
install -o root -g "$primary_group" -m 0640 "$public_key_file" \
  /home/freezeprotect/.ssh/authorized_keys

# This client has standard-library imports only. Do not execute a writable
# firmware checkout as root; Python isolated mode also excludes that checkout.
install -d -o root -g root -m 0755 /usr/local/lib/freeze-protect-commission
require_root_protected /usr/local/lib/freeze-protect-commission
install -o root -g root -m 0644 "$client_source" \
  /usr/local/lib/freeze-protect-commission/paired_gpio_client.py
install -o root -g root -m 0755 "$helper_source" \
  /usr/local/sbin/freeze-protect-commission
install -o root -g root -m 0440 "$sudoers_source" \
  /etc/sudoers.d/freeze-protect-commission
visudo -cf /etc/sudoers.d/freeze-protect-commission

[ "$(stat -c %u:%g:%a /home/freezeprotect)" = "0:$primary_gid:750" ]
[ "$(stat -c %u:%g:%a /home/freezeprotect/.ssh)" = "0:$primary_gid:710" ]
[ "$(stat -c %u:%g:%a /home/freezeprotect/.ssh/authorized_keys)" = "0:$primary_gid:640" ]
runuser -u freezeprotect -- test -r /home/freezeprotect/.ssh/authorized_keys
for path in /home/freezeprotect /home/freezeprotect/.ssh \
  /home/freezeprotect/.ssh/authorized_keys; do
  if runuser -u freezeprotect -- test -w "$path"; then
    echo "freezeprotect must not be able to replace its authorized key: $path" >&2
    exit 1
  fi
done

echo "freezeprotect access installed"
