"""Read-only target inventory must never disclose flow/settings contents."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

@pytest.fixture
def inventory():
    spec = importlib.util.spec_from_file_location("lighting_inventory", ROOT / "deployment/lighting/inventory.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_flow_report_does_not_echo_names_code_urls_or_credentials(inventory):
    secret = "PRIVATE_SENTINEL_DO_NOT_EMIT"
    rows = [{"id":"t", "type":"tab", "disabled":False, "label":secret},
            {"id":"a", "z":"t", "type":"function", "func":secret},
            {"id":"b", "z":"t", "type":"http in", "url":"/lighting/unifi"},
            {"id":"c", "z":"t", "type":"rpi-gpio out", "pin":"21", "name":secret},
            {"id":"d", "z":"t", "type":secret, "credentials":secret}]
    result = inventory.flow_summary(rows)
    assert result["nodes"] == 5
    assert result["enabled_light_routes"] == 1
    assert result["gpio_output_nodes_present"] is True
    assert secret not in json.dumps(result)


def test_disabled_tabs_and_nodes_not_counted_as_active_routes(inventory):
    rows = [{"id":"t", "type":"tab", "disabled":True},
            {"id":"a", "z":"t", "type":"http in", "url":"/lighting/unifi"},
            {"id":"b", "type":"http in", "d":True, "url":"/lighting/unifi"}]
    assert inventory.flow_summary(rows)["enabled_light_routes"] == 0


@pytest.mark.parametrize("value", [{}, ["bad"], [{"type":[]}], [{"id":[]}], [{"z":[]}]])
def test_malformed_flow_is_rejected(inventory, value):
    with pytest.raises(ValueError):
        inventory.flow_summary(value)


def test_journal_projection_is_strict_and_never_prints_arbitrary_paths(inventory):
    text = "Node-RED version: v4.1.0\nNode.js version: v22.1.0\nSettings file : /mnt/dietpi_userdata/node-red/settings.js\nUser directory : /mnt/dietpi_userdata/node-red\nFlows file : /secret-token.json\nNode-RED version: secret\n"
    result = inventory.startup_summary(text)
    assert result["node_red_version"] == "4.1.0"
    assert result["settings_path_matches"] is True
    assert result["flow_path_matches"] is False
    assert "secret" not in json.dumps(result)


def test_wrong_host_stops_before_any_commands(inventory, monkeypatch):
    monkeypatch.setattr(inventory, "read", lambda path, limit: b"synology_r1000_923+")
    monkeypatch.setattr(inventory, "run", lambda args: pytest.fail("command on wrong host"))
    with pytest.raises(ValueError, match="WRONG_HOST"):
        inventory.collect()


def test_metadata_probe_requests_no_gpio_or_process_changes(inventory):
    import ast
    tree = ast.parse(inventory.GPIO_PROBE)
    calls = [n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
    assert "get_line_info" in calls
    assert not {"request_lines", "set_value", "set_values", "reconfigure_lines"}.intersection(calls)
    assert all(args[0] in {"/usr/bin/systemctl", "/usr/bin/journalctl", inventory.PAIR_PYTHON} for args in inventory.COMMANDS)
    assert all(args[1] in {"show", "-u", "-I"} for args in inventory.COMMANDS)


def test_collect_returns_only_projection_and_preserves_input_files(inventory, monkeypatch):
    monkeypatch.setattr(inventory, "read", lambda path, limit: b"Raspberry Pi 4 Model B Rev 1.1\x00" if str(path).endswith("model") else b"[]")
    def fake_run(args):
        if args[0] == inventory.PAIR_PYTHON:
            return json.dumps({"chip_name_matches":True, "lines": {str(pin): {"used":False, "paired_owner":False, "name_matches":True} for pin in (20,21,26)}})
        if args[0].endswith("systemctl"):
            return "ActiveState=active\nMainPID=123\nUser=nodered\nSECRET=PRIVATE_SENTINEL"
        return "Node-RED version: v4.1.0\nPRIVATE_SENTINEL"
    monkeypatch.setattr(inventory, "run", fake_run)
    result = inventory.collect()
    assert result["mode"] == "READ_ONLY_INVENTORY"
    assert result["node_red_service"]["MainPID"] == 123
    assert "PRIVATE_SENTINEL" not in json.dumps(result)
    assert result["gpio_metadata"]["lines"]["21"]["used"] is False


@pytest.mark.parametrize("probe", [{"lines":{"21":{"used":False}}}, {"chip_name_matches":True,"lines":{str(p):{"used":"false", "paired_owner":False, "name_matches":True} for p in (20,21,26)}}])
def test_incomplete_or_non_boolean_gpio_probe_never_claims_free(inventory, monkeypatch, probe):
    monkeypatch.setattr(inventory, "read", lambda path, limit: b"Raspberry Pi 4 Model B Rev 1.1\x00" if str(path).endswith("model") else b"[]")
    monkeypatch.setattr(inventory, "run", lambda args: json.dumps(probe))
    assert inventory.collect()["gpio_metadata"] == {"result":"NOT_OBSERVED"}
