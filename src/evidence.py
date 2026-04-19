from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .parser import parse_attributes_text


MAX_TEXT_SNAPSHOT_BYTES = 8 * 1024 * 1024
MAX_BINARY_SNAPSHOT_BYTES = 16 * 1024 * 1024


@dataclass
class FileCapture:
    path: Path
    captured_at: datetime
    mtime: datetime | None
    size: int | None
    sha256: str
    content_text: str | None = None
    content_blob: bytes | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class LogEvent:
    timestamp: datetime
    event_type: str
    summary: str
    confidence: str
    line_no: int
    payload: dict[str, Any]


@dataclass
class MatchCandidate:
    ended_at: datetime
    started_at: datetime | None = None
    postmatch_at: datetime | None = None
    map_name: str | None = None
    duration_seconds: int | None = None
    confidence: str = "observed"
    evidence: dict[str, Any] | None = None


_LOG_TS_RE = re.compile(
    r"^(?:<(?P<bracket_time>\d{2}:\d{2}:\d{2})>"
    r"|(?:(?P<date>\d{4}-\d{2}-\d{2})[ T])?"
    r"(?P<plain_time>\d{2}:\d{2}:\d{2})(?:[.,](?P<millis>\d{1,6}))?)"
)
_LOG_STARTED_RE = re.compile(
    r"^Log Started at \w{3} (?P<month>\w{3}) (?P<day>\d{1,2}) "
    r"(?P<time>\d{2}:\d{2}:\d{2}) (?P<year>\d{4})"
)

_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

_MAP_HINTS = {
    "cemetery": "DeSalle",
    "civilwar": "Stillwater Bayou",
    "creek": "Lawson Delta",
    "desalle": "DeSalle",
    "lawson": "Lawson Delta",
    "stillwater": "Stillwater Bayou",
    "mammon": "Mammon's Gulch",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def capture_file(path: Path, *, text: bool) -> FileCapture | None:
    try:
        stat = path.stat()
        data = path.read_bytes()
    except OSError:
        return None

    metadata: dict[str, Any] = {}
    captured_at = datetime.now()
    mtime = datetime.fromtimestamp(stat.st_mtime)
    digest = sha256_bytes(data)

    if text:
        if len(data) > MAX_TEXT_SNAPSHOT_BYTES:
            metadata["truncated"] = True
            metadata["stored_bytes"] = MAX_TEXT_SNAPSHOT_BYTES
            data = data[:MAX_TEXT_SNAPSHOT_BYTES]
        return FileCapture(
            path=path,
            captured_at=captured_at,
            mtime=mtime,
            size=stat.st_size,
            sha256=digest,
            content_text=data.decode("utf-8", errors="replace"),
            metadata=metadata,
        )

    if len(data) > MAX_BINARY_SNAPSHOT_BYTES:
        metadata["omitted_blob"] = True
        metadata["reason"] = "binary snapshot exceeds size limit"
        blob = None
    else:
        blob = data
    return FileCapture(
        path=path,
        captured_at=captured_at,
        mtime=mtime,
        size=stat.st_size,
        sha256=digest,
        content_blob=blob,
        metadata=metadata,
    )


def parse_json_text(text: str) -> Any | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _flatten_scalars(value: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if _is_scalar(value):
        out[prefix or "$"] = value
        return out
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{prefix}.{key}" if prefix else str(key)
            out.update(_flatten_scalars(child, child_path))
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            child_path = f"{prefix}[{idx}]" if prefix else f"[{idx}]"
            out.update(_flatten_scalars(child, child_path))
    return out


def _looks_like_achievement_record(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    keys = {str(k).lower() for k in value}
    identity = {"name", "apiname", "api_name", "id", "displayname", "display_name"}
    state = {
        "achieved",
        "unlocked",
        "unlocktime",
        "progress",
        "current",
        "max",
        "min",
        "value",
        "counter",
    }
    return bool(keys & identity) and bool(keys & state)


def _record_key(path: str, record: dict[str, Any]) -> str:
    for key in ("apiname", "apiName", "api_name", "name", "id", "displayName", "display_name"):
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    return path or "achievement"


def _iter_achievement_records(value: Any, path: str = "") -> Iterable[tuple[str, dict[str, Any]]]:
    if _looks_like_achievement_record(value):
        yield _record_key(path, value), value
        return

    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if isinstance(child, dict) and _looks_like_achievement_record(child):
                yield _record_key(child_path, child), child
            elif isinstance(child, list) and str(key).lower() in {"achievements", "rgachievements"}:
                for idx, item in enumerate(child):
                    if isinstance(item, dict):
                        item_path = f"{child_path}[{idx}]"
                        yield _record_key(item_path, item), item
            elif isinstance(child, dict) and str(key).lower() in {"achievements", "rgachievements"}:
                for child_key, item in child.items():
                    if isinstance(item, dict):
                        item_path = f"{child_path}.{child_key}"
                        yield _record_key(item_path, item), item
            else:
                yield from _iter_achievement_records(child, child_path)
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            child_path = f"{path}[{idx}]" if path else f"[{idx}]"
            yield from _iter_achievement_records(child, child_path)


def extract_achievement_values(data: Any) -> dict[tuple[str, str], Any]:
    values: dict[tuple[str, str], Any] = {}
    records = list(_iter_achievement_records(data))
    if not records:
        records = [("librarycache", data if isinstance(data, dict) else {"value": data})]

    for achievement_key, record in records:
        for field_path, value in _flatten_scalars(record).items():
            if _is_scalar(value):
                values[(achievement_key, field_path)] = value
    return values


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _value_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def diff_achievement_values(
    old: dict[tuple[str, str], Any],
    new: dict[tuple[str, str], Any],
) -> list[dict[str, Any]]:
    deltas: list[dict[str, Any]] = []
    for key in sorted(set(old) | set(new)):
        old_value = old.get(key)
        new_value = new.get(key)
        if old_value == new_value:
            continue

        achievement_key, field_path = key
        old_num = _num(old_value)
        new_num = _num(new_value)
        field_lower = field_path.lower()
        change_type = "changed"
        confidence = "observed"
        delta_num: float | None = None

        if old_value is None:
            if "unlock" in field_lower and new_num is not None and new_num > 0:
                change_type = "achievement_unlocked"
                confidence = "strong_inference"
            elif "achieved" in field_lower and new_num == 1:
                change_type = "achievement_unlocked"
                confidence = "strong_inference"
            else:
                change_type = "added"
        elif new_value is None:
            change_type = "removed"
        elif old_num is not None and new_num is not None:
            delta_num = new_num - old_num
            if "unlock" in field_lower and old_num == 0 and new_num > 0:
                change_type = "achievement_unlocked"
                confidence = "strong_inference"
            elif "achieved" in field_lower and old_num == 0 and new_num == 1:
                change_type = "achievement_unlocked"
                confidence = "strong_inference"
            elif delta_num > 0:
                change_type = "progress_increased"
                confidence = "strong_inference"
            elif delta_num < 0:
                change_type = "counter_decreased"
                confidence = "unknown"

        deltas.append(
            {
                "achievement_key": achievement_key,
                "field_path": field_path,
                "old_value": _value_text(old_value),
                "new_value": _value_text(new_value),
                "delta_num": delta_num,
                "change_type": change_type,
                "confidence": confidence,
            }
        )
    return deltas


def extract_attributes(text: str, timestamp: datetime | None = None) -> dict[str, str]:
    match = parse_attributes_text(text, timestamp or datetime.now())
    return match.raw_attributes


def _account_category(key: str) -> str:
    lower = key.lower()
    if lower.startswith("activeskin/"):
        return "skin"
    if "unlock" in lower:
        return "unlock"
    if "trait" in lower:
        return "trait"
    if "bloodline" in lower or "prestige" in lower or "xp" in lower or "money" in lower:
        return "progression"
    if lower.startswith("pc_"):
        return "keybinding"
    if "volume" in lower or "sensitivity" in lower or "fieldofview" in lower:
        return "settings"
    return "account"


def diff_account_attributes(old: dict[str, str], new: dict[str, str]) -> list[dict[str, Any]]:
    deltas: list[dict[str, Any]] = []
    for key in sorted(set(old) | set(new)):
        old_value = old.get(key)
        new_value = new.get(key)
        if old_value == new_value:
            continue
        category = _account_category(key)
        if category in {"settings", "keybinding"}:
            confidence = "observed"
        elif category in {"skin", "unlock", "trait", "progression"}:
            confidence = "strong_inference"
        else:
            confidence = "observed"

        if old_value is None:
            change_type = "added"
        elif new_value is None:
            change_type = "removed"
        elif category in {"unlock", "trait"} and old_value in {"0", "false", "False"} and new_value in {"1", "true", "True"}:
            change_type = "unlocked"
        elif category == "skin":
            change_type = "skin_changed"
        else:
            change_type = "changed"

        deltas.append(
            {
                "attr_key": key,
                "old_value": old_value or "",
                "new_value": new_value or "",
                "change_type": change_type,
                "category": category,
                "confidence": confidence,
            }
        )
    return deltas


def _parse_log_timestamp(line: str, fallback_date: datetime) -> datetime | None:
    match = _LOG_TS_RE.match(line.strip())
    if not match:
        return None

    bracket_time = match.group("bracket_time")
    time_text = bracket_time or match.group("plain_time")
    if time_text is None:
        return None
    date_text = match.group("date") or fallback_date.strftime("%Y-%m-%d")
    millis = (match.group("millis") or "0")[:6].ljust(6, "0")
    try:
        return datetime.fromisoformat(f"{date_text}T{time_text}.{millis}")
    except ValueError:
        return None


def _parse_log_started_at(line: str) -> datetime | None:
    match = _LOG_STARTED_RE.match(line.strip())
    if not match:
        return None
    month = _MONTHS.get(match.group("month").lower())
    if month is None:
        return None
    try:
        return datetime.fromisoformat(
            f"{int(match.group('year')):04d}-{month:02d}-{int(match.group('day')):02d}T"
            f"{match.group('time')}"
        )
    except ValueError:
        return None


def _map_hint(line: str) -> str | None:
    lower = line.lower()
    for needle, display in _MAP_HINTS.items():
        if needle in lower:
            return display
    return None


def parse_game_log(text: str, fallback_date: datetime | None = None) -> tuple[list[LogEvent], list[MatchCandidate]]:
    fallback = fallback_date or datetime.now()
    for line in text.splitlines():
        started_at = _parse_log_started_at(line)
        if started_at is not None:
            fallback = started_at
            break

    events: list[LogEvent] = []
    candidates: list[MatchCandidate] = []
    last_start: tuple[datetime, int] | None = None
    last_map: str | None = None
    mission_active = False

    for idx, line in enumerate(text.splitlines(), start=1):
        ts = _parse_log_timestamp(line, fallback)
        if ts is None:
            continue
        lower = line.lower()
        map_name = _map_hint(line)
        if map_name:
            last_map = map_name

        event: LogEvent | None = None
        if "postmatchsummary" in lower:
            event = LogEvent(
                timestamp=ts,
                event_type="post_match_summary",
                summary="Post-match summary screen observed",
                confidence="observed",
                line_no=idx,
                payload={"line": line.strip()},
            )
            if candidates and 0 <= (ts - candidates[-1].ended_at).total_seconds() <= 30:
                candidates[-1].postmatch_at = ts
                if candidates[-1].evidence is None:
                    candidates[-1].evidence = {}
                candidates[-1].evidence["postmatch_line"] = idx
        elif "cmetamissionbag" in lower and "contentsdumped" in lower:
            event = LogEvent(
                timestamp=ts,
                event_type="match_contents_dumped",
                summary="Match end marker observed in Game.log",
                confidence="observed",
                line_no=idx,
                payload={"line": line.strip()},
            )
            started_at = last_start[0] if last_start else None
            duration = int((ts - started_at).total_seconds()) if started_at else None
            candidates.append(
                MatchCandidate(
                    started_at=started_at,
                    ended_at=ts,
                    postmatch_at=None,
                    map_name=last_map,
                    duration_seconds=duration,
                    confidence="observed",
                    evidence={"end_line": idx, "start_line": last_start[1] if last_start else None},
                )
            )
            mission_active = False
            last_start = None
        elif "retrievepersistentlobby" in lower and "error" in lower:
            event = LogEvent(
                timestamp=ts,
                event_type="lobby_retrieval_error",
                summary="Persistent lobby retrieval failed",
                confidence="observed",
                line_no=idx,
                payload={"line": line.strip()},
            )
        elif "cmetamissionbag" in lower and "missionstarted" in lower:
            if mission_active:
                continue
            event = LogEvent(
                timestamp=ts,
                event_type="mission_started",
                summary="Mission start hint observed",
                confidence="weak_inference",
                line_no=idx,
                payload={"line": line.strip(), "map": map_name},
            )
            last_start = (ts, idx)
            mission_active = True
        elif "loading level" in lower and map_name:
            event = LogEvent(
                timestamp=ts,
                event_type="map_loading",
                summary=f"Map loading hint observed: {map_name}",
                confidence="weak_inference",
                line_no=idx,
                payload={"line": line.strip(), "map": map_name},
            )

        if event is not None:
            events.append(event)

    return events, candidates
