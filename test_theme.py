import curses
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import config
import menu
import theme


class ThemeTests(unittest.TestCase):
    def test_description_and_color_validation(self):
        raw = dict(id="git", key="g", name="Git", command=["git", "secret argument"], color="#D08770", description="Git status")
        tool = config.validate_tool(raw)
        self.assertEqual(tool["color"], "#d08770")
        self.assertEqual(tool["description"], "Git status")
        for field, value in (("color", "red"), ("color", 12), ("description", "bad\n")):
            with self.subTest(field=field), self.assertRaises(config.ConfigError):
                config.validate_tool(raw | {field: value})
        for value in ({"bad": "#ffffff"}, {"selected_bg": "red"}, []):
            with self.assertRaises(config.ConfigError): config.validate_theme(value)
        del raw["description"]
        self.assertEqual(config.validate_tool(raw)["description"], "")

    def test_herdr_nord_custom_and_plugin_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "herdr.toml"
            path.write_text('[theme]\nname="nord"\n[theme.custom]\ntext="#c2cad6"\nselection_bg="#3b4252"\naccent="#81a1c1"\n')
            with patch.dict(os.environ, HERDR_CONFIG_PATH=str(path)):
                colors = theme.resolve({"selected_bg": "#434c5e", "selected_fg": "#eceff4"})
                self.assertEqual(colors["bg"], "#2e3440")
                self.assertEqual(colors["fg"], "#c2cad6")
                self.assertEqual(colors["accent"], "#81a1c1")
                self.assertEqual(colors["selected_bg"], "#434c5e")
                self.assertEqual(colors["selected_fg"], "#eceff4")
            path.write_text('[theme]\nname="nord"\nauto_switch=true\n')
            with patch.dict(os.environ, HERDR_CONFIG_PATH=str(path)):
                self.assertIsNone(theme.resolve({})["bg"])

    def test_description_truncation_keeps_key_column(self):
        tool = config.validate_tool(dict(id="git", key="g", icon="󰊢", name="Git", description="긴 설명 " * 30, command=["git"]))
        for width in (24, 44, 80):
            nc, nw, dc, dw = menu.columns([tool], width)
            rendered = menu.truncate(tool["description"], dw)
            self.assertLessEqual(menu.cell_width(rendered), dw)
            self.assertLessEqual(dc + dw, width - 4)
            if dw: self.assertTrue(rendered.endswith("…"))
        self.assertEqual(menu.truncate("abc", 0), "")
        self.assertEqual(menu.truncate("한글", 3), "한…")

    def test_precise_palette_and_no_reserved_ansi_mutation(self):
        with patch.object(curses, "can_change_color", return_value=True), patch.object(curses, "COLORS", 256, create=True), patch.object(curses, "init_color") as init:
            palette = theme.Palette()
            index = palette.color("#d08770")
            self.assertEqual(index, 16)
            self.assertEqual(palette.color("#d08770"), index)
            init.assert_called_once_with(16, 816, 529, 439)
        with patch.object(curses, "can_change_color", return_value=False), patch.object(curses, "COLORS", 256, create=True):
            self.assertEqual(theme.Palette().color("#000000"), 16)


if __name__ == "__main__": unittest.main()
