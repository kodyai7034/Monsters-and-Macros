# Map & Calibration System

## Overview

`map_tab.py` provides a map exploration UI in the GUI. It tracks the player's position on a 2D canvas (XZ plane), overlays a zone background image, and supports coordinate calibration.

## Zone Detection

- Reads zone name from memory via `ZoneController.currentZoneHid` (e.g., "nightharbor")
- Auto-starts tracking on tab load with 500ms delay
- Fuzzy-matches zone name against `maps/zone_maps.json` entries
- Loads background image from `maps/backgrounds/` directory

## Map Calibration (2-Point Linear Transform)

Maps game world coordinates to image pixel positions.

### How It Works

Two known reference points define a linear transform:

```
image_pixel_x = game_x * scale_x + offset_x
image_pixel_y = game_z * scale_z + offset_z
```

Scale and offset computed from two calibration points:
```
scale_x = (p2_pixel_x - p1_pixel_x) / (p2_game_x - p1_game_x)
offset_x = p1_pixel_x - p1_game_x * scale_x
```

### User Flow

1. Click "Calibrate" button
2. Click a recognizable point on the map image
3. Enter the game coordinates at that point (stand there in-game)
4. Click a second point, enter its coordinates
5. Calibration saved to `maps/<zone>.json`

### Data Storage

Per-zone JSON in `maps/` directory:

```json
{
  "points": [[x, y, z, timestamp], ...],
  "calibration": {
    "p1_game": [gx, gz],
    "p1_pixel": [px, py],
    "p2_game": [gx, gz],
    "p2_pixel": [px, py]
  },
  "background": "backgrounds/Night_Harbor.jpg"
}
```

## Zone Map Config

`maps/zone_maps.json` maps zone HID names to background images:

```json
{
  "zones": {
    "nightharbor": {"background": "backgrounds/Night_Harbor.jpg"},
    "keepersbight": {"background": "backgrounds/Keepers_Bight.png"}
  }
}
```

Entries use lowercase HID names matching game memory format.

## Key Methods (MapTab class)

- `_start_calibration()` — Enters calibration mode (crosshair cursor)
- `_on_calibration_click()` — Handles click during calibration
- `_load_calibration()` — Loads saved calibration from JSON
- `_game_to_image(gx, gz)` — Transform game coords to image pixels
- `_game_to_canvas(gx, gz)` — Game coords to canvas position (with pan/zoom)
- `_center_view(gx, gz)` — Center canvas on game position
- `_auto_start_tracking()` — Auto-start on tab load
