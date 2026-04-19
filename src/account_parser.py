from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .parser import parse_attributes_xml, parse_attributes_text


_KEYCODE_MAP: dict[int, str] = {
    1: "Esc", 2: "1", 3: "2", 4: "3", 5: "4", 6: "5", 7: "6", 8: "7",
    9: "8", 10: "9", 11: "0", 12: "-", 13: "=", 14: "Backspace",
    15: "Tab", 16: "Q", 17: "W", 18: "E", 19: "R", 20: "T", 21: "Y",
    22: "U", 23: "I", 24: "O", 25: "P", 26: "[", 27: "]", 28: "Enter",
    29: "LCtrl", 30: "A", 31: "S", 32: "D", 33: "F", 34: "G", 35: "H",
    36: "J", 37: "K", 38: "L", 39: ";", 40: "'", 41: "`",
    42: "LShift", 43: "\\", 44: "Z", 45: "X", 46: "C", 47: "V",
    48: "B", 49: "N", 50: "M", 51: ",", 52: ".", 53: "/",
    54: "RShift", 55: "Num*", 56: "LAlt", 57: "Space",
    256: "LMB", 257: "RMB", 258: "MMB", 259: "Mouse4", 260: "Mouse5",
    330: "MWheelUp", 331: "MWheelDown",
}

_BIND_LABELS: dict[str, str] = {
    "attack": "Primary fire", "aim": "Aim / ADS", "aimtoggle": "ADS toggle",
    "interact": "Interact", "bandage": "Bandage", "darkvision": "Dark Sight",
    "darksight_boost": "DS boost", "darksight_interact": "DS interact",
    "crouch": "Crouch", "ascent": "Climb up", "descent": "Slide down",
    "sprint": "Sprint", "item1": "Item 1", "item2": "Item 2",
    "item3": "Item 3", "item4": "Item 4", "item5": "Item 5",
    "melee": "Melee", "reload": "Reload", "swap_weapons": "Swap weapon",
    "inspect": "Inspect", "ping": "Ping", "scoreboard": "Scoreboard",
    "map": "Map", "chat": "Chat",
}

_GRAPHICS_LABELS: dict[str, str] = {
    "FieldOfView": "Field of View",
    "MaxFPS": "Max FPS",
    "MotionBlur": "Motion Blur",
    "DepthOfField": "Depth of Field",
    "SysSpec": "Graphics Preset",
    "SysSpecObject": "Object Quality",
    "SysSpecPostProcess": "Post Process",
    "SysSpecTextureQuality": "Texture Quality",
    "SysSpecViewDist": "View Distance",
    "NVidiaSuperRes": "NVIDIA Super Res",
    "AMDSuperRes": "AMD Super Res",
    "SuperResolutionMode": "Super Res Mode",
    "VRamUsage": "VRAM Budget %",
    "Gamma": "Gamma",
    "SceneBrightness": "Scene Brightness",
}

_AUDIO_LABELS: dict[str, str] = {
    "MasterVolume": "Master Volume",
    "SFXVolume": "SFX Volume",
    "MusicVolume": "Music Volume",
    "DialogueVolume": "Dialogue Volume",
    "MenuAmbienceVolume": "Menu Ambience",
    "VOIP_VolumeIndependentFromMaster": "VOIP Separate Volume",
}

_SENS_LABELS: dict[str, str] = {
    "MouseSensitivity": "Base Sensitivity",
    "HipMouseSensitivity": "Hip Sensitivity",
    "IronSightsMouseSensitivity": "Iron Sights Sens",
    "ShortScopeMouseSensitivity": "Short Scope Sens",
    "MediumScopeMouseSensitivity": "Medium Scope Sens",
    "LongScopeMouseSensitivity": "Long Scope Sens",
    "PeepholeMouseSensitivity": "Peephole Sens",
}

_MAP_NAMES: dict[str, str] = {
    "cemetery": "DeSalle", "civilwar": "Stillwater Bayou", "creek": "Lawson Delta",
}


@dataclass
class ActiveSkin:
    slot: int
    base_item: str
    base_rarity: str
    skin_item: str
    skin_rarity: str
    is_legendary: bool


@dataclass
class AccountProfile:
    region: str = ""
    last_event: str = ""
    num_active_skins: int = 0
    map_loading_times: dict[str, int] = field(default_factory=dict)
    graphics: dict[str, str] = field(default_factory=dict)
    audio: dict[str, str] = field(default_factory=dict)
    sensitivities: dict[str, str] = field(default_factory=dict)
    keybindings: dict[str, str] = field(default_factory=dict)
    active_skins: list[ActiveSkin] = field(default_factory=list)
    misc: dict[str, str] = field(default_factory=dict)


def _keycode_name(code: int) -> str:
    return _KEYCODE_MAP.get(code, f"Key{code}")


def _parse_skin_value(slot: int, value: str) -> ActiveSkin | None:
    """Parse 'base_item|rarity|level=skin_item|rarity|level'."""
    if "=" not in value:
        return None
    left, right = value.split("=", 1)

    def _split(s: str) -> tuple[str, str]:
        parts = s.split("|")
        name = parts[0].strip()
        rarity = parts[1].strip() if len(parts) > 1 else "normal"
        return name, rarity

    base_name, base_rarity = _split(left)
    skin_name, skin_rarity = _split(right)
    is_legendary = skin_name.lower().startswith("legendary")
    return ActiveSkin(slot, base_name, base_rarity, skin_name, skin_rarity, is_legendary)


def parse_account_profile(attrs: dict[str, str]) -> AccountProfile:
    prof = AccountProfile()
    prof.region = attrs.get("Region", attrs.get("Primary Region Switcher", ""))
    prof.last_event = attrs.get("LastLiveEventIDLoaded", "")
    prof.num_active_skins = int(attrs.get("NumActiveSkins", 0) or 0)

    for raw_map, display in _MAP_NAMES.items():
        key = f"PCLevelLoadingTime{raw_map.capitalize()}"
        # game uses CamelCase variants
        for k, v in attrs.items():
            if k.lower() == key.lower():
                try:
                    prof.map_loading_times[display] = int(v)
                except ValueError:
                    pass
                break

    for key, label in _GRAPHICS_LABELS.items():
        if key in attrs:
            prof.graphics[label] = attrs[key]

    for key, label in _AUDIO_LABELS.items():
        if key in attrs:
            prof.audio[label] = attrs[key]

    for key, label in _SENS_LABELS.items():
        if key in attrs:
            prof.sensitivities[label] = attrs[key]

    # Keybindings: PC_action_1 / PC_action_2
    bind_re = re.compile(r"^PC_([a-z_]+)_([12])$")
    bindings: dict[str, dict[str, int]] = {}
    for k, v in attrs.items():
        m = bind_re.match(k)
        if m:
            action, slot = m.group(1), m.group(2)
            try:
                code = int(v)
            except ValueError:
                continue
            if code != -1:
                bindings.setdefault(action, {})[slot] = code
    for action, slots in bindings.items():
        label = _BIND_LABELS.get(action, action.replace("_", " ").title())
        parts = [_keycode_name(c) for c in sorted(slots.values())]
        prof.keybindings[label] = " / ".join(parts)

    # Active skins
    skin_re = re.compile(r"^ActiveSkin/(\d+)$")
    skins: list[ActiveSkin] = []
    for k, v in attrs.items():
        m = skin_re.match(k)
        if m:
            skin = _parse_skin_value(int(m.group(1)), v)
            if skin:
                skins.append(skin)
    skins.sort(key=lambda s: s.slot)
    prof.active_skins = skins

    # Misc interesting singleton keys
    misc_keys = [
        "NewRecruitHealthSetup", "AutoEquipEnabledWeapons", "AutoEquipEnabledTools",
        "AutoEquipEnabledConsumables", "AimMode", "CrouchSwitcher",
        "Sprint Switcher", "Crouch Switcher", "FieldOfViewShoulderAim",
        "HighlightMode", "PerformanceStatVerbosity",
    ]
    for key in misc_keys:
        if key in attrs:
            prof.misc[key] = attrs[key]

    return prof


def load_account_profile(path: Path) -> AccountProfile | None:
    try:
        match = parse_attributes_xml(path)
    except Exception:
        return None
    return parse_account_profile(match.raw_attributes)
