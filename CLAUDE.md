# turkey.club — Claude Code project instructions

## Project memory lives in-repo

Project memory files are maintained in `thoughts/shared/memory/`, **not** in the default `~/.claude/projects/<encoded-cwd>/memory/` directory. That external directory is the seed — its contents should be treated as the initial source — but the canonical, version-controlled home is in-repo.

When reading or writing project memory:

1. **Read from** `thoughts/shared/memory/MEMORY.md` and its linked files.
2. **Write to** `thoughts/shared/memory/` — new memory files, updates to existing ones, and index changes to `MEMORY.md` all go here.
3. **Keep the external directory in sync.** After writing a memory file in-repo, copy the same content to `~/.claude/projects/<encoded-cwd>/memory/` so the auto-loaded MEMORY.md index stays current for sessions that read it at startup.
4. **On conflict**, the in-repo copy wins — it is reviewed and committed alongside the code it describes.
