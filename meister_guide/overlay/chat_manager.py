"""Modal dialog to manage saved chat sessions: rename or delete them.

Self-contained Qt — takes a ChatRepo and mutates it directly, re-rendering its
list after each action so it stays live. Tracks deleted ids so the caller can
drop a now-deleted open chat back to a blank one."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget,
    QListWidget, QListWidgetItem, QInputDialog, QMessageBox,
)


class ChatManagerDialog(QDialog):
    def __init__(self, chat_repo, parent=None):
        super().__init__(parent)
        self._repo = chat_repo
        self._deleted = set()        # ids removed this session, read by the caller
        self.setWindowTitle("Manage chats")
        self.setObjectName("ChatManager")
        self.resize(360, 320)

        root = QVBoxLayout(self)
        root.addWidget(QLabel("Your chats"))
        self._list = QListWidget()
        root.addWidget(self._list, 1)

        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        bar = QHBoxLayout()
        bar.addStretch(1)
        bar.addWidget(close)
        root.addLayout(bar)

        self._reload()

    @property
    def deleted_ids(self):
        return self._deleted

    def _reload(self):
        self._list.clear()
        sessions = self._repo.list_sessions()
        if not sessions:
            item = QListWidgetItem("No saved chats yet")
            item.setFlags(Qt.NoItemFlags)
            self._list.addItem(item)
            return
        for s in sessions:
            self._add_row(s)

    def _add_row(self, session):
        title = session.title or f"Chat {session.id}"
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(4, 2, 4, 2)
        label = QLabel(title)
        label.setToolTip(session.started_at or "")
        h.addWidget(label, 1)
        rename = QPushButton("Rename")
        rename.clicked.connect(lambda _=False, s=session: self._rename(s))
        delete = QPushButton("Delete")
        delete.clicked.connect(lambda _=False, s=session: self._delete(s))
        h.addWidget(rename)
        h.addWidget(delete)

        item = QListWidgetItem()
        item.setSizeHint(row.sizeHint())
        self._list.addItem(item)
        self._list.setItemWidget(item, row)

    def _rename(self, session):
        current = session.title or f"Chat {session.id}"
        text, ok = QInputDialog.getText(
            self, "Rename chat", "New name:", text=current
        )
        if ok and text.strip():
            self._repo.set_title(session.id, text.strip())
            self._reload()

    def _delete(self, session):
        title = session.title or f"Chat {session.id}"
        resp = QMessageBox.question(
            self, "Delete chat",
            f"Delete “{title}”? This can’t be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if resp == QMessageBox.Yes:
            self._repo.delete_session(session.id)
            self._deleted.add(session.id)
            self._reload()
