# CrowPanel firmware

This PlatformIO project targets the Elecrow CrowPanel 1.28-inch ESP32-S3 rotary display. It obtains status and action permissions only from the RPi Freeze Protect Hub; it does not know GPIO pins, Node-RED, weather-provider credentials, or frost policy.

## Provision and build

Install PlatformIO Core, then provision the ignored local secret file:

```bash
cd firmware/crowpanel
cp include/secrets.example.h include/secrets.h
# edit Wi-Fi name, Wi-Fi password, the Hub LAN URL and the display token
pio test -e native
pio run -e crowpanel
```

`HUB_BASE_URL` must be the Pi's LAN address reachable by the CrowPanel, for example `http://192.168.1.50:8081`. The Hub process remains bound to loopback; the supplied Nginx configuration exposes only the three display API routes on port 8081.

See `deployment/CROWPANEL_COMMISSIONING.md` for the flash and physical acceptance sequence. Keep the 24 V valve supply disconnected for the first display tests.

## Dial controls

The dial is deliberately limited to four actions:

- turn right from the home screen to open the 7-day forecast; turn left to return;
- short press at home starts the Hub-configured timed shower (10 minutes by default);
- short press while the shower is active sends `DRAIN` immediately;
- short press on the forecast returns home without sending a Hub command;
- hold the dial for two seconds on either page to send `DRAIN` once.

The production Hub safety sensor is the three-wire PT100/MAX31865 on SPI0 CE0.
Its health, measurement and diagnostics are deliberately not shown on the
CrowPanel. The DS18B20 adapter remains rollback code only.
