---
name: project-calibration-assumptions
description: Fixed-camera, polygon-zone calibration model. One calibration JSON per venue/camera setup.
metadata:
  type: project
---

Calibration model assumptions:

- **Fixed camera per venue**: the pipeline assumes the camera position and framing don't change throughout the video. Tournament-style amateur recordings (phone on tripod behind the lanes) satisfy this. Broadcast video with camera cuts does not (out of scope for now).
- **Polygon zones, not bounding boxes**: trapezoidal polygons capture the perspective foreshortening that converts the rectangular real-world lane into the lens-warped image plane.
- **Three zones per lane**: approach (where bowler stands), lane (where ball travels), pin (where pins fall). Pin zone should be small and tightly bounded — large pin zones catch scoreboard updates, overhead light reflections, and other false positives.
- **Two-lane is the common case**: PBA / League / Doubles footage shows both lanes simultaneously; one `VenueCalibration` JSON contains both.

**Reference-image-driven calibration:**
- `calibrate` CLI command accepts one `--frame` per `--lane` (paired by order), so each lane's zones can be marked against a still where the bowler is visibly in that lane's approach.
- Calibration data is video-independent — same camera setup → reuse calibration across all games at that venue.

**Verify with overlay before extracting:** the `preview` CLI command renders the calibrated zones on every frame of a video. Always sanity-check a new calibration this way before running the long `extract` pipeline.

**Why:** Calibration is the load-bearing input that lets the pipeline ignore the 99%+ of frame pixels irrelevant to the search. Without it, motion-based ball/pin detection would catch every spectator, every adjacent-lane bowler, every overhead light flicker, every scoreboard update.

**How to apply:** Pre-build calibration when starting on a new venue — one-time interactive cost (~2 minutes of clicking). Don't try to auto-detect zones from the video; the manual click-once cost is small and produces a reusable artifact. If recalibrating because of a change in framing, save under a new name (e.g., `venue.json` → `venue_setup_b.json`) rather than overwriting — the old calibration may still be useful for older recordings. Related: [[project-search-strategy]].
