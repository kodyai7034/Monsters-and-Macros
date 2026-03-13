"""
Macro Engine Unit Tests
=======================
Tests the engine's core logic without sending real input:
  - YAML parsing and macro loading
  - Keybind resolution
  - Condition evaluation
  - Repeat/loop behavior
  - Action dispatch (all action types)
  - Edge cases (missing fields, bad values, empty macros)

Usage:
    python3 test_engine.py         # Run all tests
    python3 test_engine.py -v      # Verbose output
"""

import sys
import os
import yaml
import tempfile

sys.path.insert(0, ".")
from test_dryrun import DryRunEngine, DryRunScreenReader
from test_detection import Colors, header, passed, failed, warn


def make_engine(**kwargs):
    """Create a DryRunEngine with optional overrides."""
    return DryRunEngine(max_cycles=kwargs.get("max_cycles", 100))


def make_macro(actions, name="Test Macro", loop_delay=0.3):
    """Build a macro dict from an action list."""
    return {
        "name": name,
        "description": "unit test macro",
        "loop_delay": loop_delay,
        "actions": actions,
    }


def run_tests(verbose=False):
    results = {"passed": 0, "failed": 0}

    def check(condition, name, detail=""):
        if condition:
            passed(name, detail)
            results["passed"] += 1
        else:
            failed(name, detail)
            results["failed"] += 1

    # ================================================================
    # TEST GROUP 1: YAML Parsing & Loading
    # ================================================================
    header("TEST GROUP 1: YAML Parsing & Loading")

    # 1.1 Load a valid macro file
    engine = make_engine()
    macro = engine.load_macro("macros/enchanter_cc.yaml")
    check(
        macro.get("name") == "Enchanter CC Rotation",
        "Load valid YAML macro",
        f"name={macro.get('name')}"
    )

    # 1.2 Macro has required fields
    check("actions" in macro, "Macro has 'actions' field")
    check("name" in macro, "Macro has 'name' field")
    check(isinstance(macro["actions"], list), "Actions is a list", f"type={type(macro['actions']).__name__}")

    # 1.3 Load all macro files without errors
    macro_dir = "macros"
    all_loaded = True
    load_count = 0
    for f in os.listdir(macro_dir):
        if f.endswith((".yaml", ".yml")):
            try:
                m = engine.load_macro(os.path.join(macro_dir, f))
                if "actions" not in m and "rules" not in m:
                    all_loaded = False
                load_count += 1
            except Exception as e:
                all_loaded = False
                if verbose:
                    print(f"    Failed to load {f}: {e}")
    check(all_loaded, "All macro files parse successfully", f"{load_count} files")

    # 1.4 Load macro from string (via tempfile)
    yaml_str = """
name: "Temp Macro"
description: "test"
actions:
  - action: log
    message: "hello"
  - action: wait
    duration: 1.0
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_str)
        tmp_path = f.name
    try:
        m = engine.load_macro(tmp_path)
        check(m["name"] == "Temp Macro", "Load macro from temp file")
        check(len(m["actions"]) == 2, "Temp macro has 2 actions")
    finally:
        os.unlink(tmp_path)

    # ================================================================
    # TEST GROUP 2: Keybind Resolution
    # ================================================================
    header("TEST GROUP 2: Keybind Resolution")

    engine = make_engine()

    # 2.1 Resolve known keybinds
    check(engine.get_key("ability_1") == "1", "ability_1 → '1'")
    check(engine.get_key("ability_8") == "8", "ability_8 → '8'")
    check(engine.get_key("target_nearest") == "tab", "target_nearest → 'tab'")
    check(engine.get_key("sit") == "x", "sit → 'x'")

    # 2.2 Unknown keybind returns raw key name
    check(engine.get_key("unknown_action") == "unknown_action", "Unknown keybind passthrough")
    check(engine.get_key("w") == "w", "Raw key passthrough")

    # ================================================================
    # TEST GROUP 3: Action Dispatch
    # ================================================================
    header("TEST GROUP 3: Action Dispatch")

    # 3.1 use_ability
    engine = make_engine()
    macro = make_macro([
        {"action": "use_ability", "slot": 3, "delay": 0.3},
    ])
    engine.run_macro(macro)
    abilities = [e for e in engine.input.action_log if e["action"] == "ability"]
    check(len(abilities) == 1, "use_ability creates 1 ability action")
    check(abilities[0]["slot"] == 3, "Correct slot recorded", f"slot={abilities[0]['slot']}")

    # 3.2 target_nearest
    engine = make_engine()
    macro = make_macro([
        {"action": "target_nearest", "delay": 0.3},
    ])
    engine.run_macro(macro)
    targets = [e for e in engine.input.action_log if e["action"] == "target"]
    check(len(targets) == 1, "target_nearest creates target action")

    # 3.3 wait
    engine = make_engine()
    macro = make_macro([
        {"action": "wait", "duration": 5.0},
    ])
    engine.run_macro(macro)
    check(engine.input.sim_time >= 5.0, "Wait advances sim time", f"sim_time={engine.input.sim_time:.1f}s")

    # 3.4 press
    engine = make_engine()
    macro = make_macro([
        {"action": "press", "key": "target_nearest", "delay": 0.3},
    ])
    engine.run_macro(macro)
    presses = [e for e in engine.input.action_log if e["action"] == "key_press"]
    check(len(presses) >= 1, "press creates key_press action")
    check(presses[0]["key"] == "tab", "press resolves keybind", f"key={presses[0]['key']}")

    # 3.5 sit
    engine = make_engine()
    macro = make_macro([
        {"action": "sit"},
    ])
    engine.run_macro(macro)
    sits = [e for e in engine.input.action_log if e["action"] == "key_press" and e.get("key") == "x"]
    check(len(sits) == 1, "sit presses 'x' key")

    # 3.6 move_forward
    engine = make_engine()
    macro = make_macro([
        {"action": "move_forward", "duration": 2.0},
    ])
    engine.run_macro(macro)
    holds = [e for e in engine.input.action_log if e["action"] == "key_hold"]
    check(len(holds) == 1, "move_forward creates key_hold")
    check(holds[0]["key"] == "w", "move_forward holds 'w'")

    # 3.7 log (should not crash, produces no input)
    engine = make_engine()
    macro = make_macro([
        {"action": "log", "message": "test message"},
    ])
    engine.run_macro(macro)
    check(len(engine.input.action_log) == 0 or
          all(e["action"] in ("idle", "random_behavior") for e in engine.input.action_log),
          "log produces no input actions")

    # 3.8 multiple abilities in sequence
    engine = make_engine()
    macro = make_macro([
        {"action": "use_ability", "slot": 1, "delay": 0.3},
        {"action": "wait", "duration": 2.0},
        {"action": "use_ability", "slot": 2, "delay": 0.3},
        {"action": "wait", "duration": 2.0},
        {"action": "use_ability", "slot": 3, "delay": 0.3},
    ])
    engine.run_macro(macro)
    abilities = [e for e in engine.input.action_log if e["action"] == "ability"]
    check(len(abilities) == 3, "3 abilities in sequence", f"got {len(abilities)}")
    slots = [a["slot"] for a in abilities]
    check(slots == [1, 2, 3], "Correct slot order", f"slots={slots}")

    # ================================================================
    # TEST GROUP 4: Condition Evaluation
    # ================================================================
    header("TEST GROUP 4: Condition Evaluation")

    # 4.1 health_below — true
    engine = make_engine()
    engine.screen.set_health(0.3)
    macro = make_macro([
        {"action": "condition", "check": "health_below", "value": 0.5,
         "then": [{"action": "use_ability", "slot": 5}]},
    ])
    engine.run_macro(macro)
    abilities = [e for e in engine.input.action_log if e["action"] == "ability"]
    check(len(abilities) == 1, "health_below triggers when health=0.3 < 0.5")

    # 4.2 health_below — false
    engine = make_engine()
    engine.screen.set_health(0.8)
    macro = make_macro([
        {"action": "condition", "check": "health_below", "value": 0.5,
         "then": [{"action": "use_ability", "slot": 5}]},
    ])
    engine.run_macro(macro)
    abilities = [e for e in engine.input.action_log if e["action"] == "ability"]
    check(len(abilities) == 0, "health_below skips when health=0.8 > 0.5")

    # 4.3 health_above — true
    engine = make_engine()
    engine.screen.set_health(0.9)
    macro = make_macro([
        {"action": "condition", "check": "health_above", "value": 0.7,
         "then": [{"action": "use_ability", "slot": 6}]},
    ])
    engine.run_macro(macro)
    abilities = [e for e in engine.input.action_log if e["action"] == "ability"]
    check(len(abilities) == 1, "health_above triggers when health=0.9 > 0.7")

    # 4.4 mana_below — true
    engine = make_engine()
    engine.screen.set_mana(0.1)
    macro = make_macro([
        {"action": "condition", "check": "mana_below", "value": 0.2,
         "then": [{"action": "sit"}]},
    ])
    engine.run_macro(macro)
    sits = [e for e in engine.input.action_log if e["action"] == "key_press" and e.get("key") == "x"]
    check(len(sits) == 1, "mana_below triggers when mana=0.1 < 0.2")

    # 4.5 mana_above — false
    engine = make_engine()
    engine.screen.set_mana(0.3)
    macro = make_macro([
        {"action": "condition", "check": "mana_above", "value": 0.5,
         "then": [{"action": "use_ability", "slot": 1}]},
    ])
    engine.run_macro(macro)
    abilities = [e for e in engine.input.action_log if e["action"] == "ability"]
    check(len(abilities) == 0, "mana_above skips when mana=0.3 < 0.5")

    # 4.6 else branch
    engine = make_engine()
    engine.screen.set_health(0.9)
    macro = make_macro([
        {"action": "condition", "check": "health_below", "value": 0.5,
         "then": [{"action": "use_ability", "slot": 5}],
         "else": [{"action": "use_ability", "slot": 1}]},
    ])
    engine.run_macro(macro)
    abilities = [e for e in engine.input.action_log if e["action"] == "ability"]
    check(len(abilities) == 1, "Else branch executes when condition is false")
    check(abilities[0]["slot"] == 1, "Else branch runs correct ability", f"slot={abilities[0]['slot']}")

    # 4.7 nested conditions
    engine = make_engine()
    engine.screen.set_health(0.3)
    engine.screen.set_mana(0.8)
    macro = make_macro([
        {"action": "condition", "check": "health_below", "value": 0.5,
         "then": [
             {"action": "condition", "check": "mana_above", "value": 0.5,
              "then": [{"action": "use_ability", "slot": 2}]},
         ]},
    ])
    engine.run_macro(macro)
    abilities = [e for e in engine.input.action_log if e["action"] == "ability"]
    check(len(abilities) == 1, "Nested condition — both true")
    check(abilities[0]["slot"] == 2, "Nested condition correct ability")

    # 4.8 nested condition — inner false
    engine = make_engine()
    engine.screen.set_health(0.3)
    engine.screen.set_mana(0.1)
    macro = make_macro([
        {"action": "condition", "check": "health_below", "value": 0.5,
         "then": [
             {"action": "condition", "check": "mana_above", "value": 0.5,
              "then": [{"action": "use_ability", "slot": 2}]},
         ]},
    ])
    engine.run_macro(macro)
    abilities = [e for e in engine.input.action_log if e["action"] == "ability"]
    check(len(abilities) == 0, "Nested condition — inner false, no action")

    # ================================================================
    # TEST GROUP 5: Repeat / Loop
    # ================================================================
    header("TEST GROUP 5: Repeat / Loop")

    # 5.1 Basic repeat
    engine = make_engine(max_cycles=10)
    macro = make_macro([
        {"action": "repeat", "times": 3, "actions": [
            {"action": "use_ability", "slot": 1},
        ]},
    ])
    engine.run_macro(macro)
    abilities = [e for e in engine.input.action_log if e["action"] == "ability"]
    check(len(abilities) == 3, "Repeat 3 times produces 3 abilities", f"got {len(abilities)}")

    # 5.2 Repeat respects max_cycles limit
    engine = make_engine(max_cycles=5)
    macro = make_macro([
        {"action": "repeat", "times": 100, "actions": [
            {"action": "use_ability", "slot": 1},
        ]},
    ])
    engine.run_macro(macro)
    abilities = [e for e in engine.input.action_log if e["action"] == "ability"]
    check(len(abilities) == 5, "Repeat capped at max_cycles=5", f"got {len(abilities)}")

    # 5.3 Nested repeat
    engine = make_engine(max_cycles=10)
    macro = make_macro([
        {"action": "repeat", "times": 3, "actions": [
            {"action": "repeat", "times": 2, "actions": [
                {"action": "use_ability", "slot": 1},
            ]},
        ]},
    ])
    engine.run_macro(macro)
    abilities = [e for e in engine.input.action_log if e["action"] == "ability"]
    check(len(abilities) == 6, "Nested repeat 3×2 = 6 abilities", f"got {len(abilities)}")

    # 5.4 Repeat with mixed actions
    engine = make_engine(max_cycles=10)
    macro = make_macro([
        {"action": "repeat", "times": 2, "actions": [
            {"action": "target_nearest", "delay": 0.3},
            {"action": "use_ability", "slot": 3, "delay": 0.3},
            {"action": "wait", "duration": 1.0},
        ]},
    ])
    engine.run_macro(macro)
    targets = [e for e in engine.input.action_log if e["action"] == "target"]
    abilities = [e for e in engine.input.action_log if e["action"] == "ability"]
    check(len(targets) == 2, "Repeat 2× with target produces 2 targets")
    check(len(abilities) == 2, "Repeat 2× with ability produces 2 abilities")

    # 5.5 Repeat times=0 does nothing
    engine = make_engine()
    macro = make_macro([
        {"action": "repeat", "times": 0, "actions": [
            {"action": "use_ability", "slot": 1},
        ]},
    ])
    engine.run_macro(macro)
    abilities = [e for e in engine.input.action_log if e["action"] == "ability"]
    check(len(abilities) == 0, "Repeat times=0 produces no actions")

    # ================================================================
    # TEST GROUP 6: Edge Cases
    # ================================================================
    header("TEST GROUP 6: Edge Cases")

    # 6.1 Empty actions list
    engine = make_engine()
    macro = make_macro([])
    try:
        engine.run_macro(macro)
        check(True, "Empty actions list doesn't crash")
    except Exception as e:
        check(False, "Empty actions list crashed", str(e))

    # 6.2 Unknown action type
    engine = make_engine()
    macro = make_macro([
        {"action": "nonexistent_action", "foo": "bar"},
    ])
    try:
        engine.run_macro(macro)
        check(True, "Unknown action type doesn't crash")
    except Exception as e:
        check(False, "Unknown action type crashed", str(e))

    # 6.3 Missing optional fields
    engine = make_engine()
    macro = make_macro([
        {"action": "use_ability"},  # no slot
        {"action": "wait"},         # no duration
        {"action": "press"},        # no key
    ])
    try:
        engine.run_macro(macro)
        check(True, "Missing optional fields don't crash")
    except Exception as e:
        check(False, "Missing optional fields crashed", str(e))

    # 6.4 Condition with missing then/else
    engine = make_engine()
    engine.screen.set_health(0.3)
    macro = make_macro([
        {"action": "condition", "check": "health_below", "value": 0.5},
        # no then or else
    ])
    try:
        engine.run_macro(macro)
        check(True, "Condition without then/else doesn't crash")
    except Exception as e:
        check(False, "Condition without then/else crashed", str(e))

    # 6.5 Repeat with missing actions
    engine = make_engine()
    macro = make_macro([
        {"action": "repeat", "times": 5},  # no actions
    ])
    try:
        engine.run_macro(macro)
        check(True, "Repeat without actions doesn't crash")
    except Exception as e:
        check(False, "Repeat without actions crashed", str(e))

    # 6.6 Very large wait doesn't block (sim time, not real time)
    engine = make_engine()
    macro = make_macro([
        {"action": "wait", "duration": 9999},
    ])
    engine.run_macro(macro)
    check(engine.input.sim_time >= 9999, "Large wait value handled", f"sim_time={engine.input.sim_time:.0f}s")

    # 6.7 Condition with unknown check type
    engine = make_engine()
    macro = make_macro([
        {"action": "condition", "check": "bogus_check", "value": 0.5,
         "then": [{"action": "use_ability", "slot": 1}]},
    ])
    try:
        engine.run_macro(macro)
        abilities = [e for e in engine.input.action_log if e["action"] == "ability"]
        check(len(abilities) == 0, "Unknown check type evaluates to false")
    except Exception as e:
        check(False, "Unknown check type crashed", str(e))

    # 6.8 Macro with only log actions
    engine = make_engine()
    macro = make_macro([
        {"action": "log", "message": "start"},
        {"action": "log", "message": "middle"},
        {"action": "log", "message": "end"},
    ])
    engine.run_macro(macro)
    input_actions = [e for e in engine.input.action_log
                     if e["action"] not in ("idle", "random_behavior")]
    check(len(input_actions) == 0, "Log-only macro produces no input")

    # ================================================================
    # TEST GROUP 7: Action Timing
    # ================================================================
    header("TEST GROUP 7: Action Timing")

    # 7.1 Actions advance sim time
    engine = make_engine()
    macro = make_macro([
        {"action": "use_ability", "slot": 1, "delay": 0.3},
        {"action": "wait", "duration": 2.0},
        {"action": "use_ability", "slot": 2, "delay": 0.3},
    ])
    engine.run_macro(macro)
    check(engine.input.sim_time > 2.0, "Actions advance sim time beyond wait", f"{engine.input.sim_time:.1f}s")

    # 7.2 Abilities have positive delay
    engine = make_engine()
    macro = make_macro([
        {"action": "use_ability", "slot": 1},
        {"action": "use_ability", "slot": 2},
        {"action": "use_ability", "slot": 3},
    ])
    engine.run_macro(macro)
    abilities = [e for e in engine.input.action_log if e["action"] == "ability"]
    all_positive = all(a["delay_ms"] > 0 for a in abilities)
    check(all_positive, "All ability delays are positive")

    # 7.3 Abilities have positive hold duration
    all_hold_positive = all(a["hold_ms"] > 0 for a in abilities)
    check(all_hold_positive, "All ability holds are positive")

    # 7.4 Target delays are positive
    engine = make_engine()
    macro = make_macro([
        {"action": "target_nearest"},
        {"action": "target_nearest"},
        {"action": "target_nearest"},
    ])
    engine.run_macro(macro)
    targets = [e for e in engine.input.action_log if e["action"] == "target"]
    all_target_positive = all(t["delay_ms"] > 0 for t in targets)
    check(all_target_positive, "All target delays are positive")

    # 7.5 Actions are in chronological order
    engine = make_engine()
    macro = make_macro([
        {"action": "use_ability", "slot": 1},
        {"action": "wait", "duration": 1.0},
        {"action": "use_ability", "slot": 2},
        {"action": "wait", "duration": 1.0},
        {"action": "use_ability", "slot": 3},
    ])
    engine.run_macro(macro)
    times = [e["time"] for e in engine.input.action_log]
    is_sorted = all(times[i] <= times[i+1] for i in range(len(times)-1))
    check(is_sorted, "Action timestamps are chronologically ordered")

    # ================================================================
    # TEST GROUP 8: Wait-for-resource
    # ================================================================
    header("TEST GROUP 8: Wait-for-resource")

    # 8.1 wait_for_mana
    engine = make_engine()
    engine.screen.set_mana(0.1)
    macro = make_macro([
        {"action": "wait_for_mana", "above": 0.5, "timeout": 30, "interval": 1.0},
    ])
    engine.run_macro(macro)
    check(engine.screen.mana >= 0.5, "wait_for_mana restores mana", f"mana={engine.screen.mana:.2f}")
    check(engine.input.sim_time > 0, "wait_for_mana advances time")

    # 8.2 wait_for_health
    engine = make_engine()
    engine.screen.set_health(0.2)
    macro = make_macro([
        {"action": "wait_for_health", "above": 0.8, "timeout": 30, "interval": 1.0},
    ])
    engine.run_macro(macro)
    check(engine.screen.health >= 0.8, "wait_for_health restores health", f"health={engine.screen.health:.2f}")

    # ================================================================
    # SUMMARY
    # ================================================================
    header("ENGINE TEST SUMMARY")
    total = results["passed"] + results["failed"]
    print(f"  {Colors.GREEN}PASSED: {results['passed']}{Colors.END}")
    if results["failed"]:
        print(f"  {Colors.RED}FAILED: {results['failed']}{Colors.END}")
    print(f"  TOTAL:  {total}")

    if results["failed"] == 0:
        print(f"\n  {Colors.GREEN}{Colors.BOLD}ALL ENGINE TESTS PASS!{Colors.END}")
    else:
        print(f"\n  {Colors.RED}{Colors.BOLD}ISSUES FOUND — Review failed tests above.{Colors.END}")

    return results["failed"]


if __name__ == "__main__":
    verbose = "-v" in sys.argv
    failures = run_tests(verbose=verbose)
    sys.exit(failures)
