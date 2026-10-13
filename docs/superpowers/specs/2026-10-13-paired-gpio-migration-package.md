# Paired GPIO trusted-console migration package

User authorized continuing to installation and confirmed both valve24V and
lamp mains loads disconnected in this conversation. No energizing/SUPPLY,
lighting activation, firmware, Node-RED editing, SSH permission change or release.
Use existing reviewed GPIO source and migration runbook; restricted remote helper
remains inventory/status/diagnose-pair-gpio/drain only. Operator runs package locally.

Observed: Raspberry Pi4 ModelB Rev1.1, BCM2711, kernel6.18.39+rpt-rpi-v8,
Python3.13.5 aarch64/page4096. Canonical gpiochip0 points at fe200000.gpio with
GPIO20/21/26 labels, shared DT bank7e200000, legacy gpiomem size0x1000. gpiochip4
is an alias of0; use canonical0 only. gpiod absent from system and Hubvenv.
Old daemon SHA33088ea9e6ccf8d327e226bab1602c6a2b3ba2423de7dcab408b1d06f2233d2f,
base unit SHA0ce0b112ae54783846784ccb1fb77f17748c830392deb612391047d22da840ff;
source HEADd0dfeac61856e0ff716e700348be61709dc68505. Hub1.3.1 installation
receipt historical; recheck package/state before mutation. Preserve readiness dropin.

Architecture: self-contained operator package with exact daemon, reviewed helper
copy, pinned gpiod2.3.0 cp313 aarch64 wheel. Two stages: prepare isolated root-owned
0755 venv under/opt (never change Hubvenv) and validate metadata/API using canonical
chip and actual source validate_platform with NO request_lines or candidate MMIO mapping; then install
only after matching prepared receipt, exact source/unit checks, durable USER_OFF/
DRAIN, high/high, flowpreflight and all services. Dedicated venv path must be
fixed/reviewed or durably bound, secure, accessible to nodered. No apt/build from
source/unpinned network resolution. Offline pip --no-index --no-deps exactwheel.
Wheel SHA7fdc3f63a277f8ae193f0c9b565bbd48e525e94c39cd463acd7b06250bf26507.
Use a metadata-check subprocess under nodered: verifychiplabel/count andlineidentities/
unused status, actual validator, gpiod API; no line requests. Do not import candidate
from inaccessible/root stage in service identity; use a staged root-controlled
readable candidate path or pass reviewed source in subprocess stdin.

Install: protected lock/private evidence; validate bundle hashes/rootpath/host/
baseline/env/SQLite weather identity/durable useroff/settings, existing units and
unknown overrides fail closed. Existing Hubreadiness dropin must be preserved,
not rejected merely for being present. Reject any active/enabled/commissioned
lighting. Preserve all unrelated config/settings/DB/history/sourceHEAD. Back up
exact daemon/baseunit/dropins/config and supporting runtime inventory; fsync/hash
verify before service mutation. Stop Hub and establish paired DRAIN, stop pair,
confirm MainPID0/high-high, expire old request TTL; no new requests while replacing.
Atomic daemon replacement + reviewed new dropin/env/marker with exactgpiochip0
DeviceAllow and isolated interpreter. No base unit overwrite. systemd-analyze verify
and exact effective config/identity before start. Startpair, bounded readiness,
DRAIN receipt/high-high and kernel ownership checks, startHub via existing readiness
gate, verifyUSER_OFF/status/services/preservedfiles/settings/history.

Failure: stop on firstfailed receipt/readback, no actuation retry or automatic
rollback; report phase/safe nonsecretcode and private evidence path. After any
cutover failure keep Hub stopped, attempt DRAIN only when ownerrunning and no
prior receipt/readback failure. No claims from cleanup alone. Keep paired process
ownership if healthy; no indiscriminatekill. Preserve backup/private diagnostics.
Rollback instructions disable lighting first and restore only reviewed paired
assets with loads disconnected; no automated database restore or legacyflows.

Tests must prove stageboundaries, unknownhost/alias/dependencies/baseline/active
light/nonuseroff/malformedreceipt failures before mutation, durability/partial
replacement failures and lifecycle order, no candidateconstructors during prepare,
secretfree stdout. Actual Pi prepare/install are operator-run, pending receipts.

## Review clarification

The metadata-only preparation prohibition covers candidate GPIO owner creation,
line requests, register mapping and writes. The separately required current
HIGH/HIGH observation uses the existing documented read-only `pinctrl get`
checks. That tool may map registers internally to read status; this is not a
claim that no process reads MMIO during preparation. No direction or output
change is authorized in prepare.
