"""
Auto-Probe — Continuous game memory scanner.

Runs on Windows, dumps findings to probes/ as JSON files that can be
examined from WSL without switching back and forth.

Usage (from Windows PowerShell):
    python auto_probe.py

Output goes to probes/ directory:
    probes/snapshot.json        — Full game state snapshot (updates every 2s)
    probes/all_stats.json       — All 64 stat indices with values
    probes/all_buffs.json       — Detailed buff list for player + target
    probes/entity_scan.json     — Raw field scan of player entity (0x100-0x500)
    probes/target_scan.json     — Raw field scan of target entity
    probes/nearby_scan.json     — Attempt to find nearby entity list
    probes/abilities_scan.json  — Probe ClientAbilities structure
    probes/unknown_fields.json  — Unidentified fields with interesting values
    probes/changelog.json       — Log of values that changed between scans

Press Ctrl+C to stop. All files are updated in-place every scan cycle.
"""

import sys
import os
import json
import time
import struct
import math
from datetime import datetime

try:
    import pymem
    import pymem.process
except ImportError:
    print("pymem not installed. Run: pip install pymem")
    sys.exit(1)

from memory_reader import (
    EntityOff, ClientOff, IL2CPP,
    AntiTamperVector3Off, AntiTamperFloatOff,
    TargetHandlerOff, EntityBuffsOff, BuffRecordOff,
    CLIENT_TYPEINFO_RVA, ZONE_CONTROLLER_TYPEINFO_RVA,
    ZoneControllerOff,
)

# Output directory
PROBE_DIR = os.path.join(os.path.dirname(__file__), "probes")

# All known stat indices from game_data.py
STAT_NAMES = {
    0: "HEALTH", 1: "MAX_HEALTH", 2: "MANA", 3: "MAX_MANA",
    4: "ENDURANCE", 5: "MAX_ENDURANCE",
    16: "EXPERIENCE", 17: "LEVEL", 18: "AC", 19: "WEIGHT", 20: "MAX_WEIGHT",
    21: "STR", 22: "STA", 23: "DEX", 24: "AGI", 25: "INT", 26: "WIS", 27: "CHA",
    28: "BASE_RUN_SPEED", 29: "BASE_WALK_SPEED", 30: "MOVEMENT_SPEED",
    31: "MELEE_HASTE", 32: "RANGED_HASTE", 33: "SPELL_HASTE",
    34: "ICE_RESIST", 35: "FIRE_RESIST", 36: "ELECTRIC_RESIST",
    37: "MAGIC_RESIST", 38: "CORRUPT_RESIST", 39: "POISON_RESIST",
    40: "DISEASE_RESIST", 41: "ESSENCE",
    42: "HEALTH_REGEN", 43: "MANA_REGEN", 44: "SPIN_VELOCITY",
    45: "PHYSICAL_DAMAGE", 46: "SPELL_DAMAGE",
    47: "CHANCE_TO_EAT", 48: "CHANCE_TO_DRINK",
    50: "SIZE", 51: "BLOCK_CHANCE", 52: "PARRY_CHANCE", 53: "DODGE_CHANCE",
    54: "BRASS_MOD", 55: "PERCUSSION_MOD", 56: "SINGING_MOD",
    57: "STRING_MOD", 58: "WIND_MOD",
    59: "MOUNT_DISCIPLINE", 60: "MOUNT_SWIFTNESS",
    61: "HOLY_RESIST", 62: "MELEE_DAMAGE", 63: "RANGED_DAMAGE",
}


# =========================================================================
# Low-level readers
# =========================================================================

def read_ptr(pm, addr):
    try:
        return pm.read_longlong(addr)
    except Exception:
        return 0

def read_int(pm, addr):
    try:
        return pm.read_int(addr)
    except Exception:
        return 0

def read_uint(pm, addr):
    try:
        return pm.read_uint(addr)
    except Exception:
        return 0

def read_float(pm, addr):
    try:
        return pm.read_float(addr)
    except Exception:
        return None

def read_bool(pm, addr):
    try:
        return pm.read_bool(addr)
    except Exception:
        return False

def read_ushort(pm, addr):
    try:
        return pm.read_ushort(addr)
    except Exception:
        return 0

def read_ulong(pm, addr):
    try:
        return pm.read_ulonglong(addr)
    except Exception:
        return 0

def read_il2cpp_string(pm, str_ptr):
    if not str_ptr or str_ptr < 0x10000:
        return ""
    try:
        length = pm.read_int(str_ptr + IL2CPP.STRING_LENGTH)
        if length <= 0 or length > 2048:
            return ""
        raw = pm.read_bytes(str_ptr + IL2CPP.STRING_CHARS, length * 2)
        return raw.decode("utf-16-le", errors="replace")
    except Exception:
        return ""

def read_string_at(pm, base, offset):
    ptr = read_ptr(pm, base + offset)
    return read_il2cpp_string(pm, ptr)

def read_antitamper_float(pm, atf_ptr):
    if not atf_ptr or atf_ptr < 0x10000:
        return None
    return read_float(pm, atf_ptr + AntiTamperFloatOff.PRIMARY)

def read_antitamper_vec3(pm, vec_ptr):
    if not vec_ptr or vec_ptr < 0x10000:
        return None
    coords = []
    for off in (AntiTamperVector3Off.X, AntiTamperVector3Off.Y, AntiTamperVector3Off.Z):
        atf = read_ptr(pm, vec_ptr + off)
        val = read_antitamper_float(pm, atf)
        coords.append(val if val is not None else 0.0)
    return coords


# =========================================================================
# Resolve pointers
# =========================================================================

def resolve_mine(pm, ga_base):
    il2cpp_class = read_ptr(pm, ga_base + CLIENT_TYPEINFO_RVA)
    if not il2cpp_class:
        return None
    static_fields = read_ptr(pm, il2cpp_class + IL2CPP.CLASS_STATIC_FIELDS)
    if not static_fields:
        return None
    return read_ptr(pm, static_fields + ClientOff.MINE_STATIC)

def resolve_target(pm, entity_ptr):
    handler = read_ptr(pm, entity_ptr + EntityOff.TARGET_HANDLER)
    if not handler:
        return None
    target = read_ptr(pm, handler + TargetHandlerOff.TARGET_ENTITY)
    return target if target and target > 0x10000 else None

def resolve_zone(pm, ga_base):
    il2cpp_class = read_ptr(pm, ga_base + ZONE_CONTROLLER_TYPEINFO_RVA)
    if not il2cpp_class:
        return ""
    static_fields = read_ptr(pm, il2cpp_class + IL2CPP.CLASS_STATIC_FIELDS)
    if not static_fields:
        return ""
    instance = read_ptr(pm, static_fields + ZoneControllerOff.INSTANCE_STATIC)
    if not instance:
        return ""
    return read_string_at(pm, instance, ZoneControllerOff.CURRENT_ZONE_HID)


# =========================================================================
# Probe: Entity basics
# =========================================================================

def probe_entity(pm, entity_ptr, label="entity"):
    """Read all known Entity fields into a dict."""
    if not entity_ptr:
        return None

    data = {
        "_label": label,
        "_address": f"0x{entity_ptr:X}",
        "id": read_uint(pm, entity_ptr + EntityOff.ID),
        "name": read_string_at(pm, entity_ptr, EntityOff.NAME),
        "race": read_string_at(pm, entity_ptr, EntityOff.RACE_HID),
        "sex": read_string_at(pm, entity_ptr, EntityOff.SEX_HID),
        "is_stunned": read_bool(pm, entity_ptr + EntityOff.IS_STUNNED),
        "is_feared": read_bool(pm, entity_ptr + EntityOff.IS_FEARED),
        "is_corpse": read_bool(pm, entity_ptr + EntityOff.IS_CORPSE),
        "is_hostile": read_bool(pm, entity_ptr + EntityOff.IS_HOSTILE),
        "is_casting": read_bool(pm, entity_ptr + EntityOff.IS_CASTING),
        "autoattacking": read_bool(pm, entity_ptr + EntityOff.AUTOATTACKING),
        "posture": read_int(pm, entity_ptr + EntityOff.POSTURE),
    }

    # Position
    vec_ptr = read_ptr(pm, entity_ptr + EntityOff.POSITION)
    pos = read_antitamper_vec3(pm, vec_ptr)
    if pos:
        data["position"] = {"x": round(pos[0], 4), "y": round(pos[1], 4), "z": round(pos[2], 4)}
    else:
        data["position"] = None

    return data

def probe_client_fields(pm, mine_ptr):
    """Read Client-specific fields beyond Entity base."""
    data = {
        "class_hid": read_string_at(pm, mine_ptr, ClientOff.CLASS_HID),
        "is_feign_death": read_bool(pm, mine_ptr + ClientOff.IS_FEIGN_DEATH),
    }

    # Heading
    atf_ptr = read_ptr(pm, mine_ptr + ClientOff.HEADING_ATF)
    heading = read_antitamper_float(pm, atf_ptr)
    data["heading"] = round(heading, 2) if heading is not None else None

    # Auto-follow
    af_ptr = read_ptr(pm, mine_ptr + ClientOff.AUTO_FOLLOW)
    if af_ptr and af_ptr > 0x10000:
        data["auto_follow_target"] = read_string_at(pm, af_ptr, EntityOff.NAME)
    else:
        data["auto_follow_target"] = None

    # Last target
    lt_ptr = read_ptr(pm, mine_ptr + ClientOff.LAST_TARGET)
    if lt_ptr and lt_ptr > 0x10000:
        data["last_target"] = read_string_at(pm, lt_ptr, EntityOff.NAME)
    else:
        data["last_target"] = None

    return data


# =========================================================================
# Probe: All stats
# =========================================================================

def probe_all_stats(pm, entity_ptr, label="entity"):
    """Read ALL stat dictionary entries (not just the 7 we normally poll)."""
    if not entity_ptr:
        return None

    stats_ptr = read_ptr(pm, entity_ptr + EntityOff.STATS)
    if not stats_ptr:
        return {"_error": "EntityStats pointer is NULL"}

    dict_ptr = read_ptr(pm, stats_ptr + 0x10)
    if not dict_ptr:
        return {"_error": "Stats dictionary pointer is NULL"}

    entries_arr = read_ptr(pm, dict_ptr + IL2CPP.DICT_ENTRIES)
    count = read_int(pm, dict_ptr + IL2CPP.DICT_COUNT)

    if not entries_arr or count <= 0:
        return {"_error": f"Stats dict empty or null (count={count})"}

    arr_length = read_int(pm, entries_arr + IL2CPP.ARRAY_LENGTH)
    data_start = entries_arr + IL2CPP.ARRAY_DATA

    stats = {"_label": label, "_count": count, "_array_length": arr_length, "stats": {}}
    found = 0

    for i in range(min(count + 10, arr_length, 128)):
        entry_base = data_start + (i * IL2CPP.ENTRY_SIZE)
        hash_code = read_int(pm, entry_base + IL2CPP.ENTRY_HASHCODE)
        if hash_code < 0:
            continue

        key = read_int(pm, entry_base + IL2CPP.ENTRY_KEY)
        obs_ptr = read_ptr(pm, entry_base + IL2CPP.ENTRY_VALUE)
        val = read_int(pm, obs_ptr + 0x10) if obs_ptr else 0

        stat_name = STAT_NAMES.get(key, f"UNKNOWN_{key}")
        stats["stats"][stat_name] = {"index": key, "value": val}
        found += 1
        if found >= count:
            break

    return stats


# =========================================================================
# Probe: All buffs
# =========================================================================

def probe_all_buffs(pm, entity_ptr, label="entity"):
    """Read full buff details for an entity."""
    if not entity_ptr:
        return None

    buffs_obj = read_ptr(pm, entity_ptr + EntityOff.BUFFS)
    if not buffs_obj:
        return {"_label": label, "buffs": [], "_note": "EntityBuffs is NULL"}

    dict_ptr = read_ptr(pm, buffs_obj + EntityBuffsOff.BUFFS_DICT)
    if not dict_ptr:
        return {"_label": label, "buffs": [], "_note": "Buffs dictionary is NULL"}

    entries_arr = read_ptr(pm, dict_ptr + IL2CPP.DICT_ENTRIES)
    count = read_int(pm, dict_ptr + IL2CPP.DICT_COUNT)

    if not entries_arr or count <= 0:
        return {"_label": label, "buffs": [], "_count": count}

    arr_length = read_int(pm, entries_arr + IL2CPP.ARRAY_LENGTH)
    data_start = entries_arr + IL2CPP.ARRAY_DATA

    buffs = []
    found = 0
    for i in range(min(count + 10, arr_length, 256)):
        entry_base = data_start + (i * IL2CPP.ENTRY_SIZE)
        hash_code = read_int(pm, entry_base + IL2CPP.ENTRY_HASHCODE)
        if hash_code < 0:
            continue

        buff_ptr = read_ptr(pm, entry_base + IL2CPP.ENTRY_VALUE)
        if not buff_ptr:
            continue

        buff = {
            "entity_buff_id": read_uint(pm, buff_ptr + BuffRecordOff.ENTITY_BUFF_ID),
            "buff_hid": read_string_at(pm, buff_ptr, BuffRecordOff.BUFF_HID),
            "name": read_string_at(pm, buff_ptr, BuffRecordOff.BUFF_NAME),
            "type": read_string_at(pm, buff_ptr, BuffRecordOff.TYPE),
            "stacks": read_ushort(pm, buff_ptr + BuffRecordOff.STACKS),
            "category_hid": read_string_at(pm, buff_ptr, BuffRecordOff.CATEGORY_HID),
            "ability_hid": read_string_at(pm, buff_ptr, BuffRecordOff.ABILITY_HID),
            "icon_hid": read_string_at(pm, buff_ptr, BuffRecordOff.ICON_HID),
            "fade_time_ms": read_ulong(pm, buff_ptr + BuffRecordOff.FADE_TIME_MS),
            "duration_ms": read_uint(pm, buff_ptr + BuffRecordOff.DURATION_MS),
            "description": read_string_at(pm, buff_ptr, BuffRecordOff.DESCRIPTION),
        }
        buffs.append(buff)
        found += 1
        if found >= count:
            break

    return {"_label": label, "_count": count, "buffs": buffs}


# =========================================================================
# Probe: Raw entity field scan
# =========================================================================

def probe_raw_entity_scan(pm, entity_ptr, label="entity", scan_range=(0x100, 0x500)):
    """Scan all fields on an entity, classifying each 8-byte slot.

    For each offset, tries to interpret as:
    - Pointer to IL2CPP string
    - Pointer to AntiTamperFloat
    - Pointer to AntiTamperVector3
    - Pointer to another entity (has name string at 0x120)
    - Raw float (4 bytes)
    - Raw int (4 bytes)
    - Bool sequence (1 byte)
    """
    if not entity_ptr:
        return None

    start, end = scan_range
    results = {"_label": label, "_address": f"0x{entity_ptr:X}", "_range": f"0x{start:X}-0x{end:X}", "fields": {}}

    known_offsets = {
        0x118: "ID", 0x120: "NAME", 0x140: "RACE_HID", 0x148: "SEX_HID",
        0x190: "IS_STUNNED", 0x191: "IS_FEARED", 0x19C: "IS_CORPSE", 0x19D: "IS_HOSTILE",
        0x1B0: "TARGET_HANDLER", 0x250: "STATS", 0x258: "IS_CASTING", 0x25F: "AUTOATTACKING",
        0x280: "POSITION", 0x28C: "POSTURE", 0x2D0: "BUFFS",
        0x2F8: "AUTO_FOLLOW", 0x308: "CLASS_HID", 0x330: "INVENTORY",
        0x370: "LAST_TARGET", 0x388: "HEADING_ATF", 0x3C2: "IS_FEIGN_DEATH",
        0x4AC: "HEADING_RAW", 0x4D8: "ABILITIES",
    }

    for off in range(start, end, 0x8):
        ptr = read_ptr(pm, entity_ptr + off)
        field_key = f"0x{off:03X}"
        known = known_offsets.get(off, None)

        entry = {"offset": f"0x{off:03X}"}
        if known:
            entry["known_as"] = known

        if ptr and 0x10000 < ptr < 0x7FFFFFFFFFFF:
            # Try as IL2CPP string
            text = read_il2cpp_string(pm, ptr)
            if text and len(text) < 200 and all(c.isprintable() or c == ' ' for c in text):
                entry["type"] = "string"
                entry["value"] = text
                results["fields"][field_key] = entry
                continue

            # Try as AntiTamperFloat
            atf = read_antitamper_float(pm, ptr)
            if atf is not None and not (atf != atf) and abs(atf) < 100000:
                entry["type"] = "antitamper_float"
                entry["value"] = round(atf, 4)
                results["fields"][field_key] = entry
                continue

            # Try as AntiTamperVector3
            vec = read_antitamper_vec3(pm, ptr)
            if vec and all(v is not None for v in vec) and all(abs(v) < 100000 for v in vec):
                if any(abs(v) > 0.001 for v in vec):
                    entry["type"] = "antitamper_vec3"
                    entry["value"] = [round(v, 4) for v in vec]
                    results["fields"][field_key] = entry
                    continue

            # Try as entity pointer (does it have a name at +0x120?)
            sub_name_ptr = read_ptr(pm, ptr + EntityOff.NAME)
            if sub_name_ptr:
                sub_name = read_il2cpp_string(pm, sub_name_ptr)
                if sub_name and len(sub_name) < 100 and all(c.isprintable() or c == ' ' for c in sub_name):
                    entry["type"] = "entity_ptr"
                    entry["entity_name"] = sub_name
                    entry["ptr"] = f"0x{ptr:X}"
                    results["fields"][field_key] = entry
                    continue

            # Generic pointer
            entry["type"] = "pointer"
            entry["ptr"] = f"0x{ptr:X}"
            results["fields"][field_key] = entry
        else:
            # Try raw floats at this offset
            f1 = read_float(pm, entity_ptr + off)
            f2 = read_float(pm, entity_ptr + off + 4)
            i1 = read_int(pm, entity_ptr + off)
            i2 = read_int(pm, entity_ptr + off + 4)

            # Only record if something is non-zero
            if i1 != 0 or i2 != 0:
                entry["type"] = "raw"
                entry["int_lo"] = i1
                entry["int_hi"] = i2
                if f1 is not None and abs(f1) > 0.001 and abs(f1) < 100000:
                    entry["float_lo"] = round(f1, 6)
                if f2 is not None and abs(f2) > 0.001 and abs(f2) < 100000:
                    entry["float_hi"] = round(f2, 6)

                # Check for bools in the region
                bools = []
                for b in range(8):
                    try:
                        val = pm.read_bool(entity_ptr + off + b)
                        if val:
                            bools.append(b)
                    except Exception:
                        pass
                if bools:
                    entry["true_bytes"] = bools

                results["fields"][field_key] = entry

    return results


# =========================================================================
# Probe: Abilities structure
# =========================================================================

def probe_abilities(pm, mine_ptr):
    """Probe the ClientAbilities structure to discover its layout."""
    abilities_ptr = read_ptr(pm, mine_ptr + ClientOff.ABILITIES)
    if not abilities_ptr:
        return {"_error": "ClientAbilities pointer is NULL"}

    data = {"_address": f"0x{abilities_ptr:X}", "fields": {}}

    # Scan the abilities object for interesting data
    for off in range(0x00, 0x80, 0x8):
        ptr = read_ptr(pm, abilities_ptr + off)
        if not ptr or ptr < 0x10000:
            continue

        entry = {"offset": f"0x{off:02X}"}

        # Try as string
        text = read_il2cpp_string(pm, ptr)
        if text and len(text) < 200:
            entry["type"] = "string"
            entry["value"] = text
            data["fields"][f"0x{off:02X}"] = entry
            continue

        # Try as array (IL2CPP array has length at +0x18, data at +0x20)
        arr_len = read_int(pm, ptr + IL2CPP.ARRAY_LENGTH)
        if 0 < arr_len < 200:
            entry["type"] = "possible_array"
            entry["length"] = arr_len

            # Try reading array elements as pointers
            elements = []
            for i in range(min(arr_len, 20)):
                elem = read_ptr(pm, ptr + IL2CPP.ARRAY_DATA + i * 8)
                if elem and elem > 0x10000:
                    # Try reading element as something useful
                    elem_name = read_il2cpp_string(pm, read_ptr(pm, elem + 0x20))
                    if elem_name:
                        elements.append({"index": i, "name": elem_name})
                    else:
                        elem_name = read_il2cpp_string(pm, read_ptr(pm, elem + 0x10))
                        if elem_name:
                            elements.append({"index": i, "name_alt": elem_name})
                        else:
                            elements.append({"index": i, "ptr": f"0x{elem:X}"})
                elif elem:
                    elements.append({"index": i, "raw": elem})

            if elements:
                entry["elements"] = elements
            data["fields"][f"0x{off:02X}"] = entry
            continue

        # Generic pointer
        entry["type"] = "pointer"
        entry["ptr"] = f"0x{ptr:X}"
        data["fields"][f"0x{off:02X}"] = entry

    return data


# =========================================================================
# Probe: Nearby entities (discovery)
# =========================================================================

def probe_nearby_entities(pm, mine_ptr, ga_base):
    """Try to discover the entity list / entity manager.

    Common patterns in Unity games:
    1. A static EntityManager/EntityList with a List<Entity> or Dictionary
    2. Entity[] array reference on a manager singleton
    3. Linked list of entities

    We'll scan static_fields on Client for pointers that look like collections
    of entities.
    """
    data = {"_note": "Experimental — scanning for entity collections", "candidates": []}

    # Strategy 1: Scan Client object for pointers to objects containing
    # arrays/dicts of entities
    for off in range(0x100, 0x600, 0x8):
        ptr = read_ptr(pm, mine_ptr + off)
        if not ptr or ptr < 0x10000:
            continue

        # Check if this pointer leads to an object with a dict or array
        # that contains entity pointers (things with names at +0x120)
        for sub_off in [0x10, 0x18, 0x20, 0x28]:
            sub_ptr = read_ptr(pm, ptr + sub_off)
            if not sub_ptr or sub_ptr < 0x10000:
                continue

            # Check if sub_ptr is an IL2CPP array
            arr_len = read_int(pm, sub_ptr + IL2CPP.ARRAY_LENGTH)
            if 1 <= arr_len <= 500:
                # Try reading elements as entity pointers
                entities_found = []
                for i in range(min(arr_len, 10)):
                    elem = read_ptr(pm, sub_ptr + IL2CPP.ARRAY_DATA + i * 8)
                    if elem and elem > 0x10000:
                        name_ptr = read_ptr(pm, elem + EntityOff.NAME)
                        name = read_il2cpp_string(pm, name_ptr) if name_ptr else ""
                        if name and len(name) < 50:
                            entities_found.append(name)

                if len(entities_found) >= 2:
                    data["candidates"].append({
                        "entity_offset": f"0x{off:03X}",
                        "sub_offset": f"0x{sub_off:02X}",
                        "array_length": arr_len,
                        "sample_names": entities_found[:10],
                    })

    return data


# =========================================================================
# Change detection
# =========================================================================

class ChangeTracker:
    """Track which values change between scans."""

    def __init__(self):
        self.previous = {}
        self.changes = []

    def update(self, scan_data, label):
        """Compare new scan to previous, record changes."""
        if not scan_data or "fields" not in scan_data:
            return

        new_changes = []
        for key, entry in scan_data["fields"].items():
            val = entry.get("value", entry.get("int_lo", entry.get("ptr")))
            prev_key = f"{label}:{key}"
            if prev_key in self.previous and self.previous[prev_key] != val:
                new_changes.append({
                    "timestamp": datetime.now().isoformat(),
                    "entity": label,
                    "field": key,
                    "known_as": entry.get("known_as"),
                    "type": entry.get("type"),
                    "old": self.previous[prev_key],
                    "new": val,
                })
            self.previous[prev_key] = val

        if new_changes:
            self.changes.extend(new_changes)
            # Keep last 500 changes
            self.changes = self.changes[-500:]

    def get_log(self):
        return self.changes


# =========================================================================
# File I/O
# =========================================================================

def save_json(filename, data):
    """Write data to JSON file atomically."""
    path = os.path.join(PROBE_DIR, filename)
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        os.replace(tmp, path)
    except Exception as e:
        print(f"  [WARN] Could not write {filename}: {e}")


# =========================================================================
# Main loop
# =========================================================================

def main():
    print("\n\033[96mMonsters & Memories — Auto Probe\033[0m")
    print("=" * 60)
    print(f"  Output: {PROBE_DIR}/")
    print(f"  Updates every 2 seconds. Press Ctrl+C to stop.")
    print("=" * 60)

    os.makedirs(PROBE_DIR, exist_ok=True)

    # Connect
    try:
        pm = pymem.Pymem("mnm.exe")
    except Exception as e:
        print(f"\n  [\033[91mFAIL\033[0m] Could not open mnm.exe: {e}")
        print(f"  Make sure the game is running.")
        sys.exit(1)

    ga_module = pymem.process.module_from_name(pm.process_handle, "GameAssembly.dll")
    if not ga_module:
        print("  [\033[91mFAIL\033[0m] GameAssembly.dll not found")
        sys.exit(1)

    ga_base = ga_module.lpBaseOfDll
    print(f"\n  [\033[92mOK\033[0m] Attached to mnm.exe (PID: {pm.process_id})")
    print(f"  [\033[92mOK\033[0m] GameAssembly.dll: 0x{ga_base:X}\n")

    tracker = ChangeTracker()
    scan_count = 0

    try:
        while True:
            scan_count += 1
            timestamp = datetime.now().isoformat()

            # Resolve player
            mine = resolve_mine(pm, ga_base)
            if not mine:
                print(f"  [scan {scan_count}] Client.mine is NULL — not logged in?")
                save_json("snapshot.json", {"timestamp": timestamp, "error": "Client.mine is NULL"})
                time.sleep(2)
                continue

            # Resolve target
            target_ptr = resolve_target(pm, mine)

            # Resolve zone
            zone = resolve_zone(pm, ga_base)

            # === Snapshot (quick summary) ===
            player = probe_entity(pm, mine, "player")
            player_client = probe_client_fields(pm, mine)
            target = probe_entity(pm, target_ptr, "target") if target_ptr else None

            # Distance to target
            dist = None
            if target and player and player["position"] and target["position"]:
                dx = target["position"]["x"] - player["position"]["x"]
                dz = target["position"]["z"] - player["position"]["z"]
                dist = round(math.sqrt(dx*dx + dz*dz), 2)

            snapshot = {
                "timestamp": timestamp,
                "scan": scan_count,
                "zone": zone,
                "player": player,
                "player_client": player_client,
                "target": target,
                "distance_to_target": dist,
            }
            save_json("snapshot.json", snapshot)

            # === All stats ===
            player_stats = probe_all_stats(pm, mine, "player")
            target_stats = probe_all_stats(pm, target_ptr, "target") if target_ptr else None
            save_json("all_stats.json", {
                "timestamp": timestamp,
                "player": player_stats,
                "target": target_stats,
            })

            # === All buffs ===
            player_buffs = probe_all_buffs(pm, mine, "player")
            target_buffs = probe_all_buffs(pm, target_ptr, "target") if target_ptr else None
            save_json("all_buffs.json", {
                "timestamp": timestamp,
                "player": player_buffs,
                "target": target_buffs,
            })

            # === Raw entity scan ===
            player_scan = probe_raw_entity_scan(pm, mine, "player")
            save_json("entity_scan.json", player_scan)

            if target_ptr:
                target_scan = probe_raw_entity_scan(pm, target_ptr, "target", scan_range=(0x100, 0x300))
                save_json("target_scan.json", target_scan)

            # === Abilities probe ===
            abilities = probe_abilities(pm, mine)
            save_json("abilities_scan.json", abilities)

            # === Nearby entities (runs less often — expensive) ===
            if scan_count % 5 == 1:
                nearby = probe_nearby_entities(pm, mine, ga_base)
                save_json("nearby_scan.json", nearby)

            # === Change tracking ===
            tracker.update(player_scan, "player")
            if target_ptr:
                tracker.update(probe_raw_entity_scan(pm, target_ptr, "target", scan_range=(0x100, 0x300)), "target")
            save_json("changelog.json", {
                "timestamp": timestamp,
                "total_changes": len(tracker.changes),
                "recent": tracker.changes[-50:],
            })

            # Status line
            p_name = player["name"] if player else "?"
            p_pos = player["position"] if player else None
            p_hdg = player_client.get("heading")
            t_name = target["name"] if target else "none"
            pos_str = f"({p_pos['x']:.0f}, {p_pos['z']:.0f})" if p_pos else "?"
            hdg_str = f"{p_hdg:.0f}°" if p_hdg is not None else "?"
            changes = len(tracker.changes)

            print(f"  [scan {scan_count:4d}] {p_name} @ {pos_str} hdg={hdg_str} | target={t_name} dist={dist} | {changes} changes logged")

            time.sleep(2)

    except KeyboardInterrupt:
        print(f"\n\nStopped after {scan_count} scans.")
        print(f"Results saved in: {PROBE_DIR}/")
        print(f"  snapshot.json        — Latest game state")
        print(f"  all_stats.json       — All {len(STAT_NAMES)} stat indices")
        print(f"  all_buffs.json       — Full buff details")
        print(f"  entity_scan.json     — Raw player entity fields")
        print(f"  target_scan.json     — Raw target entity fields")
        print(f"  abilities_scan.json  — ClientAbilities structure")
        print(f"  nearby_scan.json     — Entity list search")
        print(f"  changelog.json       — {len(tracker.changes)} field changes recorded")

    pm.close_process()


if __name__ == "__main__":
    main()
