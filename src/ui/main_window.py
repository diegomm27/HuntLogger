from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from ..config import AppConfig, guess_install_paths, load_config, save_config
from ..db import Database
from ..evidence_collector import SessionEvidenceCollector
from ..screen_capture import (
    PostMatchCaptureWorker,
    PostMatchLogTailer,
    debug as capture_debug,
    describe_window_capture_blocker,
    find_game_log,
    inspect_hunt_window,
)
from ..vision_parser import process_recent_captures_for_vision_debug
from ..watcher import AttributesWatcher
from .account_panel import AccountPanel
from .evidence_panel import EvidencePanel
from .match_list import MatchListWidget
from .theme import PALETTE


APP_NAME = "HUNT LOGGER"

# Panel indices for _left_stack
_IDX_MATCHES  = 0
_IDX_SESSIONS = 1
_IDX_ACCOUNT  = 2


class _SettingsDialog(QDialog):
    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("SETTINGS — HUNT LOGGER")
        self.setModal(True)
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("SETTINGS")
        title.setStyleSheet(
            f"color: {PALETTE['gold_hi']}; font-size: 14px; font-weight: bold; letter-spacing: 4px;"
        )
        layout.addWidget(title)

        path_group = QGroupBox("INSTALL PATH")
        path_row = QHBoxLayout(path_group)
        path_row.setContentsMargins(12, 14, 12, 12)
        path_row.setSpacing(8)
        self._path_edit = QLineEdit(config.install_path or "")
        self._path_edit.setPlaceholderText("Select Hunt: Showdown install folder…")
        browse_btn = QPushButton("BROWSE")
        browse_btn.clicked.connect(self._browse)
        path_row.addWidget(self._path_edit, 1)
        path_row.addWidget(browse_btn)
        layout.addWidget(path_group)

        tools_group = QGroupBox("TOOLS")
        tools_layout = QVBoxLayout(tools_group)
        tools_layout.setContentsMargins(12, 14, 12, 12)
        tools_layout.setSpacing(8)
        self.btn_parse_screenshots = QPushButton("PARSE SCREENSHOTS")
        tools_layout.addWidget(self.btn_parse_screenshots)
        layout.addWidget(tools_group)

        layout.addStretch()

        btns = QHBoxLayout()
        btns.addStretch()
        cancel_btn = QPushButton("CANCEL")
        cancel_btn.clicked.connect(self.reject)
        apply_btn = QPushButton("APPLY")
        apply_btn.setObjectName("Primary")
        apply_btn.clicked.connect(self.accept)
        btns.addWidget(cancel_btn)
        btns.addWidget(apply_btn)
        layout.addLayout(btns)

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Select Hunt: Showdown install folder",
            self._path_edit.text() or str(Path.home()),
        )
        if folder:
            self._path_edit.setText(folder)

    def install_path(self) -> str:
        return self._path_edit.text().strip()


class _ScreenshotParseWorker(QThread):
    parse_finished: Signal = Signal(str)
    parse_error: Signal = Signal(str)

    def __init__(
        self,
        db: Database,
        *,
        limit: int,
        sample_per_group: int | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._db = db
        self._limit = limit
        self._sample_per_group = sample_per_group

    def run(self) -> None:
        try:
            result = process_recent_captures_for_vision_debug(
                self._db,
                limit=self._limit,
                sample_per_group=self._sample_per_group,
                cleanup_complete=True,
            )
            self.parse_finished.emit(result.message)
        except Exception as exc:
            self.parse_error.emit(f"Screenshot parsing failed: {exc}")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Hunt: Showdown 1896 — Match Logger")
        self.resize(1280, 820)

        self._config: AppConfig = load_config()
        self._db = Database()
        self._watcher = AttributesWatcher(self._db)
        self._evidence_collector = SessionEvidenceCollector(self._db)
        self._postmatch_tailer = PostMatchLogTailer()
        self._capture_workers: list[PostMatchCaptureWorker] = []
        self._parse_workers: list[_ScreenshotParseWorker] = []
        self._last_game_log_path: Path | None = None
        self._last_capture_started_at = 0.0
        self._pending_capture_trigger: str | None = None
        self._pending_capture_deadline = 0.0
        self._capture_warning_dialog: QMessageBox | None = None

        self._build_ui()
        self._wire_signals()
        self._initial_setup()

    # ------- construction -------

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("centralwidget")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_top_bar())

        self._left_stack = QStackedWidget()
        self.match_list    = MatchListWidget(self._db)
        self.evidence_panel = EvidencePanel(self._db)
        self.account_panel  = AccountPanel()
        self._left_stack.addWidget(self.match_list)      # _IDX_MATCHES
        self._left_stack.addWidget(self.evidence_panel)  # _IDX_SESSIONS
        self._left_stack.addWidget(self.account_panel)   # _IDX_ACCOUNT
        root.addWidget(self._left_stack, 1)

        self.setStatusBar(QStatusBar())

    def _build_top_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(70)

        outer = QVBoxLayout(bar)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        content = QFrame()
        content.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(content)
        layout.setContentsMargins(22, 10, 22, 10)
        layout.setSpacing(16)

        # Brand block — title + subtitle stacked
        brand = QWidget()
        brand.setStyleSheet("background: transparent;")
        brand_v = QVBoxLayout(brand)
        brand_v.setContentsMargins(0, 0, 0, 0)
        brand_v.setSpacing(0)
        title = QLabel(APP_NAME)
        title.setObjectName("AppTitle")
        subtitle = QLabel("HUNT: SHOWDOWN 1896 · MATCH LOGGER")
        subtitle.setObjectName("AppSubtitle")
        brand_v.addWidget(title)
        brand_v.addWidget(subtitle)
        layout.addWidget(brand)

        # Separator after brand
        sep1 = QFrame()
        sep1.setFixedWidth(1)
        sep1.setFixedHeight(42)
        sep1.setStyleSheet(f"background: {PALETTE['border']};")
        layout.addWidget(sep1)

        # Status indicator — dot + label
        status_wrap = QWidget()
        status_wrap.setStyleSheet("background: transparent;")
        status_h = QHBoxLayout(status_wrap)
        status_h.setContentsMargins(0, 0, 0, 0)
        status_h.setSpacing(6)
        self.status_dot = QLabel("●")
        self.status_dot.setObjectName("StatusDot")
        self.status_dot.setProperty("state", "idle")
        self.status_label = QLabel("IDLE")
        self.status_label.setObjectName("StatusLabel")
        self.status_label.setProperty("state", "idle")
        status_h.addWidget(self.status_dot)
        status_h.addWidget(self.status_label)
        layout.addWidget(status_wrap)

        # Separator after status
        sep2 = QFrame()
        sep2.setFixedWidth(1)
        sep2.setFixedHeight(42)
        sep2.setStyleSheet(f"background: {PALETTE['border']};")
        layout.addWidget(sep2)

        # Nav buttons — switch left panel
        self._nav_btns: list[QPushButton] = []
        for i, label in enumerate(["MATCHES", "MY GAME SESSIONS", "INGAME SETTINGS"]):
            btn = QPushButton(label)
            btn.setObjectName("NavBtn")
            btn.setProperty("active", "true" if i == 0 else "false")
            self._nav_btns.append(btn)
            layout.addWidget(btn)

        layout.addStretch(1)

        # Action buttons (right side)
        self.btn_recording = QPushButton("STOP RECORDING")
        self.btn_recording.setObjectName("Primary")
        self.btn_settings = QPushButton("SETTINGS")

        layout.addWidget(self.btn_recording)
        layout.addWidget(self.btn_settings)

        outer.addWidget(content, 1)

        accent = QFrame()
        accent.setObjectName("TopBarAccent")
        accent.setFixedHeight(2)
        outer.addWidget(accent)

        return bar

    # ------- signals -------

    def _wire_signals(self) -> None:
        for i, btn in enumerate(self._nav_btns):
            btn.clicked.connect(lambda checked, idx=i: self._set_nav_active(idx))

        self.btn_recording.clicked.connect(self._on_toggle_recording)
        self.btn_settings.clicked.connect(self._on_settings_clicked)

        self.match_list.match_selected.connect(self._on_match_selected)
        self.match_list.delete_requested.connect(self._on_match_delete_requested)

        self._watcher.match_saved.connect(self._on_match_saved)
        self._watcher.status_changed.connect(self._on_watch_status)
        self._watcher.error.connect(self._on_watch_error)

        # Poll + refresh every 15s as fallback for watchdog missing atomic writes.
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(15_000)
        self._refresh_timer.timeout.connect(self._on_poll_tick)
        self._refresh_timer.start()

        # Fast lightweight tailer for the short-lived post-match summary screen.
        self._postmatch_timer = QTimer(self)
        self._postmatch_timer.setInterval(500)
        self._postmatch_timer.timeout.connect(self._on_postmatch_tick)
        self._postmatch_timer.start()

    # ------- initial state -------

    def _initial_setup(self) -> None:
        if not self._config.install_path:
            for p in guess_install_paths():
                self._config.install_path = str(p)
                save_config(self._config)
                break

        self._update_path_label()
        self._sync_recording_state()
        if not self._db.list_hunt_sessions(limit=1):
            self._evidence_collector.backfill_game_log_evidence()
        if self._config.screenshot_capture_enabled:
            self._reset_postmatch_tailer()
            self._collect_evidence(show_message=False)
        self.match_list.refresh()
        self.evidence_panel.refresh()
        self._load_latest_match()
        if self.match_list.count() == 0:
            self._set_nav_active(_IDX_SESSIONS)
        if self._config.is_valid_install():
            self._reload_account()
            if self._config.screenshot_capture_enabled:
                self._start_watching()
        self._sync_recording_state()

    # ------- actions -------

    def _on_settings_clicked(self) -> None:
        dlg = _SettingsDialog(self._config, self)
        dlg.btn_parse_screenshots.clicked.connect(self._on_parse_screenshots_clicked)
        if dlg.exec() != QDialog.Accepted:
            return
        new_path = dlg.install_path()
        path_changed = new_path != (self._config.install_path or "")
        if new_path and path_changed:
            from ..config import find_attributes_xml
            candidate = Path(new_path)
            attrs = find_attributes_xml(candidate)
            if attrs is None or not attrs.exists():
                result = QMessageBox.question(
                    self,
                    "attributes.xml not found",
                    f"No attributes.xml was found under:\n{candidate}\n\n"
                    "Use this folder anyway?",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if result != QMessageBox.Yes:
                    return
        self._config.install_path = new_path or None
        save_config(self._config)
        self._update_path_label()
        self._sync_recording_state()
        if path_changed:
            if self._config.screenshot_capture_enabled:
                self._reset_postmatch_tailer()
                self._collect_evidence(show_message=True)
            self.evidence_panel.refresh()
            self._reload_account()
            if (
                self._config.screenshot_capture_enabled
                and self._config.is_valid_install()
                and not self._watcher.is_watching()
            ):
                self._start_watching()

    def _on_toggle_recording(self) -> None:
        if self._config.screenshot_capture_enabled:
            self._config.screenshot_capture_enabled = False
            self._watcher.stop()
            self._db.close_active_session()
            self.statusBar().showMessage("Recording stopped.", 6000)
        else:
            if not self._config.is_valid_install():
                QMessageBox.warning(
                    self,
                    "Install path not set",
                    "Set a valid Hunt: Showdown install folder in Settings first.",
                )
                self._config.screenshot_capture_enabled = False
                save_config(self._config)
                self._sync_recording_state()
                return
            self._config.screenshot_capture_enabled = True
            self._reset_postmatch_tailer()
            self._collect_evidence(show_message=False)
            self._start_watching()
            self.statusBar().showMessage("Recording enabled.", 6000)
        save_config(self._config)
        self.evidence_panel.refresh()
        self.match_list.refresh(preserve_selection=True)
        self._sync_recording_state()

    def _on_parse_screenshots_clicked(self) -> None:
        self._start_screenshot_parse(
            limit=5000,
            sample_per_group=None,
            message="Parsing retained screenshots...",
        )

    def _start_screenshot_parse(
        self,
        *,
        limit: int,
        sample_per_group: int | None,
        message: str,
    ) -> None:
        if self._parse_workers:
            self.statusBar().showMessage("Screenshot parsing is already running.", 6000)
            return
        worker = _ScreenshotParseWorker(
            self._db,
            limit=limit,
            sample_per_group=sample_per_group,
            parent=self,
        )
        worker.parse_finished.connect(self._on_screenshot_parse_finished)
        worker.parse_error.connect(self._on_screenshot_parse_error)
        worker.finished.connect(self._on_screenshot_parse_worker_done)
        self._parse_workers.append(worker)
        self.statusBar().showMessage(message, 10000)
        worker.start()

    def _start_watching(self) -> None:
        p = self._config.attributes_path
        if p is None:
            self._sync_recording_state()
            return
        self._watcher.start(p)

    def _load_latest_match(self) -> None:
        saved_id = self._config.last_selected_match_id
        if isinstance(saved_id, int) and saved_id and self._db.get_match_header(saved_id):
            key = f"exact:{saved_id}"
            self.match_list.select_match(key)
            return

    def _reload_account(self) -> None:
        p = self._config.attributes_path
        if p and p.exists():
            self.account_panel.reload(p)

    # ------- slots -------

    def _on_match_selected(self, match_id: object) -> None:
        key = str(match_id)
        if key.startswith("exact:"):
            self._config.last_selected_match_id = int(key.split(":", 1)[1])
            save_config(self._config)

    def _on_match_delete_requested(self, match_id: object) -> None:
        key = str(match_id)
        if key.startswith("visual:"):
            title = "Delete screenshot-derived game?"
            text = (
                "This removes the selected screenshot-derived game, its parsed OCR fields, "
                "and the retained capture files for that group."
            )
        elif key.startswith("exact:"):
            title = "Delete saved game?"
            text = "This removes the selected saved game from the local database."
        else:
            return

        result = QMessageBox.question(
            self,
            title,
            text,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if result != QMessageBox.Yes:
            return

        if key.startswith("visual:"):
            deleted = self._db.delete_visual_match(key[len("visual:"):])
            if deleted:
                self.statusBar().showMessage(
                    f"Deleted screenshot-derived game ({deleted} capture frames removed).",
                    8000,
                )
        else:
            self._db.delete_match(int(key.split(":", 1)[1]))
            self.statusBar().showMessage("Deleted saved game.", 8000)

        self.match_list.refresh(preserve_selection=False)
        self.evidence_panel.refresh()

    def _on_poll_tick(self) -> None:
        if not self._config.screenshot_capture_enabled:
            self.match_list.refresh(preserve_selection=True)
            self.evidence_panel.refresh()
            self._sync_recording_state()
            return
        if self._config.is_valid_install() and not self._watcher.is_watching():
            self._start_watching()
        if self._watcher.is_watching():
            self._watcher.poll_once()
        self._collect_evidence(show_message=False)
        self.match_list.refresh(preserve_selection=True)
        self.evidence_panel.refresh()
        self._sync_recording_state()

    def _on_postmatch_tick(self) -> None:
        if not self._config.screenshot_capture_enabled:
            return
        if self._pending_capture_trigger is not None:
            state = inspect_hunt_window()
            if state.is_ready:
                trigger_line = self._pending_capture_trigger
                self._pending_capture_trigger = None
                self._pending_capture_deadline = 0.0
                self._dismiss_capture_warning()
                self._start_postmatch_capture(trigger_line)
                return
            if time.monotonic() >= self._pending_capture_deadline:
                capture_debug("Pending post-match capture expired before Hunt became capturable")
                self._pending_capture_trigger = None
                self._pending_capture_deadline = 0.0
                self._dismiss_capture_warning()
                self.statusBar().showMessage(
                    "Missed post-match screenshots because Hunt stayed minimized or hidden.",
                    10000,
                )
            return
        path = self._game_log_path()
        trigger_line = self._postmatch_tailer.poll(path)
        if not trigger_line:
            return
        capture_debug(f"Trigger line received by main window: {trigger_line}")
        if self._capture_workers:
            capture_debug(
                f"Trigger ignored because {len(self._capture_workers)} capture worker(s) are active"
            )
            return
        elapsed = time.monotonic() - self._last_capture_started_at
        if elapsed < 90:
            capture_debug(f"Trigger ignored due to capture cooldown. elapsed={elapsed:.1f}s")
            return
        state = inspect_hunt_window()
        if not state.is_ready:
            self._queue_postmatch_capture(trigger_line, describe_window_capture_blocker(state))
            return
        self._start_postmatch_capture(trigger_line)

    def _on_match_saved(self, match_id: int) -> None:
        self._reload_account()
        self._collect_evidence(show_message=False)
        self.match_list.refresh(preserve_selection=True)
        self.evidence_panel.refresh()
        self.match_list.select_match(f"exact:{match_id}")
        self.statusBar().showMessage(f"New match logged — #{match_id}", 8000)

    def _on_watch_status(self, state: str) -> None:
        self._sync_recording_state()

    def _on_watch_error(self, message: str) -> None:
        self._set_status("error", "NOT READY")
        self.statusBar().showMessage(message, 8000)

    def _on_capture_saved(self, row_id: int) -> None:
        capture_debug(f"Capture row saved: id={row_id}")
        self.match_list.refresh(preserve_selection=True)
        self.evidence_panel.refresh()

    def _on_capture_finished(self, count: int) -> None:
        sender = self.sender()
        if isinstance(sender, PostMatchCaptureWorker) and sender in self._capture_workers:
            self._capture_workers.remove(sender)
            sender.deleteLater()
        capture_debug(f"Capture worker finished signal received. count={count}")
        self.match_list.refresh(preserve_selection=True)
        self.evidence_panel.refresh()
        self._start_screenshot_parse(
            limit=max(1, count),
            sample_per_group=10,
            message=f"Post-match screenshots captured: {count}. Parsing in background...",
        )

    def _on_capture_error(self, message: str) -> None:
        sender = self.sender()
        if isinstance(sender, PostMatchCaptureWorker) and sender in self._capture_workers:
            self._capture_workers.remove(sender)
            sender.deleteLater()
        capture_debug(f"Capture worker error signal received: {message}")
        self.statusBar().showMessage(message, 10000)

    def _on_screenshot_parse_finished(self, message: str) -> None:
        capture_debug(message)
        self.match_list.refresh(preserve_selection=True)
        self.evidence_panel.refresh()
        self.statusBar().showMessage(message, 10000)

    def _on_screenshot_parse_error(self, message: str) -> None:
        capture_debug(message)
        self.statusBar().showMessage(message, 10000)

    def _on_screenshot_parse_worker_done(self) -> None:
        sender = self.sender()
        if isinstance(sender, _ScreenshotParseWorker) and sender in self._parse_workers:
            self._parse_workers.remove(sender)
            sender.deleteLater()

    # ------- helpers -------

    def _set_nav_active(self, idx: int) -> None:
        self._left_stack.setCurrentIndex(idx)
        for i, btn in enumerate(self._nav_btns):
            btn.setProperty("active", "true" if i == idx else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _set_status(self, state: str, text: str) -> None:
        self.status_label.setText(text)
        for w in (self.status_label, self.status_dot):
            w.setProperty("state", state)
            w.style().unpolish(w)
            w.style().polish(w)

    def _update_path_label(self) -> None:
        if not self._config.is_valid_install():
            if not self._config.install_path:
                self.statusBar().showMessage(
                    "Install path not set — open Settings to configure.", 0)
            else:
                self.statusBar().showMessage(
                    f"Invalid install path — open Settings to reconfigure.", 0)

    def _sync_recording_state(self) -> None:
        ready = self._config.screenshot_capture_enabled and self._config.is_valid_install()
        self.btn_recording.setText(
            "STOP RECORDING" if self._config.screenshot_capture_enabled else "START RECORDING"
        )
        self._set_status("watching" if ready else "error", "READY" if ready else "NOT READY")

    def _game_log_path(self) -> Path | None:
        if not self._config.install_path:
            capture_debug("No install path configured; cannot resolve Game.log")
            return None
        path = find_game_log(Path(self._config.install_path), verbose=False)
        if path != self._last_game_log_path:
            capture_debug(f"Resolved Game.log path changed: {path}")
            self._last_game_log_path = path
        return path

    def _reset_postmatch_tailer(self) -> None:
        capture_debug("Resetting post-match tailer")
        self._postmatch_tailer.reset(self._game_log_path())

    def _queue_postmatch_capture(self, trigger_line: str, reason: str) -> None:
        if self._pending_capture_trigger is None:
            capture_debug(f"Queueing post-match capture until Hunt is visible: {reason}")
        self._pending_capture_trigger = trigger_line
        self._pending_capture_deadline = time.monotonic() + 12.0
        self.statusBar().showMessage(
            "Post-match detected. Restore Hunt now; desktop fallback is disabled.",
            12000,
        )
        self._show_capture_warning(reason)

    def _show_capture_warning(self, reason: str) -> None:
        text = (
            "Hunt must be visible to capture the post-match summary.\n\n"
            f"{reason}\n\n"
            "The logger will wait briefly for the window to return and will not save desktop screenshots."
        )
        if self._capture_warning_dialog is None:
            dlg = QMessageBox(self)
            dlg.setIcon(QMessageBox.Warning)
            dlg.setWindowTitle("Restore Hunt Window")
            dlg.setText(text)
            dlg.setStandardButtons(QMessageBox.Ok)
            dlg.setModal(False)
            dlg.setWindowModality(Qt.NonModal)
            dlg.setWindowFlag(Qt.WindowStaysOnTopHint, True)
            dlg.finished.connect(self._on_capture_warning_closed)
            self._capture_warning_dialog = dlg
        else:
            self._capture_warning_dialog.setText(text)
        self._capture_warning_dialog.show()
        self._capture_warning_dialog.raise_()
        self._capture_warning_dialog.activateWindow()

    def _on_capture_warning_closed(self, _result: int) -> None:
        self._capture_warning_dialog = None

    def _dismiss_capture_warning(self) -> None:
        if self._capture_warning_dialog is None:
            return
        dlg = self._capture_warning_dialog
        self._capture_warning_dialog = None
        dlg.close()
        dlg.deleteLater()

    def _start_postmatch_capture(self, trigger_line: str) -> None:
        self._dismiss_capture_warning()
        capture_debug("Starting post-match screenshot capture worker")
        self._last_capture_started_at = time.monotonic()
        worker = PostMatchCaptureWorker(
            self._db,
            trigger_event=trigger_line,
            frames=40,
            interval_seconds=0.5,
            parent=self,
        )
        worker.captured.connect(self._on_capture_saved)
        worker.finished_capture.connect(self._on_capture_finished)
        worker.error.connect(self._on_capture_error)
        self._capture_workers.append(worker)
        self.statusBar().showMessage(
            "Post-match transition detected; capturing screenshots for 20 seconds...",
            15000,
        )
        worker.start()

    def _collect_evidence(self, *, show_message: bool) -> None:
        install_path = Path(self._config.install_path) if self._config.install_path else None
        attributes_path = self._config.attributes_path
        result = self._evidence_collector.collect_all(
            install_path=install_path,
            attributes_path=attributes_path,
        )
        if not self._db.list_hunt_sessions(limit=1):
            backfill = self._evidence_collector.backfill_game_log_evidence()
            result.session_events_created += backfill.session_events_created
            result.match_candidates_created += backfill.match_candidates_created
            result.snapshots_created += backfill.snapshots_created
            result.achievement_deltas_created += backfill.achievement_deltas_created
            result.account_deltas_created += backfill.account_deltas_created
            if backfill.errors:
                for error in backfill.errors:
                    result.add_error(error)
        if not show_message:
            return

        parts = []
        if result.snapshots_created:
            parts.append(f"{result.snapshots_created} snapshots")
        if result.session_events_created:
            parts.append(f"{result.session_events_created} log events")
        if result.match_candidates_created:
            parts.append(f"{result.match_candidates_created} hunt sessions")
        if result.achievement_deltas_created:
            parts.append(f"{result.achievement_deltas_created} Steam deltas")
        if result.account_deltas_created:
            parts.append(f"{result.account_deltas_created} account deltas")
        if result.errors:
            parts.append(f"{len(result.errors)} errors")

        message = "Session refresh: " + (", ".join(parts) if parts else "no changes")
        self.statusBar().showMessage(message, 8000)

    # ------- lifecycle -------

    def closeEvent(self, event) -> None:
        try:
            self._dismiss_capture_warning()
            self._watcher.stop()
            for worker in list(self._capture_workers):
                worker.wait(5000)
            for worker in list(self._parse_workers):
                worker.wait(5000)
            self._db.close_active_session()
        finally:
            self._db.close()
        super().closeEvent(event)
