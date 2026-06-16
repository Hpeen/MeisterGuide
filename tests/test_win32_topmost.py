from meister_guide.overlay.win32_topmost import (
    force_window_to_front,
    get_foreground_window,
    is_window_topmost,
    set_window_topmost,
    _HWND_TOPMOST,
    _HWND_NOTOPMOST,
    _WS_EX_TOPMOST,
)


class FakeUser32:
    def __init__(self, foreground=999, ex_style=0):
        self.calls = []
        self._foreground = foreground
        self._ex_style = ex_style

    def SetWindowPos(self, *args):
        self.calls.append(("SetWindowPos", args))
        return 1

    def GetForegroundWindow(self):
        return self._foreground

    def GetWindowLongW(self, hwnd, index):
        return self._ex_style

    def GetWindowThreadProcessId(self, hwnd, _pid):
        return 42

    def AttachThreadInput(self, a, b, attach):
        self.calls.append(("AttachThreadInput", (a, b, attach)))
        return 1

    def SetForegroundWindow(self, hwnd):
        self.calls.append(("SetForegroundWindow", hwnd))
        return 1


class FakeKernel32:
    def GetCurrentThreadId(self):
        return 7


def test_reasserts_topmost_and_brings_to_front():
    user32, kernel32 = FakeUser32(), FakeKernel32()
    force_window_to_front(1234, user32=user32, kernel32=kernel32)

    names = [c[0] for c in user32.calls]
    swp = next(c for c in user32.calls if c[0] == "SetWindowPos")
    assert swp[1][0] == 1234           # hwnd
    assert swp[1][1] == _HWND_TOPMOST  # placed in the topmost band
    assert "SetForegroundWindow" in names
    # Foreground lock is bypassed by attaching, then detaching, the input queue.
    assert ("AttachThreadInput", (42, 7, True)) in user32.calls
    assert ("AttachThreadInput", (42, 7, False)) in user32.calls


def test_skips_foreground_dance_when_already_frontmost():
    user32, kernel32 = FakeUser32(foreground=1234), FakeKernel32()
    force_window_to_front(1234, user32=user32, kernel32=kernel32)

    names = [c[0] for c in user32.calls]
    assert "SetWindowPos" in names            # still re-asserts topmost
    assert "SetForegroundWindow" not in names  # but no needless focus steal
    assert "AttachThreadInput" not in names


def test_get_foreground_window():
    user32 = FakeUser32(foreground=555)
    assert get_foreground_window(user32=user32) == 555


def test_is_window_topmost_reads_ex_style_bit():
    topmost = FakeUser32(ex_style=_WS_EX_TOPMOST | 0x100)
    normal = FakeUser32(ex_style=0x100)
    assert is_window_topmost(42, user32=topmost) is True
    assert is_window_topmost(42, user32=normal) is False


def test_set_window_topmost_true_uses_hwnd_topmost():
    user32 = FakeUser32()
    set_window_topmost(42, True, user32=user32)
    swp = next(c for c in user32.calls if c[0] == "SetWindowPos")
    assert swp[1][0] == 42
    assert swp[1][1] == _HWND_TOPMOST


def test_set_window_topmost_false_uses_hwnd_notopmost():
    user32 = FakeUser32()
    set_window_topmost(42, False, user32=user32)
    swp = next(c for c in user32.calls if c[0] == "SetWindowPos")
    assert swp[1][0] == 42
    assert swp[1][1] == _HWND_NOTOPMOST
