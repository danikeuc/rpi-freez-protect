# Controller diagnostic access preparation — 2026-10-18

Owner requested independent diagnostics instead of copy/paste. Installed baseline verified via restricted SSH:2697465c2d98ab3b34be8da17f145411e900dc50765f02ff3e3a51ceb326364b.

Package SHA256:5ac40a9f1ce4a0c56835dd2ee40a337966792b400e059dd503a7cb83607ef09f

Candidate helper SHA256:dd390a553688b1dc208d2f871e5b3fd17d7cf5ef8cff272f23ac055bc0691a92

Full suite1068PASS; final targeted/commissioning135PASS; Ruff and diff-checkPASS. Single-file atomic update with trusted-path, exact-baseline, lock, preview, backup, replacement and postcheck tests. Fixed GET-only APIs, no redirects/proxies, literal-label output, categorized journals, rejection of unknown fields and extra args tested. No arbitrary shell, new command, restarts or actuator API added. Root-console install and second restricted SSH acceptance PENDING. Existing controller fault root cause remains under investigation.

## Activation verified — 2026-10-18

Owner reported installation complete. Two separate restricted SSH status requests
succeeded and returned diagnostic_version1 and the exact candidate helper hash
dd390a553688b1dc208d2f871e5b3fd17d7cf5ef8cff272f23ac055bc0691a92.
The form `status extra` was independently rejected by the forced dispatcher.
Controller diagnostics are now available through the existing status command.
No shell, generic deployment/restart or actuator authority was added.
This supersedes pending-activation wording in the preparation record.
