# Game Patch Update Guide

When Monsters and Memories patches, IL2CPP offsets in `memory_reader.py` will break. Here's how to fix them.

## Step 1: Re-run Il2CppDumper

Get the latest Il2CppDumper from GitHub releases. Run it on:
- `GameAssembly.dll` — from game install folder
- `global-metadata.dat` — from `<game>/MnM_Data/il2cpp_data/Metadata/`

Game path: `C:\Users\kskif\AppData\Local\Monsters & Memories`

Output files you need:
- `dump.cs` — Class definitions with field offsets
- `script.json` — TypeInfo RVA addresses

## Step 2: Find Updated Offsets

Search `dump.cs` for these classes and note new field offsets:

| Class | Key Fields to Find |
|-------|-------------------|
| `Entity` | id, entityName, isStunned, isFeared, isCorpse, isHostile, isCasting, autoattacking, _stats, _localInterpolatedServerPosition, CurrentPosture, TargetHandler, Buffs |
| `Client` (extends Entity) | mine (static), classHID, autoFollowTarget, inventory, lastTarget, Abilities, isFeignDeath |
| `AntiTamperVector3` | _x, _y, _z |
| `AntiTamperFloat` | _primary |
| `EntityTargetHandler` | _targetId, _targetEntity |
| `EntityBuffs` | _buffs |
| `BuffRecord` | All fields (entityBuffID through description) |
| `EntityStats` | _stats (dictionary field) |

## Step 3: Find Updated RVAs

Search `script.json` for TypeInfo addresses:
- `"Client"` → CLIENT_TYPEINFO_RVA
- `"ZoneController"` → ZONE_CONTROLLER_TYPEINFO_RVA

If the class isn't in `script.json`, use `find_zone_rva.py` as a template to scan for it.

## Step 4: Find Heading Offset

Heading is NOT in the Il2CppDumper output (it was found by live probing). After updating other offsets:

1. Run `python probe_rotation_live.py` with game open
2. Stand still for baseline, then turn character
3. Look for AntiTamperFloat pointer that shows degree values changing
4. Update `ClientOff.HEADING_ATF` and `ClientOff.HEADING_RAW`

## Step 5: Update memory_reader.py

Update these sections:
- `CLIENT_TYPEINFO_RVA` and `ZONE_CONTROLLER_TYPEINFO_RVA` constants
- `EntityOff` class field offsets
- `ClientOff` class field offsets
- `AntiTamperVector3Off`, `AntiTamperFloatOff` (unlikely to change)
- `TargetHandlerOff`, `EntityBuffsOff`, `BuffRecordOff`
- `IL2CPP.CLASS_STATIC_FIELDS` (if Unity version changes)

## Step 6: Verify

Run probe scripts from Windows with game open:

```powershell
python probe_offsets.py          # Full chain verification
python probe_rotation_live.py    # Heading verification
python probe_zone.py             # Zone controller verification
```

Then run tests from WSL:

```bash
python3 test_engine.py
```

## Probe Scripts Reference

| Script | Purpose |
|--------|---------|
| `probe_offsets.py` | Walks full pointer chain, prints every field value |
| `probe_rotation.py` | Static scan for rotation candidates near position offset |
| `probe_rotation_live.py` | Continuous poll — highlights values that change when turning |
| `probe_zone.py` | Verifies ZoneController singleton chain |
| `find_zone_rva.py` | Scans GameAssembly.dll data section for class TypeInfo RVAs |

## Common Issues

- **Il2CppDumper download fails:** GitHub release asset names can be misleading. Use `gh release download` or check exact asset names via API.
- **CLASS_STATIC_FIELDS wrong:** Unity version upgrades can move this. Scan nearby offsets (0x80-0xF0) on Il2CppClass — `probe_offsets.py` does this automatically.
- **Client.mine is NULL:** Player not logged into a character yet (null at character select).
- **Stats all zero:** ObservableValue layout may have changed. Check the value offset (currently 0x10).
