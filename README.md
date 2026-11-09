# Claude Notch

A small notch at the top of a Windows screen that shows what Claude Code is doing. It looks like the Dynamic Island on a Mac.

**Українська:** [README.uk.md](README.uk.md)

> Unofficial. Not made by, affiliated with or endorsed by Anthropic. "Claude" is a trademark of Anthropic.

## What it shows

**The pill at the top** changes with what Claude Code is doing:

| State | Pill |
|---|---|
| Working | The current step, e.g. `›_ PowerShell Run tests` |
| Thinking | `thinking •••` |
| Just finished | `✓ done · waiting for you`, until you open the panel or for 3 minutes |
| Idle | Only the icon and the 5-hour usage ring |

**Hover the pill** to open a panel with:
- the project, model, branch and status;
- the 5-hour and weekly plan usage, with time until each resets;
- how full the context window is, with a hint to run `/compact` past 80%;
- the agents of the current session: running or done, time and tokens;
- installed skills, plugins, MCP servers and your own agents;
- tokens used today.

The tray icon has a small menu: open the panel, hide the notch, start with Windows, quit.

## Privacy

Everything is read from local files. Nothing about you or your sessions is sent anywhere.

The widget makes only two kinds of network request:
- **The update check.** Once a day it fetches `version.json` from this repository. Turn it off with `"check_updates": false` in `config.json`.
- **The ↻ button.** It runs `claude -p /usage`, a local Claude Code command. It does not call the model and does not use up your plan.

| File | What is read |
|---|---|
| `~/.claude/projects/**/*.jsonl` | Session logs |
| `~/.claude.json` | Only `cachedUsageUtilization`, `mcpServers` and `projects`. The login token in the same file is never read. |
| `~/.claude/skills`, `~/.claude/plugins/installed_plugins.json`, `~/.claude/agents` | Installed skills, plugins and agents |

The usage percentages are the ones Claude Code itself caches after it checks your plan. If they are older than 10 minutes, the widget dims them and shows their age. Press **↻** to refresh them. The panel also refreshes them when you open it and they are older than 5 minutes.

## Install

**Requirements:**
- Windows 10 or 11. Rounded corners need Windows 11.
- [Python 3.10+](https://www.python.org/downloads/). Tick "Add to PATH" during setup.
- The Microsoft Edge WebView2 runtime. Windows 11 already has it.

**Steps:**

```powershell
git clone https://github.com/aleoniys/claude-notch.git
cd claude-notch
powershell -ExecutionPolicy Bypass -File install.ps1
```

The script:
1. installs `pystray`, `Pillow` and `pywebview`;
2. adds **Claude Notch** to the Start menu;
3. starts the notch.

To start it with Windows, right-click the tray icon and choose **Start with Windows**.

**Manual run:** `pythonw app.py`. A second copy does not start while one is running.

## Language

The language follows Windows. Included: English, Українська, Polski, Deutsch, Español, Français, Português.

To change it, use either:
- the **🌐** button at the bottom of the panel, which switches to the next language;
- **Language** in the tray menu.

The choice is saved in `config.json`.

## Updates

Once a day the widget checks this repository for a newer version. When there is one, an **Update to x.y.z** button appears in the panel and in the tray menu.

Nothing is installed until you click it. Then the widget:
1. runs `git pull` if you installed with git, or downloads the ZIP otherwise;
2. keeps your `config.json` and `custom-icon.png`;
3. restarts.

**Releasing a new version:** raise `version` in `version.json` and push to `main`.

To add a language, copy the `en` block in `i18n.json`, translate it and use the language code as the key, then open a pull request.

## Your own icon

Put a PNG named `custom-icon.png` next to `app.py` and restart. A square image with a transparent background works best.

## Files

| File | Purpose |
|---|---|
| `app.py` | Window, tray icon, positioning |
| `collect.py` | Reads the local Claude Code files |
| `ui.html` | The pill and the panel |
| `i18n.json` | Translations |
| `update.py` | Update check and install |
| `version.json` | Current version |

To check what the widget reads, run `python collect.py`.

## License

MIT
