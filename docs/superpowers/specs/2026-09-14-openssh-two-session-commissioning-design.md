# OpenSSH two-session commissioning handover

## Decision

DietPi runs OpenSSH on port 22. Commissioning therefore uses two independent
Windows SSH sessions instead of trying to stop the SSH daemon or requiring a
physical console:

1. Keep the existing `root@192.168.114.192` session open as the administrator
   recovery path.
2. Bootstrap reloads a root-owned `DenyUsers` quarantine for only
   `freezeprotect` and `freezeprotect-commission`.
3. While quarantine is active, it revokes old commissioning grants, drains
   old account processes, and rejects deferred user state.
4. It installs and validates the final policy at
   `/etc/ssh/sshd_config.d/70-freezeprotect-commission.conf`.
5. It disables the separate quarantine file, validates the resulting OpenSSH
   configuration, and reloads the active OpenSSH service.
6. Only then does it install the new root-owned key and narrow sudoers file.
7. A second Windows PowerShell session verifies the restricted `inventory`
   command before the root recovery session may be closed.

## Failure contract

- Before quarantine reload, bootstrap leaves existing SSH untouched.
- After quarantine reload, any cleanup or validation failure leaves the
  commissioning identities denied and never stops the administrator's SSH
  service.
- A failed final reload leaves the currently running quarantined daemon active;
  the new key and sudoers grant have not yet been installed.
- No GPIO, firmware, ESP32, valve, water, or 24 V operation belongs to this
  handover.
