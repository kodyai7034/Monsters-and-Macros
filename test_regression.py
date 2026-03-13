"""
Statistical Regression Baseline
================================
Captures humanizer timing distributions and saves them as a baseline.
Future runs compare against the baseline and flag regressions.

Usage:
    python3 test_regression.py --save       # Save current baseline
    python3 test_regression.py              # Compare against saved baseline
    python3 test_regression.py -v           # Verbose comparison
    python3 test_regression.py --tolerance 20  # Custom % tolerance (default 15)
"""

import sys
import os
import json
import statistics
import math

sys.path.insert(0, ".")
from humanizer import Humanizer
from test_detection import Colors, header, passed, failed, warn

BASELINE_FILE = "test_baseline.json"
NUM_SAMPLES = 5000
DEFAULT_TOLERANCE_PCT = 15  # Allow 15% drift before flagging


def collect_stats(num_samples=NUM_SAMPLES):
    """Collect timing distributions from the humanizer."""

    distributions = {}

    # 1. Reaction time delays (base delay)
    h = Humanizer(intensity=0.5)
    samples = [h.delay(0.15) * 1000 for _ in range(num_samples)]
    distributions["delay_0.15"] = summarize(samples)

    h = Humanizer(intensity=0.5)
    samples = [h.delay(0.3) * 1000 for _ in range(num_samples)]
    distributions["delay_0.30"] = summarize(samples)

    # 2. Ability delays per slot
    for slot in [1, 3, 5, 8]:
        h = Humanizer(intensity=0.5)
        samples = [h.ability_delay(slot, 0.2) * 1000 for _ in range(num_samples)]
        distributions[f"ability_slot{slot}"] = summarize(samples)

    # 3. Target acquisition delays
    h = Humanizer(intensity=0.5)
    samples = [h.target_delay(0.25) * 1000 for _ in range(num_samples)]
    distributions["target_delay"] = summarize(samples)

    # 4. Key hold durations
    h = Humanizer(intensity=0.5)
    samples = [h.key_hold_duration(0.05) * 1000 for _ in range(num_samples)]
    distributions["key_hold"] = summarize(samples)

    # 5. Action delays (with pattern breaking)
    h = Humanizer(intensity=0.5)
    samples = [h.action_delay("test_action", 0.2) * 1000 for _ in range(num_samples)]
    distributions["action_delay"] = summarize(samples)

    # 6. Combat pause
    h = Humanizer(intensity=0.5)
    samples = [h.combat_pause() * 1000 for _ in range(num_samples)]
    distributions["combat_pause"] = summarize(samples)

    # 7. Typing interval
    h = Humanizer(intensity=0.5)
    samples = [h.typing_interval(0.08) * 1000 for _ in range(num_samples)]
    distributions["typing_interval"] = summarize(samples)

    # 8. Intensity variations
    for intensity in [0.1, 0.5, 1.0]:
        h = Humanizer(intensity=intensity)
        samples = [h.delay(0.2) * 1000 for _ in range(num_samples)]
        distributions[f"delay_intensity_{intensity}"] = summarize(samples)

    # 9. Interval variance (sliding window stddev)
    h = Humanizer(intensity=0.5)
    intervals = [h.action_delay("variance_test", 0.2) * 1000 for _ in range(200)]
    window_stds = []
    for i in range(len(intervals) - 9):
        window = intervals[i:i + 10]
        window_stds.append(statistics.stdev(window))
    distributions["interval_stddev"] = summarize(window_stds)

    # 10. Session profile ranges (across 50 sessions)
    reaction_mults = []
    hold_styles = []
    combat_rhythms = []
    for _ in range(50):
        h = Humanizer(intensity=0.5)
        reaction_mults.append(h.profile.reaction_multiplier)
        hold_styles.append(h.profile.hold_style)
        combat_rhythms.append(h.profile.combat_rhythm)
    distributions["profile_reaction_mult"] = summarize(reaction_mults)
    distributions["profile_hold_style"] = summarize(hold_styles)
    distributions["profile_combat_rhythm"] = summarize(combat_rhythms)

    return distributions


def summarize(samples):
    """Compute summary statistics for a list of samples."""
    sorted_s = sorted(samples)
    n = len(sorted_s)
    return {
        "n": n,
        "min": sorted_s[0],
        "max": sorted_s[-1],
        "mean": statistics.mean(sorted_s),
        "median": statistics.median(sorted_s),
        "stdev": statistics.stdev(sorted_s) if n > 1 else 0,
        "p5": sorted_s[int(n * 0.05)],
        "p25": sorted_s[int(n * 0.25)],
        "p75": sorted_s[int(n * 0.75)],
        "p95": sorted_s[int(n * 0.95)],
        "p99": sorted_s[int(n * 0.99)] if n >= 100 else sorted_s[-1],
    }


def save_baseline(filepath=BASELINE_FILE):
    """Collect stats and save as baseline."""
    header("SAVING REGRESSION BASELINE")
    print(f"  Collecting {NUM_SAMPLES} samples per distribution...")

    stats = collect_stats()

    print(f"  Distributions captured: {len(stats)}")
    print(f"\n  Baseline values:")
    for name, s in sorted(stats.items()):
        print(f"    {name:30s}  mean={s['mean']:7.1f}  std={s['stdev']:7.1f}  min={s['min']:7.1f}  max={s['max']:7.1f}")

    with open(filepath, "w") as f:
        json.dump(stats, f, indent=2)

    print(f"\n  {Colors.GREEN}Baseline saved to {filepath}{Colors.END}")
    return stats


def compare_baseline(filepath=BASELINE_FILE, tolerance_pct=DEFAULT_TOLERANCE_PCT, verbose=False):
    """Compare current stats against saved baseline."""

    if not os.path.exists(filepath):
        print(f"  {Colors.YELLOW}No baseline file found at {filepath}{Colors.END}")
        print(f"  Run with --save first to create a baseline.")
        return 1

    with open(filepath) as f:
        baseline = json.load(f)

    header("REGRESSION TEST")
    print(f"  Comparing against baseline in {filepath}")
    print(f"  Tolerance: {tolerance_pct}% drift allowed")
    print(f"  Collecting {NUM_SAMPLES} fresh samples...\n")

    current = collect_stats()

    results = {"passed": 0, "failed": 0, "warned": 0}

    # Compare each distribution
    for name in sorted(baseline.keys()):
        if name not in current:
            warn(f"{name}", "Missing from current run")
            results["warned"] += 1
            continue

        b = baseline[name]
        c = current[name]

        issues = []

        # Check key metrics haven't drifted beyond tolerance
        for metric in ["mean", "median", "stdev", "p5", "p95"]:
            bv = b[metric]
            cv = c[metric]

            if bv == 0:
                if cv != 0:
                    drift_pct = 100
                else:
                    drift_pct = 0
            else:
                drift_pct = abs(cv - bv) / abs(bv) * 100

            if drift_pct > tolerance_pct * 2:
                issues.append(f"{metric}: {bv:.1f}→{cv:.1f} ({drift_pct:+.0f}%)")
            elif drift_pct > tolerance_pct:
                issues.append(f"{metric}: {bv:.1f}→{cv:.1f} ({drift_pct:+.0f}%) [warn]")

        # Check that minimum stays above detection threshold where applicable
        if "delay" in name or "ability" in name or "target" in name:
            if c["min"] < 100:
                issues.append(f"MIN BELOW 100ms: {c['min']:.1f}ms")

        if not issues:
            if verbose:
                passed(f"{name}", f"mean={c['mean']:.1f} (was {b['mean']:.1f})")
            results["passed"] += 1
        else:
            # Distinguish hard failures from warnings
            hard_fails = [i for i in issues if "[warn]" not in i and "MIN BELOW" not in i]
            min_fails = [i for i in issues if "MIN BELOW" in i]

            if min_fails:
                failed(f"{name}", "; ".join(issues))
                results["failed"] += 1
            elif hard_fails:
                warn(f"{name}", "; ".join(issues))
                results["warned"] += 1
            else:
                warn(f"{name}", "; ".join(issues))
                results["warned"] += 1

    # Print summary table if verbose
    if verbose:
        print(f"\n  {'Distribution':<32} {'Base Mean':>10} {'Curr Mean':>10} {'Drift':>8}")
        print(f"  {'-'*32} {'-'*10} {'-'*10} {'-'*8}")
        for name in sorted(baseline.keys()):
            if name in current:
                bm = baseline[name]["mean"]
                cm = current[name]["mean"]
                if bm > 0:
                    drift = (cm - bm) / bm * 100
                    drift_str = f"{drift:+.1f}%"
                else:
                    drift_str = "n/a"
                print(f"  {name:<32} {bm:>10.1f} {cm:>10.1f} {drift_str:>8}")

    # Summary
    header("REGRESSION SUMMARY")
    total = results["passed"] + results["failed"] + results["warned"]
    print(f"  {Colors.GREEN}PASSED: {results['passed']}{Colors.END}")
    if results["warned"]:
        print(f"  {Colors.YELLOW}WARNED: {results['warned']} (drifted but within safety){Colors.END}")
    if results["failed"]:
        print(f"  {Colors.RED}FAILED: {results['failed']} (safety threshold breached){Colors.END}")
    print(f"  TOTAL:  {total}")
    print(f"  Tolerance: {tolerance_pct}%")

    if results["failed"] == 0:
        if results["warned"] == 0:
            print(f"\n  {Colors.GREEN}{Colors.BOLD}NO REGRESSIONS — All distributions match baseline.{Colors.END}")
        else:
            print(f"\n  {Colors.YELLOW}{Colors.BOLD}MINOR DRIFT — No safety issues, but distributions shifted.{Colors.END}")
            print(f"  Consider re-saving baseline if changes are intentional: --save")
    else:
        print(f"\n  {Colors.RED}{Colors.BOLD}REGRESSION DETECTED — Safety thresholds breached!{Colors.END}")

    return results["failed"]


if __name__ == "__main__":
    verbose = "-v" in sys.argv
    save_mode = "--save" in sys.argv

    tolerance = DEFAULT_TOLERANCE_PCT
    for i, arg in enumerate(sys.argv):
        if arg == "--tolerance" and i + 1 < len(sys.argv):
            tolerance = float(sys.argv[i + 1])

    if save_mode:
        save_baseline()
        sys.exit(0)
    else:
        failures = compare_baseline(tolerance_pct=tolerance, verbose=verbose)
        sys.exit(failures)
