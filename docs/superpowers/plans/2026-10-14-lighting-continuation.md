# Lighting continuation and maintenance closure

Goal: finish the authorized paired migration work and prepare the remaining
independent-light deployment without pretending missing runtime/physical facts
are known. Use Superpowers executing-plans. Existing isolated worktrees stay.
Spec: ../specs/2026-10-12-independent-lighting-design.md.

## Tasks

1. Verify paired recovery through existing restricted SSH; retain failed history.
2. Provide a fixed read-only inventory for the exact Pi/Node-RED target, with
   sanitized output, no settings execution, no GPIO requests or service changes.
   Prove red/green projection, malformed data and wrong-host behavior.
3. Reconcile current operational documentation with installed migration; keep
   physical, Protect and runtime acceptance open. Run project gates and a fresh
   review of all maintenance/recovery plus inventory changes. Commit reviewed work.
4. Package the read-only inventory for one target handoff. Remaining activation
   depends on actual target/profile/physical evidence; do not relabel it complete.

## Review focus

- Restricted maintenance cannot execute arbitrary commands, paths or packages.
- Failed installation/recovery preserves original evidence; no repeated actuation.
- DeviceAllow order normalization must reject widened permissions.
- Hub readiness retries only refused GET connections while the process runs.
- Inventory does not expose secrets or turn unknown GPIO metadata into free lines.
- Source/tests, installed software and physical acceptance remain distinct.
