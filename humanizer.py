"""
Human-like input randomization for Monsters and Memories.

The game has built-in anti-bot detection (from IL2CPP dump analysis):

  BotBehaviorDetector:
    - IMPOSSIBLE_TIMING_THRESHOLD_MS = 100ms (anything faster = flagged)
    - REQUIRED_PATTERN_REPETITIONS = 5 (detections before alert)
    - 300s cooldown between detection alerts
    - Monitors: PerfectAbilityTiming, InstantTargetAcquisition

  InputPatternDetector:
    - Flags 10+ identical actions with machine-like precision
    - Press duration tolerance: 10ms (identical durations = suspicious)
    - Interval std deviation < 10ms = bot-like
    - Key presses > 30ms flagged as tracked duration actions

  InputController:
    - RAPID_CLICK_WINDOW = 0.3s
    - RAPID_CLICK_THRESHOLD = 3 clicks within window

Defense layers:
  1. Log-normal reaction time distribution (matches real human RT curves)
  2. Per-session fingerprinting (randomized base parameters each launch)
  3. Session fatigue (gradual slowdown over time)
  4. Behavioral variation (random "human" micro-actions)
  5. Interval variance enforcement (breaks repetitive patterns)
  6. Adaptive pattern breaking (injects noise before detector thresholds)
"""

import random
import math
import time
from collections import deque


class SessionProfile:
    """
    Per-session randomized fingerprint.
    Each time the tool launches, it generates a unique behavioral profile
    so no two sessions look the same to the detector.
    """

    def __init__(self):
        # Base reaction speed personality (some "players" are faster/slower)
        self.reaction_multiplier = random.uniform(0.85, 1.3)

        # Key hold style — some people tap, some hold longer
        self.hold_style = random.uniform(0.7, 1.4)

        # Mouse precision — some people are precise, some sloppy
        self.mouse_precision = random.uniform(0.6, 1.5)

        # Idle tendency — some people pause more
        self.idle_tendency = random.uniform(0.5, 2.0)

        # Preferred delay between combat actions
        self.combat_rhythm = random.uniform(0.8, 1.2)

        # Movement style — smooth vs jerky
        self.movement_smoothness = random.uniform(0.7, 1.3)

        # How often this "player" makes small mistakes (misclicks, hesitations)
        self.mistake_rate = random.uniform(0.01, 0.05)

        # Typing speed personality
        self.typing_speed = random.uniform(0.7, 1.5)

    def __repr__(self):
        return (
            f"SessionProfile(reaction={self.reaction_multiplier:.2f}, "
            f"hold={self.hold_style:.2f}, mouse={self.mouse_precision:.2f}, "
            f"idle={self.idle_tendency:.2f}, combat={self.combat_rhythm:.2f}, "
            f"mistakes={self.mistake_rate:.3f})"
        )


class SessionFatigue:
    """
    Simulates player fatigue over a session.
    Real players get slower and sloppier over time.
    """

    def __init__(self):
        self.start_time = time.time()
        # After this many seconds, fatigue is at full effect
        self.full_fatigue_time = random.uniform(3600, 7200)  # 1-2 hours
        self._last_break_time = self.start_time
        # Occasional "second wind" resets
        self._break_interval = random.uniform(900, 1800)  # 15-30 min

    @property
    def factor(self):
        """
        Returns fatigue multiplier (1.0 = fresh, up to ~1.4 = tired).
        Occasionally resets slightly to simulate "second wind".
        """
        now = time.time()
        elapsed = now - self.start_time

        # Check for periodic "second wind" (partial reset)
        if now - self._last_break_time > self._break_interval:
            self._last_break_time = now
            self.start_time = time.time() - elapsed * random.uniform(0.3, 0.6)
            self._break_interval = random.uniform(900, 1800)
            elapsed = now - self.start_time

        # Logarithmic fatigue curve — fast initial fatigue, then plateau
        ratio = min(elapsed / self.full_fatigue_time, 1.0)
        return 1.0 + 0.4 * math.log1p(ratio * 2.7)

    @property
    def sloppiness(self):
        """How sloppy inputs get as fatigue increases (0.0 = precise, 1.0 = sloppy)."""
        return min(0.8, (self.factor - 1.0) * 2.5)


class BehaviorVariation:
    """
    Injects random "human" micro-behaviors to break automation patterns.
    Real players do random things: check inventory, look around,
    adjust camera, jump randomly, etc.
    """

    # Possible micro-behaviors with relative weights
    BEHAVIORS = [
        ("camera_wiggle", 30),     # slight camera adjustment
        ("hesitation", 25),        # pause before acting
        ("look_around", 10),       # turn camera left/right
        ("inventory_check", 5),    # open/close inventory briefly
        ("jump", 8),               # random jump
        ("mouse_drift", 15),       # small unconscious mouse movement
        ("double_press", 5),       # accidentally press a key twice
        ("nothing", 2),            # just stand still briefly
    ]

    def __init__(self, profile: SessionProfile):
        self.profile = profile
        self._weights = [w for _, w in self.BEHAVIORS]
        self._names = [n for n, _ in self.BEHAVIORS]
        self._last_behavior_time = 0
        self._min_interval = random.uniform(15, 45)  # seconds between behaviors

    def should_inject(self):
        """Check if we should inject a random behavior now."""
        now = time.time()
        if now - self._last_behavior_time < self._min_interval:
            return False
        chance = 0.03 * self.profile.idle_tendency
        return random.random() < chance

    def pick_behavior(self):
        """Pick a random micro-behavior to perform."""
        self._last_behavior_time = time.time()
        self._min_interval = random.uniform(10, 40)
        return random.choices(self._names, weights=self._weights, k=1)[0]

    def get_behavior_params(self, behavior):
        """Get parameters for executing a behavior."""
        if behavior == "camera_wiggle":
            return {"dx": random.gauss(0, 15), "duration": random.uniform(0.1, 0.3)}
        elif behavior == "hesitation":
            return {"duration": random.uniform(0.3, 1.5)}
        elif behavior == "look_around":
            return {"dx": random.uniform(-120, 120), "duration": random.uniform(0.3, 0.8)}
        elif behavior == "inventory_check":
            return {"duration": random.uniform(0.5, 2.0)}
        elif behavior == "jump":
            return {}
        elif behavior == "mouse_drift":
            return {"dx": random.gauss(0, 8), "dy": random.gauss(0, 5)}
        elif behavior == "double_press":
            return {"delay": random.uniform(0.03, 0.08)}
        elif behavior == "nothing":
            return {"duration": random.uniform(0.5, 2.0)}
        return {}


class Humanizer:
    """Adds human-like randomization to input timing and movement."""

    # --- Game anti-bot thresholds (extracted from IL2CPP dump) ---
    # BotBehaviorDetector
    IMPOSSIBLE_TIMING_MS = 100
    REQUIRED_DETECTIONS = 5
    DETECTION_COOLDOWN_S = 300

    # InputPatternDetector
    PATTERN_MIN_ACTIONS = 10
    PATTERN_DURATION_TOLERANCE_MS = 10
    PATTERN_INTERVAL_TOLERANCE_MS = 10

    # InputController
    RAPID_CLICK_WINDOW = 0.3
    RAPID_CLICK_THRESHOLD = 3
    ABILITY_PRESS_WINDOW = 1.5
    MAX_TRACKED_PRESSES = 20

    # Safe minimums (stay well above detection thresholds)
    MIN_REACTION_MS = 150
    MIN_INTERVAL_STD_MS = 30

    def __init__(self, intensity=0.5):
        """
        intensity: 0.0 = minimal randomization, 1.0 = maximum.
        Higher values are safer but slower.
        """
        self.intensity = max(0.0, min(1.0, intensity))
        self._last_action_times = {}
        self._action_counts = {}
        self._interval_history = {}

        # Per-session systems
        self.profile = SessionProfile()
        self.fatigue = SessionFatigue()
        self.behavior = BehaviorVariation(self.profile)

        # Log-normal reaction time parameters
        # Real human RTs follow a log-normal distribution
        # Mean ~250ms, with right skew (occasional slow reactions)
        self._rt_mu = math.log(0.25)  # log of median RT in seconds
        self._rt_sigma = 0.35          # spread

    def _log_normal_rt(self, base_seconds):
        """
        Generate a reaction time using log-normal distribution.
        This matches real human reaction time curves much better
        than gaussian — right-skewed with occasional slow outliers.
        """
        # Scale the distribution around the requested base
        mu = math.log(max(base_seconds, 0.1))
        sigma = self._rt_sigma * self.intensity

        rt = random.lognormvariate(mu, sigma)

        # Apply session profile personality
        rt *= self.profile.reaction_multiplier

        # Apply fatigue (gets slower over time)
        rt *= self.fatigue.factor

        return max(self.MIN_REACTION_MS / 1000.0, rt)

    def delay(self, base_delay=0.1):
        """
        Returns a humanized delay using log-normal reaction time model.
        Always stays above the 100ms bot detection threshold.
        """
        safe_base = max(base_delay, self.MIN_REACTION_MS / 1000.0)
        delay = self._log_normal_rt(safe_base)

        # Occasional "thinking" pause — more likely when fatigued
        think_chance = 0.05 * self.intensity * self.fatigue.factor
        if random.random() < think_chance:
            delay += random.uniform(0.2, 1.2) * self.profile.idle_tendency

        # Rare "distraction" — player looked away briefly
        if random.random() < 0.008 * self.intensity:
            delay += random.uniform(1.0, 4.0)

        return max(self.MIN_REACTION_MS / 1000.0, delay)

    def key_hold_duration(self, base=0.05):
        """
        Humanized key hold duration.
        The game flags identical press durations within 10ms tolerance.
        Uses session profile for hold style personality.
        """
        styled_base = base * self.profile.hold_style
        min_hold = max(0.03, styled_base * 0.5)
        max_hold = styled_base * 2.0 + (0.1 * self.intensity)
        duration = random.uniform(min_hold, max_hold)

        # Fatigue makes holds sloppier
        duration *= (1.0 + self.fatigue.sloppiness * 0.3)

        # Occasional finger lag
        if random.random() < 0.1:
            duration += random.uniform(0.02, 0.08)

        # Rare "sticky key" — held too long
        if random.random() < self.profile.mistake_rate:
            duration += random.uniform(0.05, 0.15)

        return duration

    def movement_duration(self, base=1.0):
        """Humanized movement hold duration."""
        variance = base * 0.15 * self.intensity * self.profile.movement_smoothness
        duration = random.gauss(base, variance)
        duration *= self.fatigue.factor
        return max(0.1, duration)

    def mouse_offset(self, target_x, target_y, spread=5):
        """
        Add slight randomization to mouse click targets.
        Spread increases with fatigue (less precise when tired).
        """
        effective_spread = spread * self.intensity * self.profile.mouse_precision
        effective_spread *= (1.0 + self.fatigue.sloppiness)
        offset_x = random.gauss(0, effective_spread)
        offset_y = random.gauss(0, effective_spread)
        return (int(target_x + offset_x), int(target_y + offset_y))

    def mouse_path(self, start_x, start_y, end_x, end_y, steps=None):
        """
        Generate a curved mouse path with profile-based smoothness.
        Fatigued players have jerkier movements.
        """
        dist = math.sqrt((end_x - start_x)**2 + (end_y - start_y)**2)
        if steps is None:
            steps = max(5, int(dist / (20 * self.profile.movement_smoothness)))

        curve_intensity = self.intensity * self.profile.movement_smoothness
        ctrl_x = (start_x + end_x) / 2 + random.gauss(0, dist * 0.1 * curve_intensity)
        ctrl_y = (start_y + end_y) / 2 + random.gauss(0, dist * 0.1 * curve_intensity)

        # Jitter increases with fatigue
        jitter = 1.5 * self.intensity * (1.0 + self.fatigue.sloppiness)

        points = []
        for i in range(steps + 1):
            t = i / steps
            x = (1-t)**2 * start_x + 2*(1-t)*t * ctrl_x + t**2 * end_x
            y = (1-t)**2 * start_y + 2*(1-t)*t * ctrl_y + t**2 * end_y
            x += random.gauss(0, jitter)
            y += random.gauss(0, jitter)
            points.append((int(x), int(y)))

        return points

    def _ensure_interval_variance(self, action_name, delay):
        """
        Ensure that the interval between repeated actions has enough
        variance to avoid InputPatternDetector (flags std dev < 10ms).
        """
        if action_name not in self._interval_history:
            self._interval_history[action_name] = deque(maxlen=12)

        history = self._interval_history[action_name]

        if len(history) >= 3:
            intervals = list(history)
            mean = sum(intervals) / len(intervals)
            variance = sum((x - mean)**2 for x in intervals) / len(intervals)
            std_dev_ms = math.sqrt(variance) * 1000

            if std_dev_ms < self.MIN_INTERVAL_STD_MS:
                delay += random.uniform(0.05, 0.25) * self.intensity

        history.append(delay)
        return delay

    def action_delay(self, action_name, base_delay=0.1):
        """
        Smart delay with full defense stack:
        1. Log-normal reaction time
        2. Session profile personality
        3. Fatigue scaling
        4. Pattern-breaking injection
        5. Interval variance enforcement
        6. Rapid click prevention
        """
        now = time.time()
        last_time = self._last_action_times.get(action_name, 0)
        elapsed = now - last_time

        count = self._action_counts.get(action_name, 0)
        self._action_counts[action_name] = count + 1

        extra = 0

        # Pattern-breaking: inject pause before reaching 10-action threshold
        break_point = random.randint(3, 8)
        if count > 0 and count % break_point == 0:
            extra = random.uniform(0.1, 0.7) * self.intensity

        # Rapid click prevention
        if elapsed < self.RAPID_CLICK_WINDOW / self.RAPID_CLICK_THRESHOLD:
            extra += random.uniform(0.05, 0.2)

        # Fatigue adds extra slowness
        extra *= self.fatigue.factor

        delay = self.delay(base_delay) + extra
        delay = self._ensure_interval_variance(action_name, delay)

        self._last_action_times[action_name] = now + delay
        return delay

    def ability_delay(self, slot_index, base_delay=0.2):
        """
        Delay for ability usage. Must stay above 100ms threshold.
        Uses combat rhythm personality from session profile.
        """
        safe_base = max(base_delay, 0.2) * self.profile.combat_rhythm
        key = f"ability_{slot_index}"
        return self.action_delay(key, safe_base)

    def target_delay(self, base_delay=0.25):
        """
        Delay for targeting. BotBehaviorDetector flags InstantTargetAcquisition.
        """
        safe_base = max(base_delay, 0.25) * self.profile.reaction_multiplier
        return self.action_delay("target", safe_base)

    def should_idle(self, idle_chance=0.02):
        """Occasionally pause. More likely when fatigued."""
        effective_chance = idle_chance * self.intensity * self.profile.idle_tendency
        effective_chance *= self.fatigue.factor
        return random.random() < effective_chance

    def idle_duration(self):
        """Duration for idle pause — longer when fatigued."""
        base = random.uniform(0.5, 3.0)
        return base * self.fatigue.factor * self.profile.idle_tendency

    def should_inject_behavior(self):
        """Check if a random micro-behavior should be injected."""
        return self.behavior.should_inject()

    def get_random_behavior(self):
        """Get a random micro-behavior to perform."""
        behavior = self.behavior.pick_behavior()
        params = self.behavior.get_behavior_params(behavior)
        return behavior, params

    def typing_interval(self, base=0.08):
        """Humanized typing interval with session personality."""
        styled = base * self.profile.typing_speed
        return random.uniform(styled * 0.5, styled * 2.0) * self.fatigue.factor

    def scroll_amount(self, base=3):
        """Randomized scroll amount."""
        return base + random.randint(-1, 1)

    def combat_pause(self):
        """
        Natural pause during combat with session rhythm.
        """
        base = random.uniform(0.15, 0.4) * self.profile.combat_rhythm
        return base + random.uniform(0, 0.2) * self.intensity * self.fatigue.factor

    def post_combat_delay(self):
        """Delay after combat — longer when fatigued."""
        base = random.uniform(1.0, 4.0) * (0.5 + 0.5 * self.intensity)
        return base * self.fatigue.factor * self.profile.idle_tendency

    def get_session_info(self):
        """Return session profile info for logging/debugging."""
        return {
            "profile": str(self.profile),
            "fatigue_factor": round(self.fatigue.factor, 3),
            "fatigue_sloppiness": round(self.fatigue.sloppiness, 3),
            "session_age_minutes": round((time.time() - self.fatigue.start_time) / 60, 1),
        }
