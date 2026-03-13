"""
Probe ZoneController to find the current zone name.

ZoneController is at TypeInfo RVA 0x0542B5B0.
This script resolves the singleton instance and scans its fields for strings.

Run on Windows with the game running:
    python probe_zone.py
"""

import sys

try:
    import pymem
    import pymem.process
except ImportError:
    print("pymem not installed. Run: pip install pymem")
    sys.exit(1)

from memory_reader import IL2CPP

PROCESS_NAME = "mnm.exe"
MODULE_NAME = "GameAssembly.dll"
ZONE_CONTROLLER_RVA = 0x0542B5B0

# Il2CppClass offsets
CLASS_NAME_OFF = 0x10
CLASS_STATIC_FIELDS_OFF = 0xB8  # void* static_fields


def read_ptr(pm, addr):
    try:
        return pm.read_longlong(addr)
    except Exception:
        return 0


def read_cstring(pm, addr, max_len=128):
    if not addr or addr < 0x10000:
        return ""
    try:
        raw = pm.read_bytes(addr, max_len)
        null_idx = raw.find(b'\x00')
        if null_idx >= 0:
            raw = raw[:null_idx]
        return raw.decode("utf-8", errors="replace")
    except Exception:
        return ""


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


def main():
    print(f"\nZoneController Probe")
    print(f"{'=' * 60}\n")

    try:
        pm = pymem.Pymem(PROCESS_NAME)
    except Exception as e:
        print(f"Could not open {PROCESS_NAME}: {e}")
        sys.exit(1)

    ga_module = pymem.process.module_from_name(pm.process_handle, MODULE_NAME)
    if not ga_module:
        print(f"Could not find {MODULE_NAME}")
        sys.exit(1)

    ga_base = ga_module.lpBaseOfDll
    print(f"GameAssembly.dll base: 0x{ga_base:X}")

    # Step 1: TypeInfo -> Il2CppClass
    typeinfo_addr = ga_base + ZONE_CONTROLLER_RVA
    class_ptr = read_ptr(pm, typeinfo_addr)
    print(f"ZoneController TypeInfo @ 0x{typeinfo_addr:X} => Il2CppClass* 0x{class_ptr:X}")

    if not class_ptr:
        print("FAIL: Could not read Il2CppClass pointer")
        sys.exit(1)

    # Verify class name
    name_ptr = read_ptr(pm, class_ptr + CLASS_NAME_OFF)
    name = read_cstring(pm, name_ptr)
    print(f"Class name: {name}")

    # Step 2: Get static_fields
    static_fields = read_ptr(pm, class_ptr + CLASS_STATIC_FIELDS_OFF)
    print(f"static_fields: 0x{static_fields:X}")

    if not static_fields:
        print("FAIL: No static_fields found")
        sys.exit(1)

    # Step 3: Scan static fields for the singleton instance
    # Typically static_fields[0] or [1] is the instance pointer
    print(f"\nScanning static fields for singleton instance:")
    instance_ptr = 0
    for off in range(0x0, 0x40, 0x8):
        val = read_ptr(pm, static_fields + off)
        label = f"  static_fields+0x{off:X}"
        if val and val > 0x10000:
            # Check if this looks like an object (has a class pointer at offset 0)
            maybe_class = read_ptr(pm, val)
            if maybe_class and maybe_class > 0x10000:
                maybe_name_ptr = read_ptr(pm, maybe_class + CLASS_NAME_OFF)
                maybe_name = read_cstring(pm, maybe_name_ptr)
                print(f"{label} => 0x{val:X}  (object type: {maybe_name})")
                if maybe_name == "ZoneController":
                    instance_ptr = val
            else:
                print(f"{label} => 0x{val:X}")
        else:
            print(f"{label} => 0x{val:X}")

    if not instance_ptr:
        # Maybe it's a MonoBehaviour and uses a different pattern
        # Try static_fields+0x0 as the instance directly
        print("\nNo ZoneController instance found in static fields.")
        print("Trying static_fields+0x0 as instance directly...")
        instance_ptr = read_ptr(pm, static_fields)
        if not instance_ptr:
            print("FAIL: Could not find ZoneController instance")
            sys.exit(1)

    print(f"\nZoneController instance: 0x{instance_ptr:X}")

    # Step 4: Scan instance fields for strings
    print(f"\nScanning instance fields for strings (0x10..0x200):\n")
    for off in range(0x10, 0x200, 0x8):
        ptr = read_ptr(pm, instance_ptr + off)
        if not ptr or ptr < 0x10000:
            continue

        # Try as IL2CPP string (UTF-16)
        text = read_il2cpp_string(pm, ptr)
        if text and len(text) >= 1 and all(c.isprintable() or c == ' ' for c in text):
            print(f"  0x{off:03X}  =>  \"{text}\"  (Il2CppString)")
            continue

        # Try as pointer to an object that might contain strings
        # (e.g., ZoneRecord with a zoneName field)
        inner_class = read_ptr(pm, ptr)
        if inner_class and inner_class > 0x10000:
            inner_name_ptr = read_ptr(pm, inner_class + CLASS_NAME_OFF)
            inner_name = read_cstring(pm, inner_name_ptr)
            if inner_name and len(inner_name) >= 2 and inner_name[0].isalpha():
                print(f"  0x{off:03X}  =>  0x{ptr:X}  (object type: {inner_name})")
                # If it's a ZoneRecord or similar, scan its fields too
                if "zone" in inner_name.lower() or "record" in inner_name.lower():
                    print(f"         Scanning {inner_name} fields:")
                    for inner_off in range(0x10, 0x80, 0x8):
                        inner_ptr = read_ptr(pm, ptr + inner_off)
                        if not inner_ptr or inner_ptr < 0x10000:
                            continue
                        inner_text = read_il2cpp_string(pm, inner_ptr)
                        if inner_text and all(c.isprintable() or c == ' ' for c in inner_text):
                            print(f"           0x{inner_off:03X}  =>  \"{inner_text}\"")

    pm.close_process()
    print()


if __name__ == "__main__":
    main()
