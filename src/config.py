from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


def app_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.local/share")
    path = Path(base) / "HuntLogger"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class AppConfig:
    install_path: str = ""
    auto_watch: bool = True
    screenshot_capture_enabled: bool = True
    last_selected_match_id: int | None = None
    window_geometry: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def attributes_path(self) -> Path | None:
        if not self.install_path:
            return None
        return find_attributes_xml(Path(self.install_path))

    def is_valid_install(self) -> bool:
        p = self.attributes_path
        return p is not None and p.exists()


def config_file() -> Path:
    return app_data_dir() / "config.json"


def load_config() -> AppConfig:
    path = config_file()
    if not path.exists():
        return AppConfig()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return AppConfig()
    return AppConfig(
        install_path=data.get("install_path", ""),
        auto_watch=data.get("auto_watch", True),
        screenshot_capture_enabled=data.get("screenshot_capture_enabled", True),
        last_selected_match_id=data.get("last_selected_match_id"),
        window_geometry=data.get("window_geometry", ""),
        extra=data.get("extra", {}),
    )


def save_config(cfg: AppConfig) -> None:
    path = config_file()
    path.write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")


_FOLDER_NAMES = ["Hunt Showdown 1896", "Hunt Showdown"]
_DRIVES = ["C", "D", "E", "F", "G"]
_STEAM_SUBDIRS = [
    "Program Files/Steam/steamapps/common",
    "Program Files (x86)/Steam/steamapps/common",
    "SteamLibrary/steamapps/common",
    "Steam/steamapps/common",
]


def find_attributes_xml(install: Path) -> Path | None:
    """Return the attributes.xml under *install*, tolerating any sub-path casing."""
    if not install or not install.is_dir():
        return None
    sub_variants = [
        ("USER", "Profiles", "default", "attributes.xml"),
        ("user", "profiles", "default", "attributes.xml"),
        ("User", "Profiles", "Default", "attributes.xml"),
    ]
    for parts in sub_variants:
        p = install.joinpath(*parts)
        if p.exists():
            return p
    # Return the canonical expected path so the UI can show it as the watch target.
    return install / "user" / "profiles" / "default" / "attributes.xml"


def guess_install_paths() -> list[Path]:
    candidates: list[Path] = []
    for drive in _DRIVES:
        for subdir in _STEAM_SUBDIRS:
            base = Path(f"{drive}:/{subdir}")
            for name in _FOLDER_NAMES:
                candidates.append(base / name)
    found: list[Path] = []
    for p in candidates:
        attrs = find_attributes_xml(p)
        if attrs is not None and attrs.exists():
            found.append(p)
    return found
