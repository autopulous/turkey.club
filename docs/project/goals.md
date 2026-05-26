# Goals — turkey.club

## Outcome

A reusable command-line tool that processes a recorded bowling match video and produces frame-accurate, ready-to-publish per-shot clips of a specific named bowler — covering the moment they set up on the approach through the moment the pins stop moving — plus an optional merged highlight reel of all their shots in chronological order.

## Motivation

Bowlers, coaches, and tournament organizers want a per-bowler view of a game without manually scrubbing through a multi-hour recording to find each shot and trim it. Existing video editors require frame-by-frame human attention; automated sports-analytics tools target broadcast video with fixed branding, not amateur tournament recordings. Filling this gap allows John (and others with similar needs) to publish or review individual-bowler reels from full-match footage at scale.

## Stakeholders

- **Primary user**: John Hart — author and primary user; PBA-experienced; processes match footage from his own tournament videos.
- **Secondary users**: other bowlers / coaches / tournament organizers with a fixed-camera setup and a similar need.
- **Out-of-scope users (for now)**: broadcast video editors, real-time streaming systems, multi-camera fusion pipelines.

## Scope

### In scope
- Fixed-camera amateur recordings (e.g., phone on tripod behind the lanes), one or two lanes in frame.
- Bowling formats: PBA qualifying / match play, doubles, league, Baker (traditional / half / double), singles practice, multi-bowler practice, open bowling.
- Identifying a single named target bowler across all their shots in a match.
- Local video files and remote URLs (anything yt-dlp supports — YouTube, direct MP4, etc.).
- Per-shot clip extraction at full source resolution.
- Optional merged highlight reel.

### Out of scope
- Broadcast video with shot-cut transitions or multiple camera angles.
- Real-time / live-streaming processing.
- Tracking multiple bowlers simultaneously in a single run.
- Auto-detecting zones from video (manual one-time calibration is the design).
- Cloud / GPU rendering — runs locally on a Windows laptop.

## Success criteria

A run is considered successful when:

1. **Completeness** — the tool finds every shot the target bowler threw, with no more than 1 false negative per 10 shots.
2. **Tight boundaries** — start of each clip is between 0.3s and 0.7s before the bowler's first forward motion; end is within 0.5s after the last visible pin motion.
3. **No false positives** — fewer than 1 false positive per 10 true shots. False positives from teammates' shots are the primary risk.
4. **Reusable artifacts** — venue calibration and bowler target are built once per venue / bowler and reused across all games at that venue.
5. **Idempotent** — re-running the same `extract` command produces the same shot list and clips.
6. **Manageable runtime** — a 41-minute PBA-qualifying game completes in 30 minutes or less on a typical Windows CPU laptop (with the default 0.5× downscale).

## Constraints

- **CPU-only assumed** — must work without an NVIDIA GPU. GPU optional acceleration is a future enhancement, not a requirement.
- **Windows-first toolchain** — the project owner runs Windows 11. PowerShell + Git Bash. ffmpeg via winget. `py -3` launcher rather than bare `python`.
- **Fixed-camera assumption** — calibration must remain valid for the duration of a single video; if framing changes, recalibrate.
- **Multiple matches per session** — six-game match sets are common; per-match runtime matters because the cost compounds.
- **Multiple bowlers per match** — same calibration can serve multiple bowler-extract passes; per-bowler target file is the additional artifact per bowler.

## Time horizon

- **Near term (this iteration)**: validate end-to-end on the 6-game 2026 PBA Colony Park Lanes Games Challenge - Non-Champion Event match set with the Clemons target. Tune thresholds and runtime to acceptable ranges.
- **Medium term**: add the format-preset CLI (auto-restrict to lanes / sanity-check expected shot counts), expose `build-bowler` as a first-class CLI command.
- **Long term**: optional GPU acceleration; broadcast-video support (requires shot-cut detection + per-shot recalibration).

## Non-goals

- Beautifully edited highlight reels with overlays, music, scoring graphics — out of scope; this tool produces raw clips that a downstream editor can polish.
- Bowler scoring / accuracy analytics — adjacent problem, separate tool.
- Cross-bowler comparison reports — a higher-level tool could consume this tool's output.
