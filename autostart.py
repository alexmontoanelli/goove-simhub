"""Start with Windows via the HKCU Run registry key. No-op off Windows."""

import sys

APP_NAME = "AdalightGoveeBridge"
_RUN_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"


def is_supported():
    return sys.platform == "win32"


def _command():
    """Command stored in the registry: the current executable."""
    return f'"{sys.executable}"'


def is_enabled():
    if not is_supported():
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_PATH) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except OSError:
        return False


def enable():
    if not is_supported():
        return False
    import winreg

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, _RUN_PATH, 0, winreg.KEY_SET_VALUE
    ) as key:
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _command())
    return True


def disable():
    if not is_supported():
        return False
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_PATH, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, APP_NAME)
    except OSError:
        pass
    return True


def apply(enabled):
    """Enable or disable autostart. Returns True if a change was applied."""
    return enable() if enabled else disable()
