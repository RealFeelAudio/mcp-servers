"""
Hook event logger — called by Claude Code PostToolUse and Stop hooks.
Reads event JSON from stdin, appends to monitoring.json, checks threshold.
"""

import json
import os
import sys
import subprocess
from datetime import datetime, timezone

MONITORING_FILE  = r"C:\streamdeck-setup\events\monitoring.json"
TOAST_SCRIPT     = r"C:\streamdeck-setup\monitoring-mcp\toast.ps1"
SESSION_GAP_MIN  = 30
MAX_EVENTS       = 200
DEFAULT_THRESHOLD = 60


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def elapsed_minutes(session_start: str) -> float:
    try:
        start = datetime.fromisoformat(session_start)
        return (datetime.now(timezone.utc) - start).total_seconds() / 60
    except Exception:
        return 0.0


def load() -> dict:
    if not os.path.exists(MONITORING_FILE):
        return new_session()
    try:
        with open(MONITORING_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return new_session()


def save(data: dict) -> None:
    os.makedirs(os.path.dirname(MONITORING_FILE), exist_ok=True)
    with open(MONITORING_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def new_session() -> dict:
    return {
        "session_start":     now(),
        "last_event":        now(),
        "tool_count":        0,
        "stop_count":        0,
        "threshold_minutes": DEFAULT_THRESHOLD,
        "alerts":            [],
        "events":            []
    }


def toast(title: str, message: str) -> None:
    try:
        subprocess.Popen(
            ["powershell", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-File", TOAST_SCRIPT, "-Title", title, "-Message", message],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def main():
    # Read hook payload from stdin
    try:
        raw   = sys.stdin.read()
        hook  = json.loads(raw) if raw.strip() else {}
    except Exception:
        hook = {}

    event_type = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    data = load()

    # Detect new session: gap > SESSION_GAP_MIN since last event
    try:
        last = datetime.fromisoformat(data.get("last_event", now()))
        gap  = (datetime.now(timezone.utc) - last).total_seconds() / 60
        if gap > SESSION_GAP_MIN:
            thresh = data.get("threshold_minutes", DEFAULT_THRESHOLD)
            data   = new_session()
            data["threshold_minutes"] = thresh
    except Exception:
        pass

    data["last_event"] = now()

    # Log the event
    entry = {"timestamp": now(), "type": event_type}

    if event_type == "post_tool":
        tool_name = hook.get("tool_name", "")
        entry["tool"] = tool_name
        data["tool_count"] = data.get("tool_count", 0) + 1

    elif event_type == "stop":
        data["stop_count"] = data.get("stop_count", 0) + 1
        stop_reason = hook.get("stop_reason", "end_turn")
        entry["stop_reason"] = stop_reason
        # Toast for task complete
        toast("Claude finished", f"Task complete — {data['tool_count']} tool calls this session")

    data.setdefault("events", []).append(entry)
    if len(data["events"]) > MAX_EVENTS:
        data["events"] = data["events"][-MAX_EVENTS:]

    # Check threshold
    thresh  = data.get("threshold_minutes", DEFAULT_THRESHOLD)
    elapsed = elapsed_minutes(data["session_start"])
    alerts  = data.get("alerts", [])

    warn_threshold = thresh * 0.75
    already_warned = any(a.get("type") == "session_warn" for a in alerts)
    already_critical = any(a.get("type") == "session_critical" for a in alerts)

    if elapsed >= thresh and not already_critical:
        alert = {"type": "session_critical", "timestamp": now(),
                 "message": f"Session exceeded {thresh} min ({round(elapsed,1)} min elapsed). Start a new session."}
        alerts.append(alert)
        toast("Start a new Claude session", f"{round(elapsed,1)} min elapsed — threshold reached")

    elif elapsed >= warn_threshold and not already_warned:
        alert = {"type": "session_warn", "timestamp": now(),
                 "message": f"Session at {round(elapsed,1)} min — {thresh}-min threshold approaching."}
        alerts.append(alert)
        toast("Claude session check", f"{round(elapsed,1)} min in — consider wrapping up soon")

    data["alerts"] = alerts
    save(data)


if __name__ == "__main__":
    main()
