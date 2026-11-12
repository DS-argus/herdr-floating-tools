import curses
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
import config
import floating_tools as app
import menu


def raw(**kwargs):
    return dict(id="git", key="g", name="Git", command=["lazygit"], **kwargs)


class ConfigurationTests(unittest.TestCase):
    def test_example_and_defaults(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, HERDR_PLUGIN_CONFIG_DIR=directory):
            tools = config.load_config()["tools"]
            self.assertEqual(len(tools), 6)
            self.assertEqual(tools[0]["width"], "80%")
            self.assertTrue(tools[0]["close_on_exit"])

    def test_invalid_configuration_never_falls_back(self):
        invalid = [[], {}, {"tools": []}, {"tools": [raw(), raw()]}, {"tools": [raw()], "typo": 1}]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(config.ConfigError):
                config.validate_config(value)
        for field, value in [("key", "j"), ("key", "GG"), ("id", "../bad"), ("name", "bad\x1b"),
                             ("icon", "bad\n"), ("command", "sh -c evil"), ("command", [""]),
                             ("command", ["test", "\0"]), ("cwd", ""), ("width", True),
                             ("width", "101%"), ("height", 0), ("close_on_exit", "false")]:
            tool = raw(); tool[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(config.ConfigError):
                config.validate_tool(tool)
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, HERDR_PLUGIN_CONFIG_DIR=directory):
            (Path(directory) / "config.toml").write_text("[")
            with self.assertRaises(config.ConfigError): config.load_config()["tools"]

    def test_cwd_resolution(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve(); (base / "한글 space").mkdir()
            self.assertEqual(config.resolve_cwd(raw(cwd="한글 space"), str(base)), str(base / "한글 space"))
            self.assertEqual(config.resolve_cwd(raw(), str(base)), str(base))
            with self.assertRaises(config.ConfigError): config.resolve_cwd(raw(cwd="absent"), str(base))

    def test_source_uses_context_not_plugin_directory(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, HERDR_PLUGIN_CONTEXT_JSON=json.dumps({"focused_pane_cwd": directory})):
            self.assertEqual(app.source_cwd(), directory)
        with patch.dict(os.environ, HERDR_PLUGIN_CONTEXT_JSON="{}"), self.assertRaises(config.ConfigError): app.source_cwd()

    def test_payload_is_bounded(self):
        with self.assertRaises(config.ConfigError): app.encode("한" * 16000)


class LifecycleTests(unittest.TestCase):
    def test_popup_sizing_and_busy_retry(self):
        busy = {"error": {"code": "ui_busy"}}
        with patch.object(app, "api", side_effect=[busy, {"result": {}}]) as api, patch.object(app.time, "sleep"):
            app.open_popup("tool", "/tmp", "90%", 20, {}, True)
            params = api.call_args.args[1]
            self.assertEqual((params["width"], params["height"]), ("90%", 20))
            self.assertNotIn("target_pane_id", params)
        with patch.object(app, "api", return_value=busy) as api, patch.object(app.time, "sleep"), self.assertRaises(RuntimeError):
            app.open_popup("tool", "/tmp", 40, 20, {}, True)
        self.assertEqual(api.call_count, 40)
        with patch.object(app, "api", return_value=busy), self.assertRaises(RuntimeError):
            app.open_popup("menu", "/tmp", 40, 20, {})

    def test_launch_selection_cancel_and_invalid_selection(self):
        for selection in ("git", "", "missing"):
            with self.subTest(selection=selection), tempfile.TemporaryDirectory() as directory:
                calls = []; threads = []
                def open_popup(entry, cwd, width, height, env, retry_busy=False):
                    calls.append((entry, cwd, width, height, env))
                    if entry == "menu":
                        def choose():
                            with socket.socket(socket.AF_UNIX) as client:
                                client.connect(env["FLOATING_SOCKET"])
                                # Send in pieces to exercise stream framing.
                                for char in selection: client.sendall(char.encode())
                        thread = threading.Thread(target=choose); thread.start(); threads.append(thread)
                with patch.object(app, "load_config", return_value={"tools": [config.validate_tool(raw(width=60, height="70%"))], "theme": {}}), patch.object(app, "source_cwd", return_value=directory), patch.object(app, "open_popup", side_effect=open_popup):
                    if selection == "missing":
                        with self.assertRaises(RuntimeError): app.launch()
                    else: app.launch()
                for thread in threads: thread.join(timeout=2); self.assertFalse(thread.is_alive())
                self.assertFalse(Path(calls[0][4]["FLOATING_SOCKET"]).exists())
                if selection == "git":
                    self.assertEqual(calls[1][:4], ("tool", str(Path(directory).resolve()), 60, "70%"))
                else: self.assertEqual(len(calls), 1)

    def test_execute_argv_and_retained_exit_status(self):
        tool = config.validate_tool(raw(close_on_exit=False))
        tool["command"] = ["test", "$(id)", "space arg"]
        with patch.object(app.shutil, "which", return_value="/usr/bin/test"), patch.object(subprocess, "run", return_value=subprocess.CompletedProcess([], 7)) as run, patch("builtins.input") as wait, patch("builtins.print"):
            self.assertEqual(app.execute(tool), 7)
            run.assert_called_once_with(["/usr/bin/test", "$(id)", "space arg"], check=False)
            wait.assert_called_once()
        tool["close_on_exit"] = True
        with patch.object(app.shutil, "which", return_value="/usr/bin/test"), patch.object(os, "execvpe", side_effect=SystemExit) as execute:
            with self.assertRaises(SystemExit): app.execute(tool)
            self.assertEqual(execute.call_args.args[1], ["/usr/bin/test", "$(id)", "space arg"])
        with patch.object(app.shutil, "which", return_value=None), self.assertRaises(RuntimeError): app.execute(tool)


class MenuTests(unittest.TestCase):
    def test_dimensions_and_unicode_clipping(self):
        tools = [config.validate_tool(raw())]
        small = menu.dimensions(tools)
        self.assertGreater(menu.dimensions(tools * 20)[1], small[1])
        tools[0]["name"] = "한글" * 30
        self.assertGreater(menu.dimensions(tools)[0], small[0])
        self.assertEqual(menu.clip("한글abc", 5), "한글a")
        self.assertEqual(menu.page_for(7, 6), 6)

    def test_fixed_rows_pagination_and_shared_highlight(self):
        tools = [config.validate_tool({"id": str(i), "key": str(i), "name": "Tool", "icon": "󰊢", "command": ["test"]}) for i in range(8)]
        class Screen:
            def __init__(self): self.keys = iter(["j"] * 7 + ["\n"]); self.frames = []
            def keypad(self, value): pass
            def bkgd(self, char, attr): pass
            def scrollok(self, value): self.scrolling = value
            def getmaxyx(self): return 11, 44
            def erase(self): self.frames.append([])
            def addstr(self, r, c, text, attr=0): self.frames[-1].append((r, c, text, attr))
            def refresh(self): pass
            def get_wch(self): return next(self.keys)
        screen = Screen(); pairs = {}
        from contextlib import ExitStack
        with ExitStack() as stack:
            for name in ("curs_set", "set_escdelay", "start_color", "use_default_colors"):
                stack.enter_context(patch.object(curses, name))
            stack.enter_context(patch.object(curses, "has_colors", return_value=True))
            stack.enter_context(patch.object(curses, "COLORS", 256, create=True))
            stack.enter_context(patch.object(curses, "COLOR_PAIRS", 256, create=True))
            stack.enter_context(patch.object(curses, "can_change_color", return_value=False))
            stack.enter_context(patch.object(menu, "resolve", return_value={"bg": "#2e3440", "fg": "#d8dee9", "muted": "#c2cad6", "accent": "#88c0d0", "selected_bg": "#434c5e", "selected_fg": "#eceff4"}))
            stack.enter_context(patch.object(curses, "color_pair", side_effect=lambda i: i << 8))
            stack.enter_context(patch.object(curses, "init_pair", side_effect=lambda i, fg, bg: pairs.update({i: bg})))
            self.assertEqual(menu.draw(screen, tools), "7")
        self.assertFalse(screen.scrolling)
        for frame in screen.frames:
            row = next(r for r, c, t, a in frame if c == 2 and t == "›")
            self.assertEqual({pairs[(a >> 8) & 255] for r, c, t, a in frame if r == row}, {pairs[3]})


if __name__ == "__main__": unittest.main()
