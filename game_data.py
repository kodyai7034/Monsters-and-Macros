"""
Monsters and Memories game data definitions.
Extracted from IL2CPP dump of GameAssembly.dll and Addressables catalog.

These constants and enums mirror the game's internal data structures
for use in macro logic and condition checking.
"""


# Entity stat types (from EntityStatType enum in dump.cs)
class Stat:
    # Vitals
    HEALTH = 0
    MAX_HEALTH = 1
    MANA = 2
    MAX_MANA = 3
    ENDURANCE = 4
    MAX_ENDURANCE = 5
    # 6-15 unused/unknown
    EXPERIENCE = 16
    LEVEL = 17
    AC = 18
    WEIGHT = 19
    MAX_WEIGHT = 20
    # Attributes
    STR = 21
    STA = 22
    DEX = 23
    AGI = 24
    INT = 25
    WIS = 26
    CHA = 27
    # Movement
    BASE_RUN_SPEED = 28
    BASE_WALK_SPEED = 29
    MOVEMENT_SPEED = 30
    # Haste
    MELEE_HASTE = 31
    RANGED_HASTE = 32
    SPELL_HASTE = 33
    # Resistances
    ICE_RESIST = 34
    FIRE_RESIST = 35
    ELECTRIC_RESIST = 36
    MAGIC_RESIST = 37
    CORRUPT_RESIST = 38
    POISON_RESIST = 39
    DISEASE_RESIST = 40
    HOLY_RESIST = 61
    # Misc
    ESSENCE = 41
    HEALTH_REGEN = 42
    MANA_REGEN = 43
    SPIN_VELOCITY = 44
    PHYSICAL_DAMAGE = 45
    SPELL_DAMAGE = 46
    CHANCE_TO_EAT = 47
    CHANCE_TO_DRINK = 48
    SIZE = 50
    BLOCK_CHANCE = 51
    PARRY_CHANCE = 52
    DODGE_CHANCE = 53
    # Instrument mods
    BRASS_MOD = 54
    PERCUSSION_MOD = 55
    SINGING_MOD = 56
    STRING_MOD = 57
    WIND_MOD = 58
    # Mount
    MOUNT_DISCIPLINE = 59
    MOUNT_SWIFTNESS = 60
    # Combat
    MELEE_DAMAGE = 62
    RANGED_DAMAGE = 63


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


# =========================================================================
# Data extracted from Addressables catalog (catalog.bin)
# =========================================================================

# Playable races (from character model prefabs)
RACES = [
    "Ashira",       # Unique race (M/F models)
    "Dwarf",        # M/F
    "Elf_Wood",     # Wood Elf, M/F (also called "Deep" variant: Elf_Deep)
    "Gnome",        # M/F
    "Goblin",       # M/F
    "Halfling",     # M/F
    "Human",        # M/F
    "Ogre",         # M/F
]

# Monsters/creatures (from Capsule prefabs = collision entities)
MONSTERS = [
    "AirElemental",
    "Bat",
    "Bear",
    "Beetle",
    "Crocodile",
    "DeepBeetle",
    "Dervish",
    "Dragon",
    "Drake",
    "EarthElemental",
    "EvilEye",
    "FireElemental",
    "Ghoul",
    "GhoulChef",
    "Giant",
    "GlowingGhoul",
    "Jackal",
    "Myconid",
    "Mycothane",
    "Ooze",
    "Orc",
    "Rat",
    "Ratman",
    "Scarab",
    "Shadowman",
    "Shark",
    "Skeleton",
    "SmallSnake",
    "Snake",
    "Spectre",
    "Treant",
    "Wasp",
    "WaterElemental",
    "Wererat",
    "WilloWisp",
    "Wolf",
]

# NPC types (from model prefabs and NPC sets)
NPC_TYPES = [
    "Banker",
    "Guard",
    "Merchant",
    "Trainer",
]

# Mounts
MOUNTS = ["Donkey", "Horse"]

# Zones (from scene subscenes and asset bundles)
ZONES = {
    "NightHarbor":          "Starting city — main hub",
    "NightHarborSewers":    "Dungeon beneath Night Harbor",
    "KeepersBight":         "Coastal zone (KB prefix)",
    "ShallowShoals":        "Coastal/underwater zone (SS prefix)",
    "Broodwood":            "Forest zone",
    "EverGrove":            "Forest/grove zone",
    "Scarwood":             "Dark forest zone",
    "FaeCave":              "Cave dungeon",
    "Faelindral":           "Elven area (has Wwise music entry)",
    "KingPyrotrsFortress":  "Fortress dungeon (KPF prefix)",
    "AilVorith":            "Zone area",
    "Calafrey":             "Large zone (636MB bundle)",
    "Szuur":                "Largest zone (1.7GB bundle)",
    "Sea":                  "Ocean/sea zone (255MB bundle)",
}

# Weapon types (from equipment prefabs)
WEAPON_TYPES = {
    # One-handed
    "1H_Axe": "One-hand axe",
    "1H_Dagger": "Dagger",
    "1H_Mace": "One-hand mace",
    "1H_Scepter": "Scepter (caster)",
    "1H_Scimitar": "Scimitar",
    "1H_Scythe": "One-hand scythe",
    "1H_Spear": "One-hand spear",
    "1H_Staff": "One-hand staff",
    "1H_Sword": "One-hand sword",
    # Two-handed
    "2H_Axe": "Two-hand axe",
    "2H_Mace": "Two-hand mace",
    "2H_Scythe": "Two-hand scythe",
    "2H_Spear": "Two-hand spear",
    "2H_Staff": "Two-hand staff",
    "2H_Sword": "Two-hand sword",
    # Ranged
    "BowL": "Longbow",
    "BowS": "Shortbow",
    # Other
    "Fist": "Fist weapon",
    "Hammer": "Hammer",
    "Maul": "Maul (2H)",
    "Trident": "Trident",
    "Spellbook": "Spellbook (offhand)",
    "Lantern": "Lantern (offhand)",
    "Stein": "Stein",
    # Shields
    "ShieldK": "Kite shield",
    "ShieldR": "Round shield",
    "ShieldT": "Tower shield",
}

# Armor types (from equipment prefabs)
ARMOR_TYPES = ["Cloth", "Leather", "Chain", "Plate"]

# Class-specific armor sets (from prefab names)
CLASS_ARMOR_SETS = {
    "ENC": "Enchanter cloth",
    "FTR": "Fighter plate",
    "INQ": "Inquisitor plate",
    "SHD": "Shadow Knight plate",
}

# Named armor sets (from prefab names)
NAMED_ARMOR_SETS = [
    "BeetleLeather",      # Beetle leather armor
    "CraftedPlate",       # Player-crafted plate
    "NightHarborChain",   # Night Harbor chain
    "NightHarborCloth",   # Night Harbor cloth
    "NightHarborGuard",   # Guard armor
    "NightHarborLeather", # Night Harbor leather
    "NightHarborPlate",   # Night Harbor plate
    "WeatheredChain",     # Weathered chain
    "WeatheredCloth",     # Weathered cloth
    "WeatheredLeather",   # Weathered leather
    "WoodElfChain",       # Wood Elf chain
    "WoodElfCloth",       # Wood Elf cloth
    "WoodElfLeather",     # Wood Elf leather
    "WyrmsbonePlate",     # Wyrmsbone plate (dragon?)
    "ZintarCloth",        # Zintar cloth
    "MyconidArmor",       # Myconid armor
]

# Gathering/harvest node types (from HarvestNode prefabs)
HARVEST_NODES = {
    # Ores
    "Adamantium": "Rare ore",
    "Coal": "Common ore",
    "Cobalt": "Mid-tier ore",
    "Copper": "Starter ore",
    "Gold": "Rare ore",
    "Iron": "Common ore",
    "Limestone": "Stone",
    "Mithril": "High-tier ore",
    "Platinum": "Rare ore",
    "Silver": "Mid-tier ore",
    "Tin": "Starter ore",
    # Herbs
    "Dewdrop": "Herb",
    "DragonsVigil": "Herb",
    "Duneleaf": "Herb",
    "Ethtongue": "Herb",
    "Flamestalk": "Herb",
    "Gadolvine": "Herb",
    "GhostPoppy": "Herb",
    "Ironroot": "Herb",
    "LastBreath": "Herb",
    "LionLeaf": "Herb",
    "Magebloom": "Herb",
    "Moonveil": "Herb",
    "NomadsGrace": "Herb",
    "PhoenixFlower": "Herb",
    "Shadeshroom": "Herb",
    "Stranglevine": "Herb",
    "StygianMoss": "Herb",
    "Sylvine": "Herb",
    "WhisperingSage": "Herb",
    "Witherweed": "Herb",
}

# Chat channels (from chats.json)
CHAT_CHANNELS = {
    # Social
    "Say": "Local area chat",
    "Tell": "Private message",
    "TellSent": "Sent private message",
    "Party": "Party chat",
    "Shout": "Zone-wide shout",
    "OOC": "Out of character",
    "Auction": "Auction channel",
    "Guild": "Guild chat",
    "GuildOfficer": "Guild officer chat",
    "Emote": "Emote/roleplay",
    "Pet": "Pet messages",
    "Roll": "Dice rolls",
    "GM": "Game master",
    "Who": "Who listing",
    "Hardcore": "Hardcore mode",
    "Mud": "MUD-style output",
    # Combat
    "CombatHitMine": "My melee hits",
    "CombatHitVictim": "Hits on me",
    "CombatMissMine": "My misses",
    "CombatMissVictim": "Misses on me",
    "AbilityHitBenefitMine": "My beneficial ability hits",
    "AbilityHitDetrimentMine": "My harmful ability hits",
    "AbilityResistMine": "My resisted abilities",
    "BuffApplyBenefitMine": "Buff applied to me",
    "BuffFadeBenefitMine": "Buff faded from me",
    "BuffTickDetrimentMine": "DoT tick on me",
    "DeathMe": "My death",
    "DeathOther": "Other deaths",
    # System
    "Experience": "XP gains",
    "Loot": "Loot messages",
    "Coin": "Currency",
    "Status": "Status messages",
    "Faction": "Faction standing",
    "Skill": "Skill ups",
    "Action": "Action feedback",
}
