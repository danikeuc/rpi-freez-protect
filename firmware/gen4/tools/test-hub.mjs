import http from "node:http";
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
export const BENCH_TOKEN = "gen4-bench-only";

// In-memory fixture only: no outbound connections, services, GPIO or credentials.
export function createTestHub({ now = () => performance.now(), mode = () => "normal", trace = () => {} } = {}) {
  let deadline = 0, starts = 0, drains = 0, seq = 0;
  const status = () => {
    const active = deadline > now();
    return { simulated: true, mode: "manual_timed", command: active ? "SUPPLY" : "DRAIN",
      state: active ? "TIMED_SHOWER" : "MANUAL_DRAIN", reason: "isolated_test_fixture",
      remaining_seconds: active ? Math.ceil((deadline - now()) / 1000) : 0,
      action: active ? "CLOSE_NOW" : "TIMED_SHOWER", action_enabled: true };
  };
  const server = http.createServer({ maxHeaderSize: 2048 }, (req, res) => {
    const kind = req.method === "GET" && req.url === "/api/v1/display/status" ? "status" :
      req.method === "POST" && req.url === "/api/v1/display/actions/timed-shower" ? "start" :
      req.method === "POST" && req.url === "/api/v1/display/actions/drain" ? "drain" : "unknown";
    const reply = (code, payload) => {
      const body = typeof payload === "string" ? payload : JSON.stringify(payload);
      res.writeHead(code, { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(body), "Connection": "close" });
      res.end(body);
      const s = status();
      trace({ seq: ++seq, method: kind === "status" ? "GET" : kind === "unknown" ? "OTHER" : "POST", kind, code, command: s.command, remaining_seconds: s.remaining_seconds, starts, drains });
    };
    req.on("error", () => {});
    res.on("error", () => {});
    if (req.headers["x-display-token"] !== BENCH_TOKEN) return reply(401, { simulated: true });
    if (kind === "unknown") return reply(404, { simulated: true });
    if (req.headers["transfer-encoding"] || Number(req.headers["content-length"] || 0) !== 0) return reply(400, { simulated: true });
    const fault = mode();
    if (fault === "unauthorized") return reply(401, { simulated: true });
    if (!["normal", "reject", "malformed", "slow"].includes(fault)) return reply(503, { simulated: true });
    if (kind === "status") {
      if (fault === "malformed") return reply(200, "{");
      if (fault === "slow") return setTimeout(() => { if (!res.destroyed) reply(200, status()); }, 3000);
      return reply(200, status());
    }
    if (fault === "reject") return reply(409, { simulated: true });
    if (kind === "start") {
      starts++;
      if (deadline <= now()) deadline = now() + 600000;
    } else { drains++; deadline = 0; }
    return reply(200, status());
  });
  server.headersTimeout = 5000;
  server.requestTimeout = 5000;
  server.setTimeout(5000, socket => socket.destroy());
  return { server };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const [host, controlFile] = process.argv.slice(2);
  if (!host || !/^(127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3})$/.test(host) || !controlFile) {
    console.error("Usage: node tools/test-hub.mjs <explicit private IPv4> <local control JSON>");
    process.exit(2);
  }
  const mode = () => { try { return JSON.parse(readFileSync(controlFile, "utf8").replace(/^\uFEFF/, "")).mode; } catch { return "unavailable"; } };
  const { server } = createTestHub({ mode, trace: value => console.log(JSON.stringify(value)) });
  server.on("error", err => { console.error(`TEST_HUB_ERROR code=${err.code || "UNKNOWN"}`); process.exitCode = 1; stop(); });
  server.listen(18081, host, () => console.log("TEST_HUB_READY port=18081 ttl_seconds=1200"));
  const stop = () => { server.closeAllConnections(); server.close(); clearTimeout(ttl); };
  const ttl = setTimeout(stop, 1200000);
  process.on("SIGTERM", stop);
  process.on("SIGINT", stop);
}
