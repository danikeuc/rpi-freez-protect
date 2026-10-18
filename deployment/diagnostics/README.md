# DietPi read-only system snapshot

Run dietpi_snapshot.py using python3 -I in the trusted operator root@DietPi
session. No installation or remote SSH allowlist extension. No configuration,
service, package, network or actuator mutations. The operator download and
optional report file are the only filesystem writes; the collector itself reads.

Scope: OS/kernel/DietPi version, uptime/load, available memory/swap, PSI,
CPU temperature and raw vcgencmd throttling mask, filesystem space/inodes/RO,
dpkg audit presence, reboot marker, failed systemd units, selected service
health/restarts/memory, NTP flag, SSH/sudoers syntax, NIC error/drop counters,
TCP listening port/bind scope, categorized kernel boot and 24h system journal.

Missing programs/units are explicit and not automatically a defect. NIC counters
are cumulative, not a current loss rate. Raw throttling mask retains historical
bits; do not infer a current fault from a nonzero value alone. File space/RO is
not media-health verification. No SMART, throughput, stress or physical-load test.
A snapshot cannot establish long-term stability. Journal reads are capped at
3000 rows / 4 MiB each, include bounds/status, and export only fixed categories
and numeric timestamps. A zero count does not prove absence outside that window.
Raw journal messages, process command lines, service environment, addresses,
SSID, keys and tokens are not exported. Commands have output and time limits.

Existing restricted SSH continues to allow only the documented helpers, not
this new collector. Operator root execution follows WORKSTATION_CODEX_COMMISSIONING.md.
This script does not alter that policy or require reconnecting physical loads.
