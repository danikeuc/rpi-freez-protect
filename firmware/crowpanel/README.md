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
