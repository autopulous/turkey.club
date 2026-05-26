# Performance and hardware expectations

[← Back to README](../../README.md)

This document sets realistic expectations for how long turkey.club takes to process a match on different hardware. The numbers are estimates — your mileage will vary with codec, frame rate, shot density, and background processes.

## Where the time goes

The dominant per-frame cost is **YOLOv8n person detection** running on CPU. Everything else (video decode, color-histogram match, frame-diff for pin motion, ffmpeg cut) is small in comparison.

Per-frame cost breakdown (full-resolution 720×1280 input on a mid-range Intel CPU, no GPU):

| Stage | Cost |
|---|---|
| Video decode (`cv2.VideoCapture.read`) | 5–10 ms |
| **YOLOv8n person detection** | **100–300 ms** ← dominates |
| Color-histogram identification (per matched person) | 5–10 ms |
| Pin-zone frame-difference | ~5 ms |

Total per-frame work: roughly **120–340 ms**. At 30 fps, that's 4–10 seconds of compute per 1 second of video.

The default `--downscale-factor 0.5` cuts YOLO cost roughly **3×** by halving each dimension (¼ the pixels). The probe-then-range search additionally skips ~85% of dead-time frames in a typical PBA-qualifying game.

## Runtime estimates by hardware class

All estimates below assume:

- A **41-minute (~74,000-frame) match video** at 30 fps (PBA qualifying length).
- **Default settings**: `--strategy probe --downscale-factor 0.5 --probe-interval 10`.
- **Linear baseline** is `--strategy linear --downscale-factor 1.0` for comparison.

| Hardware | YOLO @ 360×640 | Probe-strategy runtime | Linear-baseline runtime |
|---|---|---|---|
| **High-end desktop CPU** (Ryzen 9 7950X, i9-13900K, M3 Max) | ~30 ms/frame | **~5–10 min** | ~40–60 min |
| **Mid-range desktop CPU** (Ryzen 5 7600, i5-13400) | ~50 ms/frame | **~10–18 min** | ~70–110 min |
| **Modern laptop CPU** (Intel U/P series 12th-13th gen, M2/M3 Air) | ~70 ms/frame | **~15–30 min** | ~90–150 min |
| **Older laptop** (Intel 8th-10th gen, M1, Ryzen 4000) | ~120 ms/frame | **~30–60 min** | ~3–4 hours |
| **Low-end / very old** (Atom, Celeron, older mobile chips) | ~250 ms+/frame | **2+ hours** | impractical |
| **Single-board** (Pi 5, ARM SBC) | ~500 ms+/frame | hours | impractical |

If you're not sure which class your machine falls into: the project owner's reference run on a typical mid-range Windows laptop processed Game 1 of the 2026 PBA Colony Park Lanes match (41 min, 74,002 frames) in roughly 25–35 minutes with the default probe + 0.5× settings. That maps to the "modern laptop CPU" row above.

## When GPU acceleration arrives (planned, not yet implemented)

GPU support is on the roadmap (see [implementation_plan.md](../project/implementation_plan.md), phase 17). When it ships, expected speedups:

| GPU | YOLO @ 360×640 | Probe runtime | Linear baseline |
|---|---|---|---|
| **RTX 4090 / RTX 4080** | ~3 ms/frame | **~1–2 min** | ~6–10 min |
| **RTX 3070 / RTX 4060** | ~8 ms/frame | **~3–5 min** | ~15–25 min |
| **RTX 3050 / 2060 / older NVIDIA** | ~15 ms/frame | **~5–8 min** | ~30–45 min |
| **Apple Silicon MPS** (M-series) | ~20 ms/frame | **~7–10 min** | ~40–60 min |
| **AMD GPU (ROCm, Linux only)** | varies widely | similar to mid-NVIDIA | — |

GPU acceleration is roughly a **10–30× speedup** over CPU at the same resolution. A 41-minute match becomes a tea-break, not a lunch break.

## Tuning for your hardware

### If processing is too slow

| Lever | Effect | Trade-off |
|---|---|---|
| `--downscale-factor 0.25` | ~2× faster than 0.5 | Pin polygons get small (~19×9 px); slight false-negative risk on subtle pin motion. |
| `--probe-interval 12` | Fewer probes in dead time | Must stay < min shot on-approach duration (~12-15s). 12s is the practical ceiling. |
| `--bowler-lane <name>` | Halves work in two-lane footage | Only valid for Baker / single-lane formats; produces wrong results for cross-lane. |
| Close other heavy apps | YOLO benefits from CPU headroom | Browser tabs, Slack, IDEs all compete for CPU during the run. |

### If accuracy is a concern (fast hardware, want maximum quality)

| Lever | Effect | Trade-off |
|---|---|---|
| `--downscale-factor 1.0` | Full-resolution detection | 3–4× slower; small accuracy gain in practice (Clemons-class detection is robust at 0.5). |
| `--strategy linear` | Every-frame scan (no probe skipping) | 5–10× slower; useful as an oracle to validate a probe run. |
| `--probe-interval 6` | More frequent probes | Slightly more work; catches shots that probe-at-10s might miss in unusual rhythms. |

## Disk and memory expectations

### Disk

| Artifact | Size |
|---|---|
| Source video (41-min 720p phone footage) | 300–500 MB |
| Detection-resolution cache (`<source>.detect_0.5x.mp4`) | 60–120 MB |
| Per-shot clip | 3–10 MB |
| Merged highlight reel (21 shots × ~5 s each) | 30–80 MB |
| YOLOv8n weights | ~6 MB (one-time) |
| EasyOCR detector + recognizer models | ~150 MB (one-time) |

For a 6-game match set, plan for **2–4 GB total** including all detection caches and output clips.

### RAM

Peak working set during a run:

| Component | RAM |
|---|---|
| Python + PyTorch core | ~250 MB |
| YOLOv8n loaded | +50 MB |
| EasyOCR loaded (if used) | +300 MB |
| OpenCV frame buffer + signal accumulators | +50–100 MB |
| **Total typical** | **~500–800 MB** |

Tested on a machine with 8 GB RAM successfully. 4 GB is workable but tight if other apps are running.

### Network

Only relevant if you use `--video <URL>`. yt-dlp downloads the full source file into `~/.cache/turkey-club/videos/` before processing. Plan for:

- 200–500 MB per 41-minute PBA-qualifying-style video (HD).
- Up to 2 GB if the source is 1080p or higher.
- Re-runs against the same URL are free (cached).

## What if your hardware isn't enough?

Three options:

1. **More aggressive downscale**: `--downscale-factor 0.25` is the floor; below that, pin-motion detection becomes unreliable.
2. **Process overnight**: kick off a run, let it complete in the background while you sleep. The probe progress lines + ffmpeg `-stats` line let you check from any shell.
3. **Borrow GPU compute**: if you have access to a desktop with an NVIDIA GPU but typically work on a laptop, wait for GPU acceleration to land (phase 17 on the roadmap) and run there.

For routine processing of many matches per week, **investing in a desktop CPU upgrade or any NVIDIA GPU** is the highest-leverage hardware change. Below the "modern laptop CPU" row above, runtime starts to feel painful.

## Calibrating your expectations to *your* hardware

If you want a precise estimate before committing to a long run, time a small slice:

```
# Time how long a 30-second prefix takes
py -3 -c "
import time, cv2
from turkey_club.detect import detect_persons
cap = cv2.VideoCapture('match.mp4')
start = time.time()
for _ in range(900):  # 30s at 30fps
    ok, frame = cap.read()
    if not ok: break
    persons = detect_persons(frame)
elapsed = time.time() - start
print(f'{900/elapsed:.1f} fps; full 41-min match would take ~{74002/(900/elapsed)/60:.1f} min linear')
"
```

Halve that number for the probe strategy (rough rule of thumb). For two-lane PBA footage with ~21 shots per game, probe is typically 3-5× faster than linear.
