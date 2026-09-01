"""Interactive video frame picker with side-panel controls and bowler name entry."""
from __future__ import annotations

import re
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from turkey_club.config import VenueCalibration

MONOSPACE_FONT_PATH = "C:/Windows/Fonts/consola.ttf"

WINDOW_NAME = "turkey-club frame picker"

ZONE_COLORS: dict[str, tuple[int, int, int]] = {
    "approach": (0, 255, 255),
    "lane":     (0, 165, 255),
    "pin":      (0, 255, 0),
}

BG_COLOR = (30, 30, 30)
PANEL_BG = (45, 45, 45)
TEXT_COLOR = (220, 220, 220)
DIM_COLOR = (140, 140, 140)
ACCENT_COLOR = (0, 200, 255)
INPUT_BG = (60, 60, 60)
INPUT_ACTIVE_BORDER = (0, 200, 255)
INPUT_INACTIVE_BORDER = (80, 80, 80)

PANEL_RATIO = 0.25
PANEL_MIN_PX = 300

FIELD_NAME = 0
FIELD_FRAME = 1
FIELD_TIME = 2
FIELD_COUNT = 3

KEY_ESCAPE = 27
KEY_ENTER = 13
KEY_BACKSPACE = 8
KEY_TAB = 9
KEY_LEFT = 2424832
KEY_RIGHT = 2555904
KEY_PAGE_UP = 2162688
KEY_PAGE_DOWN = 2228224
KEY_HOME = 2359296
KEY_END = 2293760
KEY_DELETE = 3014656


def _parse_time_to_seconds(text: str) -> float | None:
    """Parse a time string to seconds.

    Accepted formats: ``90`` (seconds), ``1:30`` (min:sec), ``1:30.5`` (min:sec.frac).
    """
    text = text.strip()
    if not text:
        return None
    match = re.fullmatch(r"(\d+):(\d{1,2}(?:\.\d+)?)", text)
    if match:
        minutes = int(match.group(1))
        seconds = float(match.group(2))
        return minutes * 60.0 + seconds
    try:
        return float(text)
    except ValueError:
        return None


def pick_reference_frame(
    video_path: Path,
    venue: VenueCalibration,
    initial_name: str = "",
    initial_frame: int = 0,
) -> tuple[int, str] | None:
    """Open an interactive viewer to select a reference frame and enter a bowler name.

    Returns ``(frame_number, bowler_name)`` or ``None`` if the user canceled.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    video_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    video_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    current_frame = max(0, min(initial_frame, total_frames - 1))
    bowler_name = initial_name
    frame_input = ""
    time_input = ""
    active_field = FIELD_NAME
    cursor_visible = True
    last_cursor_toggle = time.monotonic()

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)

    initial_canvas_w = 1600
    initial_canvas_h = 900
    cv2.resizeWindow(WINDOW_NAME, initial_canvas_w, initial_canvas_h)

    def on_trackbar(pos: int) -> None:
        nonlocal current_frame
        current_frame = pos

    cv2.createTrackbar("Frame", WINDOW_NAME, 0, max(total_frames - 1, 0), on_trackbar)

    selected = False

    while True:
        canvas_w, canvas_h = _get_window_size(initial_canvas_w, initial_canvas_h)

        cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame)
        ret, frame = cap.read()
        if not ret:
            current_frame = min(current_frame, total_frames - 1)
            continue

        now = time.monotonic()
        if now - last_cursor_toggle > 0.5:
            cursor_visible = not cursor_visible
            last_cursor_toggle = now

        canvas = _compose_canvas(
            frame, venue, canvas_w, canvas_h, video_w, video_h,
            current_frame, total_frames, fps,
            bowler_name, frame_input, time_input,
            active_field, cursor_visible,
        )

        cv2.imshow(WINDOW_NAME, canvas)
        cv2.setTrackbarPos("Frame", WINDOW_NAME, current_frame)

        key = cv2.waitKeyEx(30)

        if key == KEY_ESCAPE:
            break
        elif key == KEY_TAB:
            active_field = (active_field + 1) % FIELD_COUNT
            cursor_visible = True
            last_cursor_toggle = now
        elif key == KEY_ENTER:
            if active_field == FIELD_FRAME:
                target = _parse_frame_number(frame_input, total_frames)
                if target is not None:
                    current_frame = target
                    frame_input = ""
            elif active_field == FIELD_TIME:
                seconds = _parse_time_to_seconds(time_input)
                if seconds is not None:
                    target = int(seconds * fps)
                    current_frame = max(0, min(target, total_frames - 1))
                    time_input = ""
            elif active_field == FIELD_NAME:
                if bowler_name.strip():
                    selected = True
                    break
        elif key == KEY_RIGHT:
            if active_field == FIELD_NAME:
                current_frame = min(current_frame + 1, total_frames - 1)
            # arrow keys don't navigate in frame/time text fields
        elif key == KEY_LEFT:
            if active_field == FIELD_NAME:
                current_frame = max(current_frame - 1, 0)
        elif key == KEY_PAGE_UP:
            current_frame = min(current_frame + int(fps), total_frames - 1)
        elif key == KEY_PAGE_DOWN:
            current_frame = max(current_frame - int(fps), 0)
        elif key == KEY_HOME:
            current_frame = 0
        elif key == KEY_END:
            current_frame = total_frames - 1
        elif key == KEY_BACKSPACE:
            if active_field == FIELD_NAME:
                bowler_name = bowler_name[:-1]
            elif active_field == FIELD_FRAME:
                frame_input = frame_input[:-1]
            elif active_field == FIELD_TIME:
                time_input = time_input[:-1]
            cursor_visible = True
            last_cursor_toggle = now
        elif key == KEY_DELETE:
            if active_field == FIELD_NAME:
                bowler_name = ""
            elif active_field == FIELD_FRAME:
                frame_input = ""
            elif active_field == FIELD_TIME:
                time_input = ""
            cursor_visible = True
            last_cursor_toggle = now
        elif 32 <= key <= 126:
            ch = chr(key)
            if active_field == FIELD_NAME:
                bowler_name += ch
            elif active_field == FIELD_FRAME:
                if ch.isdigit():
                    frame_input += ch
            elif active_field == FIELD_TIME:
                if ch.isdigit() or ch in (":", "."):
                    time_input += ch
            cursor_visible = True
            last_cursor_toggle = now

    cap.release()
    cv2.destroyWindow(WINDOW_NAME)
    return (current_frame, bowler_name) if selected else None


_FIELD_VF_FRAME = 0
_FIELD_VF_TIME = 1
_FIELD_VF_COUNT = 2


def pick_video_frame(video_path: Path, initial_frame: int = 0) -> int | None:
    """Open an interactive viewer to select a video frame.

    Simplified variant of ``pick_reference_frame`` without venue overlays or
    bowler name input.  Returns the selected frame number, or ``None`` if the
    user canceled.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    video_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    video_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    current_frame = max(0, min(initial_frame, total_frames - 1))
    frame_input = ""
    time_input = ""
    active_field = _FIELD_VF_FRAME
    cursor_visible = True
    last_cursor_toggle = time.monotonic()

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)

    initial_canvas_w = 1600
    initial_canvas_h = 900
    cv2.resizeWindow(WINDOW_NAME, initial_canvas_w, initial_canvas_h)

    def on_trackbar(pos: int) -> None:
        nonlocal current_frame
        current_frame = pos

    cv2.createTrackbar("Frame", WINDOW_NAME, current_frame, max(total_frames - 1, 0), on_trackbar)

    selected = False

    while True:
        canvas_w, canvas_h = _get_window_size(initial_canvas_w, initial_canvas_h)

        cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame)
        ret, frame = cap.read()
        if not ret:
            current_frame = min(current_frame, total_frames - 1)
            continue

        now = time.monotonic()
        if now - last_cursor_toggle > 0.5:
            cursor_visible = not cursor_visible
            last_cursor_toggle = now

        canvas = _compose_canvas_simple(
            frame, canvas_w, canvas_h, video_w, video_h,
            current_frame, total_frames, fps,
            frame_input, time_input,
            active_field, cursor_visible,
        )

        cv2.imshow(WINDOW_NAME, canvas)
        cv2.setTrackbarPos("Frame", WINDOW_NAME, current_frame)

        key = cv2.waitKeyEx(30)

        if key == KEY_ESCAPE:
            break
        elif key == KEY_TAB:
            active_field = (active_field + 1) % _FIELD_VF_COUNT
            cursor_visible = True
            last_cursor_toggle = now
        elif key == KEY_ENTER:
            if active_field == _FIELD_VF_FRAME and frame_input.strip():
                target = _parse_frame_number(frame_input, total_frames)
                if target is not None:
                    current_frame = target
                    frame_input = ""
            elif active_field == _FIELD_VF_TIME and time_input.strip():
                seconds = _parse_time_to_seconds(time_input)
                if seconds is not None:
                    target = int(seconds * fps)
                    current_frame = max(0, min(target, total_frames - 1))
                    time_input = ""
            else:
                selected = True
                break
        elif key == KEY_RIGHT:
            current_frame = min(current_frame + 1, total_frames - 1)
        elif key == KEY_LEFT:
            current_frame = max(current_frame - 1, 0)
        elif key == KEY_PAGE_UP:
            current_frame = min(current_frame + int(fps), total_frames - 1)
        elif key == KEY_PAGE_DOWN:
            current_frame = max(current_frame - int(fps), 0)
        elif key == KEY_HOME:
            current_frame = 0
        elif key == KEY_END:
            current_frame = total_frames - 1
        elif key == KEY_BACKSPACE:
            if active_field == _FIELD_VF_FRAME:
                frame_input = frame_input[:-1]
            elif active_field == _FIELD_VF_TIME:
                time_input = time_input[:-1]
            cursor_visible = True
            last_cursor_toggle = now
        elif key == KEY_DELETE:
            if active_field == _FIELD_VF_FRAME:
                frame_input = ""
            elif active_field == _FIELD_VF_TIME:
                time_input = ""
            cursor_visible = True
            last_cursor_toggle = now
        elif 32 <= key <= 126:
            ch = chr(key)
            if active_field == _FIELD_VF_FRAME:
                if ch.isdigit():
                    frame_input += ch
            elif active_field == _FIELD_VF_TIME:
                if ch.isdigit() or ch in (":", "."):
                    time_input += ch
            cursor_visible = True
            last_cursor_toggle = now

    cap.release()
    cv2.destroyWindow(WINDOW_NAME)
    return current_frame if selected else None


def _parse_frame_number(text: str, total_frames: int) -> int | None:
    text = text.strip()
    if not text:
        return None
    try:
        n = int(text)
        return max(0, min(n, total_frames - 1))
    except ValueError:
        return None


def _get_window_size(fallback_w: int, fallback_h: int) -> tuple[int, int]:
    try:
        rect = cv2.getWindowImageRect(WINDOW_NAME)
        w, h = rect[2], rect[3]
        if w > 0 and h > 0:
            return w, h
    except cv2.error:
        pass
    return fallback_w, fallback_h


def _compose_canvas(
    frame: np.ndarray,
    venue: VenueCalibration,
    canvas_w: int,
    canvas_h: int,
    video_w: int,
    video_h: int,
    current_frame: int,
    total_frames: int,
    fps: float,
    bowler_name: str,
    frame_input: str,
    time_input: str,
    active_field: int,
    cursor_visible: bool,
) -> np.ndarray:
    canvas = np.full((canvas_h, canvas_w, 3), BG_COLOR, dtype=np.uint8)

    panel_w = max(PANEL_MIN_PX, int(canvas_w * PANEL_RATIO))
    view_w = canvas_w - panel_w
    view_h = canvas_h

    scale = min(view_w / max(video_w, 1), view_h / max(video_h, 1))
    scaled_w = int(video_w * scale)
    scaled_h = int(video_h * scale)

    x_off = (view_w - scaled_w) // 2
    y_off = (view_h - scaled_h) // 2

    display = frame.copy()
    _draw_zones(display, venue)
    scaled = cv2.resize(display, (scaled_w, scaled_h), interpolation=cv2.INTER_AREA)
    canvas[y_off:y_off + scaled_h, x_off:x_off + scaled_w] = scaled

    panel_x = view_w
    cv2.rectangle(canvas, (panel_x, 0), (canvas_w, canvas_h), PANEL_BG, -1)
    cv2.line(canvas, (panel_x, 0), (panel_x, canvas_h), (70, 70, 70), 1)

    _draw_panel(canvas, panel_x, panel_w, canvas_h,
                current_frame, total_frames, fps,
                bowler_name, frame_input, time_input,
                active_field, cursor_visible)

    return canvas


def _compose_canvas_simple(
    frame: np.ndarray,
    canvas_w: int,
    canvas_h: int,
    video_w: int,
    video_h: int,
    current_frame: int,
    total_frames: int,
    fps: float,
    frame_input: str,
    time_input: str,
    active_field: int,
    cursor_visible: bool,
) -> np.ndarray:
    canvas = np.full((canvas_h, canvas_w, 3), BG_COLOR, dtype=np.uint8)

    panel_w = max(PANEL_MIN_PX, int(canvas_w * PANEL_RATIO))
    view_w = canvas_w - panel_w
    view_h = canvas_h

    scale = min(view_w / max(video_w, 1), view_h / max(video_h, 1))
    scaled_w = int(video_w * scale)
    scaled_h = int(video_h * scale)

    x_off = (view_w - scaled_w) // 2
    y_off = (view_h - scaled_h) // 2

    scaled = cv2.resize(frame, (scaled_w, scaled_h), interpolation=cv2.INTER_AREA)
    canvas[y_off:y_off + scaled_h, x_off:x_off + scaled_w] = scaled

    panel_x = view_w
    cv2.rectangle(canvas, (panel_x, 0), (canvas_w, canvas_h), PANEL_BG, -1)
    cv2.line(canvas, (panel_x, 0), (panel_x, canvas_h), (70, 70, 70), 1)

    _draw_panel_simple(canvas, panel_x, panel_w, canvas_h,
                       current_frame, total_frames, fps,
                       frame_input, time_input,
                       active_field, cursor_visible)

    return canvas


def _draw_panel_simple(
    canvas: np.ndarray,
    panel_x: int,
    panel_w: int,
    panel_h: int,
    current_frame: int,
    total_frames: int,
    fps: float,
    frame_input: str,
    time_input: str,
    active_field: int,
    cursor_visible: bool,
) -> None:
    margin = 20
    x = panel_x + margin
    x2 = panel_x + panel_w - margin
    y = 40

    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = _fit_font_scale(panel_w - margin * 2, panel_w)
    line_h = int(30 * font_scale / 0.55)
    small_scale = font_scale * 0.75

    _put_text(canvas, "FRAME PICKER", x, y, font, font_scale, ACCENT_COLOR, 2)
    y += line_h + 10

    cv2.line(canvas, (x, y), (x2, y), (70, 70, 70), 1)
    y += 20

    time_seconds = current_frame / fps if fps > 0 else 0
    minutes = int(time_seconds // 60)
    seconds = time_seconds % 60

    _put_text(canvas, "Frame", x, y, font, small_scale, DIM_COLOR)
    y += int(line_h * 0.8)
    _put_text(canvas, f"{current_frame} / {total_frames - 1}", x, y, font, font_scale, TEXT_COLOR)
    y += line_h + 5

    _put_text(canvas, "Time", x, y, font, small_scale, DIM_COLOR)
    y += int(line_h * 0.8)
    _put_text(canvas, f"{minutes}:{seconds:05.2f}", x, y, font, font_scale, TEXT_COLOR)
    y += line_h + 20

    cv2.line(canvas, (x, y), (x2, y), (70, 70, 70), 1)
    y += 20

    _put_text(canvas, "Go to Frame  [Tab to switch]", x, y, font, small_scale, DIM_COLOR)
    y += int(line_h * 0.8)
    _draw_input_field(canvas, frame_input, x, y, x2, line_h,
                      active_field == _FIELD_VF_FRAME, cursor_visible)
    y += line_h + 15

    _put_text(canvas, "Go to Time  (sec or m:ss)", x, y, font, small_scale, DIM_COLOR)
    y += int(line_h * 0.8)
    _draw_input_field(canvas, time_input, x, y, x2, line_h,
                      active_field == _FIELD_VF_TIME, cursor_visible)
    y += line_h + 25

    cv2.line(canvas, (x, y), (x2, y), (70, 70, 70), 1)
    y += 20

    _put_text(canvas, "Controls", x, y, font, small_scale, DIM_COLOR)
    y += int(line_h * 0.9)

    controls = [
        ("Tab", "cycle input fields"),
        ("Enter", "jump (frame/time) or select"),
        ("Left / Right", "+/- 1 frame"),
        ("PgUp / PgDn", "fwd / back 1 sec"),
        ("Home / End", "first / last"),
        ("Esc", "cancel"),
    ]

    for label, desc in controls:
        _put_text(canvas, label, x, y, font, small_scale, ACCENT_COLOR)
        y += int(line_h * 0.7)
        _put_text(canvas, desc, x + 10, y, font, small_scale * 0.9, DIM_COLOR)
        y += int(line_h * 0.8)


def _draw_input_field(
    canvas: np.ndarray,
    text: str,
    x1: int,
    y_baseline: int,
    x2: int,
    line_h: int,
    is_active: bool,
    cursor_visible: bool,
) -> None:
    input_h = line_h + 12
    input_y1 = y_baseline - int(line_h * 0.7)
    input_y2 = input_y1 + input_h
    border_color = INPUT_ACTIVE_BORDER if is_active else INPUT_INACTIVE_BORDER
    cv2.rectangle(canvas, (x1, input_y1), (x2, input_y2), INPUT_BG, -1)
    cv2.rectangle(canvas, (x1, input_y1), (x2, input_y2), border_color, 1)

    display_text = text
    if is_active and cursor_visible:
        display_text += "|"
    _put_monospace_text(canvas, display_text, x1 + 8, y_baseline - int(line_h * 0.5),
                        int(line_h * 0.9), TEXT_COLOR)


def _draw_panel(
    canvas: np.ndarray,
    panel_x: int,
    panel_w: int,
    panel_h: int,
    current_frame: int,
    total_frames: int,
    fps: float,
    bowler_name: str,
    frame_input: str,
    time_input: str,
    active_field: int,
    cursor_visible: bool,
) -> None:
    margin = 20
    x = panel_x + margin
    x2 = panel_x + panel_w - margin
    y = 40

    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = _fit_font_scale(panel_w - margin * 2, panel_w)
    line_h = int(30 * font_scale / 0.55)
    small_scale = font_scale * 0.75

    _put_text(canvas, "FRAME PICKER", x, y, font, font_scale, ACCENT_COLOR, 2)
    y += line_h + 10

    cv2.line(canvas, (x, y), (x2, y), (70, 70, 70), 1)
    y += 20

    time_seconds = current_frame / fps if fps > 0 else 0
    minutes = int(time_seconds // 60)
    seconds = time_seconds % 60

    _put_text(canvas, "Frame", x, y, font, small_scale, DIM_COLOR)
    y += int(line_h * 0.8)
    _put_text(canvas, f"{current_frame} / {total_frames - 1}", x, y, font, font_scale, TEXT_COLOR)
    y += line_h + 5

    _put_text(canvas, "Time", x, y, font, small_scale, DIM_COLOR)
    y += int(line_h * 0.8)
    _put_text(canvas, f"{minutes}:{seconds:05.2f}", x, y, font, font_scale, TEXT_COLOR)
    y += line_h + 20

    cv2.line(canvas, (x, y), (x2, y), (70, 70, 70), 1)
    y += 20

    # Bowler Name field
    _put_text(canvas, "Bowler Name  [Tab to switch]", x, y, font, small_scale, DIM_COLOR)
    y += int(line_h * 0.8)
    _draw_input_field(canvas, bowler_name, x, y, x2, line_h,
                      active_field == FIELD_NAME, cursor_visible)
    y += line_h + 15

    # Go to Frame field
    _put_text(canvas, "Go to Frame", x, y, font, small_scale, DIM_COLOR)
    y += int(line_h * 0.8)
    _draw_input_field(canvas, frame_input, x, y, x2, line_h,
                      active_field == FIELD_FRAME, cursor_visible)
    y += line_h + 15

    # Go to Time field
    _put_text(canvas, "Go to Time  (sec or m:ss)", x, y, font, small_scale, DIM_COLOR)
    y += int(line_h * 0.8)
    _draw_input_field(canvas, time_input, x, y, x2, line_h,
                      active_field == FIELD_TIME, cursor_visible)
    y += line_h + 25

    cv2.line(canvas, (x, y), (x2, y), (70, 70, 70), 1)
    y += 20

    _put_text(canvas, "Controls", x, y, font, small_scale, DIM_COLOR)
    y += int(line_h * 0.9)

    controls = [
        ("Tab", "cycle input fields"),
        ("Enter", "jump (frame/time) or select"),
        ("Left / Right", "+/- 1 frame"),
        ("PgUp / PgDn", "fwd / back 1 sec"),
        ("Home / End", "first / last"),
        ("Esc", "cancel"),
    ]

    for label, desc in controls:
        _put_text(canvas, label, x, y, font, small_scale, ACCENT_COLOR)
        y += int(line_h * 0.7)
        _put_text(canvas, desc, x + 10, y, font, small_scale * 0.9, DIM_COLOR)
        y += int(line_h * 0.8)


def _fit_font_scale(max_text_w: int, panel_w: int) -> float:
    if panel_w >= 450:
        return 0.6
    if panel_w >= 350:
        return 0.5
    return 0.45


def _put_monospace_text(
    canvas: np.ndarray,
    text: str,
    x: int,
    y: int,
    font_size: int,
    color: tuple[int, int, int],
) -> None:
    if not text:
        return
    pil_font = ImageFont.truetype(MONOSPACE_FONT_PATH, font_size)
    bbox = pil_font.getbbox(text)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    pil_img = Image.new("RGBA", (text_w + 4, text_h + 4), (0, 0, 0, 0))
    draw = ImageDraw.Draw(pil_img)
    draw.text((-bbox[0], -bbox[1]), text, font=pil_font, fill=(*color, 255))
    text_arr = np.array(pil_img)
    alpha = text_arr[:, :, 3].astype(np.float32) / 255.0
    region_h, region_w = text_arr.shape[:2]
    canvas_h, canvas_w = canvas.shape[:2]
    x1 = max(0, x)
    y1 = max(0, y)
    x2_c = min(canvas_w, x + region_w)
    y2_c = min(canvas_h, y + region_h)
    if x2_c <= x1 or y2_c <= y1:
        return
    sx = x1 - x
    sy = y1 - y
    rw = x2_c - x1
    rh = y2_c - y1
    rgb = text_arr[sy:sy + rh, sx:sx + rw, :3][:, :, ::-1]
    a = alpha[sy:sy + rh, sx:sx + rw, np.newaxis]
    roi = canvas[y1:y2_c, x1:x2_c].astype(np.float32)
    canvas[y1:y2_c, x1:x2_c] = (rgb.astype(np.float32) * a + roi * (1.0 - a)).astype(np.uint8)


def _put_text(
    canvas: np.ndarray,
    text: str,
    x: int,
    y: int,
    font: int,
    scale: float,
    color: tuple[int, int, int],
    thickness: int = 1,
) -> None:
    cv2.putText(canvas, text, (x, y), font, scale, color, thickness, cv2.LINE_AA)


def _draw_zones(frame: np.ndarray, venue: VenueCalibration) -> None:
    for lane in venue.lanes:
        _draw_zone(frame, lane.approach_zone, ZONE_COLORS["approach"], 0.15)
        _draw_zone(frame, lane.lane_zone, ZONE_COLORS["lane"], 0.08)
        _draw_zone(frame, lane.pin_zone, ZONE_COLORS["pin"], 0.08)


def _draw_zone(
    frame: np.ndarray,
    polygon: list[tuple[int, int]],
    color: tuple[int, int, int],
    alpha: float,
) -> None:
    if len(polygon) < 3:
        return
    pts = np.array(polygon, dtype=np.int32)
    overlay = frame.copy()
    cv2.fillPoly(overlay, [pts], color)
    cv2.addWeighted(overlay, alpha, frame, 1.0 - alpha, 0, dst=frame)
    cv2.polylines(frame, [pts], isClosed=True, color=color, thickness=2)
