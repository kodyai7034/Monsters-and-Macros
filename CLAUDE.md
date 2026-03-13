# Monsters & Memories Macro Tool

Macro automation for "Monsters and Memories" (Unity IL2CPP MMO). Reads game memory via pymem, evaluates conditions, sends humanized input via DirectInput.

## Environment

- **Run GUI/probes from Windows:** `python gui.py` (not `python3`, not WSL)
- **Run tests from WSL:** `python3 test_engine.py`
- **Game path:** `C:\Users\kskif\AppData\Local\Monsters & Memories`

## Project Docs

Detailed reference docs live in `docs/`. Read the relevant doc when working on that area:

| Doc | When to read |
|-----|-------------|
| `docs/architecture.md` | Starting a new session, understanding data flow |
| `docs/memory-offsets.md` | Touching `memory_reader.py`, probe scripts, or after a game patch |
| `docs/macro-engine.md` | Editing conditions, actions, reactive engine, or macro YAML files |
| `docs/map-and-calibration.md` | Working on `map_tab.py` or map features |
| `docs/game-patch-guide.md` | Game has been updated, offsets need re-extraction |

## Tests

```bash
python3 test_engine.py      # 57 engine tests
python3 test_dryrun.py      # Dry-run macros without game
python3 test_stress.py      # Stress test reactive engine
python3 test_detection.py   # Anti-detection validation
```
