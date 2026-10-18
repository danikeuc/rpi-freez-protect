# Lighting target inventory — 2026-10-15

## Provenance

Operator supplied the output of the read-only package
lighting-inventory-20261014-v1.tar.gz. Outer archive and inner README.md and
inventory.py checks passed. Expected archive SHA256:
4ca46df66b03556292d74b1b41b66de3585451f7d0672edb024ad675258c904f.
This is an operator-supplied receipt, not an independently repeated SSH capture.
No observation timestamp was included; the date is the conversation receipt date.
The tool does not install software, evaluate settings.js, request GPIO lines,
write output values or restart services.

## Observations

| Item | Reported result |
| --- | --- |
| Host | Raspberry Pi 4 Model B Rev 1.1 |
| Kernel | 6.18.39+rpt-rpi-v8 |
| Chip name | gpiochip0 matches |
| GPIO20 and GPIO26 | Correct line names, used=true, paired_owner=true |
| GPIO21 | Correct line name, used=false, paired_owner=false |
| node-red.service | active=true, MainPID572, user_is_nodered=true |
| Flow projection | 51 nodes;2 disabled tabs;5 enabled Function nodes |
| Lighting ingress | 0 enabled /lighting/unifi HTTP routes |
| GPIO output nodes | No enabled rpi-gpio out nodes in this projection |
| Startup journal | Node-RED5.0.7 observed; Node.js version NOT_OBSERVED |
| Startup paths | Settings, userDir and flows path match expected known paths |
| Effective runtime settings | NOT_EVALUATED |
| Physical acceptance | NOT_VERIFIED |

The GPIO consumer metadata corroborates the installed paired ownership and
shows line21 unused at this observation. It is not a reservation, electrical
level readback, contact observation or startup/release/crash trace. No enabled
rpi-gpio out nodes does not rule out other GPIO access in Function/exec/custom
nodes; this projection is not a full deployed-flow safety preflight.

The startup log is limited to500 current-boot journal lines and is explicitly
not an effective-configuration query. Node-RED5.0.7 is a journal observation,
not a newly verified running package identity. Matched paths are:
/mnt/dietpi_userdata/node-red/settings.js,
/mnt/dietpi_userdata/node-red and
/mnt/dietpi_userdata/node-red/flows.json.

## File identity checkpoint

These SHA256 values bind this receipt to the observed bytes; hashes alone do not
establish configuration compatibility or authorize replacement.

| File under /mnt/dietpi_userdata/node-red | SHA256 / result |
| --- | --- |
| flows.json | a4c0f46f9fd51f547b4e306834749672e3c4aed093f94fa92ac98e7b8dbe9f9d |
| settings.js | a4c90e51bc8c7f57bf58ef71136dc4575a74d31ca4784eeaaec417290a7e63ae |
| package.json | 63501f862d92255c70f00df4361d1ebde1816b0b54430d5f54d288667b2062dd |
| package-lock.json | 6d717013e445919f98a67f27d4ef2ebff879854f7e2d655784212862076d5352 |
| .config.projects.json | UNAVAILABLE_OR_INVALID |

UNAVAILABLE_OR_INVALID does not establish that Projects is disabled or that the
file is missing; no stronger interpretation is made.

## Remaining deployment gates

The requested inventory has been received; do not ask the operator to rerun it
without a concrete changed-baseline reason. The following facts remain open:

- Effective Node-RED settings: Function library support, memory context store,
  Projects/active flow, editor authentication and installed dependency versions.
- Actual Protect version, authenticated POST capability, original event/source/
  timestamp/type fields and retry behavior. The earlier question is still open;
  this Pi receipt contains no Protect information.
- Disconnected GPIO21 request/release/restart/crash acceptance and actual relay
  board/active-level confirmation. Installed GPIO ownership is not this test.
- Exact lighting installation/provisioning and Dial flash/acceptance, followed by
  separately bounded physical acceptance. No activation or new release is claimed.

[Read-only inventory scope](../../deployment/lighting/INVENTORY.md) and
[successful paired migration](2026-10-14-device-allow-recovery.md) remain separate.
