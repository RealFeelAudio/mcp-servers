"use strict";
/**
 * Claude Bridge — Stream Deck Plugin
 * Connects to Stream Deck software via WebSocket and logs button events
 * to C:\streamdeck-setup\events\button_events.json for the MCP server to read.
 */
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const ws_1 = __importDefault(require("ws"));
const fs = __importStar(require("fs"));
const path = __importStar(require("path"));
const EVENTS_FILE = "C:\\streamdeck-setup\\events\\button_events.json";
const MAX_EVENTS = 200;
function ensureEventsFile() {
    const dir = path.dirname(EVENTS_FILE);
    if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
    }
    if (!fs.existsSync(EVENTS_FILE)) {
        fs.writeFileSync(EVENTS_FILE, JSON.stringify([]), "utf-8");
    }
}
function appendEvent(ev) {
    let events = [];
    try {
        const raw = fs.readFileSync(EVENTS_FILE, "utf-8");
        const parsed = JSON.parse(raw);
        events = Array.isArray(parsed) ? parsed : [];
    }
    catch {
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
const argMap = {};
for (let i = 0; i < args.length - 1; i += 2) {
    argMap[args[i]] = args[i + 1];
}
const port = parseInt(argMap["-port"] ?? "28196", 10);
const pluginUUID = argMap["-pluginUUID"] ?? "";
const registerEvent = argMap["-registerEvent"] ?? "registerPlugin";
ensureEventsFile();
console.log(`[claude-bridge] connecting to Stream Deck on port ${port}`);
const ws = new ws_1.default(`ws://127.0.0.1:${port}`);
ws.on("open", () => {
    console.log("[claude-bridge] connected, registering plugin");
    ws.send(JSON.stringify({ event: registerEvent, uuid: pluginUUID }));
});
ws.on("message", (data) => {
    let msg;
    try {
        msg = JSON.parse(data.toString());
    }
    catch {
        return;
    }
    const { event, action = "", context = "", device = "", payload = {} } = msg;
    if (event === "keyDown" || event === "keyUp") {
        const settings = (payload.settings ?? {});
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
ws.on("error", (err) => {
    console.error("[claude-bridge] WebSocket error:", err.message);
});
ws.on("close", () => {
    console.log("[claude-bridge] disconnected, exiting.");
    process.exit(0);
});
