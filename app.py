"""Claude notch: a Dynamic-Island-style pill at the top of the screen plus a tray icon.
Reads only local Claude Code files. Start without a console: pythonw app.py"""
import ctypes
import json
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

import pystray
import webview
from PIL import Image, ImageDraw

from collect import collect

HERE = Path(__file__).resolve().parent
PYW = Path(sys.executable).with_name("pythonw.exe")
STARTUP = Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs/Startup/claude-notch.vbs"
CONFIG = HERE / "config.json"     # optional: {"lang": "en"}
ICON = HERE / ("custom-icon.png" if (HERE / "custom-icon.png").exists() else "icon.png")
TOP = 12          # px hidden above the screen edge, so only the bottom corners are rounded
PILL_H = 34
OPEN_W = 560

def _config():
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _lang(table):
    """config.json "lang", else the Windows UI language, else English."""
    want = str(_config().get("lang") or os.environ.get("NOTCH_LANG") or "").lower()
    if not want:
        buf = ctypes.create_unicode_buffer(85)
        if ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, 85):
            want = buf.value.lower()
    want = want.split("-")[0].split("_")[0]
    if want == "ua":
        want = "uk"
    return want if want in table else "en"


I18N = json.loads((HERE / "i18n.json").read_text(encoding="utf-8"))
LANG = _lang(I18N)
T = {**I18N["en"], **I18N[LANG]}

_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "claude-notch-single")
if ctypes.windll.kernel32.GetLastError() == 183:
    sys.exit(0)

from ctypes import wintypes as _wt  # noqa: E402

user32 = ctypes.windll.user32
user32.SetWindowPos.argtypes = [_wt.HWND, _wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
user32.GetDpiForWindow.argtypes = [_wt.HWND]
user32.GetWindowRect.argtypes = [_wt.HWND, ctypes.c_void_p]
user32.GetWindowLongW.argtypes = [_wt.HWND, ctypes.c_int]
user32.SetWindowLongW.argtypes = [_wt.HWND, ctypes.c_int, ctypes.c_long]
user32.ShowWindow.argtypes = [_wt.HWND, ctypes.c_int]
ctypes.windll.dwmapi.DwmSetWindowAttribute.argtypes = [_wt.HWND, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
window = None
tray = None
hidden = False
expanded = False
_last = {"data": None, "at": 0.0}


def log(msg):
    with open(HERE / "notch.log", "a", encoding="utf-8") as f:
        f.write(time.strftime("%H:%M:%S ") + str(msg) + "\n")


def hwnd():
    return int(str(window.native.Handle))


def scale():
    try:
        return user32.GetDpiForWindow(hwnd()) / 96
    except Exception:
        return 1.0


def place(w, h):
    """Size and centre the window at the top edge, in logical px, without stealing focus."""
    s = scale()
    W, H = int(w * s), int((h + TOP) * s)
    sw = user32.GetSystemMetrics(0)
    if not user32.SetWindowPos(hwnd(), _wt.HWND(-1), (sw - W) // 2, -int(TOP * s), W, H, 0x0010 | 0x0040):  # NOACTIVATE | SHOWWINDOW
        log(f"SetWindowPos failed {ctypes.GetLastError()}")


def style():
    """Windows 11: smooth rounded corners and no 1px border."""
    d = ctypes.windll.dwmapi
    v = ctypes.c_int(2)
    d.DwmSetWindowAttribute(hwnd(), 33, ctypes.byref(v), 4)
    c = ctypes.c_uint(0xFFFFFFFE)
    d.DwmSetWindowAttribute(hwnd(), 34, ctypes.byref(c), 4)
    # Tool window: not on the taskbar or in Alt+Tab, only the tray icon stays.
    ex = user32.GetWindowLongW(hwnd(), -20)
    user32.ShowWindow(hwnd(), 0)
    user32.SetWindowLongW(hwnd(), -20, (ex | 0x80) & ~0x40000)  # WS_EX_TOOLWINDOW, no WS_EX_APPWINDOW
    user32.ShowWindow(hwnd(), 4)  # SW_SHOWNOACTIVATE


def data_cached():
    if time.time() - _last["at"] > 2:
        _last["data"] = collect()
        _last["at"] = time.time()
    return _last["data"]


class Api:
    def data(self):
        try:
            return data_cached()
        except Exception as e:
            log(f"data: {e!r}")
            raise

    def pill(self, w):
        if not expanded:
            place(int(w), PILL_H)

    def expand(self, h):
        global expanded
        expanded = True
        place(OPEN_W, int(h))

    def collapse(self, w):
        global expanded
        expanded = False
        place(int(w), PILL_H)

    def strings(self):
        return {**T, "_lang": LANG}

    def icon(self):
        return ICON.name

    def open_url(self, url):
        webbrowser.open(url)

    def log(self, msg):
        log("js: " + str(msg))


# ---------- tray ----------
BASE = Image.open(ICON).convert("RGBA").resize((64, 64), Image.LANCZOS)


def tray_image(pct):
    im = BASE.copy()
    if pct is not None:
        color = (248, 113, 113) if pct >= 85 else (251, 191, 36) if pct >= 60 else (74, 222, 128)
        ImageDraw.Draw(im).ellipse((42, 42, 63, 63), fill=color, outline=(13, 13, 15), width=3)
    return im


def toggle_autostart(icon, item):
    """Only when the user ticks it in the tray menu."""
    if STARTUP.exists():
        STARTUP.unlink()
    else:
        STARTUP.write_text(f'CreateObject("WScript.Shell").Run """{PYW}"" ""{HERE / "app.py"}""", 0, False\r\n',
                           encoding="utf-8")


def toggle_notch(icon=None, item=None):
    global hidden
    hidden = not hidden
    window.hide() if hidden else window.show()


def pin_panel(icon=None, item=None):
    if hidden:
        toggle_notch()
    window.evaluate_js("pinOpen(true)")


def quit_all(icon, item):
    icon.visible = False
    icon.stop()
    window.destroy()


def tray_loop():
    while True:
        try:
            d = data_cached()
            five = (d["limits"].get("five") or {}).get("pct")
            week = (d["limits"].get("week") or {}).get("pct")
            proj = (d.get("session") or {}).get("project", "")
            tray.icon = tray_image(five)
            tip = T["trayTip"].format(a=five if five is not None else "—", b=week if week is not None else "—")
            tray.title = f"Claude · {proj}\n{tip}"
        except Exception as e:
            log(f"tray: {e!r}")
        time.sleep(30)


def watch_cursor():
    """WebView2 often misses mouseleave, so the panel closes when the cursor is away from it."""

    class P(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    class R(ctypes.Structure):
        _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]

    away = 0.0
    while True:
        time.sleep(0.2)
        if not expanded:
            away = 0.0
            continue
        try:
            pt, rc = P(), R()
            user32.GetCursorPos(ctypes.byref(pt))
            user32.GetWindowRect(hwnd(), ctypes.byref(rc))
            inside = rc.l - 6 <= pt.x <= rc.r + 6 and pt.y <= rc.b + 6
            away = 0.0 if inside else away + 0.2
            if away >= 0.4:
                away = 0.0
                window.evaluate_js("autoClose()")
        except Exception as e:
            log(f"watch: {e!r}")


def on_start():
    global tray
    tray = pystray.Icon(
        "claude-notch", tray_image(None), "Claude",
        menu=pystray.Menu(
            pystray.MenuItem(T["trayOpen"], pin_panel, default=True),
            pystray.MenuItem(T["trayToggle"], toggle_notch),
            pystray.MenuItem(T["trayAutostart"], toggle_autostart, checked=lambda i: STARTUP.exists()),
            pystray.MenuItem(T["usage"], lambda i, it: webbrowser.open("https://claude.ai/settings/usage")),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(T["trayQuit"], quit_all),
        ),
    )
    tray.run_detached()
    threading.Thread(target=tray_loop, daemon=True).start()
    threading.Thread(target=watch_cursor, daemon=True).start()
    time.sleep(0.8)
    try:
        style()
        place(110, PILL_H)
    except Exception as e:
        log(f"start: {e!r}")


if __name__ == "__main__":
    os.chdir(HERE)
    window = webview.create_window(
        "Claude notch", url=str(HERE / "ui.html"), js_api=Api(),
        width=110, height=PILL_H + TOP, x=900, y=-TOP,
        frameless=True, easy_drag=False, on_top=True, focus=False, resizable=False,
        background_color="#000000", min_size=(60, 20),
    )
    webview.start(on_start, debug=False)
