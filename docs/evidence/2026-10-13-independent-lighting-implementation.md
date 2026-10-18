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
| Task reviews | Task and final scoped reviews approved for disabled source delivery |

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

- Known **GPIO_SHARED_FSEL2_COEXISTENCE** is an activation blocker: deliver
  disabled source only until separately reviewed architecture eliminates
  uncoordinated whole-register updates and regression/physical evidence exists.
  Initial service ordering and userspace locking alone do not cover kernel cleanup.
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
The artifact was not flashed. Task 3 scoped review closed its earlier findings.
Whole-branch review then identified browser settings-failure control loss and
the missing explicit shared-register activation blocker; their source fixes
and focused evidence are recorded below, with final scoped review approved for disabled source delivery.

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

## Final software fix candidate — review approved

Dial `6a5e03ed3a1b26a61536d602c697795f2444bccb` separates browser status and settings failure handling. With fresh AUTO/ON status and settings503, the original revision/freshness remain and deliberate OFF is admitted. With fresh manual status and settings503, Back to AUTO remains usable. Unknown settings clear the settings revision and both confirmed durations; timed/manual activation is gated. The original configuration/session fences and ten-second freshness bound remain in force.

Focused browser RED: `settings failure preserves fresh status revision` failed with `null !== 7` against the previous source. GREEN at1280/390 widths:

    light admin desktop/mobile: settings503 preserves fresh AUTO/ON OFF and manual BackAUTO; durations/activation gated; CSRF, private tokens, no activation on save/history, manual zero/stale, old Pi, session fences, no retries PASS

Exact final Dial commit build PASS with ESP-IDF5.5.5, firmware size0x22c400,13% partition free, binary SHA256 `78c0280d7f8af62f7e529c239e110c3972b2f5901db5a153a62743f940610f47`. Generated header and patch checks PASS. Native source did not change in this last wave; no broad suites were repeated. The source fixes address the remaining software findings; final scoped approval passed for disabled source delivery. This is a disabled software/source candidate, **not installable/enablable** while the following named architecture gate remains open.

### GPIO_SHARED_FSEL2_COEXISTENCE

The current [paired mmap configure path](../../deployment/node-red/paired_gpio_daemon.py#L65) reads FSEL2 then writes a modified snapshot during startup/restart. GPIO20/21/26 share that register. Candidate [gpiod21 request/release](../../src/freeze_protect/lighting/executor.py#L391), including uncoordinated kernel cleanup after close/crash, can overlap this writer. Fixed per-line API ownership does not establish whole-system physical/configuration isolation. The configuration race is established from source; no electrical manifestation has been measured.

Do not enable the candidate GPIO21 executor alongside the current paired mmap daemon, create `/etc/independent-light/commissioned`, or set `LIGHT_GPIO21_ENABLED=commissioned` until separately reviewed architecture removes uncoordinated shared-register updates and records startup/restart/request/release/crash regression plus physical acceptance while preserving paired atomic output/lease behavior. Initial service ordering alone cannot cover later restarts or crash release; a userspace lock alone cannot cover uncoordinated kernel cleanup. No paired backend rewrite or hardware test was performed. Existing templates/flow/gateway remain disabled and their activation comments name this blocker. See [canonical gate](../superpowers/specs/2026-10-12-independent-lighting-design.md#gpio_shared_fsel2_coexistence) and [deployment prohibition](../../deployment/lighting/README.md#gpio_shared_fsel2_coexistence).

## Final review receipt

Final code references: Pi `26a22ec67081a5e352a80d6c24059e8b91b9f0db`,
Dial `6a5e03ed3a1b26a61536d602c697795f2444bccb`. The subsequent receipt commit
changes documentation only. The whole-branch review and exactly one final fix
wave/scoped re-review closed both P2 findings. The final reviewer independently
checked production browser JavaScript for malformed settings cache clearing,
settings503 OFF/BackAUTO routes, activation gating, ten-second expiry during a
pending settings request, session reset and original generation binding. Generated
page equality, final firmware SHA256 and patch checks passed. Broad suites were
not redundantly repeated; no hosted CI or hardware execution is claimed.

[Archived final review and scoped verdict](2026-10-13-independent-lighting-final-review.md)
record both findings and their closure. Approval is for disabled source delivery;
`GPIO_SHARED_FSEL2_COEXISTENCE` remains an open installation/activation blocker.
Its resolution requires another reviewed implementation and commissioning step,
with preserved paired output semantics. Both development branches remain local;
no merge, push, release, install or GPIO operation was performed.

## Subsequent paired ownership source repair

The separately authorized 2026-10-13 repair removes the raw FSEL configure path
from candidate source. Earlier evidence describes the pre-repair source and
unchanged installed legacy backend. See [repair evidence](2026-10-13-gpio-coexistence-fix.md)
and [migration runbook](../operations/paired-gpio-migration.md).
Installed migration, disconnected-load traces and all lighting/Protect gates
remain open; no runtime activation or new physical evidence is claimed.
