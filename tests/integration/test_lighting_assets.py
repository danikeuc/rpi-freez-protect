import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "deployment" / "lighting"


def test_flow_disabled_and_transport_only():
    flow = json.loads((ASSETS / "lighting-flow.json").read_text())
    tab = next(n for n in flow if n["type"] == "tab")
    assert tab["disabled"] is True
    assert {n["type"] for n in flow} == {"tab", "http in", "function", "http response"}
    fn = next(n for n in flow if n["type"] == "function")
    source = (ASSETS / "unifi-adapter.js").read_text().split("module.exports")[0]
    assert source in fn["func"]
    assert "node.done()" in fn["func"]
    assert "global." not in fn["func"]
    assert "flow." not in fn["func"]
    assert "gpio" not in fn["func"].lower()
    assert "cancel()" in fn["finalize"]


def test_gateway_exact_routes_and_disabled_network_gate():
    text = (ASSETS / "light-gateway.conf").read_text()
    for suffix in ("status", "actions", "settings", "history", "events/unifi"):
        assert "location = /api/v1/lights/" + suffix in text
    assert "proxy_pass http://127.0.0.1:1880/lighting/unifi" in text
    assert "deny all;" in text
    assert "client_max_body_size 4k;" in text
    assert "access_log off;" in text
    assert "location /api" not in text


def test_units_default_disabled_and_separate_from_shower():
    for name in ("light-controller", "light-gpio"):
        text = (ASSETS / (name + ".service")).read_text()
        assert "[Install]" not in text
        assert "ConditionPathExists=/etc/independent-light/commissioned" in text
        assert "User=independent-light" in text
        assert "RestartSec=2" in text
        assert "TimeoutStopSec=5" in text
        assert "NoNewPrivileges=true" in text
        assert "freeze-protect.service" not in text
        assert "freeze-protect-pair" not in text
    controller = (ASSETS / "light-controller.service").read_text()
    assert "PrivateDevices=true" in controller
    gpio = (ASSETS / "light-gpio.service").read_text()
    assert "DevicePolicy=closed" in gpio
    assert "DeviceAllow=" not in gpio


def test_example_and_docs_keep_commissioning_gates_explicit():
    env = (ASSETS / "environment.example").read_text()
    for name in ("LIGHT_DISPLAY_TOKEN", "LIGHT_SETTINGS_TOKEN", "LIGHT_CAMERA_TOKEN",
                 "LIGHT_UNIFI_INGRESS_TOKEN", "LIGHT_UNIFI_PROFILE", "LIGHT_GPIO_CHIP"):
        assert name + "=" in env
    assert "LIGHT_UNIFI_ENABLED=" in env
    assert "LIGHT_UNIFI_ENABLED=commissioned" not in env
    assert "LIGHT_GPIO21_ENABLED=commissioned" not in env
    docs = (ASSETS / "README.md").read_text()
    assert "--provision-new-db" in docs
    assert "WatchdogSec" in docs
    assert "Protect" in docs and "stable" in docs
