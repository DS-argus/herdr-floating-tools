"""Validated user-owned tool configuration, never loaded from project directories."""
import os
from pathlib import Path
import re
import tomllib
import unicodedata

FIELDS = {"id", "key", "name", "icon", "command", "cwd", "width", "height", "close_on_exit"}
RESERVED = set("jkq")


class ConfigError(ValueError):
    pass


def text(value, field, maximum=100):
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ConfigError(f"{field} must be a nonempty string (up to {maximum} characters).")
    if any(unicodedata.category(char) in {"Cc", "Cf", "Cs", "Cn"} for char in value):
        raise ConfigError(f"{field} must not contain control characters.")
    return value


def popup_size(value, field):
    if type(value) is int and 1 <= value <= 1000:
        return value
    if isinstance(value, str) and re.fullmatch(r"(?:[1-9][0-9]?|100)%", value):
        return value
    raise ConfigError(f"{field} must be 1–1000 cells or a percentage from 1% to 100%.")


def validate_tool(raw):
    if not isinstance(raw, dict) or set(raw) - FIELDS:
        raise ConfigError("Unknown tool setting; use only the documented fields.")
    tool = dict(raw)
    for field in ("id", "key", "name"):
        tool[field] = text(tool.get(field), field)
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", tool["id"]):
        raise ConfigError("Tool id must use letters, digits, underscores or hyphens.")
    if not re.fullmatch(r"[a-z0-9]", tool["key"]) or tool["key"] in RESERVED:
        raise ConfigError("Shortcut must be one lowercase letter or digit, excluding j/k/q.")
    icon = tool.get("icon", "")
    if icon != "":
        text(icon, "icon", 8)
    tool["icon"] = icon
    command = tool.get("command")
    if not isinstance(command, list) or not command or len(command) > 64:
        raise ConfigError("command must be a nonempty argv array (up to 64 arguments).")
    for arg in command:
        if not isinstance(arg, str) or "\0" in arg or len(arg) > 4096:
            raise ConfigError("Command arguments must be strings without NUL (up to 4096 characters).")
    if not command[0]:
        raise ConfigError("The command executable cannot be empty.")
    if "cwd" in tool:
        text(tool["cwd"], "cwd", 4096)
    for field in ("width", "height"):
        tool[field] = popup_size(tool.get(field, "80%"), field)
    tool.setdefault("close_on_exit", True)
    if type(tool["close_on_exit"]) is not bool:
        raise ConfigError("close_on_exit must be a boolean.")
    return tool


def validate_config(config):
    if not isinstance(config, dict) or set(config) != {"tools"}:
        raise ConfigError("Configuration must contain [[tools]] entries only.")
    raw = config["tools"]
    if not isinstance(raw, list) or not 1 <= len(raw) <= 64:
        raise ConfigError("Configure between 1 and 64 tools.")
    tools = [validate_tool(item) for item in raw]
    for field in ("id", "key"):
        if len({tool[field] for tool in tools}) != len(tools):
            raise ConfigError(f"Tool {field} values must be unique.")
    return tools


def load_tools():
    directory = os.environ.get("HERDR_PLUGIN_CONFIG_DIR")
    if not directory:
        raise ConfigError("Missing Herdr plugin config directory.")
    path = Path(directory) / "config.toml"
    if not path.exists():
        path = Path(__file__).with_name("config.example.toml")
    try:
        with path.open("rb") as handle:
            return validate_config(tomllib.load(handle))
    except (OSError, tomllib.TOMLDecodeError):
        raise ConfigError("Cannot read config.toml. Check syntax and permissions.") from None


def resolve_cwd(tool, source):
    path = Path(tool.get("cwd", source)).expanduser()
    if not path.is_absolute():
        path = Path(source) / path
    path = path.resolve()
    if not path.is_dir():
        raise ConfigError("The tool working directory does not exist or is not a directory.")
    return str(path)
