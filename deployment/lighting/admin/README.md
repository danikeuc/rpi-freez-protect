# Light admin connection — trusted-console installation

This additive deployment connects the already implemented Waveshare Luč admin
section to the installed independent light controller. Delivery task: roon-knob
issue15. The owner requested installation on2026-10-15.

## Prerequisites

- Keep both loads disconnected under the existing maintenance window.
- Pi192.168.114.192, RaspberryPi4BRev1.1, migrated paired daemon with pinned hash.
- Light runtime/controller and camera HTTPS8443 already installed and healthy.
- Reviewed lighting firmware installed on Dial192.168.114.173; PIN already set.
- Run the verified package only from an interactive root@DietPi console.

The existing limited SSH account does not authorize this installer. No widening
of SSH permissions, actuator request, controller restart, token rotation or
shower/camera configuration change is included.

## Transport and scope

The reviewed Dial client supports HTTP on the private LAN. Add a separate
light-only8082 listener restricted to the exact Dial and Pi addresses. This
preserves shower8081 and cameraHTTPS8443. Four exact routes forward to loopback
8002: status/actions/settings/history; controller authorization still separates
display and settings roles. No camera-event route is exposed on8082.

This retains the existing private-LAN HTTP trust model; it is not TLS. Do not
publish this port or change the Dial address without reviewing the gateway and
provisioning target together. Camera transport keeps its verified TLS identity.

## Operation

`python3 -I -B install_admin.py --loads-disconnected`

Enter the existing Dial PIN only in the local hidden terminal prompt. The script
reads root-only existing credentials, logs in without following redirects, and
refuses an existing configured light connection. It checks health, records a
private baseline, adds the site, validates nginx, reloads nginx, and verifies
read routes and missing-token rejection. It sends the two existing light roles
to the authenticated Dial config endpoint exactly once, then checks status,
settings and history through the Dial. No values of tokens, PIN or session
cookies are printed. It logs out afterwards.

Success is `LIGHT_ADMIN_CONNECTED`; this confirms connectivity/readback, not
physical load behavior. The durable receipt is in `/root/light-admin-install.*`.
`/root/light-admin-install.started` prevents an automatic repeated installation.
Any failure stops without retry or rollback. Preserve the receipt and inspect
the phase before deciding recovery; do not remove markers and blindly rerun.

## Verification

Unit tests cover source-gated routes, preservation of an existing connection,
redirect rejection, one-attempt timeout handling, sanitized HTTP errors, and
private PIN entry. Fresh deployment evidence is separate from software tests.
