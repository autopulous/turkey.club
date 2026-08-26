---
name: project-performance-constraints
description: CPU YOLO is the per-frame bottleneck (~200ms/frame). Downscale + frame-skip + GPU are the planned optimization levers.
metadata:
  type: project
---

Per-frame cost breakdown on CPU (Windows laptop, no GPU, observed 2026-05-25):

| Stage | Cost |
|---|---|
| Video decode (`cv2.VideoCapture.read`) | 5-10 ms |
| **YOLOv8n person detection (720x1280 frame)** | **100-300 ms** ← dominates |
| Color-histogram identification per person | 5-10 ms |
| Pin-zone frame-diff | 5 ms |

Total: ~120-340 ms per frame. At 30-fps video, **1 sec of video = 4-10 sec of compute**. Full 41-min video linear scan = ~4 hours.

**Probe strategy reduces total compute by skipping dead-time frames** (~85% of game runtime), but doesn't change per-frame cost in range-expand windows. Estimated probe-strategy runtime on PBA qualifying: ~85 min (still slow; ~21 shots × 40s window × 30fps × 200ms).

**Planned optimization levers:**
1. **Downscale input to YOLO (720→360 or 240)**: estimated **2-3×** speedup. Output clips still cut from full-res source — quality unaffected.
2. **Frame-skip in range-expand windows (every 3rd frame)**: estimated **3×** speedup. Requires adjusting `stationary_pose_frames` and `pin_settle_frames` in `SegmentationParameters` to compensate for reduced temporal resolution.
3. **Motion-gate YOLO (background subtraction first)**: estimated **2×** speedup in dead-time regions. Skip YOLO when no motion in approach zone.
4. **GPU + CUDA torch**: estimated **10-50×** speedup. Requires NVIDIA GPU + torch reinstall with `cu*` wheels.

**Combined downscale + frame-skip estimated: 6-9× speedup** with no hardware dependency. Likely the right next optimization to pursue.

**Why:** Processing the 6-game match set with the current pipeline (~4 hours linear or ~85 min probe per game × 6 = days of CPU compute) is impractical for routine use. The downscale + frame-skip combination gets per-game runtime to ~10-30 min — usable.

**How to apply:** When implementing the downscale optimization, downscale ONLY inside the detection pipeline (cv2.resize before YOLO inference). The ffmpeg export cut uses the original-resolution source file, so output quality is unchanged. Use bilinear interpolation. Test detection accuracy on a few sample frames before committing. Related: [[project-search-strategy]].
