"""
Live rotation probe — polls continuously and highlights changing values.

Stand still, run this script, then turn your character in-game.
Values that change will be highlighted in green.

Run from Windows:
    python probe_rotation_live.py
"""

import sys
import time
import os

try:
    import pymem
    import pymem.process
except ImportError:
    print("pymem not installed. Run: pip install pymem")
    sys.exit(1)

from memory_reader import (
    EntityOff, ClientOff, IL2CPP,
    AntiTamperVector3Off, AntiTamperFloatOff,
    CLIENT_TYPEINFO_RVA,
)

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"


def read_ptr(pm, addr):
    try:
        return pm.read_longlong(addr)
    except Exception:
        return 0


def read_float(pm, addr):
    try:
        return pm.read_float(addr)
    except Exception:
        return None


def read_int(pm, addr):
    try:
        return pm.read_int(addr)
    except Exception:
        return 0


def read_antitamper_float(pm, ptr):
    if not ptr or ptr < 0x10000:
        return None
    return read_float(pm, ptr + AntiTamperFloatOff.PRIMARY)


def get_mine(pm):
    ga_module = pymem.process.module_from_name(pm.process_handle, "GameAssembly.dll")
    if not ga_module:
        return None
    ga_base = ga_module.lpBaseOfDll
    il2cpp_class = read_ptr(pm, ga_base + CLIENT_TYPEINFO_RVA)
    if not il2cpp_class:
        return None
    static_fields = read_ptr(pm, il2cpp_class + IL2CPP.CLASS_STATIC_FIELDS)
    if not static_fields:
        return None
    return read_ptr(pm, static_fields + ClientOff.MINE_STATIC)


def collect_values(pm, entity_ptr):
    """Collect all candidate rotation values from the entity."""
    values = {}

    # 1. Raw floats on entity object (wide scan 0x100..0x500)
    for off in range(0x100, 0x500, 0x4):
        fval = read_float(pm, entity_ptr + off)
        if fval is not None and not (fval != fval):  # not NaN
            values[f"raw_0x{off:03X}"] = fval

    # 2. AntiTamperFloat pointers (8-byte aligned, 0x200..0x400)
    for off in range(0x200, 0x400, 0x8):
        ptr = read_ptr(pm, entity_ptr + off)
        if ptr and ptr > 0x10000:
            atf = read_antitamper_float(pm, ptr)
            if atf is not None and not (atf != atf):
                values[f"atf_0x{off:03X}"] = atf

    # 3. Pointer at 0x010 (possible Transform) — deeper scan
    transform_ptr = read_ptr(pm, entity_ptr + 0x10)
    if transform_ptr and transform_ptr > 0x10000:
        for sub in range(0x00, 0x80, 0x4):
            fval = read_float(pm, transform_ptr + sub)
            if fval is not None and not (fval != fval):
                values[f"t010+0x{sub:02X}"] = fval

    # 4. Pointer at 0x018 — deeper scan
    ptr_18 = read_ptr(pm, entity_ptr + 0x18)
    if ptr_18 and ptr_18 > 0x10000:
        for sub in range(0x00, 0x80, 0x4):
            fval = read_float(pm, ptr_18 + sub)
            if fval is not None and not (fval != fval):
                values[f"t018+0x{sub:02X}"] = fval

    # 5. Pointer at 0x020 — deeper scan
    ptr_20 = read_ptr(pm, entity_ptr + 0x20)
    if ptr_20 and ptr_20 > 0x10000:
        for sub in range(0x00, 0x80, 0x4):
            fval = read_float(pm, ptr_20 + sub)
            if fval is not None and not (fval != fval):
                values[f"t020+0x{sub:02X}"] = fval

    # 6. Two-level pointer chase from 0x298 and 0x2A0 (unknown ptrs near position)
    for base_off in [0x298, 0x2A0]:
        ptr = read_ptr(pm, entity_ptr + base_off)
        if ptr and ptr > 0x10000:
            for sub in range(0x00, 0x40, 0x4):
                fval = read_float(pm, ptr + sub)
                if fval is not None and not (fval != fval):
                    values[f"p{base_off:03X}+0x{sub:02X}"] = fval

    return values


def main():
    print(f"\n{CYAN}Monsters & Memories — LIVE Rotation Probe{RESET}")
    print(f"{'=' * 70}")
    print(f"  Polls every 0.5s and shows values that CHANGE when you turn.")
    print(f"  Stand still, then turn your character.")
    print(f"  Press Ctrl+C to stop.")
    print(f"{'=' * 70}\n")

    try:
        pm = pymem.Pymem("mnm.exe")
    except Exception as e:
        print(f"[{RED}FAIL{RESET}] Could not open mnm.exe: {e}")
        sys.exit(1)

    mine = get_mine(pm)
    if not mine:
        print(f"[{RED}FAIL{RESET}] Could not resolve Client.mine")
        pm.close_process()
        sys.exit(1)

    print(f"[{GREEN}OK{RESET}] Client.mine: 0x{mine:X}")
    print(f"\nTaking baseline snapshot... stand still!")
    time.sleep(1.0)

    baseline = collect_values(pm, mine)
    print(f"Captured {len(baseline)} values. Now turn your character!\n")

    # Track which fields have ever changed and by how much
    changed_fields = {}
    prev_values = dict(baseline)

    try:
        tick = 0
        while True:
            time.sleep(0.5)
            tick += 1

            current = collect_values(pm, mine)

            # Find fields that changed from baseline
            newly_changed = []
            for key, val in current.items():
                if key in baseline:
                    diff = abs(val - baseline[key])
                    if diff > 0.0001:
                        if key not in changed_fields or abs(val - prev_values.get(key, val)) > 0.0001:
                            newly_changed.append(key)
                        changed_fields[key] = val

            prev_values = dict(current)

            # Display changed fields
            if changed_fields:
                # Clear screen on Windows
                os.system('cls' if os.name == 'nt' else 'clear')
                print(f"{CYAN}Monsters & Memories — LIVE Rotation Probe (tick {tick}){RESET}")
                print(f"Press Ctrl+C to stop.\n")
                print(f"{'Field':<20} {'Baseline':<14} {'Current':<14} {'Delta':<14} {'Notes'}")
                print(f"{'-'*20} {'-'*14} {'-'*14} {'-'*14} {'-'*20}")

                # Sort by absolute delta descending
                sorted_fields = sorted(
                    changed_fields.keys(),
                    key=lambda k: abs(current.get(k, 0) - baseline.get(k, 0)),
                    reverse=True
                )

                for key in sorted_fields[:30]:  # show top 30 changed
                    base_val = baseline.get(key, 0)
                    cur_val = current.get(key, 0)
                    delta = cur_val - base_val

                    notes = []
                    if -6.3 <= cur_val <= 6.3 and abs(cur_val) > 0.001:
                        notes.append("radian?")
                    if 0 < cur_val <= 360:
                        notes.append("degree?")
                    if -1.0 <= cur_val <= 1.0 and abs(cur_val) > 0.001:
                        notes.append("quat?")

                    # Highlight rotation-plausible changes
                    color = GREEN if notes else ""
                    reset = RESET if notes else ""

                    print(f"{color}{key:<20} {base_val:<14.4f} {cur_val:<14.4f} {delta:<+14.4f} {', '.join(notes)}{reset}")

                print(f"\n  Total changed fields: {len(changed_fields)}")
                if not newly_changed and tick > 4:
                    print(f"\n  {YELLOW}No changes detected yet — try turning your character!{RESET}")

            elif tick % 4 == 0:
                print(f"  ... waiting for changes (tick {tick}) — turn your character! ...")

    except KeyboardInterrupt:
        print(f"\n\n{CYAN}{'=' * 70}")
        print(f"  SUMMARY — Fields that changed")
        print(f"{'=' * 70}{RESET}\n")

        if not changed_fields:
            print(f"  {YELLOW}No fields changed! Rotation may not be on the Entity object.{RESET}")
            print(f"  Try: re-run Il2CppDumper and search dump.cs for rotation/heading fields.")
        else:
            final = collect_values(pm, mine)
            print(f"{'Field':<20} {'Baseline':<14} {'Final':<14} {'Delta':<14}")
            print(f"{'-'*20} {'-'*14} {'-'*14} {'-'*14}")

            sorted_fields = sorted(
                changed_fields.keys(),
                key=lambda k: abs(final.get(k, 0) - baseline.get(k, 0)),
                reverse=True
            )

            for key in sorted_fields:
                base_val = baseline.get(key, 0)
                fin_val = final.get(key, 0)
                delta = fin_val - base_val
                print(f"{key:<20} {base_val:<14.4f} {fin_val:<14.4f} {delta:<+14.4f}")

    pm.close_process()


if __name__ == "__main__":
    main()
