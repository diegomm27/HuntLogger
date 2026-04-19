from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .db import Database
from .evidence import (
    capture_file,
    diff_account_attributes,
    diff_achievement_values,
    extract_achievement_values,
    extract_attributes,
    parse_game_log,
    parse_json_text,
)


@dataclass
class CollectionResult:
    snapshots_created: int = 0
    session_events_created: int = 0
    match_candidates_created: int = 0
    achievement_deltas_created: int = 0
    account_deltas_created: int = 0
    errors: list[str] | None = None

    def add_error(self, message: str) -> None:
        if self.errors is None:
            self.errors = []
        self.errors.append(message)


_STEAM_SUBDIRS = [
    "Program Files/Steam",
    "Program Files (x86)/Steam",
    "Steam",
    "SteamLibrary",
]

_DRIVES = ["C", "D", "E", "F", "G"]


class SessionEvidenceCollector:
    """Collects current local evidence without pretending it is exact match data."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def collect_all(
        self,
        *,
        install_path: Path | None,
        attributes_path: Path | None,
    ) -> CollectionResult:
        result = CollectionResult()
        session_id = self._db.get_or_create_active_session()

        if install_path is not None:
            self._collect_game_log(install_path, session_id, result)
            for path in self._find_steam_achievement_paths(install_path):
                self._collect_steam_achievements(path, result)
            for path in self._find_binary_save_paths(install_path):
                self._collect_binary_save(path, result)

        if attributes_path is not None:
            self._collect_attributes(attributes_path, result)

        return result

    def backfill_game_log_evidence(self, limit: int = 250) -> CollectionResult:
        result = CollectionResult()
        snapshot = self._db.get_latest_source_snapshot_by_type("game_log")
        if snapshot is None or not snapshot.get("content_text"):
            return result

        source_snapshot_id = int(snapshot["id"])
        fallback = (
            datetime.fromisoformat(snapshot["mtime"])
            if snapshot.get("mtime") else None
        )
        events, candidates = parse_game_log(snapshot["content_text"], fallback)
        for event in events:
            event_id = self._db.save_session_event(
                session_id=None,
                timestamp=event.timestamp,
                event_type=event.event_type,
                summary=event.summary,
                confidence=event.confidence,
                source_snapshot_id=source_snapshot_id,
                line_no=event.line_no,
                payload=event.payload,
            )
            if event_id is not None:
                result.session_events_created += 1
        for candidate in candidates:
            candidate_id = self._db.save_match_candidate(
                session_id=None,
                started_at=candidate.started_at,
                ended_at=candidate.ended_at,
                postmatch_at=candidate.postmatch_at,
                map_name=candidate.map_name,
                duration_seconds=candidate.duration_seconds,
                confidence=candidate.confidence,
                source_snapshot_id=source_snapshot_id,
                evidence=candidate.evidence,
            )
            if candidate_id is not None:
                result.match_candidates_created += 1
        return result

    def _collect_game_log(
        self,
        install_path: Path,
        session_id: int,
        result: CollectionResult,
    ) -> None:
        path = self._find_game_log(install_path)
        if path is None:
            return
        previous = self._db.get_latest_source_snapshot("game_log", path)
        capture = capture_file(path, text=True)
        if capture is None or capture.content_text is None:
            return
        snapshot_id, created = self._db.save_source_snapshot(
            source_type="game_log",
            path=path,
            captured_at=capture.captured_at,
            sha256=capture.sha256,
            mtime=capture.mtime,
            size=capture.size,
            content_text=capture.content_text,
            metadata=capture.metadata,
        )
        if not created:
            return
        result.snapshots_created += 1

        fallback_date = capture.mtime or datetime.now()
        events, candidates = parse_game_log(capture.content_text, fallback_date)
        for event in events:
            event_id = self._db.save_session_event(
                session_id=session_id,
                timestamp=event.timestamp,
                event_type=event.event_type,
                summary=event.summary,
                confidence=event.confidence,
                source_snapshot_id=snapshot_id,
                line_no=event.line_no,
                payload=event.payload,
            )
            if event_id is not None:
                result.session_events_created += 1
        for candidate in candidates:
            candidate_id = self._db.save_match_candidate(
                session_id=session_id,
                started_at=candidate.started_at,
                ended_at=candidate.ended_at,
                postmatch_at=candidate.postmatch_at,
                map_name=candidate.map_name,
                duration_seconds=candidate.duration_seconds,
                confidence=candidate.confidence,
                source_snapshot_id=snapshot_id,
                evidence=candidate.evidence,
            )
            if candidate_id is not None:
                result.match_candidates_created += 1

        if previous is None:
            self._db.save_session_event(
                session_id=session_id,
                timestamp=capture.captured_at,
                event_type="session_baseline",
                summary="Game.log baseline captured",
                confidence="observed",
                source_snapshot_id=snapshot_id,
                line_no=None,
                payload={"path": str(path)},
            )

    def _collect_steam_achievements(self, path: Path, result: CollectionResult) -> None:
        previous = self._db.get_latest_source_snapshot("steam_achievements", path)
        capture = capture_file(path, text=True)
        if capture is None or capture.content_text is None:
            return
        snapshot_id, created = self._db.save_source_snapshot(
            source_type="steam_achievements",
            path=path,
            captured_at=capture.captured_at,
            sha256=capture.sha256,
            mtime=capture.mtime,
            size=capture.size,
            content_text=capture.content_text,
            metadata=capture.metadata,
        )
        if not created:
            return
        result.snapshots_created += 1
        if previous is None or not previous.get("content_text"):
            return

        old_json = parse_json_text(previous["content_text"])
        new_json = parse_json_text(capture.content_text)
        if old_json is None or new_json is None:
            result.add_error(f"Could not parse Steam achievement JSON: {path}")
            return
        old_values = extract_achievement_values(old_json)
        new_values = extract_achievement_values(new_json)
        deltas = diff_achievement_values(old_values, new_values)
        result.achievement_deltas_created += self._db.save_achievement_deltas(
            from_snapshot_id=int(previous["id"]),
            to_snapshot_id=snapshot_id,
            deltas=deltas,
        )

    def _collect_attributes(self, path: Path, result: CollectionResult) -> None:
        previous = self._db.get_latest_source_snapshot("attributes", path)
        capture = capture_file(path, text=True)
        if capture is None or capture.content_text is None:
            return
        snapshot_id, created = self._db.save_source_snapshot(
            source_type="attributes",
            path=path,
            captured_at=capture.captured_at,
            sha256=capture.sha256,
            mtime=capture.mtime,
            size=capture.size,
            content_text=capture.content_text,
            metadata=capture.metadata,
        )
        if not created:
            return
        result.snapshots_created += 1
        if previous is None or not previous.get("content_text"):
            return

        try:
            old_attrs = extract_attributes(previous["content_text"])
            new_attrs = extract_attributes(capture.content_text)
        except Exception as exc:
            result.add_error(f"Could not parse attributes.xml: {exc}")
            return
        deltas = diff_account_attributes(old_attrs, new_attrs)
        result.account_deltas_created += self._db.save_account_deltas(
            from_snapshot_id=int(previous["id"]),
            to_snapshot_id=snapshot_id,
            deltas=deltas,
        )

    def _collect_binary_save(self, path: Path, result: CollectionResult) -> None:
        capture = capture_file(path, text=False)
        if capture is None:
            return
        _, created = self._db.save_source_snapshot(
            source_type="binary_save",
            path=path,
            captured_at=capture.captured_at,
            sha256=capture.sha256,
            mtime=capture.mtime,
            size=capture.size,
            content_blob=capture.content_blob,
            metadata=capture.metadata,
        )
        if created:
            result.snapshots_created += 1

    def _find_game_log(self, install_path: Path) -> Path | None:
        variants = [
            install_path / "USER" / "Game.log",
            install_path / "user" / "Game.log",
            install_path / "User" / "Game.log",
        ]
        for path in variants:
            if path.exists():
                return path
        return None

    def _steam_roots(self, install_path: Path) -> list[Path]:
        roots: list[Path] = []
        try:
            parts = install_path.resolve().parts
        except OSError:
            parts = install_path.parts
        lower_parts = [p.lower() for p in parts]
        if "steamapps" in lower_parts:
            idx = lower_parts.index("steamapps")
            if idx > 0:
                roots.append(Path(*parts[:idx]))

        for drive in _DRIVES:
            for subdir in _STEAM_SUBDIRS:
                roots.append(Path(f"{drive}:/{subdir}"))

        unique: list[Path] = []
        seen: set[str] = set()
        for root in roots:
            key = str(root).lower()
            if key not in seen and root.exists():
                seen.add(key)
                unique.append(root)
        return unique

    def _userdata_dirs(self, install_path: Path) -> list[Path]:
        dirs: list[Path] = []
        for root in self._steam_roots(install_path):
            userdata = root / "userdata"
            if not userdata.is_dir():
                continue
            try:
                children = list(userdata.iterdir())
            except OSError:
                continue
            for child in children:
                if child.is_dir() and child.name.isdigit():
                    dirs.append(child)
        return dirs

    def _find_steam_achievement_paths(self, install_path: Path) -> list[Path]:
        paths: list[Path] = []
        for user_dir in self._userdata_dirs(install_path):
            candidate = user_dir / "config" / "librarycache" / "594650.json"
            if candidate.exists():
                paths.append(candidate)
        return paths

    def _find_binary_save_paths(self, install_path: Path) -> list[Path]:
        paths: list[Path] = []
        for user_dir in self._userdata_dirs(install_path):
            save_dir = user_dir / "3764200" / "remote" / "win64_save"
            if not save_dir.is_dir():
                continue
            try:
                for candidate in save_dir.glob("data*.bin"):
                    if candidate.is_file():
                        paths.append(candidate)
            except OSError:
                continue
        return paths
