# GPIO21 bench preparation — 2026-10-15

User authorized connecting MCP to the independent relay and said no lamp is
attached. Fresh restricted maintenance status confirms the migrated daemon SHA256
ef96336ec9fd299459adb4bc751aac4ef5bf7f992fb0757886e496851c73b51f,
Hub/pair/Node-RED active. A separate status read shows GPIO26 and20 both output/LOW.
Thus current paired state is SUPPLY, not the older DRAIN record. Requested operator
STOP/USER_OFF and confirmation valve24V is disconnected; responses pending.

Prepared [bounded GPIO21 bench](../../deployment/lighting/GPIO21_BENCH.md).
No GPIO writes or new Pi software installation occurred during preparation.
Existing remote helper does not authorize this new root-console operation.

Independent reviewer found missing directory fsync for the no-repeat marker.
Regression reproduced missing durable ordering; fixed by existing durable helper.
Nine focused tests pass including paired HIGH-only samples, inactive initial GPIO21
request, input failure cleanup, durable marker failure, bench failure and OFF
recovery failure reporting. Final full suite:938 tests passed, one existing Starlette/httpx deprecation
warning. Ruff passed; configured mypy passed for34 src modules; diff-check passed.

This is software preparation, not actual driver or physical acceptance. The VM
adapter remains observe-only; no forwarding credential/endpoint has been set.

## Operator prerequisites confirmed

The owner replied "urejeno" to both valve24V disconnection and Dial STOP.
A subsequent restricted SSH status read confirms GPIO26 and20 both output/HIGH,
with the three checked services active. Archive delivery was rechecked against
SHA256 cdb0d132218c5b08aba7c998bd59b8e57a6f43244a96aa097e80db9d4747f0e6.
The root-console bench has not run; it will independently require authenticated
and durable USER_OFF before GPIO21 access. No further load confirmation is needed
for this same bounded disconnected test unless the operator changes the setup.

## First disconnected hardware attempt: stopped

The operator returned a checksum-verified package receipt followed by:

```json
{"result":"LIGHT_LEVEL_MISMATCH","attempted_gpio21":true,"final_off_readback":true,"physical_acceptance":"NOT_VERIFIED","automation_enabled":false,"evidence":"/root/light-gpio21-bench.ehy6qh3b"}
```

This is a failed bench, not acceptance. The test reached GPIO21 access and its
final OFF recovery/readback completed. The receipt alone does not identify the
failing phase: startup, command, normal release and crash release all share the
same level assertion. Inspect the saved phase/pin samples before changing code or
repeating actuation. No root cause is yet confirmed, and no forwarding is enabled.
The no-repeat marker remains in place. Next action is read-only summarization of
samples.json and diagnostic.json through the trusted root console; these files
are outside the installed restricted SSH helper's read allowlist.
