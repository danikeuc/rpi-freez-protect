# DietPi system diagnostic review — 2026-10-18

Source: operator snapshot at 10:41:21 UTC (12:41:21 Europe/Budapest), collector v1.
Read-only system collection; no configuration/actuator writes. Snapshot is not
an exhaustive media, physical-load, or long-term network stability test.

## Findings

- Pi4B Rev1.1, Debian13, DietPi version fields10/6/2, kernel6.18.39+rpt-rpi-v8.
- Uptime38.4h; load0.45/0.70/0.77 across4 logicalCPUs: no load pressure evident.
- AvailableRAM1.157GiB of1.802GiB; swap unused. PSI unavailable, not zero pressure.
- CPU62.809C. vcgencmd mask0x0; no reported undervoltage/throttling flag in snapshot.
- Root filesystem24.40GiB available, writable, plentiful free inodes. Repeated
  paths report the same filesystem; do not count them as four separate disks.
- No failed systemd units. SSH, nginx, Node-RED, Hub, pairedGPIO and both light
  services active; NRestarts0. This does not count deliberate stop/start cycles.
- SSH/sudoers syntax checks passed; dpkg audit no findings; no reboot marker.
- Ethernetdown, WiFiup. Cumulative wlan0 counters: RXdrops2483 / RXpackets649711,
  TXdrops7, RX/TXerrors0. This does not establish current packet loss or RF quality.
- Node-RED1880 and controller APIs8000/8002 loopback-bound. Gateways8082/8443
  bound to specific addresses. Ports22/8081/3389 wildcard-bound: host listener
  scope only, not evidence of public Internet reachability or firewall policy.

## Clock is the most relevant unresolved lead

Kernel journal contained3 categorized clock-change messages. First timestamp
2026-10-16T20:15:55.003406Z, last2026-10-18T01:25:00.579785Z. The prior light
fault was observed around01:25UTC on October17. Same time-of-day supports a
periodic time-sync hypothesis, but does not prove the direction/size of the
jump or a causal link. The middle event time/raw message is not exported.

systemd-timesyncd inactive at snapshot; chrony not installed. DietPi offers
boot-only, daily, hourly and daemon modes, so inactive timesyncd is not by itself
proof time sync is broken. Actual CONFIG_NTP_MODE and NTPSynchronized pending.
Official mode reference: https://github.com/MichaIng/DietPi/blob/master/dietpi.txt

Collector v1 incorrectly combined timedatectl properties into one comma-separated
property name; it returned {}. The local collector now requests separate -p
properties with a regression test. This is a diagnostic gap, not a measured
unsynchronized clock. Original served payload/hash retained for provenance.

## Bounds

Kernel497 entries scanned; system-last24h hit3000-entry cap. No categorized
OOM/storage/service failures found in inspected windows. Full24h coverage is
NOT established. No raw journal text was exported. NetworkManager/networkd
inactive/not-found can coexist with active networking.service; not classified as
an error. Disk SMART, supply voltage measurement and physical acceptance absent.

## Next bounded check

Read timedatectl properties and CONFIG_NTP_MODE through trusted root console.
Do not force a clock step, enable a new sync daemon, restart actuator services,
or weaken clock-discontinuity detection based only on this hypothesis.

## Time-sync configuration supplied by operator

Timezone=UTC, LocalRTC=no, NTP=no, NTPSynchronized=no, CONFIG_NTP_MODE=2.
This confirms boot+daily mode. Upstream DietPi timesync code explicitly stops
systemd-timesyncd after one-shot modes (<4), so inactive/NTP=no must not be
reported as proof of a broken service. NTPSynchronized=no is not confirmation
of current synchronization and gives no numeric clock offset. UTC is a valid
server timezone and is distinct from a discontinuity in the clock.

Reference: https://github.com/MichaIng/DietPi/blob/master/dietpi/func/dietpi-timesync
(the upstream source was inspected, not the deployed script bytes).

Periodic clock correction remains an unconfirmed causal hypothesis; event
direction and offset still missing. Continuous mode4 is a possible maintenance
improvement, not applied and not a guarantee against clock steps. No NTP restart,
mode change, forced synchronization or actuator policy change was executed.
