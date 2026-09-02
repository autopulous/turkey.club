"""Interactive debug visualization for the bowler clustering and identification pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from turkey_club.config import (
    BowlerCluster,
    BowlerTarget,
    CensusPersonRecord,
    CensusRecord,
    ClusterAppearance,
    SegmentationParameters,
)
from turkey_club.detect import (
    KEYPOINT_LEFT_HIP,
    KEYPOINT_LEFT_SHOULDER,
    KEYPOINT_RIGHT_HIP,
    KEYPOINT_RIGHT_SHOULDER,
)
from turkey_club.identify import (
    LBP_HISTOGRAM_BINS,
    MIN_KEYPOINT_CONFIDENCE,
    SHOULDER_HORIZONTAL_PAD_FRACTION,
    TORSO_VERTICAL_PAD_FRACTION,
    UPPER_BACK_BOTTOM_FRACTION,
    UPPER_BACK_TOP_FRACTION,
    histogram_distance,
    resolve_reference_histogram,
)

WINDOW_NAME = "turkey-club clustering debug"
CROP_DISPLAY_HEIGHT = 200
PANEL_WIDTH = 400
INFO_PANEL_WIDTH = 480
CANVAS_HEIGHT = 640
AUTO_ADVANCE_MS = 1000


@dataclass
class ClusteringStep:
    """One person-detection comparison recorded during the clustering replay."""

    frame_number: int
    person_index: int
    lane_name: str
    bbox: tuple[int, int, int, int]
    person_histogram: list[float]
    distance_to_reference: float
    cluster_distances: list[tuple[str, float]]
    assignment: str
    cluster_sizes: dict[str, int]
    stage: str
    keypoints: list[tuple[float, float, float]] | None = None


def _resolve_reference_histogram(target: BowlerTarget) -> np.ndarray:
    """Return the reference histogram from the target, preferring reference_histogram."""
    hist = resolve_reference_histogram(target)
    if hist is not None:
        return hist
    return np.zeros((LBP_HISTOGRAM_BINS, 1), dtype=np.float32)


def replay_clustering(
    records: list[CensusRecord],
    params: SegmentationParameters,
    target: BowlerTarget,
) -> list[ClusteringStep]:
    """Replay the Stage 2-4 clustering logic, recording each comparison step."""
    reference_hist = _resolve_reference_histogram(target)
    steps: list[ClusteringStep] = []
    clusters: list[BowlerCluster] = []
    uncertain: list[tuple[CensusRecord, CensusPersonRecord]] = []

    for record in records:
        for pi, person in enumerate(record.persons):
            person_hist = _to_hist_array(person.histogram)
            if person_hist is None:
                steps.append(_make_step(
                    record, pi, person, 1.0, [], "skipped (no histogram)",
                    clusters, reference_hist, "Stage 2",
                ))
                uncertain.append((record, person))
                continue

            dist_to_ref = histogram_distance(person_hist, reference_hist)

            if not clusters:
                clusters.append(_create_cluster(len(clusters), record, person))
                steps.append(_make_step(
                    record, pi, person, dist_to_ref, [],
                    f"new {clusters[-1].cluster_id} (first)",
                    clusters, reference_hist, "Stage 2",
                ))
                continue

            cluster_dists = []
            best_cluster = None
            best_distance = float("inf")

            for cluster in clusters:
                centroid = _to_hist_array(cluster.centroid_histogram)
                if centroid is None:
                    continue
                dist = histogram_distance(person_hist, centroid)
                cluster_dists.append((cluster.cluster_id, dist))
                if dist < best_distance:
                    best_distance = dist
                    best_cluster = cluster

            if best_cluster is not None and best_distance < params.cluster_tight_threshold:
                same_frame_clusters = {
                    c.cluster_id
                    for c in clusters
                    for a in c.frame_appearances
                    if a.frame_number == record.frame_number
                }
                if best_cluster.cluster_id in same_frame_clusters:
                    new_cluster = _create_cluster(len(clusters), record, person)
                    clusters.append(new_cluster)
                    assignment = f"new {new_cluster.cluster_id} (co-occurrence split)"
                else:
                    _assign_to_cluster(best_cluster, record, person)
                    assignment = f"{best_cluster.cluster_id} (dist={best_distance:.3f})"
            else:
                uncertain.append((record, person))
                assignment = f"uncertain (best={best_distance:.3f})"

            steps.append(_make_step(
                record, pi, person, dist_to_ref, cluster_dists,
                assignment, clusters, reference_hist, "Stage 2",
            ))

    for record, person in uncertain:
        pi = next(
            (i for i, p in enumerate(record.persons) if p is person), 0
        )
        person_hist = _to_hist_array(person.histogram)
        if person_hist is None:
            continue

        dist_to_ref = histogram_distance(person_hist, reference_hist)

        if not clusters:
            clusters.append(_create_cluster(len(clusters), record, person))
            steps.append(_make_step(
                record, pi, person, dist_to_ref, [],
                f"new {clusters[-1].cluster_id} (recovery, first)",
                clusters, reference_hist, "Stage 3",
            ))
            continue

        distances = []
        for cluster in clusters:
            centroid = _to_hist_array(cluster.centroid_histogram)
            if centroid is None:
                continue
            dist = histogram_distance(person_hist, centroid)
            distances.append((dist, cluster))

        cluster_dists = [(c.cluster_id, d) for d, c in distances]
        distances.sort(key=lambda x: x[0])

        if not distances:
            clusters.append(_create_cluster(len(clusters), record, person))
            assignment = f"new {clusters[-1].cluster_id} (recovery)"
        else:
            best_dist, best_cluster = distances[0]
            if best_dist < params.cluster_loose_threshold:
                if len(distances) > 1:
                    margin = distances[1][0] - best_dist
                    if margin >= params.cluster_margin_ratio:
                        _assign_to_cluster(best_cluster, record, person)
                        assignment = f"{best_cluster.cluster_id} (recovery, dist={best_dist:.3f}, margin={margin:.3f})"
                    else:
                        clusters.append(_create_cluster(len(clusters), record, person))
                        assignment = f"new {clusters[-1].cluster_id} (recovery, margin too small={margin:.3f})"
                elif len(distances) == 1:
                    _assign_to_cluster(best_cluster, record, person)
                    assignment = f"{best_cluster.cluster_id} (recovery, only cluster)"
                else:
                    clusters.append(_create_cluster(len(clusters), record, person))
                    assignment = f"new {clusters[-1].cluster_id} (recovery)"
            else:
                clusters.append(_create_cluster(len(clusters), record, person))
                assignment = f"new {clusters[-1].cluster_id} (recovery, too far={best_dist:.3f})"

        steps.append(_make_step(
            record, pi, person, dist_to_ref, cluster_dists,
            assignment, clusters, reference_hist, "Stage 3",
        ))

    return steps


def build_reference_visualization(target: BowlerTarget) -> np.ndarray:
    """Build a visual representation of the reference target."""
    if target.shirt_color_samples:
        samples = target.shirt_color_samples
        n = len(samples)
        side = int(np.ceil(np.sqrt(n)))
        pixels = np.zeros((side * side, 3), dtype=np.uint8)
        for i, (b, g, r) in enumerate(samples):
            pixels[i] = [b, g, r]
        grid = pixels.reshape(side, side, 3)
        scale_factor = max(1, CROP_DISPLAY_HEIGHT // side)
        img = cv2.resize(grid, (side * scale_factor, side * scale_factor), interpolation=cv2.INTER_NEAREST)
        h, w = img.shape[:2]
        if w > PANEL_WIDTH:
            ratio = PANEL_WIDTH / w
            img = cv2.resize(img, (PANEL_WIDTH, int(h * ratio)), interpolation=cv2.INTER_NEAREST)
        if img.shape[0] > CROP_DISPLAY_HEIGHT:
            img = img[:CROP_DISPLAY_HEIGHT]
        return img

    if target.reference_histogram:
        ref_hist = _resolve_reference_histogram(target).flatten()
        img = np.zeros((CROP_DISPLAY_HEIGHT, PANEL_WIDTH, 3), dtype=np.uint8)
        img[:] = (50, 50, 50)
        _draw_text(img, "LBP texture reference", 10, 25, scale=0.5, color=(200, 200, 200))
        max_val = ref_hist.max() if ref_hist.max() > 0 else 1.0
        bar_w = (PANEL_WIDTH - 20) // len(ref_hist)
        bar_area_h = CROP_DISPLAY_HEIGHT - 50
        for i, val in enumerate(ref_hist):
            bar_h = int((val / max_val) * bar_area_h)
            x1 = 10 + i * bar_w
            y1 = CROP_DISPLAY_HEIGHT - 10 - bar_h
            y2 = CROP_DISPLAY_HEIGHT - 10
            cv2.rectangle(img, (x1, y1), (x1 + bar_w - 2, y2), (180, 180, 180), -1)
        return img

    img = np.zeros((CROP_DISPLAY_HEIGHT, PANEL_WIDTH, 3), dtype=np.uint8)
    _draw_text(img, "No reference data", 10, CROP_DISPLAY_HEIGHT // 2)
    return img


def render_step(
    step: ClusteringStep,
    census_dir: Path,
    target: BowlerTarget,
    reference_vis: np.ndarray,
) -> np.ndarray:
    """Build the composite display frame for one clustering step."""
    canvas = np.zeros((CANVAS_HEIGHT, PANEL_WIDTH + PANEL_WIDTH + INFO_PANEL_WIDTH, 3), dtype=np.uint8)
    canvas[:] = (40, 40, 40)

    ref_h, ref_w = reference_vis.shape[:2]
    canvas[10:10 + ref_h, 10:10 + ref_w] = reference_vis
    _draw_text(canvas, "REFERENCE", 10, 10 + ref_h + 20, scale=0.6, color=(200, 200, 200))
    _draw_text(canvas, target.name, 10, 10 + ref_h + 45, scale=0.7, color=(0, 255, 255))

    frame_path = census_dir / f"{step.frame_number:06d}.jpg"
    candidate_crop = None
    if frame_path.exists():
        frame_img = cv2.imread(str(frame_path))
        if frame_img is not None:
            x1, y1, x2, y2 = step.bbox
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(frame_img.shape[1], x2)
            y2 = min(frame_img.shape[0], y2)
            if x2 > x1 and y2 > y1:
                candidate_crop = frame_img[y1:y2, x1:x2].copy()
                _draw_crop_overlay(candidate_crop, step.keypoints, x1, y1)

    crop_x = PANEL_WIDTH + 10
    if candidate_crop is not None and candidate_crop.size > 0:
        ch, cw = candidate_crop.shape[:2]
        if ch > 0 and cw > 0:
            scale_factor = min(CROP_DISPLAY_HEIGHT / ch, (PANEL_WIDTH - 20) / cw)
            new_w = max(1, int(cw * scale_factor))
            new_h = max(1, int(ch * scale_factor))
            resized = cv2.resize(candidate_crop, (new_w, new_h))
            canvas[10:10 + new_h, crop_x:crop_x + new_w] = resized
    else:
        _draw_text(canvas, "No crop available", crop_x, CROP_DISPLAY_HEIGHT // 2)

    _draw_text(canvas, "CANDIDATE", crop_x, 10 + CROP_DISPLAY_HEIGHT + 20, scale=0.6, color=(200, 200, 200))

    info_x = PANEL_WIDTH * 2 + 20
    y = 30
    line_h = 28

    _draw_text(canvas, f"[{step.stage}]", info_x, y, scale=0.6, color=(128, 128, 255))
    y += line_h

    _draw_text(canvas, f"Frame: {step.frame_number}", info_x, y, scale=0.6)
    y += line_h
    _draw_text(canvas, f"Lane: {step.lane_name}", info_x, y, scale=0.6)
    y += line_h
    _draw_text(canvas, f"Person: #{step.person_index + 1}", info_x, y, scale=0.6)
    y += line_h + 10

    dist_color = _distance_color(step.distance_to_reference)
    _draw_text(canvas, f"Dist to reference: {step.distance_to_reference:.3f}", info_x, y, scale=0.6, color=dist_color)
    y += line_h + 10

    _draw_text(canvas, "Cluster distances:", info_x, y, scale=0.5, color=(180, 180, 180))
    y += line_h - 4
    for cluster_id, dist in sorted(step.cluster_distances, key=lambda x: x[1]):
        c = _distance_color(dist)
        _draw_text(canvas, f"  {cluster_id}: {dist:.3f}", info_x, y, scale=0.5, color=c)
        y += line_h - 6
    y += 10

    assign_color = (0, 255, 0) if "new" not in step.assignment and "uncertain" not in step.assignment else (0, 200, 255)
    _draw_text(canvas, f"Assignment: {step.assignment}", info_x, y, scale=0.55, color=assign_color)
    y += line_h + 10

    _draw_text(canvas, "Cluster sizes:", info_x, y, scale=0.5, color=(180, 180, 180))
    y += line_h - 4
    for cid, count in sorted(step.cluster_sizes.items()):
        _draw_text(canvas, f"  {cid}: {count}", info_x, y, scale=0.5)
        y += line_h - 6

    return canvas


def run_debug_viewer(
    steps: list[ClusteringStep],
    census_dir: Path,
    target: BowlerTarget,
) -> None:
    """Open an interactive OpenCV window to browse the clustering steps."""
    if not steps:
        print("No clustering steps to display.", flush=True)
        return

    reference_vis = build_reference_visualization(target)
    total = len(steps)
    index = 0
    paused = False

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    total_width = PANEL_WIDTH + PANEL_WIDTH + INFO_PANEL_WIDTH
    cv2.resizeWindow(WINDOW_NAME, min(total_width, 1400), min(CANVAS_HEIGHT, 900))

    cache: dict[int, np.ndarray] = {}

    def show_current() -> None:
        if index not in cache:
            frame = render_step(steps[index], census_dir, target, reference_vis)
            nav_y = CANVAS_HEIGHT - 30
            nav_text = f"[{index + 1}/{total}]  arrows: prev/next | SPACE: {'resume' if paused else 'pause'} | Q: quit"
            _draw_text(frame, nav_text, 10, nav_y, scale=0.5, color=(160, 160, 160))
            cache[index] = frame
        cv2.imshow(WINDOW_NAME, cache[index])

    show_current()

    try:
        while True:
            wait_ms = 0 if paused else AUTO_ADVANCE_MS
            key = cv2.waitKeyEx(max(wait_ms, 1))

            if key == -1 and not paused:
                index = min(index + 1, total - 1)
                show_current()
                continue

            if key == ord("q") or key == ord("Q") or key == 27:
                break
            elif key == 32:
                paused = not paused
                cache.pop(index, None)
                show_current()
            elif key in (2555904, 83, ord("d")):
                index = min(index + 1, total - 1)
                cache.pop(index, None)
                show_current()
            elif key in (2424832, 81, ord("a")):
                index = max(index - 1, 0)
                cache.pop(index, None)
                show_current()
    finally:
        cv2.destroyWindow(WINDOW_NAME)


def _make_step(
    record: CensusRecord,
    person_index: int,
    person: CensusPersonRecord,
    dist_to_ref: float,
    cluster_dists: list[tuple[str, float]],
    assignment: str,
    clusters: list[BowlerCluster],
    reference_hist: np.ndarray,
    stage: str,
) -> ClusteringStep:
    sizes = {c.cluster_id: len(c.frame_appearances) for c in clusters}
    return ClusteringStep(
        frame_number=record.frame_number,
        person_index=person_index,
        lane_name=person.lane_name,
        bbox=tuple(person.bbox),
        person_histogram=person.histogram,
        distance_to_reference=dist_to_ref,
        cluster_distances=list(cluster_dists),
        assignment=assignment,
        cluster_sizes=dict(sizes),
        stage=stage,
        keypoints=person.keypoints,
    )


def _draw_crop_overlay(
    crop: np.ndarray,
    keypoints: list[tuple[float, float, float]] | None,
    bbox_x1: int,
    bbox_y1: int,
) -> None:
    """Draw the crop region rectangle and keypoint markers on a bbox crop.

    Cyan rectangle + green/blue keypoint circles when keypoints are confident;
    orange rectangle for the fixed-fraction fallback otherwise.
    """
    crop_h, crop_w = crop.shape[:2]
    used_keypoints = False

    if keypoints is not None:
        ls = keypoints[KEYPOINT_LEFT_SHOULDER]
        rs = keypoints[KEYPOINT_RIGHT_SHOULDER]
        lh = keypoints[KEYPOINT_LEFT_HIP]
        rh = keypoints[KEYPOINT_RIGHT_HIP]

        shoulders_ok = ls[2] >= MIN_KEYPOINT_CONFIDENCE and rs[2] >= MIN_KEYPOINT_CONFIDENCE
        hips_ok = lh[2] >= MIN_KEYPOINT_CONFIDENCE and rh[2] >= MIN_KEYPOINT_CONFIDENCE

        kp_indices = [
            (KEYPOINT_LEFT_SHOULDER, (0, 220, 0)),
            (KEYPOINT_RIGHT_SHOULDER, (0, 220, 0)),
            (KEYPOINT_LEFT_HIP, (220, 140, 0)),
            (KEYPOINT_RIGHT_HIP, (220, 140, 0)),
        ]
        for idx, confident_color in kp_indices:
            kp = keypoints[idx]
            cx = int(kp[0] - bbox_x1)
            cy = int(kp[1] - bbox_y1)
            if 0 <= cx < crop_w and 0 <= cy < crop_h:
                if kp[2] >= MIN_KEYPOINT_CONFIDENCE:
                    cv2.circle(crop, (cx, cy), 5, confident_color, -1)
                else:
                    cv2.circle(crop, (cx, cy), 5, (80, 80, 80), 1)

        if shoulders_ok and hips_ok:
            s_left_x = min(ls[0], rs[0])
            s_right_x = max(ls[0], rs[0])
            s_top_y = min(ls[1], rs[1])
            h_bottom_y = max(lh[1], rh[1])
            s_width = s_right_x - s_left_x
            t_height = h_bottom_y - s_top_y

            if s_width > 1 and t_height > 1:
                pad_x = s_width * SHOULDER_HORIZONTAL_PAD_FRACTION
                pad_y = t_height * TORSO_VERTICAL_PAD_FRACTION
                r_x1 = int(s_left_x - pad_x - bbox_x1)
                r_y1 = int(s_top_y - pad_y - bbox_y1)
                r_x2 = int(s_right_x + pad_x - bbox_x1)
                r_y2 = int(h_bottom_y + pad_y - bbox_y1)
                r_x1 = max(0, r_x1)
                r_y1 = max(0, r_y1)
                r_x2 = min(crop_w - 1, r_x2)
                r_y2 = min(crop_h - 1, r_y2)
                cv2.rectangle(crop, (r_x1, r_y1), (r_x2, r_y2), (255, 255, 0), 2)
                used_keypoints = True

    if not used_keypoints:
        ub_top = int(UPPER_BACK_TOP_FRACTION * crop_h)
        ub_bottom = int(UPPER_BACK_BOTTOM_FRACTION * crop_h)
        cv2.rectangle(crop, (0, ub_top), (crop_w - 1, ub_bottom), (0, 165, 255), 2)


def _draw_text(
    img: np.ndarray,
    text: str,
    x: int,
    y: int,
    scale: float = 0.7,
    color: tuple[int, int, int] = (255, 255, 255),
    thickness: int = 1,
) -> None:
    cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thickness + 2, cv2.LINE_AA)
    cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)


def _distance_color(dist: float) -> tuple[int, int, int]:
    """Green for close (< 0.3), yellow for moderate, red for far (> 0.7)."""
    if dist < 0.3:
        return (0, 255, 0)
    elif dist < 0.5:
        return (0, 255, 255)
    elif dist < 0.7:
        return (0, 165, 255)
    return (0, 0, 255)


def _to_hist_array(histogram: list[float]) -> np.ndarray | None:
    if not histogram:
        return None
    arr = np.array(histogram, dtype=np.float32)
    if 0 == arr.size:
        return None
    return arr.reshape(-1, 1)


def _create_cluster(
    index: int,
    record: CensusRecord,
    person: CensusPersonRecord,
) -> BowlerCluster:
    cluster_id = f"bowler_{index + 1:02d}"
    return BowlerCluster(
        cluster_id=cluster_id,
        centroid_histogram=list(person.histogram),
        frame_appearances=[ClusterAppearance(
            frame_number=record.frame_number,
            lane_name=person.lane_name,
            bbox=person.bbox,
        )],
    )


def _assign_to_cluster(
    cluster: BowlerCluster,
    record: CensusRecord,
    person: CensusPersonRecord,
) -> None:
    cluster.frame_appearances.append(ClusterAppearance(
        frame_number=record.frame_number,
        lane_name=person.lane_name,
        bbox=person.bbox,
    ))
    n = len(cluster.frame_appearances)
    if n <= 1:
        cluster.centroid_histogram = list(person.histogram)
        return
    old = np.array(cluster.centroid_histogram, dtype=np.float32)
    new = np.array(person.histogram, dtype=np.float32)
    if old.shape != new.shape:
        return
    updated = old * ((n - 1) / n) + new * (1 / n)
    cluster.centroid_histogram = updated.tolist()
