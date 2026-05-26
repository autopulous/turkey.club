## Description

Brief summary of the change. Focus on the **why**, not the **what** — the diff shows what.

Closes #<!-- issue number -->

## Type of change

- [ ] Bug fix (non-breaking)
- [ ] New feature (non-breaking)
- [ ] Breaking change
- [ ] Documentation update
- [ ] Refactor (no functional change)
- [ ] Performance improvement
- [ ] CI / build / tooling

## Testing

How did you verify this works?

- [ ] `py -3 -m pytest tests/` passes.
- [ ] Smoke-tested the affected CLI subcommand by hand.
- [ ] End-to-end tested on real video (describe the match and bowler target used).
- [ ] Added a test that exercises the change.

## Invariants checked

If you modified pipeline logic, please confirm:

- [ ] `flush=True` on any new long-running pipeline `print()` calls.
- [ ] Strict forward progress maintained in any search loop.
- [ ] Tuple coercion in any new `BowlerTarget.load`-style JSON deserialization.
- [ ] Output path validated upfront in any new interactive collector.

See [CONTRIBUTING.md](../CONTRIBUTING.md) for context on each.

## Documentation

- [ ] Updated `README.md` if the CLI surface changed.
- [ ] Updated `docs/project/implementation_plan.md` if a phase moved forward.
- [ ] Updated `docs/project/requirements.md` if requirements changed.
- [ ] Added a `CHANGELOG.md` entry under `[Unreleased]`.

## Notes for reviewers

Anything reviewers should know — gotchas, trade-offs, deliberate non-goals, follow-up TODOs.
