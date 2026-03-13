"""
Detection Simulator Test Suite
==============================
Re-implements the game's anti-bot detection logic (BotBehaviorDetector,
InputPatternDetector, InputController rapid-click) and feeds our
humanizer's output through it to verify zero detections.

Usage:
    python test_detection.py            # Run all tests
    python test_detection.py -v         # Verbose output
    python test_detection.py -n 5000    # Custom sample count
"""

import math
import random
import statistics
import sys
import time
from collections import deque

# Add project root to path
sys.path.insert(0, ".")
from humanizer import Humanizer, SessionProfile, SessionFatigue, BehaviorVariation


# =============================================================================
# Game Detection Logic (re-implemented from IL2CPP dump)
# =============================================================================

class BotBehaviorDetector:
    """
    Re-implementation of the game's BotBehaviorDetector.

    From dump.cs lines 330851-330919:
      - IMPOSSIBLE_TIMING_THRESHOLD_MS = 100
      - REQUIRED_PATTERN_REPETITIONS = 5
      - DEBOUNCE_PERIOD_SECONDS = 300
      - Monitors: PerfectAbilityTiming, InstantTargetAcquisition
    """

    IMPOSSIBLE_TIMING_THRESHOLD_MS = 100
    REQUIRED_PATTERN_REPETITIONS = 5
    DEBOUNCE_PERIOD_SECONDS = 300

    class BotIndicator:
        PerfectAbilityTiming = 0
        InstantTargetAcquisition = 1

    def __init__(self):
        self.last_detection_times = {}
        self.behavior_histories = {}
        self.detections = []

    def record_reaction_time(self, behavior_type, reaction_time_ms, context=""):
        key = f"{behavior_type}_{context}"
        if key not in self.behavior_histories:
            self.behavior_histories[key] = {
                "behavior_type": behavior_type,
                "reaction_times": deque(maxlen=20),
                "timestamps": deque(maxlen=20),
                "context": context,
            }
        history = self.behavior_histories[key]
        history["reaction_times"].append(reaction_time_ms)
        history["timestamps"].append(time.time())
        self._check_suspicious(history)

    def record_ability_timing(self, timing_offset_ms, ability_name):
        self.record_reaction_time(
            self.BotIndicator.PerfectAbilityTiming,
            timing_offset_ms,
            ability_name,
        )

    def record_target_acquisition(self, reaction_time_ms, mob_type=""):
        self.record_reaction_time(
            self.BotIndicator.InstantTargetAcquisition,
            reaction_time_ms,
            mob_type,
        )

    def _check_suspicious(self, history):
        rts = list(history["reaction_times"])
        if len(rts) < self.REQUIRED_PATTERN_REPETITIONS:
            return False

        # Check last N reaction times — if average is below impossible threshold
        recent = rts[-self.REQUIRED_PATTERN_REPETITIONS:]
        avg = sum(recent) / len(recent)
        if avg < self.IMPOSSIBLE_TIMING_THRESHOLD_MS:
            # Debounce check
            bt = history["behavior_type"]
            last = self.last_detection_times.get(bt, 0)
            now = time.time()
            if now - last > self.DEBOUNCE_PERIOD_SECONDS:
                self.last_detection_times[bt] = now
                self.detections.append({
                    "type": bt,
                    "avg_ms": avg,
                    "samples": recent,
                    "context": history["context"],
                })
                return True
        return False

    def reset(self):
        self.last_detection_times.clear()
        self.behavior_histories.clear()
        self.detections.clear()


class InputPatternDetector:
    """
    Re-implementation of the game's InputPatternDetector.

    From dump.cs lines 331543-331601:
      - REQUIRED_REPETITIONS = 10
      - MAX_PRESS_DURATION_MS = 30  (tracked duration threshold)
      - IDENTICAL_DURATION_TOLERANCE_MS = 10
      - MIN_INTERVAL_FOR_IDENTICAL_MS = 200
      - MAX_INTERVAL_STDDEV_MS = 10
    """

    REQUIRED_REPETITIONS = 10
    MAX_PRESS_DURATION_MS = 30
    IDENTICAL_DURATION_TOLERANCE_MS = 10
    MIN_INTERVAL_FOR_IDENTICAL_MS = 200
    MAX_INTERVAL_STDDEV_MS = 10

    def __init__(self):
        self.action_histories = {}
        self.detections = []

    def record_action(self, action_id, press_duration_ms=-1, timestamp=None):
        now = timestamp if timestamp is not None else time.time()
        if action_id not in self.action_histories:
            self.action_histories[action_id] = {
                "action": action_id,
                "timestamps": deque(maxlen=20),
                "intervals": deque(maxlen=20),
                "press_durations": deque(maxlen=20),
                "last_timestamp": 0,
            }
        history = self.action_histories[action_id]

        if history["last_timestamp"] > 0:
            interval = (now - history["last_timestamp"]) * 1000  # to ms
            history["intervals"].append(interval)

        history["timestamps"].append(now)
        if press_duration_ms >= 0:
            history["press_durations"].append(press_duration_ms)
        history["last_timestamp"] = now

        self._check_suspicious(history)

    def _check_suspicious(self, history):
        intervals = list(history["intervals"])
        durations = list(history["press_durations"])

        if len(intervals) < self.REQUIRED_REPETITIONS:
            return False

        recent_intervals = intervals[-self.REQUIRED_REPETITIONS:]

        # Check 1: Interval standard deviation too low
        if len(recent_intervals) >= 2:
            std_dev = statistics.stdev(recent_intervals)
            if std_dev < self.MAX_INTERVAL_STDDEV_MS:
                self.detections.append({
                    "action": history["action"],
                    "reason": "interval_stddev_too_low",
                    "stddev_ms": std_dev,
                    "intervals": recent_intervals,
                })
                return True

        # Check 2: Press durations too identical
        if len(durations) >= self.REQUIRED_REPETITIONS:
            recent_durations = durations[-self.REQUIRED_REPETITIONS:]
            if len(recent_durations) >= 2:
                dur_std = statistics.stdev(recent_durations)
                if dur_std < self.IDENTICAL_DURATION_TOLERANCE_MS:
                    self.detections.append({
                        "action": history["action"],
                        "reason": "duration_too_identical",
                        "stddev_ms": dur_std,
                        "durations": recent_durations,
                    })
                    return True

        return False

    def reset(self):
        self.action_histories.clear()
        self.detections.clear()


class RapidClickDetector:
    """
    Re-implementation of InputController's rapid click detection.

    From dump.cs lines 331362-331363:
      - RAPID_CLICK_WINDOW = 0.3
      - RAPID_CLICK_THRESHOLD = 3
    """

    RAPID_CLICK_WINDOW = 0.3
    RAPID_CLICK_THRESHOLD = 3

    def __init__(self):
        self.click_times = deque(maxlen=50)
        self.detections = []

    def record_click(self, timestamp):
        self.click_times.append(timestamp)
        self._check()

    def _check(self):
        if len(self.click_times) < self.RAPID_CLICK_THRESHOLD:
            return
        times = list(self.click_times)
        latest = times[-1]
        recent = [t for t in times if latest - t <= self.RAPID_CLICK_WINDOW]
        if len(recent) >= self.RAPID_CLICK_THRESHOLD:
            self.detections.append({
                "reason": "rapid_clicking",
                "clicks_in_window": len(recent),
                "window_ms": self.RAPID_CLICK_WINDOW * 1000,
            })

    def reset(self):
        self.click_times.clear()
        self.detections.clear()


class AbilityTimingDetector:
    """
    Re-implementation of AbilityTimingTracker.

    From dump.cs lines 330661-330696:
      - RECENT_EXPIRY_WINDOW = 0.5
      - Tracks cooldown expiry and checks if ability is cast
        too perfectly on cooldown expiry (within 0.5s window)

    Combined with BotBehaviorDetector.RecordAbilityTiming,
    this flags when abilities are consistently used the instant
    their cooldown expires.
    """

    RECENT_EXPIRY_WINDOW = 0.5  # seconds

    def __init__(self):
        self.cooldowns = {}
        self.timing_offsets = []

    def set_cooldown(self, ability_id, duration_s):
        self.cooldowns[ability_id] = time.time() + duration_s

    def record_cast(self, ability_id):
        if ability_id in self.cooldowns:
            expiry = self.cooldowns[ability_id]
            now = time.time()
            offset_ms = (now - expiry) * 1000
            self.timing_offsets.append(offset_ms)

    def reset(self):
        self.cooldowns.clear()
        self.timing_offsets.clear()


# =============================================================================
# Test Suite
# =============================================================================

class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    END = "\033[0m"


def header(text):
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}{Colors.END}")


def passed(name, detail=""):
    detail_str = f" — {detail}" if detail else ""
    print(f"  {Colors.GREEN}PASS{Colors.END}  {name}{detail_str}")


def failed(name, detail=""):
    detail_str = f" — {detail}" if detail else ""
    print(f"  {Colors.RED}FAIL{Colors.END}  {name}{detail_str}")


def warn(name, detail=""):
    detail_str = f" — {detail}" if detail else ""
    print(f"  {Colors.YELLOW}WARN{Colors.END}  {name}{detail_str}")


def run_tests(num_samples=5000, verbose=False):
    results = {"passed": 0, "failed": 0, "warned": 0}

    # ==== TEST 1: Reaction times above impossible threshold ====
    header("TEST 1: Reaction times vs BotBehaviorDetector")
    print(f"  Generating {num_samples} reaction time samples...")
    print(f"  Game threshold: {BotBehaviorDetector.IMPOSSIBLE_TIMING_THRESHOLD_MS}ms")
    print(f"  Our floor: {Humanizer.MIN_REACTION_MS}ms")

    humanizer = Humanizer(intensity=0.5)
    bot_detector = BotBehaviorDetector()

    delays = []
    for i in range(num_samples):
        d = humanizer.delay(0.15)
        delays.append(d)
        ms = d * 1000
        bot_detector.record_ability_timing(ms, f"ability_{i % 8}")

    min_ms = min(delays) * 1000
    max_ms = max(delays) * 1000
    mean_ms = statistics.mean(delays) * 1000
    median_ms = statistics.median(delays) * 1000
    below_threshold = sum(1 for d in delays if d * 1000 < BotBehaviorDetector.IMPOSSIBLE_TIMING_THRESHOLD_MS)

    print(f"  Min: {min_ms:.1f}ms  Max: {max_ms:.1f}ms  Mean: {mean_ms:.1f}ms  Median: {median_ms:.1f}ms")

    if below_threshold == 0:
        passed("No samples below 100ms threshold", f"0/{num_samples}")
        results["passed"] += 1
    else:
        failed("Samples below 100ms threshold", f"{below_threshold}/{num_samples}")
        results["failed"] += 1

    if len(bot_detector.detections) == 0:
        passed("BotBehaviorDetector triggered 0 detections")
        results["passed"] += 1
    else:
        failed("BotBehaviorDetector triggered", f"{len(bot_detector.detections)} detections")
        results["failed"] += 1
        if verbose:
            for det in bot_detector.detections[:3]:
                print(f"    Detection: avg={det['avg_ms']:.1f}ms samples={det['samples']}")

    # ==== TEST 2: Target acquisition timing ====
    header("TEST 2: Target acquisition vs BotBehaviorDetector")
    print(f"  Generating {num_samples} target acquisition delays...")

    humanizer = Humanizer(intensity=0.5)
    bot_detector = BotBehaviorDetector()

    target_delays = []
    for i in range(num_samples):
        d = humanizer.target_delay(0.25)
        target_delays.append(d)
        ms = d * 1000
        bot_detector.record_target_acquisition(ms, f"mob_{i % 5}")

    min_ms = min(target_delays) * 1000
    mean_ms = statistics.mean(target_delays) * 1000
    below = sum(1 for d in target_delays if d * 1000 < 100)

    print(f"  Min: {min_ms:.1f}ms  Mean: {mean_ms:.1f}ms")

    if below == 0:
        passed("No target acquisitions below 100ms", f"0/{num_samples}")
        results["passed"] += 1
    else:
        failed("Target acquisitions below 100ms", f"{below}/{num_samples}")
        results["failed"] += 1

    if len(bot_detector.detections) == 0:
        passed("BotBehaviorDetector triggered 0 detections")
        results["passed"] += 1
    else:
        failed("BotBehaviorDetector triggered", f"{len(bot_detector.detections)} detections")
        results["failed"] += 1

    # ==== TEST 3: Interval variance vs InputPatternDetector ====
    header("TEST 3: Interval variance vs InputPatternDetector")
    print(f"  Simulating {num_samples} repeated actions...")
    print(f"  Game threshold: stddev < {InputPatternDetector.MAX_INTERVAL_STDDEV_MS}ms = flagged")
    print(f"  Our target: stddev > {Humanizer.MIN_INTERVAL_STD_MS}ms")

    humanizer = Humanizer(intensity=0.5)
    pattern_detector = InputPatternDetector()

    # Simulate a realistic macro — same ability pressed repeatedly
    action_delays = []
    sim_time = 0
    for i in range(num_samples):
        d = humanizer.action_delay("test_ability", 0.2)
        action_delays.append(d)
        sim_time += d
        # Record with simulated press duration
        hold = humanizer.key_hold_duration(0.05)
        pattern_detector.action_histories.clear()  # Don't accumulate across full run
        # Instead, test in batches of 15 (realistic window)

    # Re-test with proper batching — simulate how the game actually tracks
    pattern_detector.reset()
    humanizer = Humanizer(intensity=0.5)
    batch_detections = 0
    num_batches = num_samples // 15

    for batch in range(num_batches):
        pattern_detector.reset()
        cumulative = batch * 1000.0  # offset each batch
        for i in range(15):
            d = humanizer.action_delay("ability_3", 0.2)
            hold = humanizer.key_hold_duration(0.05)
            cumulative += d
            pattern_detector.record_action("ability_3", hold * 1000, timestamp=cumulative)

        if len(pattern_detector.detections) > 0:
            batch_detections += 1

    # Also test interval std dev directly
    humanizer = Humanizer(intensity=0.5)
    stddev_violations = 0
    for batch in range(200):
        intervals = []
        for i in range(12):
            d = humanizer.action_delay(f"batch_{batch}", 0.2)
            intervals.append(d * 1000)
        if len(intervals) >= 10:
            std = statistics.stdev(intervals[-10:])
            if std < InputPatternDetector.MAX_INTERVAL_STDDEV_MS:
                stddev_violations += 1

    if stddev_violations == 0:
        passed("Interval stddev always above 10ms", f"0/{200} batches violated")
        results["passed"] += 1
    else:
        failed("Interval stddev too low in some batches", f"{stddev_violations}/200")
        results["failed"] += 1

    # Direct stddev measurement
    humanizer = Humanizer(intensity=0.5)
    all_intervals = []
    for i in range(100):
        d = humanizer.action_delay("stddev_test", 0.2)
        all_intervals.append(d * 1000)

    windowed_stds = []
    for i in range(len(all_intervals) - 9):
        window = all_intervals[i:i+10]
        windowed_stds.append(statistics.stdev(window))

    min_std = min(windowed_stds) if windowed_stds else 0
    mean_std = statistics.mean(windowed_stds) if windowed_stds else 0
    below_thresh = sum(1 for s in windowed_stds if s < 10)

    print(f"  Sliding window stddev: min={min_std:.1f}ms  mean={mean_std:.1f}ms")
    if below_thresh == 0:
        passed("All sliding windows above 10ms stddev", f"0/{len(windowed_stds)} violated")
        results["passed"] += 1
    else:
        failed("Some windows below 10ms stddev", f"{below_thresh}/{len(windowed_stds)}")
        results["failed"] += 1

    # ==== TEST 4: Key hold duration variance ====
    header("TEST 4: Key hold duration variance vs InputPatternDetector")
    print(f"  Game threshold: duration stddev < {InputPatternDetector.IDENTICAL_DURATION_TOLERANCE_MS}ms = flagged")

    humanizer = Humanizer(intensity=0.5)
    hold_durations = [humanizer.key_hold_duration(0.05) * 1000 for _ in range(num_samples)]

    hold_std = statistics.stdev(hold_durations)
    hold_min = min(hold_durations)
    hold_max = max(hold_durations)
    hold_mean = statistics.mean(hold_durations)

    print(f"  Min: {hold_min:.1f}ms  Max: {hold_max:.1f}ms  Mean: {hold_mean:.1f}ms  StdDev: {hold_std:.1f}ms")

    # Check in sliding windows
    hold_violations = 0
    for i in range(len(hold_durations) - 9):
        window = hold_durations[i:i+10]
        if statistics.stdev(window) < InputPatternDetector.IDENTICAL_DURATION_TOLERANCE_MS:
            hold_violations += 1

    if hold_violations == 0:
        passed("Hold duration variance always above 10ms", f"0/{len(hold_durations)-9} windows")
        results["passed"] += 1
    else:
        pct = hold_violations / (len(hold_durations) - 9) * 100
        if pct < 1:
            warn("Rare hold duration clusters", f"{hold_violations} windows ({pct:.2f}%)")
            results["warned"] += 1
        else:
            failed("Hold duration too uniform", f"{hold_violations} windows ({pct:.1f}%)")
            results["failed"] += 1

    # ==== TEST 5: Rapid click prevention ====
    header("TEST 5: Rapid click prevention")
    print(f"  Game threshold: {RapidClickDetector.RAPID_CLICK_THRESHOLD} clicks in {RapidClickDetector.RAPID_CLICK_WINDOW*1000}ms")

    humanizer = Humanizer(intensity=0.5)
    rapid_detector = RapidClickDetector()
    sim_time = 0

    for i in range(num_samples):
        d = humanizer.action_delay("click", 0.05)  # Fast base delay
        sim_time += d
        rapid_detector.record_click(sim_time)

    if len(rapid_detector.detections) == 0:
        passed("No rapid clicking detected", f"0 detections over {num_samples} clicks")
        results["passed"] += 1
    else:
        failed("Rapid clicking detected", f"{len(rapid_detector.detections)} detections")
        results["failed"] += 1

    # ==== TEST 6: Ability press timing (AbilityTimingTracker) ====
    header("TEST 6: Ability timing vs AbilityTimingTracker")
    print(f"  Simulating abilities used right after cooldown expires...")
    print(f"  Game flags: avg reaction < 100ms across 5 samples")

    humanizer = Humanizer(intensity=0.5)
    bot_detector = BotBehaviorDetector()

    # Simulate: cooldown expires, player reacts and presses ability
    for i in range(500):
        reaction = humanizer.ability_delay(i % 8, 0.2)
        reaction_ms = reaction * 1000
        bot_detector.record_ability_timing(reaction_ms, f"slot_{i % 8}")

    if len(bot_detector.detections) == 0:
        passed("No perfect ability timing detected")
        results["passed"] += 1
    else:
        failed("Perfect ability timing flagged", f"{len(bot_detector.detections)} detections")
        results["failed"] += 1

    # ==== TEST 7: Session variation ====
    header("TEST 7: Session uniqueness")
    print(f"  Creating 20 session profiles...")

    profiles = [SessionProfile() for _ in range(20)]
    reaction_mults = [p.reaction_multiplier for p in profiles]
    hold_styles = [p.hold_style for p in profiles]
    combat_rhythms = [p.combat_rhythm for p in profiles]

    react_std = statistics.stdev(reaction_mults)
    hold_std = statistics.stdev(hold_styles)
    combat_std = statistics.stdev(combat_rhythms)

    print(f"  Reaction multiplier spread: {min(reaction_mults):.2f}-{max(reaction_mults):.2f} (std={react_std:.3f})")
    print(f"  Hold style spread: {min(hold_styles):.2f}-{max(hold_styles):.2f} (std={hold_std:.3f})")
    print(f"  Combat rhythm spread: {min(combat_rhythms):.2f}-{max(combat_rhythms):.2f} (std={combat_std:.3f})")

    # Check no two profiles are too similar
    duplicates = 0
    for i in range(len(profiles)):
        for j in range(i+1, len(profiles)):
            p1, p2 = profiles[i], profiles[j]
            diff = abs(p1.reaction_multiplier - p2.reaction_multiplier) + \
                   abs(p1.hold_style - p2.hold_style) + \
                   abs(p1.combat_rhythm - p2.combat_rhythm)
            if diff < 0.05:
                duplicates += 1

    if duplicates == 0:
        passed("All 20 sessions are unique")
        results["passed"] += 1
    else:
        warn("Some sessions are very similar", f"{duplicates} near-duplicates")
        results["warned"] += 1

    # ==== TEST 8: Fatigue progression ====
    header("TEST 8: Fatigue progression")
    fatigue = SessionFatigue()
    # Override start time to simulate time passage
    original_start = fatigue.start_time

    factors = []
    for minutes in [0, 15, 30, 45, 60, 90, 120]:
        fatigue.start_time = time.time() - (minutes * 60)
        fatigue._last_break_time = time.time()  # prevent second wind during test
        f = fatigue.factor
        factors.append((minutes, f))

    print(f"  Fatigue curve:")
    for minutes, f in factors:
        bar = "#" * int(f * 20)
        print(f"    {minutes:>3}min: {f:.3f} {bar}")

    monotonic = all(factors[i][1] <= factors[i+1][1] for i in range(len(factors)-1))
    reasonable_range = factors[0][1] >= 1.0 and factors[-1][1] <= 2.0

    if monotonic and reasonable_range:
        passed("Fatigue increases monotonically", f"{factors[0][1]:.2f} -> {factors[-1][1]:.2f}")
        results["passed"] += 1
    else:
        failed("Fatigue curve issue", f"monotonic={monotonic} range={factors[0][1]:.2f}-{factors[-1][1]:.2f}")
        results["failed"] += 1

    # ==== TEST 9: Distribution shape (log-normal) ====
    header("TEST 9: Reaction time distribution shape")
    humanizer = Humanizer(intensity=0.5)
    samples = [humanizer.delay(0.2) * 1000 for _ in range(num_samples)]

    mean_rt = statistics.mean(samples)
    median_rt = statistics.median(samples)
    std_rt = statistics.stdev(samples)
    skew = (mean_rt - median_rt) / std_rt if std_rt > 0 else 0

    # Log-normal should be right-skewed (mean > median)
    print(f"  Mean: {mean_rt:.1f}ms  Median: {median_rt:.1f}ms  StdDev: {std_rt:.1f}ms")
    print(f"  Skew indicator: {skew:.3f} (positive = right-skewed = human-like)")

    # Check percentiles
    sorted_samples = sorted(samples)
    p5 = sorted_samples[int(len(sorted_samples) * 0.05)]
    p25 = sorted_samples[int(len(sorted_samples) * 0.25)]
    p75 = sorted_samples[int(len(sorted_samples) * 0.75)]
    p95 = sorted_samples[int(len(sorted_samples) * 0.95)]
    p99 = sorted_samples[int(len(sorted_samples) * 0.99)]

    print(f"  P5={p5:.0f}ms  P25={p25:.0f}ms  P50={median_rt:.0f}ms  P75={p75:.0f}ms  P95={p95:.0f}ms  P99={p99:.0f}ms")

    if mean_rt > median_rt and skew > 0:
        passed("Distribution is right-skewed (human-like)")
        results["passed"] += 1
    else:
        failed("Distribution is not right-skewed")
        results["failed"] += 1

    # ==== TEST 10: Full macro simulation ====
    header("TEST 10: Full enchanter CC macro simulation")
    print(f"  Simulating 50 CC rotation cycles through all detectors...")

    humanizer = Humanizer(intensity=0.5)
    bot_det = BotBehaviorDetector()
    pattern_det = InputPatternDetector()
    rapid_det = RapidClickDetector()
    sim_time = 0

    for cycle in range(50):
        # Target nearest
        d = humanizer.target_delay(0.3)
        sim_time += d
        bot_det.record_target_acquisition(d * 1000, "add")

        # Mez (slot 3)
        d = humanizer.ability_delay(3, 0.3)
        sim_time += d
        hold = humanizer.key_hold_duration(0.05)
        pattern_det.record_action("ability_3", hold * 1000, timestamp=sim_time)
        bot_det.record_ability_timing(d * 1000, "mez")
        rapid_det.record_click(sim_time)

        # Cast time wait
        sim_time += 3.0

        # Tab to next target
        d = humanizer.action_delay("tab", 0.3)
        sim_time += d
        hold = humanizer.key_hold_duration(0.05)
        pattern_det.record_action("tab", hold * 1000, timestamp=sim_time)

        # Mez target 2
        d = humanizer.ability_delay(3, 0.3)
        sim_time += d
        hold = humanizer.key_hold_duration(0.05)
        pattern_det.record_action("ability_3", hold * 1000, timestamp=sim_time)
        bot_det.record_ability_timing(d * 1000, "mez")
        rapid_det.record_click(sim_time)

        sim_time += 3.0

        # Tab to next
        d = humanizer.action_delay("tab", 0.3)
        sim_time += d
        pattern_det.record_action("tab", hold * 1000, timestamp=sim_time)

        # Mez target 3
        d = humanizer.ability_delay(3, 0.3)
        sim_time += d
        hold = humanizer.key_hold_duration(0.05)
        pattern_det.record_action("ability_3", hold * 1000, timestamp=sim_time)
        bot_det.record_ability_timing(d * 1000, "mez")
        rapid_det.record_click(sim_time)

        sim_time += 3.0

        # DPS window — nuke
        d = humanizer.ability_delay(1, 0.3)
        sim_time += d
        pattern_det.record_action("ability_1", humanizer.key_hold_duration(0.05) * 1000, timestamp=sim_time)
        rapid_det.record_click(sim_time)

        sim_time += 2.5

        # Wait before next cycle
        sim_time += 5.0 + humanizer.delay(0.5)

    total_detections = len(bot_det.detections) + len(pattern_det.detections) + len(rapid_det.detections)
    sim_minutes = sim_time / 60

    print(f"  Simulated {sim_minutes:.1f} minutes of gameplay")
    print(f"  BotBehaviorDetector:  {len(bot_det.detections)} detections")
    print(f"  InputPatternDetector: {len(pattern_det.detections)} detections")
    print(f"  RapidClickDetector:   {len(rapid_det.detections)} detections")

    if total_detections == 0:
        passed("ZERO detections across all systems", f"{sim_minutes:.0f} min simulated")
        results["passed"] += 1
    else:
        failed("Detections triggered!", f"{total_detections} total")
        results["failed"] += 1
        if verbose:
            for d in bot_det.detections[:3]:
                print(f"    Bot: {d}")
            for d in pattern_det.detections[:3]:
                print(f"    Pattern: {d}")
            for d in rapid_det.detections[:3]:
                print(f"    Rapid: {d}")

    # ==== TEST 11: Intensity levels ====
    header("TEST 11: Safety across intensity levels")
    for intensity in [0.1, 0.3, 0.5, 0.7, 1.0]:
        h = Humanizer(intensity=intensity)
        bot = BotBehaviorDetector()
        pat = InputPatternDetector()
        t = 0

        for i in range(500):
            d = h.ability_delay(i % 8, 0.2)
            t += d
            bot.record_ability_timing(d * 1000, f"slot_{i%8}")
            hold = h.key_hold_duration(0.05)
            pat.record_action(f"ability_{i%8}", hold * 1000, timestamp=t)

        total = len(bot.detections) + len(pat.detections)
        if total == 0:
            passed(f"Intensity {intensity:.1f}", "0 detections")
            results["passed"] += 1
        else:
            failed(f"Intensity {intensity:.1f}", f"{total} detections")
            results["failed"] += 1

    # ==== SUMMARY ====
    header("RESULTS SUMMARY")
    total = results["passed"] + results["failed"] + results["warned"]
    print(f"  {Colors.GREEN}PASSED: {results['passed']}{Colors.END}")
    if results["warned"]:
        print(f"  {Colors.YELLOW}WARNED: {results['warned']}{Colors.END}")
    if results["failed"]:
        print(f"  {Colors.RED}FAILED: {results['failed']}{Colors.END}")
    print(f"  TOTAL:  {total}")

    if results["failed"] == 0:
        print(f"\n  {Colors.GREEN}{Colors.BOLD}ALL CLEAR — Humanizer passes all detection checks!{Colors.END}")
    else:
        print(f"\n  {Colors.RED}{Colors.BOLD}ISSUES FOUND — Review failed tests above.{Colors.END}")

    return results["failed"]


if __name__ == "__main__":
    verbose = "-v" in sys.argv
    num_samples = 5000
    for i, arg in enumerate(sys.argv):
        if arg == "-n" and i + 1 < len(sys.argv):
            num_samples = int(sys.argv[i + 1])

    failures = run_tests(num_samples=num_samples, verbose=verbose)
    sys.exit(failures)
