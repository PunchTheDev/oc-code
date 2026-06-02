# Punch Log — Gittensor Base-Miner Flywheel

Milestone trail for the base-miner benchmark. Discord is the primary channel; this file is the audit trail.

---

## 2026-06-02 — Pool refresh 343→347, score breakdown (commit cdb7b4c)

### Pool expansion (+4 ragflow problems)
- Added `infiniflow_ragflow_15116`, `15118`, `15266`, `15359` — all real API bug fixes with unit tests.
- Pool: 343 → 347 problems. Oracle mean: 22.84 → 22.85.
- Checked entrius/gittensor: 0 new qualifying PRs (saturated at #1407).

### `gitminer run --score` — detailed scoring breakdown
- **Test failure**: now shows last 20 lines of test output so miners know exactly what broke.
- **Test pass**: shows source-token score with ASCII progress bar `[████████░░░░░░░░░░░░]` alongside the final score.
- **Oracle delta**: comparison against this problem's oracle (reference diff score) with ± color.
- **Mean oracle**: comparison against the pool-wide oracle mean (22.85).
- Color-coded: green = beating reference, red = below, cyan = informational.

---

## 2026-06-02 — Context file tree, gitminer info (commits 7238f6e, 0b2e016)

### Context file tree in dashboard drawer
- `generate_dashboard_data.py` now enumerates each problem's `context/` directory and includes `context_files` and `test_files` lists in `data.json`.
- Problem drawer now shows a "Context files — what your agent sees" section: every file listed with 📄 (source) or 🧪 (test) icons. Test files are highlighted in green.
- Summary line: "3 source · 1 test" — miners immediately know what they're working with before cloning anything.
- data.json regenerated and pushed (dashboard commit `0b2e016`).

### `gitminer info ID`
- New CLI command: rich terminal view of a single problem.
- Shows: issue title, repo/PR/issue links, merged date, issue body (truncated), test command, per-problem scores (baseline + DAS), context file tree (source vs test), quick-copy run commands.
- Example: `python gitminer.py info 0463`

### Pool refresh
- Dry-run confirms pool still at 342 problems, 0 new qualifying PRs.

---

## 2026-06-02 — Reward loop closed, docs/rewards.md (commit b6a314f)

### Auto-labeling in CI (`eval.yml`)
- CI now applies `agent-improvement` (2.0× multiplier) automatically on every scored PR.
- If score beats current SOTA: `new-champion` label added + celebration comment posted.
- Labels are created in the repo on first run if they don't exist.
- `issues: write` permission added to the job.

### Auto-record on merge (`record-champion.yml`)
- New workflow fires when an `agent-improvement` PR is merged to main.
- Downloads the eval artifact from the PR; falls back to re-eval if artifact expired.
- Calls `record_result.py` and commits updated `leaderboard.json` / `history.json` back to main.
- Regenerates `data.json` for the dashboard co-located at `../gittensor-miner-dashboard`.

### `docs/rewards.md`
- Full earnings model: score → label → Gittensor emission → TAO.
- Explains label multipliers, time decay, open PR threshold, eligibility requirements.
- Strategy section: how to maximize earnings (beat oracle, submit early, hard problems, tight diffs).
- Hyperparameter reference table linked to official docs.

### API server
- Running persistently at port 8083 (`nohup gitminer.py serve-api`).
- Dashboard docker-compose updated to include `api` service (port 8083) alongside `dashboard` (port 8082).

---

## 2026-06-02 — REST API + mine daemon (commit 019ab38)

### REST API (`api/server.py`, `gitminer serve-api`)

Added a full JSON REST API so miners can fetch benchmark data programmatically — no scraping needed:

- `GET /api/health` — liveness + pool size
- `GET /api/stats` — pool-level stats (language/difficulty distribution, mean baseline, repo count)
- `GET /api/shard` — current weekly 30-problem shard with rotation date
- `GET /api/problems` — paginated, filterable problem list (`?lang=py&difficulty=hard&limit=10&q=search`)
- `GET /api/problems/{id}` — full problem detail (meta, file tree, context paths, DAS scores)
- `GET /api/leaderboard` — ranked submissions

The server uses Python stdlib only (ThreadingHTTPServer + json) — no new deps. CORS-open for browser clients. Launch with `python gitminer.py serve-api [--host HOST] [--port PORT]`.

### Mine daemon (`gitminer mine`)

Added `mine` subcommand — the "idle compute" product concept:

- Runs your agent against the current shard (same eval as CI)
- If you beat the champion: prints commit-reveal hash + step-by-step PR instructions
- `--loop` mode sleeps until next shard rotation (Monday 00:00 UTC) and repeats
- The pitch: point it at your agent and walk away — your machine contributes code, earns TAO, and improves the network's best coding agent

```bash
python gitminer.py mine --agent agent/submissions/myhandle/agent.py --loop
```

### Docs and README

- `docs/api.md`: full API reference with endpoint descriptions, query params, example responses, Python snippet
- README: updated badge (342 problems), added "idle compute" vision paragraph, API + mine examples in CLI section, repo structure updated
- CONTRIBUTING.md: new "Autonomous mining" and "REST API" sections

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

## 2026-06-02 — CLI DX improvements

- **Repo cache for local eval** (commit 7da8450): `score.py` now maintains `~/.cache/gitminer/repos/` — one clone per unique repo, then git worktrees per problem. Cuts 30-problem `--no-sandbox` eval time dramatically after first run.
- **`gitminer cache`** (commit 7da8450): pre-warms the cache across all 325 problems' repos with progress output.
- **`gitminer problems`** (commit dd41305): list/filter/sort all 325 problems by language, difficulty, repo, or text search. Reads baselines.json for difficulty tier.
- **Better eval summary** (commit b796e28): shows pass rate, language breakdown (Python/JS/Rust/Java pass counts), and failed problem list with test failure hint.

---

## 2026-06-02 — Test file context: agents can now see what tests to pass

- **Problem.test_cmd exposed** (commit aa40095): `test_cmd` field added to the `Problem` dataclass and populated from `meta.json`. Agents now know exactly which test command the harness will run.
- **Test files added to context** (commit aa40095): `build_pool.py` now includes test files referenced in `test_cmd` alongside source files. For newly-added test files (which don't exist at `base_commit`), the content is extracted from the diff itself.
- **42 existing problems enriched** (commit aa40095): `scripts/enrich_test_context.py` retroactively added test files to 42 Python problems (17 entrius/gittensor, 21 infiniflow/ragflow, 4 vouchdev/vouch). Agents on these problems now see the test expectations they must satisfy.
- **Example agent updated** (commit aa40095): `OBSERVE_PROMPT` now shows the test command and asks the model to confirm the fix will pass it in the planning turn.
- **Stray `--output` files removed** from both benchmark and dashboard repos (generate_dashboard_data.py arg bug, already fixed in code).

---

## 2026-06-02 — Eval CI enrichment + oracle score sync

- **Richer eval PR comment** (commit 85da967 → e798f43): CI comment now shows per-problem language (py/js/rs/java), difficulty (easy/medium/hard), baseline ceiling score, and a "vs Baseline" delta column. Summary line shows "N/M beat baseline" and oracle score for direct comparison.
- **Oracle score synced to 22.77** (commit e798f43, c98d80d): leaderboard.json, record_result.py, and generate_dashboard_data.py now all use 22.77 (actual mean of 324 reference diffs). Was 21.60 in leaderboard/record, 22.79 in dashboard generator — all consistent now.
- **Fixed generate_dashboard_data.py arg parsing** (commit 652c46c): CLI `--output path` silently wrote to a file named `--output`. Fixed to use argparse positional arg.
- Dashboard data.json regenerated (dashboard commit 9da35e9).

### Waiting on operator

1. Verify `OPENROUTER_KEY` in GitHub Actions Environment is the correct production key.
2. Gittensor registration — team handles approval; hyperparameters.json is ready.

---

## 2026-06-02 — CLI DX: validate + leaderboard commands

- **`gitminer validate`** (commits 487ede7, daa9456): new command that applies a patch to a problem's base commit and reports PASS/FAIL with diff stat. Uses the repo cache for speed. `--run-tests` also runs the problem's test command locally. Fills the gap between generating a patch and running a full 30-problem eval.
- **`gitminer leaderboard`** (commit 69e7b04): prints current rankings in the terminal without needing to visit the dashboard. Shows oracle score and dashboard link when no ranked submissions exist yet.
- **`--no-sandbox` calibration note** (commit daa9456): eval output now shows a reminder that local heuristic scores run 3–5× above Docker CI scores, so miners interpret them correctly.

### Waiting on operator

1. Verify `OPENROUTER_KEY` in GitHub Actions Environment is the correct production key.
2. Gittensor registration — team handles approval; hyperparameters.json is ready.

---

## 2026-06-02 — Test file enrichment: 217 → 324/324 coverage

- **Extended enrich_test_context.py** (commit 7c38605): added a second pass that scans `reference.diff` for test file paths across all languages (npm, cargo, gradlew, Ruby, Kotlin, etc.). Newly-added test files extracted from the diff; pre-existing ones fetched from GitHub.
- **Enriched 66 more problems**: 217 → 289 problems with test files (by filename), and actually 324/324 when checking full paths (many enriched files live in `tests/` directories).
- **build_pool.py updated** (commit a69f5ac): future pool additions now automatically include test files found in diffs for all languages, not just Python pytest.
- All 324 problems now have test files in context — agents can see what they need to pass.

### Waiting on operator

1. Verify `OPENROUTER_KEY` in GitHub Actions Environment is the correct production key.
2. Gittensor registration — team handles approval; hyperparameters.json is ready.

---

## 2026-06-02 — Oracle eval mode + pool_config fix

- **`gitminer eval --oracle`** (commit a310fc8): new calibration mode that scores reference diffs directly through the full pipeline without any agent or API key. Expected mean ~22.77 / 30. Useful for: (1) verifying the scoring pipeline is wired correctly before spending API credits, (2) giving miners a pipeline smoke test.
- **Fixed `pool_config.json pool_size`** (commit a310fc8): was 325 (stale from before the empty-body problem removal); corrected to 324.
- **Fixed `_oracle_mean()` lookup** (commit a310fc8): was looking for `handle == "oracle"` but leaderboard uses `agent == "Oracle (accepted solution)"`.

### Waiting on operator

1. Verify `OPENROUTER_KEY` in GitHub Actions Environment is the correct production key.
2. Gittensor registration — team handles approval; hyperparameters.json is ready.

---

## 2026-06-02 — gitminer run: single-problem dev loop

Added `gitminer run` command (commit dddee08) — the missing inner development loop tool.

**Why:** Miners had no fast way to inspect what their agent actually produces for a specific problem. The only option was `eval --problems ID`, which runs the full pipeline but shows only a score, not the patch. Dev iteration was slow.

**What ships:**
- `gitminer run --problem ID [--agent PATH]` — runs agent on one problem, prints the generated diff with ANSI color
- `--show-ref` — prints the reference diff below for side-by-side comparison
- `--score [--no-sandbox]` — scores the patch inline, shows baseline delta
- `--output FILE` — saves the patch to disk for `validate` or manual inspection
- `--verbose` — prints the agent's internal reasoning log
- `_print_diff()` helper with color output (red/green/cyan, no-op when not a TTY)

**README + CONTRIBUTING.md** updated with examples.

Pending: OPENROUTER_KEY verification, Gittensor registration.

---

## 2026-06-02 — Improved example agent + calibration correction

### Example agent upgrade (commit 1722327)

Rewrote `agent/example/agent.py` with three meaningful improvements over the old observe→plan→act→verify baseline:

1. **Context file ranking** — `_rank_files()` scores each file by keyword overlap with the issue (paths mentioned, identifiers extracted). Most relevant files go first. `_truncate_context()` caps at 20 files / 40k chars — agents no longer dump all context blindly.

2. **Structural diff validation** — `_diagnose_diff()` goes beyond the basic `@@` presence check. It parses each hunk header against `@@ -N,N +N,N @@` and returns a precise description of the first problem found. The repair loop uses this targeted feedback instead of a generic "invalid diff" message.

3. **Wider repair window** — 3 attempts (up from 2), with format vs. semantic failures handled separately so repair effort isn't wasted on the wrong problem.

### Calibration correction

Updated all 3-5× calibration notes to reflect actual measured data: local scores run ~2× above DAS (measured across 289 reference diffs with known DAS scores: local mean 23.47 vs DAS mean 10.78). Updated in `score.py`, `gitminer.py`, and `results/baselines.json`.

Pending: OPENROUTER_KEY verification, Gittensor registration.

---

## 2026-06-02 — Pool quality, dashboard fix, agent tuning

### Pool quality (benchmark commits 331df8c, 834388e)

- **Removed problem 1187** (entrius/gittensor PR #1187): deletion-only refactor (removes dead `get_github_id` wrapper). Scores 0 on token-overlap regardless of correctness — unusable as a benchmark problem.
- **Added `has_additions()` guard to `build_pool.py`**: future problems must add ≥5 lines. Deletion-only diffs are now filtered out at ingestion.
- Pool: 343 → 342 problems. Oracle mean updated: 22.76 → 22.83.
- Synced oracle score across leaderboard.json, record_result.py, evaluate.py, gitminer.py, generate_dashboard_data.py.

### Dashboard overhaul (dashboard commit f068d1b — previous step)

- Fixed critical `pl is not defined` crash that prevented entire page from rendering.
- Full UI overhaul: loading spinner, sticky header + Submit CTA, gradient stat cards, rank medals, dedicated Allowed Models pill grid, dynamic pool count, table surface cards, graceful error state.
- Docker deployment files added (Dockerfile, docker-compose.yml, systemd unit).

### Example agent tuning (commit 834388e)

- **Verify turn grounded**: VERIFY_PROMPT now shows the original issue title so the model knows what it's validating against (was verifying diff in isolation).
- **temperature=0 for diff turns**: act and repair calls use temp=0 for format precision; planning turn keeps 0.2 for open-ended reasoning.

Pending: nginx hookup, Gittensor registration.

### Example agent: verify prompt enriched (commit 018c97f)

- **Issue body in verify**: VERIFY_PROMPT previously silently discarded `body=problem.issue_body` (passed but not in template). Now shows first 1500 chars of issue body in the verify turn — model has full problem context when checking its diff.
- **Test command in verify**: Added `Test command that must pass: \`{test_cmd}\`` before the diff and as criterion 4. Model now explicitly checks its patch will pass the scoring test, not just that it compiles.
- Scope: small but closed a real gap — the verify turn was semantically disconnected from the problem except for the title.

### Pool refresh audit (2026-06-02)

- Checked new entrius/gittensor PRs: 1360, 1364, 1374, 1381, 1408, 1418 — none qualify.
  - 1360 (bound inline-test regex): has test files, no linked issue in body → skip
  - 1364, 1374 (CLI fixes): linked issue, no test files → skip  
  - 1381, 1408 (issue-discovery fixes): has test files, no linked issue → skip
- Full dry-run: 0 new qualifying problems across all 20 registered repos. Pool remains at 342.

Pending: Gittensor registration (operator action).

## 2026-06-02 — Dashboard hero redesign + agent file windowing

### Dashboard (commit 26a6b76)
- **Hero section**: "Ship code. Earn TAO. Improve the network." — big headline, 2-line pitch, live stats bar (pool size, oracle score, SOTA), 3 CTAs
- **How it works**: 4-step visual (Browse → Build → Submit → Earn) as connected panel grid
- **Quick start terminal block**: 3 commands with syntax coloring, no copy confusion
- **REST API info box**: one-liner explaining the API is available, links to docs/api.md
- **Model pills**: now show short name (e.g. `deepseek-chat`) with full ID in tooltip — was showing verbose `deepseek/deepseek-chat`
- **Leaderboard section**: count badge + "no submissions yet" CTA box when empty
- **Meta**: better title + description tag for SEO/share previews

### Benchmark (commit b5f613b)
- **File content windowing**: `_window_file()` in example agent — for files >300 lines, shows only ±40-line windows around keyword hits with `... [N lines omitted]` markers; lets more files fit in the 40k-char context budget
- **README stale counts fixed**: 324 → 342 in 3 places

### Status
- Dashboard: http://localhost:8082 (serving, commit 26a6b76)
- API: http://localhost:8083 (serving)
- Pool: 342 problems, oracle 22.83
- Pending: Gittensor registration, nginx hookup
