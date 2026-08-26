---
name: feedback-gh-auto-switch
description: Automatically switch to autopulous GitHub account for turkey.club repo operations, then switch back to john-hart-vertexinc-com afterward
metadata:
  type: feedback
---

When interacting with GitHub for the turkey.club project (push, PR creation, any `gh` command targeting this repo), automatically switch to the `autopulous` account before the operation and switch back to `john-hart-vertexinc-com` afterward. Do not prompt or ask — just do the switch-operate-switch sequence.

**Why:** `john-hart-vertexinc-com` is the default/work GitHub profile on this system. `autopulous` is the personal account that owns the turkey.club repo. The user does not want to be interrupted to manually switch credentials every time.

**How to apply:** Wrap any GitHub-touching command (`git push`, `gh pr create`, etc.) with `gh auth switch --user autopulous` before and `gh auth switch --user john-hart-vertexinc-com` after. See [[reference-gh-credential-switch]] for the underlying credential setup.
