"""
Macro engine that loads YAML macro definitions and executes them.
Supports conditional logic, loops, screen-reading conditions,
memory-based conditions, and humanized input to avoid the game's bot detection.
"""

import yaml
import time
import os
from input_simulator import InputSimulator
from macro_player import MacroPlayer
from screen_reader import ScreenReader
from memory_reader import GameMemoryReader


class MacroEngine:
    """Loads and runs macro definitions from YAML files."""

    def __init__(self, config):
        self.config = config
        input_cfg = config.get("input", {})
        humanizer_cfg = config.get("humanizer", {})
        memory_cfg = config.get("memory", {})
        self.keybinds = config.get("keybinds", {})

        self.input = InputSimulator(
            method=input_cfg.get("method", "directinput"),
            hold_duration=input_cfg.get("hold_duration", 0.05),
            humanize=humanizer_cfg.get("enabled", True),
            humanize_intensity=humanizer_cfg.get("intensity", 0.5),
        )
        self.player = MacroPlayer(self.input)
        self.screen = ScreenReader(config)
        self.running = False

        # Memory reader (optional — requires pymem and game running)
        self.memory = None
        if memory_cfg.get("enabled", False):
            self.memory = GameMemoryReader(config=memory_cfg)
            try:
                self.memory.connect()
                print("[ENGINE] Memory reader connected")
            except Exception as e:
                print(f"[ENGINE] Memory reader failed to connect: {e}")
                self.memory = None

    def get_key(self, action_name):
        """Resolve an action name to its keybind."""
        return self.keybinds.get(action_name, action_name)

    def load_macro(self, filepath):
        """Load a macro definition from a YAML file."""
        with open(filepath, "r") as f:
            return yaml.safe_load(f)

    def run_macro(self, macro_def, loop=False):
        """
        Run a macro definition.

        Macro format:
          name: "My Macro"
          description: "Does something"
          actions:
            - action: press
              key: "ability_1"    # Uses keybind names or raw keys
              delay: 0.5
            - action: wait
              duration: 2.0
            - action: condition
              check: health_below
              value: 0.5
              then:
                - action: press
                  key: "ability_5"
            - action: repeat
              times: 3
              actions:
                - action: move_forward
                  duration: 2.0
            - action: use_ability
              slot: 1
        """
        self.running = True
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
                # Humanized loop delay
                base_delay = macro_def.get("loop_delay", 0.1)
                self.input._humanize_delay(base_delay, "macro_loop")
        except KeyboardInterrupt:
            pass
        finally:
            self.running = False

    def _execute_actions(self, actions):
        """Execute a list of actions, handling conditionals and loops."""
        for action in actions:
            if not self.running:
                break

            # Occasional idle to look human
            self.input.maybe_idle()

            # Inject random micro-behaviors (look around, jump, etc.)
            behavior, did_it = self.input.maybe_random_behavior()
            if did_it:
                print(f"[HUMAN] Random behavior: {behavior}")

            act_type = action.get("action")

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
                self._use_ability(action)
            elif act_type == "move_forward":
                self.input.move_forward(action.get("duration", 1.0))
            elif act_type == "move_backward":
                self.input.move_backward(action.get("duration", 1.0))
            elif act_type == "strafe_left":
                self.input.strafe_left(action.get("duration", 1.0))
            elif act_type == "strafe_right":
                self.input.strafe_right(action.get("duration", 1.0))
            elif act_type == "turn":
                self.input.turn(action.get("dx", 100), action.get("duration", 0.5))
            elif act_type == "target_nearest":
                if self.input.humanizer:
                    time.sleep(self.input.humanizer.target_delay())
                self.input.press_key(self.get_key("target_nearest"))
            elif act_type == "auto_run":
                self.input.auto_run_toggle()
            elif act_type == "sit":
                self.input.press_key(self.get_key("sit"))
            else:
                # Resolve keybind names in press/hold actions
                resolved = dict(action)
                if "key" in resolved:
                    resolved["key"] = self.get_key(resolved["key"])
                self.player._execute_action(resolved)

    def _use_ability(self, action):
        """Use an ability by slot number with anti-detection delay."""
        slot = action.get("slot", 1)
        key_name = f"ability_{slot}"
        key = self.get_key(key_name)
        self.input.press_ability(slot, key)

    def _handle_condition(self, action):
        """Handle conditional action execution."""
        check = action.get("check")
        value = action.get("value", 0.5)
        result = False

        # Screen-based conditions
        if check == "health_below":
            result = self.screen.get_health_percent() < value
        elif check == "health_above":
            result = self.screen.get_health_percent() > value
        elif check == "mana_below":
            result = self.screen.get_mana_percent() < value
        elif check == "mana_above":
            result = self.screen.get_mana_percent() > value
        elif check == "pixel_color":
            x, y = action.get("x", 0), action.get("y", 0)
            expected = tuple(action.get("color", [0, 0, 0]))
            actual = self.screen.get_pixel_color(x, y)
            result = self.screen.colors_match(actual, expected)
        elif check == "pixel_not_color":
            x, y = action.get("x", 0), action.get("y", 0)
            expected = tuple(action.get("color", [0, 0, 0]))
            actual = self.screen.get_pixel_color(x, y)
            result = not self.screen.colors_match(actual, expected)

        # Memory-based conditions (require memory reader)
        elif check == "has_target":
            result = self.memory.has_target() if self.memory else False
        elif check == "no_target":
            result = not self.memory.has_target() if self.memory else True
        elif check == "target_is_hostile":
            if self.memory:
                t = self.memory.get_target()
                result = t["is_hostile"] if t else False
        elif check == "target_is_corpse":
            if self.memory:
                t = self.memory.get_target()
                result = t["is_corpse"] if t else False
        elif check == "target_is_stunned":
            result = self.memory.target_is_stunned() if self.memory else False
        elif check == "target_is_feared":
            result = self.memory.target_is_feared() if self.memory else False
        elif check == "target_is_mezzed":
            result = self.memory.target_is_mezzed() if self.memory else False
        elif check == "target_has_buff":
            buff_name = action.get("buff_name", "")
            result = self.memory.target_has_buff(buff_name) if self.memory else False
        elif check == "target_not_has_buff":
            buff_name = action.get("buff_name", "")
            result = not self.memory.target_has_buff(buff_name) if self.memory else True
        elif check == "player_has_buff":
            buff_name = action.get("buff_name", "")
            result = self.memory.player_has_buff(buff_name) if self.memory else False
        elif check == "player_not_has_buff":
            buff_name = action.get("buff_name", "")
            result = not self.memory.player_has_buff(buff_name) if self.memory else True
        elif check == "player_is_casting":
            result = self.memory.player_is_casting() if self.memory else False
        elif check == "player_not_casting":
            result = not self.memory.player_is_casting() if self.memory else True
        elif check == "target_name":
            name = action.get("name", "")
            result = self.memory.target_name().lower() == name.lower() if self.memory else False
        elif check == "target_name_contains":
            name = action.get("name", "")
            result = name.lower() in self.memory.target_name().lower() if self.memory else False
        elif check == "mem_health_below":
            if self.memory:
                pct = self.memory.get_health_pct()
                result = pct < value
        elif check == "mem_health_above":
            if self.memory:
                pct = self.memory.get_health_pct()
                result = pct > value
        elif check == "mem_mana_below":
            if self.memory:
                pct = self.memory.get_mana_pct()
                result = pct < value
        elif check == "mem_mana_above":
            if self.memory:
                pct = self.memory.get_mana_pct()
                result = pct > value

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
            self._execute_actions(sub_actions)

    def _wait_for_health(self, action):
        """Wait until health is above a threshold."""
        target = action.get("above", 0.8)
        timeout = action.get("timeout", 30)
        interval = action.get("interval", 0.5)
        start = time.time()

        while self.running and time.time() - start < timeout:
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
            if self.screen.get_mana_percent() >= target:
                return
            self.input._humanize_delay(interval, "mana_check")

        print(f"[MACRO] Mana wait timed out after {timeout}s")

    def stop(self):
        """Stop macro execution."""
        self.running = False
        self.player.stop()
        if self.memory:
            self.memory.disconnect()

    def list_macros(self, directory="macros"):
        """List available macro files."""
        macros = []
        if os.path.isdir(directory):
            for f in os.listdir(directory):
                if f.endswith((".yaml", ".yml")):
                    macros.append(f)
        return macros
