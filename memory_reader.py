"""
Game memory reader for Monsters and Memories.
Reads entity data (health, mana, buffs, target info) directly from game memory
using Windows ReadProcessMemory API via pymem.

Offsets extracted from IL2CPP dump of GameAssembly.dll.

Usage:
    reader = GameMemoryReader()
    reader.connect()
    player = reader.get_player()
    target = reader.get_target()
    buffs = reader.get_target_buffs()
"""

import time
import struct
import threading
import copy

try:
    import pymem
    import pymem.process
    HAS_PYMEM = True
except ImportError:
    HAS_PYMEM = False


# =========================================================================
# IL2CPP offsets from dump.cs (GameAssembly.dll)
# These WILL change when the game patches — re-run Il2CppDumper to update
# =========================================================================

# Entity class (base for all game entities)
class EntityOff:
    ID = 0x118              # uint id
    NAME = 0x120            # Il2CppString* entityName
    RACE_HID = 0x140        # Il2CppString* raceHID
    SEX_HID = 0x148         # Il2CppString* sexHID
    IS_STUNNED = 0x190      # bool isStunned
    IS_FEARED = 0x191       # bool isFeared
    IS_HOSTILE = 0x19D      # bool isHostile
    IS_CORPSE = 0x19C       # bool isCorpse
    STATS = 0x250           # EntityStats* _stats
    IS_CASTING = 0x258      # bool isCasting
    AUTOATTACKING = 0x25F   # bool autoattacking
    POSITION = 0x280        # AntiTamperVector3* _localInterpolatedServerPosition
    POSTURE = 0x28C         # EntityPosture CurrentPosture (int)
    TARGET_HANDLER = 0x1B0  # EntityTargetHandler* TargetHandler
    BUFFS = 0x2D0           # EntityBuffs* Buffs


# Client class (extends Entity — the local player)
class ClientOff:
    # Static fields — accessed via Il2CppClass->static_fields
    MINE_STATIC = 0x0       # Client* mine (static offset within static fields block)
    # Instance fields (added to Entity base offsets)
    AUTO_FOLLOW = 0x2F8     # Entity* autoFollowTarget
    CLASS_HID = 0x308       # Il2CppString* classHID
    INVENTORY = 0x330       # Inventory* inventory
    LAST_TARGET = 0x370     # Entity* lastTarget
    HEADING_ATF = 0x388     # AntiTamperFloat* heading (degrees 0-360)
    HEADING_RAW = 0x4AC     # float heading (cached copy, degrees 0-360)
    ABILITIES = 0x4D8       # ClientAbilities* Abilities
    IS_FEIGN_DEATH = 0x3C2  # bool isFeignDeath


# AntiTamperVector3 — stores position as 3 AntiTamperFloat references
class AntiTamperVector3Off:
    X = 0x10                # AntiTamperFloat* _x
    Y = 0x18                # AntiTamperFloat* _y
    Z = 0x20                # AntiTamperFloat* _z


# AntiTamperFloat — tamper-protected float wrapper
class AntiTamperFloatOff:
    PRIMARY = 0x10          # float _primary (the actual readable value)


# EntityTargetHandler
class TargetHandlerOff:
    TARGET_ID = 0x18        # Nullable<uint> _targetId
    TARGET_ENTITY = 0x20    # Entity* _targetEntity


# EntityBuffs
class EntityBuffsOff:
    BUFFS_DICT = 0x10       # Dictionary<uint, BuffRecord>* _buffs


# BuffRecord
class BuffRecordOff:
    ENTITY_BUFF_ID = 0x10   # uint entityBuffID
    BUFF_HID = 0x18         # Il2CppString* buffHID
    BUFF_NAME = 0x20        # Il2CppString* buffName
    TYPE = 0x28             # Il2CppString* type
    STACKS = 0x30           # ushort stacks
    DATA = 0x38             # Il2CppString* data
    ICON_HID = 0x40         # Il2CppString* iconHID
    ABILITY_HID = 0x48      # Il2CppString* abilityHID
    CATEGORY_HID = 0x50     # Il2CppString* categoryHID
    FADE_TIME_MS = 0x58     # ulong fadeTimeMs
    DURATION_MS = 0x60      # uint durationMs
    DESCRIPTION = 0x68      # Il2CppString* description


# IL2CPP internal structures
class IL2CPP:
    # Il2CppString layout
    STRING_LENGTH = 0x10    # int32 length
    STRING_CHARS = 0x14     # char[length] (UTF-16LE)

    # Il2CppArray layout
    ARRAY_LENGTH = 0x18     # int32 length (or ulong on 64-bit)
    ARRAY_DATA = 0x20       # T[] data starts here

    # Dictionary<TKey, TValue> internal layout (System.Collections.Generic)
    # After Il2CppObject header (0x10), fields in declaration order:
    DICT_BUCKETS = 0x10     # int[] _buckets
    DICT_ENTRIES = 0x18     # Entry[] _entries
    DICT_COUNT = 0x20       # int _count
    DICT_FREECOUNT = 0x28   # int _freeCount
    DICT_VERSION = 0x2C     # int _version

    # Dictionary.Entry<uint, BuffRecord> struct
    # hashCode(0x0, int), next(0x4, int), key(0x8, uint/int depending),
    # value(0x10, pointer for ref types)
    ENTRY_SIZE = 0x18       # sizeof(Entry) with alignment
    ENTRY_HASHCODE = 0x0
    ENTRY_KEY = 0x8
    ENTRY_VALUE = 0x10

    # Il2CppClass structure (for finding static fields)
    CLASS_STATIC_FIELDS = 0xB8  # void* static_fields (Unity 6000.x / 2023+)


# Metadata addresses (RVAs within GameAssembly.dll)
CLIENT_TYPEINFO_RVA = 0x54405D8
ZONE_CONTROLLER_TYPEINFO_RVA = 0x0542B5B0


# ZoneController — singleton that tracks current zone
class ZoneControllerOff:
    INSTANCE_STATIC = 0x0   # ZoneController* instance (in static_fields)
    CURRENT_ZONE_HID = 0x28 # Il2CppString* currentZoneHid


class GameSnapshot:
    """Immutable snapshot of game state at a point in time."""

    def __init__(self):
        self.timestamp = 0.0

        # Player
        self.player = None          # dict from _read_entity_data + extras
        self.player_hp = 0
        self.player_max_hp = 0
        self.player_mana = 0
        self.player_max_mana = 0
        self.player_endurance = 0
        self.player_max_endurance = 0
        self.player_level = 0
        self.player_buffs = []      # list of buff dicts
        self.player_x = 0.0
        self.player_y = 0.0         # vertical axis
        self.player_z = 0.0
        self.player_heading = 0.0   # degrees 0-360
        self.zone_name = ""

        # Target
        self.target = None          # dict from _read_entity_data
        self.target_hp = 0
        self.target_max_hp = 0
        self.target_mana = 0
        self.target_max_mana = 0
        self.target_level = 0
        self.target_buffs = []      # list of buff dicts
        self.target_x = 0.0
        self.target_y = 0.0
        self.target_z = 0.0

    @property
    def age(self):
        """Seconds since this snapshot was taken."""
        return time.monotonic() - self.timestamp if self.timestamp else float("inf")


class GameMemoryReader:
    """Reads game state from Monsters and Memories process memory.

    Runs a background polling thread that takes periodic snapshots of
    game state. Macros and conditions read from the latest snapshot
    instead of hitting ReadProcessMemory on every query.
    """

    PROCESS_NAME = "mnm.exe"
    MODULE_NAME = "GameAssembly.dll"

    def __init__(self, config=None):
        self.config = config or {}
        self.pm = None
        self.ga_base = 0
        self._connected = False
        self._client_mine_ptr = 0
        self._zone_controller_ptr = 0

        # Polling thread
        self._poll_interval = self.config.get("poll_interval", 0.1)  # 100ms default
        self._poll_thread = None
        self._poll_stop = threading.Event()

        # Thread-safe snapshot — written by poll thread, read by main thread
        self._lock = threading.Lock()
        self._snapshot = GameSnapshot()

        # Event callbacks — {event_name: [callable, ...]}
        self._callbacks = {}

    def connect(self):
        """Attach to the game process and find GameAssembly.dll."""
        if not HAS_PYMEM:
            raise RuntimeError("pymem not installed. Run: pip install pymem")

        self.pm = pymem.Pymem(self.PROCESS_NAME)
        ga_module = pymem.process.module_from_name(
            self.pm.process_handle, self.MODULE_NAME
        )
        if not ga_module:
            raise RuntimeError(f"Could not find {self.MODULE_NAME} in process")

        self.ga_base = ga_module.lpBaseOfDll
        self._connected = True
        self._resolve_client_mine()

        # Take an initial snapshot before starting the poll thread
        self._poll_once()

        # Start background polling
        self._poll_stop.clear()
        self._poll_thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="MemoryPoller"
        )
        self._poll_thread.start()
        print(f"[MEMORY] Polling thread started ({self._poll_interval * 1000:.0f}ms interval)")
        return True

    def disconnect(self):
        """Stop polling and detach from the game process."""
        self._poll_stop.set()
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=2.0)
        if self.pm:
            self.pm.close_process()
        self._connected = False
        self._client_mine_ptr = 0
        self._zone_controller_ptr = 0

    @property
    def connected(self):
        return self._connected

    # =====================================================================
    # Event callbacks
    # =====================================================================

    def on(self, event, callback):
        """Register a callback for a game state event.

        Events:
            'target_changed'  — target entity changed (passes new target dict or None)
            'health_warning'  — player health dropped below threshold
            'player_died'     — player is now a corpse
            'buff_gained'     — new buff appeared on player (passes buff dict)
            'buff_lost'       — buff disappeared from player (passes buff name)
        """
        self._callbacks.setdefault(event, []).append(callback)

    def _fire(self, event, *args):
        """Fire all callbacks for an event."""
        for cb in self._callbacks.get(event, []):
            try:
                cb(*args)
            except Exception as e:
                print(f"[MEMORY] Callback error ({event}): {e}")

    # =====================================================================
    # Low-level memory reads
    # =====================================================================

    def read_ptr(self, addr):
        """Read a 64-bit pointer. Returns 0 on failure."""
        if not addr:
            return 0
        try:
            return self.pm.read_longlong(addr)
        except Exception:
            return 0

    def read_int(self, addr):
        """Read a 32-bit signed integer."""
        if not addr:
            return 0
        try:
            return self.pm.read_int(addr)
        except Exception:
            return 0

    def read_uint(self, addr):
        """Read a 32-bit unsigned integer."""
        if not addr:
            return 0
        try:
            return self.pm.read_uint(addr)
        except Exception:
            return 0

    def read_ulong(self, addr):
        """Read a 64-bit unsigned integer."""
        if not addr:
            return 0
        try:
            return self.pm.read_ulonglong(addr)
        except Exception:
            return 0

    def read_ushort(self, addr):
        """Read a 16-bit unsigned integer."""
        if not addr:
            return 0
        try:
            return self.pm.read_ushort(addr)
        except Exception:
            return 0

    def read_float(self, addr):
        """Read a 32-bit float."""
        if not addr:
            return 0.0
        try:
            return self.pm.read_float(addr)
        except Exception:
            return 0.0

    def read_bool(self, addr):
        """Read a single byte as boolean."""
        if not addr:
            return False
        try:
            return self.pm.read_bool(addr)
        except Exception:
            return False

    def read_bytes(self, addr, size):
        """Read raw bytes."""
        if not addr or size <= 0:
            return b""
        try:
            return self.pm.read_bytes(addr, size)
        except Exception:
            return b""

    def read_il2cpp_string(self, str_ptr):
        """Read an IL2CPP string (Il2CppString*). Returns Python str."""
        if not str_ptr:
            return ""
        length = self.read_int(str_ptr + IL2CPP.STRING_LENGTH)
        if length <= 0 or length > 2048:
            return ""
        raw = self.read_bytes(str_ptr + IL2CPP.STRING_CHARS, length * 2)
        if not raw:
            return ""
        return raw.decode("utf-16-le", errors="replace")

    def follow_chain(self, base, *offsets):
        """Follow a pointer chain: base -> [off1] -> [off2] -> ..."""
        addr = base
        for off in offsets[:-1]:
            addr = self.read_ptr(addr + off)
            if not addr:
                return 0
        return addr + offsets[-1] if offsets else addr

    # =====================================================================
    # IL2CPP runtime resolution
    # =====================================================================

    def _resolve_client_mine(self):
        """Find the Client.mine static field — pointer to local player Entity."""
        # Method: Read the Il2CppClass* for Client from the TypeInfo pointer,
        # then read static_fields, then read mine at offset 0x0.

        # The TypeInfo RVA points to a pointer to the Il2CppClass struct
        rva = self.config.get("client_typeinfo_rva", CLIENT_TYPEINFO_RVA)
        typeinfo_ptr_addr = self.ga_base + rva

        # Read the Il2CppClass* pointer
        il2cpp_class = self.read_ptr(typeinfo_ptr_addr)
        if not il2cpp_class:
            print("[MEMORY] Warning: Could not read Client Il2CppClass pointer")
            return

        # Read static_fields pointer from Il2CppClass
        static_fields = self.read_ptr(il2cpp_class + IL2CPP.CLASS_STATIC_FIELDS)
        if not static_fields:
            print("[MEMORY] Warning: Could not read Client static_fields")
            return

        # Client.mine is at static offset 0x0
        self._client_mine_ptr = self.read_ptr(static_fields + ClientOff.MINE_STATIC)

        if self._client_mine_ptr:
            name = self.read_il2cpp_string(
                self.read_ptr(self._client_mine_ptr + EntityOff.NAME)
            )
            print(f"[MEMORY] Found player entity: {name} @ 0x{self._client_mine_ptr:X}")
        else:
            print("[MEMORY] Client.mine is null (not logged in?)")

    def _refresh_client_mine(self):
        """Re-read Client.mine (in case player zoned or logged in)."""
        rva = self.config.get("client_typeinfo_rva", CLIENT_TYPEINFO_RVA)
        typeinfo_ptr_addr = self.ga_base + rva
        il2cpp_class = self.read_ptr(typeinfo_ptr_addr)
        if not il2cpp_class:
            self._client_mine_ptr = 0
            return
        static_fields = self.read_ptr(il2cpp_class + IL2CPP.CLASS_STATIC_FIELDS)
        if not static_fields:
            self._client_mine_ptr = 0
            return
        self._client_mine_ptr = self.read_ptr(static_fields + ClientOff.MINE_STATIC)

    def _read_zone_name(self):
        """Read current zone HID from ZoneController singleton."""
        if not self._zone_controller_ptr:
            # Resolve ZoneController.instance from static fields
            rva = self.config.get("zone_controller_rva", ZONE_CONTROLLER_TYPEINFO_RVA)
            typeinfo_addr = self.ga_base + rva
            il2cpp_class = self.read_ptr(typeinfo_addr)
            if not il2cpp_class:
                return ""
            static_fields = self.read_ptr(il2cpp_class + IL2CPP.CLASS_STATIC_FIELDS)
            if not static_fields:
                return ""
            self._zone_controller_ptr = self.read_ptr(
                static_fields + ZoneControllerOff.INSTANCE_STATIC
            )
        if not self._zone_controller_ptr:
            return ""
        str_ptr = self.read_ptr(
            self._zone_controller_ptr + ZoneControllerOff.CURRENT_ZONE_HID
        )
        return self.read_il2cpp_string(str_ptr)

    # =====================================================================
    # Polling thread
    # =====================================================================

    def _poll_loop(self):
        """Background thread: periodically read game state into snapshot."""
        while not self._poll_stop.is_set():
            try:
                self._poll_once()
            except Exception as e:
                print(f"[MEMORY] Poll error: {e}")
            self._poll_stop.wait(self._poll_interval)

    def _poll_once(self):
        """Read all game state and update the snapshot atomically."""
        self._refresh_client_mine()
        player_ptr = self._client_mine_ptr

        snap = GameSnapshot()
        snap.timestamp = time.monotonic()

        # Player
        if player_ptr:
            snap.player = self._read_entity_data(player_ptr)
            snap.player["class_hid"] = self.read_il2cpp_string(
                self.read_ptr(player_ptr + ClientOff.CLASS_HID)
            )
            snap.player["is_feign_death"] = self.read_bool(
                player_ptr + ClientOff.IS_FEIGN_DEATH
            )
            snap.player_hp = self._read_stat(player_ptr, 0)
            snap.player_max_hp = self._read_stat(player_ptr, 1)
            snap.player_mana = self._read_stat(player_ptr, 2)
            snap.player_max_mana = self._read_stat(player_ptr, 3)
            snap.player_endurance = self._read_stat(player_ptr, 4)
            snap.player_max_endurance = self._read_stat(player_ptr, 5)
            snap.player_level = self._read_stat(player_ptr, 17)
            snap.player_buffs = self.read_buffs(player_ptr)
            snap.player_x, snap.player_y, snap.player_z = self._read_position(player_ptr)
            snap.player_heading = self._read_heading(player_ptr)

        # Zone
        snap.zone_name = self._read_zone_name()

        # Target
        target_ptr = 0
        if player_ptr:
            handler = self.read_ptr(player_ptr + EntityOff.TARGET_HANDLER)
            if handler:
                target_ptr = self.read_ptr(handler + TargetHandlerOff.TARGET_ENTITY)

        if target_ptr:
            snap.target = self._read_entity_data(target_ptr)
            snap.target_hp = self._read_stat(target_ptr, 0)
            snap.target_max_hp = self._read_stat(target_ptr, 1)
            snap.target_mana = self._read_stat(target_ptr, 2)
            snap.target_max_mana = self._read_stat(target_ptr, 3)
            snap.target_level = self._read_stat(target_ptr, 17)
            snap.target_buffs = self.read_buffs(target_ptr)
            snap.target_x, snap.target_y, snap.target_z = self._read_position(target_ptr)

        # Detect changes and fire events
        old = self._snapshot
        if old.target and not snap.target:
            self._fire("target_changed", None)
        elif snap.target and (not old.target or old.target["id"] != snap.target["id"]):
            self._fire("target_changed", snap.target)

        if snap.player:
            # Health warning at 30%
            if snap.player_max_hp > 0:
                pct = snap.player_hp / snap.player_max_hp
                old_pct = old.player_hp / old.player_max_hp if old.player_max_hp > 0 else 1.0
                if pct < 0.3 and old_pct >= 0.3:
                    self._fire("health_warning", pct)

            # Death
            if snap.player.get("is_corpse") and not (old.player or {}).get("is_corpse"):
                self._fire("player_died")

            # Buff tracking
            old_buff_names = {b["name"] for b in old.player_buffs}
            new_buff_names = {b["name"] for b in snap.player_buffs}
            for b in snap.player_buffs:
                if b["name"] not in old_buff_names:
                    self._fire("buff_gained", b)
            for name in old_buff_names - new_buff_names:
                self._fire("buff_lost", name)

        # Swap snapshot atomically
        with self._lock:
            self._snapshot = snap

    def _read_entity_data(self, entity_ptr):
        """Read basic entity fields from a pointer (internal, no caching)."""
        if not entity_ptr:
            return None
        return {
            "ptr": entity_ptr,
            "id": self.read_uint(entity_ptr + EntityOff.ID),
            "name": self.read_il2cpp_string(
                self.read_ptr(entity_ptr + EntityOff.NAME)
            ),
            "is_stunned": self.read_bool(entity_ptr + EntityOff.IS_STUNNED),
            "is_feared": self.read_bool(entity_ptr + EntityOff.IS_FEARED),
            "is_hostile": self.read_bool(entity_ptr + EntityOff.IS_HOSTILE),
            "is_corpse": self.read_bool(entity_ptr + EntityOff.IS_CORPSE),
            "is_casting": self.read_bool(entity_ptr + EntityOff.IS_CASTING),
            "autoattacking": self.read_bool(entity_ptr + EntityOff.AUTOATTACKING),
            "posture": self.read_int(entity_ptr + EntityOff.POSTURE),
        }

    # =====================================================================
    # Snapshot accessors (thread-safe, read from latest poll)
    # =====================================================================

    @property
    def snapshot(self):
        """Get a copy of the latest game state snapshot."""
        with self._lock:
            return copy.copy(self._snapshot)

    def get_player(self):
        """Get player data from latest snapshot."""
        with self._lock:
            return self._snapshot.player

    def get_target(self):
        """Get target data from latest snapshot."""
        with self._lock:
            return self._snapshot.target

    def has_target(self):
        """Check if player has a target."""
        with self._lock:
            return self._snapshot.target is not None

    def get_player_ptr(self):
        """Get pointer to local player entity. Re-resolves if null."""
        if not self._client_mine_ptr:
            self._refresh_client_mine()
        return self._client_mine_ptr

    def get_target_ptr(self):
        """Get pointer to current target entity via TargetHandler."""
        player = self.get_player_ptr()
        if not player:
            return 0
        handler = self.read_ptr(player + EntityOff.TARGET_HANDLER)
        if not handler:
            return 0
        return self.read_ptr(handler + TargetHandlerOff.TARGET_ENTITY)

    # =====================================================================
    # Stat reading
    # =====================================================================

    def _read_stat(self, entity_ptr, stat_key):
        """
        Read a stat value from EntityStats dictionary.
        stat_key is the EntityStatType enum value (int).
        Returns int value or 0.
        """
        if not entity_ptr:
            return 0
        stats_ptr = self.read_ptr(entity_ptr + EntityOff.STATS)
        if not stats_ptr:
            return 0

        # EntityStats has _stats Dictionary<TKey, ObservableValue<TValue>>
        # at offset 0x10 (first field after object header)
        dict_ptr = self.read_ptr(stats_ptr + 0x10)
        if not dict_ptr:
            return 0

        # Read dictionary entries to find the stat
        entries_arr = self.read_ptr(dict_ptr + IL2CPP.DICT_ENTRIES)
        count = self.read_int(dict_ptr + IL2CPP.DICT_COUNT)
        if not entries_arr or count <= 0:
            return 0

        arr_length = self.read_int(entries_arr + IL2CPP.ARRAY_LENGTH)
        data_start = entries_arr + IL2CPP.ARRAY_DATA

        # Entry<int, ObservableValue<int>> — key is int (4 bytes, enum)
        # value is ObservableValue<int>* (pointer)
        # Entry: hashCode(0x0), next(0x4), key(0x8), value(0x10)
        for i in range(min(count + 5, arr_length, 64)):
            entry_base = data_start + (i * IL2CPP.ENTRY_SIZE)
            hash_code = self.read_int(entry_base + IL2CPP.ENTRY_HASHCODE)
            if hash_code < 0:
                continue
            key = self.read_int(entry_base + IL2CPP.ENTRY_KEY)
            if key == stat_key:
                # ObservableValue<int> has the value at some offset
                # ObservableValue likely has: object header (0x10), then _value
                obs_ptr = self.read_ptr(entry_base + IL2CPP.ENTRY_VALUE)
                if obs_ptr:
                    return self.read_int(obs_ptr + 0x10)  # _value field
                return 0
        return 0

    def _read_position(self, entity_ptr):
        """Read AntiTamperVector3 position from an entity.

        Path: entity_ptr + 0x280 -> AntiTamperVector3*
              -> _x(0x10) -> AntiTamperFloat* -> _primary(0x10) = float
              -> _y(0x18) -> AntiTamperFloat* -> _primary(0x10) = float
              -> _z(0x20) -> AntiTamperFloat* -> _primary(0x10) = float
        Returns (x, y, z) tuple of floats.
        """
        if not entity_ptr:
            return (0.0, 0.0, 0.0)

        vec_ptr = self.read_ptr(entity_ptr + EntityOff.POSITION)
        if not vec_ptr:
            return (0.0, 0.0, 0.0)

        coords = []
        for offset in (AntiTamperVector3Off.X, AntiTamperVector3Off.Y, AntiTamperVector3Off.Z):
            atf_ptr = self.read_ptr(vec_ptr + offset)
            if atf_ptr:
                coords.append(self.read_float(atf_ptr + AntiTamperFloatOff.PRIMARY))
            else:
                coords.append(0.0)

        return tuple(coords)

    def _read_heading(self, entity_ptr):
        """Read player heading from AntiTamperFloat at ClientOff.HEADING_ATF.

        Returns heading in degrees (0-360).
        """
        if not entity_ptr:
            return 0.0
        atf_ptr = self.read_ptr(entity_ptr + ClientOff.HEADING_ATF)
        if atf_ptr:
            val = self.read_float(atf_ptr + AntiTamperFloatOff.PRIMARY)
            if val is not None:
                return val
        return 0.0

    def get_entity_health(self, entity_ptr):
        """Get current health for an entity (live read, not snapshot)."""
        return self._read_stat(entity_ptr, 0)

    def get_entity_max_health(self, entity_ptr):
        """Get max health for an entity (live read)."""
        return self._read_stat(entity_ptr, 1)

    def get_entity_mana(self, entity_ptr):
        """Get current mana for an entity (live read)."""
        return self._read_stat(entity_ptr, 2)

    def get_entity_max_mana(self, entity_ptr):
        """Get max mana for an entity (live read)."""
        return self._read_stat(entity_ptr, 3)

    def get_entity_level(self, entity_ptr):
        """Get level for an entity (live read)."""
        return self._read_stat(entity_ptr, 17)

    # =====================================================================
    # Buff reading
    # =====================================================================

    def read_buffs(self, entity_ptr):
        """Read all buffs/debuffs on an entity. Returns list of dicts."""
        if not entity_ptr:
            return []

        buffs_obj = self.read_ptr(entity_ptr + EntityOff.BUFFS)
        if not buffs_obj:
            return []

        dict_ptr = self.read_ptr(buffs_obj + EntityBuffsOff.BUFFS_DICT)
        if not dict_ptr:
            return []

        entries_arr = self.read_ptr(dict_ptr + IL2CPP.DICT_ENTRIES)
        count = self.read_int(dict_ptr + IL2CPP.DICT_COUNT)
        if not entries_arr or count <= 0:
            return []

        arr_length = self.read_int(entries_arr + IL2CPP.ARRAY_LENGTH)
        data_start = entries_arr + IL2CPP.ARRAY_DATA

        result = []
        for i in range(min(count + 5, arr_length, 128)):
            entry_base = data_start + (i * IL2CPP.ENTRY_SIZE)
            hash_code = self.read_int(entry_base + IL2CPP.ENTRY_HASHCODE)
            if hash_code < 0:
                continue

            buff_ptr = self.read_ptr(entry_base + IL2CPP.ENTRY_VALUE)
            if not buff_ptr:
                continue

            buff = self._read_buff_record(buff_ptr)
            if buff:
                result.append(buff)

            if len(result) >= count:
                break

        return result

    def _read_buff_record(self, ptr):
        """Read a single BuffRecord from memory."""
        if not ptr:
            return None
        return {
            "entity_buff_id": self.read_uint(ptr + BuffRecordOff.ENTITY_BUFF_ID),
            "buff_hid": self.read_il2cpp_string(
                self.read_ptr(ptr + BuffRecordOff.BUFF_HID)
            ),
            "name": self.read_il2cpp_string(
                self.read_ptr(ptr + BuffRecordOff.BUFF_NAME)
            ),
            "type": self.read_il2cpp_string(
                self.read_ptr(ptr + BuffRecordOff.TYPE)
            ),
            "stacks": self.read_ushort(ptr + BuffRecordOff.STACKS),
            "category_hid": self.read_il2cpp_string(
                self.read_ptr(ptr + BuffRecordOff.CATEGORY_HID)
            ),
            "fade_time_ms": self.read_ulong(ptr + BuffRecordOff.FADE_TIME_MS),
            "duration_ms": self.read_uint(ptr + BuffRecordOff.DURATION_MS),
            "description": self.read_il2cpp_string(
                self.read_ptr(ptr + BuffRecordOff.DESCRIPTION)
            ),
        }

    # =====================================================================
    # Convenience query methods (read from snapshot)
    # =====================================================================

    def target_has_buff(self, buff_name):
        """Check if current target has a buff/debuff by name (case-insensitive)."""
        search = buff_name.lower()
        with self._lock:
            for buff in self._snapshot.target_buffs:
                if search in buff["name"].lower():
                    return True
        return False

    def target_has_category(self, category_hid):
        """Check if target has a buff with a specific category (e.g. 'mez', 'dot')."""
        with self._lock:
            for buff in self._snapshot.target_buffs:
                if buff["category_hid"] == category_hid:
                    return True
        return False

    def player_has_buff(self, buff_name):
        """Check if local player has a buff by name (case-insensitive)."""
        search = buff_name.lower()
        with self._lock:
            for buff in self._snapshot.player_buffs:
                if search in buff["name"].lower():
                    return True
        return False

    def target_is_mezzed(self):
        """Check if target is mesmerized."""
        return self.target_has_category("mez")

    def target_is_stunned(self):
        """Check if target is stunned."""
        with self._lock:
            t = self._snapshot.target
            return t["is_stunned"] if t else False

    def target_is_feared(self):
        """Check if target is feared."""
        with self._lock:
            t = self._snapshot.target
            return t["is_feared"] if t else False

    def player_is_casting(self):
        """Check if local player is currently casting."""
        with self._lock:
            p = self._snapshot.player
            return p["is_casting"] if p else False

    def player_is_sitting(self):
        """Check if local player is sitting (posture == 1)."""
        with self._lock:
            p = self._snapshot.player
            return p["posture"] == 1 if p else False

    def player_is_standing(self):
        """Check if local player is standing (posture == 0)."""
        with self._lock:
            p = self._snapshot.player
            return p["posture"] == 0 if p else False

    def player_is_autoattacking(self):
        """Check if player has auto-attack enabled."""
        with self._lock:
            p = self._snapshot.player
            return p["autoattacking"] if p else False

    def player_posture(self):
        """Get player posture as int (0=standing, 1=sitting, etc.)."""
        with self._lock:
            p = self._snapshot.player
            return p["posture"] if p else 0

    def get_endurance_pct(self):
        """Get player endurance as a 0.0-1.0 percentage."""
        with self._lock:
            snap = self._snapshot
            if snap.player_max_endurance <= 0:
                return 0.0
            return snap.player_endurance / snap.player_max_endurance

    def get_player_level(self):
        """Get player level from snapshot."""
        with self._lock:
            return self._snapshot.player_level

    def get_zone_name(self):
        """Get the current zone HID string."""
        with self._lock:
            return self._snapshot.zone_name

    def player_buff_count(self):
        """Get number of active buffs on the player."""
        with self._lock:
            return len(self._snapshot.player_buffs)

    def target_buff_count(self):
        """Get number of active buffs/debuffs on the target."""
        with self._lock:
            return len(self._snapshot.target_buffs)

    def get_target_position(self):
        """Get target position as (x, y, z). Returns (0,0,0) if no target."""
        with self._lock:
            snap = self._snapshot
            return (snap.target_x, snap.target_y, snap.target_z)

    def get_player_position(self):
        """Get player position as (x, y, z)."""
        with self._lock:
            snap = self._snapshot
            return (snap.player_x, snap.player_y, snap.player_z)

    def get_player_heading(self):
        """Get player heading in degrees (0-360)."""
        with self._lock:
            return self._snapshot.player_heading

    def get_distance_to_target(self):
        """Get 2D distance (XZ plane) to current target."""
        with self._lock:
            snap = self._snapshot
            if not snap.target:
                return float("inf")
            dx = snap.target_x - snap.player_x
            dz = snap.target_z - snap.player_z
            return (dx * dx + dz * dz) ** 0.5

    def get_angle_to_target(self):
        """Get angle (degrees) from player to target on XZ plane.

        Returns angle in degrees where 0 = +X, 90 = +Z.
        Returns None if no target.
        """
        import math
        with self._lock:
            snap = self._snapshot
            if not snap.target:
                return None
            dx = snap.target_x - snap.player_x
            dz = snap.target_z - snap.player_z
            if dx == 0 and dz == 0:
                return 0.0
            return math.degrees(math.atan2(dz, dx))

    def target_name(self):
        """Get the name of the current target."""
        with self._lock:
            t = self._snapshot.target
            return t["name"] if t else ""

    def target_level(self):
        """Get level of the current target."""
        with self._lock:
            return self._snapshot.target_level

    def get_player_buffs(self):
        """Get all buffs on the local player."""
        with self._lock:
            return list(self._snapshot.player_buffs)

    def get_target_buffs(self):
        """Get all buffs/debuffs on the current target."""
        with self._lock:
            return list(self._snapshot.target_buffs)

    def get_health_pct(self, entity_ptr=None):
        """Get player health as a 0.0-1.0 percentage (from snapshot)."""
        with self._lock:
            if self._snapshot.player_max_hp <= 0:
                return 0.0
            return self._snapshot.player_hp / self._snapshot.player_max_hp

    def get_mana_pct(self, entity_ptr=None):
        """Get player mana as a 0.0-1.0 percentage (from snapshot)."""
        with self._lock:
            if self._snapshot.player_max_mana <= 0:
                return 0.0
            return self._snapshot.player_mana / self._snapshot.player_max_mana

    def get_target_health_pct(self):
        """Get target health as a 0.0-1.0 percentage."""
        with self._lock:
            if self._snapshot.target_max_hp <= 0:
                return 0.0
            return self._snapshot.target_hp / self._snapshot.target_max_hp

    # =====================================================================
    # Debug / diagnostic
    # =====================================================================

    def dump_player_info(self):
        """Print full player info from snapshot."""
        snap = self.snapshot
        player = snap.player
        if not player:
            print("[MEMORY] No player entity found")
            return

        hp_pct = snap.player_hp / snap.player_max_hp if snap.player_max_hp > 0 else 0
        mp_pct = snap.player_mana / snap.player_max_mana if snap.player_max_mana > 0 else 0

        print(f"\n  Player: {player['name']}")
        print(f"  ID: {player['id']}")
        print(f"  Class: {player.get('class_hid', '?')}")
        print(f"  Casting: {player['is_casting']}")
        print(f"  Posture: {player['posture']}")
        print(f"  Health: {snap.player_hp}/{snap.player_max_hp} ({hp_pct:.0%})")
        print(f"  Mana: {snap.player_mana}/{snap.player_max_mana} ({mp_pct:.0%})")
        print(f"  Level: {snap.player_level}")
        print(f"  Position: ({snap.player_x:.1f}, {snap.player_y:.1f}, {snap.player_z:.1f})")
        print(f"  Heading:  {snap.player_heading:.1f}°")
        print(f"  Zone: {snap.zone_name}")

        print(f"  Buffs ({len(snap.player_buffs)}):")
        for b in snap.player_buffs:
            print(f"    - {b['name']} [{b['category_hid']}] "
                  f"stacks={b['stacks']} dur={b['duration_ms']}ms")

    def dump_target_info(self):
        """Print full target info from snapshot."""
        snap = self.snapshot
        target = snap.target
        if not target:
            print("[MEMORY] No target")
            return

        hp_pct = snap.target_hp / snap.target_max_hp if snap.target_max_hp > 0 else 0

        print(f"\n  Target: {target['name']}")
        print(f"  ID: {target['id']}")
        print(f"  Hostile: {target['is_hostile']}")
        print(f"  Stunned: {target['is_stunned']}")
        print(f"  Feared: {target['is_feared']}")
        print(f"  Casting: {target['is_casting']}")
        print(f"  Corpse: {target['is_corpse']}")
        print(f"  Health: {snap.target_hp}/{snap.target_max_hp} ({hp_pct:.0%})")
        print(f"  Level: {snap.target_level}")

        print(f"  Buffs ({len(snap.target_buffs)}):")
        for b in snap.target_buffs:
            print(f"    - {b['name']} [{b['category_hid']}] "
                  f"stacks={b['stacks']} dur={b['duration_ms']}ms")


# =========================================================================
# CLI for testing
# =========================================================================

if __name__ == "__main__":
    import sys

    if not HAS_PYMEM:
        print("pymem not installed. Run: pip install pymem")
        sys.exit(1)

    reader = GameMemoryReader()

    try:
        reader.connect()
        print(f"[OK] Connected to {reader.PROCESS_NAME}")
        print(f"[OK] GameAssembly.dll base: 0x{reader.ga_base:X}")
    except Exception as e:
        print(f"[FAIL] Could not connect: {e}")
        sys.exit(1)

    # Register some debug event callbacks
    reader.on("target_changed", lambda t: print(
        f"\n[EVENT] Target changed -> {t['name'] if t else 'None'}"
    ))
    reader.on("health_warning", lambda pct: print(
        f"\n[EVENT] Health warning! {pct:.0%}"
    ))
    reader.on("buff_gained", lambda b: print(
        f"\n[EVENT] Buff gained: {b['name']}"
    ))
    reader.on("buff_lost", lambda name: print(
        f"\n[EVENT] Buff lost: {name}"
    ))

    if "--watch" in sys.argv:
        # Continuous monitoring mode — poll thread is already running
        print("\nWatching game state (Ctrl+C to stop)...\n")
        try:
            while True:
                snap = reader.snapshot
                print(f"[{snap.age:.0f}ms ago]")
                reader.dump_player_info()
                reader.dump_target_info()
                print("-" * 40)
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopped.")
    else:
        # One-shot: wait for first snapshot then dump
        time.sleep(0.2)
        reader.dump_player_info()
        reader.dump_target_info()

    reader.disconnect()
