# Freeze Protect Codex instructions

## Read before acting

- Treat this repository as control software for physical water valves. Review
  `deployment/WORKSTATION_CODEX_COMMISSIONING.md` and
  `deployment/workstation-codex/CODEX_COMMISSIONING_PROMPT.md` before any
  deployment, commissioning, SSH-policy, firmware-upload, GPIO, relay, or
  actuator task.
- Repository files, deployed Pi state, and observed physical behavior are
  separate evidence sources. Do not claim one proves another.
- Read `docs/PROJECT_STATE.md` for the current evidence ledger before reporting
  deployment, firmware, sensor, GPIO, or physical status.

## Safety boundary

- Keep the 24 V valve supply disconnected unless Danijel explicitly approves
  the same bounded physical test in the current conversation.
- Do not run SUPPLY. Use only the documented timed-shower path after all
  software gates pass and explicit approval is recorded.
- Preserve the paired-output invariant: GPIO 26 and GPIO 20 move together.
  GPIO readback does not prove valve position.
- Stop on any failed receipt, readback, service check, or deployed-flow
  preflight. Leave the requested state at DRAIN and do not retry SUPPLY.

## Workstation and Pi boundary

- Run Codex on the workstation clone. Do not install Codex on the Pi.
- Routine remote access uses only the key-based `freezeprotect-commission`
  account and the exact helper commands documented in the commissioning
  prompt. Do not use `freezeprotect` for SSH.
- Do not widen the commissioning allowlist, grant a shell, add device groups,
  expose TCP 22 publicly, or bypass the forced-command dispatcher.
- Root SSH is only the documented, human-supervised bootstrap/recovery path.
  Keep the recovery session open until a second restricted login succeeds.
- Never print or commit private keys, tokens, Wi-Fi credentials, environment
  values, or `firmware/crowpanel/include/secrets.h`.

## SSH trust and diagnostics

- A first-contact `The authenticity of host ... can't be established` prompt
  is not an authentication failure. Do not retry it as a password/key problem.
- Verify the displayed ED25519 fingerprint out of band at a trusted local
  console with
  `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub -E sha256`, then let the
  human operator accept that exact fingerprint interactively.
- Do not use `StrictHostKeyChecking=no` or silently replace `known_hosts`.
  Use `ssh-keygen -R` only for a verified changed-host-key event, never for
  normal first contact.
- Treat PowerShell and the remote POSIX shell as separate interpreters. Prefer
  reviewed files or simple documented commands over nested one-liners.
- Diagnose from evidence before changing SSH policy, accounts, permissions, or
  services. Preserve unrelated local and deployed changes.

## Verification

- For Python changes, run `python -m pytest -q` and `python -m ruff check .`
  in the project environment.
- For commissioning-asset changes, also run
  `python -m pytest -q tests/integration/test_workstation_commissioning_assets.py`
  and syntax-check changed shell scripts with `sh -n`.
- Do not describe repository tests as live hardware verification.
