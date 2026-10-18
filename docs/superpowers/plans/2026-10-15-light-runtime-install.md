# Independent light runtime installation

Goal: reviewed root-console package installs a separate light controller/GPIO21
executor, initial OFF, private credentials and HTTPS camera-only ingress without
modifying the shower application, Node-RED or existing gateway routes. Owner
accepted retained light ON after executor death/hang; no watchdog is required.
Both loads remain disconnected by current confirmation. Scope is preparation;
operator installation is necessary because SSH helper cannot install this package.

Execution: Superpowers subagent-driven development, focused implementer plus
independent review. Existing isolated worktree codex/independent-lighting-design.

## Fixed interfaces

- Package root has manifest.json mapping every payload member to SHA256,
  wheelhouse/*.whl, runtime-install.lock (pip hashes), operator_checks.py,
  install_light.py, light-controller.service, light-gpio.service,
  light-camera.conf, wait_executor.py, recipient-public.pem and README.
- Separate distribution rpi-freeze-protect-light1.0.0 installs only parent
  freeze_protect/__init__.py and unchanged freeze_protect/lighting/*.py.
  Pinned Python3.13/aarch64 binary wheels; no dependency on Hub/spidev package.
- Fixed target /opt/independent-light, venv /opt/independent-light/venv;
  account/group independent-light, no login, no supplementary GPIO group.
- Executor needs gpiochip0 through reviewed DeviceAllow plus narrowly scoped
  udev? DO NOT change device ownership/groups: use service SupplementaryGroups=gpio
  only for executor; account itself remains without supplementary membership.
  Controller PrivateDevices=true, no supplementary GPIO group.
- Controller env root0600 /etc/independent-light/controller.env has three new
  distinct64-character tokens, allowlist6797d43f03968103e40003f1, database
  /var/lib/independent-light/independent-light.db, socket
  /run/independent-light/executor.sock. Executor env root0600 has only GPIO/socket.
- Services loaded from fixed files in package; only light units started/enabled.
  Executor ExecStartPost waits up to12seconds for its socket before controller startup;
  RuntimeDirectoryPreserve=no handles stale
  socket cleanup on unit stop. Automatic restart is operational recovery only.
- HTTPS camera-only endpoint192.168.114.192:8443 at exact path
  /api/v1/lights/events/unifi proxies loopback8002. All other paths404,
  methodPOST only, body4096, timeouts finite, no access log/token logging.
  Self-signed certificate SAN IP192.168.114.192 generated onPi; VM pins this cert
  as its trust anchor. No TLS bypass. Existing port8081 remains untouched.
- Camera token handoff encrypts JSON with token,endpoint,CA SHA256 using bundled
  RSA4096 public key and openssl pkeyutl OAEP SHA256. CA certificate is public.
  Never print plaintext controller.env or camera token. Export transport mechanism
  is a later separate step; adapter stays observe meanwhile.

## Task1: runtime package/units (parent)
Build isolated light-only wheel and offline dependency lock; fixed units and
nginx HTTPS file, VM recipient public key. Test layout/import requirements and
systemd/nginx syntax where available. No target mutations for packaging.
Include only packages needed by light module, keeping wheelhouse offline/reproducible.

## Task2: operator installer (fresh implementer)
Create deployment/lighting/install/install_light.py and tests.
Preflight exact Pi4, root, aarch64Python3.13, manifest allfixedsafe members,
fresh paired hash ef96336ec9fd299459adb4bc751aac4ef5bf7f992fb0757886e496851c73b51f,
authenticated+durable USER_OFF, pairHIGH, active migratedowner20/26,21free,
bench receipt resultLIGHT_LEVEL_MISMATCH with first bad phasecrash_release and
finalOFF true. No missing/changed/untrusted prerequisites.
Require all new target paths/units/account absent and8002/8443unused; stop safely
on partial previous installation. Private backup/checkpoint before any mutation.
Create dedicated account dirs/venv, offline pip with require-hashes; provision
new database asuser, private env/tls, installonly lightunits and additive nginx
site. nginx -t before reload. ActivateGPIO21 only after exact preflight,
initialOFF; noON commands. Observe authenticated status and GPIO21HIGH with pair
unchanged before success. On failure no blindretry/rollback, fixedsanitizederror,
stoponly newlightservices ifstarted and verify/readbackOFF ifpossible. Do not
claim OFF unless readback supports it; preserveevidence. No permissionwidening
for commissioningSSH. Installer prints summary/backup/hash, no secrets.

## Task3: review/package/handoff (parent+fresh reviewer)
Run focusedred/green, fullpytest/ruff, reviewcontracts/mutations/credentialhandling.
Package immutablefileswithSHA, verify actualHTTPdownload. One rootconsoleblock.
Operatorreceipt then freshrestrictedstatus acceptance asavailable; complete
forwarding/credentialtransfer only after targetinstallation evidence.

## Rulings
- Light-onlydistribution avoids installing/uninstallingHub dependencies.
- No repeat rawreleasebench; requirement changed, originalreceiptretained.
- TLSroute is camera-only; ESPdisplay credential/provisioning is a later distinct
  step, never expose settings/displayroles through this camera route.
- No guaranteedcrashcutoff; normalcontrollerlease andOFF remainimplemented.
