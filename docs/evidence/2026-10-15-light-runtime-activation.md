# Independent light installation and camera forwarding — 2026-10-15

## Evidence and current scope

Owner supplied successful trusted-console receipt `LIGHT_RUNTIME_INSTALLED_OFF`,
with final_off_readback=true, stage=acceptance, error_code=null. This confirms the
installer's checks; relay contacts/load behavior remain NOT_VERIFIED.

- Pi evidence: `/root/independent-light-install.34wttm51`.
- Backup: `/root/independent-light-install.34wttm51/backup`.
- ManifestSHA256:5775a540d700639f49317933a7dd21ec85ad771dd2e5f19c0d7fa894dd0bdd1f.
- Required migrated paired daemon:ef96336ec9fd299459adb4bc751aac4ef5bf7f992fb0757886e496851c73b51f.
- Original bench result remains LIGHT_LEVEL_MISMATCH; retainedON after executor
  crash/hang is OWNER_ACCEPTED, not a rewritten crash-off PASS.

A separate restricted SSH `freeze-protect-commission status` after forwarding
activation returned all three existing services active and GPIO26/HIGH,
GPIO20/HIGH. This is fresh paired readback, not physical valve-position evidence.

## Credential and TLS handoff

Owner exported only512bytes of RSA-OAEP ciphertext from the installer's fixed
provisioning export. It was decrypted directly on the VM using its existing
private recipient key; no plaintext token was printed or committed.
The Pi certificate fetched during bootstrap matched the hash inside that
trusted-console export. Subsequent HTTP requests used normal certificate/IP
verification with that certificate as the trust anchor; no Pi TLS bypass.

CertificatePEM SHA256:a715a37012b03b4f7eadcc3eda2252bbf33e43c53be4ee0180d5abf11481d857.
Auth-only probes: POST{} without token401; with camera token422. The mandatory
Event fields are absent, so these probes never call the event controller.
No valid event or ON command was synthesized.

## VM activation

Existing adapter source hash d5e2e6bb617a78134e2d161907983c1d9df281ccfcf3591d85e9ee22702173b0
and exact observe config were checked before mutation. Original config was backed
up; token and CA were stored in new user-owned0600 files under private0700dir:
`/home/danik/.config/protect-light-adapter/provisioning/camera-0_4g3ao7`.
Candidate config was parsed by the installed adapter and its Sink constructed
before atomic replacement; then only `protect-light-adapter.service` restarted.

- Mode:forward, cameraG4Pro ID6797d43f03968103e40003f1, person only.
- Endpoint:`https://192.168.114.192:8443/api/v1/lights/events/unifi`.
- User service active/running, MainPID73747, NRestarts0.
- Fresh journal19:23:08–19:23:39UTC shows successful forwarding polls, fresh0.
- Startup boundary discards historical events; normal new events may now reachPi.

This completes software installation and authenticated connection configuration.
A fresh-person/relay response, timer expiry, duplicate/manual inhibition,
connection recovery and physical acceptance remain pending. The owner was asked
to create one new person detection while both loads stay disconnected.
No claim is made yet that an event was delivered or a real lamp switched.

No source/runtime logic changed in this operational step. Prior reviewed1026-test
record remains preparation evidence; no new test run is claimed here.

## First new-person acceptance — follow-up on2026-10-15

Owner replied "je sprozen" to the requested third-relay/LED response check.
A separate fresh VM journal read confirms one admitted event at
2026-10-15T19:38:57.375132+00:00 (21:38:57 Europe/Budapest):
state=forwarding, fresh=1, accepted=1. Adapter remains active/running,
MainPID73747, NRestarts0; the120-row window contains no unavailable/error states.
Latest sampled poll19:42:38UTC has fresh0.

Result: software camera-to-Pi event acceptance VERIFIED; third-relay/LED response
OPERATOR_REPORTED. Both loads remain disconnected per the maintenance context.
This does not prove mains lamp switching or relay contact behavior under load.
Five-minute expiry with no new detections is still NOT_VERIFIED; duplicate,
manual-inhibition and recovery checks retain their previous pending status.
