"""
Offset probe for Monsters and Memories memory reader.
Walks the IL2CPP pointer chain step by step, printing the address and value
at each level so you can see exactly where things break.

Run from Windows (not WSL) with the game running:
    pip install pymem
    python probe_offsets.py
"""

import sys
import struct

try:
    import pymem
    import pymem.process
except ImportError:
    print("pymem not installed. Run: pip install pymem")
    sys.exit(1)

from memory_reader import (
    EntityOff, ClientOff, EntityBuffsOff, BuffRecordOff, IL2CPP,
    TargetHandlerOff, AntiTamperVector3Off, AntiTamperFloatOff,
    CLIENT_TYPEINFO_RVA,
)


# =========================================================================
# Helpers
# =========================================================================

PASS = "\033[92mOK\033[0m"
FAIL = "\033[91mFAIL\033[0m"
WARN = "\033[93mWARN\033[0m"
CYAN = "\033[96m"
RESET = "\033[0m"


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
    if not str_ptr:
        return ""
    try:
        length = pm.read_int(str_ptr + IL2CPP.STRING_LENGTH)
        if length == 0:
            return ""
        if length < 0 or length > 2048:
            return f"<bad length: {length}>"
        raw = pm.read_bytes(str_ptr + IL2CPP.STRING_CHARS, length * 2)
        return raw.decode("utf-16-le", errors="replace")
    except Exception as e:
        return f"<read error: {e}>"


def probe_ptr(pm, label, addr, offset, expect_nonzero=True):
    """Read a pointer at addr+offset, print result, return the value."""
    target = addr + offset
    val = read_ptr(pm, target)
    status = PASS if (val != 0) == expect_nonzero else FAIL
    print(f"  [{status}] {label:<40} @ 0x{target:X}  =>  0x{val:X}")
    return val


def probe_str(pm, label, addr, offset):
    """Read a string pointer at addr+offset, print the string."""
    str_ptr = read_ptr(pm, addr + offset)
    if not str_ptr:
        print(f"  [{FAIL}] {label:<40} @ 0x{addr + offset:X}  =>  NULL")
        return ""
    text = read_il2cpp_string(pm, str_ptr)
    status = PASS if text and not text.startswith("<") else WARN
    print(f"  [{status}] {label:<40} @ 0x{addr + offset:X}  =>  \"{text}\"")
    return text


def probe_int(pm, label, addr, offset):
    """Read a 32-bit int at addr+offset."""
    val = read_int(pm, addr + offset)
    print(f"  [{'--':^4}] {label:<40} @ 0x{addr + offset:X}  =>  {val}")
    return val


def probe_uint(pm, label, addr, offset):
    """Read a 32-bit uint at addr+offset."""
    val = read_uint(pm, addr + offset)
    print(f"  [{'--':^4}] {label:<40} @ 0x{addr + offset:X}  =>  {val}")
    return val


def probe_bool(pm, label, addr, offset):
    """Read a bool at addr+offset."""
    val = read_bool(pm, addr + offset)
    print(f"  [{'--':^4}] {label:<40} @ 0x{addr + offset:X}  =>  {val}")
    return val


def section(title):
    print(f"\n{CYAN}{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}{RESET}")


# =========================================================================
# Probe chain
# =========================================================================

def probe_typeinfo_chain(pm, ga_base):
    """Walk: GameAssembly.dll + RVA -> TypeInfo* -> Il2CppClass -> static_fields -> mine"""
    section("Step 1: TypeInfo RVA -> Il2CppClass")

    rva_addr = ga_base + CLIENT_TYPEINFO_RVA
    print(f"  GameAssembly.dll base:     0x{ga_base:X}")
    print(f"  CLIENT_TYPEINFO_RVA:       0x{CLIENT_TYPEINFO_RVA:X}")
    print(f"  TypeInfo pointer address:  0x{rva_addr:X}")

    il2cpp_class = probe_ptr(pm, "Il2CppClass*", rva_addr, 0)
    if not il2cpp_class:
        print(f"\n  [{FAIL}] Cannot continue — Il2CppClass pointer is NULL.")
        print(f"  The RVA 0x{CLIENT_TYPEINFO_RVA:X} may be wrong.")
        print(f"  Re-run Il2CppDumper and check script.json for Client_TypeInfo.")
        return 0

    section("Step 2: Il2CppClass -> static_fields")
    static_fields = probe_ptr(pm, "static_fields", il2cpp_class, IL2CPP.CLASS_STATIC_FIELDS)
    if not static_fields:
        print(f"\n  [{FAIL}] static_fields is NULL.")
        print(f"  Possible causes:")
        print(f"    - CLASS_STATIC_FIELDS offset (0x{IL2CPP.CLASS_STATIC_FIELDS:X}) is wrong for this Unity version")
        print(f"    - Class hasn't been initialized yet (not logged in?)")
        print(f"  Try scanning nearby offsets...")
        scan_static_fields(pm, il2cpp_class)
        return 0

    section("Step 3: static_fields -> Client.mine")
    mine = probe_ptr(pm, "Client.mine", static_fields, ClientOff.MINE_STATIC)
    if not mine:
        print(f"\n  [{FAIL}] Client.mine is NULL.")
        print(f"  Are you logged into a character? mine is null at character select.")
        return 0

    return mine


def scan_static_fields(pm, il2cpp_class):
    """Try nearby offsets for static_fields if the expected one failed."""
    print(f"\n  Scanning Il2CppClass for static_fields pointer (0x80-0xF0):")
    for off in range(0x80, 0xF8, 0x8):
        val = read_ptr(pm, il2cpp_class + off)
        if val and 0x10000 < val < 0x7FFFFFFFFFFF:
            # Try reading it as static_fields — if mine is there, we'll get a valid pointer
            test_mine = read_ptr(pm, val)
            marker = ""
            if test_mine and 0x10000 < test_mine < 0x7FFFFFFFFFFF:
                # Try reading entity name from test_mine
                test_name_ptr = read_ptr(pm, test_mine + EntityOff.NAME)
                if test_name_ptr:
                    test_name = read_il2cpp_string(pm, test_name_ptr)
                    if test_name and not test_name.startswith("<"):
                        marker = f"  <-- POSSIBLE MATCH! name=\"{test_name}\""
            print(f"    0x{off:03X}: 0x{val:X}{marker}")


def probe_entity(pm, label, entity_ptr):
    """Probe all entity fields."""
    section(f"{label} Entity Fields (@ 0x{entity_ptr:X})")

    probe_uint(pm, "Entity.id", entity_ptr, EntityOff.ID)
    probe_str(pm, "Entity.entityName", entity_ptr, EntityOff.NAME)
    probe_str(pm, "Entity.raceHID", entity_ptr, EntityOff.RACE_HID)
    probe_str(pm, "Entity.sexHID", entity_ptr, EntityOff.SEX_HID)
    probe_bool(pm, "Entity.isStunned", entity_ptr, EntityOff.IS_STUNNED)
    probe_bool(pm, "Entity.isFeared", entity_ptr, EntityOff.IS_FEARED)
    probe_bool(pm, "Entity.isCorpse", entity_ptr, EntityOff.IS_CORPSE)
    probe_bool(pm, "Entity.isHostile", entity_ptr, EntityOff.IS_HOSTILE)
    probe_bool(pm, "Entity.isCasting", entity_ptr, EntityOff.IS_CASTING)
    probe_bool(pm, "Entity.autoattacking", entity_ptr, EntityOff.AUTOATTACKING)
    probe_int(pm, "Entity.CurrentPosture", entity_ptr, EntityOff.POSTURE)

    # Position (AntiTamperVector3)
    vec_ptr = probe_ptr(pm, "Entity._localInterpolatedServerPos", entity_ptr, EntityOff.POSITION, expect_nonzero=False)
    if vec_ptr:
        for axis_name, axis_off in [("X", AntiTamperVector3Off.X), ("Y", AntiTamperVector3Off.Y), ("Z", AntiTamperVector3Off.Z)]:
            atf_ptr = read_ptr(pm, vec_ptr + axis_off)
            if atf_ptr:
                try:
                    val = pm.read_float(atf_ptr + AntiTamperFloatOff.PRIMARY)
                    print(f"  [{PASS}] {'Position.' + axis_name:<40} @ 0x{atf_ptr + AntiTamperFloatOff.PRIMARY:X}  =>  {val:.2f}")
                except Exception:
                    print(f"  [{FAIL}] {'Position.' + axis_name:<40} @ 0x{atf_ptr + AntiTamperFloatOff.PRIMARY:X}  =>  read error")
            else:
                print(f"  [{FAIL}] {'AntiTamperFloat._' + axis_name.lower():<40} @ 0x{vec_ptr + axis_off:X}  =>  NULL")


def probe_client_fields(pm, mine_ptr):
    """Probe Client-specific fields beyond Entity base."""
    section(f"Client Instance Fields (@ 0x{mine_ptr:X})")

    probe_str(pm, "Client.classHID", mine_ptr, ClientOff.CLASS_HID)
    probe_bool(pm, "Client.isFeignDeath", mine_ptr, ClientOff.IS_FEIGN_DEATH)
    probe_ptr(pm, "Client.autoFollowTarget", mine_ptr, ClientOff.AUTO_FOLLOW, expect_nonzero=False)
    probe_ptr(pm, "Client.inventory", mine_ptr, ClientOff.INVENTORY)
    probe_ptr(pm, "Client.Abilities", mine_ptr, ClientOff.ABILITIES)
    probe_ptr(pm, "Client.lastTarget (tab-cycle)", mine_ptr, ClientOff.LAST_TARGET, expect_nonzero=False)

    # Current target via TargetHandler
    handler = probe_ptr(pm, "Entity.TargetHandler", mine_ptr, EntityOff.TARGET_HANDLER)
    target_ptr = 0
    if handler:
        target_ptr = probe_ptr(pm, "TargetHandler._targetEntity", handler, TargetHandlerOff.TARGET_ENTITY, expect_nonzero=False)
    else:
        print(f"  [{FAIL}] No TargetHandler — cannot read current target")

    return target_ptr


def probe_stats(pm, label, entity_ptr):
    """Probe the EntityStats dictionary chain."""
    section(f"{label} Stats Chain")

    stats_ptr = probe_ptr(pm, "Entity._stats", entity_ptr, EntityOff.STATS)
    if not stats_ptr:
        return

    # EntityStats._stats dict is at offset 0x10
    dict_ptr = probe_ptr(pm, "EntityStats._stats (dict)", stats_ptr, 0x10)
    if not dict_ptr:
        return

    entries_arr = probe_ptr(pm, "Dictionary.entries[]", dict_ptr, IL2CPP.DICT_ENTRIES)
    count = probe_int(pm, "Dictionary.count", dict_ptr, IL2CPP.DICT_COUNT)

    if not entries_arr or count <= 0:
        print(f"  [{WARN}] Dictionary empty or entries null")
        return

    arr_length = probe_int(pm, "entries[].Length", entries_arr, IL2CPP.ARRAY_LENGTH)
    data_start = entries_arr + IL2CPP.ARRAY_DATA

    print(f"\n  Scanning first {min(count, 10)} stat entries (entry size=0x{IL2CPP.ENTRY_SIZE:X}):")
    from memory_reader import GameMemoryReader as _GMR
    from game_data import Stat

    stat_names = {v: k for k, v in vars(Stat).items() if isinstance(v, int)}

    found = 0
    for i in range(min(count + 5, arr_length, 64)):
        entry_base = data_start + (i * IL2CPP.ENTRY_SIZE)
        hash_code = read_int(pm, entry_base + IL2CPP.ENTRY_HASHCODE)
        if hash_code < 0:
            continue

        key = read_int(pm, entry_base + IL2CPP.ENTRY_KEY)
        obs_ptr = read_ptr(pm, entry_base + IL2CPP.ENTRY_VALUE)
        val = read_int(pm, obs_ptr + 0x10) if obs_ptr else 0

        stat_label = stat_names.get(key, f"UNKNOWN_{key}")
        print(f"    entry[{i:2d}] key={key:2d} ({stat_label:<16}) obs=0x{obs_ptr:X}  value={val}")
        found += 1
        if found >= count:
            break

    if found == 0:
        print(f"  [{WARN}] No valid entries found — Entry size may be wrong")
        print(f"  Try dumping raw entry bytes to check alignment:")
        raw = pm.read_bytes(data_start, min(0x60, arr_length * IL2CPP.ENTRY_SIZE))
        hex_dump(raw, data_start)


def probe_buffs(pm, label, entity_ptr):
    """Probe the EntityBuffs dictionary chain."""
    section(f"{label} Buffs Chain")

    buffs_obj = probe_ptr(pm, "Entity.Buffs", entity_ptr, EntityOff.BUFFS)
    if not buffs_obj:
        print(f"  [{WARN}] No EntityBuffs object — entity may not have buffs loaded")
        return

    dict_ptr = probe_ptr(pm, "EntityBuffs._buffs (dict)", buffs_obj, EntityBuffsOff.BUFFS_DICT)
    if not dict_ptr:
        return

    entries_arr = probe_ptr(pm, "Dictionary.entries[]", dict_ptr, IL2CPP.DICT_ENTRIES)
    count = probe_int(pm, "Dictionary.count", dict_ptr, IL2CPP.DICT_COUNT)

    if not entries_arr:
        return

    if count <= 0:
        print(f"  [{'--':^4}] No active buffs")
        return

    arr_length = probe_int(pm, "entries[].Length", entries_arr, IL2CPP.ARRAY_LENGTH)
    data_start = entries_arr + IL2CPP.ARRAY_DATA

    print(f"\n  Reading {count} buff entries:")
    found = 0
    for i in range(min(count + 5, arr_length, 128)):
        entry_base = data_start + (i * IL2CPP.ENTRY_SIZE)
        hash_code = read_int(pm, entry_base + IL2CPP.ENTRY_HASHCODE)
        if hash_code < 0:
            continue

        key = read_uint(pm, entry_base + IL2CPP.ENTRY_KEY)
        buff_ptr = read_ptr(pm, entry_base + IL2CPP.ENTRY_VALUE)

        if not buff_ptr:
            print(f"    entry[{i}] key={key}  buff_ptr=NULL")
            continue

        buff_name = read_il2cpp_string(pm, read_ptr(pm, buff_ptr + BuffRecordOff.BUFF_NAME))
        buff_type = read_il2cpp_string(pm, read_ptr(pm, buff_ptr + BuffRecordOff.TYPE))
        category = read_il2cpp_string(pm, read_ptr(pm, buff_ptr + BuffRecordOff.CATEGORY_HID))
        stacks = read_ushort(pm, buff_ptr + BuffRecordOff.STACKS)
        duration = read_uint(pm, buff_ptr + BuffRecordOff.DURATION_MS)

        status = PASS
        if not buff_name or buff_name.startswith("<"):
            status = WARN

        print(f"    [{status}] entry[{i}] \"{buff_name}\" type=\"{buff_type}\" "
              f"cat=\"{category}\" stacks={stacks} dur={duration}ms")

        found += 1
        if found >= count:
            break

    if found == 0 and count > 0:
        print(f"\n  [{FAIL}] Expected {count} buffs but found 0 valid entries")
        print(f"  Entry size (0x{IL2CPP.ENTRY_SIZE:X}) may be wrong. Dumping raw bytes:")
        raw = pm.read_bytes(data_start, min(0x90, arr_length * IL2CPP.ENTRY_SIZE))
        hex_dump(raw, data_start)


def hex_dump(data, base_addr, width=16):
    """Print a hex dump of raw bytes."""
    for i in range(0, len(data), width):
        chunk = data[i:i+width]
        hex_part = " ".join(f"{b:02X}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        print(f"    0x{base_addr + i:X}  {hex_part:<{width*3}}  {ascii_part}")


def probe_string_sanity(pm, mine_ptr):
    """Quick sanity check — scan nearby offsets for valid-looking strings."""
    section("String Scan (validating Entity field alignment)")
    print(f"  Scanning 0x100-0x160 for Il2CppString* pointers:")
    for off in range(0x100, 0x168, 0x8):
        ptr = read_ptr(pm, mine_ptr + off)
        if ptr and 0x10000 < ptr < 0x7FFFFFFFFFFF:
            text = read_il2cpp_string(pm, ptr)
            if text and not text.startswith("<") and len(text) < 100:
                print(f"    0x{off:03X}: \"{text}\"")
            else:
                print(f"    0x{off:03X}: (pointer 0x{ptr:X}, not a valid string)")
        else:
            val = read_ulong(pm, mine_ptr + off)
            if val != 0:
                print(f"    0x{off:03X}: (raw value: 0x{val:X} / {val})")


def probe_all_strings(pm, entity_ptr):
    """Scan all 8-byte-aligned offsets on the Client object for IL2CPP strings.

    This helps discover unmapped fields like zone name.
    Scans from 0x100 to 0x600 (Client extends Entity, fields go up to ~0x4D8+).
    """
    section("String Scan (all string-like fields on Client object)")
    print(f"  Scanning 0x100..0x600 on entity @ 0x{entity_ptr:X}")
    print(f"  Looking for valid Il2CppString pointers...\n")

    found = 0
    for offset in range(0x100, 0x600, 0x8):
        ptr = read_ptr(pm, entity_ptr + offset)
        if not ptr or ptr < 0x10000:
            continue

        # Check if this looks like an IL2CPP string:
        # - Il2CppString has a class pointer at 0x0, length at 0x10, chars at 0x14
        try:
            length = pm.read_int(ptr + IL2CPP.STRING_LENGTH)
        except Exception:
            continue

        if length <= 0 or length > 256:
            continue

        try:
            raw = pm.read_bytes(ptr + IL2CPP.STRING_CHARS, length * 2)
            text = raw.decode("utf-16-le", errors="replace")
        except Exception:
            continue

        # Filter: must be printable ASCII-ish
        if not text or not all(c.isprintable() or c == ' ' for c in text):
            continue

        print(f"  0x{offset:03X}  =>  \"{text}\"")
        found += 1

    if found == 0:
        print(f"  (no valid strings found in scan range)")
    else:
        print(f"\n  Found {found} string fields.")
    print(f"  Look for zone-related strings (e.g. 'Night Harbor', 'NightHarbor', etc.)")


# =========================================================================
# Main
# =========================================================================

def main():
    print(f"\n{CYAN}Monsters & Memories — Offset Probe{RESET}")
    print(f"{'=' * 60}\n")

    # Connect
    try:
        pm = pymem.Pymem("mnm.exe")
    except Exception as e:
        print(f"[{FAIL}] Could not open mnm.exe: {e}")
        print(f"  Make sure the game is running.")
        sys.exit(1)

    print(f"[{PASS}] Attached to mnm.exe (PID: {pm.process_id})")

    ga_module = pymem.process.module_from_name(pm.process_handle, "GameAssembly.dll")
    if not ga_module:
        print(f"[{FAIL}] GameAssembly.dll not found in process")
        sys.exit(1)

    ga_base = ga_module.lpBaseOfDll
    print(f"[{PASS}] GameAssembly.dll base: 0x{ga_base:X}")
    print(f"[{PASS}] Module size: {ga_module.SizeOfImage / 1024 / 1024:.1f} MB")

    # Step 1-3: TypeInfo -> Class -> static_fields -> mine
    mine = probe_typeinfo_chain(pm, ga_base)
    if not mine:
        print(f"\n[{FAIL}] Could not resolve Client.mine — stopping here.")
        pm.close_process()
        sys.exit(1)

    # Step 4: Entity fields on player
    probe_entity(pm, "Player", mine)

    # Step 5: String scan for field alignment verification
    probe_string_sanity(pm, mine)

    # Step 6: Client-specific fields
    target_ptr = probe_client_fields(pm, mine)

    # Step 7: Player stats
    probe_stats(pm, "Player", mine)

    # Step 8: Player buffs
    probe_buffs(pm, "Player", mine)

    # Step 9: Target (if any)
    if target_ptr:
        probe_entity(pm, "Target", target_ptr)
        probe_stats(pm, "Target", target_ptr)
        probe_buffs(pm, "Target", target_ptr)
    else:
        section("Target")
        print(f"  [{'--':^4}] No target selected — target probes skipped")
        print(f"  Tab-target something in game and re-run to test target chain")

    # Step 10: Scan for all string fields on Client (to find zone name, etc.)
    probe_all_strings(pm, mine)

    # Summary
    section("Summary")
    print(f"  GameAssembly.dll:   0x{ga_base:X}")
    print(f"  Client.mine:        0x{mine:X}")
    if target_ptr:
        print(f"  Current target:     0x{target_ptr:X}")
    print(f"\n  If strings look wrong, entity offsets need re-checking against dump.cs.")
    print(f"  If stats show all zeros, ObservableValue layout may differ.")
    print(f"  If buffs fail, Dictionary Entry size (0x{IL2CPP.ENTRY_SIZE:X}) may need adjustment.\n")

    pm.close_process()


if __name__ == "__main__":
    main()
