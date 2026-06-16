"""Force the overlay above a borderless-fullscreen game on Windows.

Qt's ``WindowStaysOnTopHint`` sets ``WS_EX_TOPMOST``, but ``raise_()`` and
``activateWindow()`` only reorder windows *within our own process* and are
silently denied by Windows' foreground lock when the game is the active app.
So a freshly shown overlay sits *behind* a borderless-fullscreen game (which is
itself topmost/foreground).

We fix that at the source: re-assert ``HWND_TOPMOST`` explicitly on every show,
then bypass the foreground lock with the ``AttachThreadInput`` trick so
``SetForegroundWindow`` is actually honoured.

(Exclusive/true-fullscreen games render through the GPU and can only be drawn
over by DirectX/OpenGL hooking, which is out of scope — those need the game set
to borderless windowed.)
"""
import sys

_HWND_TOPMOST = -1
_HWND_NOTOPMOST = -2
_SWP_NOSIZE = 0x0001
_SWP_NOMOVE = 0x0002
_SWP_NOACTIVATE = 0x0010
_SWP_SHOWWINDOW = 0x0040

_GWL_EXSTYLE = -20
_WS_EX_TOPMOST = 0x00000008


def _user32(user32):
    """Resolve the live user32 if not injected; None off Windows."""
    if user32 is not None:
        return user32
    if sys.platform != "win32":
        return None
    import ctypes

    return ctypes.windll.user32


def get_foreground_window(user32=None) -> int:
    """Handle of the window that currently owns the foreground (0 off Windows)."""
    user32 = _user32(user32)
    if user32 is None:
        return 0
    return user32.GetForegroundWindow()


def is_window_topmost(hwnd, user32=None) -> bool:
    """True if ``hwnd`` carries the WS_EX_TOPMOST (always-on-top) style."""
    user32 = _user32(user32)
    if user32 is None:
        return False
    return bool(user32.GetWindowLongW(hwnd, _GWL_EXSTYLE) & _WS_EX_TOPMOST)


def set_window_topmost(hwnd, topmost: bool, user32=None) -> None:
    """Move ``hwnd`` into or out of the always-on-top z-order band.

    Only the z-order band changes — position, size, and activation are left
    untouched — so demoting a fullscreen game and restoring it is non-disruptive.
    """
    user32 = _user32(user32)
    if user32 is None:
        return
    insert_after = _HWND_TOPMOST if topmost else _HWND_NOTOPMOST
    user32.SetWindowPos(
        hwnd,
        insert_after,
        0,
        0,
        0,
        0,
        _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE,
    )


def force_window_to_front(hwnd, user32=None, kernel32=None) -> None:
    """Put the window ``hwnd`` at the top of the z-order and bring it forward.

    ``user32``/``kernel32`` are injectable for testing; in production they
    default to the live Win32 libraries. On non-Windows platforms this is a
    no-op so the GUI can still be exercised headlessly elsewhere.
    """
    if user32 is None or kernel32 is None:
        if sys.platform != "win32":
            return
        import ctypes

        user32 = user32 or ctypes.windll.user32
        kernel32 = kernel32 or ctypes.windll.kernel32

    # 1. Re-insert at the top of the topmost band. WS_EX_TOPMOST alone is not
    #    enough once another topmost/foreground window already exists.
    user32.SetWindowPos(
        hwnd,
        _HWND_TOPMOST,
        0,
        0,
        0,
        0,
        _SWP_NOMOVE | _SWP_NOSIZE | _SWP_SHOWWINDOW,
    )

    # 2. Bring to the foreground. Windows blocks SetForegroundWindow from a
    #    background process, so attach our input queue to the foreground
    #    window's thread for the duration of the call, then detach.
    foreground = user32.GetForegroundWindow()
    if foreground == hwnd:
        return

    fg_thread = user32.GetWindowThreadProcessId(foreground, None)
    cur_thread = kernel32.GetCurrentThreadId()
    attached = False
    if fg_thread and fg_thread != cur_thread:
        attached = bool(user32.AttachThreadInput(fg_thread, cur_thread, True))
    try:
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(fg_thread, cur_thread, False)
