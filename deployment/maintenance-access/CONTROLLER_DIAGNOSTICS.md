# Controller diagnostics through restricted SSH

## Owner request and scope — 2026-10-18

The owner requested access that lets Codex investigate the shower and light
without repeated operator copy/paste. This package extends the existing exact
`sudo -n /usr/local/sbin/freeze-protect-maintenance status` command.
**Prepared, not activated:** root-console installation and a separate restricted
SSH check are still required before claiming this capability is available.

The added `controllers` field reports fixed loopback GETs for shower status and
up to 1000 history entries, light status and up to 300 history entries, and
categories from at most 3000 recent journal entries for six named services.
At most 60 selected events per controller are exported. Labels come from a
fixed source-derived allowlist; unknown text is replaced with UNCLASSIFIED.
Credentials remain in root-controlled local environment files. HTTP redirects
and environment proxies are disabled. No caller-supplied path, URL, command,
service, token or argument is accepted.

This grants no controller actions, fault clearing, service restarts, generic
installation or shell access. It does not change sshd, sudoers, the dispatcher,
GPIO permissions, or the existing pinned migration operations. Controller GET
handlers remain application code; their normal internal status/history handling
is not replaced by this diagnostic reader.

## Installation

Run the hash-verified package only from the existing trusted root@DietPi console.
The installer checks the exact Pi4 model and installed helper SHA256
`2697465c2d98ab3b34be8da17f145411e900dc50765f02ff3e3a51ceb326364b`,
obtains the existing maintenance lock, previews sanitized output, saves a private
backup and atomically replaces only maintenance.py, preserving ownership/mode.
It checks the existing helper command afterward. No service is restarted. On
failure it records whether replacement occurred and stops without blind rollback.
Repeated installation against a changed baseline is rejected.

The installation success receipt is not SSH acceptance. Codex must then run the
exact status command via the dedicated key and forced-command SSH account and
check the new field and helper hash; an extra argument must still be rejected.
Do not run prepare/install: those remain the older pinned GPIO migration only.

## Recovery scope

Restoring controller operation is a separate action after diagnosis. These
permissions do not bypass the fault latch or enable AUTO/relays. Hardware
acceptance and energized tests retain their existing user approval boundaries.

## Activation verified — 2026-10-18

Owner reported installation complete. Two separate restricted SSH status requests
succeeded and returned diagnostic_version1 and the exact candidate helper hash
dd390a553688b1dc208d2f871e5b3fd17d7cf5ef8cff272f23ac055bc0691a92.
The form `status extra` was independently rejected by the forced dispatcher.
Controller diagnostics are now available through the existing status command.
No shell, generic deployment/restart or actuator authority was added.
This supersedes pending-activation wording in the preparation record.
