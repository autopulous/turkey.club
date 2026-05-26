# turkey.club

Extract frame-accurate per-shot clips of a named bowler from a fixed-camera match video, optionally merged into a single highlight reel.

Given a video and a bowler's identifying jersey color, the tool:
1. Finds every shot that bowler threw, from setup on the approach through pins-stop-falling.
2. Cuts each shot as a separate MP4 from the original source (full quality).
3. Optionally concatenates them into a chronological highlight reel.

## Why this exists

Bowlers, coaches, and tournament organizers want per-bowler views of a match without manually scrubbing through hours of footage. This tool automates the search and the cuts.

## How it works (one paragraph)

For each frame, the pipeline computes four per-lane signals: bowler-confidence (color-histogram match against the target's reference samples), pose-motion (bbox centroid delta), pin-motion (frame-difference inside the pin polygon), and a placeholder ball-reached-pins. A state machine over those streams identifies each shot as the sequence `setup → forward-motion onset → pin impact → pin settle`. Probe-then-range search skips dead time between shots. Detection runs against a cached downscaled copy of the source; clip cuts use the full-resolution source via ffmpeg.

Full documentation lives in [`docs/`](docs/), split into user-facing and project-management directories:

**User documentation** ([`docs/user/`](docs/user/)):
- [Prerequisites](docs/user/prerequisites.md) — what to install before this tool.
- [Installation](docs/user/installation.md) — getting this tool running, with troubleshooting.
- [Performance](docs/user/performance.md) — hardware expectations and tuning levers.

**Project management documentation** ([`docs/project/`](docs/project/)):
- [Goals](docs/project/goals.md) — outcome, motivation, scope, success criteria.
- [Use cases](docs/project/use_cases.md) — representative end-to-end scenarios.
- [Requirements](docs/project/requirements.md) — functional, non-functional, acceptance criteria.
- [Implementation plan](docs/project/implementation_plan.md) — architecture, module map, phased status.

**Project meta** (at project root):
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — how to contribute.
- [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) — community standards.
- [`SECURITY.md`](SECURITY.md) — vulnerability reporting.
- [`CHANGELOG.md`](CHANGELOG.md) — release history.

## Bowling "Lane Policy" formats supported by turkey.club

| Format | Lane policy | Shots per bowler per game | Notes |
|---|---|---|---|
| PBA qualifying / match play | Cross-lane rotation each frame | 12–21 | Default |
| Doubles | Each bowler alternates lanes | 5–11 | Both lanes; alternates frames |
| Scotch Doubles | Bowlers alternate shots and the team alternates lanes each frame | 5–11 | Both lanes |
| League play | Cross-lane rotation | 12–21 | Both lanes |
| Baker (traditional / half / double) | Fixed lane per bowler | 1–11 (varies with team size: ~2-6 for 5-bowler, ~3-11 for half, ~1-3 for double) | Use `--bowler-lane` |
| Singles practice | Single lane or alternating pair | 12–21 per game | Use `--bowler-lane` if single |
| Multi-bowler practice | Mixed | varies by group size | Configurable |
| Open bowling | Chaotic, irregular | 12–21 per game | Both lanes |

> Shot-count ranges assume a standard 10-frame game. A perfect game (all strikes) is **12 balls total** (10 frames + 2 bonus); a fully-open game (no strikes or spares except possibly the 10th) tops out at **~21 balls**. Per-bowler ranges are derived from how many of those balls each bowler throws in the format.

A format preset `--format <preset>` option is planned to bundle these settings.

## Installation

Two-step process:

1. Install the prerequisites (Python 3.10+, ffmpeg, git). See **[docs/user/prerequisites.md](docs/user/prerequisites.md)** for per-platform instructions.
2. Install the tool itself. See **[docs/user/installation.md](docs/user/installation.md)** for the full walkthrough including troubleshooting.

Short version (after prerequisites are in place):

```
git clone <repo-url>
cd turkey.club
py -3 -m pip install -e .[dev]
```

This exposes a `turkey-club` command and a `py -3 -m turkey_club.cli` fallback.

## Quick start

### 1. Grab a reference still for each lane

You need one still frame per lane the target bowler will appear on:

- **Cross-lane formats** (PBA qualifying, Doubles, League): one still for the **left** lane and one for the **right**.
- **Baker / singles formats**: one still for whichever single lane the bowler uses.

In each still, the target bowler should be clearly visible standing somewhere in that lane's approach area — not necessarily mid-release; even just standing near the ball return works as long as their upper back (where the jersey color samples come from) is visible.

Three ways to extract a still from your match video:

#### Option A — VLC (easiest, GUI)

1. Open the match video in VLC.
2. Scrub or play until the target bowler is visible on the **left** lane.
3. Pause.
4. **Video** menu → **Take Snapshot** (or press `Shift+S`).
5. VLC saves the snapshot to your Pictures folder by default — see VLC's `Tools → Preferences → Video → Video snapshots` to change the directory.
6. Rename / move the snapshot to `stills/left.jpg` next to your video file.
7. Repeat steps 2-6 for the **right** lane → `stills/right.jpg`.

#### Option B — Microsoft Photos (Windows, no install needed)

Exact menu wording varies between Windows / Photos versions, but the flow is:

1. In File Explorer, right-click the match video file → **Open with** → **Photos**.
2. Use the scrubber at the bottom of the Photos window to navigate to a moment where the target bowler is on the **left** lane. Pause.
3. Look for one of these (Photos has changed across versions):
   - **Older Photos** (Win 10 / early Win 11): click **Edit & Create** → **Save photos from a video**. Fine-tune the position with the scrubber, click **Save a photo**, save as `stills\left.jpg`.
   - **Newer Photos** (Win 11 2023+, with Clipchamp integration): the "Save photos from a video" feature may have moved or been removed. Use the screenshot fallback below.
4. Repeat steps 2-3 for the **right** lane → `stills\right.jpg`.

**Screenshot fallback** (works on any Photos version):

1. Pause at the target moment in Photos.
2. Maximize the Photos window so the video frame fills as much screen as possible.
3. Press `Win + Shift + S` to launch Snipping Tool.
4. Drag-select **just the video frame area** (avoid the UI borders / toolbars).
5. Click the notification that appears (bottom-right) to open the snip, then **File** → **Save As** → `stills\left.jpg`.
6. Repeat for the right lane.

> ⚠️ Screenshot-based capture produces an image whose pixel dimensions depend on your display, not the source video's native resolution. The pipeline will still work, but calibration polygons drawn against a screenshot-resolution still won't match the source video — **calibrate against the same image format you'll detect on**. If you took screenshots, calibrate with those screenshots. If you used Option A (VLC) or Options C / D (ffmpeg) which preserve source resolution, calibrate with those.

#### Option C — ffmpeg at a known timestamp (scriptable, exact)

If you know roughly when the bowler appears on each lane (from scrubbing the video):

```
mkdir stills
ffmpeg -ss 01:35 -i match.mp4 -frames:v 1 stills/left.jpg
ffmpeg -ss 03:42 -i match.mp4 -frames:v 1 stills/right.jpg
```

- `-ss <MM:SS>` seeks to that timestamp.
- `-frames:v 1` grabs exactly one frame and exits.

Replace `01:35` / `03:42` with the moments where the bowler is on each lane. Use `MM:SS` or `HH:MM:SS` format.

#### Option D — ffmpeg sample sheet (browse and pick)

If you don't know in advance when the bowler appears, extract one frame per second across the whole match and browse the results:

```
mkdir -p stills/samples
ffmpeg -i match.mp4 -vf "fps=1" stills/samples/frame_%04d.jpg
```

That produces `frame_0001.jpg`, `frame_0002.jpg`, … — one per second (so a 41-minute match yields ~2,460 small JPEGs). Open the `stills/samples/` directory in your file explorer, find one clean shot of the bowler on each lane, then copy and rename them:

```
cp stills/samples/frame_0095.jpg stills/left.jpg
cp stills/samples/frame_0222.jpg stills/right.jpg
```

(You can delete `stills/samples/` afterward.)

#### Tips for choosing a good reference frame

- The bowler's **upper back must be clearly visible** — this is where the color samples are drawn for identification.
- Prefer **static stance** (settling on the approach, holding the ball) over mid-release; motion blur smears the color signature.
- Avoid frames where another bowler / spectator is overlapping or directly behind the target.
- Adequate lighting; not too dark, not blown out by overhead lights.
- One reference per lane is enough; more than that helps but the additional samples have diminishing returns.

### 2. Calibrate the venue (one-time, per camera setup)

```
py -3 -m turkey_club.cli calibrate \
    --frame stills/left.jpg \
    --frame stills/right.jpg \
    --out venue.json \
    --lane left --lane right
```

> ⚠️ **This step is interactive.** The command opens an **OpenCV GUI window** on your desktop showing the reference still you supplied. You'll mark polygon zones by clicking with your mouse. You cannot do this step over SSH without X-forwarding or VNC — it needs a display.

You'll mark **three zones per lane** (six total for a two-lane setup), in this fixed order:

1. **Left lane → approach**
2. **Left lane → lane**
3. **Left lane → pin**
4. *(window swaps to the right-lane reference still)*
5. **Right lane → approach**
6. **Right lane → lane**
7. **Right lane → pin**

A top-of-window banner tells you which zone you're currently marking.

#### The three zones — what each is, and how the tool uses it

**Approach zone** — the wooden / floor area where the bowler **stands** before and during the release. From the camera's perspective, this is the front portion of each lane, between the ball return and the foul line.

- *How the tool uses it*: Every video frame, YOLOv8 detects all persons. A person whose **foot position** (bottom-center of their bounding box) lies inside this polygon is a **candidate to be the target bowler**. The pipeline then runs the color-histogram check on their upper back to confirm identity.
- *Secondary use*: Tracking the matched bowler's bounding-box centroid frame-to-frame here gives the **pose-motion signal** — stationary = setup, big jump = forward motion (release approach).

**Lane zone** — the synthetic / oiled lane surface between the foul line and the pins. From the camera angle (behind the lanes), this is a long trapezoid that **narrows toward the top of the frame** because of perspective foreshortening.

- *How the tool uses it*: Reserved for ball-motion detection (frame-difference inside this polygon, isolated from the approach and pin zones). The current pipeline doesn't strictly require this signal — pin-motion is sufficient for impact detection — but the zone is calibrated for future enhancements (e.g., ball-position tracking, foul-line crossings).

**Pin zone** — the pin deck at the far end of the lane, where the pins stand. From the camera angle this is a **small rectangle** at the top of the frame, just barely covering the pin triangle area.

- *How the tool uses it*: Every frame, the pipeline computes the **mean absolute frame-difference** of pixels inside this polygon. When the ball hits the pins, motion spikes (high frame-diff). When pins finish falling and settle, motion returns to near zero. This is the **impact + settle** signal that bounds the **end** of every shot clip:
  - **Impact** = first frame where pin-motion exceeds threshold after the bowler's forward-motion onset.
  - **Settle** = pin-motion drops below threshold for ≥ 12 consecutive frames.
  - **`end_frame`** = settle + 0.3 s pad.

#### GUI controls

| Action | Effect |
|---|---|
| **Left click** | Add a polygon vertex at the cursor. Numbered marker appears. |
| **Right click** *(or press `U`)* | Undo last vertex. |
| **Enter** | Finalize the current zone (need ≥ 3 vertices) and advance to the next zone. |
| **Esc** | Cancel calibration entirely — no JSON is written. |

While you're clicking, the window shows:
- Numbered dots at each vertex.
- A polyline / closed polygon updates as you add points.
- **Previously-finalized zones** for prior lanes are drawn semi-transparent for spatial reference (since the camera is fixed, the right-lane zones should be at roughly mirror-image positions to the left-lane zones in the right-lane reference still).

#### How to bound each zone — practical guidance

**Approach zone (~4-8 vertices)**:
- Trace the **wooden floor area** where the bowler stands.
- Include from the ball return up to (but not crossing) the foul line.
- **Exclude**: the ball return mechanism, carpet/seating behind the approach, the synthetic lane surface itself.
- A pentagonal or hexagonal shape usually fits best. Don't worry about a few pixels of slop — the pipeline uses foot-bottom-center for the inside-polygon test.

**Lane zone (4 vertices = trapezoid is ideal)**:
- Mark the four corners of the **synthetic lane surface** as it appears in the camera:
  1. Bottom-left corner (near the foul line, gutter side).
  2. Bottom-right corner (near the foul line, divider side).
  3. Top-right corner (just before the pins, divider side).
  4. Top-left corner (just before the pins, gutter side).
- The lane appears as a perspective-foreshortened **trapezoid**, wider at the bottom (close to camera) and narrower at the top (far from camera).
- **Exclude** the gutters on either side and the pin deck.

**Pin zone (4 vertices)**:
- Mark a **small rectangle** that **just barely covers the pin triangle**.
- Tight is better than generous — a large pin zone catches scoreboard updates, overhead light reflections, and adjacent-lane activity, producing false impact signals.
- Typical size in a 720×1280 phone shot of a typical bowling alley: ~75×35 pixels per lane.

#### When you finish

After the sixth polygon (right lane → pin) is confirmed with **Enter**, the window closes and the tool writes the calibration to the path you passed via `--out` (e.g., `venue.json`).

The saved file is just JSON — you can open it to verify, version-control it, or hand-edit polygon vertices later. Structure:

```json
{
  "lanes": [
    {
      "name": "left",
      "approach_zone": [[x1, y1], [x2, y2], ...],
      "lane_zone":     [[x1, y1], [x2, y2], ...],
      "pin_zone":      [[x1, y1], [x2, y2], ...]
    },
    {
      "name": "right",
      "approach_zone": [...],
      "lane_zone":     [...],
      "pin_zone":      [...]
    }
  ],
  "frame_width": 720,
  "frame_height": 1280
}
```

#### Verifying the calibration

Before running the long `extract` pipeline on a 41-minute video, sanity-check that your zones actually align with the action:

```
py -3 -m turkey_club.cli preview \
    --video match.mp4 \
    --calibration venue.json \
    --out overlay.mp4
```

This renders **colored semi-transparent overlays** of each zone onto every frame of the video. Open the resulting `overlay.mp4` in any video player and scrub through. You should see:
- The **approach zones** light up when bowlers stand on them.
- The **lane zones** highlight the synthetic surface during ball travel.
- The **pin zones** light up at the pin decks.

If any zone is misplaced, re-run `calibrate` to redo it. Calibration is the fastest step of the workflow (~2 minutes of clicking) — re-doing it is cheap.

Verify with overlay:

```
py -3 -m turkey_club.cli preview \
    --video match.mp4 \
    --calibration venue.json \
    --out overlay.mp4
```

### 3. Build a bowler target

A **bowler target** is a small JSON file containing the target bowler's display name plus a few thousand sampled pixel colors from their jersey's upper back. The pipeline uses these samples to identify the bowler across the match via HSV histogram-distance matching.

Until a dedicated CLI subcommand lands (planned), the target is built with a short Python script. Below is a worked example for a bowler named **"Clemons"** with two reference stills (one per lane).

#### Step 3a — Write the build script

Save the following as `build_bowler_target.py` next to your video file. Adjust the **bowler name** and the **(image, lane_name) pairs** for your case:

```python
from pathlib import Path
from turkey_club.config import VenueCalibration
from turkey_club.identify import build_bowler_target_from_references

# Project files live next to this script.
base = Path(__file__).parent

# Load the venue calibration from Step 2.
venue = VenueCalibration.load(base / "venue.json")

# One (image_path, lane_name) pair per reference still.
# Lane names MUST match what you used in Step 2's `--lane` arguments.
references = [
    (base / "stills" / "left.jpg",  "left"),
    (base / "stills" / "right.jpg", "right"),
]

target = build_bowler_target_from_references(
    name="Clemons",                # Bowler's display name (used in OCR matching too)
    references=references,
    venue=venue,
    samples_per_image=2000,        # ~2000 pixels per reference is a good baseline
)

out_path = base / "clemons.json"
target.save(out_path)
print(f"Saved {target.name!r} target with {len(target.shirt_color_samples)} samples -> {out_path}")
```

#### Step 3b — Run the script

```
py -3 build_bowler_target.py
```

Expected output:

```
Saved 'Clemons' target with 4000 samples -> .../clemons.json
```

(2,000 samples × 2 reference images = 4,000 total. First run also downloads YOLOv8n weights ~6 MB if not already cached.)

#### What's happening internally

1. Each reference image is loaded.
2. **YOLOv8** detects all persons in the image.
3. For each reference, the function picks the **single person whose foot position is inside the named lane's approach polygon** — that's your target bowler in that frame.
4. It crops the **upper-back region** of that person's bounding box (the vertical band ~18 % to ~55 % of bbox height, where the jersey name sits).
5. **2,000 random pixels** are sampled from the crop.
6. Samples from all reference images are concatenated and saved as the `shirt_color_samples` list in the output JSON.

#### Variations

- **Single-lane format (Baker / singles)** — pass one tuple:
  ```python
  references = [(base / "stills" / "left.jpg", "left")]
  ```
- **More reference frames per lane** (for lighting variation) — add more tuples:
  ```python
  references = [
      (base / "stills" / "left_early.jpg", "left"),
      (base / "stills" / "left_late.jpg",  "left"),
      (base / "stills" / "right.jpg",      "right"),
  ]
  ```
- **More samples per image** — increase `samples_per_image=4000` (or `8000`) if you want a richer histogram. Diminishing returns above ~4000 per image.

#### Verifying the result

Open `clemons.json` in a text editor — you should see:

```json
{
  "name": "Clemons",
  "shirt_color_samples": [
    [42, 38, 35],
    [51, 45, 41],
    ...
  ]
}
```

The list should contain roughly `samples_per_image × len(references)` entries (3-tuples of BGR values in 0-255). The `name` should match what you passed.

#### Troubleshooting

- **`No person detected with foot in lane 'left' approach zone for stills/left.jpg`** — the reference frame doesn't have a detected person whose foot lands inside the calibrated left-approach polygon. Either: (a) pick a different reference frame where the bowler is clearly in approach, or (b) verify your calibration with `preview` and re-do Step 2 if a zone is misplaced.
- **`Could not read reference image`** — the image path is wrong (typo, wrong working directory) or the file is corrupted.
- **`KeyError: 'left'` from `venue.lane()`** — the lane name passed (e.g., `"left"`) doesn't match the names used during Step 2's calibration. Check the `lanes[].name` values in `venue.json`.

### 4. Extract shots

```
py -3 -m turkey_club.cli extract \
    --video match.mp4 \
    --bowler-target clemons.json \
    --calibration venue.json \
    --out clips/
```

This produces:
- `clips/shot_01_left.mp4`, `clips/shot_02_right.mp4`, …
- `clips/all_shots.mp4` — merged highlight reel (default; use `--no-merge` to skip)

Options worth knowing:

| Option | Default | Notes |
|---|---|---|
| `--strategy probe` | `probe` | `probe` is fast; `linear` is exhaustive (oracle). |
| `--probe-interval 10` | `10.0` | Seconds between probes. Must be < min shot on-approach duration. |
| `--bowler-lane left` | (unset → all) | Restrict to one lane (Baker format). |
| `--downscale-factor 0.5` | `0.5` | Detection-time downscale. Snap-down to {1.0, 0.75, 0.5, 0.4, 0.33, 0.25}. |
| `--no-merge` | (merge on) | Skip the highlight-reel concatenation step. |

### 5. Run on remote sources too

`--video` accepts any yt-dlp-supported URL:

```
py -3 -m turkey_club.cli extract \
    --video "https://youtube.com/watch?v=…" \
    --bowler-target clemons.json --calibration venue.json --out clips/
```

### 6. About the download cache

When you pass a URL to `--video`, yt-dlp downloads the video into the platform-default user cache directory and **subsequent runs that name the same URL skip the download entirely**.

#### Where the cache lives

| Platform | Cache directory |
|---|---|
| Linux / macOS | `~/.cache/turkey-club/videos/` |
| Windows | `%USERPROFILE%\.cache\turkey-club\videos\` |

(Both resolve from `Path.home() / ".cache" / "turkey-club" / "videos"` — same per-user concept on every platform.)

You can override the location per-run with `--cache-dir <path>`, e.g., to point at a shared network drive so multiple users on the same LAN reuse downloads.

#### How files are named

yt-dlp's output template is `%(id)s.%(ext)s`, so a YouTube video at `https://youtube.com/watch?v=aZ1QRX9Hkqw` lands as:

```
~/.cache/turkey-club/videos/aZ1QRX9Hkqw.mp4
```

The same URL on every subsequent run resolves to the same filename → cache hit → no download.

#### When the cache helps

- **Iterating on bowler-target tuning against the same match** — change the bowler-target JSON, re-run `extract`, no re-download.
- **Building multiple bowler targets from the same match** — one download, N `extract` runs (one per bowler).
- **Sharing across teammates** — point `--cache-dir` at a shared filesystem so the first teammate to process a match pays the download cost once.
- **Recovering from a crash** — if `extract` died mid-run, the cached download survives; re-run picks up from where the pipeline restarted.

#### When it's safe to delete

- You've finished extracting all the bowlers you care about from that match.
- The hosted video has been removed / replaced and you're not going to re-process the original.
- You want to force a fresh download because the host re-uploaded a longer or re-edited version under the same URL.

A typical 6-game match set occupies **2-4 GB** of download cache total; if disk space is tight, clearing the cache after you're done with a match set is a reasonable workflow.

#### When NOT to delete

- You're still iterating on calibration, bowler target, or threshold tuning for that match — deleting forces a re-download (200-500 MB per match) on the next run.
- You plan to extract more bowlers from the same match later.
- The hosted video might disappear before you'd be able to re-download it.

#### How to delete

```
# Linux / macOS / Git Bash
rm -rf ~/.cache/turkey-club/videos/

# Windows PowerShell
Remove-Item -Recurse -Force "$env:USERPROFILE\.cache\turkey-club\videos"
```

To delete a specific cached video without nuking the rest, use the YouTube video ID (or whatever filename yt-dlp produced):

```
# Linux / macOS / Git Bash
rm ~/.cache/turkey-club/videos/aZ1QRX9Hkqw.mp4

# Windows PowerShell
Remove-Item "$env:USERPROFILE\.cache\turkey-club\videos\aZ1QRX9Hkqw.mp4"
```

#### Related caches you might also want to manage

| Cache | Location | Size | Cost to regenerate |
|---|---|---|---|
| Source video downloads | `~/.cache/turkey-club/videos/` | 200 MB – 4 GB | Re-download (network bound) |
| Detection-resolution downscale | `<source>.detect_<scale>x.mp4` next to each source video | 60-120 MB per match | ~5-10 min ffmpeg re-encode |
| YOLOv8n weights | `yolov8n.pt` in cwd or `~/.config/Ultralytics/` | ~6 MB | ~3 sec re-download |
| EasyOCR detector + recognizer | `~/.EasyOCR/` | ~150 MB | ~30 sec re-download (only fires if you actually use OCR) |

The detection-resolution downscale (`*.detect_<scale>x.mp4`) is the most painful to regenerate — keep it around if you plan to re-process the same match.

## Status

- Phases 1–7 of the pipeline (calibrate, identify, segment, extract, export, merge) are implemented and validated on PBA qualifying footage.
- Probe-then-range search and the downscale cache are live optimizations.
- Format presets and a `build-bowler` CLI subcommand are planned. See [implementation_plan.md](docs/project/implementation_plan.md) for the full backlog.

## License

[MIT](LICENSE) © 2026 John Hart
