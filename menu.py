"""Compact fixed rows, clipped description column, and discrete small-screen pages."""
import curses
import unicodedata
from theme import Palette, resolve


def cell_width(text):
    return sum(0 if unicodedata.combining(c) else 2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def clip(text, cells):
    result = ""
    for char in text:
        if cell_width(result + char) > cells:
            break
        result += char
    return result


def truncate(text, cells):
    if cells <= 0:
        return ""
    return text if cell_width(text) <= cells else clip(text, cells - 1) + "…"


def dimensions(tools):
    icons = any(t["icon"] for t in tools)
    name = max(cell_width(t["name"]) for t in tools)
    description = min(30, max(cell_width(t.get("description", "")) for t in tools))
    width = max(46, name + description + (2 if description else 0) + 12 + (3 if icons else 0))
    return min(width, 100), len(tools) + 7


def page_for(selected, capacity):
    return selected // capacity * capacity


def columns(tools, width):
    name_col = 7 if any(t["icon"] for t in tools) else 4
    available = max(0, width - 6 - name_col)
    name_width = min(max(cell_width(t["name"]) for t in tools), available)
    description_width = max(0, available - name_width - 2)
    return name_col, name_width, name_col + name_width + 2, description_width


def draw(screen, tools, overrides=None):
    curses.curs_set(0)
    curses.set_escdelay(25)
    screen.keypad(True)
    screen.scrollok(False)
    colored = curses.has_colors()
    normal, muted, selected_style = 0, curses.A_DIM, curses.A_REVERSE
    accents = [(0, curses.A_REVERSE)] * len(tools)
    if colored:
        curses.start_color()
        curses.use_default_colors()
        colors = resolve(overrides or {})
        palette = Palette()
        normal = palette.pair(colors["fg"], colors["bg"])
        muted = palette.pair(colors["muted"], colors["bg"])
        selected_style = palette.pair(colors["selected_fg"], colors["selected_bg"])
        if colors["selected_bg"] is None:
            selected_style |= curses.A_REVERSE
        accents = []
        for tool in tools:
            color = tool.get("color", colors["accent"])
            active = palette.pair(color, colors["selected_bg"])
            if colors["selected_bg"] is None:
                active |= curses.A_REVERSE
            accents.append((palette.pair(color, colors["bg"]), active))
    # Explicitly fill all cells, including spaces, instead of retaining the pane
    # contents beneath the popup through terminal-default backgrounds.
    screen.bkgd(" ", normal)
    selected = 0
    keys = {t["key"]: i for i, t in enumerate(tools)}
    icons = any(t["icon"] for t in tools)
    while True:
        height, width = screen.getmaxyx()
        screen.erase()
        capacity = max(1, height - 5)
        start = page_for(selected, capacity)
        def put(row, col, text, attr=0):
            if 0 <= row < height and 0 <= col < width - 1:
                screen.addstr(row, col, clip(text, width - col - 1), attr)
        if height < 6 or width < 24:
            put(0, 0, "Enlarge terminal; Esc closes", normal)
        else:
            put(0, 2, "TOOLS", muted)
            name_col, name_width, description_col, description_width = columns(tools, width)
            for i in range(start, min(start + capacity, len(tools))):
                tool = tools[i]
                row = 2 + i - start
                active = i == selected
                style = selected_style if active else normal
                accent = accents[i][1 if active else 0]
                put(row, 1, " " * (width - 2), style)
                put(row, 2, "›" if active else " ", style)
                if icons:
                    put(row, 4, clip(tool["icon"], 2), accent)
                put(row, name_col, truncate(tool["name"], name_width), style | curses.A_BOLD)
                put(row, description_col, truncate(tool.get("description", ""), description_width), selected_style if active else muted)
                put(row, width - 4, tool["key"], accent | curses.A_BOLD)
            footer = "j/k select · enter open · esc close"
            if len(tools) > capacity:
                footer = f"{selected + 1}/{len(tools)} · PgUp/PgDn · enter open"
            put(height - 2, 2, footer, muted)
        screen.refresh()
        key = screen.get_wch()
        if key in ("q", "\x1b", "\x03"):
            return None
        if height < 6 or width < 24:
            continue
        if key in keys:
            return tools[keys[key]]["id"]
        if key in ("\n", "\r", curses.KEY_ENTER):
            return tools[selected]["id"]
        if key in ("j", curses.KEY_DOWN):
            selected = min(len(tools) - 1, selected + 1)
        elif key in ("k", curses.KEY_UP):
            selected = max(0, selected - 1)
        elif key == curses.KEY_NPAGE:
            selected = min(len(tools) - 1, selected + capacity)
        elif key == curses.KEY_PPAGE:
            selected = max(0, selected - capacity)
