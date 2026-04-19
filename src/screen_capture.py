from __future__ import annotations

import hashlib
import ctypes
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Signal

from .config import app_data_dir
from .db import Database


@dataclass(frozen=True)
class HuntWindowState:
    status: str
    hwnd: int | None = None
    title: str = ""
    bounds: dict[str, int] | None = None
    is_foreground: bool = False

    @property
    def is_ready(self) -> bool:
        return self.status == "ready" and self.hwnd is not None and self.bounds is not None


def debug(message: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[HuntLogger capture {ts}] {message}", flush=True)


def find_game_log(install_path: Path, *, verbose: bool = False) -> Path | None:
    variants = [
        install_path / "USER" / "Game.log",
        install_path / "user" / "Game.log",
        install_path / "User" / "Game.log",
    ]
    for path in variants:
        if path.exists():
            if verbose:
                debug(f"Game.log found: {path}")
            return path
    if verbose:
        debug(f"Game.log not found under install path: {install_path}")
    return None


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def inspect_hunt_window() -> HuntWindowState:
    """Return Hunt window status for capture decisions."""
    if sys.platform != "win32":
        return HuntWindowState("unsupported")

    user32 = ctypes.windll.user32
    titles: list[tuple[int, str]] = []

    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def callback(hwnd, lparam) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        title = buff.value.strip()
        if title:
            titles.append((int(hwnd), title))
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)

    candidates = []
    for hwnd, title in titles:
        lower = title.lower()
        if "logger" in lower or "hunt-test" in lower:
            continue
        if "hunt" in lower and ("showdown" in lower or "1896" in lower):
            candidates.append((hwnd, title))
    if not candidates:
        debug("No Hunt window title found")
        return HuntWindowState("missing")

    hwnd, title = candidates[0]
    if user32.IsIconic(hwnd):
        debug(f"Hunt window is minimized and cannot be captured reliably: hwnd={hwnd} title={title}")
        return HuntWindowState("minimized", hwnd=int(hwnd), title=title)

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    rect = RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        debug(f"GetWindowRect failed for Hunt window: hwnd={hwnd} title={title}")
        return HuntWindowState("invalid", hwnd=int(hwnd), title=title)

    width = rect.right - rect.left
    height = rect.bottom - rect.top
    if width <= 0 or height <= 0:
        debug(f"Hunt window has invalid bounds: hwnd={hwnd} title={title} rect={rect.left},{rect.top},{rect.right},{rect.bottom}")
        return HuntWindowState("invalid", hwnd=int(hwnd), title=title)

    bounds = {
        "left": int(rect.left),
        "top": int(rect.top),
        "width": int(width),
        "height": int(height),
    }
    foreground = int(user32.GetForegroundWindow() or 0)
    return HuntWindowState(
        "ready",
        hwnd=int(hwnd),
        title=title,
        bounds=bounds,
        is_foreground=foreground == int(hwnd),
    )


def _find_hunt_window() -> tuple[int, str, dict[str, int]] | None:
    """Return Hunt's HWND, title, and bounds."""
    state = inspect_hunt_window()
    if not state.is_ready:
        return None
    return int(state.hwnd), state.title, dict(state.bounds or {})


def _find_hunt_window_rect() -> dict[str, int] | None:
    """Return Hunt's visible window rect as an mss monitor dict on Windows."""
    state = inspect_hunt_window()
    if not state.is_ready:
        debug("No Hunt window bounds found for region capture")
        return None
    hwnd, title, bounds = int(state.hwnd), state.title, dict(state.bounds or {})
    debug(f"Using Hunt window bounds: title={title!r} hwnd={hwnd} bounds={bounds}")
    return bounds


def describe_window_capture_blocker(state: HuntWindowState) -> str:
    if state.status == "minimized":
        return "Hunt is minimized. Restore the game window now so the summary can be captured."
    if state.status == "missing":
        return "Hunt window was not found. Bring the game back to the foreground."
    if state.status == "invalid":
        return "Hunt window bounds are invalid. Restore the game window and try again."
    if state.status == "unsupported":
        return "Window-targeted capture is only supported on Windows."
    return "Hunt is not currently capturable."


def _image_looks_usable(path: Path) -> bool:
    try:
        from PIL import Image

        with Image.open(path) as image:
            thumb = image.convert("L").resize((32, 32))
            extrema = thumb.getextrema()
            return bool(extrema and extrema[1] - extrema[0] > 4)
    except Exception as exc:
        debug(f"Could not validate captured image {path}: {exc}")
        return False


class PostMatchLogTailer:
    """Small polling tailer that detects new post-match transition lines quickly."""

    def __init__(self) -> None:
        self._path: Path | None = None
        self._pos = 0
        self._last_size = 0
        self._last_trigger_line = ""
        self._last_trigger_at = 0.0

    def reset(self, path: Path | None) -> None:
        self._path = path
        self._pos = 0
        self._last_size = 0
        self._last_trigger_line = ""
        self._last_trigger_at = 0.0
        debug(f"Tailer reset. path={path}")
        if path and path.exists():
            try:
                self._pos = path.stat().st_size
                self._last_size = self._pos
                debug(f"Tailer starting at EOF. size={self._pos}")
            except OSError:
                self._pos = 0
                self._last_size = 0
                debug("Tailer could not stat path during reset; starting at 0")

    def poll(self, path: Path | None) -> str | None:
        if path is None or not path.exists():
            if path != self._path:
                self.reset(path)
            elif path is None:
                debug("Tailer poll skipped: no Game.log path")
            return None
        if path != self._path:
            self.reset(path)
            return None

        try:
            size = path.stat().st_size
        except OSError:
            debug(f"Tailer could not stat Game.log: {path}")
            return None
        if size < self._pos:
            debug(f"Game.log shrank/rotated. old_pos={self._pos} new_size={size}; reading from start")
            self._pos = 0
        if size == self._pos:
            self._last_size = size
            return None

        try:
            with path.open("rb") as f:
                f.seek(self._pos)
                data = f.read()
        except OSError:
            debug(f"Tailer could not read Game.log at pos={self._pos}: {path}")
            return None
        old_pos = self._pos
        self._pos = size
        self._last_size = size
        debug(f"Tailer read {len(data)} bytes from Game.log. pos={old_pos}->{self._pos}")

        text = data.decode("utf-8", errors="replace")
        for line in text.splitlines():
            lower = line.lower()
            is_summary = "postmatchsummary" in lower
            is_contents_dumped = "cmetamissionbag" in lower and "contentsdumped" in lower
            if not (is_summary or is_contents_dumped):
                continue
            now = time.monotonic()
            clean = line.strip()
            debug(f"Post-match candidate line matched: {clean}")
            if clean == self._last_trigger_line and now - self._last_trigger_at < 20:
                debug("Matched line ignored as duplicate trigger inside 20 seconds")
                continue
            self._last_trigger_line = clean
            self._last_trigger_at = now
            if is_summary:
                return clean or "PostMatchSummary"
            return clean or "CMetaMissionBag ContentsDumped"
        return None


class PostMatchCaptureWorker(QThread):
    captured = Signal(int)
    finished_capture = Signal(int)
    error = Signal(str)

    def __init__(
        self,
        db: Database,
        *,
        trigger_event: str,
        frames: int = 12,
        interval_seconds: float = 0.25,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._db = db
        self._trigger_event = trigger_event
        self._frames = frames
        self._interval_seconds = interval_seconds
        self._last_failure_reason = ""

    def run(self) -> None:
        debug(
            f"Capture worker starting. frames={self._frames} interval={self._interval_seconds}s "
            f"trigger={self._trigger_event}"
        )
        debug(f"Capture worker Python executable: {sys.executable}")
        capture_dir = app_data_dir() / "captures" / datetime.now().strftime("%Y%m%d_%H%M%S")
        try:
            capture_dir.mkdir(parents=True, exist_ok=True)
            debug(f"Capture directory ready: {capture_dir}")
        except OSError as exc:
            debug(f"Could not create capture directory: {exc}")
            self.error.emit(f"Could not create capture directory: {exc}")
            return

        saved = self._capture_with_windows_graphics_capture(capture_dir)
        if saved > 0:
            debug(f"Capture worker finished with Windows Graphics Capture. saved={saved}")
            self.finished_capture.emit(saved)
            return

        debug("Windows Graphics Capture did not save usable frames; falling back to mss")
        saved = self._capture_with_mss(capture_dir)
        if saved is None:
            return
        if saved <= 0:
            message = self._last_failure_reason or (
                "Post-match capture did not produce any usable Hunt frames."
            )
            self.error.emit(message)
            return

        debug(f"Capture worker finished with mss. saved={saved}")
        self.finished_capture.emit(saved)

    def _save_capture_row(
        self,
        *,
        path: Path,
        captured_at: datetime,
        width: int,
        height: int,
        backend: str,
        frame_index: int,
        target: dict[str, Any],
    ) -> int | None:
        digest = _sha256_file(path)
        return self._db.save_screenshot_capture(
            captured_at=captured_at,
            trigger_event=self._trigger_event,
            image_path=path,
            sha256=digest,
            width=width,
            height=height,
            monitor=target,
            metadata={
                "frame_index": frame_index,
                "frames_requested": self._frames,
                "capture_backend": backend,
                "target": target,
            },
        )

    def _capture_with_windows_graphics_capture(self, capture_dir: Path) -> int:
        state = inspect_hunt_window()
        if not state.is_ready:
            self._last_failure_reason = describe_window_capture_blocker(state)
            debug("Windows Graphics Capture skipped: Hunt window not found or minimized")
            return 0
        hwnd, title, bounds = int(state.hwnd), state.title, dict(state.bounds or {})
        try:
            from windows_capture import WindowsCapture
        except ImportError as exc:
            debug(f"Windows Graphics Capture unavailable: {exc}")
            self._last_failure_reason = "Window-targeted capture is unavailable because windows-capture is not installed."
            return 0

        debug(f"Starting Windows Graphics Capture for Hunt window: hwnd={hwnd} title={title!r}")
        saved = 0
        last_saved_at = 0.0
        first_error: list[str] = []

        capture = WindowsCapture(
            cursor_capture=False,
            draw_border=False,
            window_hwnd=hwnd,
            minimum_update_interval=max(1, int(self._interval_seconds * 1000)),
        )

        @capture.event
        def on_frame_arrived(frame, capture_control) -> None:
            nonlocal saved, last_saved_at
            now = time.monotonic()
            if saved > 0 and now - last_saved_at < self._interval_seconds:
                return

            captured_at = datetime.now()
            filename = f"postmatch_{captured_at.strftime('%H%M%S_%f')}_{saved:02d}_wgc.png"
            path = capture_dir / filename
            try:
                frame.save_as_image(str(path))
                if saved == 0 and not _image_looks_usable(path):
                    first_error.append("first WGC frame was blank or unusable")
                    self._last_failure_reason = (
                        "Window-targeted capture returned a blank frame. "
                        "If Hunt was minimized or hidden, restore it before the next summary."
                    )
                    capture_control.stop()
                    return
                row_id = self._save_capture_row(
                    path=path,
                    captured_at=captured_at,
                    width=int(frame.width),
                    height=int(frame.height),
                    backend="windows_graphics_capture",
                    frame_index=saved,
                    target={"hwnd": hwnd, "title": title, "bounds": bounds},
                )
            except Exception as exc:
                first_error.append(str(exc))
                self._last_failure_reason = f"Windows Graphics Capture frame save failed: {exc}"
                debug(f"Windows Graphics Capture frame save failed: {exc}")
                capture_control.stop()
                return

            if row_id is not None:
                saved += 1
                last_saved_at = now
                self.captured.emit(row_id)
                debug(f"Saved WGC screenshot frame {saved}/{self._frames}: {path}")
            else:
                debug(f"WGC screenshot frame was duplicate in DB: {path}")

            if saved >= self._frames:
                capture_control.stop()

        @capture.event
        def on_closed() -> None:
            debug("Windows Graphics Capture session closed")

        try:
            control = capture.start_free_threaded()
            deadline = time.monotonic() + max(5.0, self._frames * self._interval_seconds + 5.0)
            while not control.is_finished() and time.monotonic() < deadline:
                time.sleep(0.05)
            if not control.is_finished():
                debug("Windows Graphics Capture timed out; stopping capture")
                control.stop()
            control.wait()
        except Exception as exc:
            debug(f"Windows Graphics Capture failed: {exc}")
            self._last_failure_reason = f"Windows Graphics Capture failed: {exc}"
            return 0

        if first_error:
            debug(f"Windows Graphics Capture stopped early: {first_error[0]}")
        return saved

    def _capture_with_mss(self, capture_dir: Path) -> int | None:
        try:
            import mss
            import mss.tools
            debug(f"mss import ok. version={getattr(mss, '__version__', 'unknown')}")
        except ImportError:
            debug("Capture worker failed: mss is not installed")
            debug(f"sys.path={sys.path}")
            self.error.emit("Screenshot capture requires mss. Run: python -m pip install -r requirements.txt")
            return None

        state = inspect_hunt_window()
        if not state.is_ready:
            self._last_failure_reason = (
                describe_window_capture_blocker(state)
                + " Desktop fallback is disabled to avoid saving the wrong screen."
            )
            debug(f"mss capture skipped: {self._last_failure_reason}")
            return 0
        if not state.is_foreground:
            self._last_failure_reason = (
                "Hunt is not the foreground window. Desktop fallback is disabled unless the game is visible."
            )
            debug(f"mss capture skipped: {self._last_failure_reason}")
            return 0

        saved = 0
        try:
            with mss.mss() as sct:
                monitor = dict(state.bounds or {})
                monitor["mon"] = 0
                debug(f"Capture bounds: {monitor}")
                for idx in range(self._frames):
                    captured_at = datetime.now()
                    shot = sct.grab(monitor)
                    filename = f"postmatch_{captured_at.strftime('%H%M%S_%f')}_{idx:02d}.png"
                    path = capture_dir / filename
                    mss.tools.to_png(shot.rgb, shot.size, output=str(path))
                    row_id = self._save_capture_row(
                        path=path,
                        captured_at=captured_at,
                        width=shot.width,
                        height=shot.height,
                        backend="mss",
                        frame_index=idx,
                        target=monitor,
                    )
                    if row_id is not None:
                        saved += 1
                        self.captured.emit(row_id)
                        debug(f"Saved screenshot frame {idx + 1}/{self._frames}: {path}")
                    else:
                        debug(f"Screenshot frame {idx + 1}/{self._frames} was duplicate in DB: {path}")
                    if idx + 1 < self._frames:
                        time.sleep(self._interval_seconds)
        except Exception as exc:
            debug(f"Screenshot capture failed: {exc}")
            self.error.emit(f"Screenshot capture failed: {exc}")
            return None
        return saved
