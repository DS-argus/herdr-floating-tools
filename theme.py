"""Static Herdr custom token inheritance and terminal color allocation.

Herdr 0.9.5 exposes no resolved palette API. Nord is resolved locally; other
named themes use terminal colors plus explicit theme.custom tokens. Automatic
light/dark switching is not observable here and is not claimed supported.
"""
import curses
import os
from pathlib import Path
import re
import tomllib

NORD = dict(bg="#2e3440", fg="#d8dee9", muted="#c2cad6", accent="#88c0d0",
            selected_bg="#434c5e", selected_fg="#eceff4")


def resolve(overrides):
    directory = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    path = Path(os.environ.get("HERDR_CONFIG_PATH", str(directory / "herdr/config.toml")))
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError:
        data = {}
    colors = dict(bg=None, fg=None, muted=None, accent=None, selected_bg=None, selected_fg=None)
    theme = data.get("theme", {})
    if theme.get("name", "").lower() == "nord" and not theme.get("auto_switch", False):
        colors.update(NORD)
    custom = theme.get("custom", {})
    mapping = {"panel_bg": "bg", "text": "fg", "subtext0": "muted", "accent": "accent",
               "selection_bg": "selected_bg"}
    for token, target in mapping.items():
        color = custom.get(token)
        if isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            colors[target] = color.lower()
        elif color in ("reset", "default", "transparent", "none"):
            colors[target] = None
    if "text" in custom:
        colors["selected_fg"] = colors["fg"]
    colors.update(overrides)
    return colors


def rgb(color):
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


class Palette:
    def __init__(self):
        self.cache = {}
        self.next_color = 16
        self.next_pair = 1

    def color(self, value):
        if value is None:
            return -1
        if value in self.cache:
            return self.cache[value]
        red, green, blue = rgb(value)
        if curses.can_change_color() and self.next_color < curses.COLORS:
            index = self.next_color
            self.next_color += 1
            curses.init_color(index, *(round(v * 1000 / 255) for v in (red, green, blue)))
        elif curses.COLORS >= 256:
            levels = (0, 95, 135, 175, 215, 255)
            candidates = [(16 + 36*r + 6*g + b, (rv, gv, bv))
                          for r, rv in enumerate(levels) for g, gv in enumerate(levels) for b, bv in enumerate(levels)]
            candidates += [(232+i, (8+10*i,) * 3) for i in range(24)]
            index = min(candidates, key=lambda item: sum((a-b)**2 for a,b in zip(item[1], (red,green,blue))))[0]
        else:
            index = (1 if red >= 128 else 0) + (2 if green >= 128 else 0) + (4 if blue >= 128 else 0)
            index %= curses.COLORS
        self.cache[value] = index
        return index

    def pair(self, fg, bg):
        index = self.next_pair
        if index >= curses.COLOR_PAIRS:
            raise RuntimeError("Terminal does not support enough color pairs.")
        self.next_pair += 1
        curses.init_pair(index, self.color(fg), self.color(bg))
        return curses.color_pair(index)
