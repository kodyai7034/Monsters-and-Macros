"""
Stress Test Suite
=================
Tests edge cases and sustained use scenarios that could expose
detection vulnerabilities the basic tests miss.

Scenarios:
  1. Extended session (4+ hours of fatigue)
  2. Mez break spam (rapid emergency actions under pressure)
  3. Meditation loops (repetitive sit/stand/cast patterns)
  4. Back-to-back pulls (no downtime between fights)
  5. Mixed intensity sessions (alternating combat/idle)
  6. Worst-case timing (lowest intensity + fastest base delays)

Usage:
    python3 test_stress.py         # Run all stress tests
    python3 test_stress.py -v      # Verbose output
"""

import sys
import time
import math
import statistics
from collections import defaultdict

sys.path.insert(0, ".")
from humanizer import Humanizer, SessionProfile, SessionFatigue
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


class StressDetectors:
    """Bundle of all detection systems for a stress test."""

    def __init__(self):
        self.bot = BotBehaviorDetector()
        self.pattern = InputPatternDetector()
        self.rapid = RapidClickDetector()
        self.sim_time = 0.0

    @property
    def total_detections(self):
        return len(self.bot.detections) + len(self.pattern.detections) + len(self.rapid.detections)

    def record_ability(self, humanizer, slot, base_delay=0.3):
        d = humanizer.ability_delay(slot, base_delay)
        self.sim_time += d
        hold = humanizer.key_hold_duration(0.05)
        self.bot.record_ability_timing(d * 1000, f"slot_{slot}")
        self.pattern.record_action(f"ability_{slot}", hold * 1000, timestamp=self.sim_time)
        self.rapid.record_click(self.sim_time)
        self.sim_time += hold
        return d

    def record_target(self, humanizer):
        d = humanizer.target_delay(0.25)
        self.sim_time += d
        self.bot.record_target_acquisition(d * 1000)
        hold = humanizer.key_hold_duration(0.05)
        self.pattern.record_action("tab", hold * 1000, timestamp=self.sim_time)
        self.sim_time += hold
        return d

    def record_keypress(self, humanizer, key, base_delay=0.2):
        d = humanizer.action_delay(key, base_delay)
        self.sim_time += d
        hold = humanizer.key_hold_duration(0.05)
        self.pattern.record_action(f"key_{key}", hold * 1000, timestamp=self.sim_time)
        self.sim_time += hold
        return d

    def wait(self, seconds):
        self.sim_time += seconds

    def summary(self):
        return {
            "bot": len(self.bot.detections),
            "pattern": len(self.pattern.detections),
            "rapid": len(self.rapid.detections),
            "total": self.total_detections,
            "sim_minutes": self.sim_time / 60,
        }

    def print_detections(self, max_each=3):
        for d in self.bot.detections[:max_each]:
            print(f"      Bot: avg={d['avg_ms']:.1f}ms ctx={d['context']}")
        for d in self.pattern.detections[:max_each]:
            print(f"      Pattern: {d['action']} reason={d['reason']} stddev={d['stddev_ms']:.2f}ms")
        for d in self.rapid.detections[:max_each]:
            print(f"      Rapid: {d['clicks_in_window']} clicks in window")


def test_extended_session(verbose=False):
    """
    STRESS TEST 1: Extended 4-hour session
    Simulates continuous play for 4 hours with fatigue accumulating.
    Verifies humanizer still passes detection at extreme fatigue levels.
    """
    header("STRESS 1: Extended 4-hour session")

    humanizer = Humanizer(intensity=0.5)
    det = StressDetectors()

    # Simulate 4 hours in accelerated time
    # Each "hour" = 60 combat cycles of ~1 min each
    hours = 4
    cycles_per_hour = 60
    total_cycles = hours * cycles_per_hour

    # Manually advance fatigue by overriding start time
    phase_results = []

    for hour in range(hours):
        # Set fatigue to simulate this hour
        humanizer.fatigue.start_time = time.time() - (hour * 3600)
        humanizer.fatigue._last_break_time = time.time()

        hour_detections_before = det.total_detections
        fatigue_factor = humanizer.fatigue.factor

        for cycle in range(cycles_per_hour):
            # Standard combat rotation: target → ability × 3 → wait
            det.record_target(humanizer)
            det.record_ability(humanizer, 1, 0.3)
            det.wait(3.0)
            det.record_ability(humanizer, 2, 0.3)
            det.wait(2.5)
            det.record_ability(humanizer, 3, 0.3)
            det.wait(3.0)
            det.record_ability(humanizer, 1, 0.3)
            det.wait(5.0)

        hour_detections = det.total_detections - hour_detections_before
        phase_results.append((hour + 1, fatigue_factor, hour_detections))

    print(f"  Simulated {det.sim_time/60:.0f} minutes ({det.sim_time/3600:.1f} hours)")
    print(f"  Total actions: {total_cycles * 5}")
    print(f"\n  Fatigue by hour:")
    for hour, fatigue, dets in phase_results:
        status = f"{Colors.GREEN}0 detections{Colors.END}" if dets == 0 else f"{Colors.RED}{dets} detections{Colors.END}"
        print(f"    Hour {hour}: fatigue={fatigue:.3f}x — {status}")

    s = det.summary()
    if s["total"] == 0:
        passed("4-hour session clean", f"{total_cycles * 5} actions, 0 detections")
        return 0
    else:
        failed("Detections in extended session", f"{s['total']} total")
        if verbose:
            det.print_detections()
        return 1


def test_mez_break_spam(verbose=False):
    """
    STRESS TEST 2: Rapid mez break recovery
    Simulates the worst case: multiple mez breaks in quick succession
    requiring emergency stun → re-mez under time pressure.
    """
    header("STRESS 2: Mez break spam (emergency recovery)")

    humanizer = Humanizer(intensity=0.5)
    det = StressDetectors()

    num_breaks = 50

    print(f"  Simulating {num_breaks} mez break emergencies...")
    print(f"  Pattern: stun → re-mez → stun → re-mez (rapid sequence)")

    for i in range(num_breaks):
        # Mez breaks — emergency response
        # Stun the mob
        det.record_ability(humanizer, 4, 0.2)  # stun, fast reaction
        det.wait(1.5)  # stun duration

        # Re-mez while stunned
        det.record_ability(humanizer, 3, 0.3)  # mez
        det.wait(3.0)  # cast time

        # Sometimes double-break (two mobs wake up)
        if i % 5 == 0:
            det.record_target(humanizer)  # tab to second mob
            det.record_ability(humanizer, 4, 0.2)  # stun it
            det.wait(1.5)
            det.record_ability(humanizer, 3, 0.3)  # re-mez
            det.wait(3.0)

        # Brief recovery
        det.wait(2.0)

    s = det.summary()
    print(f"  Simulated {s['sim_minutes']:.1f} minutes of emergency CC")

    if s["total"] == 0:
        passed("Mez break spam clean", f"{num_breaks} emergencies, 0 detections")
        return 0
    else:
        failed("Detections during mez break spam", f"{s['total']} total")
        if verbose:
            det.print_detections()
        return 1


def test_meditation_loops(verbose=False):
    """
    STRESS TEST 3: Repetitive meditation cycles
    Sit → wait → stand → cast → sit → repeat. This is the most
    repetitive pattern a player can do and most likely to trigger
    the InputPatternDetector.
    """
    header("STRESS 3: Meditation loops (sit/stand/cast)")

    humanizer = Humanizer(intensity=0.5)
    det = StressDetectors()

    num_cycles = 100

    print(f"  Simulating {num_cycles} med cycles (sit → regen → stand → cast → sit)...")

    for i in range(num_cycles):
        # Sit to meditate
        det.record_keypress(humanizer, "sit", 0.2)
        det.wait(8.0)  # meditate for ~8 seconds

        # Stand up
        det.record_keypress(humanizer, "sit", 0.2)  # toggle sit
        det.wait(0.5)

        # Cast a spell (mez refresh)
        det.record_target(humanizer)
        det.record_ability(humanizer, 3, 0.3)
        det.wait(3.0)

        # Maybe cast a second spell
        if i % 3 == 0:
            det.record_ability(humanizer, 1, 0.3)
            det.wait(2.5)

        # Back to sitting
        det.wait(1.0)

    s = det.summary()
    print(f"  Simulated {s['sim_minutes']:.1f} minutes of meditation cycling")

    if s["total"] == 0:
        passed("Meditation loops clean", f"{num_cycles} cycles, 0 detections")
        return 0
    else:
        failed("Detections during meditation", f"{s['total']} total")
        if verbose:
            det.print_detections()
        return 1


def test_back_to_back_pulls(verbose=False):
    """
    STRESS TEST 4: Continuous pulls with no downtime
    Simulates an efficient group chain-pulling — target dies,
    immediately pull next. Tests whether the constant action
    stream triggers detection.
    """
    header("STRESS 4: Back-to-back pulls (chain pulling)")

    humanizer = Humanizer(intensity=0.5)
    det = StressDetectors()

    num_pulls = 80

    print(f"  Simulating {num_pulls} consecutive pulls with minimal downtime...")

    for i in range(num_pulls):
        # Pull: target → engage
        det.record_target(humanizer)

        # Combat rotation (varies slightly each pull)
        num_abilities = 3 + (i % 3)  # 3-5 abilities per pull
        for j in range(num_abilities):
            slot = (j % 5) + 1
            det.record_ability(humanizer, slot, 0.3)
            det.wait(2.0 + (j * 0.5))  # cast times vary

        # Mob dies — brief loot pause
        det.wait(1.0 + humanizer.delay(0.5))

        # Occasional heal between pulls
        if i % 4 == 0:
            det.record_ability(humanizer, 5, 0.3)  # heal
            det.wait(2.5)

    s = det.summary()
    print(f"  Simulated {s['sim_minutes']:.1f} minutes of chain pulling")

    if s["total"] == 0:
        passed("Chain pulling clean", f"{num_pulls} pulls, 0 detections")
        return 0
    else:
        failed("Detections during chain pulling", f"{s['total']} total")
        if verbose:
            det.print_detections()
        return 1


def test_mixed_intensity_session(verbose=False):
    """
    STRESS TEST 5: Mixed combat/idle session
    Alternates between intense combat and idle periods.
    Tests whether the transition patterns are suspicious.
    """
    header("STRESS 5: Mixed intensity (combat ↔ idle)")

    humanizer = Humanizer(intensity=0.5)
    det = StressDetectors()

    phases = 20  # 20 combat/idle phase pairs

    print(f"  Simulating {phases} combat/idle phase transitions...")

    for phase in range(phases):
        # COMBAT PHASE: intense action for 30-60 seconds
        combat_actions = 10 + (phase % 8)
        for j in range(combat_actions):
            slot = (j % 4) + 1
            det.record_ability(humanizer, slot, 0.2)
            det.wait(1.5)

        # TRANSITION: slow down
        det.wait(humanizer.delay(1.0))

        # IDLE PHASE: minimal actions for 15-30 seconds
        idle_time = 15 + (phase % 15)
        det.wait(idle_time)

        # Occasional idle action (check inventory, look around)
        if phase % 3 == 0:
            det.record_keypress(humanizer, "inventory", 0.3)
            det.wait(2.0)
            det.record_keypress(humanizer, "inventory", 0.3)

    s = det.summary()
    print(f"  Simulated {s['sim_minutes']:.1f} minutes of mixed activity")

    if s["total"] == 0:
        passed("Mixed intensity clean", f"{phases} phase transitions, 0 detections")
        return 0
    else:
        failed("Detections during mixed session", f"{s['total']} total")
        if verbose:
            det.print_detections()
        return 1


def test_worst_case_timing(verbose=False):
    """
    STRESS TEST 6: Worst-case parameters
    Lowest intensity (0.1) with fastest base delays.
    This is the scenario most likely to produce detectable patterns.
    """
    header("STRESS 6: Worst-case timing (intensity=0.1, fast delays)")

    humanizer = Humanizer(intensity=0.1)
    det = StressDetectors()

    num_actions = 1000

    print(f"  Intensity: 0.1 (minimum humanization)")
    print(f"  Base delay: 0.15s (fastest reasonable)")
    print(f"  Simulating {num_actions} rapid actions...")

    for i in range(num_actions):
        slot = (i % 8) + 1
        det.record_ability(humanizer, slot, 0.15)
        det.wait(1.0)  # GCD

    s = det.summary()
    print(f"  Simulated {s['sim_minutes']:.1f} minutes")

    # Also check timing statistics
    all_delays = []
    h2 = Humanizer(intensity=0.1)
    for i in range(1000):
        d = h2.ability_delay(i % 8, 0.15)
        all_delays.append(d * 1000)

    below_100 = sum(1 for d in all_delays if d < 100)
    min_d = min(all_delays)
    mean_d = statistics.mean(all_delays)

    print(f"  Delay stats: min={min_d:.0f}ms mean={mean_d:.0f}ms below_100ms={below_100}")

    results = 0
    if below_100 > 0:
        failed("Delays below 100ms at intensity=0.1", f"{below_100}/1000")
        results += 1
    else:
        passed("All delays above 100ms even at intensity=0.1")

    if s["total"] == 0:
        passed("Worst-case timing clean", f"{num_actions} actions, 0 detections")
    else:
        failed("Detections at worst-case timing", f"{s['total']} total")
        results += 1
        if verbose:
            det.print_detections()

    return results


def test_single_ability_spam(verbose=False):
    """
    STRESS TEST 7: Single ability spam
    Same ability pressed 500 times in a row — the most extreme
    repetition scenario for InputPatternDetector.
    """
    header("STRESS 7: Single ability spam (500× same key)")

    humanizer = Humanizer(intensity=0.5)
    det = StressDetectors()

    num_presses = 500

    print(f"  Pressing ability_3 (mez) {num_presses} times consecutively...")

    for i in range(num_presses):
        det.record_ability(humanizer, 3, 0.3)
        det.wait(3.0)  # cast time

    s = det.summary()
    print(f"  Simulated {s['sim_minutes']:.1f} minutes of mez spam")

    # Check interval variance over sliding windows
    h2 = Humanizer(intensity=0.5)
    intervals = []
    for i in range(200):
        d = h2.ability_delay(3, 0.3)
        intervals.append(d * 1000)

    low_variance_windows = 0
    for i in range(len(intervals) - 9):
        window = intervals[i:i+10]
        std = statistics.stdev(window)
        if std < 10:
            low_variance_windows += 1

    print(f"  Interval variance: {low_variance_windows}/{len(intervals)-9} windows below 10ms stddev")

    results = 0
    if low_variance_windows > 0:
        failed("Low variance windows found in single-ability spam", f"{low_variance_windows}")
        results += 1
    else:
        passed("Interval variance maintained across 200 presses")

    if s["total"] == 0:
        passed("Single ability spam clean", f"{num_presses} presses, 0 detections")
    else:
        failed("Detections during ability spam", f"{s['total']} total")
        results += 1
        if verbose:
            det.print_detections()

    return results


def test_multi_session_fingerprints(verbose=False):
    """
    STRESS TEST 8: Cross-session fingerprint uniqueness
    Creates 50 sessions and checks that their timing profiles
    are sufficiently different from each other.
    """
    header("STRESS 8: Multi-session fingerprint uniqueness (50 sessions)")

    num_sessions = 50
    num_samples = 100

    session_profiles = []

    for s in range(num_sessions):
        h = Humanizer(intensity=0.5)
        delays = [h.ability_delay(3, 0.3) * 1000 for _ in range(num_samples)]
        holds = [h.key_hold_duration(0.05) * 1000 for _ in range(num_samples)]
        profile = {
            "delay_mean": statistics.mean(delays),
            "delay_std": statistics.stdev(delays),
            "hold_mean": statistics.mean(holds),
            "hold_std": statistics.stdev(holds),
            "reaction_mult": h.profile.reaction_multiplier,
            "combat_rhythm": h.profile.combat_rhythm,
        }
        session_profiles.append(profile)

    # Check that sessions have meaningful differences
    delay_means = [p["delay_mean"] for p in session_profiles]
    hold_means = [p["hold_mean"] for p in session_profiles]

    delay_spread = max(delay_means) - min(delay_means)
    hold_spread = max(hold_means) - min(hold_means)

    print(f"  Delay mean range: {min(delay_means):.0f}ms - {max(delay_means):.0f}ms (spread={delay_spread:.0f}ms)")
    print(f"  Hold mean range: {min(hold_means):.0f}ms - {max(hold_means):.0f}ms (spread={hold_spread:.0f}ms)")

    # Check for near-duplicate sessions
    near_dupes = 0
    for i in range(num_sessions):
        for j in range(i + 1, num_sessions):
            p1, p2 = session_profiles[i], session_profiles[j]
            delay_diff = abs(p1["delay_mean"] - p2["delay_mean"])
            hold_diff = abs(p1["hold_mean"] - p2["hold_mean"])
            if delay_diff < 5 and hold_diff < 3:
                near_dupes += 1

    results = 0

    if delay_spread > 50:
        passed("Delay timing varies across sessions", f"spread={delay_spread:.0f}ms")
    else:
        failed("Sessions too similar in delay timing", f"spread={delay_spread:.0f}ms")
        results += 1

    if hold_spread > 20:
        passed("Hold duration varies across sessions", f"spread={hold_spread:.0f}ms")
    else:
        failed("Sessions too similar in hold duration", f"spread={hold_spread:.0f}ms")
        results += 1

    if near_dupes == 0:
        passed("No near-duplicate sessions", f"0/{num_sessions*(num_sessions-1)//2} pairs")
    else:
        pct = near_dupes / (num_sessions * (num_sessions - 1) // 2) * 100
        if pct < 2:
            warn("Rare near-duplicate sessions", f"{near_dupes} pairs ({pct:.1f}%)")
        else:
            failed("Too many near-duplicate sessions", f"{near_dupes} pairs ({pct:.1f}%)")
            results += 1

    return results


def run_stress_tests(verbose=False):
    """Run all stress tests."""

    header("STRESS TEST SUITE")
    print(f"  Testing edge cases and sustained use scenarios\n")

    tests = [
        ("Extended 4-hour session", test_extended_session),
        ("Mez break spam", test_mez_break_spam),
        ("Meditation loops", test_meditation_loops),
        ("Back-to-back pulls", test_back_to_back_pulls),
        ("Mixed intensity", test_mixed_intensity_session),
        ("Worst-case timing", test_worst_case_timing),
        ("Single ability spam", test_single_ability_spam),
        ("Multi-session fingerprints", test_multi_session_fingerprints),
    ]

    total_failures = 0
    test_failures = []
    for name, test_fn in tests:
        failures = test_fn(verbose=verbose)
        total_failures += failures
        test_failures.append((name, failures))

    # Summary
    header("STRESS TEST SUMMARY")
    total_tests = len(tests)
    failed_tests = sum(1 for _, f in test_failures if f > 0)

    for name, failures in test_failures:
        status = f"{Colors.GREEN}PASS{Colors.END}" if failures == 0 else f"{Colors.RED}FAIL{Colors.END}"
        print(f"  {status}  {name}")

    print()
    if total_failures == 0:
        print(f"  {Colors.GREEN}{Colors.BOLD}ALL {total_tests} STRESS TESTS PASSED{Colors.END}")
        print(f"  Humanizer is resilient under sustained and edge-case use.")
    else:
        print(f"  {Colors.RED}{Colors.BOLD}{failed_tests}/{total_tests} tests had failures{Colors.END}")
        print(f"  Review failed tests above.")

    return total_failures


if __name__ == "__main__":
    verbose = "-v" in sys.argv
    failures = run_stress_tests(verbose=verbose)
    sys.exit(min(failures, 127))
