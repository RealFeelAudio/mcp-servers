"""
Claude Session Monitor — Dashboard
Run: python C:\streamdeck-setup\monitoring-mcp\dashboard.py
Reads C:\streamdeck-setup\events\monitoring.json and auto-refreshes every 5s.
"""

import json
import os
import subprocess
import tkinter as tk
from datetime import datetime, timezone
from tkinter import messagebox

import customtkinter as ctk

MONITORING_FILE = r"C:\streamdeck-setup\events\monitoring.json"
REFRESH_MS      = 5000
LOG_EVENT_PY    = r"C:\streamdeck-setup\monitoring-mcp\log_event.py"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ── colours ──────────────────────────────────────────────────────────────────
COLOR_OK       = "#2ecc71"
COLOR_WARN     = "#f39c12"
COLOR_CRITICAL = "#e74c3c"
COLOR_DIM      = "#7f8c8d"
COLOR_BG       = "#1a1a2e"
COLOR_PANEL    = "#16213e"
COLOR_CARD     = "#0f3460"
COLOR_TEXT     = "#e0e0e0"
COLOR_SUBTEXT  = "#a0a0b0"


def load_data() -> dict:
    if not os.path.exists(MONITORING_FILE):
        return {}
    try:
        with open(MONITORING_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def elapsed_seconds(session_start: str) -> float:
    try:
        start = datetime.fromisoformat(session_start)
        return (datetime.now(timezone.utc) - start).total_seconds()
    except Exception:
        return 0.0


def format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def health_color(health: str) -> str:
    return {
        "OK":               COLOR_OK,
        "WARN":             COLOR_WARN,
        "START_NEW_SESSION": COLOR_CRITICAL,
    }.get(health, COLOR_DIM)


def health_label(health: str) -> str:
    return {
        "OK":               "● OK",
        "WARN":             "⚠  WARN",
        "START_NEW_SESSION": "✖  NEW SESSION",
    }.get(health, "— —")


def compute_health(elapsed_min: float, threshold: int) -> str:
    if elapsed_min >= threshold:
        return "START_NEW_SESSION"
    if elapsed_min >= threshold * 0.75:
        return "WARN"
    return "OK"


def call_reset():
    try:
        data = load_data()
        fresh = {
            "session_start":     datetime.now(timezone.utc).isoformat(),
            "last_event":        datetime.now(timezone.utc).isoformat(),
            "tool_count":        0,
            "stop_count":        0,
            "threshold_minutes": data.get("threshold_minutes", 60),
            "alerts":            [],
            "events":            []
        }
        with open(MONITORING_FILE, "w", encoding="utf-8") as f:
            json.dump(fresh, f, indent=2)
    except Exception as e:
        messagebox.showerror("Error", str(e))


def call_clear_alerts():
    try:
        data = load_data()
        data["alerts"] = []
        with open(MONITORING_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        messagebox.showerror("Error", str(e))


# ── main window ──────────────────────────────────────────────────────────────

class MonitorApp(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("Claude Session Monitor")
        self.geometry("480x640")
        self.minsize(420, 560)
        self.resizable(True, True)
        self.configure(fg_color=COLOR_BG)

        self._build_ui()
        self._refresh()

    # ── layout ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        pad = {"padx": 16, "pady": 6}

        # ── header ──
        header = ctk.CTkFrame(self, fg_color=COLOR_PANEL, corner_radius=0)
        header.pack(fill="x")

        ctk.CTkLabel(
            header, text="CLAUDE SESSION MONITOR",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=COLOR_SUBTEXT
        ).pack(side="left", padx=16, pady=12)

        self.lbl_health = ctk.CTkLabel(
            header, text="● OK",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=COLOR_OK
        )
        self.lbl_health.pack(side="right", padx=16, pady=12)

        # ── timer block ──
        timer_frame = ctk.CTkFrame(self, fg_color=COLOR_PANEL, corner_radius=12)
        timer_frame.pack(fill="x", padx=16, pady=(14, 6))

        ctk.CTkLabel(
            timer_frame, text="SESSION TIME",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLOR_SUBTEXT
        ).pack(pady=(14, 2))

        self.lbl_timer = ctk.CTkLabel(
            timer_frame, text="00:00",
            font=ctk.CTkFont(family="Segoe UI", size=52, weight="bold"),
            text_color=COLOR_TEXT
        )
        self.lbl_timer.pack(pady=(0, 2))

        self.lbl_since = ctk.CTkLabel(
            timer_frame, text="started —",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLOR_SUBTEXT
        )
        self.lbl_since.pack(pady=(0, 14))

        # ── stats row ──
        stats_frame = ctk.CTkFrame(self, fg_color="transparent")
        stats_frame.pack(fill="x", padx=16, pady=6)
        stats_frame.columnconfigure((0, 1, 2), weight=1, uniform="col")

        self.card_tools     = self._stat_card(stats_frame, "TOOL CALLS", "0", 0)
        self.card_stops     = self._stat_card(stats_frame, "RESPONSES",  "0", 1)
        self.card_threshold = self._stat_card(stats_frame, "THRESHOLD",  "60 min", 2)

        # ── recent events ──
        events_frame = ctk.CTkFrame(self, fg_color=COLOR_PANEL, corner_radius=12)
        events_frame.pack(fill="both", expand=True, padx=16, pady=6)

        ctk.CTkLabel(
            events_frame, text="RECENT EVENTS",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLOR_SUBTEXT
        ).pack(anchor="w", padx=14, pady=(10, 4))

        self.events_box = ctk.CTkTextbox(
            events_frame,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=COLOR_CARD,
            text_color=COLOR_TEXT,
            corner_radius=8,
            state="disabled",
            wrap="none"
        )
        self.events_box.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # ── alerts ──
        alerts_header = ctk.CTkFrame(self, fg_color="transparent")
        alerts_header.pack(fill="x", padx=16, pady=(6, 2))

        ctk.CTkLabel(
            alerts_header, text="ALERTS",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLOR_SUBTEXT
        ).pack(side="left")

        ctk.CTkButton(
            alerts_header, text="Clear All",
            width=80, height=26,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=COLOR_CARD,
            hover_color="#1a4a7a",
            command=lambda: (call_clear_alerts(), self._refresh())
        ).pack(side="right")

        self.alerts_box = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=COLOR_PANEL,
            text_color=COLOR_WARN,
            corner_radius=8,
            height=72,
            state="disabled",
            wrap="word"
        )
        self.alerts_box.pack(fill="x", padx=16, pady=(0, 6))

        # ── footer ──
        footer = ctk.CTkFrame(self, fg_color=COLOR_PANEL, corner_radius=0)
        footer.pack(fill="x", side="bottom")

        ctk.CTkButton(
            footer, text="Reset Session",
            width=120, height=30,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color="#c0392b",
            hover_color="#922b21",
            command=lambda: (call_reset(), self._refresh())
        ).pack(side="left", padx=14, pady=10)

        self.lbl_updated = ctk.CTkLabel(
            footer, text="",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=COLOR_SUBTEXT
        )
        self.lbl_updated.pack(side="right", padx=14, pady=10)

    def _stat_card(self, parent, label: str, value: str, col: int):
        card = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=10)
        card.grid(row=0, column=col, padx=4, pady=0, sticky="nsew")

        ctk.CTkLabel(
            card, text=label,
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=COLOR_SUBTEXT
        ).pack(pady=(10, 2))

        val_lbl = ctk.CTkLabel(
            card, text=value,
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=COLOR_TEXT
        )
        val_lbl.pack(pady=(0, 10))
        return val_lbl

    # ── refresh ──────────────────────────────────────────────────────────────

    def _refresh(self):
        data = load_data()

        if not data:
            self.lbl_timer.configure(text="--:--")
            self.lbl_since.configure(text="no data yet")
            self.lbl_health.configure(text="— —", text_color=COLOR_DIM)
            self.after(REFRESH_MS, self._refresh)
            return

        # elapsed + health
        session_start = data.get("session_start", "")
        elapsed_sec   = elapsed_seconds(session_start)
        elapsed_min   = elapsed_sec / 60
        threshold     = data.get("threshold_minutes", 60)
        health        = compute_health(elapsed_min, threshold)

        # timer
        self.lbl_timer.configure(
            text=format_duration(elapsed_sec),
            text_color=health_color(health)
        )

        # since label
        try:
            dt = datetime.fromisoformat(session_start).astimezone()
            self.lbl_since.configure(text=f"started {dt.strftime('%I:%M %p').lstrip('0')}")
        except Exception:
            self.lbl_since.configure(text="")

        # header health badge
        self.lbl_health.configure(
            text=health_label(health),
            text_color=health_color(health)
        )

        # stat cards
        self.card_tools.configure(text=str(data.get("tool_count", 0)))
        self.card_stops.configure(text=str(data.get("stop_count", 0)))
        self.card_threshold.configure(text=f"{threshold} min")

        # recent events
        events = data.get("events", [])[-12:]
        lines = []
        for ev in reversed(events):
            ts = ev.get("timestamp", "")
            try:
                t = datetime.fromisoformat(ts).astimezone().strftime("%H:%M:%S")
            except Exception:
                t = ts[-8:] if len(ts) >= 8 else ts
            etype = ev.get("type", "")
            detail = ev.get("tool", ev.get("stop_reason", ev.get("description", "")))
            lines.append(f"  {t}  {etype:<12}  {detail}")

        self._set_textbox(self.events_box, "\n".join(lines) if lines else "  No events yet.")

        # alerts
        alerts = data.get("alerts", [])
        if alerts:
            alert_lines = []
            for a in alerts:
                icon = "✖" if a.get("type") == "session_critical" else "⚠"
                alert_lines.append(f"  {icon}  {a.get('message', '')}")
            self._set_textbox(self.alerts_box, "\n".join(alert_lines))
            self.alerts_box.configure(text_color=COLOR_CRITICAL if any(
                a.get("type") == "session_critical" for a in alerts) else COLOR_WARN)
        else:
            self._set_textbox(self.alerts_box, "  No active alerts.")
            self.alerts_box.configure(text_color=COLOR_OK)

        # footer timestamp
        self.lbl_updated.configure(
            text=f"updated {datetime.now().strftime('%H:%M:%S')}"
        )

        self.after(REFRESH_MS, self._refresh)

    @staticmethod
    def _set_textbox(box: ctk.CTkTextbox, text: str):
        box.configure(state="normal")
        box.delete("1.0", "end")
        box.insert("1.0", text)
        box.configure(state="disabled")


# ── entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = MonitorApp()
    app.mainloop()
