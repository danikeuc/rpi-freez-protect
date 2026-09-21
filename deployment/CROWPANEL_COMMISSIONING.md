# CrowPanel flash and acceptance procedure

Use this only after the Hub, Node-RED bridge and display-only Nginx gateway from `deployment/COMMISSIONING.md` are installed. The entire first test is performed with the 24 V valve supply disconnected.

## 1. Prepare the build workstation

Install PlatformIO Core and a USB serial driver suitable for the CrowPanel's USB bridge. In the repository:

```bash
cd firmware/crowpanel
cp include/secrets.example.h include/secrets.h
```

Edit the new, ignored `include/secrets.h`:

- `WIFI_SSID` and `WIFI_PASSWORD`: the local 2.4 GHz Wi-Fi network.
- `HUB_BASE_URL`: `http://<Pi-LAN-IP>:8081`, never the Node-RED address or port 8000.
- `DISPLAY_TOKEN`: exactly the value of `FREEZE_PROTECT_DISPLAY_TOKEN` on the Pi.

Run the pure UI tests and the embedded build:

```bash
pio test -e native
pio run -e crowpanel
```

## 2. Put the CrowPanel in flash mode

Connect a known data-capable USB cable to the CrowPanel's programming/data connector, then list ports:

```bash
pio device list
```

If no port appears, hold **BOOT**, tap **RESET**, release **RESET**, then release **BOOT**. Repeat `pio device list`. Do not open the enclosure or attach any relay wiring to the CrowPanel; it is a Wi-Fi display only.

## 3. Flash and inspect serial output

With the detected port selected automatically or through `--upload-port`, run:

```bash
pio run -e crowpanel -t upload
pio device monitor -e crowpanel
```

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
