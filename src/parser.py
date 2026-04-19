from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


_PLAYER_RE = re.compile(r"^MissionBagPlayer_(\d+)_(\d+)_(.+)$")
_TEAM_RE = re.compile(r"^MissionBagTeam_(\d+)_(.+)$")
_ENTRY_RE = re.compile(r"^MissionBagEntry_(\d+)_(.+)$")
_ACCOLADE_RE = re.compile(r"^MissionAccoladeEntry_(\d+)_(.+)$")
_BOSS_RE = re.compile(r"^MissionBagBoss_(\d+)$")


def _to_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return default


def _to_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    return str(v).strip().lower() in ("true", "1", "yes")


@dataclass
class Player:
    team_idx: int
    player_idx: int
    fields: dict[str, str] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.fields.get("blood_line_name", "")

    @property
    def profile_id(self) -> str:
        return self.fields.get("profileid", "")

    @property
    def mmr(self) -> int:
        return _to_int(self.fields.get("mmr"))

    @property
    def killed_by_me(self) -> int:
        return _to_int(self.fields.get("killedbyme"))

    @property
    def killed_me(self) -> int:
        return _to_int(self.fields.get("killedme"))

    @property
    def downed_by_me(self) -> int:
        return _to_int(self.fields.get("downedbyme"))

    @property
    def downed_me(self) -> int:
        return _to_int(self.fields.get("downedme"))

    @property
    def killed_by_teammate(self) -> int:
        return _to_int(self.fields.get("killedbyteammate"))

    @property
    def downed_by_teammate(self) -> int:
        return _to_int(self.fields.get("downedbyteammate"))

    @property
    def is_partner(self) -> bool:
        return _to_bool(self.fields.get("ispartner"))

    @property
    def had_bounty(self) -> bool:
        return _to_bool(self.fields.get("hadbounty"))

    @property
    def bounty_picked_up(self) -> int:
        return _to_int(self.fields.get("bountypickedup"))

    @property
    def team_extraction(self) -> bool:
        return _to_bool(self.fields.get("teamextraction"))

    @property
    def is_soul_survivor(self) -> bool:
        return _to_bool(self.fields.get("issoulsurvivor"))

    @property
    def proximity_to_me(self) -> bool:
        return _to_bool(self.fields.get("proximitytome"))


@dataclass
class Team:
    idx: int
    fields: dict[str, str] = field(default_factory=dict)
    players: list[Player] = field(default_factory=list)

    @property
    def mmr(self) -> int:
        return _to_int(self.fields.get("mmr"))

    @property
    def num_players(self) -> int:
        return _to_int(self.fields.get("numplayers"), len(self.players))

    @property
    def is_own_team(self) -> bool:
        return _to_bool(self.fields.get("ownteam"))

    @property
    def handicap(self) -> int:
        return _to_int(self.fields.get("handicap"))

    @property
    def prestige(self) -> int:
        return _to_int(self.fields.get("prestige"))

    @property
    def is_invite(self) -> bool:
        return _to_bool(self.fields.get("isinvite"))


@dataclass
class Accolade:
    idx: int
    fields: dict[str, str] = field(default_factory=dict)

    @property
    def category(self) -> str:
        return self.fields.get("category", "")

    @property
    def title(self) -> str:
        return self.fields.get("title", "")

    @property
    def header(self) -> str:
        return self.fields.get("header", "")

    @property
    def bounty(self) -> int:
        return _to_int(self.fields.get("bountyScore") or self.fields.get("bounty"))

    @property
    def gold(self) -> int:
        return _to_int(self.fields.get("gold"))

    @property
    def xp(self) -> int:
        return _to_int(self.fields.get("xp"))

    @property
    def hunter_xp(self) -> int:
        return _to_int(self.fields.get("hunterXp") or self.fields.get("hunterxp"))

    @property
    def hits(self) -> int:
        return _to_int(self.fields.get("hits"))

    @property
    def weighting(self) -> int:
        return _to_int(self.fields.get("weighting"))

    @property
    def generated_gems(self) -> int:
        return _to_int(self.fields.get("generatedGems"))


@dataclass
class MissionEntry:
    idx: int
    fields: dict[str, str] = field(default_factory=dict)

    @property
    def category(self) -> str:
        return self.fields.get("category", "")

    @property
    def amount(self) -> int:
        return _to_int(self.fields.get("amount"))

    @property
    def reward(self) -> int:
        return _to_int(self.fields.get("reward"))

    @property
    def reward_size(self) -> int:
        return _to_int(self.fields.get("rewardSize"))

    @property
    def reward_type(self) -> int:
        return _to_int(self.fields.get("rewardType"))

    @property
    def descriptor_name(self) -> str:
        return self.fields.get("descriptorName", "")

    @property
    def descriptor_score(self) -> int:
        return _to_int(self.fields.get("descriptorScore"))

    @property
    def descriptor_type(self) -> str:
        return self.fields.get("descriptorType", "")

    @property
    def ui_name(self) -> str:
        return self.fields.get("uiName", "")

    @property
    def ui_name_2(self) -> str:
        return self.fields.get("uiName2", "")


@dataclass
class Match:
    timestamp: datetime
    xml_hash: str
    raw_attributes: dict[str, str]
    teams: list[Team] = field(default_factory=list)
    players: list[Player] = field(default_factory=list)
    accolades: list[Accolade] = field(default_factory=list)
    entries: list[MissionEntry] = field(default_factory=list)
    bosses: dict[int, bool] = field(default_factory=dict)
    raw_xml: str = ""

    @property
    def is_hunter_dead(self) -> bool:
        return _to_bool(self.raw_attributes.get("MissionBagIsHunterDead"))

    @property
    def is_quickplay(self) -> bool:
        return _to_bool(self.raw_attributes.get("MissionBagIsQuickPlay"))

    @property
    def is_tutorial(self) -> bool:
        return _to_bool(self.raw_attributes.get("MissionBagIsTutorial"))

    @property
    def fbe_gold_bonus(self) -> int:
        return _to_int(self.raw_attributes.get("MissionBagFbeGoldBonus"))

    @property
    def fbe_hunter_xp_bonus(self) -> int:
        return _to_int(self.raw_attributes.get("MissionBagFbeHunterXpBonus"))

    @property
    def num_teams(self) -> int:
        return _to_int(self.raw_attributes.get("MissionBagNumTeams"), len(self.teams))

    @property
    def num_accolades(self) -> int:
        return _to_int(self.raw_attributes.get("MissionBagNumAccolades"), len(self.accolades))

    @property
    def num_entries(self) -> int:
        return _to_int(self.raw_attributes.get("MissionBagNumEntries"), len(self.entries))

    @property
    def own_team(self) -> Team | None:
        for t in self.teams:
            if t.is_own_team:
                return t
        return None

    @property
    def own_players(self) -> list[Player]:
        t = self.own_team
        return t.players if t else []

    @property
    def total_kills_by_me(self) -> int:
        return sum(p.killed_by_me + p.downed_by_me for p in self.players)

    @property
    def total_deaths_to_others(self) -> int:
        return sum(p.killed_me + p.downed_me for p in self.players)

    @property
    def total_bounty(self) -> int:
        return sum(a.bounty for a in self.accolades)

    @property
    def total_hunter_xp(self) -> int:
        return sum(a.hunter_xp for a in self.accolades)

    @property
    def total_gold(self) -> int:
        return sum(a.gold for a in self.accolades)

    @property
    def has_match_data(self) -> bool:
        """True only when the file contains a post-match MissionBag snapshot."""
        return (
            "MissionBagNumTeams" in self.raw_attributes
            or "MissionBagIsHunterDead" in self.raw_attributes
            or "MissionBagNumEntries" in self.raw_attributes
        )


def compute_xml_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_attributes_xml(path: Path | str, fallback_timestamp: datetime | None = None) -> Match:
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    ts = fallback_timestamp or datetime.fromtimestamp(path.stat().st_mtime)
    return parse_attributes_text(text, ts)


def parse_attributes_text(text: str, timestamp: datetime) -> Match:
    raw: dict[str, str] = {}
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        cleaned = text.lstrip("\ufeff").strip()
        root = ET.fromstring(cleaned)

    for el in root.iter("Attr"):
        name = el.get("name")
        if name is None:
            continue
        raw[name] = el.get("value", "")

    teams: dict[int, Team] = {}
    players: dict[tuple[int, int], Player] = {}
    accolades: dict[int, Accolade] = {}
    entries: dict[int, MissionEntry] = {}
    bosses: dict[int, bool] = {}

    for key, value in raw.items():
        m = _PLAYER_RE.match(key)
        if m:
            ti, pi, sub = int(m.group(1)), int(m.group(2)), m.group(3)
            pk = (ti, pi)
            p = players.setdefault(pk, Player(team_idx=ti, player_idx=pi))
            p.fields[sub] = value
            continue
        m = _TEAM_RE.match(key)
        if m:
            ti, sub = int(m.group(1)), m.group(2)
            t = teams.setdefault(ti, Team(idx=ti))
            t.fields[sub] = value
            continue
        m = _ACCOLADE_RE.match(key)
        if m:
            idx, sub = int(m.group(1)), m.group(2)
            a = accolades.setdefault(idx, Accolade(idx=idx))
            a.fields[sub] = value
            continue
        m = _ENTRY_RE.match(key)
        if m:
            idx, sub = int(m.group(1)), m.group(2)
            e = entries.setdefault(idx, MissionEntry(idx=idx))
            e.fields[sub] = value
            continue
        m = _BOSS_RE.match(key)
        if m:
            bosses[int(m.group(1))] = _to_bool(value)

    team_list = [teams[k] for k in sorted(teams)]
    for p in players.values():
        if p.team_idx in teams:
            teams[p.team_idx].players.append(p)
    for t in team_list:
        t.players.sort(key=lambda x: x.player_idx)

    all_players = sorted(players.values(), key=lambda p: (p.team_idx, p.player_idx))
    all_accolades = [accolades[k] for k in sorted(accolades)]
    all_entries = [entries[k] for k in sorted(entries)]

    return Match(
        timestamp=timestamp,
        xml_hash=compute_xml_hash(text),
        raw_attributes=raw,
        teams=team_list,
        players=all_players,
        accolades=all_accolades,
        entries=all_entries,
        bosses=bosses,
        raw_xml=text,
    )
