# Independent light first installation —2026-10-15

Prepared, not yet installed. Target trusted **root@DietPi**, Pi192.168.114.192.
Both lamp and24V valve supplies remain disconnected. This step starts the new
light services in OFF; it does not enable camera forwarding or prove contacts.
Current restricted SSH helper cannot execute this package; use the existing
root console. Preserve failed attempt evidence and do not rerun automatically.

The package is downloaded to the parent staging directory and extracted into
its own clean subdirectory: the installer rejects unrelated package members.
LAN download was independently retrieved and SHA256-verified before handoff.
The workstation must remain available for the local download.

```sh
(
set -eu
umask 077
stage=$(mktemp -d /root/light-runtime.XXXXXXXX)
cd "$stage"
curl -fS --connect-timeout 5 --max-time 120 \
  http://192.168.111.30:8781/light-runtime-20261015.tar.gz \
  -o package.tar.gz
printf '%s  %s\n' \
  'aaadadd366c92b465eb475ba98e8becdf64d920e11f13cb926dedcdbefd923ea' \
  'package.tar.gz' | sha256sum -c -
mkdir package
tar --no-same-owner --no-same-permissions -xzf package.tar.gz -C package
cd package
sha256sum -c SHA256SUMS
/usr/bin/python3 -I -B install_light.py \
  --valves-disconnected --lamp-disconnected \
  --manifest-sha256 5775a540d700639f49317933a7dd21ec85ad771dd2e5f19c0d7fa894dd0bdd1f
)
```

Expected successful JSON field: `result=LIGHT_RUNTIME_INSTALLED_OFF`,
`final_off_readback=true`, `camera_forwarding=NOT_CONFIGURED`.
On failure, retain the JSON error_code, stage and failure_inhibition values;
do not send environment files, private logs or credentials. New activation
paths are inhibited on handled failure; installed evidence stays for review.

Private backup/export: `/root/independent-light-install.*/backup/provisioning`.
Camera credential remains RSA-OAEP-encrypted for the VM. Its transfer and
activation are separate following steps after successful installation evidence.
