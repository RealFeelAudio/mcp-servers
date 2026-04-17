/**
 * Claude Bridge — Stream Deck Plugin
 * Connects to Stream Deck software via WebSocket and logs button events
 * to C:\streamdeck-setup\events\button_events.json for the MCP server to read.
 */

import WebSocket from "ws";
import * as fs from "fs";
import * as path from "path";

const EVENTS_FILE = "C:\\streamdeck-setup\\events\\button_events.json";
const MAX_EVENTS = 200;

interface SDEvent {
  event: string;
  action?: string;
  context?: string;
  device?: string;
  payload?: {
    settings?: Record<string, unknown>;
    coordinates?: { column: number; row: number };
    state?: number;
    userDesiredState?: number;
    isInMultiAction?: boolean;
  };
}

interface ButtonEvent {
  timestamp: string;
  type: string;
  action: string;
  context: string;
  device: string;
  label: string;
  coordinates?: { column: number; row: number };
  state?: number;
}

function ensureEventsFile(): void {
  const dir = path.dirname(EVENTS_FILE);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  if (!fs.existsSync(EVENTS_FILE)) {
    fs.writeFileSync(EVENTS_FILE, JSON.stringify([]), "utf-8");
  }
}

function appendEvent(ev: ButtonEvent): void {
  let events: ButtonEvent[] = [];
  try {
    const raw = fs.readFileSync(EVENTS_FILE, "utf-8");
    const parsed = JSON.parse(raw);
    events = Array.isArray(parsed) ? parsed : [];
  } catch {
    events = [];
  }
  events.push(ev);
  if (events.length > MAX_EVENTS) {
    events = events.slice(events.length - MAX_EVENTS);
  }
  fs.writeFileSync(EVENTS_FILE, JSON.stringify(events, null, 2), "utf-8");
}

// --- Parse launch args from Stream Deck ---
const args = process.argv.slice(2);
const argMap: Record<string, string> = {};
for (let i = 0; i < args.length - 1; i += 2) {
  argMap[args[i]] = args[i + 1];
}

const port = parseInt(argMap["-port"] ?? "28196", 10);
const pluginUUID = argMap["-pluginUUID"] ?? "";
const registerEvent = argMap["-registerEvent"] ?? "registerPlugin";

ensureEventsFile();
console.log(`[claude-bridge] connecting to Stream Deck on port ${port}`);

const ws = new WebSocket(`ws://127.0.0.1:${port}`);

ws.on("open", () => {
  console.log("[claude-bridge] connected, registering plugin");
  ws.send(JSON.stringify({ event: registerEvent, uuid: pluginUUID }));
});

ws.on("message", (data: WebSocket.RawData) => {
  let msg: SDEvent;
  try {
    msg = JSON.parse(data.toString()) as SDEvent;
  } catch {
    return;
  }

  const { event, action = "", context = "", device = "", payload = {} } = msg;

  if (event === "keyDown" || event === "keyUp") {
    const settings = (payload.settings ?? {}) as Record<string, unknown>;
    const label = typeof settings["label"] === "string" ? settings["label"] : "";

    appendEvent({
      timestamp: new Date().toISOString(),
      type: event,
      action,
      context,
      device,
      label,
      coordinates: payload.coordinates,
      state: payload.state,
    });

    console.log(`[claude-bridge] ${event} logged — label=${label || "(none)"}`);
  }
});

ws.on("error", (err: Error) => {
  console.error("[claude-bridge] WebSocket error:", err.message);
});

ws.on("close", () => {
  console.log("[claude-bridge] disconnected, exiting.");
  process.exit(0);
});
