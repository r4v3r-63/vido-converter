import tempfile
import unittest
from pathlib import Path

from preferences import load_theme, save_theme


class PreferencesTest(unittest.TestCase):
    def test_theme_persists_across_launches(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Kadr" / "settings.json"
            self.assertEqual(load_theme(path), "light")
            for theme in ("dark", "light"):
                save_theme(theme, path)
                self.assertEqual(load_theme(path), theme)
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_corrupt_settings_have_safe_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            for content in ("broken", "[]", '{"theme":"unknown"}'):
                path.write_text(content, encoding="utf-8")
                self.assertEqual(load_theme(path), "light")
            with self.assertRaises(ValueError):
                save_theme("unknown", path)
