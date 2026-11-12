#!/usr/bin/env python3
"""Herdr popup tool launcher. No nested modal, shell interpolation or daemon."""
import curses
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time

from config import ConfigError, load_config, resolve_cwd, validate_config, validate_tool
from menu import dimensions, draw

PLUGIN = "ds-argus.floating-tools"
MAX_PAYLOAD = 32000


def encode(value):
    data = json.dumps(value, ensure_ascii=False)
    if len(data.encode()) > MAX_PAYLOAD:
        raise ConfigError("Tool configuration is too large (32 KB maximum).")
    return data


def api(method, params):
    request = {"id": "floating-tools", "method": method, "params": params}
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(10)
        client.connect(os.environ["HERDR_SOCKET_PATH"])
        client.sendall((json.dumps(request) + "\n").encode())
        with client.makefile("r") as stream:
            line = stream.readline(1_048_576)
        response = json.loads(line)
    if not isinstance(response, dict) or not ("error" in response or "result" in response):
        raise RuntimeError("Invalid Herdr API response.")
    return response


def open_popup(entrypoint, cwd, width, height, env, retry_busy=False):
    params = {"plugin_id": PLUGIN, "entrypoint": entrypoint, "placement": "popup",
              "cwd": cwd, "width": width, "height": height, "env": env}
    # Never supply workspace/pane targets: Herdr rejects them for popup placement.
    for attempt in range(40):
        response = api("plugin.pane.open", params)
        error = response.get("error")
        if error is None:
            return
        if not retry_busy or error.get("code") != "ui_busy" or attempt == 39:
            raise RuntimeError(error.get("message", "Herdr could not open the popup."))
        time.sleep(0.05)


def source_cwd():
    context = json.loads(os.environ.get("HERDR_PLUGIN_CONTEXT_JSON", "{}"))
    if not isinstance(context, dict):
        raise ConfigError("Invalid Herdr invocation context.")
    cwd = context.get("focused_pane_cwd")
    if not isinstance(cwd, str) or not Path(cwd).is_absolute() or not Path(cwd).is_dir():
        raise ConfigError("No valid current pane directory. Open this action from a local pane.")
    return cwd


def launch():
    settings = load_config()
    tools = settings["tools"]
    cwd = source_cwd()
    snapshot = encode(settings)
    width, height = dimensions(tools)
    # Capture config and source cwd once. Menu and tool use the same snapshot.
    with tempfile.TemporaryDirectory(prefix="herdr-ft-", dir="/tmp") as directory:
        address = str(Path(directory) / "choice.sock")
        with socket.socket(socket.AF_UNIX) as listener:
            listener.bind(address)
            os.chmod(address, 0o600)
            listener.listen(1)
            listener.settimeout(10)
            open_popup("menu", cwd, width, height,
                       {"FLOATING_SOCKET": address, "FLOATING_CONFIG": snapshot})
            connection, _ = listener.accept()
            with connection:
                connection.settimeout(None)
                # EOF is cancel/crash; IDs are bounded ASCII. Read until EOF to
                # avoid relying on Unix socket packet boundaries.
                data = bytearray()
                while True:
                    chunk = connection.recv(128)
                    if not chunk:
                        break
                    data.extend(chunk)
                    if len(data) > 64:
                        raise RuntimeError("Invalid tool selection.")
        if not data:
            return
        selected = data.decode("ascii")
        tool = next((t for t in tools if t["id"] == selected), None)
        if tool is None:
            raise RuntimeError("Unknown tool selection.")
        directory = resolve_cwd(tool, cwd)
        open_popup("tool", directory, tool["width"], tool["height"],
                   {"FLOATING_TOOL": encode(tool)}, retry_busy=True)


def menu():
    with socket.socket(socket.AF_UNIX) as connection:
        connection.connect(os.environ["FLOATING_SOCKET"])
        settings = json.loads(os.environ["FLOATING_CONFIG"])
        selected = curses.wrapper(draw, validate_config(settings), settings.get("theme", {}))
        if selected is not None:
            connection.sendall(selected.encode("ascii"))


def execute(tool):
    command = list(tool["command"])
    if command[0].startswith("~/"):
        command[0] = str(Path(command[0]).expanduser())
    executable = shutil.which(command[0])
    if executable is None:
        raise RuntimeError("Tool executable not found. Install it or check command and PATH.")
    command[0] = executable
    if tool["close_on_exit"]:
        # Popup owns the tool directly. Closing it follows Herdr's normal PTY lifecycle.
        os.execvpe(executable, command, os.environ)
    result = subprocess.run(command, check=False)
    code = result.returncode
    print(f"\nProcess exited with status {code}.", flush=True)
    try:
        input("Press Enter to close...")
    except EOFError:
        pass
    return code if code >= 0 else 128 - code


def notify(message):
    print(f"Floating tools: {message}", file=sys.stderr)
    try:
        subprocess.run([os.environ.get("HERDR_BIN_PATH", "herdr"), "notification", "show",
                        "Floating tools", "--body", message], capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        pass


def main():
    modes = {"launch": launch, "menu": menu,
             "tool": lambda: execute(validate_tool(json.loads(os.environ["FLOATING_TOOL"])))}
    if len(sys.argv) != 2 or sys.argv[1] not in modes:
        raise ConfigError("Expected launch, menu or tool.")
    return modes[sys.argv[1]]() or 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except (ConfigError, RuntimeError, OSError, ValueError, KeyError, curses.error, subprocess.SubprocessError) as error:
        # Do not echo command arguments or raw configuration (may contain secrets).
        message = str(error) if isinstance(error, (ConfigError, RuntimeError)) else "Could not run floating tools. Check configuration and Herdr availability."
        notify(message)
        sys.exit(1)
