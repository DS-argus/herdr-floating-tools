# Herdr Floating Tools

A compact keyboard launcher for terminal tools. Open a small menu, select a tool,
and run it in a larger popup **from the original pane's directory**. The existing
pane and its running program stay untouched.

This is a community plugin, not an official Herdr-maintained component.

## Requirements

- Herdr 0.9.5+ and Python 3.11+ with `curses` (macOS or Linux).
- Your chosen tools installed on the Herdr server's PATH.
- A Nerd Font for the example icons; omit `icon` to use plain text.
- Windows is not supported. Terminal glyph widths can vary by font; simple icons
  work best, rather than multi-codepoint emoji sequences.

## Quick start

### 1. Install

```sh
herdr plugin install DS-argus/herdr-floating-tools
```

This command assumes the repository is public or accessible to your Git setup.
While the repository is private, authenticated contributors can use the
[development checkout](#development-and-tests) instructions instead.

Installation registers the action but **does not edit your keybindings** or
install lazygit, btop, or other tools.

### 2. Add a shortcut

Merge into `~/.config/herdr/config.toml` (or your custom config). Keep your other
settings. Replace any existing Prefix+f binding rather than adding a duplicate.

```toml
[[keys.command]]
key = "prefix+f"
type = "plugin_action"
command = "ds-argus.floating-tools.open"
description = "Floating tools"
```

### 3. Validate and reload

```sh
herdr config check && herdr server reload-config
```

### 4. Open the menu

Press your configured Prefix, then `f`. Use `j/k` or arrow keys and Enter,
or press a tool's shortcut directly. `q`, Escape and Ctrl+C cancel the menu.
When items do not fit, the menu uses discrete pages; PageUp/PageDown also work.
Items do not scroll when they all fit. Tool popups receive their own native keys:
`q` and Escape do not universally close every tool.

## Configuration

```sh
herdr plugin config-dir ds-argus.floating-tools
```

Create `config.toml` in the directory printed above. This is separate from
Herdr's main config and is not automatically created. Without it, the plugin
uses the six entries in [config.example.toml](config.example.toml). User entries
replace that list; they are not merged with defaults. Changes apply next time
you open the menu. An already-open menu keeps its original configuration snapshot.

```toml
[[tools]]
id = "git"
key = "g"
name = "Git"
icon = "󰊢"
command = ["lazygit"]
width = "80%"
height = "80%"
close_on_exit = true

[[tools]]
id = "tests"
key = "t"
name = "Cargo tests"
command = ["cargo", "test"]
cwd = "."
width = "90%"
height = "70%"
close_on_exit = false
```

| Field | Required | Behavior |
| --- | --- | --- |
| `id` | Yes | Unique ID: letters, digits, `_`, `-`; up to 64 characters |
| `key` | Yes | Unique lowercase letter or digit; `j/k/q` are reserved |
| `name` | Yes | Display name; up to 100 characters |
| `icon` | No | Optional icon, up to 8 characters; omitted icon is blank |
| `command` | Yes | Nonempty argument array, not a shell command string |
| `cwd` | No | Default: original pane directory. Absolute, `~/path`, or relative to that directory |
| `width` | No | Tool popup width; default `"80%"` |
| `height` | No | Tool popup height; default `"80%"` |
| `close_on_exit` | No | Default `true`; `false` shows exit status and waits for Enter |

Width/height accept integer cells (1–1000) or percentages (`"1%"`–`"100%"`).
Herdr enforces its own minimums and fits popups to the available area. These
settings apply to the **tool**, not the menu. Menu dimensions grow with item
count and display-name width (up to 100 columns), with pagination when clamped.
There are at most 64 tools and a 32 KB serialized configuration limit.

The menu uses a compact Frost-colored style and one row per tool. Selected
icons, names and shortcuts share the same background. When no entries have
icons, the icon column is removed. Long names are clipped to the actual width.

## Execution and safety

- The source directory is captured from Herdr's invocation context, not the
  plugin checkout. The action requires a valid local pane directory.
- Relative executable paths such as `./scripts/check` resolve in the tool's cwd.
  `~/` is expanded in cwd and the executable path; other arguments are literal.
- No shell interpolation, globbing, variable substitution or command chaining.
  Complex operations belong in a trusted script explicitly listed in `command`.
- Tools are not sandboxed: they run with your user permissions. Never put
  secrets in command arguments, and review configuration before using it.
- Missing executables and invalid settings produce an English notification and
  an error log. Missing tools remain visible; they are not silently removed.
- `close_on_exit=false` waits only after the process exits. It does not keep the
  process alive after the popup is closed, nor make a persistent agent session.
- This is not a process supervisor. Programs that daemonize themselves have
  their own lifecycles. Prefer normal panes for persistent servers or agents.
- Popup closure and terminal signals follow Herdr's normal PTY behavior.
- Existing Herdr popups/modals may prevent opening the menu. Only the brief
  menu-to-tool teardown race is retried, with a bounded deadline.
- Error notifications follow Herdr's global delivery and position settings.

## Development and tests

```sh
gh repo clone DS-argus/herdr-floating-tools
cd herdr-floating-tools
herdr plugin link "$PWD"
python3 -m unittest discover -v
```

The opt-in real Herdr test uses an isolated HOME/server and a harmless fixture
command. It verifies cancel/reopen, actual plugin-action context, original cwd
(including spaces and Korean characters), literal arguments, nonzero process
exit status, and retained output:

```sh
RUN_HERDR_INTEGRATION=1 python3 -m unittest discover -v
```

macOS is locally integration-tested. CI runs unit tests on macOS and Ubuntu;
a real Linux Herdr session is not claimed tested unless that opt-in suite is run.

## Update and remove

GitHub-managed installation:

```sh
herdr plugin update ds-argus.floating-tools
```

Linked checkout: `git pull --ff-only`, then relink after manifest changes.
To remove, delete the shortcut and run:

```sh
herdr plugin uninstall ds-argus.floating-tools
herdr config check && herdr server reload-config
```

Use `plugin unlink` for a development checkout. Herdr may retain the plugin's
configuration; remove it separately only if no longer needed.
