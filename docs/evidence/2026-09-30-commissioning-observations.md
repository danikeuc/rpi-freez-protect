# Commissioning observations — 2026-09-30

## Evidence handling

This record preserves the non-secret output and operator statements supplied in
the supervised commissioning conversation on 2026-09-30. It was transcribed
into the repository during reconciliation; it is not a machine-generated
attestation and was not recollected from the live host. Token values, private
keys and unrestricted service logs are intentionally absent.

Observed Pi address: `192.168.114.192`. Exact times are included only where the
operator supplied them. Facts without a time are dated 2026-09-30.

## Raspberry Pi observations

The operator supplied these source/configuration results:

```text
Pi checkout: dab832f4dd98095db8e68d2189d7f159abc93183
FREEZE_PROTECT_CONTROL_MODE=manual_timed
```

Repository reconciliation later established that the checkout tree is exactly
equal to merged `rpi-freez-protect` commit
`b861c0a67dd484264dc810aa5b7525c18731736c`.

The operator supplied these runtime results:

```text
freeze-protect.service: active
freeze-protect-pair-gpio.service: active
node-red.service: active
nodered.service: disabled / inactive
GET http://127.0.0.1:8000/health:
{"service":"ok","state":"MANUAL_DRAIN"}
```

The authenticated display status was:

```json
{"mode":"manual_timed","command":"DRAIN","remaining_seconds":0,"state":"MANUAL_DRAIN","reason":"manual_idle","forecast":{"available":false,"fresh":false,"dates":[],"minima_c":[]},"timed_shower_deadline":null,"action":"TIMED_SHOWER","action_enabled":true}
```

The active Node-RED flow preflight exited zero and reported:

```text
Preflight passed: no active legacy GPIO 26/20 or /trigger paths; one paired bridge route is active.
```

The supplied listener/configuration evidence showed Node-RED on
`127.0.0.1:1880`, Nginx on port `8081`, and three Nginx display locations:
status, timed-shower and drain. An unauthenticated display request returned 401;
an unexposed route returned 404. Exact Node-RED/Node.js versions, palette
versions and installed settings hashes were not supplied.

## Disconnected GPIO sequence

The operator stated that 24 V valve power was disconnected. That statement was
not backed by an electrical measurement. The following timestamped Pi readbacks
were supplied:

```text
2026-09-30T13:56:18+00:00
GPIO26 output/high
GPIO20 output/high

2026-09-30T13:57:47+00:00
GPIO26 output/low
GPIO20 output/low

2026-09-30T13:58:34+00:00
GPIO26 output/high
GPIO20 output/high
```

The middle readback occurred during the approved timed `SUPPLY` action; the last
readback followed `DRAIN`. These observations prove paired software output
levels only. Relay contacts, valve movement and plumbing paths were not
observed.

## Waveshare and Roon observations

The operator reported volume response and the sequence `playing` → `paused` →
`playing`, then stated that the dial appeared to work. No protocol trace or Roon
zone identifier was retained.

Cross-repository revisions recorded during the release work:

- `roon-control`: `f0e5138d57f07899b307d75778ad7da14ab1b274`
- `roon-knob`: `8acbd418b599886d7c3442c2f674c1ee084359a5`
- release: [`v2.7.0-alpha.6`](https://github.com/danikeuc/roon-knob/releases/tag/v2.7.0-alpha.6)

Recorded release artifact hashes:

```text
application image: 0bfc90c60c8aa5a19cb772452be03451a2d5200dddacfd9056fd9586b36a574a
merged image:      cd00abed1b967cb0d46766d4aa959f70397d1e06bddf1f1f77e5dd27d244d766
```

The source release identified itself as `2.7.0-alpha.6`, but the release image
was not observed being flashed. The hardware-tested development image was
recorded separately:

```text
ESP32-S3 MAC: d0:cf:13:1e:15:44
firmware SHA-256: 66624aa234280d68ffc0192b73b42ed317ba963836bab5456d6dfecbc3fbb6ad
```

Accordingly, the operator-observed Roon/valve UI behavior applies to that
development image unless a later flash record ties the device to the release.

## Repository reconciliation

The `rpi-freez-protect` base and feature commits resolve to the same source tree:

```text
b861c0a67dd484264dc810aa5b7525c18731736c^{tree}
6ce434e37f0da8fc408f283163ba10835114779f

dab832f4dd98095db8e68d2189d7f159abc93183^{tree}
6ce434e37f0da8fc408f283163ba10835114779f
```

This equality does not prove that copied root-owned files, packages or running
processes match the checkout.
