"""
Plays back recorded macros and executes scripted macro sequences.
"""

import time
import threading
from input_simulator import InputSimulator


class MacroPlayer:
    """Plays back recorded or scripted macro sequences."""

    def __init__(self, input_sim: InputSimulator):
        self.input = input_sim
        self.playing = False
        self.paused = False
        self._thread = None
        self._speed = 1.0

    def set_speed(self, multiplier):
        """Set playback speed (1.0 = normal, 2.0 = double speed, 0.5 = half)."""
        self._speed = max(0.1, multiplier)

    def play_recording(self, events, loop=False, loop_count=1):
        """Play back a list of recorded events."""
        self.playing = True
        self.paused = False

        def _run():
            count = 0
            while self.playing and (loop or count < loop_count):
                prev_time = 0
                for event in events:
                    if not self.playing:
                        break
                    while self.paused:
                        time.sleep(0.1)
                        if not self.playing:
                            return

                    delay = (event["time"] - prev_time) / self._speed
                    if delay > 0:
                        time.sleep(delay)
                    prev_time = event["time"]

                    self._execute_event(event)

                count += 1

            self.playing = False

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def _execute_event(self, event):
        """Execute a single recorded event."""
        etype = event["type"]

        if etype == "key_down":
            self.input.key_down(event["key"])
        elif etype == "key_up":
            self.input.key_up(event["key"])
        elif etype == "mouse_move":
            self.input.move_mouse(event["x"], event["y"], duration=0)
        elif etype == "mouse_down":
            self.input.move_mouse(event["x"], event["y"], duration=0)
            self.input.mouse_down(event.get("button", "left"))
        elif etype == "mouse_up":
            self.input.mouse_up(event.get("button", "left"))
        elif etype == "scroll":
            self.input.scroll(event.get("dy", 0))

    def play_sequence(self, actions, loop=False, loop_count=1):
        """
        Play a scripted action sequence.

        Each action is a dict:
          {"action": "press", "key": "w", "duration": 0.5}
          {"action": "click", "x": 100, "y": 200}
          {"action": "wait", "duration": 1.0}
          {"action": "move", "x": 500, "y": 300}
          {"action": "type", "text": "hello"}
          {"action": "combo", "keys": ["ctrl", "a"]}
          {"action": "hold", "key": "w", "duration": 2.0}
          {"action": "scroll", "amount": 3}
        """
        self.playing = True
        self.paused = False

        def _run():
            count = 0
            while self.playing and (loop or count < loop_count):
                for action in actions:
                    if not self.playing:
                        break
                    while self.paused:
                        time.sleep(0.1)
                        if not self.playing:
                            return
                    self._execute_action(action)
                count += 1
            self.playing = False

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def _execute_action(self, action):
        """Execute a single scripted action."""
        act = action["action"]
        delay = action.get("delay", 0)

        if act == "press":
            self.input.press_key(action["key"], action.get("duration"))
        elif act == "hold":
            self.input.hold_key(action["key"], action.get("duration", 1.0))
        elif act == "click":
            self.input.click(action.get("x"), action.get("y"), action.get("button", "left"))
        elif act == "right_click":
            self.input.right_click(action.get("x"), action.get("y"))
        elif act == "double_click":
            self.input.double_click(action.get("x"), action.get("y"))
        elif act == "move":
            self.input.move_mouse(action["x"], action["y"], action.get("duration", 0.1))
        elif act == "move_relative":
            self.input.move_mouse_relative(action["dx"], action["dy"])
        elif act == "type":
            self.input.type_text(action["text"], action.get("interval", 0.05))
        elif act == "combo":
            self.input.key_combo(*action["keys"])
        elif act == "wait":
            time.sleep(action.get("duration", 1.0) / self._speed)
        elif act == "scroll":
            self.input.scroll(action.get("amount", 1))

        if delay > 0:
            time.sleep(delay / self._speed)

    def stop(self):
        """Stop playback."""
        self.playing = False

    def pause(self):
        """Pause playback."""
        self.paused = True

    def resume(self):
        """Resume paused playback."""
        self.paused = False
