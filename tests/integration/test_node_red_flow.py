import json
from pathlib import Path

FLOW_PATH = (
    Path(__file__).parents[2]
    / "deployment"
    / "node-red"
    / "freeze-protect-paired-relay.json"
)


def test_flow_has_only_one_post_route_and_never_mentions_gpio21() -> None:
    content = FLOW_PATH.read_text(encoding="utf-8")
    flow = json.loads(content)
    routes = [
        (node["method"], node["url"])
        for node in flow
        if node["type"] == "http in"
    ]

    assert routes == [("post", "/internal/freeze-protect/actuator")]
    assert "GPIO21" not in content
    assert "paired_gpio_client.py" in content
    assert '"type": "rpi-gpio out"' not in content
    assert "FREEZE_PROTECT_HUB_TOKEN" in content
    assert "body.command !== 'SUPPLY' && body.command !== 'DRAIN'" in content
    assert '"type": "trigger"' not in content


def test_flow_rejects_commands_until_a_paired_gpio_readback_is_confirmed() -> None:
    flow = json.loads(FLOW_PATH.read_text(encoding="utf-8"))
    nodes = {node["id"]: node for node in flow}
    validate = nodes["fp_m1_validate"]
    executor = nodes["fp_m1_execute_pair"]

    assert "flow.get('freezeProtectReady') !== true" in validate["func"]
    assert nodes["fp_m1_start_pair"]["wires"] == [["fp_m1_execute_pair"]]
    assert executor["type"] == "exec"
    assert executor["command"].endswith("/paired_gpio_client.py")
    assert executor["wires"][0] == ["fp_m1_parse_executor"]
    assert "Date.now() + 1500" in validate["func"]
    assert "--deadline-unix-ms" in validate["func"]
    assert "flow.set('freezeProtectReady', readbackMatches)" in nodes[
        "fp_m1_parse_executor"
    ]["func"]
    assert '"type": "rpi-gpio out"' not in FLOW_PATH.read_text(encoding="utf-8")


def test_commissioning_binds_node_red_to_loopback_before_bridge_import() -> None:
    commissioning = (FLOW_PATH.parents[1] / "COMMISSIONING.md").read_text(
        encoding="utf-8"
    )

    assert 'uiHost: "127.0.0.1"' in commissioning
    assert "sudo ss -ltnp | rg ':1880'" in commissioning
    assert "another LAN device" in commissioning


def test_atomic_pair_daemon_is_a_service_before_node_red_starts() -> None:
    deployment_root = FLOW_PATH.parents[1]
    unit = (deployment_root / "systemd" / "freeze-protect-pair-gpio.service").read_text(
        encoding="utf-8"
    )
    commissioning = (deployment_root / "COMMISSIONING.md").read_text(encoding="utf-8")

    assert "Before=node-red.service" in unit
    assert "User=nodered" in unit
    assert "SupplementaryGroups=gpio" in unit
    assert "RuntimeDirectory=freeze-protect" in unit
    assert "paired_gpio_daemon.py" in unit
    assert "freeze-protect-pair-gpio.service" in commissioning
    hub_unit = (deployment_root / "systemd" / "freeze-protect.service").read_text(
        encoding="utf-8"
    )
    assert "Requires=freeze-protect-pair-gpio.service" in hub_unit
    assert "SupplementaryGroups=spi" in hub_unit


def test_commissioning_preflight_rejects_active_legacy_relay_paths() -> None:
    preflight = (
        FLOW_PATH.parent / "preflight-no-legacy-gpio.js"
    ).read_text(encoding="utf-8")
    commissioning = (FLOW_PATH.parents[1] / "COMMISSIONING.md").read_text(
        encoding="utf-8"
    )

    assert "rpi-gpio out" in preflight
    assert "'/trigger'" in preflight
    assert "tabs.get(node.z)?.disabled" in preflight
    assert "disable the legacy relay flow" in commissioning
    assert "preflight-no-legacy-gpio.js" in commissioning


def test_display_gateway_rejects_methods_outside_its_device_contract() -> None:
    nginx = (FLOW_PATH.parents[1] / "nginx" / "freeze-protect-display.conf").read_text(
        encoding="utf-8"
    )

    assert nginx.count("if ($request_method != GET) { return 405; }") == 1
    assert nginx.count("if ($request_method != POST) { return 405; }") == 2


def test_crowpanel_enables_fonts_and_renders_the_dedicated_forecast_page() -> None:
    firmware = FLOW_PATH.parents[2] / "firmware" / "crowpanel"
    lv_conf = (firmware / "include" / "lv_conf.h").read_text(encoding="utf-8")
    hardware = (firmware / "src" / "hardware.cpp").read_text(encoding="utf-8")
    display_state = (firmware / "src" / "display_state.cpp").read_text(
        encoding="utf-8"
    )

    assert "#define LV_FONT_MONTSERRAT_16 1" in lv_conf
    assert "#define LV_FONT_MONTSERRAT_20 1" in lv_conf
    assert '"7-DNEVNA NAPOVED"' in hardware
    assert '"PRITISNI ZA NAZAJ"' in hardware
    assert '"VKLOPI TUŠ"' in display_state
    assert '"ZAPRI VODO"' in display_state
    assert "POSODOBLJENO " not in hardware
