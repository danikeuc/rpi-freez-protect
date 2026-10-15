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
