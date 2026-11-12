"""Fixed rows when tools fit; discrete pages when a terminal is smaller."""
import curses
import unicodedata


def cell_width(text):
    return sum(0 if unicodedata.combining(c) else 2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def clip(text, cells):
    result = ""
    for char in text:
        if cell_width(result + char) > cells:
            break
        result += char
    return result


def dimensions(tools):
    icons = any(t["icon"] for t in tools)
    width = max(44, max(cell_width(t["name"]) for t in tools) + 14 + (4 if icons else 0))
    return min(width, 100), len(tools) + 7


def page_for(selected, capacity):
    return selected // capacity * capacity


def draw(screen, tools):
    curses.curs_set(0)
    curses.set_escdelay(25)
    screen.keypad(True)
    screen.scrollok(False)
    colored = curses.has_colors()
    if colored:
        curses.start_color()
        curses.use_default_colors()
        # Accent, active accent and active text share the same active background.
        curses.init_pair(1, 116 if curses.COLORS >= 256 else curses.COLOR_CYAN, -1)
        curses.init_pair(2, 116 if curses.COLORS >= 256 else curses.COLOR_CYAN, 60 if curses.COLORS >= 256 else curses.COLOR_BLUE)
        curses.init_pair(3, 252 if curses.COLORS >= 256 else curses.COLOR_WHITE, 60 if curses.COLORS >= 256 else curses.COLOR_BLUE)
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
            put(0, 0, "Enlarge terminal; Esc closes")
        else:
            put(0, 2, "TOOLS", curses.A_DIM)
            for i in range(start, min(start + capacity, len(tools))):
                tool = tools[i]
                row = 2 + i - start
                active = i == selected
                bg = (curses.color_pair(3) if colored else curses.A_REVERSE) if active else 0
                accent = curses.color_pair(2 if active else 1) if colored else bg
                put(row, 1, " " * (width - 2), bg)
                put(row, 2, "›" if active else " ", bg)
                name_col = 8 if icons else 4
                if icons:
                    put(row, 4, clip(tool["icon"], 3), accent)
                name = clip(tool["name"], width - name_col - 7)
                put(row, name_col, name, bg | curses.A_BOLD)
                put(row, width - 4, tool["key"], accent | curses.A_BOLD)
            footer = "j/k select · enter open · esc close"
            if len(tools) > capacity:
                footer = f"{selected + 1}/{len(tools)} · PgUp/PgDn · enter open"
            put(height - 2, 2, footer, curses.A_DIM)
        screen.refresh()
        key = screen.get_wch()
        if key in ("q", "\x1b", "\x03"):
            return None
        # While too small, allow only cancellation and resize.
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
