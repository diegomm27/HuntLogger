from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re
import shutil
from typing import Any

from .config import app_data_dir
from .db import Database, ScreenshotCapture
from .screen_capture import debug


@dataclass
class VisionDebugResult:
    processed: int = 0
    crops: int = 0
    failed: int = 0
    complete_groups: int = 0
    deleted_files: int = 0
    message: str = ""


# Normalized crop boxes: x, y, width, height. Coordinates are relative to the
# Hunt viewport, not the full desktop. If a dual-monitor screenshot is captured,
# the parser first isolates the left 16:9 game viewport.
POSTMATCH_REGIONS: dict[str, tuple[float, float, float, float]] = {
    "bounty_obtained_value": (0.240, 0.195, 0.055, 0.070),
    "hunters_killed_value": (0.240, 0.288, 0.055, 0.075),
    "monsters_killed_value": (0.445, 0.195, 0.055, 0.070),
    "bounty_token_value": (0.445, 0.288, 0.055, 0.075),
    "hunter_status": (0.190, 0.410, 0.205, 0.155),
    "hunter_death_penalty": (0.205, 0.525, 0.175, 0.040),
    "bloodline_level": (0.340, 0.625, 0.045, 0.055),
    "bloodline_progress": (0.390, 0.670, 0.100, 0.045),
    "bloodline_xp": (0.175, 0.735, 0.060, 0.075),
    "hunt_dollars": (0.350, 0.735, 0.065, 0.075),
    "event_reward": (0.425, 0.735, 0.065, 0.075),
    "next_unlock": (0.555, 0.660, 0.075, 0.085),
}

NUMERIC_FIELDS = {
    "bounty_obtained_value",
    "hunters_killed_value",
    "monsters_killed_value",
    "bounty_token_value",
    "bloodline_level",
    "bloodline_progress",
    "bloodline_xp",
    "hunt_dollars",
    "event_reward",
    "next_unlock",
}

SIGNED_SMALL_FIELDS = {
    "bounty_obtained_value",
    "hunters_killed_value",
    "monsters_killed_value",
    "bounty_token_value",
}

COMPLETE_MATCH_FIELDS = {
    "bounty_obtained_value",
    "hunters_killed_value",
    "monsters_killed_value",
    "bounty_token_value",
    "hunter_status",
    "bloodline_xp",
}


def _crop_box(width: int, height: int, region: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    x, y, w, h = region
    return (
        max(0, int(width * x)),
        max(0, int(height * y)),
        min(width, int(width * (x + w))),
        min(height, int(height * (y + h))),
    )


def _hunt_viewport_box(width: int, height: int) -> tuple[int, int, int, int]:
    expected_width = int(round(height * 16 / 9))
    if width > expected_width * 1.25:
        return (0, 0, min(width, expected_width), height)
    return (0, 0, width, height)


def _debug_crop_dir(capture: ScreenshotCapture) -> Path:
    base = Path(capture.image_path).parent
    path = base / "vision_debug" / f"capture_{capture.id}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _is_inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _group_has_complete_match_data(db: Database, group_path: Path) -> bool:
    detail = db.get_visual_match_detail(str(group_path))
    if not detail:
        return False
    fields = detail.get("parsed_fields", {})
    for name in COMPLETE_MATCH_FIELDS:
        value = str(fields.get(name, "")).strip()
        if not value or value == "?":
            return False
    return True


def _delete_completed_group_files(captures: list[ScreenshotCapture]) -> int:
    if not captures:
        return 0
    captures_root = app_data_dir() / "captures"
    group = Path(captures[0].image_path).parent
    if not _is_inside(group, captures_root):
        debug(f"Skipping screenshot cleanup outside capture root: {group}")
        return 0

    deleted = 0
    for capture in captures:
        path = Path(capture.image_path)
        if not _is_inside(path, captures_root):
            debug(f"Skipping screenshot cleanup outside capture root: {path}")
            continue
        try:
            if path.exists() and path.is_file():
                path.unlink()
                deleted += 1
        except OSError as exc:
            debug(f"Could not delete completed screenshot {path}: {exc}")

    debug_dir = group / "vision_debug"
    if _is_inside(debug_dir, captures_root) and debug_dir.exists():
        try:
            deleted += sum(1 for child in debug_dir.rglob("*") if child.is_file())
            shutil.rmtree(debug_dir)
        except OSError as exc:
            debug(f"Could not delete vision debug files for {group}: {exc}")

    try:
        if group.exists() and not any(group.iterdir()):
            group.rmdir()
    except OSError as exc:
        debug(f"Could not remove empty capture directory {group}: {exc}")

    return deleted


def _cleanup_completed_groups(
    db: Database,
    groups: dict[Path, list[ScreenshotCapture]],
) -> tuple[int, int]:
    complete_groups = 0
    deleted_files = 0
    for group_path, captures in groups.items():
        if not _group_has_complete_match_data(db, group_path):
            continue
        deleted = _delete_completed_group_files(captures)
        if deleted:
            complete_groups += 1
            deleted_files += deleted
    return complete_groups, deleted_files


_TEMPLATE_CACHE: list[tuple[str, Any]] | None = None


def _font_paths() -> list[str]:
    candidates = [
        r"C:\Windows\Fonts\georgiab.ttf",
        r"C:\Windows\Fonts\georgia.ttf",
        r"C:\Windows\Fonts\timesbd.ttf",
        r"C:\Windows\Fonts\times.ttf",
        r"C:\Windows\Fonts\cambriab.ttf",
    ]
    return [path for path in candidates if os.path.exists(path)]


def _binary_text_mask(image: Any, *, threshold: int = 118) -> Any:
    from PIL import Image

    rgb = image.convert("RGB")
    width, height = rgb.size
    mask = Image.new("1", (width, height), 0)
    src = rgb.load()
    dst = mask.load()
    for y in range(height):
        for x in range(width):
            r, g, b = src[x, y]
            bright = (r + g + b) / 3
            spread = max(r, g, b) - min(r, g, b)
            is_white = bright >= threshold and spread < 95
            is_gold = r >= 135 and g >= 105 and b >= 55 and bright >= threshold - 18
            if is_white or is_gold:
                dst[x, y] = 1
    return mask


def _component_boxes(mask: Any) -> list[tuple[int, int, int, int, int]]:
    width, height = mask.size
    pixels = mask.load()
    seen: set[tuple[int, int]] = set()
    boxes: list[tuple[int, int, int, int, int]] = []

    for y in range(height):
        for x in range(width):
            if not pixels[x, y] or (x, y) in seen:
                continue
            stack = [(x, y)]
            seen.add((x, y))
            xs: list[int] = []
            ys: list[int] = []
            while stack:
                cx, cy = stack.pop()
                xs.append(cx)
                ys.append(cy)
                for nx in (cx - 1, cx, cx + 1):
                    for ny in (cy - 1, cy, cy + 1):
                        if (
                            0 <= nx < width
                            and 0 <= ny < height
                            and (nx, ny) not in seen
                            and pixels[nx, ny]
                        ):
                            seen.add((nx, ny))
                            stack.append((nx, ny))
            area = len(xs)
            if area >= 4:
                boxes.append((min(xs), min(ys), max(xs) + 1, max(ys) + 1, area))
    return sorted(boxes, key=lambda b: (b[0], b[1]))


def _normalize_glyph(mask: Any, size: tuple[int, int] = (24, 32)) -> Any:
    from PIL import Image

    bbox = mask.getbbox()
    if not bbox:
        return Image.new("1", size, 0)
    glyph = mask.crop(bbox).convert("L")
    glyph.thumbnail((size[0] - 4, size[1] - 4), Image.Resampling.NEAREST)
    out = Image.new("L", size, 0)
    out.paste(glyph, ((size[0] - glyph.width) // 2, (size[1] - glyph.height) // 2))
    return out.point(lambda value: 255 if value > 50 else 0).convert("1")


def _glyph_templates() -> list[tuple[str, Any]]:
    global _TEMPLATE_CACHE
    if _TEMPLATE_CACHE is not None:
        return _TEMPLATE_CACHE

    from PIL import Image, ImageDraw, ImageFont

    templates: list[tuple[str, Any]] = []
    chars = "+0123456789/"
    for font_path in _font_paths():
        for size in range(10, 36):
            font = ImageFont.truetype(font_path, size)
            for ch in chars:
                img = Image.new("L", (80, 80), 0)
                ImageDraw.Draw(img).text((10, 5), ch, font=font, fill=255)
                binary = img.point(lambda value: 255 if value > 30 else 0).convert("1")
                templates.append((ch, _normalize_glyph(binary)))
    _TEMPLATE_CACHE = templates
    return templates


def _match_score(a: Any, b: Any) -> float:
    a_pixels = a.load()
    b_pixels = b.load()
    intersect = 0
    union = 0
    for y in range(a.height):
        for x in range(a.width):
            av = bool(a_pixels[x, y])
            bv = bool(b_pixels[x, y])
            if av or bv:
                union += 1
            if av and bv:
                intersect += 1
    return intersect / union if union else 0.0


def _classify_component(
    mask: Any,
    box: tuple[int, int, int, int, int],
    *,
    allowed_chars: set[str] | None = None,
) -> tuple[str, float]:
    x1, y1, x2, y2, area = box
    width = x2 - x1
    height = y2 - y1
    if (allowed_chars is None or "+" in allowed_chars) and 5 <= width <= 10 and height <= 9 and area <= 35:
        return "+", 0.86
    if width <= 3 and height >= 8:
        return "1", 0.80
    if width <= 4 and height >= 8 and area <= 18:
        pixels = mask.load()
        top: list[int] = []
        bottom: list[int] = []
        midpoint = y1 + height // 2
        for y in range(y1, y2):
            for x in range(x1, x2):
                if pixels[x, y]:
                    (top if y < midpoint else bottom).append(x)
        if top and bottom and abs((sum(bottom) / len(bottom)) - (sum(top) / len(top))) > 0.75:
            return "/", 0.78
    if width <= 5 and height >= 11:
        return "1", 0.78

    glyph = _normalize_glyph(mask.crop((x1, y1, x2, y2)))
    best_char = ""
    best_score = 0.0
    for ch, template in _glyph_templates():
        if allowed_chars is not None and ch not in allowed_chars:
            continue
        score = _match_score(glyph, template)
        if score > best_score:
            best_char = ch
            best_score = score
    return best_char, best_score


def _read_numeric_crop(crop: Any, field_name: str) -> tuple[str, float]:
    threshold = 72 if field_name == "bloodline_progress" else 118
    mask = _binary_text_mask(crop, threshold=threshold)
    boxes = []
    crop_width, crop_height = crop.size
    for box in _component_boxes(mask):
        x1, y1, x2, y2, area = box
        width = x2 - x1
        height = y2 - y1
        if area < 8 or height < 4:
            continue
        if width > crop_width * 0.30 and height > crop_height * 0.45:
            continue
        if y2 < 3 or y1 > crop_height - 3:
            continue
        boxes.append(box)

    if field_name in SIGNED_SMALL_FIELDS and len(boxes) > 4:
        return "", 0.0
    if field_name not in {"bloodline_progress", "hunter_status"} and len(boxes) > 8:
        return "", 0.0

    chars: list[str] = []
    scores: list[float] = []
    allowed_chars = set("0123456789/") if field_name == "bloodline_progress" else None
    for box in boxes:
        ch, score = _classify_component(mask, box, allowed_chars=allowed_chars)
        if not ch or score < 0.35:
            continue
        chars.append(ch)
        scores.append(score)

    text = "".join(chars)
    plus_index = text.find("+")
    if plus_index > 0:
        text = text[plus_index:]
    text = re.sub(r"^\++", "+", text)
    text = re.sub(r"[^+0-9/]", "", text)
    text = _sanitize_field_text(field_name, text)
    if text in {"", "+", "/"}:
        return "", 0.0
    return text, sum(scores) / len(scores) if scores else 0.0


def _sanitize_field_text(field_name: str, text: str) -> str:
    text = text.strip()
    if field_name in SIGNED_SMALL_FIELDS:
        match = re.search(r"\+\d{1,2}", text)
        return match.group(0) if match else ""
    if field_name == "bloodline_level":
        match = re.search(r"\d{1,3}", text)
        return match.group(0) if match else ""
    if field_name == "bloodline_progress":
        match = re.search(r"\d{1,5}/25000", text)
        return match.group(0) if match else ""
    if field_name in {"bloodline_xp", "hunt_dollars", "event_reward"}:
        match = re.search(r"\+\d{1,5}", text)
        return match.group(0) if match else ""
    if field_name == "next_unlock":
        match = re.search(r"\d{1,5}", text)
        return match.group(0) if match else ""
    return text


def _numeric_value(text: str) -> float | None:
    if not text:
        return None
    match = re.search(r"[+-]?\d+", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _read_hunter_status(viewport: Any) -> tuple[str, float]:
    width, height = viewport.size
    penalty_box = _crop_box(width, height, POSTMATCH_REGIONS["hunter_death_penalty"])
    crop = viewport.crop(penalty_box)
    mask = _binary_text_mask(crop, threshold=96)
    light_pixels = sum(box[4] for box in _component_boxes(mask))
    density = light_pixels / max(1, crop.width * crop.height)
    if density > 0.015:
        return "dead", min(0.95, density * 25)
    return "unknown", 0.15


def create_vision_debug_crops(capture: ScreenshotCapture) -> list[dict[str, Any]]:
    from PIL import Image, ImageOps

    image_path = Path(capture.image_path)
    if not image_path.exists():
        raise RuntimeError(f"Screenshot file not found: {image_path}")

    image = Image.open(image_path)
    full_width, full_height = image.size
    viewport_box = _hunt_viewport_box(full_width, full_height)
    viewport = image.crop(viewport_box)
    width, height = viewport.size
    crop_dir = _debug_crop_dir(capture)
    fields: list[dict[str, Any]] = []

    for name, region in POSTMATCH_REGIONS.items():
        if name == "hunter_death_penalty":
            continue
        box = _crop_box(width, height, region)
        crop = viewport.crop(box)
        crop_path = crop_dir / f"{name}.png"
        crop.save(crop_path)

        # Also save a contrast-enhanced version for future template work.
        processed = ImageOps.autocontrast(ImageOps.grayscale(crop))
        processed_path = crop_dir / f"{name}_processed.png"
        processed.save(processed_path)

        value_text = ""
        value_num = None
        confidence: str | float = "debug"
        method = "fixed_region_crop"
        if name in NUMERIC_FIELDS:
            value_text, numeric_confidence = _read_numeric_crop(crop, name)
            value_num = _numeric_value(value_text)
            confidence = f"{numeric_confidence:.2f}" if value_text else "empty"
            method = "fixed_region_digit_template"
        elif name == "hunter_status":
            value_text, status_confidence = _read_hunter_status(viewport)
            confidence = f"{status_confidence:.2f}"
            method = "fixed_region_status_density"

        fields.append(
            {
                "field_name": name,
                "value_text": value_text,
                "value_num": value_num,
                "confidence": str(confidence),
                "region_name": name,
                "method": method,
                "crop_path": str(crop_path),
                "metadata": {
                    "source_image": str(image_path),
                    "processed_crop_path": str(processed_path),
                    "normalized_region": region,
                    "pixel_box": box,
                    "source_size": [full_width, full_height],
                    "viewport_box": viewport_box,
                    "viewport_size": [width, height],
                },
            }
        )

    return fields


def process_recent_captures_for_vision_debug(
    db: Database,
    *,
    limit: int = 20,
    sample_per_group: int | None = 10,
    cleanup_complete: bool = True,
) -> VisionDebugResult:
    captures = db.list_recent_screenshot_captures(limit=limit)
    if not captures:
        return VisionDebugResult(message="No screenshot captures found.")

    grouped: dict[Path, list[ScreenshotCapture]] = {}
    for capture in captures:
        grouped.setdefault(Path(capture.image_path).parent, []).append(capture)
    selected: list[ScreenshotCapture] = []
    for group_path, group_captures in grouped.items():
        if _group_has_complete_match_data(db, group_path):
            continue

        existing_captures = [
            capture for capture in group_captures
            if Path(capture.image_path).exists()
        ]
        existing_captures.sort(key=lambda item: item.captured_at)
        n = len(existing_captures)
        if sample_per_group is None or n <= sample_per_group:
            selected.extend(existing_captures)
        else:
            # Sample frames evenly across the session so the parser sees
            # frames from the middle/end where the postmatch UI has settled,
            # not just the first few frames during the opening animation.
            step = n / sample_per_group
            indices = sorted({int(i * step) for i in range(sample_per_group)})
            selected.extend(existing_captures[i] for i in indices)
    selected.sort(key=lambda item: item.captured_at, reverse=True)

    result = VisionDebugResult()
    for capture in selected:
        try:
            debug(f"Vision debug crop processing screenshot id={capture.id} path={capture.image_path}")
            fields = create_vision_debug_crops(capture)
            result.crops += db.save_vision_fields(
                screenshot_capture_id=capture.id,
                fields=fields,
            )
            result.processed += 1
        except Exception as exc:
            result.failed += 1
            debug(f"Vision debug failed for screenshot id={capture.id}: {exc}")

    if cleanup_complete:
        result.complete_groups, result.deleted_files = _cleanup_completed_groups(db, grouped)

    result.message = (
        f"Parsed {result.processed} screenshots, saved {result.crops} field records, "
        f"deleted {result.deleted_files} files from {result.complete_groups} complete matches, "
        f"failed {result.failed}."
    )
    return result
