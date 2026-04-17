"""
Hook event logger — called by Claude Code PostToolUse and Stop hooks.
Reads event JSON from stdin, appends to monitoring.json, checks threshold.
"""

import json
import os
import sys
import subprocess
from datetime import datetime, timezone

MONITORING_FILE   = r"C:\streamdeck-setup\events\monitoring.json"
TOAST_SCRIPT      = r"C:\streamdeck-setup\monitoring-mcp\toast.ps1"
SESSION_GAP_MIN   = 30
MAX_EVENTS        = 200
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
        "warn_acked":        False,
        "critical_acked":    False,
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
    try:
        raw  = sys.stdin.read()
        hook = json.loads(raw) if raw.strip() else {}
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
        entry["stop_reason"] = hook.get("stop_reason", "end_turn")
        toast("Claude finished", f"Task complete — {data['tool_count']} tool calls this session")

    data.setdefault("events", []).append(entry)
    if len(data["events"]) > MAX_EVENTS:
        data["events"] = data["events"][-MAX_EVENTS:]

    # Check threshold — respect acked flags so Clear All stays cleared
    thresh   = data.get("threshold_minutes", DEFAULT_THRESHOLD)
    elapsed  = elapsed_minutes(data["session_start"])
    alerts   = data.get("alerts", [])
    warn_pct = thresh * 0.75

    warn_acked     = data.get("warn_acked", False)
    critical_acked = data.get("critical_acked", False)

    if elapsed >= thresh and not critical_acked:
        alert = {
            "type":    "session_critical",
            "timestamp": now(),
            "message": f"Session exceeded {thresh} min ({round(elapsed, 1)} min elapsed). Start a new session."
        }
        # Replace any existing critical alert
        alerts = [a for a in alerts if a.get("type") != "session_critical"]
        alerts.append(alert)
        toast("Start a new Claude session", f"{round(elapsed, 1)} min elapsed — threshold reached")

    elif elapsed >= warn_pct and not warn_acked and not critical_acked:
        already_warned = any(a.get("type") == "session_warn" for a in alerts)
        if not already_warned:
            pct = int((elapsed / thresh) * 100)
            alert = {
                "type":    "session_warn",
                "timestamp": now(),
                "message": f"You've used ~{pct}% of your session limit ({round(elapsed, 1)} of {thresh} min)."
            }
            alerts.append(alert)
            toast("Claude session check", f"{pct}% of session limit used — consider wrapping up")

    data["alerts"] = alerts
    save(data)


if __name__ == "__main__":
    main()
