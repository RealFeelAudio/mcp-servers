"""
Stream Deck Event Watcher
Monitors the button_events.json file and prints new events to the terminal in real time.
Run this in a separate terminal: python C:\streamdeck-setup\streamdeck-mcp\watcher.py
"""

import json
import os
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

EVENTS_FILE = r"C:\streamdeck-setup\events\button_events.json"
POLL_INTERVAL = 0.5


class EventFileHandler(FileSystemEventHandler):
    def __init__(self):
        self._last_count = 0
        self._load_initial_count()

    def _load_initial_count(self):
        try:
            with open(EVENTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._last_count = len(data) if isinstance(data, list) else 0
        except Exception:
            self._last_count = 0

    def on_modified(self, event):
        if not event.is_directory and event.src_path.endswith("button_events.json"):
            self._check_new_events()

    def _check_new_events(self):
        try:
            with open(EVENTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                return
            if len(data) > self._last_count:
                new_events = data[self._last_count:]
                for ev in new_events:
                    ts = ev.get("timestamp", "")
                    etype = ev.get("type", "")
                    label = ev.get("label", "")
                    action = ev.get("action", "")
                    print(f"[{ts}] {etype:10s}  label={label!r}  action={action}")
                self._last_count = len(data)
        except Exception as e:
            print(f"[watcher error] {e}")


def main():
    events_dir = os.path.dirname(EVENTS_FILE)
    os.makedirs(events_dir, exist_ok=True)
    if not os.path.exists(EVENTS_FILE):
        with open(EVENTS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)

    print(f"Watching {EVENTS_FILE} for new Stream Deck events...")
    print("Press Ctrl+C to stop.\n")

    handler = EventFileHandler()
    observer = Observer()
    observer.schedule(handler, path=events_dir, recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print("\nStopping watcher.")
    finally:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    main()
