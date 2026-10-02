"""Execute exported Function node JavaScript with fake Node-RED context."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

FLOW = (
    Path(__file__).parents[2] / "deployment/node-red/freeze-protect-paired-relay.json"
)

SCRIPT = r"""
const assert = require('assert');
const fs = require('fs');
const functions = JSON.parse(fs.readFileSync(0, 'utf8'));
let ready = false;
const flow = {get: () => ready, set: (_key, value) => { ready = value; }};
const env = {get: () => 'secret'};
const node = {status: () => {}};
function run(id, msg) {
  return new Function('msg', 'flow', 'env', 'node', functions[id])(msg, flow, env, node);
}
function request(command, extra = {}, token = 'secret') {
  return {req: {headers: {'x-hub-token': token}},
          payload: {command, request_id: '12345678', protocol_version: 2, ...extra}};
}
// Safe DRAIN is available before readiness, but still authenticated.
let result = run('fp_m1_validate', request('DRAIN'));
assert.strictEqual(result[0]._freezeProtect.command, 'DRAIN');
assert.strictEqual(run('fp_m1_validate', request('DRAIN', {}, 'bad'))[1].statusCode, 401);
assert.strictEqual(run('fp_m1_validate', request('SUPPLY', {supply_action: 'begin'}))[1].statusCode, 503);
// Old daemon cannot establish bridge readiness after its startup DRAIN.
run('fp_m1_start_pair', {});
run('fp_m1_parse_executor', {_freezeProtect: {command: 'DRAIN', startup: true},
  payload: JSON.stringify({ok: true, command: 'DRAIN', gpio: {'26': 1, '20': 1}})});
assert.strictEqual(ready, false);
run('fp_m1_parse_executor', {_freezeProtect: {command: 'DRAIN', startup: true},
  payload: JSON.stringify({ok: true, command: 'DRAIN', protocol_version: 2,
                           gpio: {'26': 1, '20': 1}})});
assert.strictEqual(ready, true);
assert.strictEqual(run('fp_m1_validate', request('SUPPLY'))[1].statusCode, 400);
assert.strictEqual(run('fp_m1_validate', request('SUPPLY', {supply_action: 'invalid'}))[1].statusCode, 400);
result = run('fp_m1_validate', request('SUPPLY', {supply_action: 'begin'}));
assert.match(result[0].payload, /--supply-action begin/);
assert.strictEqual(result[0]._freezeProtect.supply_action, 'begin');
const accepted = run('fp_m1_parse_executor', {_freezeProtect: result[0]._freezeProtect,
  payload: JSON.stringify({ok: true, command: 'SUPPLY', supply_action: 'begin',
    protocol_version: 2, gpio: {'26': 0, '20': 0}})});
assert.strictEqual(accepted.statusCode, 200);
assert.strictEqual(accepted.payload.supply_action, 'begin');
assert.strictEqual(accepted.payload.protocol_version, 2);
"""


def test_exported_functions_enforce_strict_mode_and_startup_capability() -> None:
    runtime = shutil.which("node") or shutil.which("node.exe")
    if runtime is None:
        pytest.skip("Node.js is unavailable")
    nodes = {
        node["id"]: node["func"]
        for node in json.loads(FLOW.read_text())
        if node["type"] == "function"
    }
    result = subprocess.run(
        [runtime, "-e", SCRIPT],
        input=json.dumps(nodes),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
