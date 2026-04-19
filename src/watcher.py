from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QMetaObject, QObject, Qt, QThread, Signal, Slot
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .db import Database
from .parser import Match, compute_xml_hash, parse_attributes_text


class _Handler(FileSystemEventHandler):
    """Reads the file immediately on every OS event and passes the raw text back.

    Reading in the watchdog thread (before any debounce) is the key change: if
    Hunt writes match data then overwrites it within ~1 s, we capture the
    first write here instead of losing it while waiting for a debounce.
    """

    def __init__(self, target: Path, callback: Callable[[str], None]) -> None:
        self.target = target.resolve()
        self._callback = callback

    def _match(self, path: str) -> bool:
        try:
            return Path(path).resolve() == self.target
        except OSError:
            return False

    def _fire(self) -> None:
        try:
            text = self.target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        if text.strip():
            self._callback(text)

    def on_modified(self, event) -> None:
        if not event.is_directory and self._match(event.src_path):
            self._fire()

    def on_created(self, event) -> None:
        if not event.is_directory and self._match(event.src_path):
            self._fire()

    def on_moved(self, event) -> None:
        dest = getattr(event, "dest_path", None)
        if dest and self._match(dest):
            self._fire()


class AttributesWatcher(QObject):
    """Watches attributes.xml and emits match_saved when a new match is logged."""

    match_saved = Signal(int)
    match_seen = Signal(str)
    error = Signal(str)
    status_changed = Signal(str)
    # Internal signal used to marshal text from watchdog thread → main thread.
    _text_ready = Signal(str)

    def __init__(self, db: Database, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._db = db
        self._observer: Observer | None = None
        self._path: Path | None = None
        self._last_hash: str | None = None
        # Connect internal signal on the main thread so _process_text runs there.
        self._text_ready.connect(self._process_text, Qt.QueuedConnection)

    def is_watching(self) -> bool:
        return self._observer is not None

    def start(self, attributes_path: Path) -> None:
        self.stop()
        self._path = attributes_path
        if not attributes_path.exists():
            self.error.emit(f"attributes.xml not found at {attributes_path}")
            self.status_changed.emit("idle")
            return
        self._observer = Observer()
        handler = _Handler(attributes_path, self._on_text_from_thread)
        self._observer.schedule(handler, str(attributes_path.parent), recursive=False)
        self._observer.start()
        self.status_changed.emit("watching")
        self.poll_once()

    def stop(self) -> None:
        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=2.0)
            except Exception:
                pass
            self._observer = None
        self.status_changed.emit("idle")

    def _on_text_from_thread(self, text: str) -> None:
        """Called from watchdog thread — emit signal to cross to main thread."""
        self._text_ready.emit(text)

    @Slot()
    def poll_once(self) -> None:
        """Fallback manual poll (called from main thread or timer)."""
        if self._path is None or not self._path.exists():
            return
        try:
            text = self._path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            self.error.emit(f"read failed: {e}")
            return
        if text.strip():
            self._process_text(text)

    @Slot(str)
    def _process_text(self, text: str) -> None:
        """Process a snapshot of attributes.xml on the main thread."""
        xml_hash = compute_xml_hash(text)
        if xml_hash == self._last_hash:
            return
        self._last_hash = xml_hash
        self.match_seen.emit(xml_hash)
        if self._db.match_exists(xml_hash):
            return
        try:
            match = parse_attributes_text(text, datetime.now())
        except Exception as e:
            self.error.emit(f"parse failed: {e}")
            return
        if not match.has_match_data:
            return
        match_id = self._db.save_match(match)
        if match_id is not None:
            self.match_saved.emit(match_id)


class ImportWorker(QThread):
    """One-shot import of an existing attributes.xml file at startup."""

    finished_ok = Signal(object)  # match_id or None
    error = Signal(str)

    def __init__(self, db: Database, path: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._db = db
        self._path = path

    def run(self) -> None:
        try:
            if not self._path.exists():
                self.finished_ok.emit(None)
                return
            text = self._path.read_text(encoding="utf-8", errors="replace")
            if not text.strip():
                self.finished_ok.emit(None)
                return
            xml_hash = compute_xml_hash(text)
            if self._db.match_exists(xml_hash):
                self.finished_ok.emit(None)
                return
            match = parse_attributes_text(text, datetime.now())
            if not match.has_match_data:
                self.finished_ok.emit(None)
                return
            match_id = self._db.save_match(match)
            self.finished_ok.emit(match_id)
        except Exception as e:
            self.error.emit(str(e))
