"""
Screen reading utilities for conditional macro logic.
Captures screen regions and analyzes colors/pixels for game state detection.
"""

import math

try:
    import pyautogui
    from PIL import Image
    HAS_SCREEN = True
except ImportError:
    HAS_SCREEN = False


class ScreenReader:
    """Reads screen state for conditional automation logic."""

    def __init__(self, config):
        self.config = config
        screen_cfg = config.get("screen", {})
        self.health_bar = screen_cfg.get("health_bar", [0, 0, 200, 20])
        self.mana_bar = screen_cfg.get("mana_bar", [0, 0, 200, 20])
        self.health_color = tuple(screen_cfg.get("health_color", [0, 200, 0]))
        self.mana_color = tuple(screen_cfg.get("mana_color", [0, 0, 200]))
        self.color_tolerance = screen_cfg.get("color_tolerance", 30)

    def capture_region(self, x, y, width, height):
        """Capture a screen region and return as PIL Image."""
        if not HAS_SCREEN:
            return None
        return pyautogui.screenshot(region=(x, y, width, height))

    def get_pixel_color(self, x, y):
        """Get the RGB color of a pixel at (x, y)."""
        if not HAS_SCREEN:
            return (0, 0, 0)
        img = pyautogui.screenshot(region=(x, y, 1, 1))
        return img.getpixel((0, 0))[:3]

    def colors_match(self, color1, color2, tolerance=None):
        """Check if two RGB colors match within tolerance."""
        tolerance = tolerance or self.color_tolerance
        return all(abs(a - b) <= tolerance for a, b in zip(color1, color2))

    def get_bar_percentage(self, bar_region, bar_color):
        """
        Estimate a bar's fill percentage by scanning pixels left to right.
        Returns float 0.0 - 1.0.
        """
        if not HAS_SCREEN:
            return 1.0

        x, y, w, h = bar_region
        img = self.capture_region(x, y, w, h)
        if img is None:
            return 1.0

        mid_y = h // 2
        filled_pixels = 0

        for px in range(w):
            pixel = img.getpixel((px, mid_y))[:3]
            if self.colors_match(pixel, bar_color):
                filled_pixels += 1
            else:
                break

        return filled_pixels / w if w > 0 else 1.0

    def get_health_percent(self):
        """Get current health bar percentage (0.0 - 1.0)."""
        return self.get_bar_percentage(self.health_bar, self.health_color)

    def get_mana_percent(self):
        """Get current mana bar percentage (0.0 - 1.0)."""
        return self.get_bar_percentage(self.mana_bar, self.mana_color)

    def find_color_on_screen(self, target_color, region=None, tolerance=None):
        """
        Find the first pixel matching target_color in a region.
        Returns (x, y) or None.
        """
        if not HAS_SCREEN:
            return None

        tolerance = tolerance or self.color_tolerance

        if region:
            rx, ry, rw, rh = region
        else:
            rx, ry, rw, rh = 0, 0, 1920, 1080

        img = self.capture_region(rx, ry, rw, rh)
        if img is None:
            return None

        # Sample every 4th pixel for speed
        for py in range(0, rh, 4):
            for px in range(0, rw, 4):
                pixel = img.getpixel((px, py))[:3]
                if self.colors_match(pixel, target_color, tolerance):
                    return (rx + px, ry + py)

        return None

    def wait_for_color(self, x, y, target_color, timeout=10.0, interval=0.2):
        """Wait until a pixel matches the target color, or timeout."""
        import time
        start = time.time()
        while time.time() - start < timeout:
            current = self.get_pixel_color(x, y)
            if self.colors_match(current, target_color):
                return True
            time.sleep(interval)
        return False

    def pixel_changed(self, x, y, reference_color, tolerance=None):
        """Check if a pixel has changed from a reference color."""
        current = self.get_pixel_color(x, y)
        return not self.colors_match(current, reference_color, tolerance)

    def capture_calibration_point(self):
        """
        Interactive helper: waits for user click and returns position + color.
        Useful for setting up health/mana bar regions.
        """
        if not HAS_SCREEN:
            return None
        print("Move your mouse to the target point and press Enter...")
        input()
        pos = pyautogui.position()
        color = self.get_pixel_color(pos[0], pos[1])
        print(f"Position: ({pos[0]}, {pos[1]}), Color: RGB{color}")
        return {"position": (pos[0], pos[1]), "color": color}
