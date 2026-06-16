from PySide6.QtWidgets import QApplication
from meister_guide.ai.worker import ChatStreamWorker


class FakeClient:
    def __init__(self, chunks=None, boom=False):
        self._chunks = chunks or []
        self._boom = boom
    def chat(self, model, messages):
        if self._boom:
            raise RuntimeError("stream broke")
        for c in self._chunks:
            yield c


def test_worker_emits_tokens_then_finished():
    QApplication.instance() or QApplication([])
    worker = ChatStreamWorker(FakeClient(["He", "llo"]), "llama3", [])
    tokens, done = [], []
    worker.token.connect(lambda t: tokens.append(t))
    worker.finished.connect(lambda full: done.append(full))
    worker.run()
    assert tokens == ["He", "llo"]
    assert done == ["Hello"]


def test_worker_emits_error_not_finished_on_failure():
    QApplication.instance() or QApplication([])
    worker = ChatStreamWorker(FakeClient(boom=True), "llama3", [])
    errors, done = [], []
    worker.error.connect(lambda m: errors.append(m))
    worker.finished.connect(lambda full: done.append(full))
    worker.run()
    assert errors and "stream broke" in errors[0]
    assert done == []
