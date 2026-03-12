"""
Monsters and Memories game data definitions.
Extracted from IL2CPP dump of GameAssembly.dll.

These constants and enums mirror the game's internal data structures
for use in macro logic and condition checking.
"""


# Entity stat types (from EntityStatType enum)
class Stat:
    HEALTH = 0
    MANA = 1
    ENDURANCE = 2
    LEVEL = 3
    EXPERIENCE = 4
    STR = 5
    STA = 6
    DEX = 7
    AGI = 8
    INT = 9
    WIS = 10
    CHA = 11
    AC = 12
    # Resistances
    ICE_RESIST = 13
    FIRE_RESIST = 14
    ELECTRIC_RESIST = 15
    MAGIC_RESIST = 16
    CORRUPT_RESIST = 17
    POISON_RESIST = 18
    DISEASE_RESIST = 19
    HOLY_RESIST = 20


# Status effect types (from StatusType enum)
class Status:
    NONE = 0
    STUNNED = 1
    FEARED = 2
    MESMERIZED = 3
    SILENCED = 4
    INVISIBLE = 5
    LEVITATING = 6
    SNEAKING = 7
    SHIELDING = 8


# Posture states
class Posture:
    STAND = 0
    SIT = 1
    CROUCH = 2
    KNEEL = 3


# Movement modes (from KinematicController)
class MovementMode:
    NORMAL = 0
    SWIMMING = 1
    FLYING = 2
    LEVITATING = 3
    CLIMBING = 4


# Hotbar button types (from HotButtonType enum)
class HotButtonType:
    ICON_UI_RELAY = 0
    MACRO = 1
    SKILL = 2
    PET_ABILITY = 3
    PET_CONTROL = 4
    HOST_ABILITY = 5
    INVENTORY = 6
    ABILITY = 7
    BAG_SLOT = 8


# Network update rates (from Client class)
NETWORK_INPUT_UPDATE_DELTA = 0.1          # when moving
NETWORK_INPUT_UPDATE_DELTA_STATIONARY = 0.25  # when stationary
JUMP_ENDURANCE_COST = 10

# Anti-bot detection thresholds (from BotBehaviorDetector)
class BotDetection:
    IMPOSSIBLE_TIMING_MS = 100
    REQUIRED_REPETITIONS = 5
    COOLDOWN_SECONDS = 300

    # InputPatternDetector
    PATTERN_MIN_ACTIONS = 10
    DURATION_TOLERANCE_MS = 10
    INTERVAL_TOLERANCE_MS = 10
    TRACKED_DURATION_THRESHOLD_MS = 30

    # InputController
    RAPID_CLICK_WINDOW = 0.3
    RAPID_CLICK_THRESHOLD = 3
    ABILITY_PRESS_WINDOW = 1.5


# Targeting constants (from TabTargetController)
class Targeting:
    MAX_RANGE = 50.0
    MAX_RANGE_SQR = 2500.0


# Chat limits
class Chat:
    MAX_MESSAGE_LENGTH = 4096


# Ability casting requirements (from AbilityRecord/AbilityModel)
class CastRequirement:
    """Possible casting position requirements."""
    NONE = 0
    BEHIND_TARGET = 1
    BESIDE_TARGET = 2
    FACING_TARGET = 3
    LINE_OF_SIGHT = 4
