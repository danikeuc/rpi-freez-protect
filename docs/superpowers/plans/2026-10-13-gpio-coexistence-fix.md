# GPIO coexistence repair implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:subagent-driven-development.

**Goal:** eliminate uncoordinated FSEL2 writes while preserving paired command writes.
**Architecture:** kernel-owned directions/exclusive lines, restricted single-mask MMIO latch writes.
**Tech Stack:** Python, libgpiod >=2.3,<3, existing paired protocol2 and pytest.
**Spec:** [GPIO coexistence fix](../specs/2026-10-13-gpio-coexistence-fix.md).

## Global constraints

Software only; no hardware/deployment/merge/release. Preserve GPIO26/20 grouped
writes, lease60s and existing protocol. GPIO21 has a separate owner. No fallback
to legacy FSEL manipulation or sequential per-line command writes. Unsupported
platform or missing verified configuration fails closed before device mutation.

## Review focus

Wrong chip/platform versus gpiomem mapping; partial request/map failure and
ownership lifetime; shutdown exceptions masking cleanup; concurrent light request/
release preserving paired bits; test/documentation accidentally claiming physical
atomic initialization, crash safety or installation acceptance.

## Task1: repair paired hardware boundary and reconcile activation evidence

Files: deployment/node-red/paired_gpio_daemon.py; related paired tests; pyproject.toml
optional GPIO dependency; reviewed disabled migration unit/config example under
deployment/lighting; current lighting spec/runbook/README/evidence/PROJECT_STATE;
companion Dial operations lighting doc only (no firmware change).

- [ ] Write failing regression reproducing old FSEL lost update and requiring
  kernel-owned direction path, preserved single-mask command traces and line21
  untouched under fake concurrent kernel request/release. Test lifecycle and
  partial failures, mapping/config/unsupported rejection before writes, no fallback.
- [ ] Run RED, implement minimal kernel ownership plus guarded register backend.
  Keep real paired lease/socket regression fixtures; do not duplicate policy.
- [ ] Verify targeted GREEN, full pytest and Ruff required by AGENTS; mypy/build
  where changed package metadata requires it. No actual GPIO or fake hardware claims.
- [ ] Add explicit migration/runbook with installed-old versus source-new distinction,
  dependency/interpreter/config/device requirements, disconnected-load acceptance,
  all four fault-domain limits and rollback requiring light disabled first.
- [ ] Commit and independent task/whole-change review; fix findings and scoped
  re-review. Reconcile docs but retain physical and actual Protect acceptance gates.

## Decisions

User approval to repair the blocker permits this narrow paired hardware-boundary
change. Full replacement with gpiod set_values was rejected because reviewed
driver has no set_multiple callback. Hybrid direction ownership retains current
atomic latch mechanism, but remains BCM-specific and needs installed-driver and
physical acceptance. No deployed behavior changes are included.

Implementation ruling: exclusive AS_IS reservation precedes MMIO mapping and
one DRAIN preload, then kernel OUTPUT/HIGH reconfiguration and readback.
Supported profile intentionally covers only the verified legacy BCM gpiomem
DT binding and fails closed for absent/ambiguous sysfs mapping. The parentless
gpiomem class node is bound through its class dev number and unique
rpi-gpiomem platform instance. No installed-platform support is asserted.
