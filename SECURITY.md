# Security Policy

[← Back to README](README.md)

## Reporting a vulnerability

If you discover a security issue in `turkey-club`, please report it **privately** by emailing the maintainer at **john.hart@vertexinc.com** with the subject line `turkey-club security issue`.

Please do **not** open a public GitHub issue for security reports.

Include:

- A clear description of the vulnerability.
- Steps to reproduce, ideally with a minimal example.
- Affected version(s) — a git commit SHA if you're tracking `main`.
- Any suggested mitigation.

You can expect:

- **Acknowledgement within 7 days** of your report.
- **Substantive response within 30 days**, with a status update on investigation and any planned fix timeline.
- **Disclosure timing coordination** — if the issue is confirmed, the maintainer will work with you on a responsible disclosure schedule before any public discussion.

## Supported versions

This project is pre-1.0; only the latest tagged release and `main` HEAD receive security patches. Older releases will not be back-patched.

| Version | Supported          |
|---------|--------------------|
| 0.1.x   | ✅                 |
| < 0.1   | ❌                 |

## Scope

**In scope**:

- Vulnerabilities in the `turkey-club` package itself (Python code under `src/`).
- Vulnerabilities introduced by bundled dependencies as configured in this project's `pyproject.toml`, where the issue is exploitable through the documented use case.

**Out of scope**:

- Generic issues in third-party dependencies (PyTorch, OpenCV, EasyOCR, ultralytics, yt-dlp). Please report those upstream.
- Functional bugs that don't have a security impact — please open a regular bug report instead (see [`.github/ISSUE_TEMPLATE/bug_report.md`](.github/ISSUE_TEMPLATE/bug_report.md)).
- Issues that require a malicious actor to already have local code execution on the user's machine.

## Threat model

This project processes user-provided video files locally on the user's machine. Realistic threats:

- **Malicious video files** crafted to exploit decoder vulnerabilities in opencv-python or ffmpeg. Mitigation: keep ffmpeg and opencv-python current.
- **Malicious calibration / bowler-target JSON files** crafted to exploit the JSON deserializer. Mitigation: only load files from trusted sources; this project parses with the stdlib `json` module, which doesn't execute code.
- **Path traversal** via crafted `--out` paths. The tool writes only where the user specifies; review your `--out` arguments before running on untrusted CLI invocations.

Out of threat model:

- Remote attackers (the tool has no network listening service).
- Multi-tenant isolation (this is a single-user CLI tool).
