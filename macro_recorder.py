"""
Records keyboard and mouse input with timestamps for playback.
"""

import json
import time
import threading

try:
    from pynput import keyboard, mouse
    HAS_PYNPUT = True
except ImportError:
    HAS_PYNPUT = False


class MacroRecorder:
    """Records user input (keyboard + mouse) and saves for replay."""

    def __init__(self, capture_mouse=True, capture_keyboard=True):
        self.capture_mouse = capture_mouse
        self.capture_keyboard = capture_keyboard
        self.events = []
        self.recording = False
        self.start_time = 0
        self._kb_listener = None
        self._mouse_listener = None

    def _timestamp(self):
        return round(time.time() - self.start_time, 4)

    def _on_key_press(self, key):
        if not self.recording:
            return
        try:
            key_name = key.char if hasattr(key, 'char') and key.char else key.name
        except AttributeError:
            key_name = str(key)
        self.events.append({
            "time": self._timestamp(),
            "type": "key_down",
            "key": key_name
        })

    def _on_key_release(self, key):
        if not self.recording:
            return
        try:
            key_name = key.char if hasattr(key, 'char') and key.char else key.name
        except AttributeError:
            key_name = str(key)
        self.events.append({
            "time": self._timestamp(),
            "type": "key_up",
            "key": key_name
        })

    def _on_mouse_move(self, x, y):
        if not self.recording:
            return
        # Throttle mouse move events - only record every 50ms
        if self.events and self.events[-1]["type"] == "mouse_move":
            last_time = self.events[-1]["time"]
            if self._timestamp() - last_time < 0.05:
                return
        self.events.append({
            "time": self._timestamp(),
            "type": "mouse_move",
            "x": x,
            "y": y
        })

    def _on_mouse_click(self, x, y, button, pressed):
        if not self.recording:
            return
        self.events.append({
            "time": self._timestamp(),
            "type": "mouse_down" if pressed else "mouse_up",
            "x": x,
            "y": y,
            "button": button.name
        })

    def _on_mouse_scroll(self, x, y, dx, dy):
        if not self.recording:
            return
        self.events.append({
            "time": self._timestamp(),
            "type": "scroll",
            "x": x,
            "y": y,
            "dy": dy
        })

    def start(self):
        """Start recording input events."""
        if not HAS_PYNPUT:
            print("[ERROR] pynput not installed. Cannot record.")
            return

        self.events = []
        self.recording = True
        self.start_time = time.time()

        if self.capture_keyboard:
            self._kb_listener = keyboard.Listener(
                on_press=self._on_key_press,
                on_release=self._on_key_release
            )
            self._kb_listener.start()

        if self.capture_mouse:
            self._mouse_listener = mouse.Listener(
                on_move=self._on_mouse_move,
                on_click=self._on_mouse_click,
                on_scroll=self._on_mouse_scroll
            )
            self._mouse_listener.start()

        print(f"[REC] Recording started... ({len(self.events)} events)")

    def stop(self):
        """Stop recording."""
        self.recording = False
        if self._kb_listener:
            self._kb_listener.stop()
        if self._mouse_listener:
            self._mouse_listener.stop()
        print(f"[REC] Recording stopped. {len(self.events)} events captured.")

    def save(self, filepath):
        """Save recorded events to a JSON file."""
        data = {
            "version": 1,
            "duration": self.events[-1]["time"] if self.events else 0,
            "event_count": len(self.events),
            "events": self.events
        }
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
        print(f"[REC] Saved {len(self.events)} events to {filepath}")

    @staticmethod
    def load(filepath):
        """Load recorded events from a JSON file."""
        with open(filepath, "r") as f:
            data = json.load(f)
        return data["events"]
