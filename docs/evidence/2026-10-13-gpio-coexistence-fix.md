# Paired GPIO coexistence source repair evidence

Scope: authorized narrow repair on codex/independent-lighting-design, based on
Pi fe33abd and Dial 6a5e03e. No installed artifact, hardware, service or release
was changed. Candidate semantics and all migration gates are in the
[migration runbook](../operations/paired-gpio-migration.md).

## Finding and repair

An executable fixture using the actual old PairedGpio.configure_outputs method
and fake registers reproduced the lost update: kernel GPIO21 field became
output (1) after a userspace FSEL read, then the old full-register store
restored it to input (0). This is source-level reproduction, not an observed
electrical trace.

New production code removes all userspace FSEL reads/writes. Explicit
libgpiod>=2.3,<3 chip/profile and platform validation precedes exclusive pair
reservation. AS_IS reservation precedes mapping, one paired HIGH preload,
kernel OUTPUT/HIGH configuration and verified paired DRAIN. Only fixed
68157440-mask GPSET0/GPCLR0 stores and GPLEV0 reads are exposed. The original
protocol2, lease60s and socket/controller behavior are retained.

The mapping profile is intentionally restricted to the reviewed legacy BCM
gpiomem DT/sysfs binding. Primary driver source showed the gpiomem character
device has NULL parent; platform/class/rdev evidence is validated instead of
assuming device/of_node. No actual installed model/kernel identification or
physical startup/crash guarantee is asserted.

## Executed software checks

Initial RED: tests/integration/test_paired_gpio_ownership.py produced 18 failures
against the old daemon; its MMIO open preceded exclusive kernel ownership.
The fake kernel/MMIO boundary now checks line identities, AS_IS/OUTPUT settings,
ownership-before-map, exact command trace and light request/release interleavings,
partial request/map/configure/read/write failures, original-cause preservation,
failed unmap retention, missing dependency/config and unsupported hardware.

A second RED found the provisional validator incorrectly expected a parent on
legacy gpiomem. The realistic parentless sysfs/DT fixture failed; corrected
binding passed. Additional checks reject RP1, wrong bank/driver/compatible,
ambiguous driver, wrong character device, missing metadata and addressing;
restricted MMIO refuses configuration registers or non-pair masks.

Focused GREEN: 52 tests across ownership, paired daemon and lease protocol.
First full run: 768 passed, 2 failed. One pre-existing asset assertion interpreted
a disabled activation warning comment as an enabled assignment; the warning
was reworded while preserving its prohibition. The other failure was the
repair-evidence link before this evidence file was added. Neither failure was
a GPIO behavior regression. Follow-up final results are recorded below.
Ruff passed; strict mypy passed 34 source modules; source/wheel build passed.
The standalone deployment script is outside the repository mypy source set.
Required commissioning asset suite: 110 passed. No shell scripts changed.

## Acceptance boundary

Kernel configuration cooperates with GPIO21 only after exact installed paired
migration. Source regression checks are not driver timing or physical evidence.
Lighting remains disabled until migration and disconnected-load
startup/request/release/restart/crash traces pass, preserving legal energized
states (0,0,0),(0,0,1),(1,1,0),(1,1,1). Physical DRAIN, contact timing and all
four fault domains remain unverified as detailed in the migration runbook.
Actual Protect profile/authentication, lamp/contact/board suitability and
on-device Dial acceptance remain separate requirements.

## Initial implementation verification

After the two documented fixes: python -m pytest -q passed **770 tests** in
16.04 seconds. One existing Starlette/httpx deprecation warning remains.
python -m ruff check . and git diff --check passed. Strict mypy and package build
passed before the final documentation-only correction; no Python behavior or
package metadata changed afterwards. No deployment, hardware or firmware tests
were run. Independent review followed this initial verification; its correction and final disposition are recorded below.

## Task review correction: GPIO-REVIEW-01

Independent review found the initial validator assumed a class-style device
parent link for a GPIO bus device. A realistic direct-of_node fixture reproduced
the failure. The validator now checks the opened character identity, GPIO bus,
direct firmware node and matching structural platform parent bound to the
exact pinctrl driver. Conflicting ancestry/driver/bank metadata fails before
reservation. Parentless legacy gpiomem validation is retained.
Focused checks:60 passed. Required full suite:778 passed, one existing
Starlette/httpx warning,17.07 seconds. Ruff and whitespace checks passed.
No dependencies/package or typed src modules changed in this correction;
build/mypy were not repeated. Physical and installed migration gates remain.

## Final review and delivery disposition

Implementation commit:9088c0ce027e3876fe8deb8ab83898d7f4c09827.
Reviewed correction:44091d627fffe72f9840092996e6e1421251260f.
Companion Dial documentation:70bc5b5bebafd69ab2222178d269ba17dd991c9d.
Task scoped re-review closed GPIO-REVIEW-01; independent final integration
review passed specification, quality and integration with no remaining
actionable findings. [Durable final review](2026-10-13-gpio-coexistence-final-review.md).
Final code checks remain778 pytest and Ruff PASS, with the existing Starlette
warning; typed-src mypy34, package build and commissioning110 checks above
remain applicable. Final reconciliation changes documentation only.

Controller disposition of declined-to-judge items: installed inventory and
migration, electrical/physical/fault-domain/live recovery, actual Protect and
Dial acceptance remain mandatory pre-activation gates, not waived tests.
Unsupported platforms/privileged competing writers remain outside the supported
profile; no universal isolation claim is made. Unchanged unrelated product
behavior and optional repeated suites are not reopened for this source repair.
Prior primary-source notes used by the final reviewer are corroborated by the
controller's direct retrieval of the official gpiomem and libgpiod sources.

No hardware, installation, service activation, push, merge or release occurred.
Both development worktrees are retained for the subsequent installation work.
