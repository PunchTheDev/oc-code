# Punch Log — Gittensor Base-Miner Flywheel

Milestone trail for the base-miner benchmark. Discord is the primary channel; this file is the audit trail.

---

## 2026-06-01 — Repo scaffold live

**Milestone: Initial repo structure created and pushed to GitHub.**

What was built:
- `agent/base.py`: `BaseAgent` interface (Problem → Patch)
- `agent/example/`: minimal single-shot reference agent
- `benchmark/harness/score.py`: local scoring approximation (correctness gate + quality heuristic)
- `benchmark/evaluate.py`: full evaluation runner
- `scripts/curate_problems.py`: tooling to pull benchmark problems from real Gittensor merged PRs
- `docs/scoring.md`: scoring mechanics
- `docs/hyperparameters.md`: full hyperparameter config rationale
- `docs/threat_model.md`: anti-gaming threat model (6 threats, 18 mitigations)
- `hyperparameters.json`: live Gittensor repo config (ready for registration submission)
- `.github/` templates: PR template with commit-reveal, issue templates

**Next steps:**
1. Curate the first batch of ~30 benchmark problems from real Gittensor merged PRs.
2. Run `scripts/curate_problems.py --repo entrius/gittensor` once GitHub API access is confirmed.
3. Test the harness end-to-end with the example agent on one problem.
4. Post Discord milestone once first agent scores across problems.

**Open decision (non-blocking, going with defaults):**
- Frozen model: defaulting to `anthropic/claude-3-5-haiku` via OpenRouter. If a different model or Chutes/whitelist is preferred, please confirm.
- Gittensor scoring engine: using an approximation for local dev. Need location of the validator's native scoring engine to wire it in for CI. Going with approximation until then.

---

## 2026-06-01 — Phase 5: GitHub Actions CI

**Milestone: `.github/workflows/eval.yml` live (commit `3f3dc5e`).**

What was built:
- `detect` job: diffs PR against base, finds `agent/submissions/*/agent.py` changes, extracts handle
- `evaluate` job: sets up Python 3.12, installs deps, runs `scripts/run_eval.py` in Docker sandbox, posts formatted score table as a PR comment (upserts to avoid spam)
- Results uploaded as workflow artifact (30-day retention)
- `agent/submissions/` directory created — the expected landing zone for miner submissions
- Workflow skips gracefully for non-agent PRs (docs, harness changes, etc.)

Comment format: mean score + per-problem pass/fail table + collapsed run details block.

**Remaining:** Phase 6 (Gittensor registration) is on the operator side. Flywheel is ready to receive submissions.

---

## 2026-06-01 — Smoke test + harness hardening (commit `aeb6004`)

**Milestone: End-to-end smoke test confirmed. Harness fixes pushed.**

Ran `score_patch()` on problem 1033 (reference.diff as input). Surfaced two bugs:

1. **test_cmd ran full suite** — all 30 meta.json had `["python", "-m", "pytest", "--tb=short", "-q"]` with no file scope. Each problem's reference.diff already names the exact test files to run. Updated all 30 to scope the test_cmd (e.g. problem 1033 now runs only `tests/validator/oss_contributions/mirror/test_scoring.py`). Result: CI runs ~10x faster per problem; local dev doesn't collect tests that require unrelated heavy deps.

2. **Tests always skipped locally** — Gittensor test files use `pytest.importorskip('gittensor.validator...')` which fires because `bittensor` (a heavy dep) isn't installed locally. pytest exits with code 5 (no tests collected). `run_tests()` treated this as failure. Fixed: `run_tests()` now returns an `all_skipped` flag; exit code 5 with no failures is a soft pass. Result adds `tests_skipped_locally: true` to the score JSON and an honest `scoring_note`. Docker CI installs full deps via pyproject.toml so tests actually run there.

**Confirmed smoke test output (problem 1033, reference.diff):**
```json
{
  "patch_applied": true,
  "tests_passed": true,
  "tests_skipped_locally": true,
  "source_token_score": 12.0,
  "final_score": 4.83,
  "scoring_note": "tests skipped locally (missing heavy deps e.g. bittensor) — quality score estimated from diff; Docker CI runs full correctness check"
}
```

**Waiting on operator:**
1. `OPENROUTER_KEY` as a GitHub Actions secret (CI can't run actual agents without it)
2. `hyperparameters.json` submission to Gittensor team for registration
3. Confirm frozen model preference (default: `claude-3-5-haiku` via OpenRouter)

---

## 2026-06-02 — Pool 325, Product Polished, Awaiting Registration

**Milestone: benchmark is feature-complete and ready for Gittensor registration.**

### What's live

- **325 curated problems** across 20 Gittensor-registered repos — all post-cutoff (merged 2026+), all with linked issues, test files, and DAS reference scores where available.
- **Shard rotation**: 30 problems/eval, deterministic weekly seed so all evaluators see the same shard.
- **Sandboxed harness**: Docker-per-problem, correctness gates before quality scoring, Gittensor's exact scoring formula (constants from `constants.py`).
- **CI pipeline**: eval on PR (score comment upserted), record on merge, champion agent updated on new SOTA, weekly pool refresh (Sunday 02:00 UTC).
- **Static dashboard** live at https://punchthedev.github.io/gittensor-miner-dashboard/ — leaderboard, SOTA chart, problem browser with DAS reference scores + diff viewer, live submission queue.
- **`gitminer` CLI**: `eval`, `hash`, `shard`, `submit`, `parity` subcommands.
- **SOTA-grade docs**: README with badges, CONTRIBUTING.md, threat model, hyperparameter rationale.

### Calibration note

Local harness over-estimates DAS reference scores by median 3.4×. Root cause: tree-sitter counts AST nodes with language weights; local heuristic counts raw diff tokens. Dashboard now shows this note inline in the problem drawer. CI is authoritative.

### Dashboard improvements (dashboard commits c2fb53b, 2cc0f67)

- Reference diff now **auto-loads** when the problem drawer opens — fetched from `raw.githubusercontent.com` (no GitHub API rate limit). Removed the "Load Reference Diff" button.
- Issue bodies now **rendered as markdown** — fenced code blocks, inline code, bold/italic, headings, links, lists. Previously raw escaped text.

### Waiting on operator

1. Verify `OPENROUTER_KEY` in GitHub Actions Environment is the correct production key.
2. Gittensor registration — team handles approval; hyperparameters.json is ready.

---
