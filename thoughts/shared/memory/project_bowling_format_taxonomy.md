---
name: project-bowling-format-taxonomy
description: Per-format lane policies, expected shot counts, and probe-interval implications for the game-to-frames pipeline.
metadata:
  type: project
---

Bowling formats relevant to the search strategy:

| Format | Lane policy | Expected shots/bowler | Inter-shot gap |
|---|---|---|---|
| PBA qualifying / match play | Cross-lane rotation each frame | ~21 | ~2 min |
| Doubles | Each bowler alternates lanes | ~21 | ~1 min (interleaved with teammate) |
| Scotch Doubles | Bowlers alternate shots and the team alternates lanes each frame | ~10-12 | Variable — depends on strike/spare distribution |
| League play | Cross-lane rotation | ~21 | ~90s |
| Baker (traditional / half / double) | **Fixed lane per bowler** | varies by team size | ~30-40s (clustered) |
| Singles practice | **Single lane OR alternating pair** | open-ended | ~20-30s |
| Multi-bowler practice | Mixed | open-ended | varies |
| Open bowling | Chaotic, irregular | open-ended | unpredictable |

**Why:** Format determines (a) whether to search one lane or both, (b) probe-interval tuning, (c) sanity-check expectations on output shot count. Source: domain knowledge from the project owner (PBA-experienced) recorded in conversation 2026-05-25.

**How to apply:** When implementing the format-aware CLI (`--format <preset>` per Task #12), Baker presets auto-restrict to one lane; cross-lane formats search both. The probe interval invariant is `< minimum on-approach duration` (~12-15s), so 10s works for ALL formats — rhythm only affects higher-level priors (expected shot count, false-positive sanity-check). Singles-practice needs `--bowler-lane` override or short-prefix auto-detect. Related: [[project-search-strategy]], [[project-identification-strategy]].
