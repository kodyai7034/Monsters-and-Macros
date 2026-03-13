"""
Macro engine that loads YAML macro definitions and executes them.

Supports two macro types:
  - Active: sequential scripts (movement, combat rotations, grinding loops)
  - Reactive: rule-based monitors (heal when health low, rebuff, mana sit)

Both types support conditional logic, memory-based conditions, screen reading,
and humanized input to avoid the game's bot detection.
"""

import yaml
import time
import os
import threading
from input_simulator import InputSimulator
from macro_player import MacroPlayer
from screen_reader import ScreenReader


class MacroEngine:
    """Loads and runs macro definitions from YAML files.

    Owns a single InputSimulator and an input lock so that active macros
    and reactive monitors can safely share input without collisions.
    """

    def __init__(self, config, memory_reader=None):
        self.config = config
        input_cfg = config.get("input", {})
        humanizer_cfg = config.get("humanizer", {})
        self.keybinds = config.get("keybinds", {})

        self.input = InputSimulator(
            method=input_cfg.get("method", "directinput"),
            hold_duration=input_cfg.get("hold_duration", 0.05),
            humanize=humanizer_cfg.get("enabled", True),
            humanize_intensity=humanizer_cfg.get("intensity", 0.5),
        )
        self.player = MacroPlayer(self.input)
        self.screen = ScreenReader(config)

        # Memory reader — shared instance, owned and managed by the GUI
        self.memory = memory_reader

        # Active macro state
        self.running = False
        self._pause_event = threading.Event()
        self._pause_event.set()  # not paused initially
        self._current_action = ""  # description of what's executing now

        # Input lock — prevents active + reactive from pressing keys simultaneously
        self._input_lock = threading.Lock()

        # Reactive engine — single loop evaluating rules from all monitors
        self._reactive_engine = ReactiveEngine(self)

    def get_key(self, action_name):
        """Resolve an action name to its keybind."""
        return self.keybinds.get(action_name, action_name)

    def load_macro(self, filepath):
        """Load a macro definition from a YAML file."""
        with open(filepath, "r") as f:
            return yaml.safe_load(f)

    # =====================================================================
    # Active macro execution
    # =====================================================================

    @property
    def paused(self):
        return not self._pause_event.is_set()

    @property
    def current_action(self):
        return self._current_action

    def pause(self):
        """Pause active macro and all reactive monitors."""
        self._pause_event.clear()
        for r in self._reactive_runners.values():
            r.pause()

    def resume(self):
        """Resume active macro and all reactive monitors."""
        self._pause_event.set()
        for r in self._reactive_runners.values():
            r.resume()

    def run_macro(self, macro_def, loop=False):
        """Run an active macro definition."""
        self.running = True
        self._pause_event.set()
        self._current_action = ""
        actions = macro_def.get("actions", [])

        # Log session fingerprint
        if self.input.humanizer:
            info = self.input.humanizer.get_session_info()
            print(f"[SESSION] {info['profile']}")
            print(f"[SESSION] Fatigue: {info['fatigue_factor']}x, Age: {info['session_age_minutes']}min")

        try:
            while self.running:
                self._execute_actions(actions)
                if not loop:
                    break
                base_delay = macro_def.get("loop_delay", 0.1)
                self.input._humanize_delay(base_delay, "macro_loop")
        except KeyboardInterrupt:
            pass
        finally:
            self.running = False
            self._current_action = ""

    def _execute_actions(self, actions):
        """Execute a list of actions, handling conditionals and loops."""
        for action in actions:
            if not self.running:
                break

            # Block here if paused — resumes exactly where we left off
            self._pause_event.wait()
            if not self.running:
                break

            # Occasional idle to look human
            self.input.maybe_idle()

            # Inject random micro-behaviors
            behavior, did_it = self.input.maybe_random_behavior()
            if did_it:
                print(f"[HUMAN] Random behavior: {behavior}")

            act_type = action.get("action")
            self._current_action = self._describe_action(action)

            if act_type == "condition":
                self._handle_condition(action)
            elif act_type == "repeat":
                self._handle_repeat(action)
            elif act_type == "wait_for_health":
                self._wait_for_health(action)
            elif act_type == "wait_for_mana":
                self._wait_for_mana(action)
            elif act_type == "log":
                print(f"[MACRO] {action.get('message', '')}")
            elif act_type == "use_ability":
                with self._input_lock:
                    self._use_ability(action)
            elif act_type == "move_forward":
                with self._input_lock:
                    self.input.move_forward(action.get("duration", 1.0))
            elif act_type == "move_backward":
                with self._input_lock:
                    self.input.move_backward(action.get("duration", 1.0))
            elif act_type == "strafe_left":
                with self._input_lock:
                    self.input.strafe_left(action.get("duration", 1.0))
            elif act_type == "strafe_right":
                with self._input_lock:
                    self.input.strafe_right(action.get("duration", 1.0))
            elif act_type == "turn":
                with self._input_lock:
                    self.input.turn(action.get("dx", 100), action.get("duration", 0.5))
            elif act_type == "target_nearest":
                with self._input_lock:
                    if self.input.humanizer:
                        time.sleep(self.input.humanizer.target_delay())
                    self.input.press_key(self.get_key("target_nearest"))
            elif act_type == "auto_run":
                with self._input_lock:
                    self.input.auto_run_toggle()
            elif act_type == "sit":
                with self._input_lock:
                    self.input.press_key(self.get_key("sit"))
            elif act_type == "stand":
                with self._input_lock:
                    self.input.press_key(self.get_key("sit"))
            elif act_type == "auto_attack":
                with self._input_lock:
                    self.input.press_key(self.get_key("auto_attack"))
            elif act_type == "interact":
                with self._input_lock:
                    self.input.press_key(self.get_key("interact"))
            elif act_type == "target_nearest_hostile":
                with self._input_lock:
                    if self.input.humanizer:
                        time.sleep(self.input.humanizer.target_delay())
                    self.input.press_key(self.get_key("target_nearest_hostile"))
            elif act_type == "assist":
                with self._input_lock:
                    self.input.press_key(self.get_key("assist"))
            elif act_type == "press":
                key = action.get("key", "")
                with self._input_lock:
                    self.input.press_key(self.get_key(key))
            elif act_type == "move_to_target":
                self._move_to_target(action)
            elif act_type == "wait_for_target_dead":
                self._wait_for_target_dead(action)
            elif act_type == "wait_for_combat_end":
                self._wait_for_combat_end(action)
            elif act_type == "wait":
                duration = action.get("duration", 1.0)
                time.sleep(duration)
            else:
                resolved = dict(action)
                if "key" in resolved:
                    resolved["key"] = self.get_key(resolved["key"])
                with self._input_lock:
                    self.player._execute_action(resolved)

    def _describe_action(self, action):
        """Short human-readable description of an action."""
        act = action.get("action", "?")
        if act == "use_ability":
            return f"ability {action.get('slot', '?')}"
        elif act == "move_forward":
            return f"move forward ({action.get('duration', 1.0)}s)"
        elif act == "wait":
            return f"wait ({action.get('duration', 0)}s)"
        elif act == "condition":
            return f"check {action.get('check', '?')}"
        elif act == "log":
            return action.get("message", "")[:40]
        elif act == "wait_for_target_dead":
            return "waiting for target to die"
        elif act == "wait_for_combat_end":
            return "waiting for combat to end"
        elif act == "auto_attack":
            return "auto attack"
        elif act == "interact":
            return "interact/loot"
        elif act == "target_nearest_hostile":
            return "target nearest hostile"
        return act

    def _use_ability(self, action):
        """Use an ability by slot number with anti-detection delay."""
        slot = action.get("slot", 1)
        key_name = f"ability_{slot}"
        key = self.get_key(key_name)
        self.input.press_ability(slot, key)

    # =====================================================================
    # Condition evaluation (shared by active macros and reactive rules)
    # =====================================================================

    def check_condition(self, action):
        """Evaluate a condition and return True/False without executing anything.

        Used by both _handle_condition (active macros) and ReactiveRunner.
        """
        check = action.get("check")
        value = action.get("value", 0.5)

        # Screen-based conditions
        if check == "health_below":
            return self.screen.get_health_percent() < value
        elif check == "health_above":
            return self.screen.get_health_percent() > value
        elif check == "mana_below":
            return self.screen.get_mana_percent() < value
        elif check == "mana_above":
            return self.screen.get_mana_percent() > value
        elif check == "pixel_color":
            x, y = action.get("x", 0), action.get("y", 0)
            expected = tuple(action.get("color", [0, 0, 0]))
            actual = self.screen.get_pixel_color(x, y)
            return self.screen.colors_match(actual, expected)
        elif check == "pixel_not_color":
            x, y = action.get("x", 0), action.get("y", 0)
            expected = tuple(action.get("color", [0, 0, 0]))
            actual = self.screen.get_pixel_color(x, y)
            return not self.screen.colors_match(actual, expected)

        # Memory-based conditions
        elif check == "has_target":
            return self.memory.has_target() if self.memory else False
        elif check == "no_target":
            return not self.memory.has_target() if self.memory else True
        elif check == "target_is_hostile":
            if self.memory:
                t = self.memory.get_target()
                return t["is_hostile"] if t else False
            return False
        elif check == "target_is_corpse":
            if self.memory:
                t = self.memory.get_target()
                return t["is_corpse"] if t else False
            return False
        elif check == "target_is_stunned":
            return self.memory.target_is_stunned() if self.memory else False
        elif check == "target_is_feared":
            return self.memory.target_is_feared() if self.memory else False
        elif check == "target_is_mezzed":
            return self.memory.target_is_mezzed() if self.memory else False
        elif check == "target_has_buff":
            buff_name = action.get("buff_name", "")
            return self.memory.target_has_buff(buff_name) if self.memory else False
        elif check == "target_not_has_buff":
            buff_name = action.get("buff_name", "")
            return not self.memory.target_has_buff(buff_name) if self.memory else True
        elif check == "player_has_buff":
            buff_name = action.get("buff_name", "")
            return self.memory.player_has_buff(buff_name) if self.memory else False
        elif check == "player_not_has_buff":
            buff_name = action.get("buff_name", "")
            return not self.memory.player_has_buff(buff_name) if self.memory else True
        elif check == "player_is_casting":
            return self.memory.player_is_casting() if self.memory else False
        elif check == "player_not_casting":
            return not self.memory.player_is_casting() if self.memory else True
        elif check == "target_name":
            name = action.get("name", "")
            return self.memory.target_name().lower() == name.lower() if self.memory else False
        elif check == "target_name_contains":
            name = action.get("name", "")
            return name.lower() in self.memory.target_name().lower() if self.memory else False
        elif check == "mem_health_below":
            return self.memory.get_health_pct() < value if self.memory else False
        elif check == "mem_health_above":
            return self.memory.get_health_pct() > value if self.memory else False
        elif check == "mem_mana_below":
            return self.memory.get_mana_pct() < value if self.memory else False
        elif check == "mem_mana_above":
            return self.memory.get_mana_pct() > value if self.memory else False

        # --- Player state conditions ---
        elif check == "endurance_below":
            return self.memory.get_endurance_pct() < value if self.memory else False
        elif check == "endurance_above":
            return self.memory.get_endurance_pct() > value if self.memory else False
        elif check == "player_is_sitting":
            return self.memory.player_is_sitting() if self.memory else False
        elif check == "player_is_standing":
            return self.memory.player_is_standing() if self.memory else False
        elif check == "player_is_autoattacking":
            return self.memory.player_is_autoattacking() if self.memory else False
        elif check == "player_not_autoattacking":
            return not self.memory.player_is_autoattacking() if self.memory else True
        elif check == "player_level_above":
            return self.memory.get_player_level() > int(value) if self.memory else False
        elif check == "player_level_below":
            return self.memory.get_player_level() < int(value) if self.memory else False
        elif check == "player_buff_count_above":
            return self.memory.player_buff_count() > int(value) if self.memory else False
        elif check == "player_buff_count_below":
            return self.memory.player_buff_count() < int(value) if self.memory else False

        # --- Target conditions ---
        elif check == "target_health_below":
            return self.memory.get_target_health_pct() < value if self.memory else False
        elif check == "target_health_above":
            return self.memory.get_target_health_pct() > value if self.memory else False
        elif check == "target_level_above":
            return self.memory.target_level() > int(value) if self.memory else False
        elif check == "target_level_below":
            return self.memory.target_level() < int(value) if self.memory else False
        elif check == "target_has_buff_category":
            category = action.get("category", "")
            return self.memory.target_has_category(category) if self.memory else False
        elif check == "target_not_has_buff_category":
            category = action.get("category", "")
            return not self.memory.target_has_category(category) if self.memory else True

        # --- Combat state (derived) ---
        elif check == "in_combat":
            if self.memory:
                return self.memory.player_is_autoattacking() or (
                    self.memory.has_target() and
                    self.memory.get_target() and
                    self.memory.get_target().get("is_hostile", False)
                )
            return False
        elif check == "not_in_combat":
            if self.memory:
                return not self.memory.player_is_autoattacking() and not (
                    self.memory.has_target() and
                    self.memory.get_target() and
                    self.memory.get_target().get("is_hostile", False)
                )
            return True

        # --- Zone conditions ---
        elif check == "zone_is":
            zone = action.get("zone", "")
            if self.memory:
                current = self.memory.get_zone_name()
                return current.lower() == zone.lower()
            return False
        elif check == "zone_is_not":
            zone = action.get("zone", "")
            if self.memory:
                current = self.memory.get_zone_name()
                return current.lower() != zone.lower()
            return True

        # --- Compound logic ---
        elif check == "and":
            conditions = action.get("conditions", [])
            return all(self.check_condition(c) for c in conditions)
        elif check == "or":
            conditions = action.get("conditions", [])
            return any(self.check_condition(c) for c in conditions)
        elif check == "not":
            inner = action.get("condition", {})
            return not self.check_condition(inner)

        return False

    def _handle_condition(self, action):
        """Handle conditional action execution in active macros."""
        result = self.check_condition(action)

        if result:
            then_actions = action.get("then", [])
            self._execute_actions(then_actions)
        else:
            else_actions = action.get("else", [])
            if else_actions:
                self._execute_actions(else_actions)

    def _handle_repeat(self, action):
        """Handle repeated action blocks."""
        times = action.get("times", 1)
        sub_actions = action.get("actions", [])
        for _ in range(times):
            if not self.running:
                break
            self._pause_event.wait()
            self._execute_actions(sub_actions)

    def _wait_for_health(self, action):
        """Wait until health is above a threshold."""
        target = action.get("above", 0.8)
        timeout = action.get("timeout", 30)
        interval = action.get("interval", 0.5)
        start = time.time()

        while self.running and time.time() - start < timeout:
            self._pause_event.wait()
            if self.screen.get_health_percent() >= target:
                return
            self.input._humanize_delay(interval, "health_check")

        print(f"[MACRO] Health wait timed out after {timeout}s")

    def _wait_for_mana(self, action):
        """Wait until mana is above a threshold."""
        target = action.get("above", 0.8)
        timeout = action.get("timeout", 30)
        interval = action.get("interval", 0.5)
        start = time.time()

        while self.running and time.time() - start < timeout:
            self._pause_event.wait()
            if self.screen.get_mana_percent() >= target:
                return
            self.input._humanize_delay(interval, "mana_check")

        print(f"[MACRO] Mana wait timed out after {timeout}s")

    def _move_to_target(self, action):
        """Move toward the current target until within range.

        Uses player heading to calculate turn direction, then moves forward.
        Compares current heading to the angle toward the target and issues
        mouse-turn adjustments to face the target before moving.

        Parameters:
            range: stop distance (default 5.0 game units)
            timeout: max time to spend moving (default 15s)
        """
        import math

        stop_range = action.get("range", 5.0)
        timeout = action.get("timeout", 15.0)
        start = time.time()

        if not self.memory:
            print("[MACRO] move_to_target requires memory reader")
            return

        self._current_action = f"moving to target (range {stop_range})"

        while self.running and time.time() - start < timeout:
            self._pause_event.wait()
            if not self.running:
                return

            # Check we still have a living target
            if not self.memory.has_target():
                print("[MACRO] Lost target while moving")
                return
            t = self.memory.get_target()
            if t and t.get("is_corpse", False):
                return

            dist = self.memory.get_distance_to_target()
            if dist <= stop_range:
                print(f"[MACRO] In range ({dist:.1f} <= {stop_range})")
                return

            # Calculate desired heading toward target
            px, _, pz = self.memory.get_player_position()
            tx, _, tz = self.memory.get_target_position()
            dx = tx - px
            dz = tz - pz

            # atan2 gives angle from +X axis; game heading 0° may differ
            # Game heading is in degrees 0-360. We need to figure out the
            # mapping. For now: desired = degrees(atan2(dx, dz)) mapped to 0-360
            # (using atan2(dx, dz) so 0° = +Z direction, common in games)
            desired_heading = math.degrees(math.atan2(dx, dz)) % 360

            current_heading = self.memory.get_player_heading()

            # Signed angle difference (-180 to +180)
            angle_diff = (desired_heading - current_heading + 180) % 360 - 180

            # Turn toward target if not roughly facing it
            if abs(angle_diff) > 5.0:
                # Convert angle difference to mouse dx pixels
                # Rough calibration: ~4 pixels per degree of turn
                turn_px = int(angle_diff * 4)
                # Clamp to avoid huge mouse moves
                turn_px = max(-400, min(400, turn_px))

                with self._input_lock:
                    self.input.turn(turn_px, duration=0.15)
                time.sleep(0.15)
                continue  # re-check heading after turn

            # Facing target — move forward
            move_time = min(0.5, max(0.1, dist / 50.0))
            with self._input_lock:
                self.input.move_forward(move_time)

            time.sleep(0.1)

        print(f"[MACRO] move_to_target timed out after {timeout}s")

    def _wait_for_target_dead(self, action):
        """Wait until the current target is a corpse or no target remains."""
        timeout = action.get("timeout", 60)
        interval = action.get("interval", 0.3)
        start = time.time()

        while self.running and time.time() - start < timeout:
            self._pause_event.wait()
            if not self.running:
                return
            if self.memory:
                # Target died (is corpse) or target lost
                if not self.memory.has_target():
                    return
                t = self.memory.get_target()
                if t and t.get("is_corpse", False):
                    return
            time.sleep(interval)

        print(f"[MACRO] Target dead wait timed out after {timeout}s")

    def _wait_for_combat_end(self, action):
        """Wait until no longer in combat (no hostile target, not autoattacking)."""
        timeout = action.get("timeout", 60)
        interval = action.get("interval", 0.5)
        start = time.time()

        while self.running and time.time() - start < timeout:
            self._pause_event.wait()
            if not self.running:
                return
            if self.memory:
                if not self.memory.player_is_autoattacking() and not self.memory.has_target():
                    return
            time.sleep(interval)

        print(f"[MACRO] Combat end wait timed out after {timeout}s")

    # =====================================================================
    # Reactive monitors — single shared evaluation loop
    # =====================================================================

    def start_reactive(self, macro_def):
        """Add a reactive macro's rules to the shared reactive engine."""
        name = macro_def.get("name", "Unnamed")
        self._reactive_engine.add_monitor(name, macro_def)
        print(f"[REACTIVE] Started: {name}")

    def stop_reactive(self, name):
        """Remove a reactive macro's rules from the shared reactive engine."""
        self._reactive_engine.remove_monitor(name)
        print(f"[REACTIVE] Stopped: {name}")

    def stop_all_reactive(self):
        """Remove all reactive monitors."""
        self._reactive_engine.remove_all()

    def get_reactive_names(self):
        """Get names of currently active reactive monitors."""
        return self._reactive_engine.get_monitor_names()

    def is_reactive_running(self, name):
        """Check if a reactive monitor is currently loaded."""
        return name in self._reactive_engine.get_monitor_names()

    def get_reactive_current_rule(self):
        """Get the name of the rule currently firing (if any)."""
        return self._reactive_engine.current_rule

    # =====================================================================
    # Stop / cleanup
    # =====================================================================

    def stop(self):
        """Stop active macro execution (does not stop reactive monitors)."""
        self.running = False
        self._pause_event.set()  # unblock if paused so thread can exit
        self.player.stop()
        self._current_action = ""

    def stop_all(self):
        """Stop everything — active macro and all reactive monitors."""
        self.stop()
        self.stop_all_reactive()

    def list_macros(self, directory="macros"):
        """List available macro files."""
        macros = []
        if os.path.isdir(directory):
            for f in sorted(os.listdir(directory)):
                if f.endswith((".yaml", ".yml")):
                    macros.append(f)
        return macros

    def list_macros_by_type(self, directory="macros"):
        """List macros grouped by type. Returns (active_list, reactive_list).

        Each entry is (filename, name, description).
        """
        active = []
        reactive = []
        if not os.path.isdir(directory):
            return active, reactive

        for f in sorted(os.listdir(directory)):
            if not f.endswith((".yaml", ".yml")):
                continue
            try:
                with open(os.path.join(directory, f), "r") as fh:
                    data = yaml.safe_load(fh)
                if not data:
                    continue
                entry = (f, data.get("name", f), data.get("description", ""))
                if data.get("type") == "reactive":
                    reactive.append(entry)
                else:
                    active.append(entry)
            except Exception:
                active.append((f, f, "(failed to parse)"))

        return active, reactive


class ReactiveEngine:
    """Single-threaded reactive evaluation engine.

    Collects rules from multiple monitors into one global priority queue.
    One background thread evaluates all rules each tick, firing the single
    highest-priority matching rule that isn't on cooldown. This prevents
    conflicts between monitors (e.g. sit vs stand) by design.

    Inspired by MacroQuest's single-loop architecture where all conditions
    are evaluated in priority order within one main loop.
    """

    # Default tick rate when no monitors are loaded
    DEFAULT_POLL_INTERVAL = 0.2

    def __init__(self, engine):
        self.engine = engine
        self._monitors = {}       # name -> {"rules": [...], "poll_interval": float}
        self._global_rules = []   # merged + sorted list of (priority, monitor_name, rule)
        self._cooldowns = {}      # "monitor_name:rule_name" -> last_fire_time
        self._current_rule = ""
        self._running = False
        self._thread = None
        self._lock = threading.Lock()  # protects _monitors and _global_rules

    @property
    def current_rule(self):
        return self._current_rule

    def add_monitor(self, name, macro_def):
        """Add a monitor's rules to the global queue and start if needed."""
        rules = macro_def.get("rules", [])
        poll_interval = macro_def.get("poll_interval", self.DEFAULT_POLL_INTERVAL)

        with self._lock:
            # Remove existing monitor with same name first
            self._monitors.pop(name, None)
            self._monitors[name] = {
                "rules": rules,
                "poll_interval": poll_interval,
            }
            self._rebuild_global_rules()

        # Start the evaluation thread if not already running
        if not self._running:
            self._start()

    def remove_monitor(self, name):
        """Remove a monitor's rules from the global queue."""
        with self._lock:
            if name not in self._monitors:
                return
            del self._monitors[name]
            # Clean up cooldowns for this monitor
            prefix = f"{name}:"
            self._cooldowns = {
                k: v for k, v in self._cooldowns.items()
                if not k.startswith(prefix)
            }
            self._rebuild_global_rules()

        # Stop thread if no monitors remain
        if not self._monitors:
            self._stop()

    def remove_all(self):
        """Remove all monitors and stop the evaluation thread."""
        with self._lock:
            self._monitors.clear()
            self._global_rules.clear()
            self._cooldowns.clear()
        self._stop()

    def get_monitor_names(self):
        """Get names of all loaded monitors."""
        with self._lock:
            return list(self._monitors.keys())

    def _rebuild_global_rules(self):
        """Merge all monitor rules into one priority-sorted list.
        Must be called with self._lock held.
        """
        merged = []
        for mon_name, mon_data in self._monitors.items():
            for rule in mon_data["rules"]:
                priority = rule.get("priority", 50)
                merged.append((priority, mon_name, rule))
        # Sort by priority (lower number = higher priority)
        merged.sort(key=lambda x: x[0])
        self._global_rules = merged

    def _get_poll_interval(self):
        """Use the fastest (lowest) poll interval across all monitors."""
        with self._lock:
            if not self._monitors:
                return self.DEFAULT_POLL_INTERVAL
            return min(m["poll_interval"] for m in self._monitors.values())

    def _start(self):
        """Start the evaluation thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="ReactiveEngine"
        )
        self._thread.start()

    def _stop(self):
        """Stop the evaluation thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        self._current_rule = ""

    def _loop(self):
        """Main evaluation loop — one thread, one priority queue."""
        while self._running:
            try:
                self._evaluate()
            except Exception as e:
                print(f"[REACTIVE] Engine error: {e}")

            # Sleep in small increments so we can stop quickly
            interval = self._get_poll_interval()
            end_time = time.monotonic() + interval
            while self._running and time.monotonic() < end_time:
                time.sleep(min(0.05, end_time - time.monotonic()))

        self._current_rule = ""

    def _evaluate(self):
        """Evaluate all rules in global priority order. Fire the first match."""
        now = time.monotonic()

        with self._lock:
            rules_snapshot = list(self._global_rules)

        for priority, mon_name, rule in rules_snapshot:
            rule_name = rule.get("name", "unnamed")
            cooldown_key = f"{mon_name}:{rule_name}"

            # Check cooldown
            cooldown = rule.get("cooldown", 0)
            last_fired = self._cooldowns.get(cooldown_key, 0)
            if now - last_fired < cooldown:
                continue

            # Check condition
            condition = rule.get("condition", {})
            if not condition:
                continue

            if self.engine.check_condition(condition):
                self._current_rule = f"{mon_name}: {rule_name}"
                self._cooldowns[cooldown_key] = now
                print(f"[REACTIVE] {mon_name}: firing '{rule_name}' (pri {priority})")

                # Execute the rule's actions
                self._execute_actions(rule.get("actions", []))

                # Only fire one rule per tick — highest priority wins
                return

        self._current_rule = ""

    def _execute_actions(self, actions):
        """Execute a rule's action list."""
        for action in actions:
            if not self._running:
                break
            act_type = action.get("action")
            if act_type == "use_ability":
                with self.engine._input_lock:
                    self.engine._use_ability(action)
            elif act_type == "sit":
                with self.engine._input_lock:
                    self.engine.input.press_key(self.engine.get_key("sit"))
            elif act_type == "stand":
                with self.engine._input_lock:
                    self.engine.input.press_key(self.engine.get_key("sit"))
            elif act_type == "wait":
                time.sleep(action.get("duration", 0.5))
            elif act_type == "log":
                print(f"[REACTIVE] {action.get('message', '')}")
            elif act_type == "press":
                key = action.get("key", "")
                key = self.engine.get_key(key)
                with self.engine._input_lock:
                    self.engine.input.press_key(key)
            else:
                # Generic key action
                resolved = dict(action)
                if "key" in resolved:
                    resolved["key"] = self.engine.get_key(resolved["key"])
                with self.engine._input_lock:
                    self.engine.player._execute_action(resolved)
