# Installation

[← Back to README](../../README.md)

This guide installs the turkey.club tool itself. Before starting, confirm Python, ffmpeg, and git are working — see [prerequisites.md](prerequisites.md).

## 1. Clone the repository

```
git clone <repo-url> turkey.club
cd turkey.club
```

(Replace `<repo-url>` with the actual repository URL once it's published.)

## 2. Install the package in editable mode

Editable mode (`-e`) means source changes take effect immediately without reinstalling — useful for iterating on the code.

```
py -3 -m pip install -e .[dev]
```

(On macOS / Linux: `python3 -m pip install -e .[dev]`. The `[dev]` extra adds pytest.)

This installs:

| Package | Purpose | Approx size |
|---|---|---|
| `typer` | CLI framework | small |
| `opencv-python` | image decoding, polygon ops, frame-diff | ~70 MB |
| `numpy` | array math | small |
| `mediapipe` | pose estimation (currently unused but installed) | ~80 MB |
| `easyocr` | OCR for jersey names (fallback path) | ~5 MB + ~750 MB torch |
| `ultralytics` | YOLOv8 person detection | ~50 MB + shared torch |
| `yt-dlp` | URL → local file resolution | small |
| `pytest` | test runner (dev extra) | small |

**Note:** easyocr and ultralytics both depend on torch. On Windows CPU-only, torch is ~750 MB after extraction. The full install downloads roughly 1.5 GB and takes 5-15 minutes depending on your network.

If the install gets killed partway through, you can resume:

```
py -3 -m pip install -e .[dev]
```

Pip re-uses cached wheels, so the second run is much faster.

## 3. First-run model downloads

The first time you run `extract`, two additional asset downloads happen automatically:

- **YOLOv8n weights** (~6 MB) — `ultralytics` downloads `yolov8n.pt` into the current working directory or `~/.config/Ultralytics/`. Auto-cached for subsequent runs.
- **EasyOCR detector + recognizer models** (~150 MB total) — `easyocr` downloads into `~/.EasyOCR/` on first use. Auto-cached.

You don't need to do anything for these; they happen on the first `extract` invocation. Just be aware the first run is ~30 seconds slower than subsequent runs.

## 4. Smoke test

Confirm the CLI loads:

```
py -3 -m turkey_club.cli --help
```

You should see the four subcommands: `calibrate`, `extract`, `merge`, `preview`, `fetch`.

Confirm Python can import every module without errors:

```
py -3 -m pytest tests/
```

You should see all tests pass (CLI loads, modules import, `resolve_source` handles local files).

## 5. (Optional) Add the entry-point to PATH

After `pip install -e .[dev]`, a `turkey-club` executable is created in your Python `Scripts/` directory. On Windows this is typically:

```
C:\Program Files\Python\Python312\Scripts\turkey-club.exe
```

If `Scripts/` is on your PATH (the python.org installer puts it there by default), you can invoke the tool directly:

```
turkey-club --help
```

If not on PATH, just keep using the `py -3 -m turkey_club.cli ...` form.

## 6. Verify with a real run (optional but recommended)

Use the `fetch` subcommand to sanity-check yt-dlp resolution:

```
py -3 -m turkey_club.cli fetch "https://example.com/some-bowling-video.mp4"
```

It should download the file (or echo the path if you passed a local file) and print the resolved local path. If this works, the full extract pipeline is ready to use.

## Troubleshooting

### `ModuleNotFoundError: No module named 'turkey_club'`

The install didn't finish. Check pip's output for errors. Common causes:

- Background process was killed before pip wrote the editable install record. Re-run `pip install -e .[dev]`.
- Wrong Python interpreter — `pip` may have installed to a different Python than `py -3` resolves to. Verify with `py -3 -m pip show turkey-club`.

### `OSError: [WinError 123]` from calibrate or extract

A path argument contains a newline or other illegal character — usually from PowerShell paste-wrapping a long quoted argument. Re-type the command on a single line, or define a shell variable:

```powershell
$dir = "C:/path/to/your/match/dir"
py -3 -m turkey_club.cli calibrate --frame "$dir/stills/left.jpg" --out "$dir/venue.json" --lane left
```

### `ffmpeg failed for ...`

The clip-cut step couldn't run ffmpeg. Check:

- `ffmpeg -version` succeeds independently.
- The source file isn't open in another program (Windows file-locking).
- Free disk space on the output drive.

### Heavy ML install (torch + easyocr + ultralytics) takes forever

This is expected — total ~1.5 GB download and ~3 GB extracted to site-packages. On a slow network it can be 20+ minutes. Pip is making progress even when it appears stuck on "Installing collected packages: …" — that line stays for the entire extraction phase.

If it truly hangs (no disk activity for 5+ minutes), kill and resume; cached wheels make the second attempt much faster.

### Cannot use the `extract` interactive prompt in a background task

The `--downscale-factor` validation prompts for confirmation when the input value isn't in the supported set. In background runs stdin is closed and the prompt would hang. Use `--yes` to auto-confirm:

```
py -3 -m turkey_club.cli extract --downscale-factor 0.45 --yes ...
```

Or pass an exactly-supported value: `{1.0, 0.75, 0.5, 0.4, 0.33, 0.25}`.

## Next steps

You're installed. Head to the [README quick-start](../../README.md#quick-start) to extract your first set of clips.

Related user documentation:

- [Performance](performance.md) — hardware-tier runtime expectations and tuning levers.

Project design and roadmap:

- [Goals](../project/goals.md) — what the tool does and why.
- [Requirements](../project/requirements.md) — what the system must do.
- [Implementation plan](../project/implementation_plan.md) — architecture and phased status.
