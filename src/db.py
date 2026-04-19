from __future__ import annotations

import json
import re
import shutil
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from .config import app_data_dir
from .parser import Match, Player, Team, Accolade, MissionEntry


SCHEMA = """
CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    xml_hash TEXT NOT NULL UNIQUE,
    is_hunter_dead INTEGER NOT NULL DEFAULT 0,
    is_quickplay INTEGER NOT NULL DEFAULT 0,
    is_tutorial INTEGER NOT NULL DEFAULT 0,
    own_team_mmr INTEGER,
    num_teams INTEGER,
    total_kills INTEGER,
    total_deaths INTEGER,
    total_bounty INTEGER,
    total_hunter_xp INTEGER,
    total_gold INTEGER,
    fbe_gold_bonus INTEGER,
    fbe_hunter_xp_bonus INTEGER,
    raw_xml TEXT,
    raw_attrs_json TEXT
);

CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    team_idx INTEGER NOT NULL,
    mmr INTEGER,
    num_players INTEGER,
    is_own_team INTEGER,
    handicap INTEGER,
    prestige INTEGER,
    is_invite INTEGER,
    fields_json TEXT
);

CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    team_idx INTEGER NOT NULL,
    player_idx INTEGER NOT NULL,
    name TEXT,
    profile_id TEXT,
    mmr INTEGER,
    killed_by_me INTEGER,
    killed_me INTEGER,
    downed_by_me INTEGER,
    downed_me INTEGER,
    killed_by_teammate INTEGER,
    downed_by_teammate INTEGER,
    is_partner INTEGER,
    had_bounty INTEGER,
    bounty_picked_up INTEGER,
    team_extraction INTEGER,
    is_soul_survivor INTEGER,
    proximity_to_me INTEGER,
    fields_json TEXT
);

CREATE TABLE IF NOT EXISTS accolades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    category TEXT,
    title TEXT,
    header TEXT,
    bounty INTEGER,
    gold INTEGER,
    xp INTEGER,
    hunter_xp INTEGER,
    hits INTEGER,
    weighting INTEGER,
    generated_gems INTEGER,
    fields_json TEXT
);

CREATE TABLE IF NOT EXISTS mission_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    category TEXT,
    amount INTEGER,
    reward INTEGER,
    reward_size INTEGER,
    reward_type INTEGER,
    descriptor_name TEXT,
    descriptor_score INTEGER,
    descriptor_type TEXT,
    ui_name TEXT,
    ui_name_2 TEXT,
    fields_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_players_profile ON players(profile_id);
CREATE INDEX IF NOT EXISTS idx_matches_ts ON matches(timestamp);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    evidence_json TEXT
);

CREATE TABLE IF NOT EXISTS source_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at TEXT NOT NULL,
    source_type TEXT NOT NULL,
    path TEXT NOT NULL,
    mtime TEXT,
    size INTEGER,
    sha256 TEXT NOT NULL,
    content_text TEXT,
    content_blob BLOB,
    metadata_json TEXT,
    UNIQUE(source_type, path, sha256)
);

CREATE TABLE IF NOT EXISTS session_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    summary TEXT NOT NULL,
    confidence TEXT NOT NULL,
    source_snapshot_id INTEGER REFERENCES source_snapshots(id) ON DELETE SET NULL,
    line_no INTEGER,
    payload_json TEXT,
    UNIQUE(source_snapshot_id, line_no, event_type)
);

CREATE TABLE IF NOT EXISTS match_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
    started_at TEXT,
    ended_at TEXT NOT NULL,
    postmatch_at TEXT,
    map_name TEXT,
    duration_seconds INTEGER,
    confidence TEXT NOT NULL,
    source_snapshot_id INTEGER REFERENCES source_snapshots(id) ON DELETE SET NULL,
    evidence_json TEXT,
    UNIQUE(session_id, ended_at)
);

CREATE TABLE IF NOT EXISTS achievement_deltas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_snapshot_id INTEGER REFERENCES source_snapshots(id) ON DELETE SET NULL,
    to_snapshot_id INTEGER NOT NULL REFERENCES source_snapshots(id) ON DELETE CASCADE,
    achievement_key TEXT NOT NULL,
    field_path TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    delta_num REAL,
    change_type TEXT NOT NULL,
    confidence TEXT NOT NULL,
    payload_json TEXT,
    UNIQUE(from_snapshot_id, to_snapshot_id, achievement_key, field_path)
);

CREATE TABLE IF NOT EXISTS account_deltas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_snapshot_id INTEGER REFERENCES source_snapshots(id) ON DELETE SET NULL,
    to_snapshot_id INTEGER NOT NULL REFERENCES source_snapshots(id) ON DELETE CASCADE,
    attr_key TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    change_type TEXT NOT NULL,
    category TEXT NOT NULL,
    confidence TEXT NOT NULL,
    payload_json TEXT,
    UNIQUE(from_snapshot_id, to_snapshot_id, attr_key)
);

CREATE INDEX IF NOT EXISTS idx_source_snapshots_type_path ON source_snapshots(source_type, path, captured_at);
CREATE INDEX IF NOT EXISTS idx_session_events_ts ON session_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_achievement_deltas_to ON achievement_deltas(to_snapshot_id);
CREATE INDEX IF NOT EXISTS idx_account_deltas_to ON account_deltas(to_snapshot_id);

CREATE TABLE IF NOT EXISTS screenshot_captures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at TEXT NOT NULL,
    trigger_event TEXT NOT NULL,
    image_path TEXT NOT NULL,
    sha256 TEXT NOT NULL UNIQUE,
    width INTEGER,
    height INTEGER,
    monitor_json TEXT,
    status TEXT NOT NULL DEFAULT 'captured',
    ocr_text TEXT,
    ocr_json TEXT,
    metadata_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_screenshot_captures_ts ON screenshot_captures(captured_at);

CREATE TABLE IF NOT EXISTS vision_fields (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    screenshot_capture_id INTEGER NOT NULL REFERENCES screenshot_captures(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    field_name TEXT NOT NULL,
    value_text TEXT,
    value_num REAL,
    confidence TEXT NOT NULL,
    region_name TEXT NOT NULL,
    method TEXT NOT NULL,
    crop_path TEXT,
    metadata_json TEXT,
    UNIQUE(screenshot_capture_id, field_name, region_name, method)
);

CREATE INDEX IF NOT EXISTS idx_vision_fields_capture ON vision_fields(screenshot_capture_id);
"""


@dataclass
class MatchSummary:
    id: int
    timestamp: datetime
    is_hunter_dead: bool
    is_quickplay: bool
    own_team_mmr: int
    total_kills: int
    total_deaths: int
    total_bounty: int
    total_hunter_xp: int
    total_gold: int


@dataclass
class DisplayMatchSummary:
    id: str
    source: str
    timestamp: datetime
    title: str
    subtitle: str
    is_hunter_dead: bool
    total_kills: int
    total_deaths: int
    total_bounty: int
    total_hunter_xp: int
    total_gold: int = 0
    own_team_mmr: int = 0
    frame_count: int = 0
    parsed_fields: dict[str, str] | None = None


@dataclass
class SessionSummary:
    id: int
    started_at: datetime
    ended_at: datetime | None
    status: str
    event_count: int
    match_candidate_count: int


@dataclass
class HuntSessionSummary:
    id: int
    started_at: datetime | None
    ended_at: datetime
    postmatch_at: datetime | None
    map_name: str
    duration_seconds: int | None
    confidence: str


@dataclass
class EvidenceEvent:
    id: int
    timestamp: datetime
    event_type: str
    summary: str
    confidence: str
    source_type: str
    line_no: int | None


@dataclass
class EvidenceDelta:
    id: int
    captured_at: datetime
    key: str
    field_path: str
    old_value: str
    new_value: str
    delta_num: float | None
    change_type: str
    confidence: str
    source_type: str
    from_captured_at: datetime | None = None


@dataclass
class SourceSnapshotSummary:
    id: int
    captured_at: datetime
    source_type: str
    path: str
    mtime: datetime | None
    size: int | None
    sha256: str


@dataclass
class ScreenshotCapture:
    id: int
    captured_at: datetime
    trigger_event: str
    image_path: str
    sha256: str
    width: int | None
    height: int | None
    status: str
    ocr_text: str = ""


@dataclass
class VisionField:
    id: int
    screenshot_capture_id: int
    captured_at: datetime
    field_name: str
    value_text: str
    value_num: float | None
    confidence: str
    region_name: str
    method: str
    crop_path: str


def db_path() -> Path:
    return app_data_dir() / "hunt_logger.db"


class Database:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else db_path()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        self._lock = threading.RLock()
        self._purge_empty_matches()

    def close(self) -> None:
        self._conn.close()

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def match_exists(self, xml_hash: str) -> bool:
        with self._lock:
            return self._match_exists_unlocked(xml_hash)

    def _match_exists_unlocked(self, xml_hash: str) -> bool:
        cur = self._conn.execute("SELECT 1 FROM matches WHERE xml_hash = ?", (xml_hash,))
        return cur.fetchone() is not None

    def save_match(self, match: Match) -> int | None:
        with self._lock:
            if self._match_exists_unlocked(match.xml_hash):
                return None
        own_team = match.own_team
        with self._tx() as conn:
            cur = conn.execute(
                """
                INSERT INTO matches (
                    timestamp, xml_hash, is_hunter_dead, is_quickplay, is_tutorial,
                    own_team_mmr, num_teams, total_kills, total_deaths,
                    total_bounty, total_hunter_xp, total_gold,
                    fbe_gold_bonus, fbe_hunter_xp_bonus, raw_xml, raw_attrs_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    match.timestamp.isoformat(),
                    match.xml_hash,
                    int(match.is_hunter_dead),
                    int(match.is_quickplay),
                    int(match.is_tutorial),
                    own_team.mmr if own_team else None,
                    match.num_teams,
                    match.total_kills_by_me,
                    match.total_deaths_to_others,
                    match.total_bounty,
                    match.total_hunter_xp,
                    match.total_gold,
                    match.fbe_gold_bonus,
                    match.fbe_hunter_xp_bonus,
                    match.raw_xml,
                    json.dumps(match.raw_attributes),
                ),
            )
            match_id = cur.lastrowid
            self._insert_teams(conn, match_id, match.teams)
            self._insert_players(conn, match_id, match.players)
            self._insert_accolades(conn, match_id, match.accolades)
            self._insert_entries(conn, match_id, match.entries)
            return match_id

    def _insert_teams(self, conn: sqlite3.Connection, match_id: int, teams: list[Team]) -> None:
        conn.executemany(
            """
            INSERT INTO teams (
                match_id, team_idx, mmr, num_players, is_own_team,
                handicap, prestige, is_invite, fields_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    match_id,
                    t.idx,
                    t.mmr,
                    t.num_players,
                    int(t.is_own_team),
                    t.handicap,
                    t.prestige,
                    int(t.is_invite),
                    json.dumps(t.fields),
                )
                for t in teams
            ],
        )

    def _insert_players(self, conn: sqlite3.Connection, match_id: int, players: list[Player]) -> None:
        conn.executemany(
            """
            INSERT INTO players (
                match_id, team_idx, player_idx, name, profile_id, mmr,
                killed_by_me, killed_me, downed_by_me, downed_me,
                killed_by_teammate, downed_by_teammate,
                is_partner, had_bounty, bounty_picked_up,
                team_extraction, is_soul_survivor, proximity_to_me,
                fields_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    match_id,
                    p.team_idx,
                    p.player_idx,
                    p.name,
                    p.profile_id,
                    p.mmr,
                    p.killed_by_me,
                    p.killed_me,
                    p.downed_by_me,
                    p.downed_me,
                    p.killed_by_teammate,
                    p.downed_by_teammate,
                    int(p.is_partner),
                    int(p.had_bounty),
                    p.bounty_picked_up,
                    int(p.team_extraction),
                    int(p.is_soul_survivor),
                    int(p.proximity_to_me),
                    json.dumps(p.fields),
                )
                for p in players
            ],
        )

    def _insert_accolades(self, conn: sqlite3.Connection, match_id: int, accolades: list[Accolade]) -> None:
        conn.executemany(
            """
            INSERT INTO accolades (
                match_id, idx, category, title, header,
                bounty, gold, xp, hunter_xp, hits,
                weighting, generated_gems, fields_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    match_id,
                    a.idx,
                    a.category,
                    a.title,
                    a.header,
                    a.bounty,
                    a.gold,
                    a.xp,
                    a.hunter_xp,
                    a.hits,
                    a.weighting,
                    a.generated_gems,
                    json.dumps(a.fields),
                )
                for a in accolades
            ],
        )

    def _insert_entries(self, conn: sqlite3.Connection, match_id: int, entries: list[MissionEntry]) -> None:
        conn.executemany(
            """
            INSERT INTO mission_entries (
                match_id, idx, category, amount, reward,
                reward_size, reward_type, descriptor_name, descriptor_score,
                descriptor_type, ui_name, ui_name_2, fields_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    match_id,
                    e.idx,
                    e.category,
                    e.amount,
                    e.reward,
                    e.reward_size,
                    e.reward_type,
                    e.descriptor_name,
                    e.descriptor_score,
                    e.descriptor_type,
                    e.ui_name,
                    e.ui_name_2,
                    json.dumps(e.fields),
                )
                for e in entries
            ],
        )

    def _purge_empty_matches(self) -> None:
        """Remove any matches saved before the has_match_data guard was added."""
        with self._lock:
            self._conn.execute(
                """
                DELETE FROM matches
                WHERE (num_teams IS NULL OR num_teams = 0)
                  AND (raw_attrs_json IS NULL
                       OR raw_attrs_json NOT LIKE '%MissionBag%')
                """
            )
            self._conn.commit()

    def delete_match(self, match_id: int) -> None:
        with self._tx() as conn:
            conn.execute("DELETE FROM matches WHERE id = ?", (match_id,))

    def delete_visual_match(self, group_path: str) -> int:
        group = Path(group_path)
        captures_root = app_data_dir() / "captures"

        with self._lock:
            cur = self._conn.execute(
                "SELECT id, image_path FROM screenshot_captures ORDER BY id"
            )
            rows = cur.fetchall()

        capture_ids: list[int] = []
        image_paths: list[Path] = []
        for row in rows:
            image_path = Path(row["image_path"])
            if image_path.parent != group:
                continue
            capture_ids.append(int(row["id"]))
            image_paths.append(image_path)

        if not capture_ids:
            return 0

        placeholders = ", ".join("?" for _ in capture_ids)
        with self._tx() as conn:
            conn.execute(
                f"DELETE FROM screenshot_captures WHERE id IN ({placeholders})",
                tuple(capture_ids),
            )

        self._delete_visual_group_files(group, image_paths, captures_root)
        return len(capture_ids)

    def list_matches(self, limit: int = 500) -> list[MatchSummary]:
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT id, timestamp, is_hunter_dead, is_quickplay, own_team_mmr,
                       total_kills, total_deaths, total_bounty, total_hunter_xp,
                       total_gold
                FROM matches
                ORDER BY datetime(timestamp) DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cur.fetchall()
        return [
            MatchSummary(
                id=row["id"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                is_hunter_dead=bool(row["is_hunter_dead"]),
                is_quickplay=bool(row["is_quickplay"]),
                own_team_mmr=row["own_team_mmr"] or 0,
                total_kills=row["total_kills"] or 0,
                total_deaths=row["total_deaths"] or 0,
                total_bounty=row["total_bounty"] or 0,
                total_hunter_xp=row["total_hunter_xp"] or 0,
                total_gold=row["total_gold"] or 0,
            )
            for row in rows
        ]

    def list_display_matches(self, limit: int = 1000) -> list[DisplayMatchSummary]:
        items: list[DisplayMatchSummary] = []
        for match in self.list_matches(limit=limit):
            items.append(
                DisplayMatchSummary(
                    id=f"exact:{match.id}",
                    source="exact",
                    timestamp=match.timestamp,
                    title=f"Exact match #{match.id}",
                    subtitle=(
                        f"K {match.total_kills} D {match.total_deaths} "
                        f"Bounty {match.total_bounty} XP {match.total_hunter_xp}"
                    ),
                    is_hunter_dead=match.is_hunter_dead,
                    total_kills=match.total_kills,
                    total_deaths=match.total_deaths,
                    total_bounty=match.total_bounty,
                    total_hunter_xp=match.total_hunter_xp,
                    total_gold=match.total_gold,
                    own_team_mmr=match.own_team_mmr,
                )
            )

        groups: dict[str, dict[str, Any]] = {}
        for capture in self.list_recent_screenshot_captures(limit=limit * 100):
            group_path = str(Path(capture.image_path).parent)
            group = groups.setdefault(
                group_path,
                {
                    "started_at": capture.captured_at,
                    "ended_at": capture.captured_at,
                    "frame_count": 0,
                },
            )
            group["started_at"] = min(group["started_at"], capture.captured_at)
            group["ended_at"] = max(group["ended_at"], capture.captured_at)
            group["frame_count"] += 1

        for group_path, group in groups.items():
            ts = group["ended_at"]
            frame_count = int(group["frame_count"] or 0)
            detail = self.get_visual_match_detail(group_path)
            parsed = detail["parsed_fields"] if detail else {}
            kills = _field_int(parsed, "hunters_killed_value")
            bounty = _field_int(parsed, "bounty_obtained_value")
            hunter_xp = _field_int(parsed, "bloodline_xp")
            status = parsed.get("hunter_status", "")
            subtitle_parts = [f"{frame_count} frames"]
            if parsed:
                subtitle_parts.extend(
                    [
                        f"K {kills}" if kills is not None else "",
                        f"Monsters {_field_text(parsed, 'monsters_killed_value')}",
                        f"Bounty {_field_text(parsed, 'bounty_obtained_value')}",
                        f"XP {_field_text(parsed, 'bloodline_xp')}",
                    ]
                )
            else:
                subtitle_parts.append("parser pending")
            items.append(
                DisplayMatchSummary(
                    id=f"visual:{group_path}",
                    source="visual",
                    timestamp=ts,
                    title="Screenshot match",
                    subtitle=f"{frame_count} captured frames · screenshot-derived",
                    is_hunter_dead=status == "dead",
                    total_kills=kills or 0,
                    total_deaths=0,
                    total_bounty=bounty or 0,
                    total_hunter_xp=hunter_xp or 0,
                    frame_count=frame_count,
                    parsed_fields=parsed,
                )
            )

        items.sort(key=lambda x: x.timestamp, reverse=True)
        return items[:limit]

    def get_match_raw(self, match_id: int) -> dict | None:
        with self._lock:
            cur = self._conn.execute(
                "SELECT raw_xml, raw_attrs_json, timestamp FROM matches WHERE id = ?",
                (match_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return {
            "raw_xml": row["raw_xml"],
            "raw_attrs": json.loads(row["raw_attrs_json"] or "{}"),
            "timestamp": datetime.fromisoformat(row["timestamp"]),
        }

    def get_match_teams(self, match_id: int) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM teams WHERE match_id = ? ORDER BY team_idx",
                (match_id,),
            )
            return [dict(row) for row in cur.fetchall()]

    def get_match_players(self, match_id: int) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM players WHERE match_id = ? ORDER BY team_idx, player_idx",
                (match_id,),
            )
            return [dict(row) for row in cur.fetchall()]

    def get_match_accolades(self, match_id: int) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM accolades WHERE match_id = ? ORDER BY idx",
                (match_id,),
            )
            return [dict(row) for row in cur.fetchall()]

    def get_match_entries(self, match_id: int) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM mission_entries WHERE match_id = ? ORDER BY idx",
                (match_id,),
            )
            return [dict(row) for row in cur.fetchall()]

    def get_match_header(self, match_id: int) -> dict | None:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM matches WHERE id = ?", (match_id,))
            row = cur.fetchone()
        return dict(row) if row else None

    def aggregate_stats(self) -> dict:
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT COUNT(*) AS matches,
                       SUM(total_kills) AS kills,
                       SUM(total_deaths) AS deaths,
                       SUM(total_bounty) AS bounty,
                       SUM(total_hunter_xp) AS hunter_xp,
                       SUM(CASE WHEN is_hunter_dead = 0 THEN 1 ELSE 0 END) AS survived
                FROM matches
                """
            )
            row = cur.fetchone()
        return dict(row) if row else {}

    def get_latest_source_snapshot(self, source_type: str, path: Path | str) -> dict | None:
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT *
                FROM source_snapshots
                WHERE source_type = ? AND path = ?
                ORDER BY datetime(captured_at) DESC, id DESC
                LIMIT 1
                """,
                (source_type, str(path)),
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def get_latest_source_snapshot_by_type(self, source_type: str) -> dict | None:
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT *
                FROM source_snapshots
                WHERE source_type = ?
                ORDER BY datetime(captured_at) DESC, id DESC
                LIMIT 1
                """,
                (source_type,),
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def get_latest_source_snapshot_in_range(
        self,
        source_type: str,
        *,
        started_at: datetime,
        ended_at: datetime | None = None,
    ) -> dict | None:
        params: list[Any] = [source_type, started_at.isoformat()]
        query = [
            "SELECT *",
            "FROM source_snapshots",
            "WHERE source_type = ?",
            "  AND captured_at >= ?",
        ]
        if ended_at is not None:
            query.append("  AND captured_at <= ?")
            params.append(ended_at.isoformat())
        query.extend(
            [
                "ORDER BY datetime(captured_at) DESC, id DESC",
                "LIMIT 1",
            ]
        )
        with self._lock:
            cur = self._conn.execute("\n".join(query), tuple(params))
            row = cur.fetchone()
        return dict(row) if row else None

    def get_source_snapshot(self, snapshot_id: int) -> dict | None:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM source_snapshots WHERE id = ?",
                (snapshot_id,),
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def save_source_snapshot(
        self,
        *,
        source_type: str,
        path: Path | str,
        captured_at: datetime,
        sha256: str,
        mtime: datetime | None,
        size: int | None,
        content_text: str | None = None,
        content_blob: bytes | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[int, bool]:
        path_text = str(path)
        with self._tx() as conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO source_snapshots (
                    captured_at, source_type, path, mtime, size, sha256,
                    content_text, content_blob, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    captured_at.isoformat(),
                    source_type,
                    path_text,
                    mtime.isoformat() if mtime else None,
                    size,
                    sha256,
                    content_text,
                    content_blob,
                    json.dumps(metadata or {}),
                ),
            )
            created = cur.rowcount > 0
            if created:
                return int(cur.lastrowid), True
            cur = conn.execute(
                """
                SELECT id
                FROM source_snapshots
                WHERE source_type = ? AND path = ? AND sha256 = ?
                """,
                (source_type, path_text, sha256),
            )
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("source snapshot insert/select failed")
            return int(row["id"]), False

    def get_or_create_active_session(self, started_at: datetime | None = None) -> int:
        with self._tx() as conn:
            cur = conn.execute(
                """
                SELECT id
                FROM sessions
                WHERE status = 'active'
                ORDER BY datetime(started_at) DESC, id DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()
            if row:
                return int(row["id"])
            cur = conn.execute(
                "INSERT INTO sessions (started_at, status, evidence_json) VALUES (?, 'active', ?)",
                ((started_at or datetime.now()).isoformat(), json.dumps({})),
            )
            return int(cur.lastrowid)

    def close_active_session(self, ended_at: datetime | None = None) -> None:
        with self._tx() as conn:
            conn.execute(
                """
                UPDATE sessions
                SET ended_at = ?, status = 'closed'
                WHERE status = 'active'
                """,
                ((ended_at or datetime.now()).isoformat(),),
            )

    def save_session_event(
        self,
        *,
        session_id: int | None,
        timestamp: datetime,
        event_type: str,
        summary: str,
        confidence: str,
        source_snapshot_id: int | None,
        line_no: int | None,
        payload: dict[str, Any] | None = None,
    ) -> int | None:
        with self._tx() as conn:
            cur = conn.execute(
                """
                SELECT id
                FROM session_events
                WHERE (session_id IS ? OR session_id = ?)
                  AND timestamp = ?
                  AND event_type = ?
                  AND summary = ?
                LIMIT 1
                """,
                (session_id, session_id, timestamp.isoformat(), event_type, summary),
            )
            if cur.fetchone() is not None:
                return None
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO session_events (
                    session_id, timestamp, event_type, summary, confidence,
                    source_snapshot_id, line_no, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    timestamp.isoformat(),
                    event_type,
                    summary,
                    confidence,
                    source_snapshot_id,
                    line_no,
                    json.dumps(payload or {}),
                ),
            )
            if cur.rowcount == 0:
                return None
            return int(cur.lastrowid)

    def save_match_candidate(
        self,
        *,
        session_id: int | None,
        started_at: datetime | None,
        ended_at: datetime,
        postmatch_at: datetime | None,
        map_name: str | None,
        duration_seconds: int | None,
        confidence: str,
        source_snapshot_id: int | None,
        evidence: dict[str, Any] | None = None,
    ) -> int | None:
        with self._tx() as conn:
            cur = conn.execute(
                """
                SELECT id
                FROM match_candidates
                WHERE (session_id IS ? OR session_id = ?)
                  AND ended_at = ?
                LIMIT 1
                """,
                (session_id, session_id, ended_at.isoformat()),
            )
            if cur.fetchone() is not None:
                return None
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO match_candidates (
                    session_id, started_at, ended_at, postmatch_at, map_name,
                    duration_seconds, confidence, source_snapshot_id, evidence_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    started_at.isoformat() if started_at else None,
                    ended_at.isoformat(),
                    postmatch_at.isoformat() if postmatch_at else None,
                    map_name,
                    duration_seconds,
                    confidence,
                    source_snapshot_id,
                    json.dumps(evidence or {}),
                ),
            )
            if cur.rowcount == 0:
                return None
            return int(cur.lastrowid)

    def save_achievement_deltas(
        self,
        *,
        from_snapshot_id: int,
        to_snapshot_id: int,
        deltas: list[dict[str, Any]],
    ) -> int:
        if not deltas:
            return 0
        with self._tx() as conn:
            before = conn.total_changes
            conn.executemany(
                """
                INSERT OR IGNORE INTO achievement_deltas (
                    from_snapshot_id, to_snapshot_id, achievement_key, field_path,
                    old_value, new_value, delta_num, change_type, confidence, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        from_snapshot_id,
                        to_snapshot_id,
                        d["achievement_key"],
                        d["field_path"],
                        d.get("old_value"),
                        d.get("new_value"),
                        d.get("delta_num"),
                        d["change_type"],
                        d["confidence"],
                        json.dumps(d.get("payload", {})),
                    )
                    for d in deltas
                ],
            )
            return conn.total_changes - before

    def save_account_deltas(
        self,
        *,
        from_snapshot_id: int,
        to_snapshot_id: int,
        deltas: list[dict[str, Any]],
    ) -> int:
        if not deltas:
            return 0
        with self._tx() as conn:
            before = conn.total_changes
            conn.executemany(
                """
                INSERT OR IGNORE INTO account_deltas (
                    from_snapshot_id, to_snapshot_id, attr_key, old_value, new_value,
                    change_type, category, confidence, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        from_snapshot_id,
                        to_snapshot_id,
                        d["attr_key"],
                        d.get("old_value"),
                        d.get("new_value"),
                        d["change_type"],
                        d["category"],
                        d["confidence"],
                        json.dumps(d.get("payload", {})),
                    )
                    for d in deltas
                ],
            )
            return conn.total_changes - before

    def list_sessions(self, limit: int = 100) -> list[SessionSummary]:
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT s.id, s.started_at, s.ended_at, s.status,
                       COUNT(DISTINCT e.id) AS event_count,
                       COUNT(DISTINCT m.id) AS match_candidate_count
                FROM sessions s
                LEFT JOIN session_events e ON e.session_id = s.id
                LEFT JOIN match_candidates m ON m.session_id = s.id
                GROUP BY s.id
                ORDER BY datetime(s.started_at) DESC, s.id DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cur.fetchall()
        return [
            SessionSummary(
                id=int(row["id"]),
                started_at=datetime.fromisoformat(row["started_at"]),
                ended_at=datetime.fromisoformat(row["ended_at"]) if row["ended_at"] else None,
                status=row["status"],
                event_count=int(row["event_count"] or 0),
                match_candidate_count=int(row["match_candidate_count"] or 0),
            )
            for row in rows
        ]

    def list_hunt_sessions(self, limit: int = 100) -> list[HuntSessionSummary]:
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT id, started_at, ended_at, postmatch_at, map_name,
                       duration_seconds, confidence
                FROM match_candidates
                ORDER BY datetime(ended_at) DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cur.fetchall()
        return [
            HuntSessionSummary(
                id=int(row["id"]),
                started_at=(
                    datetime.fromisoformat(row["started_at"])
                    if row["started_at"] else None
                ),
                ended_at=datetime.fromisoformat(row["ended_at"]),
                postmatch_at=(
                    datetime.fromisoformat(row["postmatch_at"])
                    if row["postmatch_at"] else None
                ),
                map_name=row["map_name"] or "",
                duration_seconds=row["duration_seconds"],
                confidence=row["confidence"] or "unknown",
            )
            for row in rows
        ]

    def list_recent_session_events(self, limit: int = 200) -> list[EvidenceEvent]:
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT e.id, e.timestamp, e.event_type, e.summary, e.confidence,
                       ss.source_type, e.line_no
                FROM session_events e
                LEFT JOIN source_snapshots ss ON ss.id = e.source_snapshot_id
                ORDER BY datetime(e.timestamp) DESC, e.id DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cur.fetchall()
        return [
            EvidenceEvent(
                id=int(row["id"]),
                timestamp=datetime.fromisoformat(row["timestamp"]),
                event_type=row["event_type"],
                summary=row["summary"],
                confidence=row["confidence"],
                source_type=row["source_type"] or "",
                line_no=row["line_no"],
            )
            for row in rows
        ]

    def list_recent_achievement_deltas(self, limit: int = 200) -> list[EvidenceDelta]:
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT d.id, ss.captured_at, prev.captured_at AS from_captured_at,
                       d.achievement_key AS key_name,
                       d.field_path, d.old_value, d.new_value, d.delta_num,
                       d.change_type, d.confidence, ss.source_type
                FROM achievement_deltas d
                JOIN source_snapshots ss ON ss.id = d.to_snapshot_id
                LEFT JOIN source_snapshots prev ON prev.id = d.from_snapshot_id
                ORDER BY datetime(ss.captured_at) DESC, d.id DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cur.fetchall()
        return [
            EvidenceDelta(
                id=int(row["id"]),
                captured_at=datetime.fromisoformat(row["captured_at"]),
                key=row["key_name"],
                field_path=row["field_path"],
                old_value=row["old_value"] or "",
                new_value=row["new_value"] or "",
                delta_num=row["delta_num"],
                change_type=row["change_type"],
                confidence=row["confidence"],
                source_type=row["source_type"] or "steam_achievements",
                from_captured_at=(
                    datetime.fromisoformat(row["from_captured_at"])
                    if row["from_captured_at"] else None
                ),
            )
            for row in rows
        ]

    def list_recent_account_deltas(self, limit: int = 200) -> list[EvidenceDelta]:
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT d.id, ss.captured_at, prev.captured_at AS from_captured_at,
                       d.attr_key AS key_name,
                       d.category AS field_path, d.old_value, d.new_value,
                       NULL AS delta_num, d.change_type, d.confidence, ss.source_type
                FROM account_deltas d
                JOIN source_snapshots ss ON ss.id = d.to_snapshot_id
                LEFT JOIN source_snapshots prev ON prev.id = d.from_snapshot_id
                ORDER BY datetime(ss.captured_at) DESC, d.id DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cur.fetchall()
        return [
            EvidenceDelta(
                id=int(row["id"]),
                captured_at=datetime.fromisoformat(row["captured_at"]),
                key=row["key_name"],
                field_path=row["field_path"],
                old_value=row["old_value"] or "",
                new_value=row["new_value"] or "",
                delta_num=None,
                change_type=row["change_type"],
                confidence=row["confidence"],
                source_type=row["source_type"] or "attributes",
                from_captured_at=(
                    datetime.fromisoformat(row["from_captured_at"])
                    if row["from_captured_at"] else None
                ),
            )
            for row in rows
        ]

    def get_latest_match_candidate(self) -> dict | None:
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT *
                FROM match_candidates
                ORDER BY datetime(ended_at) DESC, id DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def list_session_events_for_session(self, session_id: int, limit: int = 100) -> list[EvidenceEvent]:
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT e.id, e.timestamp, e.event_type, e.summary, e.confidence,
                       ss.source_type, e.line_no
                FROM session_events e
                LEFT JOIN source_snapshots ss ON ss.id = e.source_snapshot_id
                WHERE e.session_id = ?
                ORDER BY datetime(e.timestamp) DESC, e.id DESC
                LIMIT ?
                """,
                (session_id, limit),
            )
            rows = cur.fetchall()
        return [
            EvidenceEvent(
                id=int(row["id"]),
                timestamp=datetime.fromisoformat(row["timestamp"]),
                event_type=row["event_type"],
                summary=row["summary"],
                confidence=row["confidence"],
                source_type=row["source_type"] or "",
                line_no=row["line_no"],
            )
            for row in rows
        ]

    def list_achievement_deltas_since(self, since: datetime, limit: int = 100) -> list[EvidenceDelta]:
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT d.id, ss.captured_at, prev.captured_at AS from_captured_at,
                       d.achievement_key AS key_name,
                       d.field_path, d.old_value, d.new_value, d.delta_num,
                       d.change_type, d.confidence, ss.source_type
                FROM achievement_deltas d
                JOIN source_snapshots ss ON ss.id = d.to_snapshot_id
                LEFT JOIN source_snapshots prev ON prev.id = d.from_snapshot_id
                WHERE ss.captured_at >= ?
                ORDER BY datetime(ss.captured_at) DESC, d.id DESC
                LIMIT ?
                """,
                (since.isoformat(), limit),
            )
            rows = cur.fetchall()
        return [
            EvidenceDelta(
                id=int(row["id"]),
                captured_at=datetime.fromisoformat(row["captured_at"]),
                key=row["key_name"],
                field_path=row["field_path"],
                old_value=row["old_value"] or "",
                new_value=row["new_value"] or "",
                delta_num=row["delta_num"],
                change_type=row["change_type"],
                confidence=row["confidence"],
                source_type=row["source_type"] or "steam_achievements",
                from_captured_at=(
                    datetime.fromisoformat(row["from_captured_at"])
                    if row["from_captured_at"] else None
                ),
            )
            for row in rows
        ]

    def list_account_deltas_since(self, since: datetime, limit: int = 100) -> list[EvidenceDelta]:
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT d.id, ss.captured_at, prev.captured_at AS from_captured_at,
                       d.attr_key AS key_name,
                       d.category AS field_path, d.old_value, d.new_value,
                       NULL AS delta_num, d.change_type, d.confidence, ss.source_type
                FROM account_deltas d
                JOIN source_snapshots ss ON ss.id = d.to_snapshot_id
                LEFT JOIN source_snapshots prev ON prev.id = d.from_snapshot_id
                WHERE ss.captured_at >= ?
                ORDER BY datetime(ss.captured_at) DESC, d.id DESC
                LIMIT ?
                """,
                (since.isoformat(), limit),
            )
            rows = cur.fetchall()
        return [
            EvidenceDelta(
                id=int(row["id"]),
                captured_at=datetime.fromisoformat(row["captured_at"]),
                key=row["key_name"],
                field_path=row["field_path"],
                old_value=row["old_value"] or "",
                new_value=row["new_value"] or "",
                delta_num=None,
                change_type=row["change_type"],
                confidence=row["confidence"],
                source_type=row["source_type"] or "attributes",
                from_captured_at=(
                    datetime.fromisoformat(row["from_captured_at"])
                    if row["from_captured_at"] else None
                ),
            )
            for row in rows
        ]

    def count_match_candidates_between(
        self,
        *,
        session_id: int | None,
        start: datetime,
        end: datetime,
    ) -> int:
        with self._lock:
            if session_id is None:
                cur = self._conn.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM match_candidates
                    WHERE ended_at >= ? AND ended_at <= ?
                    """,
                    (start.isoformat(), end.isoformat()),
                )
            else:
                cur = self._conn.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM match_candidates
                    WHERE session_id = ? AND ended_at >= ? AND ended_at <= ?
                    """,
                    (session_id, start.isoformat(), end.isoformat()),
                )
            row = cur.fetchone()
        return int(row["count"] if row else 0)

    def list_latest_source_snapshots(self, limit: int = 20) -> list[SourceSnapshotSummary]:
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT id, captured_at, source_type, path, mtime, size, sha256
                FROM source_snapshots
                ORDER BY datetime(captured_at) DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cur.fetchall()
        return [
            SourceSnapshotSummary(
                id=int(row["id"]),
                captured_at=datetime.fromisoformat(row["captured_at"]),
                source_type=row["source_type"],
                path=row["path"],
                mtime=datetime.fromisoformat(row["mtime"]) if row["mtime"] else None,
                size=row["size"],
                sha256=row["sha256"],
            )
            for row in rows
        ]

    def save_screenshot_capture(
        self,
        *,
        captured_at: datetime,
        trigger_event: str,
        image_path: Path | str,
        sha256: str,
        width: int | None,
        height: int | None,
        monitor: dict[str, Any] | None = None,
        status: str = "captured",
        metadata: dict[str, Any] | None = None,
    ) -> int | None:
        with self._tx() as conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO screenshot_captures (
                    captured_at, trigger_event, image_path, sha256, width, height,
                    monitor_json, status, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    captured_at.isoformat(),
                    trigger_event,
                    str(image_path),
                    sha256,
                    width,
                    height,
                    json.dumps(monitor or {}),
                    status,
                    json.dumps(metadata or {}),
                ),
            )
            if cur.rowcount == 0:
                return None
            return int(cur.lastrowid)

    def list_recent_screenshot_captures(self, limit: int = 100) -> list[ScreenshotCapture]:
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT id, captured_at, trigger_event, image_path, sha256,
                       width, height, status, ocr_text
                FROM screenshot_captures
                ORDER BY datetime(captured_at) DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cur.fetchall()
        return [
            ScreenshotCapture(
                id=int(row["id"]),
                captured_at=datetime.fromisoformat(row["captured_at"]),
                trigger_event=row["trigger_event"],
                image_path=row["image_path"],
                sha256=row["sha256"],
                width=row["width"],
                height=row["height"],
                status=row["status"],
                ocr_text=row["ocr_text"] or "",
            )
            for row in rows
        ]

    def save_vision_fields(
        self,
        *,
        screenshot_capture_id: int,
        fields: list[dict[str, Any]],
    ) -> int:
        with self._tx() as conn:
            conn.execute(
                "DELETE FROM vision_fields WHERE screenshot_capture_id = ?",
                (screenshot_capture_id,),
            )
            if not fields:
                return 0
            before = conn.total_changes
            conn.executemany(
                """
                INSERT OR IGNORE INTO vision_fields (
                    screenshot_capture_id, created_at, field_name, value_text, value_num,
                    confidence, region_name, method, crop_path, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        screenshot_capture_id,
                        datetime.now().isoformat(),
                        f["field_name"],
                        f.get("value_text", ""),
                        f.get("value_num"),
                        f.get("confidence", "debug"),
                        f["region_name"],
                        f.get("method", "fixed_region_crop"),
                        f.get("crop_path", ""),
                        json.dumps(f.get("metadata", {})),
                    )
                    for f in fields
                ],
            )
            return conn.total_changes - before

    def list_recent_vision_fields(self, limit: int = 300) -> list[VisionField]:
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT vf.id, vf.screenshot_capture_id, sc.captured_at, vf.field_name,
                       vf.value_text, vf.value_num, vf.confidence, vf.region_name,
                       vf.method, vf.crop_path
                FROM vision_fields vf
                JOIN screenshot_captures sc ON sc.id = vf.screenshot_capture_id
                ORDER BY datetime(sc.captured_at) DESC, vf.id DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cur.fetchall()
        return [
            VisionField(
                id=int(row["id"]),
                screenshot_capture_id=int(row["screenshot_capture_id"]),
                captured_at=datetime.fromisoformat(row["captured_at"]),
                field_name=row["field_name"],
                value_text=row["value_text"] or "",
                value_num=row["value_num"],
                confidence=row["confidence"],
                region_name=row["region_name"],
                method=row["method"],
                crop_path=row["crop_path"] or "",
            )
            for row in rows
        ]

    def get_visual_match_detail(self, group_path: str) -> dict | None:
        group = Path(group_path)
        captures = [
            c for c in self.list_recent_screenshot_captures(limit=5000)
            if Path(c.image_path).parent == group
        ]
        if not captures:
            return None
        captures.sort(key=lambda c: c.captured_at)
        capture_ids = {c.id for c in captures}
        fields = [
            f for f in self.list_recent_vision_fields(limit=5000)
            if f.screenshot_capture_id in capture_ids
        ]
        return {
            "group_path": str(group),
            "started_at": captures[0].captured_at,
            "ended_at": captures[-1].captured_at,
            "frame_count": len(captures),
            "captures": captures,
            "vision_fields": fields,
            "parsed_fields": aggregate_vision_fields(fields),
        }

    def _delete_visual_group_files(
        self,
        group: Path,
        image_paths: list[Path],
        captures_root: Path,
    ) -> None:
        group_resolved = self._resolve_path(group)
        captures_root_resolved = self._resolve_path(captures_root)
        if (
            group_resolved is None
            or captures_root_resolved is None
            or not self._is_inside(group_resolved, captures_root_resolved)
        ):
            return

        for image_path in image_paths:
            image_resolved = self._resolve_path(image_path)
            if image_resolved is None or not self._is_inside(image_resolved, captures_root_resolved):
                continue
            try:
                if image_resolved.exists() and image_resolved.is_file():
                    image_resolved.unlink()
            except OSError:
                continue

        debug_dir = group_resolved / "vision_debug"
        if debug_dir.exists() and self._is_inside(debug_dir, captures_root_resolved):
            try:
                shutil.rmtree(debug_dir)
            except OSError:
                pass

        try:
            if group_resolved.exists() and not any(group_resolved.iterdir()):
                group_resolved.rmdir()
        except OSError:
            pass

    @staticmethod
    def _resolve_path(path: Path) -> Path | None:
        try:
            return path.resolve()
        except OSError:
            return None

    @staticmethod
    def _is_inside(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
        except ValueError:
            return False
        return True


def _confidence_value(field: VisionField) -> float:
    try:
        return float(field.confidence)
    except (TypeError, ValueError):
        return 0.0


def aggregate_vision_fields(fields: list[VisionField]) -> dict[str, str]:
    best: dict[str, VisionField] = {}
    for field in fields:
        value = (field.value_text or "").strip()
        if not value:
            continue
        current = best.get(field.field_name)
        if current is None:
            best[field.field_name] = field
            continue
        score = _confidence_value(field)
        current_score = _confidence_value(current)
        if field.field_name in {"bloodline_xp", "hunt_dollars", "event_reward", "next_unlock"}:
            if (field.value_num or 0) > (current.value_num or 0):
                best[field.field_name] = field
            continue
        if score > current_score:
            best[field.field_name] = field
    return {name: field.value_text for name, field in best.items()}


def _field_text(fields: dict[str, str], name: str) -> str:
    return fields.get(name, "?") or "?"


def _field_int(fields: dict[str, str], name: str) -> int | None:
    value = fields.get(name)
    if not value:
        return None
    match = re.search(r"[+-]?\d+", value)
    if not match:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None
