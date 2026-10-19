import test from "node:test";
import assert from "node:assert/strict";
import { createTestHub, BENCH_TOKEN } from "./test-hub.mjs";

async function fixture(run) {
  let now = 1000;
  let mode = "normal";
  const traces = [];
  const hub = createTestHub({ now: () => now, mode: () => mode, trace: e => traces.push(e) });
  await new Promise(resolve => hub.server.listen(0, "127.0.0.1", resolve));
  const base = `http://127.0.0.1:${hub.server.address().port}`;
  const request = (path = "status", method = "GET", token = BENCH_TOKEN) => fetch(`${base}/api/v1/display/${path}`, { method, headers: { "X-Display-Token": token } });
  try { await run({ request, traces, setTime: v => { now = v; }, setMode: v => { mode = v; } }); }
  finally { hub.server.closeAllConnections(); await new Promise(resolve => hub.server.close(resolve)); }
}

test("fixture authenticates, bounds shower, does not extend duplicate, and drains in memory", async () => {
  await fixture(async ({ request, setTime, traces }) => {
    assert.equal((await request("status", "GET", "wrong")).status, 401);
    let r = await request();
    assert.equal(r.status, 200);
    let s = await r.json();
    assert.equal(s.command, "DRAIN");
    assert.equal(s.mode, "manual_timed");
    assert.equal((await request("actions/timed-shower", "POST")).status, 200);
    setTime(201000);
    assert.equal((await request("actions/timed-shower", "POST")).status, 200);
    s = await (await request()).json();
    assert.equal(s.remaining_seconds, 400);
    setTime(601000);
    assert.equal((await (await request()).json()).command, "DRAIN");
    await request("actions/timed-shower", "POST");
    await request("actions/drain", "POST");
    assert.equal((await (await request()).json()).command, "DRAIN");
    assert.equal(traces.filter(e => e.method === "POST").length, 4);
    assert.ok(traces.every(e => !JSON.stringify(e).includes(BENCH_TOKEN)));
  });
});

test("fixture injects rejection and malformed status without accepting actions", async () => {
  await fixture(async ({ request, setMode }) => {
    setMode("reject");
    assert.equal((await request("actions/timed-shower", "POST")).status, 409);
    setMode("normal");
    assert.equal((await (await request()).json()).command, "DRAIN");
    setMode("unauthorized");
    assert.equal((await request()).status, 401);
    setMode("malformed");
    const r = await request();
    assert.equal(r.status, 200);
    assert.equal(await r.text(), "{");
  });
});
