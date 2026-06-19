"""The Meister Guide overlay window (Phase 1 shell)."""
from PySide6.QtCore import Qt, QSettings, QPoint, QRect, QThread
from PySide6.QtGui import QPainter, QGuiApplication
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QTabWidget, QComboBox,
    QLineEdit, QListWidget, QListWidgetItem, QTextBrowser, QProgressBar, QSplitter,
)

import html
import sys

from meister_guide.ai.passage import relevant_passage
from meister_guide.ai.prompt import build_messages
from meister_guide.ai.ollama_client import OllamaUnavailable, pick_best_model
from meister_guide.ai.claude_client import ClaudeClient, AVAILABLE_MODELS
from meister_guide.ai.worker import ChatStreamWorker
from meister_guide.db.settings import BACKEND_OLLAMA, BACKEND_CLAUDE, BACKEND_AUTO
from meister_guide.input.hotkey import parse_hotkey

from meister_guide.config.dock import (
    dock_rect, nearest_edge, normalize_edge, PANEL_WIDTH,
)
from meister_guide.theme import painters
from meister_guide.overlay.win32_topmost import (
    force_window_to_front,
    get_foreground_window,
    is_window_topmost,
    set_window_topmost,
)
from meister_guide.scraper.worker import IngestWorker
from meister_guide.guides_status import guides_status_text
from meister_guide.overlay.chat_manager import ChatManagerDialog

class _PanelWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._edge = "right"

    def set_edge(self, edge):
        self._edge = edge
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        painters.paint_panel(p, self.width(), self.height(), self._edge)
        p.end()


class _SpineWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._edge = "right"

    def set_edge(self, edge):
        self._edge = edge
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        painters.paint_spine(p, self.width(), self.height(), self._edge)
        p.end()


class OverlayWindow(QWidget):
    def __init__(self, settings: QSettings, games=None, articles_repo=None,
                 db_path=None, chat_repo=None, ollama_client=None,
                 settings_repo=None, hotkey=None, claude_factory=ClaudeClient,
                 scrape_state_repo=None, redirect_state_repo=None):
        super().__init__()
        self._settings = settings
        self._settings_repo = settings_repo
        self._hotkey = hotkey
        self._claude_factory = claude_factory
        self._chat_client = None     # the backend actually used for chat sends
        self._drag_offset = None
        self._games = list(games) if games else []
        self.active_game = None
        # HWND of a fullscreen/always-on-top game we temporarily demoted so the
        # overlay can sit above it; restored when the overlay hides.
        self._demoted_hwnd = None
        self._articles_repo = articles_repo
        self._db_path = db_path
        self._scrape_state_repo = scrape_state_repo
        self._redirect_state_repo = redirect_state_repo
        self._ingest_thread = None
        self._ingest_worker = None
        self._last_progress_done = None  # to detect a stalled (catching-up) count
        self._chat_repo = chat_repo
        self._ollama = ollama_client
        self._tabs = None
        self._guides_index = 0
        self._chat_session = None
        self._chat_view = []        # list of {"role", "text", "sources"}
        self._chat_thread = None
        self._chat_worker = None
        self._chat_cancelled = False  # stream stopped by hide/quit, not Ollama
        self._model = None
        # Ordered backend attempts for the current settings, e.g.
        # [(claude, model, "online"), (ollama, model, "local")]. The first is the
        # primary; later entries are silent offline fallbacks.
        self._backend_chain = []
        self._attempt = 0             # index into _backend_chain in flight
        self._pending_messages = None  # so a fallback can replay the same turn
        self._dock_edge = normalize_edge(
            settings_repo.get("dock_edge", "right") if settings_repo else "right")

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool  # keeps it off the taskbar
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self._build_ui()
        self._sync_layout_for_edge()

    # ---- layout ---------------------------------------------------------
    def _build_ui(self):
        self._outer = QHBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.setSpacing(0)

        self._spine = _SpineWidget()
        self._spine.setFixedWidth(painters.SPINE_W)

        self._root_panel = _PanelWidget()
        self._root_panel.setObjectName("OverlayRoot")

        # order set by _sync_layout_for_edge(); add both now
        self._outer.addWidget(self._spine)
        self._outer.addWidget(self._root_panel)

        col = QVBoxLayout(self._root_panel)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        col.addWidget(self._build_header())
        col.addWidget(self._build_tabs(), 1)
        col.addWidget(self._build_footer())

    def _build_header(self) -> QWidget:
        from PySide6.QtWidgets import QToolButton, QMenu
        header = QWidget()
        header.setObjectName("Header")
        lay = QVBoxLayout(header)
        lay.setContentsMargins(20, 16, 20, 12)
        lay.setSpacing(9)

        row1 = QHBoxLayout()
        word = QLabel("Meister")
        word.setObjectName("Wordmark")
        sub = QLabel("guide")
        sub.setObjectName("WordmarkSub")
        row1.addWidget(word)
        row1.addWidget(sub)
        row1.addStretch(1)
        self.hotkey_chip = QLabel(
            self._settings_repo.get("hotkey", "Alt+Insert")
            if self._settings_repo else "Alt+Insert")
        self.hotkey_chip.setObjectName("HotkeyChip")
        row1.addWidget(self.hotkey_chip)
        close = QPushButton("✕")
        close.setObjectName("CloseBtn")
        close.setFixedSize(28, 28)
        close.clicked.connect(self.hide)
        row1.addWidget(close)
        lay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(7)
        self.game_pill = QToolButton()
        self.game_pill.setObjectName("GamePill")
        self.game_pill.setPopupMode(QToolButton.InstantPopup)
        self._game_menu = QMenu(self.game_pill)
        self.game_pill.setMenu(self._game_menu)
        row2.addWidget(self.game_pill)
        row2.addStretch(1)
        lay.addLayout(row2)

        self._header = header
        self._rebuild_game_menu()
        self._update_game_pill()
        return header

    def _build_tabs(self) -> QTabWidget:
        tabs = QTabWidget()
        self._guides_index = tabs.addTab(self._build_guides_tab(), "Wiki")
        tabs.addTab(self._build_chat_tab(), "Ask Meister")
        tabs.addTab(self._build_settings_tab(), "⚙")
        tabs.setCurrentIndex(0)   # default landing = Wiki
        self._tabs = tabs
        return tabs

    def _build_chat_tab(self) -> QWidget:
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(10, 10, 10, 10)
        col.setSpacing(8)

        top = QHBoxLayout()
        self.chat_new_btn = QPushButton("New chat")
        self.chat_new_btn.clicked.connect(self._on_new_chat)
        top.addWidget(self.chat_new_btn)
        self.chat_history = QComboBox()
        self.chat_history.activated.connect(self._on_load_session)
        top.addWidget(self.chat_history, 1)
        self.chat_manage_btn = QPushButton("Manage")
        self.chat_manage_btn.clicked.connect(self._on_manage_chats)
        top.addWidget(self.chat_manage_btn)
        col.addLayout(top)

        self.chat_view = QTextBrowser()
        self.chat_view.setOpenLinks(False)   # we handle guide: links ourselves
        self.chat_view.anchorClicked.connect(self._on_chat_anchor)
        col.addWidget(self.chat_view, 1)

        self.chat_status = QLabel("")
        self.chat_status.setObjectName("Disclaimer")
        self.chat_status.setWordWrap(True)
        col.addWidget(self.chat_status)

        row = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Ask Meister…")
        self.chat_input.returnPressed.connect(self._on_send)
        row.addWidget(self.chat_input, 1)
        self.chat_send_btn = QPushButton("Send")
        self.chat_send_btn.clicked.connect(self._on_send)
        row.addWidget(self.chat_send_btn)
        col.addLayout(row)

        self._refresh_history()
        self._refresh_chat_backend()
        return page

    # ---- chat: backend selection + state ---------------------------------
    def _refresh_chat_backend(self):
        """Build the ordered backend chain from settings, set the primary
        self._chat_client + self._model, and update the input enabled/disabled
        state + status. Called on startup and whenever settings are saved.

        Modes: Always online -> [Claude]; Always local -> [Ollama];
        Auto -> [Claude (if a key is set)] then [Ollama (if available)], so a
        keyless install behaves exactly like the old local-only default and a
        keyed one prefers Claude with Ollama as a silent offline backup."""
        mode = (self._settings_repo.chat_backend()
                if self._settings_repo is not None else BACKEND_AUTO)

        chain, reason = [], "AI chat is unavailable."
        if mode == BACKEND_CLAUDE:
            attempt, reason = self._claude_attempt()
            if attempt:
                chain.append(attempt)
        elif mode == BACKEND_OLLAMA:
            attempt, reason = self._ollama_attempt()
            if attempt:
                chain.append(attempt)
        else:  # BACKEND_AUTO
            claude, _ = self._claude_attempt()
            if claude:
                chain.append(claude)
            ollama, reason = self._ollama_attempt()
            if ollama:
                chain.append(ollama)

        self._backend_chain = chain
        self._attempt = 0
        if not chain:
            self._chat_client = None
            self._model = None
            self._set_chat_enabled(False, reason)
            if hasattr(self, "footer_note"):
                self._refresh_footer()
            return
        client, model, _label = chain[0]
        self._chat_client = client
        self._model = model
        self._set_chat_enabled(True, self._backend_status(0))
        if hasattr(self, "footer_note"):
            self._refresh_footer()

    def _claude_attempt(self):
        """Returns ((client, model, "online"), None) if a key is set, else
        (None, reason)."""
        key = self._settings_repo.claude_api_key() if self._settings_repo else ""
        if not key:
            return None, "Enter a Claude API key in Settings to use the Claude backend."
        model = self._settings_repo.claude_model()
        return (self._claude_factory(key), model, "online"), None

    def _ollama_attempt(self):
        """Returns ((client, model, "local"), None) if Ollama is reachable with a
        model installed, else (None, reason)."""
        if self._ollama is None:
            return None, "AI chat is unavailable."
        try:
            models = self._ollama.list_model_info()
        except OllamaUnavailable:
            return None, "Meister needs Ollama running at localhost:11434."
        model = pick_best_model(models)
        if model is None:
            return None, "No Ollama model installed. Run: ollama pull llama3"
        return (self._ollama, model, "local"), None

    def _backend_status(self, i):
        """Status line for backend attempt i (the one about to be used)."""
        _client, model, label = self._backend_chain[i]
        if label == "online":
            base = f"Backend: Claude · {model}"
            if len(self._backend_chain) > 1:
                base += "  (offline backup ready)"
        else:
            base = f"Model: {model}"
        return base + self._guides_note()

    def _guides_note(self):
        if self._articles_repo is not None and self._articles_repo.count() == 0:
            return "  (No guides loaded yet — run Update guides for better answers.)"
        return ""

    def _set_chat_enabled(self, enabled, status):
        self.chat_input.setEnabled(enabled)
        self.chat_send_btn.setEnabled(enabled)
        self.chat_status.setText(status)

    def _refresh_history(self):
        self.chat_history.blockSignals(True)
        self.chat_history.clear()
        self.chat_history.addItem("History…", None)
        if self._chat_repo is not None:
            for s in self._chat_repo.list_sessions():
                self.chat_history.addItem(s.title or f"Chat {s.id}", s.id)
        self.chat_history.blockSignals(False)

    # ---- chat: conversation ---------------------------------------------
    def _ensure_session(self):
        if self._chat_session is None and self._chat_repo is not None:
            self._chat_session = self._chat_repo.create_session()
        return self._chat_session

    def _begin_exchange(self, question, sources):
        """Record the user turn + an empty assistant turn, persist the user
        message, and render. `sources` is a list of (pageid, title)."""
        self._ensure_session()
        if self._chat_repo is not None:
            self._chat_repo.add_message(self._chat_session, "user", question)
            if len(self._chat_repo.get_messages(self._chat_session)) == 1:
                self._chat_repo.set_title(self._chat_session, question[:40])
                self._refresh_history()
        self._chat_view.append({"role": "user", "text": question, "sources": []})
        self._chat_view.append({"role": "assistant", "text": "", "sources": sources})
        self._render_chat()

    def _on_send(self):
        if not self.chat_input.isEnabled() or self._chat_thread is not None:
            return
        question = self.chat_input.text().strip()
        if not question:
            return
        self.chat_input.clear()
        self._chat_cancelled = False

        sources, passages = [], []
        if self._articles_repo is not None:
            for hit in self._articles_repo.search_ranked(question, limit=3):
                article = self._articles_repo.get_article(hit.pageid)
                if article is None:
                    continue
                sources.append((hit.pageid, hit.title))
                passages.append((hit.title, relevant_passage(article.body, question)))

        history = [(m["role"], m["text"]) for m in self._chat_view if m["text"]]
        self._begin_exchange(question, sources)
        self._pending_messages = build_messages(question, passages, history)
        self._attempt = 0
        self._start_chat_worker()

    def _start_chat_worker(self):
        """Run self._pending_messages on the current backend attempt. Factored
        out of _on_send so a failed primary can replay the same turn on the next
        backend in the chain."""
        client, model, _label = self._backend_chain[self._attempt]
        self._chat_client = client
        self._model = model
        self.chat_input.setEnabled(False)
        self.chat_send_btn.setEnabled(False)
        self._chat_thread = QThread(self)
        self._chat_worker = ChatStreamWorker(client, model, self._pending_messages)
        self._chat_worker.moveToThread(self._chat_thread)
        self._chat_thread.started.connect(self._chat_worker.run)
        self._chat_worker.token.connect(self._on_chat_token)
        self._chat_worker.finished.connect(self._on_chat_finished)
        self._chat_worker.error.connect(self._on_chat_error)
        self._chat_thread.start()

    def _on_chat_token(self, chunk):
        if self._chat_view and self._chat_view[-1]["role"] == "assistant":
            self._chat_view[-1]["text"] += chunk
            self._render_chat()

    def _on_chat_finished(self, full_text):
        if self._chat_view and self._chat_view[-1]["role"] == "assistant":
            self._chat_view[-1]["text"] = full_text or self._chat_view[-1]["text"]
        # A cancelled stream yields a truncated answer; don't persist it as if
        # it were the model's complete reply (the user turn is already saved).
        if (not self._chat_cancelled and self._chat_repo is not None
                and self._chat_session is not None):
            self._chat_repo.add_message(self._chat_session, "assistant",
                                        self._chat_view[-1]["text"])
        self._render_chat()
        self._teardown_chat_thread()

    def _on_chat_error(self, message):
        # If the primary backend failed before streaming a single token (e.g. no
        # internet / Claude API error) and a backup backend is queued, retry the
        # same question on it silently rather than surfacing the error.
        nothing_streamed = bool(
            self._chat_view and self._chat_view[-1]["role"] == "assistant"
            and self._chat_view[-1]["text"] == "")
        if (not self._chat_cancelled and nothing_streamed
                and self._attempt + 1 < len(self._backend_chain)):
            self._stop_chat_thread()
            self._attempt += 1
            _client, model, _label = self._backend_chain[self._attempt]
            self.chat_status.setText(
                f"Online backend unavailable — answering locally with {model}.")
            self._start_chat_worker()
            return

        if self._chat_view and self._chat_view[-1]["role"] == "assistant":
            partial = self._chat_view[-1]["text"]
            self._chat_view[-1]["text"] = (partial + f"\n\n[error: {message}]").strip()
            if self._chat_repo is not None and self._chat_session is not None:
                self._chat_repo.add_message(self._chat_session, "assistant",
                                            self._chat_view[-1]["text"])
        self._render_chat()
        self._teardown_chat_thread()

    def _stop_chat_thread(self):
        """Quit + join the worker thread without touching the input controls, so
        a fallback attempt can start a fresh thread while input stays disabled."""
        if self._chat_thread is not None:
            self._chat_thread.quit()
            self._chat_thread.wait(5000)
        self._chat_thread = None
        self._chat_worker = None

    def _teardown_chat_thread(self):
        self._stop_chat_thread()
        self.chat_input.setEnabled(True)
        self.chat_send_btn.setEnabled(True)

    def _render_chat(self):
        parts = []
        for msg in self._chat_view:
            who = "You" if msg["role"] == "user" else "Meister"
            body = html.escape(msg["text"]).replace("\n", "<br>")
            parts.append(f"<p><b>{who}:</b> {body}</p>")
            if msg["sources"]:
                links = " · ".join(
                    f'<a href="guide:{pid}">{html.escape(title)}</a>'
                    for pid, title in msg["sources"]
                )
                parts.append(f'<p style="color:#9a7b53">Sources: {links}</p>')
        self.chat_view.setHtml("\n".join(parts))

    def _on_chat_anchor(self, url):
        ref = url.toString()
        if ref.startswith("guide:"):
            try:
                pageid = int(ref.split(":", 1)[1])
            except ValueError:
                return
            self._open_guide(pageid)

    def _open_guide(self, pageid):
        if self._articles_repo is None:
            return
        article = self._articles_repo.get_article(pageid)
        if article is None:
            return
        self.guides_detail.setPlainText(article.body)
        if self._tabs is not None:
            self._tabs.setCurrentIndex(self._guides_index)

    def _on_new_chat(self):
        self._chat_session = None
        self._chat_view = []
        self._render_chat()

    def _on_manage_chats(self):
        if self._chat_repo is None:
            return
        dlg = ChatManagerDialog(self._chat_repo, self)
        dlg.exec()
        # If the chat currently open in the view was deleted, drop to a blank one.
        if self._chat_session in dlg.deleted_ids:
            self._on_new_chat()
        self._refresh_history()

    def _on_load_session(self, index):
        session_id = self.chat_history.itemData(index)
        if session_id is None or self._chat_repo is None:
            return
        self._chat_session = session_id
        self._chat_view = [
            {"role": m.role, "text": m.content, "sources": []}
            for m in self._chat_repo.get_messages(session_id)
        ]
        self._render_chat()

    def _build_guides_tab(self) -> QWidget:
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(10, 10, 10, 10)
        col.setSpacing(8)

        self.guides_search = QLineEdit()
        self.guides_search.setPlaceholderText("Search guides…")
        self.guides_search.textChanged.connect(self._on_search)
        col.addWidget(self.guides_search)

        split = QSplitter(Qt.Horizontal)
        self.guides_results = QListWidget()
        self.guides_results.itemClicked.connect(self._on_result_clicked)
        split.addWidget(self.guides_results)

        self.guides_detail = QTextBrowser()
        self.guides_detail.setOpenExternalLinks(True)
        split.addWidget(self.guides_detail)
        split.setSizes([180, 280])
        col.addWidget(split, 1)

        bar = QHBoxLayout()
        self.guides_update_btn = QPushButton("Update guides")
        self.guides_update_btn.clicked.connect(self._on_update_guides)
        bar.addWidget(self.guides_update_btn)
        self.guides_progress = QProgressBar()
        self.guides_progress.setVisible(False)
        bar.addWidget(self.guides_progress, 1)
        self.guides_status = QLabel("")
        bar.addWidget(self.guides_status)
        col.addLayout(bar)

        self._refresh_guides_status()
        return page

    def _on_update_guides(self):
        if self._db_path is None or self._ingest_thread is not None:
            return
        self.guides_update_btn.setEnabled(False)
        self.guides_progress.setVisible(True)
        self.guides_progress.setRange(0, 0)  # indeterminate until first progress
        self.guides_status.setText("Starting…")
        self._last_progress_done = None

        self._ingest_thread = QThread(self)
        self._ingest_worker = IngestWorker(str(self._db_path))
        self._ingest_worker.moveToThread(self._ingest_thread)
        self._ingest_thread.started.connect(self._ingest_worker.run)
        self._ingest_worker.progress.connect(self._on_ingest_progress)
        self._ingest_worker.finished.connect(self._on_ingest_done)
        self._ingest_worker.error.connect(self._on_ingest_error)
        self._ingest_thread.start()

    def _on_ingest_progress(self, done, total):
        # `total` is the wiki's content-article statistic, but `done` counts every
        # namespace-0 page enumerated (disambiguations, stubs, …), so done can
        # overtake the estimate. Grow the denominator to match once it does, so the
        # bar never overflows and the text never inverts (e.g. "17,000/16,000").
        effective_total = max(total, done) if total > 0 else 0
        if effective_total > 0:
            self.guides_progress.setRange(0, effective_total)
            self.guides_progress.setValue(done)
        # When the stored count stalls (same as last update) mid-run, the ingest
        # is re-walking already-saved articles after a resume — show that rather
        # than a frozen-looking counter.
        if done == self._last_progress_done and 0 < done < effective_total:
            self.guides_status.setText(f"Catching up… ({done:,} saved)")
        elif effective_total:
            self.guides_status.setText(f"{done:,}/{effective_total:,}")
        else:
            self.guides_status.setText(f"Linking related topics… ({done:,})")
        self._last_progress_done = done

    def _on_ingest_done(self):
        self._teardown_ingest()
        self._refresh_guides_status()
        if self.guides_search.text().strip():
            self._on_search(self.guides_search.text())

    def _on_ingest_error(self, message):
        self._teardown_ingest()
        # Surface the real reason (truncated) instead of always blaming the
        # network — a generic message once hid a stale-resume-token bug.
        detail = (message or "unknown error").strip().splitlines()[0]
        if len(detail) > 160:
            detail = detail[:157] + "…"
        self.guides_status.setText(f"Update failed: {detail}")
        self.guides_status.setToolTip(message or "")

    def _teardown_ingest(self):
        self.guides_progress.setVisible(False)
        self.guides_update_btn.setEnabled(True)
        if self._ingest_thread is not None:
            self._ingest_thread.quit()
            self._ingest_thread.wait()
        self._ingest_thread = None
        self._ingest_worker = None

    # ---- settings -------------------------------------------------------
    def _build_settings_tab(self) -> QWidget:
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(16, 16, 16, 16)
        col.setSpacing(10)
        if self._settings_repo is None:
            col.addWidget(QLabel("Settings unavailable."))
            col.addStretch(1)
            return page

        # --- chat backend ---
        col.addWidget(QLabel("<b>AI chat backend</b>"))
        self.set_backend = QComboBox()
        self.set_backend.addItem("Auto — online when possible, offline backup", BACKEND_AUTO)
        self.set_backend.addItem("Always online (Claude)", BACKEND_CLAUDE)
        self.set_backend.addItem("Always local (Ollama) — offline & private", BACKEND_OLLAMA)
        idx = self.set_backend.findData(self._settings_repo.chat_backend())
        if idx >= 0:
            self.set_backend.setCurrentIndex(idx)
        col.addWidget(self.set_backend)

        col.addWidget(QLabel("Claude API key"))
        self.set_api_key = QLineEdit(self._settings_repo.claude_api_key())
        self.set_api_key.setEchoMode(QLineEdit.Password)
        self.set_api_key.setPlaceholderText("sk-ant-…  (stored locally; only used for the Claude backend)")
        col.addWidget(self.set_api_key)

        col.addWidget(QLabel("Claude model"))
        self.set_model = QComboBox()
        for name in AVAILABLE_MODELS:
            self.set_model.addItem(name, name)
        idx = self.set_model.findData(self._settings_repo.claude_model())
        if idx >= 0:
            self.set_model.setCurrentIndex(idx)
        col.addWidget(self.set_model)

        save = QPushButton("Save backend settings")
        save.clicked.connect(self._on_save_settings)
        col.addWidget(save)
        self.set_status = QLabel("")
        self.set_status.setObjectName("Disclaimer")
        self.set_status.setWordWrap(True)
        col.addWidget(self.set_status)

        # --- hotkey ---
        col.addWidget(QLabel("<b>Show / hide hotkey</b>"))
        row = QHBoxLayout()
        self.set_hotkey = QLineEdit(self._settings_repo.get("hotkey", "Alt+Insert"))
        self.set_hotkey.setPlaceholderText("e.g. Alt+Insert, Ctrl+Shift+M")
        row.addWidget(self.set_hotkey, 1)
        apply_hk = QPushButton("Apply")
        apply_hk.clicked.connect(self._on_apply_hotkey)
        row.addWidget(apply_hk)
        col.addLayout(row)
        self.set_hotkey_status = QLabel("")
        self.set_hotkey_status.setObjectName("Disclaimer")
        self.set_hotkey_status.setWordWrap(True)
        col.addWidget(self.set_hotkey_status)

        col.addStretch(1)
        return page

    def _on_save_settings(self):
        self._settings_repo.set("chat_backend", self.set_backend.currentData())
        self._settings_repo.set("claude_api_key", self.set_api_key.text().strip())
        self._settings_repo.set("claude_model", self.set_model.currentData())
        self._refresh_chat_backend()
        self.set_status.setText("Saved. " + (self.chat_status.text() or ""))

    def _on_apply_hotkey(self):
        spec = self.set_hotkey.text().strip()
        try:
            parse_hotkey(spec)
        except ValueError as err:
            self.set_hotkey_status.setText(f"Invalid hotkey: {err}")
            return
        applied = True
        if self._hotkey is not None:
            applied = self._hotkey.rebind(spec)
        self._settings_repo.set("hotkey", spec)
        if hasattr(self, "hotkey_chip"):
            self.hotkey_chip.setText(spec)
        self.set_hotkey_status.setText(
            f"Hotkey set to {spec}." if applied else
            f"Saved {spec}, but the OS rejected it (already in use?) — it'll apply next launch.")

    def _build_footer(self) -> QWidget:
        footer = QWidget()
        footer.setObjectName("Footer")
        footer.setFixedHeight(34)
        lay = QHBoxLayout(footer)
        lay.setContentsMargins(18, 0, 18, 0)
        self.footer_note = QLabel("")
        self.footer_note.setObjectName("FooterNote")
        lay.addWidget(self.footer_note)
        lay.addStretch(1)
        stack = QLabel("PySide6")
        stack.setObjectName("FooterStack")
        lay.addWidget(stack)
        self._refresh_footer()
        return footer

    def _refresh_footer(self):
        backend = (self._settings_repo.chat_backend()
                   if self._settings_repo is not None else BACKEND_AUTO)
        key = (self._settings_repo.claude_api_key()
               if self._settings_repo is not None else "")
        online = backend == BACKEND_CLAUDE or (backend == BACKEND_AUTO and key)
        self.footer_note.setText(
            "local-first · optional online" if online
            else "runs locally · no account · no cloud")

    # ---- guides ---------------------------------------------------------
    def _on_search(self, text):
        self.guides_results.clear()
        if self._articles_repo is None or not text.strip():
            return
        for hit in self._articles_repo.search(text):
            item = QListWidgetItem()
            item.setData(Qt.UserRole, hit.pageid)
            label = QLabel(
                f"<b>{html.escape(hit.title)}</b><br><span>{hit.excerpt_html}</span>"
            )
            label.setWordWrap(True)
            label.setContentsMargins(4, 4, 4, 4)
            self.guides_results.addItem(item)
            item.setSizeHint(label.sizeHint())
            self.guides_results.setItemWidget(item, label)

    def _on_result_clicked(self, item):
        if self._articles_repo is None:
            return
        pageid = item.data(Qt.UserRole)
        article = self._articles_repo.get_article(pageid)
        if article is None:
            return
        self.guides_detail.setPlainText(article.body)

    def _refresh_guides_status(self):
        if self._articles_repo is None:
            self.guides_status.setText("")
            return
        n = self._articles_repo.count()
        articles_done = True
        redirects_done = True
        if self._scrape_state_repo is not None:
            articles_done = (self._scrape_state_repo.load().continue_token is None
                             and n > 0)
        if self._redirect_state_repo is not None:
            rs = self._redirect_state_repo.load()
            redirects_done = rs.continue_token is None and rs.done > 0
        self.guides_status.setText(
            guides_status_text(n, articles_done, redirects_done)
        )

    # ---- game selection -------------------------------------------------
    def _rebuild_game_menu(self):
        if not hasattr(self, "_game_menu"):
            return
        self._game_menu.clear()
        for game in self._games:
            act = self._game_menu.addAction(game.name)
            act.triggered.connect(lambda _=False, gid=game.id:
                                  self._on_manual_pick_game(gid))

    def _update_game_pill(self):
        if self.active_game is None:
            self.game_pill.setText("●  No game detected")
            self.game_pill.setProperty("detected", False)
        else:
            self.game_pill.setText(f"●  {self.active_game.name} detected")
            self.game_pill.setProperty("detected", True)
        # re-polish so the [detected="true"] QSS state applies
        self.game_pill.style().unpolish(self.game_pill)
        self.game_pill.style().polish(self.game_pill)

    def _on_manual_pick_game(self, game_id):
        chosen = next((g for g in self._games if g.id == game_id), None)
        if chosen is not None:
            self._set_active(chosen, manual=True)

    def set_games(self, games):
        self._games = list(games)
        self._rebuild_game_menu()

    def _set_active(self, game, manual: bool):
        self.active_game = game
        self._update_game_pill()

    def set_detected_game(self, game):
        """Called by the detector. A detection always wins over a manual pick."""
        self._set_active(game, manual=False)

    # ---- docked geometry ------------------------------------------------
    def _current_screen_geometry(self):
        scr = QGuiApplication.screenAt(self.geometry().center()) \
            or QGuiApplication.primaryScreen()
        return scr.availableGeometry()

    def _apply_dock(self, screen=None):
        screen = screen if screen is not None else self._current_screen_geometry()
        self.setFixedWidth(PANEL_WIDTH)
        self.setGeometry(dock_rect(screen, self._dock_edge))
        self._sync_layout_for_edge()

    def _snap_to_nearest(self, window_center_x=None, screen=None):
        screen = screen if screen is not None else self._current_screen_geometry()
        cx = window_center_x if window_center_x is not None \
            else self.geometry().center().x()
        self._dock_edge = nearest_edge(cx, screen)
        if self._settings_repo is not None:
            self._settings_repo.set("dock_edge", self._dock_edge)
        self.setGeometry(dock_rect(screen, self._dock_edge))
        self._sync_layout_for_edge()

    def _sync_layout_for_edge(self):
        # Spine faces inward: edge 'right' -> spine on left (index 0); edge
        # 'left' -> spine on right (last). Reorder the outer layout + tell the
        # widgets which side to round.
        spine_left = (self._dock_edge == "right")
        self._spine.set_edge(self._dock_edge)
        self._root_panel.set_edge(self._dock_edge)
        self._outer.removeWidget(self._spine)
        self._outer.removeWidget(self._root_panel)
        if spine_left:
            self._outer.addWidget(self._spine)
            self._outer.addWidget(self._root_panel)
        else:
            self._outer.addWidget(self._root_panel)
            self._outer.addWidget(self._spine)

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_dock()

    def closeEvent(self, event):
        super().closeEvent(event)

    # ---- drag by header -------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._on_header(event.position()):
            self._drag_offset = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event):
        was_dragging = self._drag_offset is not None
        self._drag_offset = None
        if was_dragging:
            self._snap_to_nearest()

    def _on_header(self, pos) -> bool:
        # pos is relative to the window; the header sits in the top band of the
        # body panel, excluding the spine — which is on the left when docked
        # right and on the right when docked left.
        if pos.y() >= self._header.height():
            return False
        if self._dock_edge == "right":
            return pos.x() >= painters.SPINE_W
        return pos.x() < self.width() - painters.SPINE_W

    # ---- toggle ---------------------------------------------------------
    def toggle(self):
        if self.isVisible():
            self.hide()
        else:
            # Capture the game BEFORE we steal the foreground, then drop it out
            # of the always-on-top band so our overlay can sit above a
            # fullscreen game (e.g. Minecraft). Restored in hideEvent.
            self._demote_foreground_game()
            self.show()
            self.raise_()
            self.activateWindow()
            # WS_EX_TOPMOST + raise_() lose to a borderless-fullscreen game that
            # owns the foreground, so re-assert topmost natively on every show.
            force_window_to_front(int(self.winId()))

    def hideEvent(self, event):
        # Covers Alt+Insert and the tray toggle — all routes that hide the
        # overlay restore the game.
        if self._ingest_worker is not None:
            self._ingest_worker.cancel()
        if self._chat_worker is not None:
            self._chat_cancelled = True
            self._chat_worker.cancel()
        self._restore_demoted_game()
        super().hideEvent(event)

    def shutdown(self):
        """Stop background workers cleanly on app quit. quit()+wait() alone
        won't interrupt a worker's blocking loop, so cancel first."""
        self._chat_cancelled = True
        if self._chat_worker is not None:
            self._chat_worker.cancel()
        if self._ingest_worker is not None:
            self._ingest_worker.cancel()
        self._teardown_chat_thread()
        self._teardown_ingest()

    def _demote_foreground_game(self):
        if sys.platform != "win32":
            return
        fg = get_foreground_window()
        my_hwnd = int(self.winId())
        # Only touch a window that is *already* topmost (a fullscreen game or
        # another always-on-top app) so we never disturb ordinary windows.
        if fg and fg != my_hwnd and is_window_topmost(fg):
            set_window_topmost(fg, False)
            self._demoted_hwnd = fg

    def _restore_demoted_game(self):
        if self._demoted_hwnd:
            set_window_topmost(self._demoted_hwnd, True)
            self._demoted_hwnd = None
