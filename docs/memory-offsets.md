# Memory Offsets & Pointer Chains

All offsets from IL2CPP dump of GameAssembly.dll. **These WILL change on game patches.**

## RVA Constants

```
CLIENT_TYPEINFO_RVA          = 0x54405D8    → Client class TypeInfo
ZONE_CONTROLLER_TYPEINFO_RVA = 0x542B5B0    → ZoneController singleton
```

## Pointer Chain: GameAssembly.dll → Player Entity

```
GameAssembly.dll base address (from pymem module lookup)
  + CLIENT_TYPEINFO_RVA → read ptr → Il2CppClass*
    + 0xB8 (CLASS_STATIC_FIELDS) → void* static_fields
      + 0x0 (MINE_STATIC) → Client.mine (player Entity*)
```

## Entity Offsets (EntityOff)

Base class for all game entities (players, NPCs, mobs).

| Offset | Field | Type | Purpose |
|--------|-------|------|---------|
| 0x118 | ID | uint | Entity unique ID |
| 0x120 | NAME | Il2CppString* | Display name |
| 0x140 | RACE_HID | Il2CppString* | Race identifier |
| 0x148 | SEX_HID | Il2CppString* | Gender identifier |
| 0x190 | IS_STUNNED | bool | Stun status |
| 0x191 | IS_FEARED | bool | Fear status |
| 0x19C | IS_CORPSE | bool | Dead (corpse) |
| 0x19D | IS_HOSTILE | bool | Hostile to player |
| 0x1B0 | TARGET_HANDLER | EntityTargetHandler* | Target tracking |
| 0x250 | STATS | EntityStats* | Stats dictionary |
| 0x258 | IS_CASTING | bool | Casting a spell |
| 0x25F | AUTOATTACKING | bool | Auto-attack on |
| 0x280 | POSITION | AntiTamperVector3* | World position |
| 0x28C | POSTURE | int | 0=standing, 1=sitting |
| 0x2D0 | BUFFS | EntityBuffs* | Buff/debuff dictionary |

## Client Offsets (ClientOff, extends Entity)

Local player-specific fields.

| Offset | Field | Type | Purpose |
|--------|-------|------|---------|
| 0x0 | MINE_STATIC | Client* | Static: local player instance |
| 0x2F8 | AUTO_FOLLOW | Entity* | Auto-follow target |
| 0x308 | CLASS_HID | Il2CppString* | Player class (e.g., "enchanter") |
| 0x330 | INVENTORY | Inventory* | Player inventory |
| 0x370 | LAST_TARGET | Entity* | Previous tab-target |
| 0x388 | HEADING_ATF | AntiTamperFloat* | Heading in degrees (0-360) |
| 0x3C2 | IS_FEIGN_DEATH | bool | Feign death active |
| 0x4AC | HEADING_RAW | float | Cached heading copy (degrees) |
| 0x4D8 | ABILITIES | ClientAbilities* | Ability list |

## AntiTamper Wrappers

Position and heading use tamper-protected wrappers. Values are stored indirectly behind pointer chains.

### AntiTamperVector3 (position at entity + 0x280)

```
AntiTamperVector3*:
  +0x10 → AntiTamperFloat* _x
  +0x18 → AntiTamperFloat* _y (vertical)
  +0x20 → AntiTamperFloat* _z
```

### AntiTamperFloat

```
AntiTamperFloat*:
  +0x10 → float PRIMARY (the actual value)
```

### Full position read path:
```
entity + 0x280 → AntiTamperVector3*
  + 0x10 → AntiTamperFloat* → + 0x10 = float x
  + 0x18 → AntiTamperFloat* → + 0x10 = float y
  + 0x20 → AntiTamperFloat* → + 0x10 = float z
```

### Heading read path:
```
entity + 0x388 → AntiTamperFloat* → + 0x10 = float heading_degrees
```

## Target Reading

```
entity + 0x1B0 → EntityTargetHandler*
  + 0x18 → Nullable<uint> _targetId
  + 0x20 → Entity* _targetEntity (same Entity layout as player)
```

## Stats Reading

Stats stored as Dictionary<int, ObservableValue<int>>.

```
entity + 0x250 → EntityStats*
  + 0x10 → Dictionary*
    + 0x18 → Entry[] (array of entries)
    + 0x20 → int count

Entry layout (0x18 bytes each, array data starts at + 0x20):
  + 0x00 → int hashCode (-1 = free slot)
  + 0x08 → int key (stat index)
  + 0x10 → ObservableValue<int>* → + 0x10 = int value
```

**Stat indices:**

| Index | Stat |
|-------|------|
| 0 | Current HP |
| 1 | Max HP |
| 2 | Current Mana |
| 3 | Max Mana |
| 4 | Current Endurance |
| 5 | Max Endurance |
| 17 | Level |

Full stat enum in `game_data.py` (Stat class, 64 types).

## Buff Reading

Buffs stored as Dictionary<uint, BuffRecord>.

```
entity + 0x2D0 → EntityBuffs*
  + 0x10 → Dictionary<uint, BuffRecord>*
    → iterate entries (same dict layout as stats)
      → entry.value → BuffRecord*
```

### BuffRecord Offsets

| Offset | Field | Type |
|--------|-------|------|
| 0x10 | ENTITY_BUFF_ID | uint |
| 0x18 | BUFF_HID | Il2CppString* |
| 0x20 | BUFF_NAME | Il2CppString* |
| 0x28 | TYPE | Il2CppString* |
| 0x30 | STACKS | ushort |
| 0x38 | DATA | Il2CppString* |
| 0x40 | ICON_HID | Il2CppString* |
| 0x48 | ABILITY_HID | Il2CppString* |
| 0x50 | CATEGORY_HID | Il2CppString* |
| 0x58 | FADE_TIME_MS | ulong |
| 0x60 | DURATION_MS | uint |
| 0x68 | DESCRIPTION | Il2CppString* |

## Zone Reading

```
GameAssembly.dll base + ZONE_CONTROLLER_TYPEINFO_RVA → Il2CppClass*
  + 0xB8 → static_fields → + 0x0 → ZoneController instance
    + 0x28 → Il2CppString* currentZoneHid (e.g., "nightharbor")
```

## IL2CPP Internal Structures

### Il2CppString
```
+ 0x10 → int32 length (char count)
+ 0x14 → char[length] (UTF-16LE encoded)
```

### Il2CppArray
```
+ 0x18 → int32/ulong length
+ 0x20 → T[] data start
```

### Dictionary<K, V>
```
+ 0x10 → int[] _buckets
+ 0x18 → Entry[] _entries
+ 0x20 → int _count
+ 0x28 → int _freeCount
+ 0x2C → int _version
```

### Dictionary Entry (0x18 bytes)
```
+ 0x00 → int hashCode (-1 = free)
+ 0x08 → TKey key
+ 0x10 → TValue value (pointer for ref types)
```

### Il2CppClass
```
+ 0xB8 → void* static_fields (Unity 6000.x / 2023+)
```

## GameSnapshot Fields

All fields populated by `_poll_once()` in the background polling thread:

**Player:** `player` (dict), `player_hp`, `player_max_hp`, `player_mana`, `player_max_mana`, `player_endurance`, `player_max_endurance`, `player_level`, `player_buffs` (list), `player_x`, `player_y`, `player_z`, `player_heading`, `zone_name`

**Target:** `target` (dict), `target_hp`, `target_max_hp`, `target_mana`, `target_max_mana`, `target_level`, `target_buffs` (list), `target_x`, `target_y`, `target_z`

**Meta:** `timestamp` (monotonic), `age` (property: seconds since taken)
