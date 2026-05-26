---
name: Bug report
about: Report something that isn't working as expected
title: '[BUG] '
labels: bug
assignees: ''
---

## Description

A clear and concise description of what the bug is.

## Reproduction

Exact CLI command that triggered the bug (use a code block):

```
py -3 -m turkey_club.cli ...
```

Steps to reproduce:

1. ...
2. ...
3. ...

## Expected behavior

What you expected to happen.

## Actual behavior

What actually happened. Include any traceback or relevant log output (use a code block; redact paths if needed).

## Environment

- OS: <!-- e.g., Windows 11, macOS 14.4, Ubuntu 22.04 -->
- Python version: <!-- output of `py -3 --version` or `python3 --version` -->
- ffmpeg version: <!-- output of `ffmpeg -version | head -1` -->
- `turkey-club` commit SHA: <!-- output of `git -C path/to/turkey.club rev-parse HEAD` -->
- Video properties (from `ffprobe`): <!-- resolution, frame rate, duration, codec -->

## Did the same input work on `--strategy linear`?

This distinguishes search-strategy bugs from signal-extraction bugs.

- [ ] Yes — `linear` works but `probe` fails
- [ ] No — both fail
- [ ] Didn't try

## Additional context

Anything else that might be relevant: screenshots, related issues, hypotheses.
