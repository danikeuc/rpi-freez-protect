# CrowPanel flash and acceptance procedure

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

If Wi-Fi is disconnected, the screen also shows a diagnostic block with the
current Wi-Fi status, IP and MAC, the last disconnect reason, and the most
recent Hub poll's HTTP result, JSON validity and age. Treat these as separate
observations: an earlier HTTP 200 does not prove the current Wi-Fi state, and
neither value proves relay or valve operation.

## 4. Functional test with valve power disconnected

1. After a successful poll, verify the Home page shows a title matching the Hub
   state (`NORMALNO DELOVANJE`, `ZAŠČITA PRED MRAZOM` or `TUŠ AKTIVEN`),
   `7 DNI · MIN … °C`, the turquoise shower icon, `VKLOPI TUŠ` and `10 MIN`.
   It must not show sensor health, pipe temperature, `sensor_pending` or any
   other technical reason.
2. Turn the encoder right to open the Forecast page and left to return. The Forecast page must show seven date/minimum rows; its short press returns Home without sending a Hub command.
3. Press the encoder or touch the bottom action on Home. Only after the Hub accepts the request may the screen change to `TUŠ AKTIVEN`, `SAMODEJNI IZKLOP VKLJUČEN`, the red STOP icon and `ZAPRI VODO`.
4. On the Pi, confirm GPIO 26 and GPIO 20 both become low together. Do not connect 24 V yet.
5. Press the action again. Confirm the display sends `DRAIN`, the Home screen returns to `VODA ZAPRTA`, and both Pi pins become high together. Then hold the dial for two seconds on either page and confirm it emits one `DRAIN`; releasing it must not start a shower.
6. Disable the display gateway temporarily or turn off the Wi-Fi access point. Within one poll interval the screen must show `NI POVEZAVE — PREVERI HUB` and disable the action. Restore the gateway; no pending action may execute automatically.

## 5. Combined water-isolated valve test

Only after all six display checks pass, continue at step 5 of `deployment/COMMISSIONING.md`: isolate water, connect 24 V, prove paired movement, charge the return capacitors for one minute, and prove immediate drain. Keep the display token and Pi secrets out of screenshots, serial logs, and Git.
