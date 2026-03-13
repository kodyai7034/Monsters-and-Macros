# TODO — Monsters & Macros

## Bugs / Critical Fixes

- [ ] **Shift+/Ctrl+ keybind parsing** — Config supports `"shift+1"`, `"ctrl+2"` etc. but `press_key()` passes the raw string to pydirectinput instead of splitting into `key_combo("shift", "1")`. All hotbutton/aura keybinds silently fail.
- [ ] **move_to_target calibration** — The 4px/degree mouse-to-heading ratio is a guess. Needs in-game testing and tuning. The `atan2(dx, dz)` heading convention (0° = +Z) may not match the game's heading system.
- [ ] **Macro load errors swallowed** — `list_macros_by_type()` catches `Exception` and shows "(failed to parse)" with no details. Should log the actual error.

## In-Progress / Needs Testing

- [ ] **Test move_to_target in-game** — Heading reading works (confirmed via probe), but the full navigation loop (turn → move → check distance → repeat) hasn't been tested with a live target.
- [ ] **Test map calibration in-game** — 2-point calibration UI is complete but hasn't been tested end-to-end with game running.
- [ ] **Enchanter grind macro end-to-end** — Updated to use `move_to_target` but not tested in game yet.

## Engine Improvements

- [ ] **Condition value validation** — No type checking on YAML condition values. `value: "abc"` on `health_below` causes runtime TypeError. Validate on macro load.
- [ ] **Key name validation** — Typos in keybind names (`ablity_1` instead of `ability_1`) crash mid-macro. Validate against known key list on load.
- [ ] **YAML editor validation** — GUI macro editor saves without checking YAML syntax. Add parse check before write.
- [ ] **Reactive engine pause/resume** — Active macro pause pauses reactive monitors, but resuming doesn't propagate cleanly in all cases. Audit pause flow.
- [ ] **move_to_target: read target heading convention** — Run probe with known compass directions to map game heading to real-world directions (which degree = north?).

## New Features

### Movement & Navigation
- [ ] **Waypoint pathing** — Define a list of (x, z) waypoints; macro walks between them in sequence. Useful for grind loops that patrol a route.
- [ ] **Return-to-camp** — After combat, navigate back to a saved "camp" position. Common in EQ/MQ2 macros.
- [ ] **Stuck detection** — If position hasn't changed after N seconds of `move_forward`, try turning randomly or jumping. Prevents getting stuck on geometry.
- [ ] **Strafe-to-target** — Instead of turn + forward, strafe to align with target. Better for melee positioning.

### Combat & Abilities
- [ ] **Spell gem/memorize support** — Read which spells are memorized, swap spells in/out of spell bar.
- [ ] **Cast time awareness** — Read cast time from ability data, wait exactly the right amount instead of hardcoded `wait: 3.0`.
- [ ] **Aggro/threat detection** — Detect when multiple mobs are engaged (target switches, health drops from unknown source).
- [ ] **Pull range check** — Before nuking, verify target is within spell range using distance calculation.
- [ ] **Auto-loot improvements** — After looting, check if loot window is still open (multiple items), loot all.
- [ ] **Pet management** — Read pet entity data (if available), send pet commands, heal pet.

### Reactive Engine
- [ ] **Rule groups / profiles** — Save sets of reactive monitors as named profiles ("Solo Grind", "Group Healer") that can be toggled as a unit.
- [ ] **Conditional rule activation** — Enable/disable reactive rules based on zone or combat state (e.g., don't run CC monitor outside of dungeons).
- [ ] **Rule statistics** — Track how often each rule fires, average cooldown usage, time spent per rule. Display in GUI.

### Memory Reader
- [ ] **Read player facing from Entity** — Currently heading is only on Client (player). Find rotation on base Entity for mob facing direction (useful for backstab positioning).
- [ ] **Read group/raid members** — Find group member entity list for group-aware healing/buffing macros.
- [ ] **Read ability cooldowns** — Know when abilities are ready vs on cooldown, avoid wasting keypresses.
- [ ] **Read inventory** — Count consumables (food, drink, reagents) for automated restocking alerts.
- [ ] **Read chat messages** — Detect tells, group invites, or "mob is enraged" messages for reactive responses.
- [ ] **Experience tracking** — Read XP values, calculate XP/hour, estimate time to level.

### GUI
- [ ] **Macro editor syntax highlighting** — Color YAML keywords, action names, condition checks in the editor.
- [ ] **Live state dashboard** — Show player HP/MP/endurance bars, target info, active buffs, heading, zone in a real-time panel.
- [ ] **Reactive monitor dashboard** — Show which monitors are loaded, which rule fired last, cooldown timers, fire counts.
- [ ] **Screen region calibrator** — Visual overlay to click-drag health/mana bar regions instead of editing config.yaml manually.
- [ ] **Macro templates / wizard** — Guided creation: "What class? What role? What abilities?" → generates starter macro YAML.

### Map System
- [ ] **Route recording** — Record player path as they walk, save as waypoint list for patrol macros.
- [ ] **POI markers** — Add named markers on the map (camp spots, named mob spawns, quest NPCs).
- [ ] **Multi-point calibration** — Use 3+ calibration points with least-squares fit for better accuracy on warped map images.
- [ ] **Map sharing** — Export/import calibration + markers per zone as shareable JSON files.

### Anti-Detection
- [ ] **AFK detection avoidance** — Periodically inject random movement/camera during long grinds to avoid AFK timeout.
- [ ] **Patrol variance** — Vary grind routes slightly each loop (random waypoint offsets) so the path isn't pixel-identical.
- [ ] **Time-of-day behavior** — Shift play patterns based on session duration (shorter pulls when "tired", longer breaks).

### Quality of Life
- [ ] **Hot-reload macros** — Watch YAML files for changes, reload without restarting the engine.
- [ ] **Macro chaining** — `action: run_macro name: "buff_cycle"` to call one macro from another.
- [ ] **Global hotkeys** — Bind F-keys to start/stop specific macros without switching to the GUI.
- [ ] **Session logging** — Log all actions, condition evaluations, and rule fires to a file for post-session review.
- [ ] **Config per-character** — Multiple config profiles (keybinds, macros) for different characters/classes.
