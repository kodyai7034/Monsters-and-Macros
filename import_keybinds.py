"""
Import keybinds from Monsters and Memories controls.json into config.yaml.

Reads the game's controls.json (saved per-character) and updates config.yaml
with the actual keybinds so macros send the correct keys.

Usage:
    python3 import_keybinds.py                    # Auto-detect controls.json
    python3 import_keybinds.py path/to/controls.json
    python3 import_keybinds.py --show             # Show keybinds without writing
"""

import json
import sys
import os
import glob

import yaml


# Unity keycode -> pydirectinput/pyautogui key name
# Reference: https://docs.unity3d.com/ScriptReference/KeyCode.html
UNITY_KEYCODE_MAP = {
    # Letters (97-122 = a-z)
    **{i: chr(i) for i in range(97, 123)},
    # Digits (48-57 = 0-9)
    **{i: chr(i) for i in range(48, 58)},
    # Special keys
    8: "backspace",
    9: "tab",
    13: "return",
    27: "escape",
    32: "space",
    45: "-",
    61: "=",
    91: "[",
    93: "]",
    92: "\\",
    59: ";",
    39: "'",
    44: ",",
    46: ".",
    47: "/",
    96: "`",
    127: "delete",
    # Arrow keys
    273: "up",
    274: "down",
    275: "right",
    276: "left",
    # Function keys (282-293 = F1-F12)
    **{282 + i: f"f{i+1}" for i in range(12)},
    # Numpad (256-265 = Num0-Num9)
    **{256 + i: f"num{i}" for i in range(10)},
    266: "decimal",
    267: "numlock",
    # Modifiers
    303: "rshift",
    304: "lshift",
    305: "rctrl",
    306: "lctrl",
    307: "ralt",
    308: "lalt",
    # Other
    277: "insert",
    278: "home",
    279: "end",
    280: "pageup",
    281: "pagedown",
    19: "pause",
    301: "capslock",
    302: "scrolllock",
    316: "printscreen",
    # Numpad operators
    270: "multiply",
    269: "subtract",
    271: "add",
    268: "separator",
    272: "divide",
    # Extra
    326: "numpadenter",
}

# Game control name -> config.yaml keybind name
CONTROL_TO_CONFIG = {
    "forward": "move_forward",
    "back": "move_backward",
    "left": "turn_left",
    "right": "turn_right",
    "leftStrafe": "strafe_left",
    "rightStrafe": "strafe_right",
    "jump": "jump",
    "sit": "sit",
    "crouch": "crouch",
    "assist": "assist",
    "autorun": "auto_run",
    "autoattack": "auto_attack",
    "hail": "hail",
    "consider": "consider",
    "look": "look",
    "tell": "tell",
    "reply": "reply",
    "retell": "retell",
    "party": "party",
    "inventory": "inventory",
    "bags": "bags",
    "abilitiesBook": "abilities_book",
    "skillsWindow": "skills_window",
    "SocialView": "social_window",
    "journalWindow": "journal_window",
    "guildWindow": "guild_window",
    "targetTab": "target_nearest",
    "cycleFriendlyTargets": "target_friendly",
    "targetNearestFriendly": "target_nearest_friendly",
    "targetNearestHostile": "target_nearest_hostile",
    "targetLast": "target_last",
    "targetSelf": "target_self",
    "targetP1": "target_party_1",
    "targetP2": "target_party_2",
    "targetP3": "target_party_3",
    "targetP4": "target_party_4",
    "targetP5": "target_party_5",
    "interact": "interact",
    "inspect": "inspect",
    "interface": "toggle_interface",
    "mainmenu": "main_menu",
    # Abilities
    **{f"ability{i}": f"ability_{i}" for i in range(1, 11)},
    # Hot buttons
    **{f"hotButton{i}": f"hotbutton_{i}" for i in range(1, 13)},
    # Auras
    **{f"aura{i}": f"aura_{i}" for i in range(1, 11)},
    # Host/pet abilities
    **{f"hostAbility{i}": f"host_ability_{i}" for i in range(1, 11)},
}


def find_controls_json():
    """Auto-detect the game's controls.json location."""
    base = os.path.expanduser("~")

    # WSL path
    wsl_pattern = "/mnt/c/Users/*/AppData/LocalLow/Niche Worlds Cult/Monsters and Memories/controls.json"
    matches = glob.glob(wsl_pattern)
    if matches:
        return matches[0]

    # Native Windows path
    locallow = os.environ.get("LOCALAPPDATA", "")
    if locallow:
        # LOCALAPPDATA is AppData/Local, we need AppData/LocalLow
        locallow_path = os.path.join(os.path.dirname(locallow), "LocalLow",
                                     "Niche Worlds Cult", "Monsters and Memories", "controls.json")
        if os.path.exists(locallow_path):
            return locallow_path

    # Try APPDATA (roaming) -> go up to AppData/LocalLow
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        locallow_path = os.path.join(os.path.dirname(appdata), "LocalLow",
                                     "Niche Worlds Cult", "Monsters and Memories", "controls.json")
        if os.path.exists(locallow_path):
            return locallow_path

    return None


def keycode_to_name(keycode):
    """Convert a Unity keycode integer to a key name string."""
    if keycode is None:
        return None
    return UNITY_KEYCODE_MAP.get(keycode, f"unknown_{keycode}")


def format_key_with_modifiers(binding):
    """Format a key binding including shift/ctrl/alt modifiers."""
    key = keycode_to_name(binding.get("key"))
    if key is None:
        return None

    parts = []
    if binding.get("ctrlModifier"):
        parts.append("ctrl")
    if binding.get("shiftModifier"):
        parts.append("shift")
    if binding.get("altModifier"):
        parts.append("alt")
    parts.append(key)

    if len(parts) == 1:
        return parts[0]
    return "+".join(parts)


def parse_controls(controls_path):
    """Parse the game's controls.json and return a keybind dict."""
    with open(controls_path) as f:
        data = json.load(f)

    keybinds = {}

    for game_name, config_name in CONTROL_TO_CONFIG.items():
        if game_name not in data:
            continue

        entry = data[game_name]
        if not isinstance(entry, dict) or "key1" not in entry:
            continue

        key1 = format_key_with_modifiers(entry["key1"])
        if key1 is None:
            continue

        keybinds[config_name] = key1

        # Include secondary binding as a comment
        if "key2" in entry:
            key2 = format_key_with_modifiers(entry["key2"])
            if key2:
                keybinds[f"#{config_name}_alt"] = key2

    return keybinds


def show_keybinds(keybinds):
    """Display parsed keybinds in a readable format."""
    print(f"\n  {'Config Key':<30} {'Game Key':<15}")
    print(f"  {'-'*30} {'-'*15}")

    # Group by category
    categories = {
        "Abilities": [k for k in sorted(keybinds) if k.startswith("ability_") and not k.startswith("#")],
        "Hot Buttons": [k for k in sorted(keybinds) if k.startswith("hotbutton_") and not k.startswith("#")],
        "Auras": [k for k in sorted(keybinds) if k.startswith("aura_") and not k.startswith("#")],
        "Movement": [k for k in sorted(keybinds) if k.startswith(("move_", "strafe_", "turn_", "jump", "sit", "crouch", "auto_")) and not k.startswith("#")],
        "Targeting": [k for k in sorted(keybinds) if k.startswith("target_") and not k.startswith("#")],
        "Other": [k for k in sorted(keybinds) if not k.startswith(("#", "ability_", "hotbutton_", "aura_", "move_", "strafe_", "turn_", "jump", "sit", "crouch", "auto_", "target_", "host_"))],
    }

    for cat_name, keys in categories.items():
        if not keys:
            continue
        print(f"\n  {cat_name}:")
        for k in keys:
            print(f"    {k:<28} {keybinds[k]:<15}")


def update_config(keybinds, config_path="config.yaml"):
    """Update config.yaml with imported keybinds."""
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Filter out comment/alt keys
    clean_binds = {k: v for k, v in keybinds.items() if not k.startswith("#")}

    config["keybinds"] = clean_binds

    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    return len(clean_binds)


def main():
    show_only = "--show" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("-")]

    if args:
        controls_path = args[0]
    else:
        controls_path = find_controls_json()

    if not controls_path or not os.path.exists(controls_path):
        print("Could not find controls.json.")
        print("Usage: python3 import_keybinds.py [path/to/controls.json]")
        print("\nExpected location:")
        print("  Windows: %LOCALAPPDATA%\\..\\LocalLow\\Niche Worlds Cult\\Monsters and Memories\\controls.json")
        print("  WSL:     /mnt/c/Users/<user>/AppData/LocalLow/Niche Worlds Cult/Monsters and Memories/controls.json")
        sys.exit(1)

    print(f"Reading: {controls_path}")
    keybinds = parse_controls(controls_path)
    print(f"Found {len([k for k in keybinds if not k.startswith('#')])} keybinds")

    show_keybinds(keybinds)

    if show_only:
        return

    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")
    count = update_config(keybinds, config_path)
    print(f"\nUpdated {config_path} with {count} keybinds.")


if __name__ == "__main__":
    main()
