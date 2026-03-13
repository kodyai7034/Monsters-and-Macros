# Macro Engine Reference

## Active Macro Actions

Actions executed sequentially in `_execute_actions()`. All input guarded by `_input_lock`.

### Movement
| Action | Parameters | Description |
|--------|-----------|-------------|
| `move_forward` | `duration` (seconds) | Hold W key |
| `move_backward` | `duration` (seconds) | Hold S key |
| `strafe_left` | `duration` (seconds) | Hold A key |
| `strafe_right` | `duration` (seconds) | Hold D key |
| `turn` | `dx` (pixels), `duration` (seconds) | Right-mouse drag to turn camera |
| `move_to_target` | `range` (default 5.0), `timeout` (default 15s) | Navigate toward target using heading |

### Targeting
| Action | Parameters | Description |
|--------|-----------|-------------|
| `target_nearest` | — | Press tab-target key |
| `target_nearest_hostile` | `delay` (optional) | Press F8 (hostile target) |
| `assist` | — | Target your target's target |

### Combat
| Action | Parameters | Description |
|--------|-----------|-------------|
| `use_ability` | `slot` (1-10) | Press ability hotkey with humanized delay |
| `auto_attack` | — | Toggle auto-attack |
| `interact` | — | Loot / interact with target |

### State
| Action | Parameters | Description |
|--------|-----------|-------------|
| `sit` | — | Sit down |
| `stand` | — | Stand up |
| `press` | `key` (keybind name) | Press arbitrary key from config |

### Wait
| Action | Parameters | Description |
|--------|-----------|-------------|
| `wait` | `duration` (seconds) | Simple sleep |
| `wait_for_health` | `above` (0-1), `timeout`, `interval` | Wait until health threshold |
| `wait_for_mana` | `above` (0-1), `timeout`, `interval` | Wait until mana threshold |
| `wait_for_target_dead` | `timeout` (default 60s), `interval` | Wait until target is corpse/gone |
| `wait_for_combat_end` | `timeout` (default 60s), `interval` | Wait until not attacking + no target |

### Control Flow
| Action | Parameters | Description |
|--------|-----------|-------------|
| `condition` | `check`, `then` (actions), `else` (actions) | If/then/else branching |
| `repeat` | `times`, `actions` (array) | Loop N times |
| `log` | `message` | Print to console |

## move_to_target Details

Heading-based navigation loop:

1. Calculate desired heading: `atan2(dx, dz)` toward target, mapped to 0-360 degrees
2. Read current heading from `ClientOff.HEADING_ATF` (AntiTamperFloat at 0x388)
3. Compute signed angle difference (-180 to +180)
4. If |diff| > 5 degrees: turn via mouse drag (~4 pixels per degree), then re-check
5. If facing target: move forward for `min(0.5, max(0.1, distance / 50))` seconds
6. Repeat until within `range` or `timeout`

**Calibration needed:** The 4px/degree ratio and atan2(dx,dz) convention may need tuning in-game.

## Condition Checks (40+)

### Screen-Based
| Check | Parameters | Evaluates |
|-------|-----------|-----------|
| `health_below` | `value` (0-1) | Screen health bar % < value |
| `health_above` | `value` (0-1) | Screen health bar % > value |
| `mana_below` | `value` (0-1) | Screen mana bar % < value |
| `mana_above` | `value` (0-1) | Screen mana bar % > value |
| `pixel_color` | `x`, `y`, `color` [R,G,B] | Pixel at (x,y) matches color |
| `pixel_not_color` | `x`, `y`, `color` [R,G,B] | Pixel doesn't match |

### Target Status
| Check | Parameters | Evaluates |
|-------|-----------|-----------|
| `has_target` | — | Player has a target |
| `no_target` | — | Player has no target |
| `target_is_hostile` | — | Target is hostile |
| `target_is_corpse` | — | Target is dead |
| `target_is_stunned` | — | Target is stunned |
| `target_is_feared` | — | Target is feared |
| `target_is_mezzed` | — | Target has "mez" category buff |

### Target Buffs & Stats
| Check | Parameters | Evaluates |
|-------|-----------|-----------|
| `target_has_buff` | `buff_name` | Target has buff (case-insensitive substring) |
| `target_not_has_buff` | `buff_name` | Target lacks buff |
| `target_has_buff_category` | `category` | Target has buff in category |
| `target_not_has_buff_category` | `category` | Target lacks category |
| `target_health_below` | `value` (0-1) | Target HP % < value |
| `target_health_above` | `value` (0-1) | Target HP % > value |
| `target_level_above` | `value` (int) | Target level > value |
| `target_level_below` | `value` (int) | Target level < value |
| `target_name` | `name` | Target name equals (case-insensitive) |
| `target_name_contains` | `name` | Target name contains substring |

### Player Status
| Check | Parameters | Evaluates |
|-------|-----------|-----------|
| `player_is_casting` | — | Player casting |
| `player_not_casting` | — | Player not casting |
| `player_is_sitting` | — | Posture == 1 |
| `player_is_standing` | — | Posture == 0 |
| `player_is_autoattacking` | — | Auto-attack on |
| `player_not_autoattacking` | — | Auto-attack off |

### Player Resources & Stats
| Check | Parameters | Evaluates |
|-------|-----------|-----------|
| `mem_health_below` | `value` (0-1) | Memory health % < value |
| `mem_health_above` | `value` (0-1) | Memory health % > value |
| `mem_mana_below` | `value` (0-1) | Memory mana % < value |
| `mem_mana_above` | `value` (0-1) | Memory mana % > value |
| `endurance_below` | `value` (0-1) | Endurance % < value |
| `endurance_above` | `value` (0-1) | Endurance % > value |
| `player_level_above` | `value` (int) | Level > value |
| `player_level_below` | `value` (int) | Level < value |
| `player_buff_count_above` | `value` (int) | Buff count > value |
| `player_buff_count_below` | `value` (int) | Buff count < value |
| `player_has_buff` | `buff_name` | Has buff (case-insensitive substring) |
| `player_not_has_buff` | `buff_name` | Lacks buff |

### Combat & Zone
| Check | Parameters | Evaluates |
|-------|-----------|-----------|
| `in_combat` | — | Auto-attacking OR has hostile target |
| `not_in_combat` | — | Not attacking AND no hostile target |
| `zone_is` | `zone` | Zone name matches (case-insensitive) |
| `zone_is_not` | `zone` | Zone name differs |

### Compound Logic
| Check | Parameters | Evaluates |
|-------|-----------|-----------|
| `and` | `conditions` (array) | ALL conditions true |
| `or` | `conditions` (array) | ANY condition true |
| `not` | `condition` (single) | Negates inner condition |

## Reactive Engine

### Design (MacroQuest-style)

Single background thread evaluates ALL monitors' rules in one global priority queue.

- Rules sorted by priority number (lower = fires first)
- **Only one rule fires per tick** — prevents monitor conflicts
- Per-rule cooldowns prevent spam
- Poll interval uses the fastest (lowest) across all loaded monitors

### Rule Structure (YAML)

```yaml
type: reactive
poll_interval: 0.3

rules:
  - name: "Emergency heal"
    priority: 1          # lower = higher priority
    condition:
      check: and
      conditions:
        - check: mem_health_below
          value: 0.25
        - check: player_not_casting
    cooldown: 2.0        # seconds before this rule can fire again
    actions:
      - action: use_ability
        slot: 6
      - action: wait
        duration: 3.5
```

### Reactive-Supported Actions

Limited subset: `use_ability`, `sit`, `stand`, `wait`, `log`, `press`, and generic fallback to MacroPlayer.

### Example: Multiple Monitors Running Together

```
smart_healer:     pri 1 (emergency), pri 5 (fast heal), pri 10 (HoT), pri 30 (sit)
debuff_monitor:   pri 15 (cure)
mana_sitter:      pri 50 (sit when safe)

→ All rules merged, sorted: [1, 5, 10, 15, 30, 50]
→ Each tick: check rule 1 first, if matches & off cooldown → fire, skip rest
→ If rule 1 doesn't match, try rule 5, etc.
→ Only ONE rule fires per tick
```
