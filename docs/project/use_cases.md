# Use Cases — turkey.club

This document describes representative end-to-end scenarios for using turkey.club. Each use case names an actor, the trigger, the main flow, and the related requirements from [requirements.md](requirements.md). These are the scenarios the tool is built for; new features should be validated against one or more of them.

---

## UC-01 — Cold start: new venue, new bowler

**Actor**: A bowler / coach with a freshly recorded match video at a venue and bowler they've never processed before.

**Precondition**:
- Recorded match video file or accessible URL.
- One or more reference still frames where the target bowler is clearly visible in their approach.
- Prerequisites and tool installed (see [installation.md](../user/installation.md)).

**Trigger**: User wants per-shot clips of one bowler from a match.

**Main flow**:
1. Extract a reference still per lane the bowler will appear on (typically two for cross-lane formats, one for Baker).
2. Run `calibrate` to mark approach / lane / pin polygon zones — once per venue/camera setup.
3. Build a `BowlerTarget` JSON by sampling shirt colors from the reference frames (currently via a small Python script invoking `identify.build_bowler_target_from_references`; a CLI subcommand is planned).
4. Verify calibration with `preview` — render zones onto the video as colored overlays.
5. Run `extract --video ... --bowler-target ... --calibration ...`.
6. Review the per-shot clips and merged `all_shots.mp4` in the output directory.

**Post-condition**: Per-shot clips and merged highlight reel exist; calibration JSON and bowler-target JSON are reusable artifacts for future matches at the same venue / same bowler.

**Related requirements**: F1 (calibration), F2 (bowler target), F4–F11 (full extract pipeline).

---

## UC-02 — Routine extract on an established setup

**Actor**: A returning user processing another match at a venue and bowler they've already calibrated.

**Precondition**:
- Existing `venue.json` and `<bowler>.json` from a prior run.
- New match video.

**Trigger**: Quickly process a fresh match.

**Main flow**:
1. Confirm the camera framing is unchanged from the calibrated reference (eyeball check, or rerun `preview` on a sample frame).
2. Run `extract --video new_match.mp4 --bowler-target clemons.json --calibration venue.json --out new_match_clips/`.
3. Spot-check the first one or two clips to confirm identification is still firing.

**Alternative flow**:
- If the camera framing has drifted, redo `calibrate` against a still from the new video.
- If identification has degraded (too few hits), re-tune the threshold or rebuild the bowler target from a fresh reference frame in the new video's lighting.

**Post-condition**: Same as UC-01; total wall-clock time dominated by per-frame YOLO inference.

**Related requirements**: F4–F11; calibration reuse F1.

---

## UC-03 — Multi-bowler processing of a single match

**Actor**: A team coach who wants per-bowler reels for several teammates from the same match video.

**Precondition**:
- One `venue.json` for the camera setup.
- One `<bowler>.json` per teammate (built once each from reference frames).
- Detection-resolution downscale cache may already exist from a previous bowler's run.

**Trigger**: Generate per-bowler clip directories for an entire team.

**Main flow**:
1. Run `extract` once per bowler, varying only `--bowler-target` and `--out`. Same `--video` and `--calibration` across all runs.
2. The downscale cache (`<source>.detect_0.5x.mp4`) is created during the first run and **reused for every subsequent bowler** in the team — no re-encoding.
3. Each run produces `<out>/shot_NN_<lane>.mp4` and `<out>/all_shots.mp4`.

**Post-condition**: One output directory per bowler; the source video is processed once (initial decode) but YOLO/identify per-frame work is repeated per bowler.

**Related requirements**: F4 (identification), F8 (downscale cache reuse), F10 (export), F11 (merge).

---

## UC-04 — Baker tournament with fixed-lane bowlers

**Actor**: A coach processing a 5-bowler Baker team match.

**Precondition**:
- Each team member is assigned a specific lane for the entire game.
- Two-lane camera framing showing both lanes.

**Trigger**: Extract per-bowler clips knowing each bowler appears on only one lane.

**Main flow**:
1. Calibrate as normal (both lanes).
2. For each bowler, run `extract --bowler-lane <lane>` to restrict the search to that bowler's assigned lane.
3. This halves per-frame work (one lane's signals computed instead of two) and eliminates the false-positive case of a teammate appearing in the other lane's approach.

**Post-condition**: Per-bowler clip directories; runtime ~50% faster than the cross-lane default.

**Related requirements**: F9.1 (`--bowler-lane`), F4.2 (foot-in-polygon filter).

---

## UC-05 — Processing a six-game match set

**Actor**: A user with a multi-game tournament recording session (e.g., 6 consecutive games per the 2026 PBA Colony Park Lanes Games Challenge).

**Precondition**:
- Six source video files in one directory.
- One `venue.json` (camera framing should be consistent across all games at the same venue).
- One `<bowler>.json` per bowler of interest.

**Trigger**: Generate per-game, per-bowler clip directories for the whole set.

**Main flow**:
1. Loop over the six games (shell `for` loop or batch script).
2. For each game, run `extract` with the same `--bowler-target` and `--calibration`.
3. Each game creates its own downscale cache (`game_N.detect_0.5x.mp4`).
4. Total runtime ≈ 6 × per-game extract time + 6 × downscale time (~5-10 min each, one-time per game).

**Alternative flow**:
- Pre-warm all downscale caches in advance with `--no-merge --downscale-factor 0.5` to spread the I/O cost from one long session.

**Post-condition**: Six output directories with per-shot clips and per-game merged reels for each tracked bowler.

**Related requirements**: F8 (downscale cache), full pipeline.

---

## UC-06 — Extract from a remote video source

**Actor**: A user who only has a URL to a hosted match video (YouTube, Vimeo, direct MP4, any yt-dlp-supported site).

**Precondition**:
- Working internet connection.
- Calibration and bowler target already built (or built from a downloaded copy first).

**Trigger**: Process a match without manually downloading the source video first.

**Main flow**:
1. Optionally run `fetch <URL>` to download and report the resolved local path (pre-warm the cache).
2. Run `extract --video <URL> ...` — yt-dlp downloads into the platform-default user cache and the pipeline uses that cached copy.
3. Subsequent runs against the same URL skip the download (cache hit).

**Alternative flow**:
- If the URL fails to resolve, check yt-dlp version (`yt-dlp --version`); the site's player may have changed and need a newer yt-dlp.

**Post-condition**: Cached download persists for future re-runs; output clips as usual.

**Related requirements**: F3 (video source resolution).

---

## UC-07 — Highlight-reel re-merge from existing clips

**Actor**: A user who already has per-shot clips and wants to re-merge them — possibly with a different subset or ordering.

**Precondition**:
- Directory of `shot_NN_<lane>.mp4` files from a prior `extract` run.

**Trigger**: Generate a fresh `all_shots.mp4` without re-running the full extract pipeline.

**Main flow**:
1. Run `merge --clips-dir clips/ --out reel.mp4`. Default pattern `shot_*.mp4` matches all per-shot clips.
2. Output is a stream-copied concatenation — instant, no quality loss.

**Alternative flow**:
- Use `--pattern shot_*_left.mp4` to merge only the left-lane shots, or hand-pick clips into a temp directory and merge that.
- Pass `--reencode` if clips have differing codec parameters that confuse ffmpeg's stream-copy concat.

**Post-condition**: Single merged video file.

**Related requirements**: F11.2 (standalone `merge` subcommand).

---

## UC-08 — Performance tuning on slow hardware

**Actor**: A user on an older laptop where default settings take too long.

**Precondition**:
- Default extract on the same machine is slower than acceptable (see [performance.md](../user/performance.md) for class-by-class expectations).

**Trigger**: Reduce per-game runtime at acceptable accuracy cost.

**Main flow**:
1. Try `--downscale-factor 0.33` (one step below default 0.5). Snap-down logic enforces the supported set {1.0, 0.75, 0.5, 0.4, 0.33, 0.25}; values in between snap down with a confirmation prompt (or auto-confirm with `--yes`).
2. If still slow, try `--downscale-factor 0.25` (the practical floor — pin polygons get small below this).
3. Spot-check the first 1–2 shots against known ground truth (e.g., first-shot timestamp) to confirm accuracy held.
4. Consider `--probe-interval 12` for very sparse-shot games (still must be < min shot on-approach duration).

**Alternative flow**:
- If results degrade unacceptably at lower downscale factors, the alternative is overnight processing at `--downscale-factor 0.5`.

**Post-condition**: Acceptable runtime / accuracy trade-off identified for this hardware class.

**Related requirements**: F8 (downscale), F7 (search strategies); see [performance.md](../user/performance.md).
