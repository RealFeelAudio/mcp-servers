"""
Claude Monitoring MCP Server
Tracks session age, tool call count, and fires alerts at configurable thresholds.
Threshold default: 60 minutes.
"""

import json
import os
from datetime import datetime, timezone
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("claude-monitor")

MONITORING_FILE = r"C:\streamdeck-setup\events\monitoring.json"
SESSION_GAP_MINUTES = 30      # gap that signals a new session
DEFAULT_THRESHOLD   = 60      # minutes before WARN alert
WARN_PCT            = 0.75    # warn at 75% of threshold (45 min for 1hr)


# ── helpers ──────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> dict:
    if not os.path.exists(MONITORING_FILE):
        return _empty_session()
    try:
        with open(MONITORING_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return _empty_session()


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(MONITORING_FILE), exist_ok=True)
    with open(MONITORING_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _empty_session() -> dict:
    return {
        "session_start": _now(),
        "last_event":    _now(),
        "tool_count":    0,
        "stop_count":    0,
        "threshold_minutes": DEFAULT_THRESHOLD,
        "alerts":        [],
        "events":        []
    }


def _elapsed_minutes(data: dict) -> float:
    try:
        start = datetime.fromisoformat(data["session_start"])
        now   = datetime.now(timezone.utc)
        return (now - start).total_seconds() / 60
    except Exception:
        return 0.0


def _health(elapsed: float, threshold: int) -> str:
    if elapsed >= threshold:
        return "START_NEW_SESSION"
    if elapsed >= threshold * WARN_PCT:
        return "WARN"
    return "OK"


# ── MCP tools ─────────────────────────────────────────────────────────────────

@mcp.tool()
def get_session_status() -> str:
    """Return current session stats: elapsed time, tool count, health status."""
    data    = _load()
    elapsed = _elapsed_minutes(data)
    thresh  = data.get("threshold_minutes", DEFAULT_THRESHOLD)
    health  = _health(elapsed, thresh)

    status = {
        "session_start":      data.get("session_start"),
        "elapsed_minutes":    round(elapsed, 1),
        "threshold_minutes":  thresh,
        "tool_count":         data.get("tool_count", 0),
        "stop_count":         data.get("stop_count", 0),
        "health":             health,
        "active_alerts":      len(data.get("alerts", [])),
    }
    return json.dumps(status, indent=2)


@mcp.tool()
def check_context_health() -> str:
    """
    Check if the session is approaching its time limit.
    Returns OK, WARN, or START_NEW_SESSION with a human-readable recommendation.
    Call this at the start of long tasks or when you want a health check.
    """
    data    = _load()
    elapsed = _elapsed_minutes(data)
    thresh  = data.get("threshold_minutes", DEFAULT_THRESHOLD)
    health  = _health(elapsed, thresh)
    remaining = max(0, thresh - elapsed)

    if health == "OK":
        msg = f"Session is healthy. {round(elapsed, 1)} min elapsed, {round(remaining, 1)} min remaining before threshold."
    elif health == "WARN":
        msg = (f"Session is getting long — {round(elapsed, 1)} min elapsed, "
               f"{round(remaining, 1)} min before the {thresh}-min threshold. "
               f"Consider wrapping up and starting a new session soon.")
    else:
        msg = (f"Session has exceeded the {thresh}-min threshold ({round(elapsed, 1)} min elapsed). "
               f"Recommend starting a new session now to avoid context compression issues.")

    return json.dumps({"health": health, "message": msg, "elapsed_minutes": round(elapsed, 1)}, indent=2)


@mcp.tool()
def mark_task_complete(description: str) -> str:
    """Call this when you finish a task to log it and notify the user."""
    data = _load()
    event = {
        "timestamp":   _now(),
        "type":        "task_complete",
        "description": description
    }
    data.setdefault("events", []).append(event)
    if len(data["events"]) > 200:
        data["events"] = data["events"][-200:]
    _save(data)

    # Fire toast notification
    _fire_toast(f"Task complete", description[:120])
    return f"Logged and notified: {description}"


@mcp.tool()
def get_active_alerts() -> str:
    """Return any uncleared alerts (session threshold, task complete, etc.)."""
    data = _load()
    alerts = data.get("alerts", [])
    return json.dumps(alerts, indent=2) if alerts else "No active alerts."


@mcp.tool()
def clear_alerts() -> str:
    """Dismiss all active alerts."""
    data = _load()
    count = len(data.get("alerts", []))
    data["alerts"] = []
    _save(data)
    return f"Cleared {count} alert(s)."


@mcp.tool()
def set_session_threshold(minutes: int) -> str:
    """Change the session age warning threshold. Default is 60 minutes."""
    if minutes < 5 or minutes > 480:
        return "Threshold must be between 5 and 480 minutes."
    data = _load()
    data["threshold_minutes"] = minutes
    _save(data)
    return f"Threshold set to {minutes} minutes."


@mcp.tool()
def get_session_events(count: int = 20) -> str:
    """Return the most recent session events (tool calls, stops, task completions)."""
    data   = _load()
    events = data.get("events", [])
    recent = events[-count:] if len(events) > count else events
    return json.dumps(recent, indent=2) if recent else "No events yet."


@mcp.tool()
def reset_session() -> str:
    """Manually reset the session clock (use when starting a fresh session)."""
    data = _empty_session()
    data["threshold_minutes"] = _load().get("threshold_minutes", DEFAULT_THRESHOLD)
    _save(data)
    return "Session reset."


# ── internal: used by log_event.py ───────────────────────────────────────────

def _fire_toast(title: str, message: str) -> None:
    """Fire a Windows toast notification via the toast.ps1 script."""
    import subprocess
    script = r"C:\streamdeck-setup\monitoring-mcp\toast.ps1"
    try:
        subprocess.Popen(
            ["powershell", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-File", script, "-Title", title, "-Message", message],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


if __name__ == "__main__":
    mcp.run()
