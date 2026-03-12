# Monsters and Macros

A macro automation tool for [Monsters and Memories](https://www.monstersandmemories.com/), built with game-aware anti-detection intelligence extracted from the game's IL2CPP binary.

## Features

- **Macro Scripting** - Define macros in simple YAML: key sequences, ability rotations, movement patterns, conditional logic
- **Input Recording & Playback** - Record your keyboard/mouse input and replay it with adjustable speed
- **Screen Reading** - Detect health/mana bar levels via pixel color analysis for conditional automation
- **Anti-Detection Humanization** - Multi-layered evasion of the game's `BotBehaviorDetector` and `InputPatternDetector`:
  - Log-normal reaction time distribution (matches real human RT curves)
  - Per-session behavioral fingerprinting (no two sessions look alike)
  - Session fatigue simulation (gradual slowdown over time)
  - Random micro-behaviors (camera wiggles, hesitations, inventory checks)
  - Interval variance enforcement (breaks repetitive patterns)
- **GUI** - Tkinter interface with macro editor, recording manager, settings, and game info reference
- **CLI** - Full command-line interface for headless operation

## Requirements

- **Windows 10/11** (the game runs on Windows)
- **Python 3.10+**
- Game must be running and focused for input simulation to work

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

### Calibrate screen regions
```bash
python main.py calibrate
```

## Writing Macros

Macros are YAML files in the `macros/` folder. Here's an example:

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

  # Heal if health drops below 50%
  - action: condition
    check: health_below
    value: 0.5
    then:
      - action: use_ability
        slot: 5
        delay: 1.0

  # Sit to regen if mana is low
  - action: condition
    check: mana_below
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
| `target_nearest` | - | Tab-target nearest enemy |
| `move_forward` | `duration` | Hold W to move forward |
| `move_backward` | `duration` | Hold S to move backward |
| `strafe_left` | `duration` | Hold A to strafe left |
| `strafe_right` | `duration` | Hold D to strafe right |
| `turn` | `dx`, `duration` | Turn camera by dx pixels |
| `auto_run` | - | Toggle auto-run |
| `sit` | - | Sit down |
| `log` | `message` | Print a log message |
| `condition` | `check`, `value`, `then`, `else` | Conditional execution |
| `repeat` | `times`, `actions` | Repeat action block N times |
| `wait_for_health` | `above`, `timeout`, `interval` | Wait until health > threshold |
| `wait_for_mana` | `above`, `timeout`, `interval` | Wait until mana > threshold |

### Condition Checks

| Check | Description |
|---|---|
| `health_below` | True if health % < value |
| `health_above` | True if health % > value |
| `mana_below` | True if mana % < value |
| `mana_above` | True if mana % > value |
| `pixel_color` | True if pixel at (x,y) matches color |
| `pixel_not_color` | True if pixel at (x,y) doesn't match color |

### Keybind Names

Use these names in `key` fields to reference your configured keybinds (set in `config.yaml`):

`move_forward`, `move_backward`, `strafe_left`, `strafe_right`, `jump`, `auto_run`, `sit`, `ability_1` through `ability_10`, `target_nearest`, `chat_open`, `inventory`

## Configuration

Edit `config.yaml` to customize:

```yaml
# Anti-detection settings
humanizer:
  enabled: true
  intensity: 0.5    # 0.0 = minimal, 1.0 = maximum randomization

# Keybinds (match your in-game settings)
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

## Project Structure

```
Monsters-and-Macros/
  main.py              # CLI entry point (also launches GUI)
  gui.py               # Tkinter GUI application
  input_simulator.py   # Keyboard/mouse simulation (DirectInput + pyautogui)
  humanizer.py         # Anti-detection humanization engine
  macro_engine.py      # YAML macro loader and executor
  macro_player.py      # Recorded macro playback
  macro_recorder.py    # Input recording (keyboard + mouse)
  screen_reader.py     # Screen capture and pixel analysis
  game_data.py         # Game constants extracted from IL2CPP dump
  config.yaml          # User configuration
  requirements.txt     # Python dependencies
  macros/              # Macro definition files (.yaml)
  recordings/          # Recorded input files (.json)
  routes/              # Waypoint route files (planned)
```

## Hotkeys

| Key | Action |
|---|---|
| F12 | Emergency stop (configurable in config.yaml) |

## Disclaimer

This tool is for personal/educational use. Use at your own risk. The developers of this tool are not responsible for any consequences of using it.

## License

MIT
