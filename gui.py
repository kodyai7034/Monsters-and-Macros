"""
Monsters and Memories Macro Tool - GUI
Tkinter-based interface for managing macros, recordings, and settings.
"""

import os
import sys
import time
import json
import yaml
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

from macro_engine import MacroEngine
from macro_recorder import MacroRecorder
from macro_player import MacroPlayer


def load_config(path="config.yaml"):
    with open(path, "r") as f:
        return yaml.safe_load(f)


def save_config(config, path="config.yaml"):
    with open(path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)


class StatusBar(ttk.Frame):
    """Bottom status bar with state indicators."""

    def __init__(self, parent):
        super().__init__(parent)
        self.status_var = tk.StringVar(value="Ready")
        self.macro_var = tk.StringVar(value="No macro running")
        self.humanizer_var = tk.StringVar(value="Humanizer: ON")

        ttk.Label(self, textvariable=self.status_var, width=30, anchor="w").pack(side="left", padx=5)
        ttk.Separator(self, orient="vertical").pack(side="left", fill="y", padx=5)
        ttk.Label(self, textvariable=self.macro_var, width=30, anchor="w").pack(side="left", padx=5)
        ttk.Separator(self, orient="vertical").pack(side="left", fill="y", padx=5)
        ttk.Label(self, textvariable=self.humanizer_var, anchor="w").pack(side="left", padx=5)

    def set_status(self, text):
        self.status_var.set(text)

    def set_macro(self, text):
        self.macro_var.set(text)

    def set_humanizer(self, enabled, intensity):
        state = "ON" if enabled else "OFF"
        self.humanizer_var.set(f"Humanizer: {state} ({intensity:.0%})")


class LogPanel(ttk.LabelFrame):
    """Scrollable log output panel."""

    def __init__(self, parent):
        super().__init__(parent, text="Log")
        self.text = scrolledtext.ScrolledText(self, height=8, state="disabled",
                                               font=("Consolas", 9), wrap="word")
        self.text.pack(fill="both", expand=True, padx=5, pady=5)

    def log(self, message, tag=None):
        self.text.config(state="normal")
        timestamp = time.strftime("%H:%M:%S")
        self.text.insert("end", f"[{timestamp}] {message}\n")
        self.text.see("end")
        self.text.config(state="disabled")

    def clear(self):
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.config(state="disabled")


class MacroListPanel(ttk.LabelFrame):
    """Panel for listing and selecting macros."""

    def __init__(self, parent, macro_dir="macros"):
        super().__init__(parent, text="Macros")
        self.macro_dir = macro_dir

        # Listbox with scrollbar
        list_frame = ttk.Frame(self)
        list_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self.listbox = tk.Listbox(list_frame, font=("Consolas", 10), selectmode="single")
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        self.listbox.config(yscrollcommand=scrollbar.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", padx=5, pady=(0, 5))
        ttk.Button(btn_frame, text="Refresh", command=self.refresh).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="Open Folder", command=self.open_folder).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="New Macro", command=self.new_macro).pack(side="left", padx=2)

        self.refresh()

    def refresh(self):
        self.listbox.delete(0, "end")
        if os.path.isdir(self.macro_dir):
            for f in sorted(os.listdir(self.macro_dir)):
                if f.endswith((".yaml", ".yml")):
                    self.listbox.insert("end", f)

    def get_selected(self):
        sel = self.listbox.curselection()
        if sel:
            filename = self.listbox.get(sel[0])
            return os.path.join(self.macro_dir, filename)
        return None

    def get_selected_name(self):
        sel = self.listbox.curselection()
        if sel:
            return self.listbox.get(sel[0])
        return None

    def open_folder(self):
        os.makedirs(self.macro_dir, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(self.macro_dir)
        else:
            os.system(f'xdg-open "{self.macro_dir}" 2>/dev/null &')

    def new_macro(self):
        template = {
            "name": "New Macro",
            "description": "Description here",
            "loop_delay": 0.5,
            "actions": [
                {"action": "log", "message": "Macro started"},
                {"action": "wait", "duration": 1.0},
                {"action": "log", "message": "Macro finished"},
            ]
        }
        filepath = filedialog.asksaveasfilename(
            initialdir=self.macro_dir,
            defaultextension=".yaml",
            filetypes=[("YAML files", "*.yaml *.yml")],
            title="Create New Macro"
        )
        if filepath:
            with open(filepath, "w") as f:
                yaml.dump(template, f, default_flow_style=False)
            self.refresh()


class MacroDetailPanel(ttk.LabelFrame):
    """Shows details of selected macro."""

    def __init__(self, parent):
        super().__init__(parent, text="Macro Details")
        self.text = scrolledtext.ScrolledText(self, height=12, font=("Consolas", 9), wrap="word")
        self.text.pack(fill="both", expand=True, padx=5, pady=5)

    def show_macro(self, filepath):
        self.text.delete("1.0", "end")
        if filepath and os.path.exists(filepath):
            with open(filepath, "r") as f:
                content = f.read()
            self.text.insert("1.0", content)

    def get_content(self):
        return self.text.get("1.0", "end").strip()

    def save_macro(self, filepath):
        content = self.get_content()
        if filepath and content:
            with open(filepath, "w") as f:
                f.write(content)
            return True
        return False


class RecordingPanel(ttk.LabelFrame):
    """Panel for recording and playing back input."""

    def __init__(self, parent):
        super().__init__(parent, text="Recordings")

        list_frame = ttk.Frame(self)
        list_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self.listbox = tk.Listbox(list_frame, font=("Consolas", 10), selectmode="single", height=6)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        self.listbox.config(yscrollcommand=scrollbar.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Speed control
        speed_frame = ttk.Frame(self)
        speed_frame.pack(fill="x", padx=5, pady=2)
        ttk.Label(speed_frame, text="Speed:").pack(side="left")
        self.speed_var = tk.DoubleVar(value=1.0)
        speed_spin = ttk.Spinbox(speed_frame, from_=0.1, to=5.0, increment=0.1,
                                  textvariable=self.speed_var, width=5)
        speed_spin.pack(side="left", padx=5)
        ttk.Label(speed_frame, text="x").pack(side="left")

        self.refresh()

    def refresh(self):
        self.listbox.delete(0, "end")
        rec_dir = "recordings"
        if os.path.isdir(rec_dir):
            for f in sorted(os.listdir(rec_dir)):
                if f.endswith(".json"):
                    self.listbox.insert("end", f)

    def get_selected(self):
        sel = self.listbox.curselection()
        if sel:
            return os.path.join("recordings", self.listbox.get(sel[0]))
        return None


class SettingsPanel(ttk.LabelFrame):
    """Settings panel for humanizer and keybinds."""

    def __init__(self, parent, config):
        super().__init__(parent, text="Settings")
        self.config = config

        canvas = tk.Canvas(self, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.inner_frame = ttk.Frame(canvas)

        self.inner_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.inner_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        scrollbar.pack(side="right", fill="y")

        self._build_settings()

    def _build_settings(self):
        frame = self.inner_frame

        # --- Humanizer ---
        ttk.Label(frame, text="Humanizer", font=("", 10, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(5, 2))

        humanizer_cfg = self.config.get("humanizer", {})
        self.humanize_enabled = tk.BooleanVar(value=humanizer_cfg.get("enabled", True))
        ttk.Checkbutton(frame, text="Enabled", variable=self.humanize_enabled).grid(row=1, column=0, columnspan=2, sticky="w")

        ttk.Label(frame, text="Intensity:").grid(row=2, column=0, sticky="w")
        self.intensity_var = tk.DoubleVar(value=humanizer_cfg.get("intensity", 0.5))
        intensity_scale = ttk.Scale(frame, from_=0.0, to=1.0, variable=self.intensity_var, orient="horizontal")
        intensity_scale.grid(row=2, column=1, sticky="ew", padx=5)

        # --- Input Method ---
        ttk.Label(frame, text="Input", font=("", 10, "bold")).grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 2))

        input_cfg = self.config.get("input", {})
        ttk.Label(frame, text="Method:").grid(row=4, column=0, sticky="w")
        self.method_var = tk.StringVar(value=input_cfg.get("method", "directinput"))
        method_combo = ttk.Combobox(frame, textvariable=self.method_var,
                                     values=["directinput", "pyautogui"], state="readonly", width=15)
        method_combo.grid(row=4, column=1, sticky="w", padx=5)

        # --- Keybinds ---
        ttk.Label(frame, text="Keybinds", font=("", 10, "bold")).grid(row=5, column=0, columnspan=2, sticky="w", pady=(10, 2))

        self.keybind_vars = {}
        keybinds = self.config.get("keybinds", {})
        row = 6
        for action, key in sorted(keybinds.items()):
            ttk.Label(frame, text=f"{action}:").grid(row=row, column=0, sticky="w")
            var = tk.StringVar(value=key)
            self.keybind_vars[action] = var
            entry = ttk.Entry(frame, textvariable=var, width=10)
            entry.grid(row=row, column=1, sticky="w", padx=5, pady=1)
            row += 1

        frame.columnconfigure(1, weight=1)

    def get_settings(self):
        """Return updated config dict."""
        self.config.setdefault("humanizer", {})
        self.config["humanizer"]["enabled"] = self.humanize_enabled.get()
        self.config["humanizer"]["intensity"] = round(self.intensity_var.get(), 2)

        self.config.setdefault("input", {})
        self.config["input"]["method"] = self.method_var.get()

        keybinds = {}
        for action, var in self.keybind_vars.items():
            keybinds[action] = var.get()
        self.config["keybinds"] = keybinds

        return self.config


class MacroToolGUI:
    """Main GUI application."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("MnM Macro Tool")
        self.root.geometry("900x700")
        self.root.minsize(800, 600)

        self.config = load_config()
        self.engine = MacroEngine(self.config)
        self.recorder = MacroRecorder(
            capture_mouse=self.config.get("recording", {}).get("capture_mouse", True),
            capture_keyboard=self.config.get("recording", {}).get("capture_keyboard", True),
        )
        self._macro_thread = None
        self._recording = False

        self._setup_style()
        self._build_ui()
        self._setup_hotkey()
        self._update_status()

    def _setup_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Run.TButton", foreground="green")
        style.configure("Stop.TButton", foreground="red")
        style.configure("Record.TButton", foreground="red")

    def _build_ui(self):
        # --- Toolbar ---
        toolbar = ttk.Frame(self.root)
        toolbar.pack(fill="x", padx=5, pady=5)

        self.run_btn = ttk.Button(toolbar, text="Run", style="Run.TButton", command=self.run_macro)
        self.run_btn.pack(side="left", padx=2)

        self.loop_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(toolbar, text="Loop", variable=self.loop_var).pack(side="left", padx=2)

        self.stop_btn = ttk.Button(toolbar, text="Stop", style="Stop.TButton", command=self.stop_all, state="disabled")
        self.stop_btn.pack(side="left", padx=2)

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8)

        self.record_btn = ttk.Button(toolbar, text="Record", style="Record.TButton", command=self.toggle_record)
        self.record_btn.pack(side="left", padx=2)

        self.play_btn = ttk.Button(toolbar, text="Play Recording", command=self.play_recording)
        self.play_btn.pack(side="left", padx=2)

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8)

        ttk.Button(toolbar, text="Save Settings", command=self.save_settings).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Calibrate", command=self.calibrate).pack(side="left", padx=2)

        ttk.Label(toolbar, text="F12 = Emergency Stop", foreground="red").pack(side="right", padx=10)

        # --- Notebook (tabs) ---
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=5, pady=5)

        # Tab 1: Macros
        macro_tab = ttk.Frame(notebook)
        notebook.add(macro_tab, text="Macros")

        macro_pane = ttk.PanedWindow(macro_tab, orient="horizontal")
        macro_pane.pack(fill="both", expand=True)

        self.macro_list = MacroListPanel(macro_pane)
        macro_pane.add(self.macro_list, weight=1)

        self.macro_detail = MacroDetailPanel(macro_pane)
        macro_pane.add(self.macro_detail, weight=2)

        self.macro_list.listbox.bind("<<ListboxSelect>>", self._on_macro_select)
        self.macro_list.listbox.bind("<Double-1>", lambda e: self.run_macro())

        # Save button for macro editor
        save_frame = ttk.Frame(macro_tab)
        save_frame.pack(fill="x", padx=5, pady=2)
        ttk.Button(save_frame, text="Save Macro", command=self._save_current_macro).pack(side="right", padx=2)
        ttk.Button(save_frame, text="Edit in Editor", command=self._edit_external).pack(side="right", padx=2)

        # Tab 2: Recordings
        rec_tab = ttk.Frame(notebook)
        notebook.add(rec_tab, text="Recordings")
        self.recording_panel = RecordingPanel(rec_tab)
        self.recording_panel.pack(fill="both", expand=True, padx=5, pady=5)

        rec_btn_frame = ttk.Frame(rec_tab)
        rec_btn_frame.pack(fill="x", padx=5, pady=5)
        ttk.Button(rec_btn_frame, text="Refresh", command=self.recording_panel.refresh).pack(side="left", padx=2)
        ttk.Button(rec_btn_frame, text="Delete Selected", command=self._delete_recording).pack(side="left", padx=2)

        # Tab 3: Settings
        settings_tab = ttk.Frame(notebook)
        notebook.add(settings_tab, text="Settings")
        self.settings_panel = SettingsPanel(settings_tab, self.config)
        self.settings_panel.pack(fill="both", expand=True, padx=5, pady=5)

        # Tab 4: Game Info
        info_tab = ttk.Frame(notebook)
        notebook.add(info_tab, text="Game Info")
        self._build_info_tab(info_tab)

        # --- Log panel ---
        self.log = LogPanel(self.root)
        self.log.pack(fill="x", padx=5, pady=(0, 5))

        # --- Status bar ---
        self.status_bar = StatusBar(self.root)
        self.status_bar.pack(fill="x", padx=5, pady=(0, 5))

        self.log.log("MnM Macro Tool started")

    def _build_info_tab(self, parent):
        """Game info reference tab."""
        text = scrolledtext.ScrolledText(parent, font=("Consolas", 9), wrap="word", state="normal")
        text.pack(fill="both", expand=True, padx=5, pady=5)
        text.insert("1.0", """Monsters and Memories - Game Data Reference
============================================

ANTI-BOT DETECTION (from IL2CPP dump):
  BotBehaviorDetector:
    - Impossible timing threshold: 100ms
    - Required pattern repetitions: 5
    - Detection cooldown: 300s (5 min)
    - Monitors: PerfectAbilityTiming, InstantTargetAcquisition

  InputPatternDetector:
    - Min actions for detection: 10 identical
    - Press duration tolerance: 10ms
    - Interval std dev threshold: <10ms = bot
    - Tracked duration threshold: 30ms

  InputController:
    - Rapid click window: 0.3s
    - Rapid click threshold: 3 clicks

COOLDOWN SYSTEM (3 tracks):
  1. abilityHid  - Individual ability cooldowns
  2. cooldownHid - Grouped/shared cooldowns
  3. globalCooldownHid - Global Cooldown (GCD)

MOVEMENT:
  - Network update rate: 0.1s (moving), 0.25s (stationary)
  - Jump endurance cost: 10
  - Modes: Normal, Swimming, Flying, Levitating, Climbing

CASTING REQUIREMENTS:
  - Line of sight, facing target
  - Behind/beside target positioning
  - Buff requirements, reagents
  - Mana cost, cast time, range

TARGETING:
  - Max range: 50 units
  - Tab target cycling (hostile/friendly)
  - Priority targeting with scoring

POSTURES: Stand, Sit, Crouch, Kneel

STATUS EFFECTS: Stunned, Feared, Mesmerized, Silenced,
  Invisible, Levitating, Sneaking, Shielding
""")
        text.config(state="disabled")

    def _on_macro_select(self, event=None):
        filepath = self.macro_list.get_selected()
        if filepath:
            self.macro_detail.show_macro(filepath)

    def _save_current_macro(self):
        filepath = self.macro_list.get_selected()
        if filepath:
            if self.macro_detail.save_macro(filepath):
                self.log.log(f"Saved: {os.path.basename(filepath)}")
                self.macro_list.refresh()
        else:
            messagebox.showwarning("No Selection", "Select a macro to save.")

    def _edit_external(self):
        filepath = self.macro_list.get_selected()
        if filepath and os.path.exists(filepath):
            if sys.platform == "win32":
                os.startfile(filepath)
            else:
                os.system(f'xdg-open "{filepath}" 2>/dev/null &')

    def _delete_recording(self):
        filepath = self.recording_panel.get_selected()
        if filepath and os.path.exists(filepath):
            if messagebox.askyesno("Delete", f"Delete {os.path.basename(filepath)}?"):
                os.remove(filepath)
                self.recording_panel.refresh()
                self.log.log(f"Deleted recording: {os.path.basename(filepath)}")

    def _setup_hotkey(self):
        try:
            import keyboard
            key = self.config.get("general", {}).get("failsafe_key", "f12")
            keyboard.add_hotkey(key, self.stop_all)
            self.log.log(f"Hotkey registered: {key.upper()} = Emergency Stop")
        except ImportError:
            self.log.log("[WARN] 'keyboard' module not installed - no global hotkey")

    def _update_status(self):
        humanizer_cfg = self.config.get("humanizer", {})
        self.status_bar.set_humanizer(
            humanizer_cfg.get("enabled", True),
            humanizer_cfg.get("intensity", 0.5)
        )

    # --- Actions ---

    def run_macro(self):
        filepath = self.macro_list.get_selected()
        if not filepath:
            messagebox.showwarning("No Selection", "Select a macro to run.")
            return

        name = self.macro_list.get_selected_name()
        loop = self.loop_var.get()

        # Reload engine with current settings
        self.config = self.settings_panel.get_settings()
        self.engine = MacroEngine(self.config)

        self.log.log(f"Starting macro: {name} (loop={loop})")
        self.status_bar.set_status("Running")
        self.status_bar.set_macro(f"Running: {name}")
        self.run_btn.config(state="disabled")
        self.stop_btn.config(state="normal")

        def _run():
            try:
                macro_def = self.engine.load_macro(filepath)
                self.engine.run_macro(macro_def, loop=loop)
            except Exception as e:
                self.root.after(0, lambda: self.log.log(f"[ERROR] {e}"))
            finally:
                self.root.after(0, self._on_macro_done)

        self._macro_thread = threading.Thread(target=_run, daemon=True)
        self._macro_thread.start()

    def _on_macro_done(self):
        self.run_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.status_bar.set_status("Ready")
        self.status_bar.set_macro("No macro running")
        self.log.log("Macro stopped")

    def stop_all(self):
        self.engine.stop()
        if self._recording:
            self._stop_recording()
        self.log.log("Emergency stop!")
        self.root.after(100, self._on_macro_done)

    def toggle_record(self):
        if self._recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        self._recording = True
        self.record_btn.config(text="Stop Recording")
        self.status_bar.set_status("Recording...")
        self.recorder.start()
        self.log.log("Recording started - press Stop Recording or F12 to stop")

    def _stop_recording(self):
        self._recording = False
        self.recorder.stop()
        self.record_btn.config(text="Record")
        self.status_bar.set_status("Ready")

        # Save recording
        os.makedirs("recordings", exist_ok=True)
        filename = f"recording_{int(time.time())}.json"
        filepath = os.path.join("recordings", filename)
        self.recorder.save(filepath)
        self.recording_panel.refresh()
        self.log.log(f"Recording saved: {filename} ({len(self.recorder.events)} events)")

    def play_recording(self):
        filepath = self.recording_panel.get_selected()
        if not filepath:
            messagebox.showwarning("No Selection", "Select a recording to play.")
            return

        speed = self.recording_panel.speed_var.get()
        loop = self.loop_var.get()

        self.log.log(f"Playing: {os.path.basename(filepath)} at {speed}x speed")
        self.status_bar.set_status("Playing recording")
        self.run_btn.config(state="disabled")
        self.stop_btn.config(state="normal")

        def _play():
            try:
                events = MacroRecorder.load(filepath)
                player = MacroPlayer(self.engine.input)
                player.set_speed(speed)
                player.play_recording(events, loop=loop)
                while player.playing:
                    time.sleep(0.1)
            except Exception as e:
                self.root.after(0, lambda: self.log.log(f"[ERROR] {e}"))
            finally:
                self.root.after(0, self._on_macro_done)

        self._macro_thread = threading.Thread(target=_play, daemon=True)
        self._macro_thread.start()

    def save_settings(self):
        self.config = self.settings_panel.get_settings()
        save_config(self.config)
        self._update_status()
        self.log.log("Settings saved to config.yaml")

    def calibrate(self):
        self.log.log("Calibration: Move mouse to health bar LEFT edge, press Enter in console")
        messagebox.showinfo("Calibrate",
            "Move your mouse to the LEFT edge of your health bar, then press OK.\n"
            "After that, move to the RIGHT edge and press OK again.")
        # This is simplified - full calibration needs screen capture
        self.log.log("Calibration not yet available in GUI mode - use 'python main.py calibrate'")

    def run(self):
        self.root.mainloop()


def main():
    app = MacroToolGUI()
    app.run()


if __name__ == "__main__":
    main()
