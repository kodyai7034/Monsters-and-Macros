# Architecture

## Data Flow

```
Memory Reader (background thread, polls every 100ms)
    → GameSnapshot (immutable, thread-safe via lock)
        → Condition Evaluation (memory + screen + compound logic)
            → Macro Engine (active sequential OR reactive rule-based)
                → Input Simulator (humanized via DirectInput)
                    → Game receives keypress/mouse input
```

## Core Files

| File | Purpose |
|------|---------|
| `memory_reader.py` | IL2CPP memory reader — pointer chains from GameAssembly.dll to entity data |
| `macro_engine.py` | Dual-mode engine: active (sequential) + reactive (priority rule queue) |
| `input_simulator.py` | Keyboard/mouse via DirectInput, humanized delays |
| `humanizer.py` | Anti-detection: log-normal reaction times, session fingerprinting, fatigue |
| `gui.py` | Tkinter GUI — macros tab, recording tab, settings |
| `map_tab.py` | Map exploration tracking with 2-point calibration |
| `game_data.py` | Enums (Stat, Status, Posture), constants, zone/monster lists |
| `screen_reader.py` | Pixel color health/mana bar detection (fallback when memory unavailable) |
| `macro_player.py` | Playback engine for recorded or scripted action sequences |
| `macro_recorder.py` | Record keyboard/mouse input to JSON |
| `config.yaml` | Keybinds, input settings, memory RVAs, humanizer config |

## Macro Types

### Active Macros

YAML files with `actions:` key. Sequential scripts — combat rotations, grinding loops, movement patterns. One runs at a time in the main thread. Support conditions, repeats, nested action blocks.

### Reactive Macros

YAML files with `rules:` key. Priority-based monitors — healing, mana management, debuff response. Multiple run simultaneously via a single ReactiveEngine background thread.

**Key design decision:** Reactive monitors use a single-thread evaluation loop (MacroQuest-style), NOT per-monitor threads. This prevents conflicts like sit vs stand fighting each other. Only one rule fires per tick across ALL monitors, selected by priority.

## Threading Model

| Thread | Purpose | Synchronization |
|--------|---------|-----------------|
| Main | GUI + active macro execution | `_pause_event` (threading.Event) |
| Memory poller | Reads game state every 100ms | `_lock` on GameSnapshot |
| ReactiveEngine | Evaluates all reactive rules | `_lock` on rules, `_input_lock` on actions |

All input (keypress/mouse) is guarded by a shared `_input_lock` to prevent active and reactive macros from sending input simultaneously.

## Humanization Layers

1. **Log-normal reaction times** — matches human response curve
2. **Session fingerprint** — random per-launch personality (reaction speed, hold style, precision)
3. **Fatigue curve** — slows down over 1-2 hours, "second wind" resets every 15-30 min
4. **Interval variance** — breaks repetitive patterns (defeats InputPatternDetector)
5. **Micro-behaviors** — random camera wiggles, hesitations, inventory checks, jumps

## Config (config.yaml)

Key sections:
```yaml
keybinds:
  auto_attack: "q"
  interact: "u"
  auto_run: "e"
  target_nearest_hostile: "f8"
  sit: "x"
  ability_1: "1"  # through ability_10: "0"

memory:
  client_typeinfo_rva: 0x54405D8
  poll_interval: 0.1

humanizer:
  enabled: true
  intensity: 0.5  # 0.0-1.0
```
