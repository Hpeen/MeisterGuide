"""Background game detection: polls running processes on a timer and emits
the active Game (or None) whenever the detected state changes."""
import psutil
from PySide6.QtCore import QObject, QTimer, Signal

from meister_guide.detector.matcher import match_running_game

_UNSET = object()


def _psutil_process_names():
    names = []
    for proc in psutil.process_iter(["name"]):
        try:
            name = proc.info["name"]
            if name:
                names.append(name)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return names


class GameDetector(QObject):
    """Emits `detected(Game | None)` on every change of detected game."""

    detected = Signal(object)

    def __init__(self, games_provider, interval_ms=10000,
                 process_lister=_psutil_process_names):
        super().__init__()
        self._games_provider = games_provider
        self._process_lister = process_lister
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.poll)
        self._last_id = _UNSET

    def start(self):
        """Poll immediately, then every interval_ms."""
        self.poll()
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def poll(self):
        game = match_running_game(self._process_lister(), self._games_provider())
        current_id = game.id if game is not None else None
        if current_id != self._last_id:
            self._last_id = current_id
            self.detected.emit(game)
