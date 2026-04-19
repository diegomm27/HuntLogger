from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .db import Database, EvidenceDelta, EvidenceEvent, SourceSnapshotSummary


@dataclass
class LastGameSummary:
    has_data: bool
    title: str
    scope: str
    warning: str
    match_candidate_id: int | None = None
    session_id: int | None = None
    ended_at: datetime | None = None
    started_at: datetime | None = None
    postmatch_at: datetime | None = None
    map_name: str | None = None
    duration_seconds: int | None = None
    confidence: str = "unknown"
    steam_deltas: list[EvidenceDelta] = field(default_factory=list)
    account_deltas: list[EvidenceDelta] = field(default_factory=list)
    log_events: list[EvidenceEvent] = field(default_factory=list)
    sources: list[SourceSnapshotSummary] = field(default_factory=list)


def _parse_dt(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _window_start(deltas: list[EvidenceDelta], fallback: datetime) -> datetime:
    starts = [d.from_captured_at for d in deltas if d.from_captured_at is not None]
    if starts:
        return min(starts)
    return fallback


def _window_end(deltas: list[EvidenceDelta], fallback: datetime) -> datetime:
    if deltas:
        return max(d.captured_at for d in deltas)
    return fallback


def _scope_warning(
    *,
    db: Database,
    session_id: int | None,
    ended_at: datetime,
    deltas: list[EvidenceDelta],
) -> tuple[str, str]:
    if not deltas:
        return (
            "observed",
            "Latest match timing is from Game.log. No Steam or account deltas have been captured after it yet.",
        )

    start = _window_start(deltas, ended_at)
    end = _window_end(deltas, ended_at)
    count = db.count_match_candidates_between(session_id=session_id, start=start, end=end)
    if count <= 1:
        return (
            "latest match",
            "Deltas are timing-linked to the latest match hint. Treat counters as inferred, not server-confirmed.",
        )
    return (
        "session",
        "Multiple match hints occurred inside the source-diff window. These values are session totals, not exact last-match stats.",
    )


def build_last_game_summary(db: Database) -> LastGameSummary:
    candidate = db.get_latest_match_candidate()
    sources = db.list_latest_source_snapshots(limit=12)

    if not candidate:
        return LastGameSummary(
            has_data=bool(sources),
            title="No match hint found yet",
            scope="source snapshots",
            warning=(
                "The app has captured local files, but Game.log has not produced a match-end marker yet."
                if sources else
                "No local Hunt evidence has been captured yet. Set the install path, start watching, then refresh after playing."
            ),
            sources=sources,
        )

    ended_at = _parse_dt(candidate.get("ended_at"))
    if ended_at is None:
        return LastGameSummary(
            has_data=bool(sources),
            title="Latest match hint is unreadable",
            scope="unknown",
            warning="The latest match candidate has an invalid timestamp.",
            sources=sources,
        )

    session_id = candidate.get("session_id")
    session_id_int = int(session_id) if session_id is not None else None
    steam = db.list_achievement_deltas_since(ended_at, limit=100)
    account = db.list_account_deltas_since(ended_at, limit=100)
    deltas = steam + account
    scope, warning = _scope_warning(
        db=db,
        session_id=session_id_int,
        ended_at=ended_at,
        deltas=deltas,
    )

    return LastGameSummary(
        has_data=True,
        title="Latest saved game data",
        scope=scope,
        warning=warning,
        match_candidate_id=int(candidate["id"]),
        session_id=session_id_int,
        started_at=_parse_dt(candidate.get("started_at")),
        ended_at=ended_at,
        postmatch_at=_parse_dt(candidate.get("postmatch_at")),
        map_name=candidate.get("map_name"),
        duration_seconds=candidate.get("duration_seconds"),
        confidence=candidate.get("confidence") or "unknown",
        steam_deltas=steam,
        account_deltas=account,
        log_events=(
            db.list_session_events_for_session(session_id_int, limit=50)
            if session_id_int is not None else []
        ),
        sources=sources,
    )
