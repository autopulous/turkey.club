"""Interactive venue-zone calibration and overlay rendering."""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

import cv2
import numpy as np

from turkey_club.config import LaneCalibration, VenueCalibration

ZONE_COLORS: dict[str, tuple[int, int, int]] = {
    "approach": (0, 255, 255),
    "lane":     (0, 165, 255),
    "pin":      (0, 255, 0),
}
WINDOW_NAME = "turkey-club calibration"


def run_interactive_calibration(
    frame_paths: Sequence[Path],
    out_path: Path,
    lane_names: Sequence[str] = ("left", "right"),
) -> VenueCalibration:
    """Walk the user through marking approach/lane/pin zones for each lane.

    ``frame_paths`` must have the same length as ``lane_names``; each lane is
    calibrated against its paired still. Frame dimensions are taken from the
    first image and a warning is printed if any subsequent image differs.
    """
    if len(frame_paths) != len(lane_names):
        raise ValueError(
            f"frame_paths length ({len(frame_paths)}) must match lane_names length ({len(lane_names)})."
        )

    if any(ch in str(out_path) for ch in ("\n", "\r", "\t")):
        raise ValueError(
            f"Output path contains whitespace control characters (likely a stray newline from shell paste): {out_path!r}"
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    first_image = cv2.imread(str(frame_paths[0]))
    if first_image is None:
        raise FileNotFoundError(f"Could not read frame: {frame_paths[0]}")
    height, width = first_image.shape[:2]

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, min(width, 1200), min(height, 900))

    lanes: list[LaneCalibration] = []
    try:
        for lane_name, frame_path in zip(lane_names, frame_paths):
            image = first_image if frame_path == frame_paths[0] else cv2.imread(str(frame_path))
            if image is None:
                raise FileNotFoundError(f"Could not read frame: {frame_path}")
            if image.shape[:2] != (height, width):
                print(
                    f"Warning: {frame_path} is {image.shape[1]}x{image.shape[0]}, "
                    f"differs from first frame {width}x{height}. Calibration assumes fixed camera."
                )
            approach = _collect_polygon(image, f"{lane_name}: approach", ZONE_COLORS["approach"], existing_lanes=lanes)
            lane_zone = _collect_polygon(image, f"{lane_name}: lane", ZONE_COLORS["lane"], existing_lanes=lanes, current_poly=approach, current_color=ZONE_COLORS["approach"])
            pin_zone = _collect_polygon(image, f"{lane_name}: pin", ZONE_COLORS["pin"], existing_lanes=lanes, current_poly=approach, current_color=ZONE_COLORS["approach"], extra_polys=[(lane_zone, ZONE_COLORS["lane"])])
            lanes.append(LaneCalibration(name=lane_name, approach_zone=approach, lane_zone=lane_zone, pin_zone=pin_zone))
    finally:
        cv2.destroyWindow(WINDOW_NAME)

    calibration = VenueCalibration(lanes=lanes, frame_width=width, frame_height=height)
    calibration.save(out_path)
    print(f"Saved calibration with {len(lanes)} lane(s) to {out_path}")
    return calibration


def render_zone_overlay(video_path: Path, calibration_path: Path, out_path: Path) -> None:
    """Render every lane's calibrated zones as colored polygon overlays on every video frame."""
    calibration = VenueCalibration.load(calibration_path)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        cap.release()
        raise RuntimeError(f"Could not open VideoWriter for {out_path}")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            for lane in calibration.lanes:
                _draw_zone(frame, lane.approach_zone, ZONE_COLORS["approach"], f"{lane.name}:approach")
                _draw_zone(frame, lane.lane_zone, ZONE_COLORS["lane"], f"{lane.name}:lane")
                _draw_zone(frame, lane.pin_zone, ZONE_COLORS["pin"], f"{lane.name}:pin")
            writer.write(frame)
    finally:
        cap.release()
        writer.release()
    print(f"Wrote overlay video to {out_path}")


def _collect_polygon(
    base_image: np.ndarray,
    zone_label: str,
    color: tuple[int, int, int],
    existing_lanes: list[LaneCalibration],
    current_poly: list[tuple[int, int]] | None = None,
    current_color: tuple[int, int, int] | None = None,
    extra_polys: list[tuple[list[tuple[int, int]], tuple[int, int, int]]] | None = None,
) -> list[tuple[int, int]]:
    """Display ``base_image`` and capture mouse-click polygon vertices.

    Left-click adds a vertex; right-click (or pressing 'u') undoes the last; Enter
    finalizes when at least 3 vertices exist; Esc raises to cancel calibration.
    Already-finished zones from prior lanes are drawn for spatial reference.
    """
    points: list[tuple[int, int]] = []
    canvas = base_image.copy()

    def on_mouse(event: int, x: int, y: int, flags: int, param: object) -> None:
        if event == cv2.EVENT_LBUTTONDOWN:
            points.append((x, y))
        elif event == cv2.EVENT_RBUTTONDOWN and points:
            points.pop()
        else:
            return
        _redraw(canvas, base_image, points, zone_label, color, existing_lanes, current_poly, current_color, extra_polys)
        cv2.imshow(WINDOW_NAME, canvas)

    cv2.setMouseCallback(WINDOW_NAME, on_mouse)
    _redraw(canvas, base_image, points, zone_label, color, existing_lanes, current_poly, current_color, extra_polys)
    cv2.imshow(WINDOW_NAME, canvas)

    while True:
        key = cv2.waitKey(20) & 0xFF
        if key == 13:  # Enter
            if len(points) >= 3:
                return points
            print(f"  Need >= 3 vertices for '{zone_label}' (have {len(points)}).")
        elif key == 27:  # Esc
            raise RuntimeError(f"Calibration cancelled by user during '{zone_label}'")
        elif key in (ord("u"), ord("U")) and points:
            points.pop()
            _redraw(canvas, base_image, points, zone_label, color, existing_lanes, current_poly, current_color, extra_polys)
            cv2.imshow(WINDOW_NAME, canvas)


def _redraw(
    canvas: np.ndarray,
    base_image: np.ndarray,
    points: list[tuple[int, int]],
    zone_label: str,
    color: tuple[int, int, int],
    existing_lanes: list[LaneCalibration],
    current_poly: list[tuple[int, int]] | None,
    current_color: tuple[int, int, int] | None,
    extra_polys: list[tuple[list[tuple[int, int]], tuple[int, int, int]]] | None,
) -> None:
    canvas[:] = base_image
    for lane in existing_lanes:
        _draw_zone(canvas, lane.approach_zone, ZONE_COLORS["approach"], f"{lane.name}:approach", alpha=0.08)
        _draw_zone(canvas, lane.lane_zone, ZONE_COLORS["lane"], f"{lane.name}:lane", alpha=0.08)
        _draw_zone(canvas, lane.pin_zone, ZONE_COLORS["pin"], f"{lane.name}:pin", alpha=0.08)
    if current_poly is not None and current_color is not None:
        _draw_zone(canvas, current_poly, current_color, "(this lane)", alpha=0.12)
    if extra_polys:
        for poly, poly_color in extra_polys:
            _draw_zone(canvas, poly, poly_color, "(this lane)", alpha=0.12)
    for index, (x, y) in enumerate(points):
        cv2.circle(canvas, (x, y), 6, color, -1)
        cv2.putText(canvas, str(index + 1), (x + 8, y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)
    if len(points) >= 2:
        cv2.polylines(canvas, [np.array(points, dtype=np.int32)], isClosed=len(points) >= 3, color=color, thickness=2)
    for line_index, text in enumerate([
        f"Marking: {zone_label.upper()}",
        "L-click add | R-click/U undo | Enter finalize | Esc cancel",
        f"Vertices: {len(points)} (need >= 3)",
    ]):
        origin = (10, 30 + line_index * 28)
        cv2.putText(canvas, text, origin, cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(canvas, text, origin, cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1, cv2.LINE_AA)


def _draw_zone(
    frame: np.ndarray,
    polygon: list[tuple[int, int]],
    color: tuple[int, int, int],
    label: str,
    alpha: float = 0.18,
) -> None:
    if len(polygon) < 3:
        return
    pts = np.array(polygon, dtype=np.int32)
    overlay = frame.copy()
    cv2.fillPoly(overlay, [pts], color)
    cv2.addWeighted(overlay, alpha, frame, 1.0 - alpha, 0, dst=frame)
    cv2.polylines(frame, [pts], isClosed=True, color=color, thickness=2)
    cx = int(pts[:, 0].mean())
    cy = int(pts[:, 1].mean())
    cv2.putText(frame, label, (cx - 60, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(frame, label, (cx - 60, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 1, cv2.LINE_AA)
