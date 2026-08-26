---
name: project-identification-strategy
description: HSV histogram-distance bowler identification, why OCR was abandoned, threshold tuning, and how to build a BowlerTarget.
metadata:
  type: project
---

Bowler identification uses **HSV histogram-distance match** (Bhattacharyya), NOT OCR.

Decision sequence (chronicle of validation work 2026-05-25):
1. **OCR was tried first** (EasyOCR with 6 preprocessing variants: original / upscaled / CLAHE / inverted / Otsu / Otsu-inverted) plus fuzzy sequence-similarity matching. Cursive PBA jerseys defeat the recognizer — "Clemons" was read as "@tenons", "@lemtot", "0lenora", etc. Fuzzy threshold 0.55 wasn't crossed.
2. **Color-inclusion match** (count pixels within HSV tolerance of sample colors) was tried — too permissive. All dark-shirted persons saturated at the cap (0.85), no discrimination.
3. **HSV histogram-distance match** (cv2.HISTCMP_BHATTACHARYYA, 16×8×8 bins) is the production approach. Stored in `identify.py::_color_histogram_confidence`.

**Threshold tuning:**
- Reference-image-only test (still frames where the bowler is visible and motionless): Clemons scored 0.69-0.74, teammate 0.45 — threshold 0.55 worked.
- Real video (motion blur, pose variation, lighting changes): Clemons drops to 0.30-0.40 range. Other persons 0.20-0.30. **Threshold must be 0.30** (`SegmentationParameters.bowler_confidence_threshold`) for the pipeline to fire on real video.

**Building a BowlerTarget:**
`identify.build_bowler_target_from_references(name, references, venue, samples_per_image=2000)` takes pairs of `(reference_image_path, expected_lane_name)`, runs person detection, identifies the person whose foot is in the named lane's approach zone, and samples random pixels from the upper-back crop. Saved as `shirt_color_samples` in the JSON.

**JSON deserialization gotcha:** `BowlerTarget.load` MUST coerce the loaded sample lists to tuples (JSON has no tuple type → they come back as lists). The histogram-from-samples helper uses `lru_cache` which requires hashable keys — lists fail with `TypeError: unhashable type: 'list'`. Coercion happens in `BowlerTarget.load`.

**Why:** Cursive jersey fonts are the rule in PBA, not the exception. OCR isn't a viable primary identifier. Color histogram captures both presence (which colors) and distribution (how much) — robust to small lighting/pose changes but sensitive enough to discriminate teammates wearing different shirts.

**How to apply:** When adding a new bowler, capture 1-2 still frames showing them in each lane they'll bowl. Run `build_bowler_target_from_references` (no dedicated CLI command yet — currently invoked via a small Python script; exposing as a CLI subcommand is on the TODO list). When tuning thresholds for a new video, sample-test detection on 8-10 frames spread across the video first. Related: [[project-bowling-format-taxonomy]], [[project-search-strategy]].
