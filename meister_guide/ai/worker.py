"""QThread worker that streams an Ollama chat completion off the UI thread.
No DB — retrieval and persistence happen on the main thread."""
from PySide6.QtCore import QObject, Signal


class ChatStreamWorker(QObject):
    token = Signal(str)       # one streamed content chunk
    finished = Signal(str)    # the full assembled answer
    error = Signal(str)

    def __init__(self, client, model, messages):
        super().__init__()
        self._client = client
        self._model = model
        self._messages = messages

    def run(self):
        parts = []
        try:
            for chunk in self._client.chat(self._model, self._messages):
                parts.append(chunk)
                self.token.emit(chunk)
        except Exception as err:
            self.error.emit(str(err))
            return
        self.finished.emit("".join(parts))
