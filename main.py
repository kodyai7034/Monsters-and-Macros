"""
Monsters and Memories Macro Tool
Main entry point - CLI and GUI launcher.
"""

import sys
import os
import yaml
import threading
import time

from macro_engine import MacroEngine
from macro_recorder import MacroRecorder
from macro_player import MacroPlayer


def load_config(path="config.yaml"):
    with open(path, "r") as f:
        return yaml.safe_load(f)


class MacroTool:
    """Main macro tool controller."""

    def __init__(self, config_path="config.yaml"):
        self.config = load_config(config_path)
        self.engine = MacroEngine(self.config)
        self.recorder = MacroRecorder(
            capture_mouse=self.config.get("recording", {}).get("capture_mouse", True),
            capture_keyboard=self.config.get("recording", {}).get("capture_keyboard", True),
        )
        self._macro_thread = None
        self._stop_hotkey_thread = None

    def start_stop_hotkey(self):
        """Listen for the failsafe hotkey to stop macros."""
        try:
            import keyboard
            key = self.config.get("general", {}).get("failsafe_key", "f12")
            print(f"[HOTKEY] Press {key.upper()} to stop any running macro")
            keyboard.add_hotkey(key, self.stop_all)
        except ImportError:
            print("[WARN] 'keyboard' module not installed - no global hotkey support")

    def stop_all(self):
        """Emergency stop everything."""
        print("\n[STOP] Emergency stop triggered!")
        self.engine.stop()
        if self.recorder.recording:
            self.recorder.stop()

    def run_macro_file(self, filepath, loop=False):
        """Load and run a macro from a YAML file."""
        macro_def = self.engine.load_macro(filepath)
        print(f"[RUN] Starting macro: {macro_def.get('name', filepath)}")
        print(f"[RUN] {macro_def.get('description', '')}")
        print(f"[RUN] Loop: {loop}")
        self.engine.run_macro(macro_def, loop=loop)

    def run_macro_async(self, filepath, loop=False):
        """Run a macro in a background thread."""
        self._macro_thread = threading.Thread(
            target=self.run_macro_file, args=(filepath, loop), daemon=True
        )
        self._macro_thread.start()

    def record(self, output_path):
        """Record input to a file."""
        print("[REC] Starting recording... Press Ctrl+C to stop.")
        self.recorder.start()
        try:
            while self.recorder.recording:
                time.sleep(0.1)
        except KeyboardInterrupt:
            pass
        self.recorder.stop()
        self.recorder.save(output_path)

    def play_recording(self, filepath, loop=False, speed=1.0):
        """Play back a recorded macro."""
        events = MacroRecorder.load(filepath)
        player = MacroPlayer(self.engine.input)
        player.set_speed(speed)
        print(f"[PLAY] Playing {len(events)} events at {speed}x speed")
        player.play_recording(events, loop=loop)
        # Wait for playback
        while player.playing:
            time.sleep(0.1)

    def calibrate_screen(self):
        """Interactive calibration for screen regions."""
        print("=== Screen Calibration ===")
        print("This will help you set up health/mana bar detection.")
        print()
        reader = self.engine.screen

        print("1) Health bar calibration:")
        print("   Move mouse to the LEFT edge of your health bar when FULL.")
        result = reader.capture_calibration_point()
        if result:
            print(f"   Got: {result}")

        print()
        print("2) Move mouse to the RIGHT edge of your health bar.")
        result2 = reader.capture_calibration_point()
        if result and result2:
            x1, y1 = result["position"]
            x2, y2 = result2["position"]
            width = abs(x2 - x1)
            height = max(20, abs(y2 - y1))
            print(f"\n   Health bar region: [{x1}, {y1}, {width}, {height}]")
            print(f"   Health color: {list(result['color'])}")
            print("   Update these values in config.yaml under 'screen'")


def print_help():
    print("""
Monsters and Memories Macro Tool
================================

Usage: python main.py [command] [options]

Commands:
  gui                     Launch GUI (default if no command given)
  list                    List available macros
  run <macro.yaml>        Run a macro file
  run <macro.yaml> --loop Run a macro in a loop
  record <output.json>    Record keyboard/mouse input
  play <recording.json>   Play back a recording
  play <file> --loop      Play recording in a loop
  play <file> --speed 2.0 Play at 2x speed
  calibrate               Calibrate screen regions (health/mana bars)
  help                    Show this help message

Example macros (in macros/ folder):
  combat_rotation.yaml    Basic combat ability rotation
  grind_loop.yaml         Automated grinding patrol
  buff_cycle.yaml         Periodic buff refresh

Hotkeys:
  F12                     Emergency stop (configurable in config.yaml)

Config:
  config.yaml             Main configuration file
  - Keybinds, humanizer settings, screen regions
""")


def main():
    args = sys.argv[1:]

    if not args or args[0] == "gui":
        from gui import MacroToolGUI
        app = MacroToolGUI()
        app.run()
        return

    if args[0] == "help":
        print_help()
        return

    tool = MacroTool()
    tool.start_stop_hotkey()

    cmd = args[0]

    if cmd == "list":
        macros = tool.engine.list_macros()
        if macros:
            print("Available macros:")
            for m in macros:
                print(f"  - {m}")
        else:
            print("No macros found in macros/ folder")

    elif cmd == "run":
        if len(args) < 2:
            print("Usage: python main.py run <macro.yaml> [--loop]")
            return
        filepath = args[1]
        if not os.path.exists(filepath):
            filepath = os.path.join("macros", filepath)
        loop = "--loop" in args
        tool.run_macro_file(filepath, loop=loop)

    elif cmd == "record":
        if len(args) < 2:
            output = f"recordings/recording_{int(time.time())}.json"
        else:
            output = args[1]
        os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
        tool.record(output)

    elif cmd == "play":
        if len(args) < 2:
            print("Usage: python main.py play <recording.json> [--loop] [--speed N]")
            return
        filepath = args[1]
        loop = "--loop" in args
        speed = 1.0
        if "--speed" in args:
            idx = args.index("--speed")
            if idx + 1 < len(args):
                speed = float(args[idx + 1])
        tool.play_recording(filepath, loop=loop, speed=speed)

    elif cmd == "calibrate":
        tool.calibrate_screen()

    else:
        print(f"Unknown command: {cmd}")
        print_help()


if __name__ == "__main__":
    main()
