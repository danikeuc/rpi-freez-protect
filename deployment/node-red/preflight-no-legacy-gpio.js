#!/usr/bin/env node
"use strict";

/*
 * Refuse the 24 V commissioning test when an enabled legacy Node-RED flow can
 * still address the two valve relays or expose the former trigger routes.
 *
 * Run after deploying the new paired-valve flow, with the valves disconnected:
 *   sudo -u nodered node preflight-no-legacy-gpio.js \
 *     /mnt/dietpi_userdata/node-red/flows.json
 */

const fs = require("fs");

const flowsPath =
  process.argv[2] || "/mnt/dietpi_userdata/node-red/flows.json";

function fail(message) {
  console.error(`Preflight failed: ${message}`);
  process.exitCode = 1;
}

let nodes;
try {
  nodes = JSON.parse(fs.readFileSync(flowsPath, "utf8"));
} catch (error) {
  fail(`cannot read ${flowsPath}: ${error.message}`);
  process.exit();
}

if (!Array.isArray(nodes)) {
  fail(`${flowsPath} is not a Node-RED flow array`);
  process.exit();
}

const tabs = new Map(
  nodes.filter((node) => node.type === "tab").map((tab) => [tab.id, tab]),
);
const isActive = (node) => !tabs.get(node.z)?.disabled;

const legacyGpio = nodes.filter(
  (node) =>
    isActive(node) &&
    node.type === "rpi-gpio out" &&
    ["26", "20"].includes(String(node.pin)),
);
const legacyTriggers = nodes.filter(
  (node) =>
    isActive(node) &&
    node.type === "http in" &&
    typeof node.url === "string" &&
    node.url.startsWith('/trigger'),
);
const pairedBridgeRoutes = nodes.filter(
  (node) =>
    isActive(node) &&
    node.type === "http in" &&
    node.method === "post" &&
    node.url === "/internal/freeze-protect/actuator",
);

if (legacyGpio.length) {
  fail(
    `active legacy rpi-gpio out nodes use BCM 26/20: ${legacyGpio
      .map((node) => node.name || node.id)
      .join(", ")}`,
  );
}
if (legacyTriggers.length) {
  fail(
    `active legacy /trigger routes: ${legacyTriggers
      .map((node) => node.url)
      .join(", ")}`,
  );
}
if (pairedBridgeRoutes.length !== 1) {
  fail(
    `expected exactly one active paired bridge route, found ${pairedBridgeRoutes.length}`,
  );
}

if (process.exitCode) {
  console.error(
    "Keep the 24 V valve supply disconnected, disable the legacy relay flow, deploy, and run this check again.",
  );
} else {
  console.log(
    "Preflight passed: no active legacy GPIO 26/20 or /trigger paths; one paired bridge route is active.",
  );
}
