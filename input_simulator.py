"""
Input simulation for Monsters and Memories.
Uses pydirectinput for game-compatible input, falls back to pyautogui.
Integrates humanization to avoid the game's InputPatternDetector and BotBehaviorDetector.
"""

import time

from humanizer import Humanizer

# Try importing Windows-specific libraries
# These will only work on Windows - graceful fallback for dev on other platforms
try:
    import pydirectinput
    pydirectinput.PAUSE = 0.01
    HAS_DIRECTINPUT = True
except ImportError:
    HAS_DIRECTINPUT = False

try:
    import pyautogui
    pyautogui.PAUSE = 0.01
    pyautogui.FAILSAFE = True
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False


class InputSimulator:
    """Handles keyboard and mouse input simulation for the game."""

    def __init__(self, method="directinput", hold_duration=0.05, humanize=True, humanize_intensity=0.5):
        self.method = method
        self.hold_duration = hold_duration
        self.humanizer = Humanizer(humanize_intensity) if humanize else None

        if method == "directinput" and not HAS_DIRECTINPUT:
            print("[WARN] pydirectinput not available, falling back to pyautogui")
            self.method = "pyautogui"

        if self.method == "pyautogui" and not HAS_PYAUTOGUI:
            raise RuntimeError("No input library available. Install pydirectinput or pyautogui.")

    def _humanize_delay(self, base=0.05, action_name=None):
        if not self.humanizer:
            time.sleep(base)
            return
        if action_name:
            time.sleep(self.humanizer.action_delay(action_name, base))
        else:
            time.sleep(self.humanizer.delay(base))

    def _humanize_hold(self, base=0.05):
        if self.humanizer:
            return self.humanizer.key_hold_duration(base)
        return base

    # --- Keyboard ---

    def press_key(self, key, duration=None):
        """Press and release a key."""
        duration = self._humanize_hold(duration or self.hold_duration)
        if self.method == "directinput":
            pydirectinput.keyDown(key)
            time.sleep(duration)
            pydirectinput.keyUp(key)
        else:
            pyautogui.keyDown(key)
            time.sleep(duration)
            pyautogui.keyUp(key)

    def hold_key(self, key, duration):
        """Hold a key for a specified duration (seconds)."""
        if self.humanizer:
            duration = self.humanizer.movement_duration(duration)
        if self.method == "directinput":
            pydirectinput.keyDown(key)
            time.sleep(duration)
            pydirectinput.keyUp(key)
        else:
            pyautogui.keyDown(key)
            time.sleep(duration)
            pyautogui.keyUp(key)

    def key_down(self, key):
        """Press a key down (without releasing)."""
        if self.method == "directinput":
            pydirectinput.keyDown(key)
        else:
            pyautogui.keyDown(key)

    def key_up(self, key):
        """Release a key."""
        if self.method == "directinput":
            pydirectinput.keyUp(key)
        else:
            pyautogui.keyUp(key)

    def type_text(self, text, interval=0.05):
        """Type a string of text."""
        for char in text:
            if self.humanizer:
                interval = self.humanizer.typing_interval(interval)
            if self.method == "directinput":
                pydirectinput.press(char)
            else:
                pyautogui.press(char)
            time.sleep(interval)

    def key_combo(self, *keys):
        """Press a key combination (e.g., key_combo('ctrl', 'a'))."""
        if self.method == "directinput":
            for key in keys:
                pydirectinput.keyDown(key)
                time.sleep(self._humanize_hold(0.02))
            time.sleep(self._humanize_hold(self.hold_duration))
            for key in reversed(keys):
                pydirectinput.keyUp(key)
                time.sleep(self._humanize_hold(0.02))
        else:
            pyautogui.hotkey(*keys)

    # --- Mouse ---

    def move_mouse(self, x, y, duration=0.1, humanize_path=True):
        """Move mouse to absolute position."""
        if self.humanizer and humanize_path and HAS_PYAUTOGUI:
            current = self.get_mouse_position()
            points = self.humanizer.mouse_path(current[0], current[1], x, y)
            step_delay = max(0.005, duration / len(points)) if points else 0
            for px, py in points:
                if self.method == "directinput":
                    pydirectinput.moveTo(px, py)
                else:
                    pyautogui.moveTo(px, py, duration=0)
                time.sleep(step_delay)
        else:
            if self.method == "directinput":
                pydirectinput.moveTo(x, y)
            else:
                pyautogui.moveTo(x, y, duration=duration)

    def move_mouse_relative(self, dx, dy, duration=0.1):
        """Move mouse relative to current position."""
        if self.method == "directinput":
            pydirectinput.moveRel(dx, dy)
        else:
            pyautogui.moveRel(dx, dy, duration=duration)

    def click(self, x=None, y=None, button="left"):
        """Click at position (or current position if x,y not given)."""
        if self.humanizer and x is not None and y is not None:
            x, y = self.humanizer.mouse_offset(x, y)
        if self.method == "directinput":
            if x is not None and y is not None:
                pydirectinput.click(x, y, button=button)
            else:
                pydirectinput.click(button=button)
        else:
            if x is not None and y is not None:
                pyautogui.click(x, y, button=button)
            else:
                pyautogui.click(button=button)

    def double_click(self, x=None, y=None):
        """Double-click at position."""
        self.click(x, y)
        time.sleep(self._humanize_hold(0.08))
        self.click(x, y)

    def right_click(self, x=None, y=None):
        """Right-click at position."""
        self.click(x, y, button="right")

    def mouse_down(self, button="left"):
        """Press mouse button down."""
        if self.method == "directinput":
            pydirectinput.mouseDown(button=button)
        else:
            pyautogui.mouseDown(button=button)

    def mouse_up(self, button="left"):
        """Release mouse button."""
        if self.method == "directinput":
            pydirectinput.mouseUp(button=button)
        else:
            pyautogui.mouseUp(button=button)

    def scroll(self, amount):
        """Scroll mouse wheel. Positive = up, negative = down."""
        if self.humanizer:
            amount = self.humanizer.scroll_amount(amount)
        if self.method == "directinput":
            pydirectinput.scroll(amount)
        else:
            pyautogui.scroll(amount)

    def get_mouse_position(self):
        """Get current mouse position."""
        if HAS_PYAUTOGUI:
            return pyautogui.position()
        return (0, 0)

    # --- MnM-Specific Actions ---

    def press_ability(self, slot_index, key):
        """Press an ability key with anti-detection delay."""
        if self.humanizer:
            time.sleep(self.humanizer.ability_delay(slot_index))
        self.press_key(key)

    def move_forward(self, duration=1.0):
        """Hold W to move forward with humanized duration."""
        self.hold_key("w", duration)

    def move_backward(self, duration=1.0):
        """Hold S to move backward."""
        self.hold_key("s", duration)

    def strafe_left(self, duration=1.0):
        """Hold Q/A to strafe left."""
        self.hold_key("a", duration)

    def strafe_right(self, duration=1.0):
        """Hold D/E to strafe right."""
        self.hold_key("d", duration)

    def turn(self, dx, duration=0.5):
        """Turn camera by holding right mouse and moving mouse."""
        self.mouse_down("right")
        time.sleep(self._humanize_hold(0.05))
        steps = max(5, abs(dx) // 10)
        step_dx = dx / steps
        for _ in range(steps):
            self.move_mouse_relative(int(step_dx), 0)
            time.sleep(duration / steps)
        self.mouse_up("right")

    def auto_run_toggle(self):
        """Toggle auto-run (typically Num Lock or R)."""
        self.press_key("numlock")

    def maybe_idle(self):
        """Occasionally pause to look human. Returns True if idled."""
        if self.humanizer and self.humanizer.should_idle():
            idle_time = self.humanizer.idle_duration()
            time.sleep(idle_time)
            return True
        return False

    def maybe_random_behavior(self):
        """
        Inject a random micro-behavior to look human.
        Returns (behavior_name, True) if performed, (None, False) if not.
        """
        if not self.humanizer or not self.humanizer.should_inject_behavior():
            return None, False

        behavior, params = self.humanizer.get_random_behavior()

        if behavior == "camera_wiggle":
            self.turn(int(params["dx"]), params["duration"])
        elif behavior == "hesitation":
            time.sleep(params["duration"])
        elif behavior == "look_around":
            self.turn(int(params["dx"]), params["duration"])
            time.sleep(0.2)
            self.turn(int(-params["dx"] * 0.8), params["duration"] * 0.8)
        elif behavior == "inventory_check":
            self.press_key("i")
            time.sleep(params["duration"])
            self.press_key("i")
        elif behavior == "jump":
            self.press_key("space")
        elif behavior == "mouse_drift":
            self.move_mouse_relative(int(params["dx"]), int(params["dy"]))
        elif behavior == "double_press":
            # Simulate accidental double-tap of last key
            self.press_key("w")
            time.sleep(params["delay"])
            self.press_key("w")
        elif behavior == "nothing":
            time.sleep(params["duration"])

        return behavior, True
