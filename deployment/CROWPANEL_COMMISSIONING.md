# Waveshare cutover and historical CrowPanel procedure

## Current Waveshare dial cutover

**The CrowPanel acceptance procedure below is historical and superseded for
the manual timed Waveshare installation.** It documents the earlier display
and its `COM6` recovery context; it does not authorize a new CrowPanel flash,
provisioning, or valve test. In particular, its old step 4 actions and step 5
reference are not the release gate for the Waveshare dial.

Before deployment, pass the repository Python test suite, Ruff, the Nginx
allowlist assertion, and the dial firmware's own build and interaction tests.
These are source checks; record the exact revisions and results. Review
`deployment/COMMISSIONING.md` and
`deployment/WORKSTATION_CODEX_COMMISSIONING.md` for the Pi and restricted
access boundaries. A trusted local-console operator must separately inspect
the installed files and active Node-RED flow; source checks do not establish
the deployed state.

1. Keep the 24 V valve supply disconnected. At the trusted Pi console,
   generate a new independent display token, rotate
   `FREEZE_PROTECT_DISPLAY_TOKEN` in the protected environment file, and set
   `FREEZE_PROTECT_CONTROL_MODE=manual_timed` explicitly. Keep the admin and
   Node-RED tokens distinct and outside firmware, screenshots, logs, and Git.
   Install and restart the Hub through the reviewed commissioning procedure.
   Verify its reported mode is `manual_timed`; absent or invalid mode is
   `safe_drain` and refuses `SUPPLY`.
2. Remove the former display token from the CrowPanel's ignored
   `firmware/crowpanel/include/secrets.h` copy and any other provisioned
   CrowPanel copy. Keep the CrowPanel retired from this valve control network;
   do not provision it with the rotated token. Provision only the Waveshare
   dial with the new token using its own controlled firmware/configuration
   procedure. Verify the retired token receives HTTP 401 on all three display
   routes before enabling the new dial. Do not expose a token in test output.
3. Confirm the installed Nginx gateway exposes exactly `GET
   /api/v1/display/status`, `POST
   /api/v1/display/actions/timed-shower`, and `POST
   /api/v1/display/actions/drain` on the trusted LAN. The Hub stays on
   loopback, as does Node-RED; no relay or administrative route is exposed
   through this gateway. Check the deployed active Node-RED flow for legacy
   GPIO nodes and trigger routes using the documented preflight.
4. Obtain Danijel's explicit approval in the same conversation for the
   bounded **24 V disconnected** software/GPIO validation before issuing any
   timed action. With 24 V still disconnected, verify startup and idle report
   `DRAIN`, `mode=manual_timed`, and zero remaining seconds. Through the
   authenticated dial path, confirm one deliberate two-second hold yields one
   accepted 600-second interval, while a duplicate press does not extend it.
   Verify the paired command receipt and read back **both** BCM 26 and BCM 20:
   low/low only during accepted `SUPPLY`, high/high after immediate `DRAIN`,
   expiry, and restart. Confirm weather/sensor activity and dial reconnection
   do not start `SUPPLY`. Readback proves output levels only, never valve
   position. On any failed receipt, readback, service check, or preflight,
   stop, leave 24 V disconnected and the requested state at `DRAIN`, and do
   not retry `SUPPLY`.
5. A live valve test is a **separate** gate. Stop after the disconnected
   validation and request Danijel's explicit approval for a bounded physical
   test in that conversation. Only then use the reviewed water-isolated
   procedure, verify both valves and return capacitors, and record physical
   observations separately from software status and GPIO readback. This
   document grants no approval to connect 24 V or run a live test.

## Historical CrowPanel procedure — superseded for this installation

Use this only after the Hub, Node-RED bridge and display-only Nginx gateway from `deployment/COMMISSIONING.md` are installed. The entire first test is performed with the 24 V valve supply disconnected.

## 1. Prepare the build workstation

Install PlatformIO Core and a USB serial driver suitable for the CrowPanel's
USB bridge on the Windows workstation. In PowerShell:

```powershell
Set-Location 'C:\Users\danik\Projects\rpi-freez-protect\firmware\crowpanel'
if (-not (Test-Path include\secrets.h)) {
    Copy-Item include/secrets.example.h include/secrets.h
}
```

Edit the new, ignored `include/secrets.h`:

- `WIFI_SSID` and `WIFI_PASSWORD`: the local 2.4 GHz Wi-Fi network.
- `HUB_BASE_URL`: `http://<Pi-LAN-IP>:8081`, never the Node-RED address or port 8000.
- `DISPLAY_TOKEN`: exactly the value of `FREEZE_PROTECT_DISPLAY_TOKEN` on the Pi.

Run the pure UI tests and the embedded build:

```powershell
pio test -e native
pio run -e crowpanel
```

## 2. Put the CrowPanel in flash mode

Connect a known data-capable USB cable to the CrowPanel's programming/data
connector. For this installation the operator-confirmed workstation port is
`COM6`. First compare the JSON inventory with the panel disconnected and then
reconnected. Record the exact `hwid` of the newly appeared entry; the mutable
COM number alone is not device identity. Verify both values before proceeding:

```powershell
$CrowPanelPort = 'COM6'
$SerialInventory = @(pio device list --serial --json-output | ConvertFrom-Json)
$PortMatches = @($SerialInventory | Where-Object { $_.port -eq $CrowPanelPort })
$CrowPanelExpectedHwid = Read-Host 'Paste the exact CrowPanel hwid recorded by disconnect/reconnect verification'
if ([string]::IsNullOrWhiteSpace($CrowPanelExpectedHwid)) {
    throw 'A verified CrowPanel hwid is required; stop.'
}
$CrowPanelMatches = @($PortMatches | Where-Object { $_.hwid -eq $CrowPanelExpectedHwid })
if ($CrowPanelMatches.Count -ne 1) {
    throw "COM port or hwid does not match the verified CrowPanel identity; stop."
}
$CrowPanelMatches | ConvertTo-Json -Depth 4
```

If `COM6` does not appear, stop before upload. If an explicitly approved
recovery requires flash mode, hold **BOOT**, tap **RESET**, release **RESET**,
then release **BOOT**, and repeat the inventory. Do not guess another port. Do
not open the enclosure or attach relay wiring to the CrowPanel; it is a Wi-Fi
display only.

## 3. Flash and inspect serial output

Do not reflash as a routine diagnostic. Firmware has already been uploaded on
this installation; upload again only after a firmware change or an explicitly
approved recovery. When upload is required, bind the already verified port
explicitly. Serial observation can run without another upload:

```powershell
pio run -e crowpanel -t upload --upload-port $CrowPanelPort
pio device monitor --baud 115200 --port $CrowPanelPort
```

After the monitor opens, tap **RESET** once without holding **BOOT**. Require a
fresh `Freeze Protect CrowPanel boot` line. Opening a monitor after the panel is
already running does not replay the one-time boot message.

Expected serial line:

```text
Freeze Protect CrowPanel boot
```

The screen must first show `NI POVEZAVE — PREVERI HUB` until Wi-Fi and the display gateway are available. It must never show GPIO, Node-RED, a weather-provider name, or an administrative token.

## 4. Functional test with valve power disconnected

1. Verify the Home page shows `VODA ZAPRTA`, `7 DNI · MIN … °C`, the turquoise shower icon, `VKLOPI TUŠ` and `10 MIN` after a successful poll. It must not show sensor health, pipe temperature, `sensor_pending` or any other technical reason.
2. Turn the encoder right to open the Forecast page and left to return. The Forecast page must show seven date/minimum rows; its short press returns Home without sending a Hub command.
3. Press the encoder or touch the bottom action on Home. Only after the Hub accepts the request may the screen change to `TUŠ AKTIVEN`, `SAMODEJNI IZKLOP VKLJUČEN`, the red STOP icon and `ZAPRI VODO`.
4. On the Pi, confirm GPIO 26 and GPIO 20 both become low together. Do not connect 24 V yet.
5. Press the action again. Confirm the display sends `DRAIN`, the Home screen returns to `VODA ZAPRTA`, and both Pi pins become high together. Then hold the dial for two seconds on either page and confirm it emits one `DRAIN`; releasing it must not start a shower.
6. Disable the display gateway temporarily or turn off the Wi-Fi access point. Within one poll interval the screen must show `NI POVEZAVE — PREVERI HUB` and disable the action. Restore the gateway; no pending action may execute automatically.

## 5. Combined water-isolated valve test

Only after all six display checks pass, continue at step 5 of `deployment/COMMISSIONING.md`: isolate water, connect 24 V, prove paired movement, charge the return capacitors for one minute, and prove immediate drain. Keep the display token and Pi secrets out of screenshots, serial logs, and Git.
