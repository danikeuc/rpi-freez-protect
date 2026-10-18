# Startup/software follow-up — 2026-10-18

## Evidence and current state

Owner-provided startup audit (attachment e680b259-d223-4576-abc2-ba13009c4d85) reports all seven units enabled/running, 14.140 s boot, 55 cached-index upgrade candidates and two not upgraded. apt-mark timed out. Node binaries were not found in the collector's deliberately restricted standard PATH. This is not evidence of missing Node.js or Node-RED.

A fresh exact restricted maintenance status query succeeded during this follow-up. Hub PID5599, paired GPIO PID436 and Node-RED PID627 remain active. Shower reports weather_assisted/MANUAL_DRAIN/user_off. Light reports AUTO/OK, desired_on=false, gpio_on=false, revision79; manual_expired event at 2026-10-18T11:01:01.395805+00:00. No selected journal matches in the bounded last3000-entry query; this is not proof of no historical faults. GPIO state is not physical contact/valve feedback.

The installed controller diagnostics hashes match the prior acceptance receipt. Historical failure receipts in maintenance status remain historical, not current migration commands to rerun.

## Investigation boundary

The light clock guard compares wall and monotonic deltas with a five-second threshold; the shared clock_or_lease_fault label also covers executor expiry/renewal failures. No clock-fault threshold, recovery policy, restart policy or actuator behavior was changed.

Restart=no on Node-RED describes recovery behavior, not the root cause of the historical HTTP503. The repository bridge can emit503 for readiness, readback and executor errors. Historical HTTP503 lacks the now-installed detailed error category. Do not claim an NTP correction or Node-RED crash as the proven cause.

## Prepared read-only follow-up

`deployment/diagnostics/clock_startup_followup.py` collects bounded current-boot per-service journals, clock delta candidates using same-boot real/monotonic metadata, allowlisted numeric light diagnostics, logged Node versions and active-process package metadata without executing that binary. It queries dpkg holds and repeats cached APT list/simulation to identify candidates omitted by upgrade. It records time configuration and selected scheduling metadata without exporting commands, environment values or raw journals.

No APT refresh, install, service restart, fault clearing, GPIO command or permission change. Runtime output PENDING; the existing helper does not authorize this broader OS query, so execution remains a trusted root-console handoff. The status-only extension remains in use for autonomous controller checks.

## Follow-up runtime receipt reviewed

Owner returned CLOCK_STARTUP_FOLLOWUP_COMPLETE. APT probes completed; the apparent pause was between output sections, not a demonstrated hang. dpkg holds is empty. Cached upgrade exclusions are linux-base-rpi-v8 and linux-image-rpi-v8, both candidate1:6.18.50-1+rpt1. Dependency reason remains unverified; no indexes were refreshed or packages installed.

Current-boot Node-RED logs report Node-RED5.0.7 and Node.js26.8.1. PID627 executable is node outside the restricted standard search PATH. This closes the missing-binary diagnostic interpretation; package_metadata remained empty.

Same-boot manager and timesync journal timestamp pairs show a forward wall-minus-monotonic adjustment of37.945121/37.945119 seconds. timesync success is2026-10-17T01:25:40.386821Z. Previously collected light fault clock_or_lease_fault occurred2026-10-17T01:25:40.423130Z, 36.309ms later. Combined with the installed clock guard threshold (>5s), this strongly supports clock-step-triggered light FAULT for that incident. Direct light diagnostic values from that moment are unavailable: light query reached4000entry cap and starts later. It does not establish the earlier shower HTTP503 cause or every light incident.

/etc/crontab reports daily run-parts at01:25 system time; UTC configured. This aligns with the synchronization timing but the specific timesync invocation chain was not captured. The assumed /boot/dietpi/func/dietpi-timesync path was unavailable. No alternative path is asserted as deployed.

Next maintenance design: continuous DietPi time synchronization with startup ordering/readiness, retaining the clock-fault protection, followed by separately validated Node-RED restart recovery and package updates. No settings changed by this review. Continuous sync reduces accumulated drift but does not guarantee absence of steps on initial sync or after outages.
