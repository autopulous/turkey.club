---
name: reference-gh-credential-switch
description: How to switch between work (john-hart-vertexinc-com) and personal (autopulous) GitHub credentials for push operations
metadata: 
  node_type: memory
  type: reference
  originSessionId: c1af1c36-96c1-4c4f-9b17-6fd635b81282
  modified: 2026-08-26T15:49:16.535Z
---

Git credential helper for this repo delegates to `gh auth git-credential` (configured in `C:/Users/John.Hart/.gitconfig`). Two GitHub accounts are authenticated in `gh`:

- **john-hart-vertexinc-com** — work account (active by default)
- **autopulous** — personal account (owns the turkey.club repo)

To push to this repo, switch to the personal account, push, and switch back:

```
gh auth switch --user autopulous && git push && gh auth switch --user john-hart-vertexinc-com
```

`gh auth status` shows both accounts and which is active.
