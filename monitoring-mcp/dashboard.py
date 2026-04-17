"""
Claude Session Monitor — Dashboard
Run: python C:/streamdeck-setup/monitoring-mcp/dashboard.py
- Minimizes to system tray on close (right-click tray icon to quit)
- Sound alerts at 45 min (single tone) and 60 min (triple tone)
- Threshold slider built in — no need to ask Claude to change it
"""

import json
import os
import threading
import time
import winsound
from datetime import datetime, timezone
from tkinter import messagebox

import customtkinter as ctk
import pystray
from PIL import Image, ImageDraw

MONITORING_FILE = r"C:\streamdeck-setup\events\monitoring.json"
REFRESH_MS      = 5000
BLINK_SLOW_MS   = 900
BLINK_FAST_MS   = 280

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

COLOR_OK       = "#2ecc71"
COLOR_WARN     = "#f39c12"
COLOR_CRITICAL = "#e74c3c"
COLOR_DIM      = "#7f8c8d"
COLOR_BG       = "#1a1a2e"
COLOR_PANEL    = "#16213e"
COLOR_CARD     = "#0f3460"
COLOR_TEXT     = "#e0e0e0"
COLOR_SUBTEXT  = "#a0a0b0"
COLOR_INVIS    = COLOR_BG


# ── helpers ──────────────────────────────────────────────────────────────────

def load_data() -> dict:
    if not os.path.exists(MONITORING_FILE):
        return {}
    try:
        with open(MONITORING_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_data(data: dict) -> None:
    os.makedirs(os.path.dirname(MONITORING_FILE), exist_ok=True)
    with open(MONITORING_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def elapsed_seconds(session_start: str) -> float:
    try:
        start = datetime.fromisoformat(session_start)
        return max(0.0, (datetime.now(timezone.utc) - start).total_seconds())
    except Exception:
        return 0.0


def format_duration(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


def compute_health(elapsed_min: float, threshold: int) -> str:
    if elapsed_min >= threshold:
        return "CRITICAL"
    if elapsed_min >= threshold * 0.75:
        return "WARN"
    return "OK"


def health_color(health: str) -> str:
    return {"OK": COLOR_OK, "WARN": COLOR_WARN, "CRITICAL": COLOR_CRITICAL}.get(health, COLOR_DIM)


def health_badge(health: str) -> str:
    return {
        "OK":       "● OK",
        "WARN":     "⚠  WARN",
        "CRITICAL": "✖  START NEW SESSION",
    }.get(health, "— —")


def make_tray_image(color_hex: str) -> Image.Image:
    """Create a solid colored circle for the tray icon."""
    img  = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    r    = int(color_hex[1:3], 16)
    g    = int(color_hex[3:5], 16)
    b    = int(color_hex[5:7], 16)
    draw.ellipse([4, 4, 60, 60], fill=(r, g, b, 255))
    return img


def play_warn_sound():
    threading.Thread(
        target=lambda: winsound.Beep(880, 500),
        daemon=True
    ).start()


def play_critical_sound():
    def _beep():
        for _ in range(3):
            winsound.Beep(1200, 280)
            time.sleep(0.12)
    threading.Thread(target=_beep, daemon=True).start()


# ── app ──────────────────────────────────────────────────────────────────────

class MonitorApp(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("Claude Session Monitor")
        self.geometry("480x740")
        self.minsize(420, 640)
        self.resizable(True, True)
        self.configure(fg_color=COLOR_BG)

        self._health           = "OK"
        self._blink_on         = True
        self._blink_after      = None
        self._warn_sound_fired = False
        self._crit_sound_fired = False
        self._tray_icon        = None
        self._quitting         = False

        self._build_ui()
        self._setup_tray()
        self.protocol("WM_DELETE_WINDOW", self._minimize_to_tray)
        self._refresh()

    # ── tray ─────────────────────────────────────────────────────────────────

    def _setup_tray(self):
        menu = pystray.Menu(
            pystray.MenuItem("Show",          self._show_from_tray, default=True),
            pystray.MenuItem("Reset Session", lambda i, it: self.after(0, self._reset_session)),
            pystray.MenuItem("Clear Alerts",  lambda i, it: self.after(0, self._clear_alerts)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit",          self._quit_app),
        )
        self._tray_icon = pystray.Icon(
            "claude-monitor",
            make_tray_image(COLOR_OK),
            "Claude Monitor — OK",
            menu
        )
        threading.Thread(target=self._tray_icon.run, daemon=True).start()

    def _show_from_tray(self, icon=None, item=None):
        self.after(0, self.deiconify)
        self.after(0, self.lift)

    def _minimize_to_tray(self):
        self.withdraw()

    def _quit_app(self, icon=None, item=None):
        self._quitting = True
        if self._tray_icon:
            self._tray_icon.stop()
        self.after(0, self.destroy)

    def _update_tray(self, health: str):
        if self._tray_icon:
            self._tray_icon.icon  = make_tray_image(health_color(health))
            self._tray_icon.title = f"Claude Monitor — {health}"

    # ── layout ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        # header
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

        # timer block
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
            timer_frame, text="",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLOR_SUBTEXT
        )
        self.lbl_since.pack(pady=(0, 8))

        self.progress_bar = ctk.CTkProgressBar(
            timer_frame, height=10, corner_radius=5,
            fg_color=COLOR_CARD, progress_color=COLOR_OK
        )
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", padx=20, pady=(0, 6))

        self.lbl_progress = ctk.CTkLabel(
            timer_frame, text="0% of session limit  •  60 min remaining",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=COLOR_OK
        )
        self.lbl_progress.pack(pady=(0, 14))

        # stat cards
        stats_frame = ctk.CTkFrame(self, fg_color="transparent")
        stats_frame.pack(fill="x", padx=16, pady=6)
        stats_frame.columnconfigure((0, 1, 2), weight=1, uniform="col")

        self.card_tools     = self._stat_card(stats_frame, "TOOL CALLS", "0",      0)
        self.card_stops     = self._stat_card(stats_frame, "RESPONSES",  "0",      1)
        self.card_threshold = self._stat_card(stats_frame, "THRESHOLD",  "60 min", 2)

        # threshold slider
        slider_frame = ctk.CTkFrame(self, fg_color=COLOR_PANEL, corner_radius=12)
        slider_frame.pack(fill="x", padx=16, pady=6)

        slider_top = ctk.CTkFrame(slider_frame, fg_color="transparent")
        slider_top.pack(fill="x", padx=14, pady=(10, 4))

        ctk.CTkLabel(
            slider_top, text="SESSION THRESHOLD",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLOR_SUBTEXT
        ).pack(side="left")

        self.lbl_slider_val = ctk.CTkLabel(
            slider_top, text="60 min",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=COLOR_TEXT
        )
        self.lbl_slider_val.pack(side="right")

        self.threshold_slider = ctk.CTkSlider(
            slider_frame, from_=15, to=120,
            number_of_steps=21,
            fg_color=COLOR_CARD,
            progress_color=COLOR_OK,
            button_color=COLOR_TEXT,
            command=self._on_slider_drag
        )
        self.threshold_slider.set(60)
        self.threshold_slider.pack(fill="x", padx=14, pady=(0, 14))
        self.threshold_slider.bind("<ButtonRelease-1>", self._on_slider_release)

        # recent events
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

        # alerts
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
            command=self._clear_alerts
        ).pack(side="right")

        self.alerts_box = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=COLOR_PANEL,
            text_color=COLOR_WARN,
            corner_radius=8,
            height=68,
            state="disabled",
            wrap="word"
        )
        self.alerts_box.pack(fill="x", padx=16, pady=(0, 6))

        # footer
        footer = ctk.CTkFrame(self, fg_color=COLOR_PANEL, corner_radius=0)
        footer.pack(fill="x", side="bottom")

        ctk.CTkButton(
            footer, text="Reset Session",
            width=120, height=30,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color="#c0392b",
            hover_color="#922b21",
            command=self._reset_session
        ).pack(side="left", padx=14, pady=10)

        self.lbl_updated = ctk.CTkLabel(
            footer, text="",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=COLOR_SUBTEXT
        )
        self.lbl_updated.pack(side="right", padx=14, pady=10)

    def _stat_card(self, parent, label: str, value: str, col: int):
        card = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=10)
        card.grid(row=0, column=col, padx=4, sticky="nsew")
        ctk.CTkLabel(
            card, text=label,
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=COLOR_SUBTEXT
        ).pack(pady=(10, 2))
        val = ctk.CTkLabel(
            card, text=value,
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=COLOR_TEXT
        )
        val.pack(pady=(0, 10))
        return val

    # ── slider ───────────────────────────────────────────────────────────────

    def _on_slider_drag(self, value):
        mins = int(round(value / 5) * 5)
        self.lbl_slider_val.configure(text=f"{mins} min")
        self.card_threshold.configure(text=f"{mins} min")

    def _on_slider_release(self, event=None):
        mins = int(round(self.threshold_slider.get() / 5) * 5)
        self.threshold_slider.set(mins)
        data = load_data()
        if data:
            data["threshold_minutes"] = mins
            data["warn_acked"]        = False
            data["critical_acked"]    = False
            save_data(data)
        self._warn_sound_fired = False
        self._crit_sound_fired = False

    # ── actions ──────────────────────────────────────────────────────────────

    def _clear_alerts(self):
        data = load_data()
        if not data:
            return
        data["alerts"]         = []
        data["warn_acked"]     = True
        data["critical_acked"] = True
        save_data(data)
        self._warn_sound_fired = False
        self._crit_sound_fired = False
        self._update_display(schedule_next=False)

    def _reset_session(self):
        data   = load_data()
        thresh = data.get("threshold_minutes", 60) if data else 60
        save_data({
            "session_start":     datetime.now(timezone.utc).isoformat(),
            "last_event":        datetime.now(timezone.utc).isoformat(),
            "tool_count":        0,
            "stop_count":        0,
            "threshold_minutes": thresh,
            "alerts":            [],
            "warn_acked":        False,
            "critical_acked":    False,
            "events":            []
        })
        self._warn_sound_fired = False
        self._crit_sound_fired = False
        self._stop_blink()
        self._health = "OK"
        self.lbl_timer.configure(text_color=COLOR_TEXT)
        self._update_display(schedule_next=False)

    # ── blink ─────────────────────────────────────────────────────────────────

    def _stop_blink(self):
        if self._blink_after is not None:
            self.after_cancel(self._blink_after)
            self._blink_after = None

    def _start_blink(self, fast: bool = False):
        self._stop_blink()
        self._blink_on = True
        self._do_blink(fast)

    def _do_blink(self, fast: bool):
        color = health_color(self._health) if self._blink_on else COLOR_INVIS
        self.lbl_timer.configure(text_color=color)
        self._blink_on    = not self._blink_on
        interval          = BLINK_FAST_MS if fast else BLINK_SLOW_MS
        self._blink_after = self.after(interval, lambda: self._do_blink(fast))

    # ── refresh ──────────────────────────────────────────────────────────────

    def _refresh(self):
        self._update_display(schedule_next=True)

    def _update_display(self, schedule_next: bool = True):
        if self._quitting:
            return

        data = load_data()

        if not data:
            self.lbl_timer.configure(text="--:--", text_color=COLOR_DIM)
            self.lbl_health.configure(text="— no data —", text_color=COLOR_DIM)
            self.lbl_progress.configure(text="waiting for first event…", text_color=COLOR_DIM)
            self.progress_bar.set(0)
            self._stop_blink()
            if schedule_next:
                self.after(REFRESH_MS, self._refresh)
            return

        session_start = data.get("session_start", "")
        elapsed_sec   = elapsed_seconds(session_start)
        elapsed_min   = elapsed_sec / 60
        threshold     = data.get("threshold_minutes", 60)
        health        = compute_health(elapsed_min, threshold)
        hcolor        = health_color(health)

        # sync slider if threshold changed externally
        self.threshold_slider.set(threshold)
        self.lbl_slider_val.configure(text=f"{threshold} min")

        # sound alerts (fire once per crossing)
        if health == "CRITICAL" and not self._crit_sound_fired:
            play_critical_sound()
            self._crit_sound_fired = True
            self._warn_sound_fired = True
        elif health == "WARN" and not self._warn_sound_fired:
            play_warn_sound()
            self._warn_sound_fired = True

        # blink
        if health == "CRITICAL" and self._health != "CRITICAL":
            self._health = "CRITICAL"
            self._start_blink(fast=True)
        elif health == "WARN" and self._health != "WARN":
            self._health = "WARN"
            self._start_blink(fast=False)
        elif health == "OK" and self._health != "OK":
            self._health = "OK"
            self._stop_blink()
            self.lbl_timer.configure(text_color=COLOR_TEXT)

        # tray icon color
        self._update_tray(health)

        # timer
        self.lbl_timer.configure(text=format_duration(elapsed_sec))
        if health == "OK":
            self.lbl_timer.configure(text_color=COLOR_TEXT)

        # started label
        try:
            dt = datetime.fromisoformat(session_start).astimezone()
            self.lbl_since.configure(text=f"started {dt.strftime('%I:%M %p').lstrip('0')}")
        except Exception:
            self.lbl_since.configure(text="")

        # header badge
        self.lbl_health.configure(text=health_badge(health), text_color=hcolor)

        # progress bar
        pct_raw   = min(elapsed_min / threshold, 1.0)
        remaining = max(0.0, threshold - elapsed_min)
        pct_int   = int(pct_raw * 100)
        self.progress_bar.set(pct_raw)
        self.progress_bar.configure(progress_color=hcolor)
        remain_str = (f"{int(remaining * 60)} sec remaining"
                      if remaining < 1 else f"{round(remaining, 1)} min remaining")
        self.lbl_progress.configure(
            text=f"{pct_int}% of session limit  •  {remain_str}",
            text_color=hcolor
        )

        # stat cards
        self.card_tools.configure(text=str(data.get("tool_count", 0)))
        self.card_stops.configure(text=str(data.get("stop_count", 0)))
        self.card_threshold.configure(text=f"{threshold} min")

        # recent events
        events = data.get("events", [])[-12:]
        lines  = []
        for ev in reversed(events):
            ts = ev.get("timestamp", "")
            try:
                t = datetime.fromisoformat(ts).astimezone().strftime("%H:%M:%S")
            except Exception:
                t = ts[-8:] if len(ts) >= 8 else ts
            etype  = ev.get("type", "")
            detail = ev.get("tool", ev.get("stop_reason", ev.get("description", "")))
            lines.append(f"  {t}  {etype:<12}  {detail}")
        self._set_textbox(self.events_box, "\n".join(lines) or "  No events yet.")

        # alerts
        alerts = data.get("alerts", [])
        if alerts:
            alines = [f"  {'✖' if a.get('type') == 'session_critical' else '⚠'}  {a.get('message', '')}"
                      for a in alerts]
            self._set_textbox(self.alerts_box, "\n".join(alines))
            crit = any(a.get("type") == "session_critical" for a in alerts)
            self.alerts_box.configure(text_color=COLOR_CRITICAL if crit else COLOR_WARN)
        else:
            self._set_textbox(self.alerts_box, "  No active alerts.")
            self.alerts_box.configure(text_color=COLOR_OK)

        self.lbl_updated.configure(text=f"updated {datetime.now().strftime('%H:%M:%S')}")

        if schedule_next:
            self.after(REFRESH_MS, self._refresh)

    @staticmethod
    def _set_textbox(box: ctk.CTkTextbox, text: str):
        box.configure(state="normal")
        box.delete("1.0", "end")
        box.insert("1.0", text)
        box.configure(state="disabled")


# ── entry ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = MonitorApp()
    app.mainloop()
