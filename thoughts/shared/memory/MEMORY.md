# game.to.frames project memory index

- [Bowling format taxonomy](project_bowling_format_taxonomy.md) — per-format lane policies, expected shot counts, probe-interval implications.
- [Identification strategy](project_identification_strategy.md) — HSV histogram-distance match, threshold 0.30 for video (not 0.55), build BowlerTarget from references.
- [Search strategy](project_search_strategy.md) — probe-then-range default; linear fallback; strict-forward-progress + dedup invariants.
- [Performance constraints](project_performance_constraints.md) — CPU YOLO is the bottleneck (~200ms/frame); downscale + frame-skip + GPU are the planned levers.
- [Calibration assumptions](project_calibration_assumptions.md) — fixed-camera per venue, polygon-zone model, one calibration JSON per camera setup.
- [Tool roadmap and current state](project_tool_roadmap.md) — what's built, what's queued, where things stand.
- [Pipeline invariants and bug-fix lessons](feedback_pipeline_invariants.md) — flush=True on long-running prints, mkdir-upfront on interactive collectors, strict-forward-progress in probe loops, tuple-coerce after JSON.
- [GitHub credential switch](reference_gh_credential_switch.md) — `gh auth switch` between work (john-hart-vertexinc-com) and personal (autopulous) accounts for push.
