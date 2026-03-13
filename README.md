# Monsters and Macros

A macro automation tool for [Monsters and Memories](https://www.monstersandmemories.com/), built with game-aware anti-detection intelligence and direct memory reading extracted from the game's IL2CPP binary.

## Features

- **Macro Scripting** — Define macros in simple YAML: key sequences, ability rotations, movement patterns, conditional logic
- **Memory Reader** — Read game state directly from process memory: health, mana, buffs, target info, stats. Background polling thread keeps a live snapshot updated every 100ms
- **Event System** — React to game state changes: target switched, health dropped, buff gained/lost, player died
- **Input Recording & Playback** — Record your keyboard/mouse input and replay it with adjustable speed
- **Screen Reading** — Detect health/mana bar levels via pixel color analysis for conditional automation
- **Keybind Import** — Auto-import your keybinds from the game's `controls.json`
- **Anti-Detection Humanization** — Multi-layered evasion of the game's `BotBehaviorDetector` and `InputPatternDetector`:
  - Log-normal reaction time distribution (matches real human RT curves)
  - Per-session behavioral fingerprinting (no two sessions look alike)
  - Session fatigue simulation (gradual slowdown over time)
  - Random micro-behaviors (camera wiggles, hesitations, inventory checks)
  - Interval variance enforcement (breaks repetitive patterns)
- **GUI** — Tkinter interface with macro editor, recording manager, settings, and game info reference
- **CLI** — Full command-line interface for headless operation

## Requirements

- **Windows 10/11** (the game runs on Windows)
- **Python 3.10+**
- Game must be running for memory reading; game must be focused for input simulation

## Installation

```bash
git clone https://github.com/kodyai7034/Monsters-and-Macros.git
cd Monsters-and-Macros
pip install -r requirements.txt
```

### Dependencies

| Package | Purpose |
|---|---|
| `pydirectinput` | DirectInput keyboard/mouse simulation (game-compatible) |
| `pyautogui` | Fallback input simulation + screen capture |
| `pynput` | Input recording (keyboard/mouse listener) |
| `keyboard` | Global hotkey support (F12 emergency stop) |
| `Pillow` | Screen region capture for health/mana detection |
| `pyyaml` | Macro definition files |
| `pymem` | Process memory reading (ReadProcessMemory API) |

## Quick Start

### Launch the GUI
```bash
python main.py
```

### Run a macro from CLI
```bash
python main.py run combat_rotation.yaml --loop
```

### Record input
```bash
python main.py record my_recording.json
```

### Play back a recording
```bash
python main.py play recordings/my_recording.json --speed 1.5 --loop
```

### Import keybinds from game
```bash
python import_keybinds.py              # Auto-detect controls.json
python import_keybinds.py --show       # Preview without writing
```

### Test memory reader
```bash
python probe_offsets.py                 # Validate all IL2CPP pointer chains
python memory_reader.py                 # One-shot player/target dump
python memory_reader.py --watch         # Live monitoring with events
```

## Memory Reader

The memory reader attaches to `mnm.exe` and reads game state via `ReadProcessMemory`. It uses IL2CPP offsets extracted from `dump.cs` to navigate the game's object hierarchy.

### Architecture

```
GameAssembly.dll + TypeInfo RVA
    -> Il2CppClass -> static_fields -> Client.mine (player entity)
        -> Entity fields (name, HP, stunned, casting, etc.)
        -> TargetHandler -> target entity
        -> EntityStats dictionary (HP, mana, level, attributes, resists)
        -> EntityBuffs dictionary (buff name, category, stacks, duration)
```

### Polling Thread

When enabled, a background thread reads all game state every 100ms (configurable) and stores it in a `GameSnapshot`. Macros read from the snapshot — no memory reads on the hot path.

```python
reader = GameMemoryReader(config={"poll_interval": 0.1})
reader.connect()

# Snapshot is always fresh
snap = reader.snapshot
print(f"HP: {snap.player_hp}/{snap.player_max_hp}")
print(f"Target: {snap.target['name'] if snap.target else 'None'}")
```

### Events

Register callbacks for game state changes:

```python
reader.on("target_changed", lambda t: print(f"New target: {t['name']}"))
reader.on("health_warning", lambda pct: print(f"Low HP: {pct:.0%}"))
reader.on("buff_gained", lambda b: print(f"Gained: {b['name']}"))
reader.on("buff_lost", lambda name: print(f"Lost: {name}"))
reader.on("player_died", lambda: print("You died!"))
```

### Offset Probe

`probe_offsets.py` walks every pointer chain step by step and reports OK/FAIL at each level. Run it after game patches to verify offsets haven't shifted:

```
python probe_offsets.py

  [OK] Il2CppClass*           @ 0x7FFE487E05D8  =>  0x1FD3242A110
  [OK] static_fields           @ 0x1FD3242A1C8  =>  0x1FD07E7F780
  [OK] Client.mine             @ 0x1FD07E7F780  =>  0x1FF24A2A800
  [OK] Entity.entityName       @ 0x1FF24A2A920  =>  "Kaybee"
  ...
```

If offsets break after a patch, re-run [Il2CppDumper](https://github.com/Perfare/Il2CppDumper) on the new `GameAssembly.dll` and update the offset constants in `memory_reader.py`.

## Writing Macros

Macros are YAML files in the `macros/` folder:

```yaml
name: "Combat Rotation"
description: "Basic combat loop with healing"
loop_delay: 0.3

actions:
  # Target nearest enemy
  - action: target_nearest
    delay: 0.3

  # Use abilities
  - action: use_ability
    slot: 1
    delay: 0.5

  - action: use_ability
    slot: 2
    delay: 0.5

  # Heal if health drops below 50% (memory-based)
  - action: condition
    check: mem_health_below
    value: 0.5
    then:
      - action: use_ability
        slot: 5
        delay: 1.0

  # Don't re-mez if target already mezzed
  - action: condition
    check: target_is_mezzed
    else:
      - action: use_ability
        slot: 3
        delay: 2.0

  # Only debuff if target doesn't have it
  - action: condition
    check: target_not_has_buff
    buff_name: "Suffocate"
    then:
      - action: use_ability
        slot: 4

  # Sit to regen if mana is low
  - action: condition
    check: mem_mana_below
    value: 0.2
    then:
      - action: sit
      - action: wait_for_mana
        above: 0.8
        timeout: 45
```

### Available Actions

| Action | Parameters | Description |
|---|---|---|
| `press` | `key`, `duration` | Press a key |
| `hold` | `key`, `duration` | Hold a key for duration |
| `click` | `x`, `y`, `button` | Click at position |
| `move` | `x`, `y`, `duration` | Move mouse to position |
| `type` | `text`, `interval` | Type text |
| `combo` | `keys` (list) | Key combination (e.g., ctrl+a) |
| `wait` | `duration` | Wait for duration (seconds) |
| `scroll` | `amount` | Scroll mouse wheel |
| `use_ability` | `slot` (1-10) | Press ability key with anti-detection delay |
| `target_nearest` | — | Tab-target nearest enemy |
| `move_forward` | `duration` | Hold W to move forward |
| `move_backward` | `duration` | Hold S to move backward |
| `strafe_left` | `duration` | Hold A to strafe left |
| `strafe_right` | `duration` | Hold D to strafe right |
| `turn` | `dx`, `duration` | Turn camera by dx pixels |
| `auto_run` | — | Toggle auto-run |
| `sit` | — | Sit down |
| `log` | `message` | Print a log message |
| `condition` | `check`, `value`, `then`, `else` | Conditional execution |
| `repeat` | `times`, `actions` | Repeat action block N times |
| `wait_for_health` | `above`, `timeout`, `interval` | Wait until health > threshold |
| `wait_for_mana` | `above`, `timeout`, `interval` | Wait until mana > threshold |

### Condition Checks

#### Screen-based (pixel reading)

| Check | Description |
|---|---|
| `health_below` | True if health bar % < value |
| `health_above` | True if health bar % > value |
| `mana_below` | True if mana bar % < value |
| `mana_above` | True if mana bar % > value |
| `pixel_color` | True if pixel at (x,y) matches color |
| `pixel_not_color` | True if pixel at (x,y) doesn't match color |

#### Memory-based (require `memory: enabled: true`)

| Check | Parameters | Description |
|---|---|---|
| `has_target` | — | Player has something targeted |
| `no_target` | — | No target selected |
| `target_is_hostile` | — | Target is hostile |
| `target_is_corpse` | — | Target is dead |
| `target_is_stunned` | — | Target is stunned |
| `target_is_feared` | — | Target is feared |
| `target_is_mezzed` | — | Target has mez category buff |
| `target_has_buff` | `buff_name` | Target has buff (name substring, case-insensitive) |
| `target_not_has_buff` | `buff_name` | Target doesn't have buff |
| `player_has_buff` | `buff_name` | Player has buff |
| `player_not_has_buff` | `buff_name` | Player doesn't have buff |
| `player_is_casting` | — | Player is mid-cast |
| `player_not_casting` | — | Player is not casting |
| `target_name` | `name` | Target name matches exactly (case-insensitive) |
| `target_name_contains` | `name` | Target name contains substring |
| `mem_health_below` | `value` (0.0-1.0) | Player health % below threshold |
| `mem_health_above` | `value` (0.0-1.0) | Player health % above threshold |
| `mem_mana_below` | `value` (0.0-1.0) | Player mana % below threshold |
| `mem_mana_above` | `value` (0.0-1.0) | Player mana % above threshold |

### Keybind Names

Use these names in `key` fields to reference your configured keybinds (set in `config.yaml` or imported from game):

**Movement:** `move_forward`, `move_backward`, `turn_left`, `turn_right`, `strafe_left`, `strafe_right`, `jump`, `auto_run`, `sit`, `crouch`

**Abilities:** `ability_1` through `ability_10`

**Hot buttons:** `hotbutton_1` through `hotbutton_12` (Shift+number)

**Auras:** `aura_1` through `aura_10` (Ctrl+number)

**Targeting:** `target_nearest`, `target_friendly`, `target_nearest_friendly`, `target_nearest_hostile`, `target_last`, `target_self`, `target_party_1` through `target_party_5`

**UI:** `inventory`, `bags`, `abilities_book`, `skills_window`, `social_window`, `journal_window`, `guild_window`

**Chat:** `hail`, `consider`, `look`, `tell`, `reply`, `retell`, `party`

## Configuration

Edit `config.yaml` to customize:

```yaml
# Anti-detection settings
humanizer:
  enabled: true
  intensity: 0.5    # 0.0 = minimal, 1.0 = maximum randomization

# Memory reading (direct game memory)
memory:
  enabled: false                 # Set to true to enable memory-based conditions
  client_typeinfo_rva: 0x54405D8 # From IL2CPP script.json — update after game patches
  poll_interval: 0.1             # Snapshot update interval (seconds)

# Keybinds (match your in-game settings, or run import_keybinds.py)
keybinds:
  move_forward: "w"
  ability_1: "1"
  target_nearest: "tab"
  # ... etc

# Screen reading regions (use 'calibrate' command to find these)
screen:
  health_bar: [x, y, width, height]
  health_color: [R, G, B]
```

## Anti-Detection System

The game includes two detection systems (discovered via IL2CPP analysis):

### BotBehaviorDetector
- Flags actions faster than **100ms** as inhuman
- Monitors `PerfectAbilityTiming` and `InstantTargetAcquisition`
- Needs **5 detections** to trigger an alert
- **300-second cooldown** between alerts

### InputPatternDetector
- Flags **10+ identical actions** with machine-like precision
- Press duration std dev < **10ms** = suspicious
- Interval std dev < **10ms** = bot-like

### Our Defenses

| Layer | What it does |
|---|---|
| Log-normal RT model | Reaction times follow real human distribution curves |
| Session fingerprinting | 8 randomized personality traits per launch |
| Session fatigue | Gradual slowdown + sloppiness over 1-2 hours |
| Behavioral variation | Random camera wiggles, hesitations, jumps, inventory checks |
| Interval variance | Enforces std dev > 30ms between repeated actions |
| Pattern breaking | Injects random pauses every 3-8 actions |
| Minimum floor | All delays stay above 150ms (game threshold: 100ms) |

## Game Data

`game_data.py` contains data extracted from the IL2CPP dump and Addressables catalog:

- **EntityStatType enum** — All 60+ stat types (HP, mana, attributes, resists, haste, etc.)
- **StatusType enum** — Stunned, feared, mesmerized, silenced, invisible, etc.
- **Races** — Ashira, Dwarf, Elf_Wood, Gnome, Goblin, Halfling, Human, Ogre
- **Monsters** — 36 creature types (from AirElemental to Wolf)
- **Zones** — 14 zones with descriptions (NightHarbor, Calafrey, Szuur, etc.)
- **Weapons** — 27 weapon types (1H/2H swords, axes, bows, shields, etc.)
- **Armor** — Cloth, Leather, Chain, Plate + class-specific and named sets
- **Harvest nodes** — 11 ores (Tin to Adamantium) + 20 herbs
- **Chat channels** — 30+ channels (social, combat, system)
- **Bot detection thresholds** — Exact values from the game's anti-cheat code

## Project Structure

```
Monsters-and-Macros/
  main.py              # CLI entry point (also launches GUI)
  gui.py               # Tkinter GUI application
  input_simulator.py   # Keyboard/mouse simulation (DirectInput + pyautogui)
  humanizer.py         # Anti-detection humanization engine
  macro_engine.py      # YAML macro loader and executor with memory conditions
  macro_player.py      # Recorded macro playback
  macro_recorder.py    # Input recording (keyboard + mouse)
  screen_reader.py     # Screen capture and pixel analysis
  memory_reader.py     # Game memory reader (IL2CPP, polling thread, events)
  probe_offsets.py     # IL2CPP offset validation tool
  import_keybinds.py   # Import keybinds from game's controls.json
  game_data.py         # Game constants extracted from IL2CPP dump
  config.yaml          # User configuration
  requirements.txt     # Python dependencies
  macros/              # Macro definition files (.yaml)
  recordings/          # Recorded input files (.json)
```

## Hotkeys

| Key | Action |
|---|---|
| F12 | Emergency stop (configurable in config.yaml) |

## Updating After Game Patches

When the game updates, IL2CPP offsets may shift. To update:

1. Run [Il2CppDumper](https://github.com/Perfare/Il2CppDumper) on the new `GameAssembly.dll` + `global-metadata.dat`
2. Update offset constants in `memory_reader.py` from the new `dump.cs`
3. Update `CLIENT_TYPEINFO_RVA` from the new `script.json` (search for `Client.Client_TypeInfo`)
4. Run `python probe_offsets.py` to validate all chains
5. Run `python import_keybinds.py` if keybind mappings changed

## Disclaimer

This tool is for personal/educational use. Use at your own risk. The developers of this tool are not responsible for any consequences of using it.

## License

MIT
