"""DPS-meter palettes shared with the macro tool interface."""

import json
import os


DEFAULT_SKIN = "night-harbor"
SKIN_REGISTRY = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "config", "live_meter_skins.json"
)

_FALLBACK_SKINS = {
    "Obsidian": {
        "background": "#10141c",
        "panel": "#191f2b",
        "rowAlt": "#252f40",
        "grid": "#35445a",
        "text": "#e7edf5",
        "muted": "#8b9aaf",
        "accent": "#e0ad4f",
        "header": "#202938",
        "headerText": "#e7edf5",
        "bar": "#e0ad4f",
        "valueText": "#ffcf00",
    },
    "Ember": {
        "background": "#18110f",
        "panel": "#241714",
        "rowAlt": "#3a241d",
        "grid": "#674033",
        "text": "#f3e6dc",
        "muted": "#b69482",
        "accent": "#ef8147",
        "header": "#31201b",
        "headerText": "#f3e6dc",
        "bar": "#ef8147",
        "valueText": "#ef8147",
    },
    "Frost": {
        "background": "#101820",
        "panel": "#17232e",
        "rowAlt": "#263a49",
        "grid": "#3b596a",
        "text": "#e4f2f8",
        "muted": "#91adba",
        "accent": "#73c8dc",
        "header": "#20313e",
        "headerText": "#e4f2f8",
        "bar": "#73c8dc",
        "valueText": "#73c8dc",
    },
}

_LEGACY_SKINS = {
    "Obsidian": DEFAULT_SKIN,
    "Ember": "ember",
    "Frost": "frost",
}


def _contrast_color(color):
    """Return a readable foreground for a hexadecimal accent color."""
    rgb = tuple(int(color[index:index + 2], 16) for index in (1, 3, 5))
    luminance = sum(channel * weight for channel, weight in zip(rgb, (0.299, 0.587, 0.114)))
    return "#101010" if luminance > 150 else "#f5f5f5"


def _normalize_palette(skin):
    required = ("id", "label", "background", "panel", "rowAlt", "grid",
                "text", "muted", "accent", "header", "headerText", "bar")
    if not isinstance(skin, dict) or any(not isinstance(skin.get(key), str) for key in required):
        raise ValueError("DPS skin entries must define id, label, and all required color fields")

    if not skin["id"] or not skin["label"]:
        raise ValueError("DPS skin entries must have a non-empty id and label")
    for key in required[2:]:
        color = skin[key]
        if (len(color) != 7 or not color.startswith("#")
                or any(character not in "0123456789abcdefABCDEF" for character in color[1:])):
            raise ValueError(f"Invalid {key} color in DPS skin {skin['id']!r}")

    return {
        "background": skin["background"],
        "panel": skin["panel"],
        "surface": skin["rowAlt"],
        "row": skin["rowAlt"],
        "border": skin["grid"],
        "text": skin["text"],
        "muted": skin["muted"],
        "accent": skin["accent"],
        "accent_text": _contrast_color(skin["accent"]),
        "danger": "#ff4b5c",
        "selection": skin["header"],
        "header": skin["header"],
        "header_text": skin["headerText"],
        "bar": skin["bar"],
        "value_text": skin.get("valueText", skin["text"]),
    }


def _load_skins():
    if not os.path.isfile(SKIN_REGISTRY):
        legacy = {
            name: _normalize_palette({
                "id": name,
                "label": name,
                **palette,
            })
            for name, palette in _FALLBACK_SKINS.items()
        }
        return legacy, {name: name for name in legacy}

    with open(SKIN_REGISTRY, "r", encoding="utf-8-sig") as skin_file:
        entries = json.load(skin_file)
    if not isinstance(entries, list):
        raise ValueError("DPS skin registry must contain a list of skins")

    skins = {}
    labels = {}
    for entry in entries:
        palette = _normalize_palette(entry)
        skin_id = entry["id"]
        label = entry["label"]
        if skin_id in skins or label in labels:
            raise ValueError(f"Duplicate DPS skin id or label: {skin_id!r} / {label!r}")
        skins[skin_id] = palette
        labels[label] = skin_id

    if not skins:
        raise ValueError("DPS skin registry contains no skins")
    return skins, labels


SKINS, SKIN_LABELS = _load_skins()
_SKINS_BY_LABEL = {label: skin_id for label, skin_id in SKIN_LABELS.items()}


def get_skin_id(name):
    """Resolve a saved id, display label, or legacy palette name to a skin id."""
    if not isinstance(name, str):
        name = ""
    if name in SKINS:
        return name
    if name in _LEGACY_SKINS and _LEGACY_SKINS[name] in SKINS:
        return _LEGACY_SKINS[name]
    if name in _SKINS_BY_LABEL:
        return _SKINS_BY_LABEL[name]
    return DEFAULT_SKIN if DEFAULT_SKIN in SKINS else next(iter(SKINS))


def get_skin_label(name):
    """Return the display label for a saved skin id or legacy palette name."""
    skin_id = get_skin_id(name)
    return next((label for label, key in SKIN_LABELS.items() if key == skin_id), skin_id)


def skin_options():
    """Return DPS skin labels for display in the settings selector."""
    return tuple(SKIN_LABELS)


def get_skin(name):
    """Return the requested DPS palette, accepting ids and legacy names."""
    return SKINS[get_skin_id(name)]
