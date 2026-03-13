"""
Dry-Run Macro Test
==================
Runs actual YAML macros through the full engine pipeline without sending
real input. Every action is intercepted, logged, and fed through the
game's detection simulators.

Tests the complete chain:
  YAML parsing → MacroEngine → InputSimulator → Humanizer → detection check

Usage:
    python3 test_dryrun.py                          # Run all macro files
    python3 test_dryrun.py macros/enchanter_cc.yaml  # Run specific macro
    python3 test_dryrun.py -v                        # Verbose output
    python3 test_dryrun.py --cycles 10               # Limit repeat cycles
"""

import sys
import os
import time
import yaml
import statistics
from collections import defaultdict

sys.path.insert(0, ".")
from humanizer import Humanizer
from test_detection import (
    BotBehaviorDetector,
    InputPatternDetector,
    RapidClickDetector,
    Colors,
    header,
    passed,
    failed,
    warn,
)


class DryRunInput:
    """
    Drop-in replacement for InputSimulator that logs actions
    instead of sending real input. Tracks all timing data.
    """

    def __init__(self, humanize_intensity=0.5):
        self.humanizer = Humanizer(intensity=humanize_intensity)
        self.action_log = []
        self.sim_time = 0.0
        self._start_time = time.time()

    def _record(self, action_type, **kwargs):
        entry = {
            "time": self.sim_time,
            "action": action_type,
            **kwargs,
        }
        self.action_log.append(entry)
        return entry

    def _advance_time(self, seconds):
        self.sim_time += seconds

    def _humanize_delay(self, base=0.05, action_name=None):
        if action_name:
            d = self.humanizer.action_delay(action_name, base)
        else:
            d = self.humanizer.delay(base)
        self._advance_time(d)
        return d

    def _humanize_hold(self, base=0.05):
        return self.humanizer.key_hold_duration(base)

    def press_key(self, key, duration=None):
        hold = self._humanize_hold(duration or 0.05)
        self._record("key_press", key=key, hold_ms=hold * 1000)
        self._advance_time(hold)

    def hold_key(self, key, duration):
        duration = self.humanizer.movement_duration(duration)
        self._record("key_hold", key=key, hold_ms=duration * 1000)
        self._advance_time(duration)

    def key_down(self, key):
        self._record("key_down", key=key)

    def key_up(self, key):
        self._record("key_up", key=key)

    def type_text(self, text, interval=0.05):
        for char in text:
            iv = self.humanizer.typing_interval(interval)
            self._record("type_char", char=char, interval_ms=iv * 1000)
            self._advance_time(iv)

    def key_combo(self, *keys):
        self._record("key_combo", keys=list(keys))
        for _ in keys:
            self._advance_time(self._humanize_hold(0.02))
        self._advance_time(self._humanize_hold(0.05))

    def move_mouse(self, x, y, duration=0.1, humanize_path=True):
        self._record("mouse_move", x=x, y=y)
        self._advance_time(duration)

    def move_mouse_relative(self, dx, dy, duration=0.1):
        self._record("mouse_move_rel", dx=dx, dy=dy)
        self._advance_time(0.01)

    def click(self, x=None, y=None, button="left"):
        if self.humanizer and x is not None and y is not None:
            x, y = self.humanizer.mouse_offset(x, y)
        self._record("click", x=x, y=y, button=button)

    def double_click(self, x=None, y=None):
        self.click(x, y)
        gap = self._humanize_hold(0.08)
        self._advance_time(gap)
        self.click(x, y)

    def right_click(self, x=None, y=None):
        self.click(x, y, button="right")

    def mouse_down(self, button="left"):
        self._record("mouse_down", button=button)

    def mouse_up(self, button="left"):
        self._record("mouse_up", button=button)

    def scroll(self, amount):
        amount = self.humanizer.scroll_amount(amount)
        self._record("scroll", amount=amount)

    def get_mouse_position(self):
        return (960, 540)

    def press_ability(self, slot_index, key):
        d = self.humanizer.ability_delay(slot_index)
        self._advance_time(d)
        hold = self._humanize_hold(0.05)
        self._record("ability", slot=slot_index, key=key, delay_ms=d * 1000, hold_ms=hold * 1000)
        self._advance_time(hold)

    def move_forward(self, duration=1.0):
        self.hold_key("w", duration)

    def move_backward(self, duration=1.0):
        self.hold_key("s", duration)

    def strafe_left(self, duration=1.0):
        self.hold_key("a", duration)

    def strafe_right(self, duration=1.0):
        self.hold_key("d", duration)

    def turn(self, dx, duration=0.5):
        self._record("turn", dx=dx, duration=duration)
        self._advance_time(duration)

    def auto_run_toggle(self):
        self.press_key("numlock")

    def maybe_idle(self):
        if self.humanizer.should_idle():
            d = self.humanizer.idle_duration()
            self._record("idle", duration_ms=d * 1000)
            self._advance_time(d)
            return True
        return False

    def maybe_random_behavior(self):
        if not self.humanizer.should_inject_behavior():
            return None, False
        behavior, params = self.humanizer.get_random_behavior()
        self._record("random_behavior", behavior=behavior, params=params)
        # Simulate time for the behavior
        dur = params.get("duration", 0.2)
        self._advance_time(dur)
        return behavior, True


class DryRunScreenReader:
    """
    Mock screen reader that simulates game state for dry-run testing.
    Returns configurable health/mana values.
    """

    def __init__(self, health=0.85, mana=0.7):
        self.health = health
        self.mana = mana
        self._health_regen = 0.001  # per check
        self._mana_regen = 0.002

    def get_health_percent(self):
        # Slowly regen during waits
        self.health = min(1.0, self.health + self._health_regen)
        return self.health

    def get_mana_percent(self):
        self.mana = min(1.0, self.mana + self._mana_regen)
        return self.mana

    def get_pixel_color(self, x, y):
        return (0, 200, 0)

    def colors_match(self, c1, c2, tolerance=30):
        return all(abs(a - b) <= tolerance for a, b in zip(c1, c2))

    def set_health(self, v):
        self.health = v

    def set_mana(self, v):
        self.mana = v


class DryRunEngine:
    """
    Macro engine that uses dry-run input and mock screen reader.
    Limits repeat cycles to keep tests fast.
    """

    def __init__(self, max_cycles=5, humanize_intensity=0.5):
        self.input = DryRunInput(humanize_intensity=humanize_intensity)
        self.screen = DryRunScreenReader()
        self.keybinds = {
            "target_nearest": "tab",
            "sit": "x",
            "auto_run": "numlock",
            **{f"ability_{i}": str(i) for i in range(1, 11)},
        }
        self.running = False
        self.max_cycles = max_cycles

    def get_key(self, action_name):
        return self.keybinds.get(action_name, action_name)

    def load_macro(self, filepath):
        with open(filepath, "r") as f:
            return yaml.safe_load(f)

    def run_macro(self, macro_def):
        self.running = True
        actions = macro_def.get("actions", [])
        try:
            self._execute_actions(actions)
        except KeyboardInterrupt:
            pass
        finally:
            self.running = False

    def _execute_actions(self, actions):
        for action in actions:
            if not self.running:
                break

            self.input.maybe_idle()
            self.input.maybe_random_behavior()

            act_type = action.get("action")

            if act_type == "condition":
                self._handle_condition(action)
            elif act_type == "repeat":
                self._handle_repeat(action)
            elif act_type == "wait_for_health":
                self._wait_for_resource("health", action)
            elif act_type == "wait_for_mana":
                self._wait_for_resource("mana", action)
            elif act_type == "log":
                pass  # Suppress macro log output during test
            elif act_type == "use_ability":
                slot = action.get("slot", 1)
                key = self.get_key(f"ability_{slot}")
                self.input.press_ability(slot, key)
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
                d = self.input.humanizer.target_delay()
                self.input._advance_time(d)
                self.input.press_key(self.get_key("target_nearest"))
                self.input._record("target", delay_ms=d * 1000)
            elif act_type == "auto_run":
                self.input.auto_run_toggle()
            elif act_type == "sit":
                self.input.press_key(self.get_key("sit"))
            elif act_type == "wait":
                dur = action.get("duration", 1.0)
                self.input._advance_time(dur)
            elif act_type == "press":
                key = action.get("key", "")
                key = self.get_key(key)
                self.input.press_key(key, action.get("duration"))
                if action.get("delay"):
                    self.input._advance_time(action["delay"])
            elif act_type == "hold":
                key = self.get_key(action.get("key", ""))
                self.input.hold_key(key, action.get("duration", 1.0))
            elif act_type == "click":
                self.input.click(action.get("x"), action.get("y"), action.get("button", "left"))
            elif act_type == "type":
                self.input.type_text(action.get("text", ""), action.get("interval", 0.05))
            elif act_type == "combo":
                self.input.key_combo(*action.get("keys", []))
            elif act_type == "scroll":
                self.input.scroll(action.get("amount", 3))

            # Handle per-action delay
            delay = action.get("delay")
            if delay and act_type not in ("press", "wait"):
                self.input._humanize_delay(delay, act_type)

    def _handle_condition(self, action):
        check = action.get("check")
        value = action.get("value", 0.5)
        result = False

        if check == "health_below":
            result = self.screen.get_health_percent() < value
        elif check == "health_above":
            result = self.screen.get_health_percent() > value
        elif check == "mana_below":
            result = self.screen.get_mana_percent() < value
        elif check == "mana_above":
            result = self.screen.get_mana_percent() > value
        elif check == "pixel_color":
            result = True
        elif check == "pixel_not_color":
            result = False

        if result:
            self._execute_actions(action.get("then", []))
        else:
            self._execute_actions(action.get("else", []))

    def _handle_repeat(self, action):
        times = min(action.get("times", 1), self.max_cycles)
        sub_actions = action.get("actions", [])
        for _ in range(times):
            if not self.running:
                break
            self._execute_actions(sub_actions)

    def _wait_for_resource(self, resource, action):
        target = action.get("above", 0.8)
        timeout = action.get("timeout", 30)
        interval = action.get("interval", 0.5)

        # Simulate waiting — just advance time and set resource high
        wait_time = min(timeout * 0.3, 10)  # Don't burn too much sim time
        self.input._advance_time(wait_time)
        if resource == "health":
            self.screen.set_health(max(self.screen.health, target))
        else:
            self.screen.set_mana(max(self.screen.mana, target))


def analyze_log(action_log, verbose=False):
    """Analyze a dry-run action log through all detection systems."""

    bot_det = BotBehaviorDetector()
    pattern_det = InputPatternDetector()
    rapid_det = RapidClickDetector()

    # Collect timing statistics
    ability_delays = []
    target_delays = []
    key_holds = []
    action_intervals = defaultdict(list)
    last_action_time = defaultdict(float)

    for entry in action_log:
        t = entry["time"]
        action = entry["action"]

        if action == "ability":
            delay_ms = entry["delay_ms"]
            ability_delays.append(delay_ms)
            bot_det.record_ability_timing(delay_ms, f"slot_{entry['slot']}")
            rapid_det.record_click(t)

            # Track interval for this specific ability
            key = f"ability_{entry['slot']}"
            if key in last_action_time:
                interval = t - last_action_time[key]
                action_intervals[key].append(interval * 1000)
            last_action_time[key] = t

            # Record press in pattern detector
            pattern_det.record_action(key, entry.get("hold_ms", 50), timestamp=t)

        elif action == "target":
            delay_ms = entry["delay_ms"]
            target_delays.append(delay_ms)
            bot_det.record_target_acquisition(delay_ms)

        elif action == "key_press":
            hold = entry.get("hold_ms", 50)
            key_holds.append(hold)
            key = entry.get("key", "unknown")
            pattern_det.record_action(f"key_{key}", hold, timestamp=t)

            if f"key_{key}" in last_action_time:
                interval = t - last_action_time[f"key_{key}"]
                action_intervals[f"key_{key}"].append(interval * 1000)
            last_action_time[f"key_{key}"] = t

        elif action == "click":
            rapid_det.record_click(t)

    return {
        "bot_det": bot_det,
        "pattern_det": pattern_det,
        "rapid_det": rapid_det,
        "ability_delays": ability_delays,
        "target_delays": target_delays,
        "key_holds": key_holds,
        "action_intervals": action_intervals,
    }


def test_macro_file(filepath, max_cycles=5, verbose=False):
    """Run a single macro through dry-run and detection analysis."""

    name = os.path.basename(filepath)
    header(f"DRY-RUN: {name}")

    engine = DryRunEngine(max_cycles=max_cycles)
    macro_def = engine.load_macro(filepath)

    print(f"  Macro: {macro_def.get('name', 'unnamed')}")
    print(f"  Description: {macro_def.get('description', '')}")
    print(f"  Max repeat cycles: {max_cycles}")

    engine.run_macro(macro_def)

    log = engine.input.action_log
    sim_time = engine.input.sim_time

    print(f"  Actions logged: {len(log)}")
    print(f"  Simulated time: {sim_time:.1f}s ({sim_time/60:.1f} min)")

    # Count action types
    type_counts = defaultdict(int)
    for entry in log:
        type_counts[entry["action"]] += 1

    if verbose:
        print(f"  Action breakdown:")
        for act, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            print(f"    {act}: {count}")

    # Run detection analysis
    results = analyze_log(log, verbose)
    test_results = {"passed": 0, "failed": 0, "warned": 0}

    # Detection results
    bot_dets = len(results["bot_det"].detections)
    pat_dets = len(results["pattern_det"].detections)
    rapid_dets = len(results["rapid_det"].detections)
    total_dets = bot_dets + pat_dets + rapid_dets

    print(f"\n  Detection results:")
    print(f"    BotBehaviorDetector:  {bot_dets}")
    print(f"    InputPatternDetector: {pat_dets}")
    print(f"    RapidClickDetector:   {rapid_dets}")

    if total_dets == 0:
        passed("Zero detections", f"{len(log)} actions over {sim_time:.0f}s")
        test_results["passed"] += 1
    else:
        failed("Detections triggered", f"{total_dets} total")
        test_results["failed"] += 1
        if verbose:
            for d in results["bot_det"].detections[:3]:
                print(f"      Bot: {d}")
            for d in results["pattern_det"].detections[:3]:
                print(f"      Pattern: {d}")
            for d in results["rapid_det"].detections[:3]:
                print(f"      Rapid: {d}")

    # Timing statistics
    if results["ability_delays"]:
        delays = results["ability_delays"]
        below_100 = sum(1 for d in delays if d < 100)
        print(f"\n  Ability delays: min={min(delays):.0f}ms mean={statistics.mean(delays):.0f}ms max={max(delays):.0f}ms")
        if below_100 == 0:
            passed("All ability delays above 100ms", f"n={len(delays)}")
            test_results["passed"] += 1
        else:
            failed("Ability delays below 100ms", f"{below_100}/{len(delays)}")
            test_results["failed"] += 1

    if results["target_delays"]:
        delays = results["target_delays"]
        below_100 = sum(1 for d in delays if d < 100)
        print(f"  Target delays:  min={min(delays):.0f}ms mean={statistics.mean(delays):.0f}ms max={max(delays):.0f}ms")
        if below_100 == 0:
            passed("All target delays above 100ms", f"n={len(delays)}")
            test_results["passed"] += 1
        else:
            failed("Target delays below 100ms", f"{below_100}/{len(delays)}")
            test_results["failed"] += 1

    if results["key_holds"]:
        holds = results["key_holds"]
        print(f"  Key hold durations: min={min(holds):.0f}ms mean={statistics.mean(holds):.0f}ms max={max(holds):.0f}ms")
        if len(holds) >= 10:
            hold_std = statistics.stdev(holds)
            if hold_std >= 10:
                passed("Hold duration variance sufficient", f"stddev={hold_std:.1f}ms")
                test_results["passed"] += 1
            else:
                warn("Hold duration variance low", f"stddev={hold_std:.1f}ms")
                test_results["warned"] += 1

    # Check interval variance per action
    for action_name, intervals in results["action_intervals"].items():
        if len(intervals) >= 10:
            std = statistics.stdev(intervals)
            if std < 10:
                failed(f"Interval stddev too low for {action_name}", f"stddev={std:.1f}ms")
                test_results["failed"] += 1
            elif verbose:
                print(f"  {action_name} interval stddev: {std:.1f}ms")

    return test_results


def run_all(macro_dir="macros", max_cycles=5, verbose=False, specific_file=None):
    """Run dry-run tests on all macro files."""

    totals = {"passed": 0, "failed": 0, "warned": 0}

    if specific_file:
        files = [specific_file]
    else:
        files = []
        if os.path.isdir(macro_dir):
            for f in sorted(os.listdir(macro_dir)):
                if f.endswith((".yaml", ".yml")):
                    files.append(os.path.join(macro_dir, f))

    if not files:
        print("No macro files found.")
        return 1

    header(f"DRY-RUN TEST SUITE — {len(files)} macro(s)")

    for filepath in files:
        results = test_macro_file(filepath, max_cycles=max_cycles, verbose=verbose)
        for k in totals:
            totals[k] += results[k]

    # Summary
    header("DRY-RUN SUMMARY")
    total = totals["passed"] + totals["failed"] + totals["warned"]
    print(f"  {Colors.GREEN}PASSED: {totals['passed']}{Colors.END}")
    if totals["warned"]:
        print(f"  {Colors.YELLOW}WARNED: {totals['warned']}{Colors.END}")
    if totals["failed"]:
        print(f"  {Colors.RED}FAILED: {totals['failed']}{Colors.END}")
    print(f"  TOTAL:  {total}")
    print(f"  Macros tested: {len(files)}")

    if totals["failed"] == 0:
        print(f"\n  {Colors.GREEN}{Colors.BOLD}ALL MACROS PASS — Full pipeline is detection-safe!{Colors.END}")
    else:
        print(f"\n  {Colors.RED}{Colors.BOLD}ISSUES FOUND — Review failed tests above.{Colors.END}")

    return totals["failed"]


if __name__ == "__main__":
    verbose = "-v" in sys.argv
    max_cycles = 5
    specific_file = None

    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--cycles" and i < len(sys.argv) - 1:
            max_cycles = int(sys.argv[i + 1])
        elif arg.endswith((".yaml", ".yml")):
            specific_file = arg
        elif arg not in ("-v",):
            pass

    failures = run_all(max_cycles=max_cycles, verbose=verbose, specific_file=specific_file)
    sys.exit(failures)
