"""
Map tab for the MnM Macro Tool GUI.
Records player coordinates as they explore and renders a self-built map.
Supports loading community map images as backgrounds with coordinate calibration.
"""

import os
import json
import math
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


ZONE_MAPS_FILE = os.path.join("maps", "zone_maps.json")


def _load_zone_map_config():
    """Load the zone-to-background-image mapping from zone_maps.json."""
    if os.path.exists(ZONE_MAPS_FILE):
        try:
            with open(ZONE_MAPS_FILE, "r") as f:
                data = json.load(f)
            return data.get("zones", {})
        except (json.JSONDecodeError, IOError):
            pass
    return {}


class MapData:
    """Stores and persists explored coordinates per zone."""

    SAVE_DIR = "maps"

    def __init__(self):
        self.zones = {}  # {zone_name: {"points": [(x, y, z, timestamp), ...], "calibration": {...}}}
        self._zone_map_config = _load_zone_map_config()
        os.makedirs(self.SAVE_DIR, exist_ok=True)

    def add_point(self, zone, x, y, z, timestamp=0.0):
        """Record an explored coordinate."""
        if zone not in self.zones:
            self.zones[zone] = {"points": [], "calibration": None, "background": None}
        points = self.zones[zone]["points"]
        # Skip if too close to last recorded point (< 2 units)
        if points:
            lx, _, lz, _ = points[-1]
            if (x - lx) ** 2 + (z - lz) ** 2 < 4.0:
                return False
        points.append((x, y, z, timestamp))
        return True

    def get_points(self, zone):
        """Get all recorded points for a zone."""
        if zone not in self.zones:
            return []
        return self.zones[zone]["points"]

    def get_bounds(self, zone):
        """Get (min_x, min_z, max_x, max_z) for a zone's explored area."""
        points = self.get_points(zone)
        if not points:
            return (0, 0, 0, 0)
        xs = [p[0] for p in points]
        zs = [p[2] for p in points]
        return (min(xs), min(zs), max(xs), max(zs))

    def set_background(self, zone, image_path):
        """Set a background map image for a zone."""
        if zone not in self.zones:
            self.zones[zone] = {"points": [], "calibration": None, "background": None}
        self.zones[zone]["background"] = image_path

    def set_calibration(self, zone, cal):
        """Set coordinate-to-pixel calibration for a zone's background.

        cal = {"p1_game": (gx, gz), "p1_pixel": (px, py),
               "p2_game": (gx, gz), "p2_pixel": (px, py)}
        """
        if zone in self.zones:
            self.zones[zone]["calibration"] = cal

    def save(self, zone=None):
        """Save zone data to disk."""
        zones_to_save = [zone] if zone else list(self.zones.keys())
        for z in zones_to_save:
            if z not in self.zones:
                continue
            safe_name = z.replace(" ", "_").replace("/", "_")
            filepath = os.path.join(self.SAVE_DIR, f"{safe_name}.json")
            with open(filepath, "w") as f:
                json.dump(self.zones[z], f, indent=2)

    def load(self, zone):
        """Load zone data from disk."""
        safe_name = zone.replace(" ", "_").replace("/", "_")
        filepath = os.path.join(self.SAVE_DIR, f"{safe_name}.json")
        if os.path.exists(filepath):
            with open(filepath, "r") as f:
                self.zones[zone] = json.load(f)
            return True
        return False

    def load_all(self):
        """Load all saved zone data (excludes zone_maps.json and backgrounds/)."""
        if not os.path.isdir(self.SAVE_DIR):
            return
        for f in os.listdir(self.SAVE_DIR):
            if f.endswith(".json") and f != "zone_maps.json":
                zone_name = f[:-5].replace("_", " ")
                filepath = os.path.join(self.SAVE_DIR, f)
                try:
                    with open(filepath, "r") as fh:
                        self.zones[zone_name] = json.load(fh)
                except (json.JSONDecodeError, IOError):
                    pass

    def get_background_path(self, zone):
        """Get background image path for a zone.

        Checks: 1) zone's own 'background' field, 2) zone_maps.json config.
        Returns absolute path or None.
        """
        # Check if zone data has a manually-set background
        if zone in self.zones:
            bg = self.zones[zone].get("background")
            if bg and os.path.exists(bg):
                return bg

        # Check zone_maps.json config — try exact name, then fuzzy variations
        match = self._find_zone_config(zone)
        if match:
            rel_path = match.get("background", "")
            abs_path = os.path.join(self.SAVE_DIR, rel_path) if not os.path.isabs(rel_path) else rel_path
            if os.path.exists(abs_path):
                return abs_path

        return None

    def _find_zone_config(self, zone):
        """Find zone config entry with flexible name matching."""
        # Exact match
        if zone in self._zone_map_config:
            return self._zone_map_config[zone]

        # Case-insensitive match
        zone_lower = zone.lower()
        for key, val in self._zone_map_config.items():
            if key.lower() == zone_lower:
                return val

        # Try normalizing: remove spaces/underscores and compare
        zone_norm = zone_lower.replace(" ", "").replace("_", "")
        for key, val in self._zone_map_config.items():
            key_norm = key.lower().replace(" ", "").replace("_", "")
            if key_norm == zone_norm:
                return val

        return None

    def get_zone_names(self):
        """Get all zone names with data."""
        return sorted(self.zones.keys())


class MapTab(ttk.Frame):
    """Map display tab — shows explored areas and player position."""

    # Drawing constants
    POINT_COLOR = "#4488ff"
    TRAIL_COLOR = "#2266cc"
    PLAYER_COLOR = "#ff4444"
    GRID_COLOR = "#333333"
    BG_COLOR = "#1a1a2e"
    TEXT_COLOR = "#aaaaaa"
    PLAYER_SIZE = 6
    POINT_SIZE = 2
    PADDING = 40  # pixels of padding around map content

    def __init__(self, parent, memory_reader=None, log_callback=None):
        super().__init__(parent)
        self.memory = memory_reader
        self.log = log_callback or (lambda msg: None)
        self.map_data = MapData()
        self.map_data.load_all()

        self._tracking = False
        self._current_zone = ""
        self._player_x = 0.0
        self._player_z = 0.0
        self._player_y = 0.0
        self._first_position = True  # Center view on first position received

        # View state
        self._view_offset_x = 0.0  # pan offset in pixels
        self._view_offset_y = 0.0
        self._zoom = 1.0
        self._drag_start = None

        # Background image
        self._bg_image = None  # PhotoImage reference
        self._bg_image_size = (0, 0)  # (width, height) of loaded image

        # Calibration state
        self._calibrating = False
        self._cal_point_1 = None  # (img_x, img_y, game_x, game_z)
        # Resolved calibration transform: maps game coords <-> image pixels
        # Set after 2-point calibration: scale_x, scale_z, offset_x, offset_z
        self._cal_transform = None  # (scale_x, scale_z, offset_x, offset_z)

        self._build_ui()

        # Auto-start tracking once the GUI is ready
        self.after(500, self._auto_start_tracking)

    def _auto_start_tracking(self):
        """Automatically start tracking if memory reader is connected."""
        if self.memory and self.memory.connected and not self._tracking:
            self._tracking = True
            self.track_btn.config(text="Stop Tracking")
            self.log("Map tracking auto-started")
            self._poll_position()

    def _build_ui(self):
        # Top controls
        ctrl = ttk.Frame(self)
        ctrl.pack(fill="x", padx=5, pady=5)

        self.track_btn = ttk.Button(ctrl, text="Start Tracking", command=self._toggle_tracking)
        self.track_btn.pack(side="left", padx=2)

        ttk.Button(ctrl, text="Center", command=self._center_view).pack(side="left", padx=2)
        ttk.Button(ctrl, text="Fit All", command=self._fit_all).pack(side="left", padx=2)

        ttk.Separator(ctrl, orient="vertical").pack(side="left", fill="y", padx=8)

        ttk.Label(ctrl, text="Zone:").pack(side="left", padx=2)
        self.zone_var = tk.StringVar()
        self.zone_combo = ttk.Combobox(ctrl, textvariable=self.zone_var, width=20, state="readonly")
        self.zone_combo.pack(side="left", padx=2)
        self.zone_combo.bind("<<ComboboxSelected>>", self._on_zone_selected)
        self._refresh_zone_list()

        ttk.Separator(ctrl, orient="vertical").pack(side="left", fill="y", padx=8)

        ttk.Button(ctrl, text="Load Background", command=self._load_background).pack(side="left", padx=2)
        self.cal_btn = ttk.Button(ctrl, text="Calibrate", command=self._start_calibration)
        self.cal_btn.pack(side="left", padx=2)
        ttk.Button(ctrl, text="Save Map Data", command=self._save_all).pack(side="left", padx=2)
        ttk.Button(ctrl, text="Clear Zone", command=self._clear_zone).pack(side="left", padx=2)

        # Coordinate display
        self.coord_var = tk.StringVar(value="Position: --")
        ttk.Label(ctrl, textvariable=self.coord_var, font=("Consolas", 9)).pack(side="right", padx=5)

        # Calibration status
        self.cal_var = tk.StringVar(value="")
        self.cal_label = ttk.Label(ctrl, textvariable=self.cal_var, font=("Consolas", 9), foreground="orange")
        self.cal_label.pack(side="right", padx=5)

        # Point count
        self.points_var = tk.StringVar(value="Points: 0")
        ttk.Label(ctrl, textvariable=self.points_var, font=("Consolas", 9)).pack(side="right", padx=5)

        # Canvas
        self.canvas = tk.Canvas(self, bg=self.BG_COLOR, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=5, pady=(0, 5))

        # Mouse bindings for pan/zoom
        self.canvas.bind("<ButtonPress-1>", self._on_drag_start)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<MouseWheel>", self._on_scroll)  # Windows
        self.canvas.bind("<Button-4>", lambda e: self._on_scroll_linux(e, 1))  # Linux scroll up
        self.canvas.bind("<Button-5>", lambda e: self._on_scroll_linux(e, -1))  # Linux scroll down

    def set_memory_reader(self, reader):
        """Set or update the memory reader reference."""
        self.memory = reader

    def _toggle_tracking(self):
        if self._tracking:
            self._tracking = False
            self.track_btn.config(text="Start Tracking")
            self.log("Map tracking stopped")
            self._save_all()
        else:
            if not self.memory or not self.memory.connected:
                messagebox.showwarning("Not Connected",
                    "Memory reader not connected to game.\n"
                    "Click 'Connect' in the status bar first.")
                return
            self._tracking = True
            self.track_btn.config(text="Stop Tracking")
            self.log("Map tracking started")
            self._poll_position()

    def _poll_position(self):
        """Poll player position from memory reader and record it."""
        if not self._tracking:
            return

        if self.memory and self.memory.connected:
            snap = self.memory.snapshot
            if snap.player:
                self._player_x = snap.player_x
                self._player_y = snap.player_y
                self._player_z = snap.player_z

                # Use zone from snapshot or fallback
                zone = snap.zone_name if snap.zone_name else "Unknown"
                if zone != self._current_zone and zone != "Unknown":
                    self._current_zone = zone
                    self.zone_var.set(zone)
                    self._refresh_zone_list()
                    self._load_zone_background(zone)
                    self.log(f"Zone changed: {zone}")

                if not self._current_zone:
                    self._current_zone = zone
                    self.zone_var.set(zone)
                    self._refresh_zone_list()
                    self._load_zone_background(zone)
                    self.log(f"Zone detected: {zone}")

                if self._current_zone:
                    import time
                    added = self.map_data.add_point(
                        self._current_zone,
                        self._player_x, self._player_y, self._player_z,
                        time.time()
                    )

                # Auto-center view on first valid position
                if self._first_position and self._player_x != 0.0:
                    self._first_position = False
                    self._center_view()

                self.coord_var.set(
                    f"Position: ({self._player_x:.1f}, {self._player_y:.1f}, {self._player_z:.1f})"
                )
                pts = self.map_data.get_points(self._current_zone)
                self.points_var.set(f"Points: {len(pts)}")

                self._redraw()

        # Poll every 250ms (4 Hz is plenty for mapping)
        self.after(250, self._poll_position)

    def _refresh_zone_list(self):
        zones = self.map_data.get_zone_names()
        self.zone_combo["values"] = zones
        if self._current_zone and self._current_zone in zones:
            self.zone_var.set(self._current_zone)

    def _on_zone_selected(self, event=None):
        zone = self.zone_var.get()
        if zone:
            self._current_zone = zone
            self._load_zone_background(zone)
            self._fit_all()

    # =====================================================================
    # Coordinate transforms
    # =====================================================================

    def _game_to_canvas(self, gx, gz):
        """Convert game coordinates to canvas pixel coordinates.

        When calibrated with a background image, maps through image pixel space.
        Otherwise, uses raw game coordinates with zoom/pan.
        """
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()

        if self._cal_transform and self._bg_image:
            # Calibrated: game -> image pixel -> canvas
            img_pos = self._game_to_image(gx, gz)
            if img_pos:
                ix, iy = img_pos
                # Image pixels are centered on canvas, then zoom/pan applied
                cx = cw / 2 + (ix - self._bg_image_size[0] / 2) * self._zoom + self._view_offset_x
                cy = ch / 2 + (iy - self._bg_image_size[1] / 2) * self._zoom + self._view_offset_y
                return cx, cy

        # Uncalibrated: raw game coords with zoom/pan
        cx = cw / 2 + (gx * self._zoom) + self._view_offset_x
        cy = ch / 2 + (gz * self._zoom) + self._view_offset_y
        return cx, cy

    def _canvas_to_game(self, cx, cy):
        """Convert canvas pixel coordinates back to game coordinates."""
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()

        if self._cal_transform and self._bg_image:
            # Reverse: canvas -> image pixel -> game
            ix = (cx - cw / 2 - self._view_offset_x) / self._zoom + self._bg_image_size[0] / 2
            iy = (cy - ch / 2 - self._view_offset_y) / self._zoom + self._bg_image_size[1] / 2
            scale_x, scale_z, offset_x, offset_z = self._cal_transform
            gx = (ix - offset_x) / scale_x if scale_x != 0 else 0
            gz = (iy - offset_z) / scale_z if scale_z != 0 else 0
            return gx, gz

        gx = (cx - cw / 2 - self._view_offset_x) / self._zoom
        gz = (cy - ch / 2 - self._view_offset_y) / self._zoom
        return gx, gz

    # =====================================================================
    # Drawing
    # =====================================================================

    def _redraw(self):
        """Redraw the entire map canvas."""
        self.canvas.delete("all")
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()

        if cw < 10 or ch < 10:
            return

        # Draw background image if available
        if self._bg_image:
            img_w, img_h = self._bg_image_size
            # Position image: centered on canvas with zoom/pan offset
            img_cx = cw / 2 + self._view_offset_x
            img_cy = ch / 2 + self._view_offset_y
            self.canvas.create_image(img_cx, img_cy, image=self._bg_image, anchor="center")

        # Draw grid
        self._draw_grid()

        # Draw explored points for current zone
        zone = self._current_zone
        if not zone:
            self.canvas.create_text(
                cw / 2, ch / 2, text="No zone selected\nStart tracking or select a zone",
                fill=self.TEXT_COLOR, font=("Consolas", 12), justify="center"
            )
            return

        points = self.map_data.get_points(zone)

        # Draw trail lines between consecutive points
        if len(points) >= 2:
            coords = []
            for p in points:
                cx, cy = self._game_to_canvas(p[0], p[2])
                coords.extend([cx, cy])
            if len(coords) >= 4:
                self.canvas.create_line(
                    *coords, fill=self.TRAIL_COLOR, width=1, smooth=True
                )

        # Draw individual points
        for p in points:
            cx, cy = self._game_to_canvas(p[0], p[2])
            r = self.POINT_SIZE
            self.canvas.create_oval(
                cx - r, cy - r, cx + r, cy + r,
                fill=self.POINT_COLOR, outline=""
            )

        # Draw player position
        if self._tracking and self._player_x != 0.0:
            px, py = self._game_to_canvas(self._player_x, self._player_z)
            r = self.PLAYER_SIZE
            # Outer glow ring
            self.canvas.create_oval(
                px - r * 3, py - r * 3, px + r * 3, py + r * 3,
                fill="", outline=self.PLAYER_COLOR, width=2, dash=(3, 3)
            )
            # Player dot
            self.canvas.create_oval(
                px - r, py - r, px + r, py + r,
                fill=self.PLAYER_COLOR, outline="white", width=2
            )
            # Coordinate label near player
            self.canvas.create_text(
                px + r * 3 + 5, py,
                text=f"({self._player_x:.0f}, {self._player_z:.0f})",
                fill="white", font=("Consolas", 9), anchor="w"
            )

        # Zone label
        self.canvas.create_text(
            10, 10, text=zone, fill=self.TEXT_COLOR,
            font=("Consolas", 11, "bold"), anchor="nw"
        )

        # Scale indicator
        self._draw_scale_bar()

    def _draw_grid(self):
        """Draw a coordinate grid."""
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()

        # Choose grid spacing based on zoom (50, 100, 200, 500 game units)
        base_spacings = [10, 25, 50, 100, 200, 500, 1000]
        grid_spacing = 100
        for s in base_spacings:
            if s * self._zoom >= 40:  # at least 40px between grid lines
                grid_spacing = s
                break

        # Find visible game coordinate range
        g_left, g_top = self._canvas_to_game(0, 0)
        g_right, g_bottom = self._canvas_to_game(cw, ch)

        # Vertical lines (along X axis)
        start_x = int(g_left / grid_spacing) * grid_spacing
        x = start_x
        while x <= g_right:
            cx, _ = self._game_to_canvas(x, 0)
            self.canvas.create_line(cx, 0, cx, ch, fill=self.GRID_COLOR, dash=(2, 4))
            self.canvas.create_text(cx + 2, ch - 5, text=f"{x:.0f}",
                                     fill=self.GRID_COLOR, font=("Consolas", 7), anchor="sw")
            x += grid_spacing

        # Horizontal lines (along Z axis)
        start_z = int(g_top / grid_spacing) * grid_spacing
        z = start_z
        while z <= g_bottom:
            _, cy = self._game_to_canvas(0, z)
            self.canvas.create_line(0, cy, cw, cy, fill=self.GRID_COLOR, dash=(2, 4))
            self.canvas.create_text(5, cy - 2, text=f"{z:.0f}",
                                     fill=self.GRID_COLOR, font=("Consolas", 7), anchor="sw")
            z += grid_spacing

    def _draw_scale_bar(self):
        """Draw a scale bar in the bottom-right corner."""
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()

        # Choose a nice round length
        for length in [10, 25, 50, 100, 200, 500, 1000]:
            px_length = length * self._zoom
            if px_length >= 50:
                break

        bar_x = cw - 20 - px_length
        bar_y = ch - 20

        self.canvas.create_line(bar_x, bar_y, bar_x + px_length, bar_y,
                                 fill=self.TEXT_COLOR, width=2)
        self.canvas.create_line(bar_x, bar_y - 4, bar_x, bar_y + 4,
                                 fill=self.TEXT_COLOR, width=1)
        self.canvas.create_line(bar_x + px_length, bar_y - 4, bar_x + px_length, bar_y + 4,
                                 fill=self.TEXT_COLOR, width=1)
        self.canvas.create_text(bar_x + px_length / 2, bar_y - 8,
                                 text=f"{length} units", fill=self.TEXT_COLOR,
                                 font=("Consolas", 8), anchor="s")

    # =====================================================================
    # Pan / Zoom
    # =====================================================================

    def _on_drag_start(self, event):
        if self._calibrating:
            self._on_calibration_click(event)
            return
        self._drag_start = (event.x, event.y)

    def _on_drag(self, event):
        if self._drag_start:
            dx = event.x - self._drag_start[0]
            dy = event.y - self._drag_start[1]
            self._view_offset_x += dx
            self._view_offset_y += dy
            self._drag_start = (event.x, event.y)
            self._redraw()

    def _on_scroll(self, event):
        """Mouse wheel zoom (Windows)."""
        factor = 1.15 if event.delta > 0 else 1 / 1.15
        self._apply_zoom(factor, event.x, event.y)

    def _on_scroll_linux(self, event, direction):
        """Mouse wheel zoom (Linux)."""
        factor = 1.15 if direction > 0 else 1 / 1.15
        self._apply_zoom(factor, event.x, event.y)

    def _apply_zoom(self, factor, cx, cy):
        """Zoom centered on mouse position."""
        old_zoom = self._zoom
        self._zoom = max(0.01, min(100.0, self._zoom * factor))
        ratio = self._zoom / old_zoom

        # Adjust offset so the point under the mouse stays fixed
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        self._view_offset_x = cx - cw / 2 - (cx - cw / 2 - self._view_offset_x) * ratio
        self._view_offset_y = cy - ch / 2 - (cy - ch / 2 - self._view_offset_y) * ratio

        self._redraw()

    def _center_view(self):
        """Center view on player position."""
        if self._player_x == 0.0 and self._player_z == 0.0:
            self._view_offset_x = 0
            self._view_offset_y = 0
        elif self._cal_transform and self._bg_image:
            # Calibrated: center on player's image-space position
            img_pos = self._game_to_image(self._player_x, self._player_z)
            if img_pos:
                ix, iy = img_pos
                img_w, img_h = self._bg_image_size
                self._view_offset_x = -(ix - img_w / 2) * self._zoom
                self._view_offset_y = -(iy - img_h / 2) * self._zoom
            else:
                self._view_offset_x = 0
                self._view_offset_y = 0
        else:
            self._view_offset_x = -self._player_x * self._zoom
            self._view_offset_y = -self._player_z * self._zoom
        self._redraw()

    def _fit_all(self):
        """Fit all explored points in view."""
        zone = self._current_zone
        if not zone:
            return

        min_x, min_z, max_x, max_z = self.map_data.get_bounds(zone)
        if min_x == max_x and min_z == max_z:
            self._center_view()
            return

        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 10 or ch < 10:
            return

        range_x = max_x - min_x
        range_z = max_z - min_z

        # Add some margin
        range_x = max(range_x, 10) * 1.2
        range_z = max(range_z, 10) * 1.2

        zoom_x = (cw - self.PADDING * 2) / range_x
        zoom_z = (ch - self.PADDING * 2) / range_z
        self._zoom = min(zoom_x, zoom_z)

        center_gx = (min_x + max_x) / 2
        center_gz = (min_z + max_z) / 2
        self._view_offset_x = -center_gx * self._zoom
        self._view_offset_y = -center_gz * self._zoom

        self._redraw()

    # =====================================================================
    # Background image support
    # =====================================================================

    def _load_background(self):
        """Load a background map image for the current zone."""
        if not self._current_zone:
            messagebox.showwarning("No Zone", "Select or start tracking a zone first.")
            return

        filepath = filedialog.askopenfilename(
            title="Load Map Image",
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.gif *.bmp"),
                ("All files", "*.*"),
            ]
        )
        if filepath:
            self.map_data.set_background(self._current_zone, filepath)
            self._load_zone_background(self._current_zone)
            self.log(f"Loaded background map: {os.path.basename(filepath)}")

    def _load_zone_background(self, zone):
        """Load the background image for a zone from zone_maps.json or manual setting."""
        bg_path = self.map_data.get_background_path(zone)
        if bg_path:
            try:
                from PIL import Image, ImageTk
                img = Image.open(bg_path)
                # Scale large images down to reasonable size for display
                max_dim = 2000
                if img.width > max_dim or img.height > max_dim:
                    ratio = min(max_dim / img.width, max_dim / img.height)
                    img = img.resize(
                        (int(img.width * ratio), int(img.height * ratio)),
                        Image.LANCZOS
                    )
                self._bg_image = ImageTk.PhotoImage(img)
                self._bg_image_size = (img.width, img.height)
            except ImportError:
                self.log("Pillow required for background images (pip install Pillow)")
                self._bg_image = None
            except Exception as e:
                self.log(f"Failed to load background: {e}")
                self._bg_image = None
        else:
            self._bg_image = None

        # Load calibration data for this zone
        self._load_calibration(zone)

    # =====================================================================
    # Calibration — 2-point map alignment
    # =====================================================================

    def _start_calibration(self):
        """Enter calibration mode."""
        if not self._current_zone:
            messagebox.showwarning("No Zone", "Select or start tracking a zone first.")
            return
        if not self._bg_image:
            messagebox.showwarning("No Background", "Load a background map image first.")
            return
        if not self._tracking or self._player_x == 0.0:
            messagebox.showwarning("No Position", "Start tracking and wait for a valid position first.")
            return

        self._calibrating = True
        self._cal_point_1 = None
        self.cal_btn.config(text="Cancel Cal.")
        self.cal_var.set("CALIBRATE: Click your location on the map")
        self.canvas.config(cursor="crosshair")
        self.log("Calibration started — click where you are standing on the map image")

    def _cancel_calibration(self):
        """Exit calibration mode without saving."""
        self._calibrating = False
        self._cal_point_1 = None
        self.cal_btn.config(text="Calibrate", command=self._start_calibration)
        self.cal_var.set("")
        self.canvas.config(cursor="")

    def _on_calibration_click(self, event):
        """Handle a click during calibration mode."""
        # Convert canvas click to image pixel coordinates
        # The background is drawn centered, so we need to figure out where
        # in the image the user clicked
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        img_w, img_h = self._bg_image_size

        # Image is drawn at canvas center
        img_left = (cw - img_w) / 2
        img_top = (ch - img_h) / 2

        img_x = event.x - img_left
        img_y = event.y - img_top

        # Check click is within the image
        if img_x < 0 or img_y < 0 or img_x >= img_w or img_y >= img_h:
            self.cal_var.set("Click was outside the map image — try again")
            return

        game_x = self._player_x
        game_z = self._player_z

        if self._cal_point_1 is None:
            # First point
            self._cal_point_1 = (img_x, img_y, game_x, game_z)
            self.cal_var.set(f"Point 1 set ({game_x:.0f}, {game_z:.0f}) — move, then click point 2")
            self.log(f"Calibration point 1: image ({img_x:.0f}, {img_y:.0f}) = game ({game_x:.1f}, {game_z:.1f})")
            # Change button to cancel
            self.cal_btn.config(command=self._cancel_calibration)
        else:
            # Second point
            p1_ix, p1_iy, p1_gx, p1_gz = self._cal_point_1
            p2_ix, p2_iy, p2_gx, p2_gz = img_x, img_y, game_x, game_z

            # Need sufficient distance between points
            dx_game = p2_gx - p1_gx
            dz_game = p2_gz - p1_gz
            dx_img = p2_ix - p1_ix
            dy_img = p2_iy - p1_iy

            if abs(dx_img) < 10 and abs(dy_img) < 10:
                self.cal_var.set("Points too close on image — click further apart")
                return
            if abs(dx_game) < 5 and abs(dz_game) < 5:
                self.cal_var.set("Move further in-game before clicking point 2")
                return

            # Compute scale: image_pixels per game_unit
            # scale_x = dx_img / dx_game (how many image pixels per game X unit)
            # scale_z = dy_img / dz_game (how many image pixels per game Z unit)
            # We need at least one axis to have meaningful distance
            if abs(dx_game) > 1:
                scale_x = dx_img / dx_game
            else:
                scale_x = dy_img / dz_game  # fallback: assume uniform scale

            if abs(dz_game) > 1:
                scale_z = dy_img / dz_game
            else:
                scale_z = dx_img / dx_game  # fallback: assume uniform scale

            # Compute offset: image pixel = game_coord * scale + offset
            # offset = image_pixel - game_coord * scale
            offset_x = p1_ix - p1_gx * scale_x
            offset_z = p1_iy - p1_gz * scale_z

            # Save calibration
            cal_data = {
                "p1_game": [p1_gx, p1_gz],
                "p1_pixel": [p1_ix, p1_iy],
                "p2_game": [p2_gx, p2_gz],
                "p2_pixel": [p2_ix, p2_iy],
                "scale_x": scale_x,
                "scale_z": scale_z,
                "offset_x": offset_x,
                "offset_z": offset_z,
            }
            self.map_data.set_calibration(self._current_zone, cal_data)
            self.map_data.save(self._current_zone)

            self._cal_transform = (scale_x, scale_z, offset_x, offset_z)
            self.log(f"Calibration complete: scale=({scale_x:.2f}, {scale_z:.2f}) offset=({offset_x:.0f}, {offset_z:.0f})")

            # Exit calibration mode
            self._calibrating = False
            self._cal_point_1 = None
            self.cal_btn.config(text="Calibrate", command=self._start_calibration)
            self.cal_var.set("Calibrated")
            self.canvas.config(cursor="")
            self._redraw()

    def _load_calibration(self, zone):
        """Load saved calibration transform for a zone."""
        self._cal_transform = None
        if zone not in self.map_data.zones:
            return
        cal = self.map_data.zones[zone].get("calibration")
        if cal and "scale_x" in cal:
            self._cal_transform = (
                cal["scale_x"], cal["scale_z"],
                cal["offset_x"], cal["offset_z"],
            )

    def _game_to_image(self, gx, gz):
        """Convert game coordinates to image pixel coordinates using calibration."""
        if not self._cal_transform:
            return None
        scale_x, scale_z, offset_x, offset_z = self._cal_transform
        ix = gx * scale_x + offset_x
        iy = gz * scale_z + offset_z
        return ix, iy

    # =====================================================================
    # Zone management
    # =====================================================================

    def _save_all(self):
        """Save all zone map data."""
        self.map_data.save()
        self.log(f"Map data saved ({len(self.map_data.zones)} zones)")

    def _clear_zone(self):
        """Clear explored data for current zone."""
        zone = self._current_zone
        if not zone:
            return
        if messagebox.askyesno("Clear Zone", f"Clear all map data for '{zone}'?"):
            if zone in self.map_data.zones:
                self.map_data.zones[zone]["points"] = []
                self.map_data.save(zone)
            self._redraw()
            self.log(f"Cleared map data for {zone}")

    def on_close(self):
        """Called when the application is closing."""
        if self._tracking:
            self._tracking = False
            self._save_all()
