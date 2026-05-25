"""
startup.py — Windows registry startup management for United Mobile EPOS

Adds / removes the app from:
  HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run

Key name : UnitedMobileEPOS
Value    : full path to the executable (or "pythonw.exe" + "main.py" in source mode)
"""

import sys
import os

STARTUP_KEY_NAME  = "UnitedMobileEPOS"
_REGISTRY_PATH    = r"Software\Microsoft\Windows\CurrentVersion\Run"


# ── helpers ───────────────────────────────────────────────────────────────────

def _build_startup_value() -> str:
    """
    Return the registry value string that launches the app at Windows startup.

    • Frozen (PyInstaller .exe) → just the exe path, quoted.
    • Source mode              → pythonw.exe + absolute path to main.py,
                                 both quoted so spaces in paths are safe.
      pythonw.exe is used so no console window appears on startup.
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'

    # Source mode — locate main.py relative to this file
    script_dir  = os.path.dirname(os.path.abspath(__file__))
    main_script = os.path.join(script_dir, "main.py")

    # Prefer pythonw (no console window); fall back to python
    import shutil
    pythonw = (
        shutil.which("pythonw")
        or shutil.which("pythonw.exe")
        or sys.executable
    )
    return f'"{pythonw}" "{main_script}"'


def is_startup_registered() -> bool:
    """Return True if the app is currently in the Windows startup registry."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            _REGISTRY_PATH,
            0,
            winreg.KEY_READ,
        )
        try:
            winreg.QueryValueEx(key, STARTUP_KEY_NAME)
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False


def register_startup() -> bool:
    """
    Write the startup registry entry.
    Returns True on success, False on failure (non-fatal).
    """
    if sys.platform != "win32":
        return False
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            _REGISTRY_PATH,
            0,
            winreg.KEY_SET_VALUE,
        )
        value = _build_startup_value()
        winreg.SetValueEx(key, STARTUP_KEY_NAME, 0, winreg.REG_SZ, value)
        winreg.CloseKey(key)
        print(f"Startup registered: {value}")
        return True
    except Exception as exc:
        print(f"WARNING: Could not register startup: {exc}")
        return False


def unregister_startup() -> bool:
    """
    Remove the startup registry entry.
    Returns True on success, False on failure (non-fatal).
    """
    if sys.platform != "win32":
        return False
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            _REGISTRY_PATH,
            0,
            winreg.KEY_SET_VALUE,
        )
        try:
            winreg.DeleteValue(key, STARTUP_KEY_NAME)
            print("Startup registration removed.")
        except FileNotFoundError:
            pass   # was not registered — that's fine
        finally:
            winreg.CloseKey(key)
        return True
    except Exception as exc:
        print(f"WARNING: Could not unregister startup: {exc}")
        return False
