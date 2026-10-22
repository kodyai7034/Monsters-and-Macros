import unittest

from ui_theme import (
    DEFAULT_SKIN,
    SKINS,
    get_skin,
    get_skin_id,
    get_skin_label,
    skin_options,
)


class DpsSkinTests(unittest.TestCase):
    def test_registry_contains_all_dps_palettes(self):
        self.assertEqual(len(SKINS), 47)
        self.assertEqual(len(skin_options()), len(SKINS))

    def test_dps_skin_colors_map_to_gui_palette(self):
        palette = get_skin("night-harbor")

        self.assertEqual(palette["background"], "#1a1d29")
        self.assertEqual(palette["panel"], "#222635")
        self.assertEqual(palette["accent"], "#d9a640")
        self.assertEqual(palette["bar"], "#d9a640")

    def test_skin_selector_resolves_labels_and_legacy_config(self):
        self.assertEqual(get_skin_id("Night Harbor"), DEFAULT_SKIN)
        self.assertEqual(get_skin_id("Obsidian"), DEFAULT_SKIN)
        self.assertEqual(get_skin_id("Ember"), "ember")
        self.assertEqual(get_skin_id("Frost"), "frost")
        self.assertEqual(get_skin_label("night-harbor"), "Night Harbor")

    def test_unknown_skin_falls_back_to_dps_default(self):
        self.assertEqual(get_skin_id("unknown-skin"), DEFAULT_SKIN)
        self.assertEqual(get_skin_id(None), DEFAULT_SKIN)
        self.assertEqual(get_skin("unknown-skin"), get_skin(DEFAULT_SKIN))


if __name__ == "__main__":
    unittest.main()
