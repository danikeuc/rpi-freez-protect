# Pi weather candidate installation — 2026-10-03

## Scope and authority

The operator confirmed current valve 24 V disconnection and an open trusted Pi console. Installation ran there using the reviewed one-file operator procedure, not an expanded remote commissioning grant. The deployment retained manual_timed and disabled weather. No START/SUPPLY or physical acceptance was authorized by these steps. Node-RED, paired GPIO daemon and systemd unit contents are unchanged between the old and new source revisions.

## Artifact identities

| Item | Exact identity |
| --- | --- |
| Original checkout | `52c0815c17ecd94d4939c2995a0cced3a40be8bc` |
| Installed checkout | `d0dfeac61856e0ff716e700348be61709dc68505` |
| Python build source | `31245c1ad66491d13e36d3201bae946d1fcdefef` |
| Wheel SHA256 | `f4fd05f46ef1e860369691d57707e270e7af35569b5f97f77dcb1352d8270a3b` |
| Display gateway SHA256 | `3c9b861142d3a4fc1e5b8660dd4487b2dd6874df2773e079a6d50006cdbe9615` |
| Offline Git bundle SHA256 | `d8bb879da36651ac4046137da1f5a3efd181855752d88556f70b3695ef179355` |
| Reviewed operator script SHA256 | `36b6a1a4a871e903a0dbef9adc49ea12f5a06a973cf47e314fb9a5e4e546a252` |

The wheel filename/version 1.1.0 alone is not source attestation and must not replace an existing published v1.1.0 artifact. The source and hashes above distinguish this candidate. Published releases were not changed.

## Operator-returned execution evidence

The following evidence was returned in this conversation on 2026-10-03; the pasted receipt has no independent device timestamp. Codex did not retrieve the private archive, environment or log contents.

1. Backup: deployed-flow preflight and authenticated manual idle passed; protocol2 DRAIN returned GPIO20/26=1 with high/high readback; archive checksum and durability passed. Backup `/root/freeze-protect-before-weather.EesduvpK`; original Hub restarted MANUAL_DRAIN with three active services and paired high. Archive restore was not exercised on the Pi.
2. Staging: all three pinned checksums and Git bundle prerequisite verification passed. Stage `/root/freeze-weather-stage.zbmD8I74`.
3. Operator script download: pinned script checksum passed.
4. Final installer receipt:

```text
INSTALL_OK source=d0dfeac61856e0ff716e700348be61709dc68505 files=26 MANUAL_DRAIN weather_enabled=false weather_version=1 GPIO26=high GPIO20=high
PRIVATE_EVIDENCE=/root/freeze-weather-install-state; physical valve position NOT_VERIFIED; keep 24 V disconnected
```

The reviewed installer emits this only after exact installed-file verification, service-user readability, unchanged dependency inventory/environment/unit checks, Nginx validation/reload, direct and gateway authenticated idle/capability checks, persisted disabled weather/identity verification and explicit paired-high readback. This is evidence from the returned installer receipt, not an independent retrieval of each private check.

## Independent read-only observation

Workstation restricted-key `freezeprotect-commission` calls to `inventory` then `status`, completed by **2026-10-03 19:29:16 UTC**, both exited zero:

- Checkout: `d0dfeac61856e0ff716e700348be61709dc68505`.
- `node-red.service`, `freeze-protect-pair-gpio.service`, `freeze-protect.service`: active.
- GPIO26 and GPIO20: output/high.

Host trust, SSH policy, users/groups and commissioning allowlist were not changed. The temporary installer-delivery server was stopped after the successful result. These read-only checks do not independently prove installed wheel bytes, authenticated API fields, Nginx config, 24 V disconnection or hydraulic state.

## Procedure validation and remaining boundaries

The operator script passed syntax checks, eight focused offline tests and independent scoped review after correcting private-umask package readability and logging-failure cleanup. Offline bundle fetching was tested in a temporary clone. Temporary archive/restore tests covered sample SQLite contents, identity and file permissions. These are local test evidence, not live Pi rollback proof.

The new Pi candidate has not performed a timed shower or weather AUTO acceptance test. Bridge candidate, Dial firmware, live playlist queue replacement/first-track behavior, sustained AUTO/continuous-duty suitability, daemon-independent enforcement, reboot output timing and individual power-domain hydraulic recovery remain unverified. PT100 remains informational. Keep manual_timed/weather disabled and 24 V disconnected pending the separate bounded acceptance stages.

For rollback, retain the protected original backup and use only the reviewed deliberate rollback procedure with writers stopped. Preserve any candidate database together with its matching `.weather-identity`; do not delete an identity file to clear a fault. No rollback was executed in this installation.
