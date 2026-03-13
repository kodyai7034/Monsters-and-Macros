"""
Rotation/Heading probe for Monsters and Memories.
Scans Entity fields near the known position offset (0x280) for rotation data.

Rotation could be stored as:
  - A single float (heading/yaw in degrees or radians)
  - An AntiTamperFloat (like position components)
  - An AntiTamperVector3 (Euler angles)
  - A Quaternion (x, y, z, w floats)
  - A Transform reference with rotation

Run from Windows (not WSL) with the game running:
    pip install pymem
    python probe_rotation.py

Instructions:
  1. Run while standing still, note the values
  2. Turn your character ~90 degrees
  3. Run again and compare — the rotation field will have changed
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
    EntityOff, ClientOff, IL2CPP,
    AntiTamperVector3Off, AntiTamperFloatOff,
    CLIENT_TYPEINFO_RVA,
)

CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"


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


def read_antitamper_float(pm, atf_ptr):
    """Read an AntiTamperFloat — the actual value is at offset 0x10."""
    if not atf_ptr or atf_ptr < 0x10000:
        return None
    return read_float(pm, atf_ptr + AntiTamperFloatOff.PRIMARY)


def read_antitamper_vec3(pm, vec_ptr):
    """Read an AntiTamperVector3 — 3 AntiTamperFloat pointers."""
    if not vec_ptr or vec_ptr < 0x10000:
        return None
    x_ptr = read_ptr(pm, vec_ptr + AntiTamperVector3Off.X)
    y_ptr = read_ptr(pm, vec_ptr + AntiTamperVector3Off.Y)
    z_ptr = read_ptr(pm, vec_ptr + AntiTamperVector3Off.Z)
    x = read_antitamper_float(pm, x_ptr)
    y = read_antitamper_float(pm, y_ptr)
    z = read_antitamper_float(pm, z_ptr)
    return (x, y, z)


def get_mine(pm):
    """Resolve Client.mine pointer."""
    ga_module = pymem.process.module_from_name(pm.process_handle, "GameAssembly.dll")
    if not ga_module:
        print(f"[{RED}FAIL{RESET}] GameAssembly.dll not found")
        return None, None

    ga_base = ga_module.lpBaseOfDll
    rva_addr = ga_base + CLIENT_TYPEINFO_RVA
    il2cpp_class = read_ptr(pm, rva_addr)
    if not il2cpp_class:
        print(f"[{RED}FAIL{RESET}] Il2CppClass pointer is NULL")
        return None, ga_base

    static_fields = read_ptr(pm, il2cpp_class + IL2CPP.CLASS_STATIC_FIELDS)
    if not static_fields:
        print(f"[{RED}FAIL{RESET}] static_fields is NULL (not logged in?)")
        return None, ga_base

    mine = read_ptr(pm, static_fields + ClientOff.MINE_STATIC)
    if not mine:
        print(f"[{RED}FAIL{RESET}] Client.mine is NULL (not on a character?)")
        return None, ga_base

    return mine, ga_base


def scan_raw_floats(pm, entity_ptr):
    """Scan raw floats around position offset for rotation candidates.

    Rotation values are typically:
      - Degrees: 0-360 (heading)
      - Radians: -PI to PI or 0 to 2*PI
      - Quaternion: -1.0 to 1.0
    """
    import math

    print(f"\n{CYAN}{'=' * 70}")
    print(f"  Raw Float Scan around Position (0x280)")
    print(f"  Scanning 0x200..0x340 at 4-byte intervals")
    print(f"{'=' * 70}{RESET}")

    # Read known position for reference
    vec_ptr = read_ptr(pm, entity_ptr + EntityOff.POSITION)
    if vec_ptr:
        pos = read_antitamper_vec3(pm, vec_ptr)
        if pos:
            print(f"\n  Known position: ({pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f})")

    print(f"\n  {'Offset':<10} {'Float':<16} {'Int':<14} {'Notes'}")
    print(f"  {'-'*10} {'-'*16} {'-'*14} {'-'*30}")

    for off in range(0x200, 0x340, 0x4):
        fval = read_float(pm, entity_ptr + off)
        ival = read_int(pm, entity_ptr + off)

        if fval is None:
            continue

        notes = []

        # Flag known fields
        if off == EntityOff.POSITION:
            notes.append("** POSITION (AntiTamperVec3 ptr)")
        elif off == EntityOff.POSTURE:
            notes.append(f"** POSTURE ({ival})")

        # Flag rotation candidates
        if fval is not None and not (fval != fval):  # not NaN
            if -3.15 <= fval <= 3.15 and abs(fval) > 0.001:
                notes.append("possible radian")
            if 0 <= fval <= 360 and abs(fval) > 0.1:
                notes.append("possible degree")
            if -1.0 <= fval <= 1.0 and abs(fval) > 0.001:
                notes.append("possible quat component")

        # Only print if non-zero or at a known offset
        if fval == 0.0 and ival == 0 and not notes:
            continue

        notes_str = f"  {YELLOW}{', '.join(notes)}{RESET}" if notes else ""
        print(f"  0x{off:03X}     {fval:<16.6f} {ival:<14}{notes_str}")


def scan_antitamper_candidates(pm, entity_ptr):
    """Scan pointer-aligned offsets for AntiTamperVector3/Float-like structures.

    Since position uses AntiTamperVector3, rotation might too.
    An AntiTamperVector3 pointer would point to a heap object containing
    3 AntiTamperFloat pointers.
    """
    print(f"\n{CYAN}{'=' * 70}")
    print(f"  AntiTamper Pointer Scan (0x260..0x2F0)")
    print(f"  Looking for pointers that resolve to float-like values")
    print(f"{'=' * 70}{RESET}\n")

    for off in range(0x260, 0x2F0, 0x8):
        ptr = read_ptr(pm, entity_ptr + off)
        if not ptr or ptr < 0x10000:
            continue

        label = ""
        if off == EntityOff.POSITION:
            label = " ** KNOWN: _localInterpolatedServerPosition"

        # Try reading as AntiTamperVector3 (3 pointer refs to AntiTamperFloat)
        vec_result = read_antitamper_vec3(pm, ptr)
        if vec_result and all(v is not None for v in vec_result):
            x, y, z = vec_result
            # Check if values are reasonable for rotation
            is_rotation = all(-400 < v < 400 for v in vec_result)
            marker = f"{GREEN}ROTATION CANDIDATE{RESET}" if is_rotation else ""
            print(f"  0x{off:03X}  -> AntiTamperVec3: ({x:.4f}, {y:.4f}, {z:.4f})  {marker}{label}")
            continue

        # Try reading as single AntiTamperFloat
        atf_val = read_antitamper_float(pm, ptr)
        if atf_val is not None and -1000 < atf_val < 1000:
            print(f"  0x{off:03X}  -> AntiTamperFloat: {atf_val:.4f}{label}")
            continue

        # Just a pointer to something else
        print(f"  0x{off:03X}  -> ptr 0x{ptr:X} (not AntiTamper){label}")


def scan_transform(pm, entity_ptr):
    """Look for Unity Transform reference which would have rotation.

    In IL2CPP, MonoBehaviour has a cached transform. Entity likely extends
    MonoBehaviour, so transform might be accessible through the base class.
    MonoBehaviour -> Component -> transform at some early offset.

    Unity Component.transform is typically accessed via native method,
    but the cached _transform field is often at offset 0x10-0x30 in the
    managed object.
    """
    print(f"\n{CYAN}{'=' * 70}")
    print(f"  Unity Transform Search (early offsets 0x10..0x80)")
    print(f"  Looking for cached Transform reference")
    print(f"{'=' * 70}{RESET}\n")

    for off in range(0x10, 0x80, 0x8):
        ptr = read_ptr(pm, entity_ptr + off)
        if not ptr or ptr < 0x10000:
            continue

        # A Unity Transform stores localPosition, localRotation, localScale
        # Try reading at typical Transform offsets for rotation quaternion
        # In some Unity builds, Transform data is at offsets like 0x38 (position), 0x48 (rotation)
        # But these are native objects, layout varies significantly

        print(f"  0x{off:03X}  -> ptr 0x{ptr:X}")

        # Try reading as floats at various sub-offsets
        interesting = False
        for sub_off in [0x10, 0x18, 0x20, 0x28, 0x30, 0x38, 0x40, 0x48, 0x50]:
            fval = read_float(pm, ptr + sub_off)
            if fval is not None and abs(fval) > 0.001 and abs(fval) < 400:
                if not interesting:
                    print(f"         Sub-offsets with valid floats:")
                    interesting = True
                print(f"           +0x{sub_off:02X}: {fval:.4f}")


def scan_wide_for_rotation(pm, entity_ptr):
    """Wider scan for any field that might be rotation.

    Scans 0x288..0x2E0 (after position + posture, before buffs at 0x2D0)
    as raw 8-byte values, trying to interpret each as:
    - Direct float (4 bytes)
    - Pointer to AntiTamperFloat
    - Pointer to AntiTamperVector3
    """
    print(f"\n{CYAN}{'=' * 70}")
    print(f"  Focused Scan: Fields between Position (0x280) and Buffs (0x2D0)")
    print(f"  These are the most likely locations for rotation/heading")
    print(f"{'=' * 70}{RESET}\n")

    for off in range(0x288, 0x2D0, 0x4):
        # Read as 4-byte float
        fval = read_float(pm, entity_ptr + off)
        # Read as 8-byte pointer (only on 8-byte boundaries)
        ptr = read_ptr(pm, entity_ptr + off) if off % 8 == 0 else 0

        notes = []
        if off == EntityOff.POSTURE:
            ival = read_int(pm, entity_ptr + off)
            notes.append(f"KNOWN: CurrentPosture = {ival}")

        # Check direct float
        if fval is not None and fval != 0.0 and not (fval != fval):
            if -6.3 <= fval <= 6.3 and abs(fval) > 0.001:
                notes.append(f"float={fval:.6f} (RADIAN RANGE)")
            elif 0 < fval <= 360:
                notes.append(f"float={fval:.6f} (DEGREE RANGE)")
            elif -1.0 <= fval <= 1.0 and abs(fval) > 0.001:
                notes.append(f"float={fval:.6f} (QUATERNION RANGE)")
            else:
                notes.append(f"float={fval:.6f}")

        # Check pointer (8-byte boundary)
        if off % 8 == 0 and ptr and ptr > 0x10000:
            atf = read_antitamper_float(pm, ptr)
            if atf is not None and abs(atf) < 400:
                notes.append(f"ATF ptr -> {atf:.4f}")

            vec = read_antitamper_vec3(pm, ptr)
            if vec and all(v is not None for v in vec):
                notes.append(f"ATV3 ptr -> ({vec[0]:.4f}, {vec[1]:.4f}, {vec[2]:.4f})")

        if notes:
            print(f"  0x{off:03X}:  {' | '.join(notes)}")


def main():
    print(f"\n{CYAN}Monsters & Memories — Rotation/Heading Probe{RESET}")
    print(f"{'=' * 70}")
    print(f"  Run this twice: once facing north, once after turning ~90 degrees.")
    print(f"  Compare the output to find which field changes = rotation.")
    print(f"{'=' * 70}\n")

    try:
        pm = pymem.Pymem("mnm.exe")
    except Exception as e:
        print(f"[{RED}FAIL{RESET}] Could not open mnm.exe: {e}")
        sys.exit(1)

    print(f"[{GREEN}OK{RESET}] Attached to mnm.exe (PID: {pm.process_id})")

    mine, ga_base = get_mine(pm)
    if not mine:
        pm.close_process()
        sys.exit(1)

    print(f"[{GREEN}OK{RESET}] Client.mine: 0x{mine:X}")

    # Run all scan methods
    scan_raw_floats(pm, mine)
    scan_antitamper_candidates(pm, mine)
    scan_wide_for_rotation(pm, mine)
    scan_transform(pm, mine)

    print(f"\n{CYAN}{'=' * 70}")
    print(f"  NEXT STEPS")
    print(f"{'=' * 70}{RESET}")
    print(f"  1. Turn your character ~90 degrees in game")
    print(f"  2. Run this script again")
    print(f"  3. Compare the two outputs — the rotation field will change")
    print(f"  4. Values in radian range (-3.14 to 3.14) are most likely heading")
    print()

    pm.close_process()


if __name__ == "__main__":
    main()
