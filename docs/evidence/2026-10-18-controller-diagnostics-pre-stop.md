# Diagnostic installer pre-stop — 2026-10-18

Operator reported backup /root/controller-fault-diagnostics.asf8pjxk and
MANUAL_OFF_TIME_REQUIRED. In the exact package this follows backup completion
and precedes stop-started.json and any service stop/source replacement. The
continuation must verify this on host before accepting the review.
Independent SSH observed healthy MANUAL_OFF/OFF with 274 seconds remaining,
shower USER_OFF/MANUAL_DRAIN. Operator renewed manual OFF; independent SSH then
observed revision77, 1698 seconds remaining, healthy OFF. No actuator commands
were sent by the assistant.

A single-use exact-attempt continuation was prepared; it preserves old evidence,
checks no stop/install/success or previous continuation occurred, unchanged
baseline/backups/environment/settings, live and durable OFF inhibition, GPIO
and active services. It requires >=600 seconds before admitting the original
installer. No SSH permission change, no automatic retry/rollback. Not installed.
1140 tests PASS and Ruff PASS. One existing Starlette deprecation warning.
