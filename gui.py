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
from map_tab import MapTab
from memory_reader import GameMemoryReader


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
        self.humanizer_var = tk.StringVar(value="Humanizer: ON")
        self.memory_var = tk.StringVar(value="Game: --")

        ttk.Label(self, textvariable=self.status_var, width=20, anchor="w").pack(side="left", padx=5)
        ttk.Separator(self, orient="vertical").pack(side="left", fill="y", padx=5)
        ttk.Label(self, textvariable=self.humanizer_var, anchor="w").pack(side="left", padx=5)
        ttk.Separator(self, orient="vertical").pack(side="left", fill="y", padx=5)

        self.memory_label = ttk.Label(self, textvariable=self.memory_var, anchor="w")
        self.memory_label.pack(side="left", padx=5)
        self.reconnect_btn = ttk.Button(self, text="Connect", width=8)
        self.reconnect_btn.pack(side="left", padx=2)

    def set_status(self, text):
        self.status_var.set(text)

    def set_humanizer(self, enabled, intensity):
        state = "ON" if enabled else "OFF"
        self.humanizer_var.set(f"Humanizer: {state} ({intensity:.0%})")

    def set_memory_status(self, connected, player_name=""):
        if connected and player_name:
            self.memory_var.set(f"Game: {player_name}")
        elif connected:
            self.memory_var.set("Game: Connected")
        else:
            self.memory_var.set("Game: Not connected")


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


class MacrosTab(ttk.Frame):
    """Macros tab — select, run, pause, stop active and reactive macros."""

    def __init__(self, parent, engine, log_callback=None):
        super().__init__(parent)
        self.engine = engine
        self.log = log_callback or (lambda msg: None)
        self._macro_thread = None
        self._active_macro_name = ""

        # Macro file index: {filename: {name, description, type}}
        self._macro_index = {}

        self._build_ui()
        self._refresh_macros()

    def _build_ui(self):
        # --- Active Macro Section ---
        active_frame = ttk.LabelFrame(self, text="Active Macro")
        active_frame.pack(fill="x", padx=5, pady=5)

        # Row 1: dropdown + controls
        row1 = ttk.Frame(active_frame)
        row1.pack(fill="x", padx=5, pady=5)

        ttk.Label(row1, text="Macro:").pack(side="left", padx=(0, 5))
        self.active_combo = ttk.Combobox(row1, width=30, state="readonly")
        self.active_combo.pack(side="left", padx=2)
        self.active_combo.bind("<<ComboboxSelected>>", self._on_active_selected)

        self.play_btn = ttk.Button(row1, text="Play", width=6, command=self._play_active)
        self.play_btn.pack(side="left", padx=2)

        self.pause_btn = ttk.Button(row1, text="Pause", width=6, command=self._pause_active, state="disabled")
        self.pause_btn.pack(side="left", padx=2)

        self.stop_btn = ttk.Button(row1, text="Stop", width=6, command=self._stop_active, state="disabled")
        self.stop_btn.pack(side="left", padx=2)

        self.loop_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row1, text="Loop", variable=self.loop_var).pack(side="left", padx=5)

        # Row 2: status
        row2 = ttk.Frame(active_frame)
        row2.pack(fill="x", padx=5, pady=(0, 5))

        self.active_status_var = tk.StringVar(value="Stopped")
        ttk.Label(row2, text="Status:").pack(side="left")
        ttk.Label(row2, textvariable=self.active_status_var, font=("Consolas", 9)).pack(side="left", padx=5)

        self.active_action_var = tk.StringVar(value="")
        ttk.Label(row2, textvariable=self.active_action_var, font=("Consolas", 9),
                  foreground="gray").pack(side="left", padx=10)

        # --- Reactive Monitors Section ---
        reactive_frame = ttk.LabelFrame(self, text="Reactive Monitors")
        reactive_frame.pack(fill="both", expand=False, padx=5, pady=5)

        # Reactive list (scrollable)
        self._reactive_canvas = tk.Canvas(reactive_frame, highlightthickness=0, height=120)
        reactive_scroll = ttk.Scrollbar(reactive_frame, orient="vertical",
                                         command=self._reactive_canvas.yview)
        self._reactive_inner = ttk.Frame(self._reactive_canvas)
        self._reactive_inner.bind("<Configure>",
            lambda e: self._reactive_canvas.configure(scrollregion=self._reactive_canvas.bbox("all")))
        self._reactive_canvas.create_window((0, 0), window=self._reactive_inner, anchor="nw")
        self._reactive_canvas.configure(yscrollcommand=reactive_scroll.set)
        self._reactive_canvas.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        reactive_scroll.pack(side="right", fill="y", pady=5)

        self._reactive_rows = {}  # filename -> {btn, status_var}

        # --- YAML Editor Section ---
        editor_frame = ttk.LabelFrame(self, text="Macro Editor")
        editor_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self.editor = scrolledtext.ScrolledText(editor_frame, height=10, font=("Consolas", 9), wrap="word")
        self.editor.pack(fill="both", expand=True, padx=5, pady=5)

        editor_btns = ttk.Frame(editor_frame)
        editor_btns.pack(fill="x", padx=5, pady=(0, 5))
        ttk.Button(editor_btns, text="Save", command=self._save_editor).pack(side="right", padx=2)
        ttk.Button(editor_btns, text="Refresh List", command=self._refresh_macros).pack(side="left", padx=2)
        ttk.Button(editor_btns, text="Open Folder", command=self._open_folder).pack(side="left", padx=2)
        ttk.Button(editor_btns, text="New Macro", command=self._new_macro).pack(side="left", padx=2)

    def set_engine(self, engine):
        """Update the engine reference (called when settings change)."""
        self.engine = engine

    # =====================================================================
    # Macro list management
    # =====================================================================

    def _refresh_macros(self):
        """Reload the macro file list and populate dropdowns."""
        active_list, reactive_list = self.engine.list_macros_by_type()

        self._macro_index = {}
        for fname, name, desc in active_list + reactive_list:
            mtype = "active"
            for rf, rn, rd in reactive_list:
                if rf == fname:
                    mtype = "reactive"
                    break
            self._macro_index[fname] = {"name": name, "description": desc, "type": mtype}

        # Active dropdown
        active_display = [f"{name}  ({fname})" for fname, name, desc in active_list]
        self._active_files = [fname for fname, _, _ in active_list]
        self.active_combo["values"] = active_display

        # Reactive monitors list
        for widget in self._reactive_inner.winfo_children():
            widget.destroy()
        self._reactive_rows = {}

        for i, (fname, name, desc) in enumerate(reactive_list):
            row = ttk.Frame(self._reactive_inner)
            row.pack(fill="x", pady=1)

            status_var = tk.StringVar(value="Stopped")

            ttk.Label(row, text=name, width=25, anchor="w").pack(side="left", padx=5)
            ttk.Label(row, text=desc[:40], foreground="gray", width=35, anchor="w").pack(side="left", padx=2)
            status_lbl = ttk.Label(row, textvariable=status_var, width=10, anchor="w",
                                    font=("Consolas", 9))
            status_lbl.pack(side="left", padx=5)

            toggle_btn = ttk.Button(row, text="Start", width=6,
                command=lambda f=fname: self._toggle_reactive(f))
            toggle_btn.pack(side="left", padx=2)

            # Show in editor on click
            name_lbl = row.winfo_children()[0]
            name_lbl.bind("<Button-1>", lambda e, f=fname: self._show_in_editor(f))

            self._reactive_rows[fname] = {
                "btn": toggle_btn,
                "status_var": status_var,
                "name": name,
            }

        # Update reactive statuses for any already-running monitors
        for fname, info in self._reactive_rows.items():
            name = info["name"]
            if self.engine.is_reactive_running(name):
                info["status_var"].set("Running")
                info["btn"].config(text="Stop")

    def _on_active_selected(self, event=None):
        idx = self.active_combo.current()
        if idx >= 0 and idx < len(self._active_files):
            fname = self._active_files[idx]
            self._show_in_editor(fname)

    def _show_in_editor(self, filename):
        """Load a macro file into the YAML editor."""
        filepath = os.path.join("macros", filename)
        self.editor.delete("1.0", "end")
        if os.path.exists(filepath):
            with open(filepath, "r") as f:
                self.editor.insert("1.0", f.read())
        self._selected_file = filename

    def _save_editor(self):
        """Save editor content back to the selected macro file."""
        if not hasattr(self, "_selected_file") or not self._selected_file:
            messagebox.showwarning("No File", "Select a macro first.")
            return
        filepath = os.path.join("macros", self._selected_file)
        content = self.editor.get("1.0", "end").strip()
        if content:
            with open(filepath, "w") as f:
                f.write(content)
            self.log(f"Saved: {self._selected_file}")
            self._refresh_macros()

    def _open_folder(self):
        os.makedirs("macros", exist_ok=True)
        if sys.platform == "win32":
            os.startfile("macros")
        else:
            os.system('xdg-open "macros" 2>/dev/null &')

    def _new_macro(self):
        filepath = filedialog.asksaveasfilename(
            initialdir="macros",
            defaultextension=".yaml",
            filetypes=[("YAML files", "*.yaml *.yml")],
            title="Create New Macro"
        )
        if filepath:
            template = (
                "name: \"New Macro\"\n"
                "# type: active    # or 'reactive' for rule-based monitors\n"
                "description: \"Description here\"\n"
                "loop_delay: 0.5\n\n"
                "actions:\n"
                "  - action: log\n"
                "    message: \"Macro started\"\n"
                "  - action: wait\n"
                "    duration: 1.0\n"
            )
            with open(filepath, "w") as f:
                f.write(template)
            self._refresh_macros()

    # =====================================================================
    # Active macro controls
    # =====================================================================

    def _play_active(self):
        idx = self.active_combo.current()
        if idx < 0 or idx >= len(self._active_files):
            messagebox.showwarning("No Selection", "Select an active macro from the dropdown.")
            return

        fname = self._active_files[idx]
        filepath = os.path.join("macros", fname)
        loop = self.loop_var.get()
        macro_name = self._macro_index.get(fname, {}).get("name", fname)

        if self.engine.running:
            # Already running — resume if paused
            if self.engine.paused:
                self.engine.resume()
                self.active_status_var.set("Running")
                self.pause_btn.config(text="Pause")
                self.log(f"Resumed: {macro_name}")
            return

        self._active_macro_name = macro_name
        self.active_status_var.set("Running")
        self.play_btn.config(state="disabled")
        self.pause_btn.config(state="normal", text="Pause")
        self.stop_btn.config(state="normal")
        self.log(f"Starting: {macro_name} (loop={loop})")

        def _run():
            try:
                macro_def = self.engine.load_macro(filepath)
                self.engine.run_macro(macro_def, loop=loop)
            except Exception as e:
                self.winfo_toplevel().after(0, lambda: self.log(f"[ERROR] {e}"))
            finally:
                self.winfo_toplevel().after(0, self._on_active_done)

        self._macro_thread = threading.Thread(target=_run, daemon=True)
        self._macro_thread.start()

        # Start polling current action
        self._poll_active_status()

    def _pause_active(self):
        if not self.engine.running:
            return
        if self.engine.paused:
            self.engine.resume()
            self.active_status_var.set("Running")
            self.pause_btn.config(text="Pause")
            self.log(f"Resumed: {self._active_macro_name}")
        else:
            self.engine.pause()
            self.active_status_var.set("Paused")
            self.pause_btn.config(text="Resume")
            self.log(f"Paused: {self._active_macro_name}")

    def _stop_active(self):
        self.engine.stop()
        self.active_status_var.set("Stopped")
        self.active_action_var.set("")
        self.log(f"Stopped: {self._active_macro_name}")
        self._on_active_done()

    def _on_active_done(self):
        self.play_btn.config(state="normal")
        self.pause_btn.config(state="disabled", text="Pause")
        self.stop_btn.config(state="disabled")
        self.active_status_var.set("Stopped")
        self.active_action_var.set("")

    def _poll_active_status(self):
        """Update the current action display while a macro is running."""
        if self.engine.running:
            action = self.engine.current_action
            if action:
                self.active_action_var.set(f">> {action}")
            self.after(200, self._poll_active_status)
        else:
            self.active_action_var.set("")

    # =====================================================================
    # Reactive monitor controls
    # =====================================================================

    def _toggle_reactive(self, filename):
        info = self._reactive_rows.get(filename)
        if not info:
            return

        name = info["name"]

        if self.engine.is_reactive_running(name):
            self.engine.stop_reactive(name)
            info["status_var"].set("Stopped")
            info["btn"].config(text="Start")
            self.log(f"Stopped monitor: {name}")
        else:
            filepath = os.path.join("macros", filename)
            try:
                macro_def = self.engine.load_macro(filepath)
                self.engine.start_reactive(macro_def)
                info["status_var"].set("Running")
                info["btn"].config(text="Stop")
                self.log(f"Started monitor: {name}")
            except Exception as e:
                self.log(f"[ERROR] Failed to start {name}: {e}")

    def stop_all(self):
        """Stop everything — called by emergency stop."""
        self.engine.stop_all()
        self._on_active_done()
        for fname, info in self._reactive_rows.items():
            info["status_var"].set("Stopped")
            info["btn"].config(text="Start")


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

        speed_frame = ttk.Frame(self)
        speed_frame.pack(fill="x", padx=5, pady=2)
        ttk.Label(speed_frame, text="Speed:").pack(side="left")
        self.speed_var = tk.DoubleVar(value=1.0)
        speed_spin = ttk.Spinbox(speed_frame, from_=0.1, to=5.0, increment=0.1,
                                  textvariable=self.speed_var, width=5)
        speed_spin.pack(side="left", padx=5)
        ttk.Label(speed_frame, text="x").pack(side="left")

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", padx=5, pady=5)
        ttk.Button(btn_frame, text="Refresh", command=self.refresh).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="Delete Selected", command=self._delete).pack(side="left", padx=2)

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

    def _delete(self):
        filepath = self.get_selected()
        if filepath and os.path.exists(filepath):
            if messagebox.askyesno("Delete", f"Delete {os.path.basename(filepath)}?"):
                os.remove(filepath)
                self.refresh()


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

        ttk.Label(frame, text="Humanizer", font=("", 10, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(5, 2))

        humanizer_cfg = self.config.get("humanizer", {})
        self.humanize_enabled = tk.BooleanVar(value=humanizer_cfg.get("enabled", True))
        ttk.Checkbutton(frame, text="Enabled", variable=self.humanize_enabled).grid(row=1, column=0, columnspan=2, sticky="w")

        ttk.Label(frame, text="Intensity:").grid(row=2, column=0, sticky="w")
        self.intensity_var = tk.DoubleVar(value=humanizer_cfg.get("intensity", 0.5))
        ttk.Scale(frame, from_=0.0, to=1.0, variable=self.intensity_var, orient="horizontal").grid(row=2, column=1, sticky="ew", padx=5)

        ttk.Label(frame, text="Input", font=("", 10, "bold")).grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 2))

        input_cfg = self.config.get("input", {})
        ttk.Label(frame, text="Method:").grid(row=4, column=0, sticky="w")
        self.method_var = tk.StringVar(value=input_cfg.get("method", "directinput"))
        ttk.Combobox(frame, textvariable=self.method_var,
                     values=["directinput", "pyautogui"], state="readonly", width=15).grid(row=4, column=1, sticky="w", padx=5)

        ttk.Label(frame, text="Keybinds", font=("", 10, "bold")).grid(row=5, column=0, columnspan=2, sticky="w", pady=(10, 2))

        self.keybind_vars = {}
        keybinds = self.config.get("keybinds", {})
        row = 6
        for action, key in sorted(keybinds.items()):
            ttk.Label(frame, text=f"{action}:").grid(row=row, column=0, sticky="w")
            var = tk.StringVar(value=key)
            self.keybind_vars[action] = var
            ttk.Entry(frame, textvariable=var, width=10).grid(row=row, column=1, sticky="w", padx=5, pady=1)
            row += 1

        frame.columnconfigure(1, weight=1)

    def get_settings(self):
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

        # Single shared memory reader
        self.memory_reader = GameMemoryReader(
            config=self.config.get("memory", {})
        )

        self.engine = MacroEngine(self.config, memory_reader=self.memory_reader)
        self.recorder = MacroRecorder(
            capture_mouse=self.config.get("recording", {}).get("capture_mouse", True),
            capture_keyboard=self.config.get("recording", {}).get("capture_keyboard", True),
        )
        self._recording = False

        self._setup_style()
        self._build_ui()
        self._setup_hotkey()
        self._update_status()
        self._try_connect_memory()
        self._memory_watchdog()

    def _setup_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

    def _build_ui(self):
        # --- Toolbar (recording + emergency stop only) ---
        toolbar = ttk.Frame(self.root)
        toolbar.pack(fill="x", padx=5, pady=5)

        self.record_btn = ttk.Button(toolbar, text="Record", command=self.toggle_record)
        self.record_btn.pack(side="left", padx=2)

        self.play_rec_btn = ttk.Button(toolbar, text="Play Recording", command=self.play_recording)
        self.play_rec_btn.pack(side="left", padx=2)

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8)

        ttk.Button(toolbar, text="Save Settings", command=self.save_settings).pack(side="left", padx=2)

        ttk.Button(toolbar, text="Emergency Stop", command=self.stop_all).pack(side="right", padx=5)
        ttk.Label(toolbar, text="F12", foreground="red", font=("", 8)).pack(side="right")

        # --- Notebook (tabs) ---
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=5, pady=5)

        # Tab 1: Macros
        self.macros_tab = MacrosTab(notebook, self.engine,
                                     log_callback=lambda msg: self.log.log(msg))
        notebook.add(self.macros_tab, text="Macros")

        # Tab 2: Recordings
        rec_tab = ttk.Frame(notebook)
        notebook.add(rec_tab, text="Recordings")
        self.recording_panel = RecordingPanel(rec_tab)
        self.recording_panel.pack(fill="both", expand=True, padx=5, pady=5)

        # Tab 3: Map
        self.map_tab = MapTab(notebook, memory_reader=self.memory_reader,
                               log_callback=lambda msg: self.log.log(msg))
        notebook.add(self.map_tab, text="Map")

        # Tab 4: Settings
        settings_tab = ttk.Frame(notebook)
        notebook.add(settings_tab, text="Settings")
        self.settings_panel = SettingsPanel(settings_tab, self.config)
        self.settings_panel.pack(fill="both", expand=True, padx=5, pady=5)

        # Tab 5: Game Info
        info_tab = ttk.Frame(notebook)
        notebook.add(info_tab, text="Game Info")
        self._build_info_tab(info_tab)

        # --- Log panel ---
        self.log = LogPanel(self.root)
        self.log.pack(fill="x", padx=5, pady=(0, 5))

        # --- Status bar ---
        self.status_bar = StatusBar(self.root)
        self.status_bar.pack(fill="x", padx=5, pady=(0, 5))
        self.status_bar.reconnect_btn.config(command=self._try_connect_memory)

        self.log.log("MnM Macro Tool started")

    def _build_info_tab(self, parent):
        text = scrolledtext.ScrolledText(parent, font=("Consolas", 9), wrap="word", state="normal")
        text.pack(fill="both", expand=True, padx=5, pady=5)
        text.insert("1.0", """Monsters and Memories - Game Data Reference
============================================

MACRO TYPES:
  Active:    Sequential scripts — movement, combat rotations, grinding loops.
             Set type: active (or omit, it's the default).
  Reactive:  Rule-based monitors — heal when low, rebuff, mana sit.
             Set type: reactive. Uses priority + cooldown rules.
             Can run alongside an active macro.

ANTI-BOT DETECTION (from IL2CPP dump):
  BotBehaviorDetector:
    - Impossible timing threshold: 100ms
    - Required pattern repetitions: 5
    - Detection cooldown: 300s (5 min)

  InputPatternDetector:
    - Min actions for detection: 10 identical
    - Press duration / interval std dev < 10ms = bot

MOVEMENT:
  - Network update rate: 0.1s (moving), 0.25s (stationary)
  - Modes: Normal, Swimming, Flying, Levitating, Climbing

TARGETING:
  - Max range: 50 units
  - Tab target cycling (hostile/friendly)

POSTURES: Stand, Sit, Crouch, Kneel

STATUS EFFECTS: Stunned, Feared, Mesmerized, Silenced,
  Invisible, Levitating, Sneaking, Shielding
""")
        text.config(state="disabled")

    def _setup_hotkey(self):
        try:
            import keyboard
            key = self.config.get("general", {}).get("failsafe_key", "f12")
            keyboard.add_hotkey(key, self.stop_all)
            self.log.log(f"Hotkey: {key.upper()} = Emergency Stop")
        except ImportError:
            self.log.log("[WARN] 'keyboard' module not installed - no global hotkey")

    def _update_status(self):
        humanizer_cfg = self.config.get("humanizer", {})
        self.status_bar.set_humanizer(
            humanizer_cfg.get("enabled", True),
            humanizer_cfg.get("intensity", 0.5)
        )

    # --- Memory Reader ---

    def _try_connect_memory(self):
        if self.memory_reader.connected:
            self.memory_reader.disconnect()

        try:
            self.memory_reader.connect()
            snap = self.memory_reader.snapshot
            player_name = snap.player["name"] if snap.player else ""
            self.status_bar.set_memory_status(True, player_name)
            self.status_bar.reconnect_btn.config(text="Reconnect")
            self.log.log(f"[MEMORY] Connected — player: {player_name or '(none)'}")
        except Exception as e:
            self.status_bar.set_memory_status(False)
            self.status_bar.reconnect_btn.config(text="Connect")
            self.log.log(f"[MEMORY] Could not connect: {e}")

    def _memory_watchdog(self):
        if self.memory_reader.connected:
            try:
                snap = self.memory_reader.snapshot
                if snap.player:
                    self.status_bar.set_memory_status(True, snap.player["name"])
                else:
                    self.status_bar.set_memory_status(True, "(no character)")
            except Exception:
                self.status_bar.set_memory_status(False)
                self.status_bar.reconnect_btn.config(text="Connect")
                self.log.log("[MEMORY] Connection lost")
                try:
                    self.memory_reader.disconnect()
                except Exception:
                    pass
        self.root.after(5000, self._memory_watchdog)

    # --- Actions ---

    def stop_all(self):
        self.macros_tab.stop_all()
        if self._recording:
            self._stop_recording()
        self.log.log("Emergency stop!")
        self.status_bar.set_status("Ready")

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
        self.log.log("Recording started")

    def _stop_recording(self):
        self._recording = False
        self.recorder.stop()
        self.record_btn.config(text="Record")
        self.status_bar.set_status("Ready")

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
        self.log.log(f"Playing: {os.path.basename(filepath)} at {speed}x")
        self.status_bar.set_status("Playing recording")

        def _play():
            try:
                events = MacroRecorder.load(filepath)
                player = MacroPlayer(self.engine.input)
                player.set_speed(speed)
                player.play_recording(events, loop=False)
                while player.playing:
                    time.sleep(0.1)
            except Exception as e:
                self.root.after(0, lambda: self.log.log(f"[ERROR] {e}"))
            finally:
                self.root.after(0, lambda: self.status_bar.set_status("Ready"))

        threading.Thread(target=_play, daemon=True).start()

    def save_settings(self):
        self.config = self.settings_panel.get_settings()
        save_config(self.config)
        # Rebuild engine with new settings, keeping memory reader
        self.engine = MacroEngine(self.config, memory_reader=self.memory_reader)
        self.macros_tab.set_engine(self.engine)
        self._update_status()
        self.log.log("Settings saved")

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        self.map_tab.on_close()
        self.engine.stop_all()
        if self.memory_reader.connected:
            self.memory_reader.disconnect()
        self.root.destroy()


def main():
    app = MacroToolGUI()
    app.run()


if __name__ == "__main__":
    main()
