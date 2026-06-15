"""Global hotkey parsing (pure) + Win32 registration (added in Task 7)."""
import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

_MOD_NAMES = {
    "alt": MOD_ALT,
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
}

# Named virtual-key codes we support beyond single characters.
_VK_NAMES = {
    "insert": 0x2D,
    "delete": 0x2E,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "space": 0x20,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
}


def parse_hotkey(spec: str):
    """Parse a string like 'Alt+Insert' into (modifiers, virtual_key_code).

    Raises ValueError if the key part is unknown.
    """
    parts = [p.strip() for p in spec.split("+") if p.strip()]
    mods = 0
    key = None
    for part in parts:
        low = part.lower()
        if low in _MOD_NAMES:
            mods |= _MOD_NAMES[low]
        else:
            key = part
    if key is None:
        raise ValueError(f"No key in hotkey spec: {spec!r}")
    low = key.lower()
    if low in _VK_NAMES:
        return mods, _VK_NAMES[low]
    if len(key) == 1:
        return mods, ord(key.upper())
    raise ValueError(f"Unknown key in hotkey spec: {spec!r}")


_WM_HOTKEY = 0x0312
_HOTKEY_ID = 1


class GlobalHotkey(QAbstractNativeEventFilter, QObject):
    """Registers a system-wide hotkey via Win32 RegisterHotKey and emits
    `triggered` when pressed. Install on the QApplication and call register()."""

    triggered = Signal()

    def __init__(self, spec: str = "Alt+Insert"):
        QObject.__init__(self)
        QAbstractNativeEventFilter.__init__(self)
        self._mods, self._vk = parse_hotkey(spec)
        self._registered = False

    def register(self) -> bool:
        # MOD_NOREPEAT (0x4000) avoids auto-repeat floods.
        ok = ctypes.windll.user32.RegisterHotKey(
            None, _HOTKEY_ID, self._mods | 0x4000, self._vk
        )
        self._registered = bool(ok)
        return self._registered

    def unregister(self) -> None:
        if self._registered:
            ctypes.windll.user32.UnregisterHotKey(None, _HOTKEY_ID)
            self._registered = False

    def rebind(self, spec: str) -> bool:
        self.unregister()
        self._mods, self._vk = parse_hotkey(spec)
        return self.register()

    def nativeEventFilter(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
            if msg.message == _WM_HOTKEY and msg.wParam == _HOTKEY_ID:
                self.triggered.emit()
        return False, 0
