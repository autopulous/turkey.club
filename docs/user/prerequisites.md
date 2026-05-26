# Prerequisites

[← Back to README](../../README.md)

Before installing turkey.club you need three tools on your system: **Python 3.10+**, **ffmpeg**, and **git**. An NVIDIA GPU is optional and only matters once GPU acceleration lands (planned, not implemented today).

This guide covers Windows 11, macOS, and Linux. Pick your platform.

---

## 1. Python 3.10 or newer

The tool is tested on Python 3.12. Anything from 3.10 onward should work.

### Windows 11

**Recommended: official installer from python.org.**

1. Open <https://www.python.org/downloads/windows/>.
2. Download the latest "Windows installer (64-bit)" for Python 3.12 or newer.
3. Run the installer. On the first screen, **tick "Add python.exe to PATH"** and **tick "Use admin privileges when installing py.exe"** so the `py` launcher is installed system-wide.
4. Click "Install Now".

Verify:

```powershell
py -3 --version
```

You should see `Python 3.12.x` (or whatever version you installed).

> ⚠️ **Avoid the Microsoft Store Python stub.** If `python` or `python3` on your PATH points to a Microsoft Store App Execution Alias, the command will exit non-zero on real invocation. Always use **`py -3`** on Windows — it resolves to the real interpreter via the launcher installed by python.org.

Alternative (Windows): `winget install Python.Python.3.12`

### macOS

```bash
brew install python@3.12
```

Verify: `python3 --version`

### Linux (Ubuntu / Debian)

```bash
sudo apt update && sudo apt install -y python3.12 python3.12-venv python3-pip
```

Verify: `python3.12 --version`

For other distros, use your package manager (`dnf`, `pacman`, etc.) or build from source.

---

## 2. ffmpeg

ffmpeg is used for both clip extraction (frame-accurate seeking) and detection-video downscaling. It MUST be on PATH.

### Windows 11

**Recommended: winget.**

Open PowerShell and run:

```powershell
winget install Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
```

After installation, **open a fresh PowerShell window** so the updated PATH is picked up. Alternatively, refresh PATH in the current window:

```powershell
$env:Path = ([Environment]::GetEnvironmentVariable('Path','Machine'), [Environment]::GetEnvironmentVariable('Path','User')) -join ';'
```

Verify:

```powershell
ffmpeg -version
```

You should see `ffmpeg version 8.x.x-full_build-www.gyan.dev …` (Gyan builds are the canonical Windows distribution).

### macOS

```bash
brew install ffmpeg
```

Verify: `ffmpeg -version`

### Linux (Ubuntu / Debian)

```bash
sudo apt install -y ffmpeg
```

Verify: `ffmpeg -version`

---

## 3. git

### Windows 11

Download from <https://git-scm.com/download/win> and run the installer. Default settings work; the installer also adds Git Bash, which is the shell most Windows users will want for Unix-style commands.

Alternative: `winget install Git.Git`

### macOS

```bash
brew install git
```

(macOS already ships with Apple's git, but the Homebrew version is newer.)

### Linux

```bash
sudo apt install -y git    # Ubuntu/Debian
sudo dnf install -y git    # Fedora
sudo pacman -S git         # Arch
```

Verify (any platform): `git --version`

---

## 4. (Optional) NVIDIA GPU for future acceleration

GPU acceleration is a **planned** optimization, not a requirement. If you have an NVIDIA GPU and want to be ready for it:

- Install the latest [NVIDIA driver](https://www.nvidia.com/Download/index.aspx) for your card.
- Install the [CUDA Toolkit](https://developer.nvidia.com/cuda-downloads) (12.x is current). You may not need the full toolkit — PyTorch's binary wheels ship their own CUDA runtime.
- When GPU support ships, you'll reinstall torch with a CUDA-aware build:

```bash
py -3 -m pip install --upgrade --extra-index-url https://download.pytorch.org/whl/cu124 torch torchvision
```

No GPU? You're fine — the tool runs entirely on CPU today.

---

## 5. Verification checklist

Run all three of these. All should print version info, not errors.

```
py -3 --version          # Windows
# or
python3 --version        # macOS / Linux

ffmpeg -version

git --version
```

If any of the three fails:

- **`'py' is not recognized…`** — the python.org installer didn't add `py.exe` to PATH. Re-run the installer with the "Install py launcher" option checked.
- **`'ffmpeg' is not recognized…`** — winget install completed but you didn't open a fresh shell. Either open a new PowerShell window or reload PATH with the snippet in step 2.
- **`'git' is not recognized…`** — git installer didn't update PATH. Open a new shell or re-run the installer.

Once all three commands work, you're ready to [install the tool](installation.md).
