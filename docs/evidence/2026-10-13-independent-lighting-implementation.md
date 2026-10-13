# Independent lighting software evidence — 2026-10-13

## Scope

Owner authorized implementation of the approved third-relay light. Work uses
`codex/independent-lighting-design` in both Pi and Dial repositories.
Source delivery is separate from installation. Existing shower relays 26/20,
Roon bridge and live device configuration were not changed.

## Pi source and checks

| Evidence | Result |
| --- | --- |
| Task 1 source | `7ddb836`, corrected by `8ee2c63` and `8425087` |
| Task 2 adapter/deployment source | `1c63837` |
| Full Python suite | 739 passed; one pre-existing Starlette deprecation warning |
| Ruff | All checks passed |
| Strict mypy | No issues in 34 source files |
| Python sdist/wheel build | Passed; development build, not a new release artifact |
| Node adapter suite | 9 passed, including exported Function execution |
| Flow inspection | 4 nodes, 0 structural issues; runtime not tested |
| Task reviews | Spec and quality approved after focused corrections |

Tests use temporary databases, fake clocks and fake GPIO/transport. They cover
AUTO hold overlap and expiry, one-hour manual inhibition, restart recovery,
durable deduplication, missing/corrupt revision records, delayed ON after OFF,
uncertain acknowledgements, bounded framing and authentication roles.
No GPIO hardware was opened. GPIO readback, when later available, still does
not prove relay contact position or lamp illumination.

## Recorded engineering decisions

- Camera hold defaults to 300 seconds; Dial timed ON uses the same hold.
  Hold and manual durations accept whole minutes from 1 to 120. Manual default
  is 60 minutes. Settings affect future actions, not active deadlines.
- Each OFF establishes an executor fence in addition to its boot generation;
  stale ON/renew requests cannot cross that fence. Maximum ON lease is 3 seconds.
- Separate durable control/settings revision watermarks prevent revision reuse
  after state corruption. Untrusted watermarks fail closed for both domains.
- Initial database creation is an explicit one-shot `--provision-new-db` action.
  Normal startup cannot silently replace lost state; recovery needs operator
  repair and credential rotation.
- UniFi ingress needs its own token, source/type allowlists and explicit
  versioned field-path profile preserving original event ID/time. No generated
  receive-time identity or unauthenticated fallback is provided.

- New native/browser/adapter suites are wired into the existing CI workflows;
  the only additional cost is CI runtime, with no deployment side effect.
- Implement the software with fake I/O while actual Protect and hardware facts
  remain activation gates; an incompatible real profile requires rework before
  installation.

Decision tradeoffs: the 1–120 minute range/shared Dial hold can be revised in
software; libgpiod requires an optional Linux dependency and verified chip;
executor fencing changes the local protocol; durable watermark recovery requires
operator repair/credential rotation; strict webhook authentication may require
an authenticated upstream adapter. These are not claims of actual Protect
compatibility or physical acceptance.

## Companion Dial

Dial source: `40c5175`, `63436b5`, and review corrections `8e6a9b8`.
The third page is capability gated; its worker has bounded jobs, separate private
credentials, no action retry and configuration/session fencing. The manual M
reminder remains visibly unknown when data becomes stale. Admin adds light
connection, mode/actions, confirmed durations and paged separate history.

New native tests cover real parser, UI, transport and asynchronous admin modules.
Existing admin, shower, playlist, weather and QGSQ/BLE suites passed. Four browser
suites passed at desktop/mobile widths with fixtures; generated assets matched.
The focused native and light browser suites passed again after the configuration
binding and status-poll starvation fixes. These tests are included in CI.

Exact `8e6a9b8` Waveshare ESP32-S3 build passed with ESP-IDF v5.5.5
(`b774170ff46c393eeb5e495ea37936038d3f4f4f`), firmware size `0x22c310`,
13% app partition free. Binary SHA256:
`5982ac20b584d33418dcb3c1cf9a2e151e5d2196ffb460afd71069a4edccd6ee`.
The artifact was not flashed. Task 3 scoped review closed both findings; whole-branch
review is the remaining software gate.

## Deployment gates

Actual Protect version, authenticated POST capability, stable event identity and
retry semantics require a sanitized observed sample. Node-RED version, external
Function modules/context settings and exact active flow require runtime capture.
The exported flow, gateway ACLs and service templates default to disabled.

The owner reports LED load maximum 20 W at 220 V. Actual board revision/jumpers,
GPIO21 mapping, driver inrush/contact suitability, NO/NC choice and power/reset/
executor failure behavior remain unverified. Installation and physical testing
need the separate commissioning procedure. This change did not connect loads,
flash a Dial, restart services, publish a release or merge a branch.
