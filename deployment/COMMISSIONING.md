# M1A DietPi and paired-valve commissioning

This procedure replaces the old Node-RED relay control with a constrained actuator bridge. Export the legacy relay flow first, but do not leave it deployed and active alongside the new bridge.

## Electrical boundary

- Raspberry Pi GPIO 26 / header 37 controls valve V1; GPIO 20 / header 38 controls valve V2.
- Both relay inputs are active-low. `DRAIN` is high/high (both relays released), connecting `Tuš` to `Izpust`. `SUPPLY` is low/low (both relays energized), connecting `Dovod` to `Tuš`.
- The valves are separate 24 V two-wire loads, wired through their own relay contacts. Do not power a valve from a Pi GPIO pin.
- Use the existing 24 V supply only after confirming its label is at least 1 A continuous. Keep the 24 V valve supply disconnected during steps 1–5.

## 1. Make the Pi service files

For the workstation-led route, create the non-login `freezeprotect` service
account below, then follow the separate commissioning-login bootstrap in
[`WORKSTATION_CODEX_COMMISSIONING.md`](WORKSTATION_CODEX_COMMISSIONING.md#2-pi-bootstrap).
The service account is deliberately not SSH-compatible; bootstrap creates and
validates `freezeprotect-commission` separately, without migrating service
data or ownership. Existing installations need an explicit trusted-console
review/remediation before either identity changes.
All privileged deployment steps here are trusted-console work, not additions
to the remote commissioning sudo allowlist. For workstation commissioning,
the physical test in step 5 also requires Danijel's explicit current-session
approval; the instructions below are not that approval.

On DietPi, clone the repository into `/opt/rpi-freez-protect`, create the dedicated service account and virtual environment, then install the supplied unit:

```bash
sudo apt update
sudo apt install -y git python3-venv
sudo useradd --system --home /var/lib/rpi-freeze-protect --shell /usr/sbin/nologin freezeprotect
sudo git clone https://github.com/danikeuc/rpi-freez-protect.git /opt/rpi-freez-protect
sudo python3 -m venv /opt/rpi-freez-protect/.venv
sudo /opt/rpi-freez-protect/.venv/bin/pip install --upgrade pip
sudo /opt/rpi-freez-protect/.venv/bin/pip install /opt/rpi-freez-protect
sudo install -d -o freezeprotect -g freezeprotect -m 0750 /var/lib/rpi-freeze-protect /etc/rpi-freeze-protect
sudo cp deployment/freeze-protect.env.example /etc/rpi-freeze-protect/environment
sudo chmod 0600 /etc/rpi-freeze-protect/environment
sudo chown root:root /etc/rpi-freeze-protect/environment
sudo cp deployment/systemd/freeze-protect.service /etc/systemd/system/freeze-protect.service
sudo cp deployment/systemd/freeze-protect-pair-gpio.service /etc/systemd/system/freeze-protect-pair-gpio.service
```

Edit `/etc/rpi-freeze-protect/environment` locally. Generate three independent long random values; the Node-RED token is shared only with the Node-RED environment file in the next section.

## 2. Bind Node-RED to loopback, then add the bridge

Create `/etc/rpi-freeze-protect/node-red.env` with exactly the one shared value:

```text
FREEZE_PROTECT_HUB_TOKEN=<same value as FREEZE_PROTECT_NODE_RED_TOKEN>
```

Set ownership and permissions, then add it to the active DietPi Node-RED service:

```bash
sudo chown root:root /etc/rpi-freeze-protect/node-red.env
sudo chmod 0600 /etc/rpi-freeze-protect/node-red.env
sudo chmod 0755 /opt/rpi-freez-protect/deployment/node-red/paired_gpio_daemon.py
sudo chmod 0755 /opt/rpi-freez-protect/deployment/node-red/paired_gpio_client.py
sudo systemctl edit node-red.service
```

In the opened override add:

```ini
[Service]
EnvironmentFile=/etc/rpi-freeze-protect/node-red.env
```

The active DietPi service uses `/mnt/dietpi_userdata/node-red` as its Node-RED user directory. Back up its active `settings.js`, then edit that file and set the `uiHost` value inside `module.exports` to the loopback address:

```bash
sudo cp -a /mnt/dietpi_userdata/node-red/settings.js /mnt/dietpi_userdata/node-red/settings.js.before-freeze-protect
sudoedit /mnt/dietpi_userdata/node-red/settings.js
```

```js
uiHost: "127.0.0.1",
```

This binds every Node-RED HTTP route, including its editor, to localhost. If remote editor access is needed during commissioning, use an SSH local port forward rather than reopening port 1880 on the LAN.

Start the atomic pair daemon before restarting Node-RED. It is the only process that accesses `/dev/gpiomem`: every state change is one masked GPSET0/GPCLR0 register write for BCM 26+20, followed by a paired level readback. The Node-RED process is only its bounded Unix-socket client.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now freeze-protect-pair-gpio.service
sudo systemctl restart node-red.service
```

Confirm both services are active, the active Node-RED service is not the broken legacy `nodered.service`, and port 1880 is loopback-only:

```bash
systemctl is-active node-red.service
systemctl is-active nodered.service
systemctl is-active freeze-protect-pair-gpio.service
sudo ss -ltnp | rg ':1880'
sudo -u nodered /opt/rpi-freez-protect/deployment/node-red/paired_gpio_client.py DRAIN
sudo pinctrl get 26
sudo pinctrl get 20
```

The socket line must begin with `127.0.0.1:1880` or `[::1]:1880`, never `0.0.0.0:1880` or `[::]:1880`. From another LAN device, `nc -vz <Pi-LAN-IP> 1880` must fail. The client command must return JSON with `"ok": true`, and the two pins must be outputs high after restart. If the daemon or client cannot run as `nodered`, do not import the bridge; fix the Pi GPIO permissions first.

In the Node-RED editor (locally or through that SSH tunnel), first export the existing relay flow to a file outside the active flow set. Then disable the legacy relay flow tab that contains the `rpi-gpio out` GPIO 26/20 nodes and the old `/trigger/...` routes. Import `deployment/node-red/freeze-protect-paired-relay.json`; inspect that it has one POST route and the single fixed-path `paired_gpio_client.py` executor, but no individual GPIO output node. Deploy the disabled legacy tab and the new tab together. The bridge returns `503` until its startup DRAIN write and both GPIO readbacks are verified; do not test it during that brief state.

With the 24 V valve supply still disconnected, run this mandatory cutover preflight against the deployed active flow file:

```bash
sudo -u nodered node /opt/rpi-freez-protect/deployment/node-red/preflight-no-legacy-gpio.js \
  /mnt/dietpi_userdata/node-red/flows.json
```

It must print `Preflight passed` and exit with code zero. If it reports a legacy GPIO 26/20 node, `/trigger` route, or a missing/duplicate bridge route, keep valve power disconnected, correct the tabs in the editor, deploy, and run the command again. The exported legacy file is only a rollback record; it must not be imported as an active relay flow.

## 3. Expose only the display API to the local Wi-Fi

The Hub itself stays on `127.0.0.1:8000`. Install the supplied narrow Nginx gateway so the CrowPanel can reach only its three device-token-protected endpoints:

```bash
sudo apt update
sudo apt install nginx-light
sudo cp deployment/nginx/freeze-protect-display.conf /etc/nginx/sites-available/freeze-protect-display
sudo ln -s /etc/nginx/sites-available/freeze-protect-display /etc/nginx/sites-enabled/freeze-protect-display
sudo nginx -t
sudo systemctl enable --now nginx
```

The CrowPanel receives `http://<Pi-LAN-IP>:8081` as `HUB_BASE_URL`. Verify `curl http://<Pi-LAN-IP>:8081/api/v1/status` returns `404`; that route must never leave loopback. Do not forward port 8081 on the internet router.

## 4. Prove the bridge with valve power still disconnected

Start the Hub only after Node-RED is active:

```bash
sudo systemctl enable --now freeze-protect.service
curl -H "X-Admin-Token: <admin token>" http://127.0.0.1:8000/api/v1/status
sudo pinctrl get 26
sudo pinctrl get 20
```

The Hub startup state must be `FROST_PROTECTION` with reason `sensor_pending`; both pins must be high. Use the authenticated display API or later CrowPanel only to request a timed shower. With valve power disconnected, start the request and confirm both pins go low; use immediate drain and confirm both return high. No single-channel action exists.

## 5. Connect and test the valves with water isolated

1. Isolate water and make sure the safe physical path is `Tuš` to `Izpust` while the Pi is stopped.
2. Connect 24 V to both valve contact circuits, start a timed shower, and verify both valves move together to `Dovod` to `Tuš`.
3. Keep `SUPPLY` active for one minute so both return capacitors charge. Invoke immediate drain; verify both return to `Tuš` to `Izpust`.
4. Repeat once by stopping `freeze-protect.service`; the Node-RED startup and Hub restart paths must both leave the relays released/high.
5. Only after the DS18B20 wiring and its separate commissioning checklist are complete may `sensor_commissioned` be changed to `true` in the administrator settings.

## Troubleshooting boundary

- If `freeze-protect.service` reports `FAULT`, do not retry `SUPPLY`; inspect the Node-RED receipt and use an administrator fault-clear only after the pins have been confirmed high.
- If Node-RED fails to start, leave its GPIO outputs high. Do not fall back to the old unauthenticated GET trigger routes.
- A missing weather location or DS18B20 is expected before commissioning and remains safe `DRAIN`; it is not a reason to bypass the Hub.
