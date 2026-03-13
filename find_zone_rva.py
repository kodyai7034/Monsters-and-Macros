"""
Scan GameAssembly.dll data section for ZoneController TypeInfo RVA.

TypeInfo pointers are stored near each other. We know Client is at RVA 0x54405D8.
This script scans nearby RVAs, reads the Il2CppClass.name for each pointer,
and prints any zone-related classes.

Run on Windows with the game running:
    python find_zone_rva.py
"""

import sys

try:
    import pymem
    import pymem.process
except ImportError:
    print("pymem not installed. Run: pip install pymem")
    sys.exit(1)

PROCESS_NAME = "mnm.exe"
MODULE_NAME = "GameAssembly.dll"
CLIENT_TYPEINFO_RVA = 0x54405D8

# Il2CppClass field offsets (64-bit)
CLASS_NAME_OFF = 0x10       # const char* name
CLASS_NAMESPACE_OFF = 0x18  # const char* namespaze


def read_ptr(pm, addr):
    try:
        return pm.read_longlong(addr)
    except Exception:
        return 0


def read_cstring(pm, addr, max_len=128):
    """Read a null-terminated C string."""
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


def main():
    print(f"\nZoneController TypeInfo Scanner")
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
    print(f"Known Client TypeInfo RVA: 0x{CLIENT_TYPEINFO_RVA:X}")

    # Scan a wide range around the known RVA
    # TypeInfo pointers are typically in a large table
    scan_start = CLIENT_TYPEINFO_RVA - 0x100000  # 1MB before
    scan_end = CLIENT_TYPEINFO_RVA + 0x100000    # 1MB after
    if scan_start < 0:
        scan_start = 0

    print(f"\nScanning RVA range 0x{scan_start:X} - 0x{scan_end:X}")
    print(f"Looking for zone-related classes...\n")

    zone_results = []
    all_classes = []

    for rva in range(scan_start, scan_end, 8):
        addr = ga_base + rva
        class_ptr = read_ptr(pm, addr)

        if not class_ptr or class_ptr < 0x10000:
            continue

        # Try reading the class name
        name_ptr = read_ptr(pm, class_ptr + CLASS_NAME_OFF)
        if not name_ptr or name_ptr < 0x10000:
            continue

        name = read_cstring(pm, name_ptr)
        if not name or len(name) < 2 or len(name) > 80:
            continue

        # Filter: must look like a valid C# class/field name
        if not name[0].isalpha() and name[0] != '_':
            continue

        # Read namespace too
        ns_ptr = read_ptr(pm, class_ptr + CLASS_NAMESPACE_OFF)
        namespace = read_cstring(pm, ns_ptr) if ns_ptr else ""

        if "zone" in name.lower() or "zone" in namespace.lower():
            zone_results.append((rva, namespace, name, class_ptr))

    if zone_results:
        print(f"Found {len(zone_results)} zone-related classes:\n")
        print(f"  {'RVA':<14} {'Namespace':<30} {'Class Name':<30} {'ClassPtr'}")
        print(f"  {'-'*14} {'-'*30} {'-'*30} {'-'*18}")
        for rva, ns, name, ptr in zone_results:
            print(f"  0x{rva:08X}     {ns:<30} {name:<30} 0x{ptr:X}")
    else:
        print("No zone-related classes found in scan range.")
        print("Try expanding the scan range or checking if the RVA is correct.")

    pm.close_process()
    print()


if __name__ == "__main__":
    main()
