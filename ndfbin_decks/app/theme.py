"""Follow the desktop's light/dark setting.

Why this needs code at all: the app ships no palette of its own, so it inherits
whatever the style provides.  On Windows that is the ``windowsvista`` style,
which is light-only and has no notion of a dark scheme; Qt only grew
``QStyleHints.colorScheme()`` in 6.5, and the one-file build is frozen with
PySide6 6.3.2.  So the scheme has to be detected *and* painted by hand.

Two consequences worth knowing:

* **Fusion, not the native style.**  A custom dark palette only comes out right
  on a style that honours ``QPalette`` role by role; ``windowsvista`` paints
  from the system theme and ignores most of it.  Switching to Fusion makes the
  light and dark palettes behave the same way, and makes what the tests see
  (headless runs already get Fusion) match what the user gets.
* **Detection has two paths.**  Qt first — it is the sanctioned API and works
  off Windows too — then the Windows registry, because 6.3.2 has no scheme API.
  A registry read through :mod:`winreg` costs microseconds, which is why the
  fallback can also be polled for live switching.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

LIGHT = "light"
DARK = "dark"

#: Which group of the palette a role belongs to when it is not obvious.
_ROLES_TEXT = (
    QPalette.ColorRole.WindowText,
    QPalette.ColorRole.Text,
    QPalette.ColorRole.ButtonText,
)


def _from_qt(app: QApplication) -> str | None:
    """``colorScheme()`` when the Qt version has it, else ``None``.

    ``Unknown`` is treated as "no answer" rather than as light: on a platform
    where Qt cannot tell, the registry often still can.
    """
    hints = app.styleHints()
    if not hasattr(hints, "colorScheme"):
        return None
    try:
        scheme = str(hints.colorScheme()).lower()
    except Exception:                                  # noqa: BLE001
        return None
    if "dark" in scheme:
        return DARK
    if "light" in scheme:
        return LIGHT
    return None


def _from_windows_registry() -> str | None:
    """``AppsUseLightTheme`` — 0 means the app theme is dark."""
    if sys.platform != "win32":
        return None
    try:
        import winreg
        path = (r"Software\Microsoft\Windows\CurrentVersion"
                r"\Themes\Personalize")
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            value, _kind = winreg.QueryValueEx(key, "AppsUseLightTheme")
    except OSError:
        return None
    except Exception:                                  # noqa: BLE001
        return None
    return LIGHT if value else DARK


def system_mode() -> str:
    """``"dark"`` or ``"light"`` — never raises, defaults to light."""
    app = QApplication.instance()
    return ((app is not None and _from_qt(app))
            or _from_windows_registry()
            or LIGHT)


def dark_palette() -> QPalette:
    """A neutral dark palette that Fusion renders consistently.

    Values follow Qt's own dark example; the grey 3-D roles are set explicitly
    because Fusion derives frame shading from them and the defaults are tuned
    for a light window.
    """
    p = QPalette()
    window = QColor(53, 53, 53)
    base = QColor(35, 35, 35)
    text = QColor(232, 232, 232)
    disabled = QColor(127, 127, 127)

    p.setColor(QPalette.ColorRole.Window, window)
    p.setColor(QPalette.ColorRole.WindowText, text)
    p.setColor(QPalette.ColorRole.Base, base)
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(43, 43, 43))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(43, 43, 43))
    p.setColor(QPalette.ColorRole.ToolTipText, text)
    p.setColor(QPalette.ColorRole.Text, text)
    p.setColor(QPalette.ColorRole.Button, window)
    p.setColor(QPalette.ColorRole.ButtonText, text)
    p.setColor(QPalette.ColorRole.BrightText, QColor(255, 85, 85))
    p.setColor(QPalette.ColorRole.Link, QColor(74, 163, 255))
    p.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor(154, 154, 154))
    p.setColor(QPalette.ColorRole.Light, QColor(74, 74, 74))
    p.setColor(QPalette.ColorRole.Midlight, QColor(64, 64, 64))
    p.setColor(QPalette.ColorRole.Mid, QColor(45, 45, 45))
    p.setColor(QPalette.ColorRole.Dark, QColor(31, 31, 31))
    p.setColor(QPalette.ColorRole.Shadow, QColor(21, 21, 21))

    for role in _ROLES_TEXT:
        p.setColor(QPalette.ColorGroup.Disabled, role, disabled)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight,
               QColor(80, 80, 80))
    p.setColor(QPalette.ColorGroup.Disabled,
               QPalette.ColorRole.HighlightedText, QColor(160, 160, 160))
    return p


def apply(app: QApplication | None = None, mode: str | None = None) -> str:
    """Paint *app* for *mode* (default: ask the desktop).  Returns the mode."""
    app = app or QApplication.instance()
    if app is None:
        return mode or LIGHT
    mode = mode or system_mode()
    # Set the style first: changing it resets the palette, so painting after it
    # is the only order that survives.
    if app.style().objectName().lower() != "fusion":
        app.setStyle("Fusion")
    if mode == DARK:
        app.setPalette(dark_palette())
    else:
        # The style's own palette, not a default-constructed one: the latter
        # drops the shaded 3-D roles Fusion needs for frames and separators.
        app.setPalette(app.style().standardPalette())
    return mode


def follow(app: QApplication, on_change) -> QTimer | None:
    """Call *on_change(mode)* when the desktop switches light/dark.

    Qt 6.5+ has the signal.  On the frozen 6.3.2 build there is none, so the
    registry is polled — one integer read every couple of seconds, which costs
    less than a repaint and keeps the window from sitting in the wrong theme
    until the next launch.
    """
    hints = app.styleHints()
    if hasattr(hints, "colorSchemeChanged"):
        try:
            hints.colorSchemeChanged.connect(
                lambda *_: on_change(system_mode()))
            return None
        except Exception:                              # noqa: BLE001
            pass
    if sys.platform != "win32":
        return None

    state = {"mode": system_mode()}
    timer = QTimer(app)
    timer.setInterval(2000)

    def poll() -> None:
        mode = system_mode()
        if mode != state["mode"]:
            state["mode"] = mode
            on_change(mode)

    timer.timeout.connect(poll)
    timer.start()
    return timer
