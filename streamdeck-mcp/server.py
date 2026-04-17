"""
Stream Deck MCP Server
Exposes Stream Deck button events to Claude via MCP tools.
Events are written by the Stream Deck plugin to C:\streamdeck-setup\events\button_events.json
"""

import json
import os
from datetime import datetime
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("streamdeck-bridge")

EVENTS_FILE = r"C:\streamdeck-setup\events\button_events.json"
MAX_EVENTS = 200


def _ensure_events_file() -> None:
    os.makedirs(os.path.dirname(EVENTS_FILE), exist_ok=True)
    if not os.path.exists(EVENTS_FILE):
        with open(EVENTS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)


def _read_events() -> list:
    _ensure_events_file()
    try:
        with open(EVENTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def _append_event(event: dict) -> None:
    events = _read_events()
    event["timestamp"] = datetime.utcnow().isoformat() + "Z"
    events.append(event)
    if len(events) > MAX_EVENTS:
        events = events[-MAX_EVENTS:]
    with open(EVENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2)


@mcp.tool()
def get_recent_events(count: int = 20) -> str:
    """Return the most recent Stream Deck button events as JSON."""
    try:
        events = _read_events()
        recent = events[-count:] if len(events) > count else events
        return json.dumps(recent, indent=2)
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def get_event_count() -> str:
    """Return total number of events currently logged."""
    try:
        events = _read_events()
        return str(len(events))
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def get_events_since(iso_timestamp: str) -> str:
    """Return all events that occurred after the given ISO timestamp (e.g. 2025-01-01T00:00:00Z)."""
    try:
        events = _read_events()
        filtered = [e for e in events if e.get("timestamp", "") > iso_timestamp]
        return json.dumps(filtered, indent=2)
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def get_last_button_press() -> str:
    """Return the most recent keyDown event, or a message if none exist."""
    try:
        events = _read_events()
        presses = [e for e in events if e.get("type") == "keyDown"]
        if not presses:
            return "No button presses recorded yet."
        return json.dumps(presses[-1], indent=2)
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def clear_event_log() -> str:
    """Clear all recorded Stream Deck events from the log."""
    try:
        _ensure_events_file()
        with open(EVENTS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)
        return "Event log cleared."
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def log_custom_event(label: str, result: str = "", error: str = "") -> str:
    """Log a custom event to the Stream Deck event log."""
    try:
        _append_event({"type": "custom", "label": label, "result": result, "error": error})
        return f"Logged: {label}"
    except Exception as e:
        return f"Error: {e}"


if __name__ == "__main__":
    mcp.run()
