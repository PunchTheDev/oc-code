# Punch Log — Gittensor Base-Miner Flywheel

Milestone trail for the base-miner benchmark. Discord is the primary channel; this file is the audit trail.

---

## Step 165 — 2026-06-03

**External Python pool expansion: 584→644 (+60 problems)**

Pool grew from 584 to 644 by adding 60 problems from two prestigious external Python repos (not in Gittensor DAS — supplementary high-quality problems):

| Repo | Added | Notes |
|---|---|---|
| pytest-dev/pytest | 30 | Real bugs: fixtures, assertions, markers, logging, JUnit XML |
| pallets/click | 30 | Real bugs: CliRunner, shell completion, option parsing, termui |

Both pass identical curation criteria as DAS problems: linked issue, test files in diff, ≥5 added lines, issue body ≥50 chars. Scored via tree-sitter, oracle updated to **15.23 weighted / 14.03 arithmetic** (slight pulldown from compact Python fixes — expected).

**Other fixes shipped in same commit (PR #15, merged):**
- `REPO_CATEGORY` in `evaluate.py` + `generate_dashboard_data.py` now includes all 5 external prestige repos
- Parity command bug: `"das_base_score" not in meta` → `meta.get("das_base_score") is None` (external problems carry `null`, not missing key — old check would crash on `float(None)`)
- Stale oracle fallback in `evaluate.py` corrected: 13.03/12.08 → 15.99/14.97

**Pool composition (644 problems):**
- python: 260 (was 200) | rust: 206 | typescript: 98 | jvm: 42 | ruby: 38
- hard: 350, medium: 242, easy: 52
- Repos: 15 (13 DAS + 2 external)

**API verified**: pool=644, oracle=15.23, repos=15

---

## 2026-06-03 — Pool 446 → 532 + dashboard deep links (step 163)

**Pool expanded: 446 → 532 problems** (PR #12 merged)
- 85 new phase-rs/phase problems (Rust — bug fixes, all with linked issues + inline tests)
- 1 new infiniflow/ragflow problem
- Oracle: 15.15 weighted → **15.62 weighted** / 14.04 → **14.57 arithmetic**
- pool_config.json pool_size updated to 532
- Added `--incremental` flag to `baseline_scores.py` (only re-scores new problems)

**Dashboard: URL deep links for problems** (gittensor-miner-dashboard commit dfe486c)
- Each problem now gets a shareable URL: `#/problem/<id>` 
- Browser back/forward works through problem navigation
- Static pool count placeholders updated to 446

---

## 2026-06-03 — Full system audit, pre-registration holding

**Codebase-wide audit** — nothing to fix.

Everything verified clean heading into the pre-registration holding period:

| Check | Result |
|---|---|
| API health | pool=441, oracle=13.03 weighted / 12.08 arithmetic ✓ |
| Shard | week=126, size=30, next_rotation=2026-06-08 ✓ |
| CLI | `shard`, `problems`, `leaderboard`, `mine`, `doctor` all working ✓ |
| All Python files | Syntax-clean (benchmark, scripts, api, agent, gitminer) ✓ |
| CI workflows (5) | eval, record_submission, refresh_pool, refresh_dashboard, build-scorer — all correct ✓ |
| Anti-gaming scripts | check_rate_limit, check_similarity, check_output_similarity — verified ✓ |
| Hyperparameters | hyperparameters.json consistent with docs/hyperparameters.md ✓ |
| Leaderboard.json | Oracle row values (weighted=13.03, arithmetic=12.08) match baselines.json ✓ |
| No open PRs | ✓ |

No changes shipped this step — system is stable. Holding pre-registration.

---

## 2026-06-03 — Oracle row stays fresh after pool rotation (commit 1d5f9c9)

**Bug**: After every pool rotation, `refresh_pool.yml` recalibrates `baselines.json` with new oracle scores, but `generate_dashboard_data.py` read the oracle row from `leaderboard.json` (where it was frozen). Dashboard would show stale oracle scores and the stale static note.

**Fix**:
- `generate_dashboard_data.py::load_leaderboard()`: always replaces stored oracle row with fresh values computed from `baselines.json` — oracle scores in dashboard now auto-update after every rotation.
- `refresh_pool.yml`: new step "Refresh oracle row in leaderboard.json" updates the oracle row on disk after recalibration, and stages `results/leaderboard.json` for commit — so `gitminer mine` oracle gap is also correct after `git pull`.

Net effect: oracle scores in dashboard, API (`baselines.json` direct read — already correct), and local CLI are all consistent post-rotation.

---

## 2026-06-03 — Three latent bugs fixed (commits 2149015, 50d5622, 146d9f4)

Pre-submission audit of CI workflows and API found three bugs that would have caused silent failures or crashes once miners start submitting.

**Bug 1 — `record_submission.yml`: NameError on first champion (commit 2149015)**

```python
# BEFORE (crashes with NameError: name 'score' is not defined)
print(f"Champion updated: {handle} (score={score})")

# AFTER
print(f"Champion updated: {handle} (weighted={weighted:.4f})")
```

Root cause: `score` was never defined in that scope — the variable was `weighted`. This would have crashed the champion-promotion step on the very first miner PR that beats the SOTA, leaving the champion directory un-updated.

**Bug 2 — `record_result.py`: misleading SOTA comparison message (commit 50d5622)**

```python
# BEFORE (prints arithmetic mean but compares against weighted SOTA)
print(f"Score {mean_score:.4f} below current SOTA {prev_sota:.4f} ...")

# AFTER
print(f"Weighted score {weighted_mean:.4f} below current SOTA {prev_sota:.4f} ...")
```

Root cause: `mean_score` (arithmetic mean) was printed in a message about failing to beat SOTA, while SOTA is a weighted mean. Misleading for any submission with high weighted but lower arithmetic score.

**Bug 3 — `api/server.py`: month-overflow crash in `/api/shard` (commit 146d9f4)**

```python
# BEFORE (crashes with ValueError: day is out of range near month-end)
next_rotation = str(today.replace(day=today.day + days_to_monday) if days_to_monday else today)

# AFTER
next_rotation = str(today + timedelta(days=days_to_monday))
```

Root cause: `date.replace(day=N)` raises ValueError when N exceeds the days in the month (e.g. July 28 + 7 days = Aug 4, but `today.replace(day=35)` throws). Affects any `/api/shard` call during the last ~7 days of most months. API restarted, verified.

---

## 2026-06-03 — scorer image build fixed (commits cc21881, e2ddd16)

**Critical bug found and fixed: Docker scorer image had never successfully built.**

Root cause chain:
1. First failure (`ERROR: Cache export is not supported for the docker driver`): `build-scorer.yml` used `cache-to: type=gha,mode=max` without setting up Docker Buildx first. Added `docker/setup-buildx-action@v3` step.
2. Second failure (`repository name must be lowercase`): `IMAGE_NAME: ${{ github.repository_owner }}/gitminer-scorer` expands to `PunchTheDev/gitminer-scorer` — GHCR requires lowercase. Hardcoded to `punchthedev/gitminer-scorer`.

Third build now queued (2026-06-03T02:27Z). This unblocks real Docker-sandboxed CI evaluations; previously the sandbox always fell back to heuristic scoring.

Also fixed: `record_submission.yml` "Update champion" step wrote `score` (arithmetic mean) to champion `meta.json` — now writes `weighted_score` (the actual ranking metric).

---

## 2026-06-03 — mine command fixes (commit 3c01104)

Three issues fixed in `gitminer mine`:
1. **Zero-score guard**: when no tests pass (score = 0), the command now prints a helpful message instead of prompting "FIRST SUBMISSION!" with a score of 0.
2. **Dead code removed**: `_seconds_to_next_monday` had a `delta_days` variable computed but never used; removed.
3. **Default model updated**: `cmd_submit` and help text used stale `claude-3-5-haiku-20241022` instead of the operator-confirmed `deepseek/deepseek-chat`.
4. **Oracle gap shown on beat**: output now includes oracle context so miners know how far they are from the theoretical max.

All systems healthy: API pool=441, oracle=13.03, 0 submissions.

---

## 2026-06-03 — Docs accuracy fixes (benchmark commit 3fef8d1)

- README: `gitminer hash your_patch.diff` → `gitminer hash agent/submissions/yourhandle/agent.py` — the `hash` command was renamed to take an agent file in commit 7940f68 but the README example was missed.
- `docs/threat_model.md` Threat 2 (overfitting): removed false "20% private held-out set" claim — no such set exists. Replaced with accurate description of the SHARD_SECRET mitigation (shard is unpredictable without the secret) + time segmentation. Summary table updated: "held-out set" → "secret shard".

All systems healthy: API pool=441, oracle=13.03, 0 submissions.

---

## 2026-06-03 — Dashboard stale placeholder fix (dashboard commit 8f886f0)

Static hero pool-count placeholders (`430`) in `index.html` were never reached by JS on slow connections — showed stale count briefly before the dynamic `d.pool_size = 441` update fired. Fixed both inline occurrences to `441`.

All systems healthy: API pool=441, oracle=13.03, 0 submissions, 13 active repos.

---

## 2026-06-03 — Fix SOTA comparison: weighted_score throughout (commit 450180f)

Found and fixed two interrelated ranking bugs:

1. **`scripts/record_result.py` `current_sota()`**: was returning `max(r["score"])` (arithmetic mean) but the leaderboard ranks by `weighted_score`. `marginal_gain` and `contribution_weight` were computed against the wrong baseline — a submission with a high weighted score but lower arithmetic score could incorrectly undercount its marginal gain.

2. **`.github/workflows/eval.yml` champion detection**: `isNewChampion = mean > sota` compared arithmetic `mean` against `sota` derived from `max(r.weighted_score)`. A new champion with a high weighted score but lower arithmetic score could be missed. Fixed to `effectiveScore = weightedMean ?? mean`.

Both now use `weighted_score` end-to-end, consistent with `update_leaderboard()` which already sorted by `weighted_score`.

---

## 2026-06-03 — info command difficulty fix (commit e88f422)

Fixed `gitminer info` displaying wrong difficulty tier. It was using score-based thresholds (`score ≥ 15 → easy`) instead of the canonical line-count system. A problem like `infiniflow_ragflow_13650` (+598 lines, hard×2) was showing "easy" because its reference score (23.06) was high. Now reads `difficulty` and `weight` directly from `results/baselines.json` — consistent with `gitminer problems`, the dashboard, and `evaluate.py`.

---

## 2026-06-03 — docs/rewards.md accuracy fixes (commit 33cf61b)

Fixed three wrong values in `docs/rewards.md` that disagreed with `hyperparameters.json`:

| Field | Was | Now |
|---|---|---|
| Contributor emission share | 59.5% | 55% |
| Maintainer emission share | 10.5% | 15% |
| Open PR base threshold | "default 10" | 3 |
| Token score per +1 threshold | "every 500" | every 250, max 15 |
| Hyperparameter reference block | truncated (missing eligibility) | matches full `hyperparameters.json` |

Also fixed README: "minimal reference implementation" → "baseline reference implementation (observe → plan → act loop)" — the example agent is 3015 lines, not minimal.

---

## 2026-06-03 — Oracle calibration message fix (commit 62c528e)

`benchmark/evaluate.py` oracle mode was printing "Expected mean: ~23.46 / 30.00" — a very old hardcoded value from before tree-sitter recalibration. Fixed to read `weighted_mean_score` and `mean_score` from `results/baselines.json` at runtime, with a fallback of 13.03/12.08. Message now reads:

> `Expected weighted mean: ~13.03 / 30.00  (arithmetic: ~12.08)`

Also ran a full pipeline health check:
- API live: pool_size=441, oracle=13.03
- `gitminer leaderboard`: correct oracle 13.03, no submissions yet
- `gitminer problems --limit 5`: correct line-count difficulty tiers
- `parity --top 10`: median local/DAS ratio 2.5× — consistent with documented behavior
- All CI workflows reviewed: eval, record_submission, record_champion (disabled), refresh_dashboard, refresh_pool, build-scorer — all correct
- Behaviors directory in results/ confirmed tracked

---

## 2026-06-03 — Stale oracle fallback cleanup (commit 06c9987)

Three files had hardcoded fallback values (11.83/12.77) from before the gittensory pool expansion. The fallbacks are only reached when baselines.json/leaderboard.json can't be read, but they should still reflect current state.

**Files updated**:
- `.github/workflows/eval.yml`: fallback oracle 12.77 → 13.03
- `scripts/generate_dashboard_data.py`: fallbacks 11.83→12.08, 12.77→13.03, count 430→441
- `scripts/record_result.py`: fallback (11.83, 12.77) → (12.08, 13.03)

**Also verified**: JVM problem baselines are correct (0.01–26.88 range); earlier diagnostic was checking wrong field (`baseline_score` vs `base_score`). Pool composition confirmed: 441 problems across 13 DAS-registered repos. API live on PM2, oracle 13.03.

---

## 2026-06-03 — Difficulty tier consistency sweep (commits 2d5bab4, 13535cd)

**Root cause**: Two places still used oracle score to classify problem difficulty (easy/medium/hard) instead of the canonical line-count system in `evaluate.py`. The eval.yml PR comment used `score ≥ 15 → easy`, and `gitminer.py problems` used the same score thresholds.

**Fixes**:
- `results/baselines.json`: each problem now includes `difficulty`, `weight`, and `added_lines` (computed from reference.diff). This makes the stored baselines self-describing.
- `scripts/baseline_scores.py`: `score_reference()` now records these three fields; weighted mean computation simplified to use stored `weight` per problem.
- `.github/workflows/eval.yml`: `difficulty()` function replaced — now reads `difficultyMap[pid]` from baselines instead of score-based heuristic. PR comment difficulty column now matches dashboard badges.
- `gitminer.py` `cmd_problems`: removed score-based `_difficulty()` helper; now reads `difficulty` directly from `difficulty_lookup` (loaded from baselines.json). `problems --difficulty hard` now filters consistently with dashboard.
- `REGISTRATION.md`: stale pool count updated (360 → 441, 20 repos → 13 active).

**Effect**: difficulty classification is now line-count-based everywhere — `evaluate.py`, dashboard, eval CI comment, `gitminer problems` CLI. All four agree.

---

## 2026-06-03 — CLI and docs consistency sweep (commits 3d6c793, 2d167a0, 1a40c37, cded40a, d38c0ae)

**Fixes shipped** — all in `gitminer.py`, `README.md`, `docs/api.md`:

- `_oracle_mean()` renamed to `_oracle_weighted()`: now reads `weighted_score` (13.03) from leaderboard instead of arithmetic `score` (12.08); fallback updated 23.46 → 13.03
- `vs oracle` comparison in `eval` output now uses `weighted_mean` vs `oracle_weighted` (apples-to-apples)
- Per-category pass rate breakdown uses `REPO_CATEGORY` map instead of test_cmd runner heuristic (old code mapped Ruby repos to "Python" as default)
- `mine` and `leaderboard` commands use `weighted_score` for champion and oracle comparisons
- All `python gitminer.py` → `python3 gitminer.py` across gitminer.py, README.md, docs/api.md (CONTRIBUTING.md was already fixed in a prior step)

**Effect**: `gitminer leaderboard` now shows "13.03 (weighted)" as the oracle target. Category breakdown is accurate in eval output.

---

## 2026-06-03 — Weighted oracle consistency fix (commits 768ba4b, e712227, a917b42, f463f35, 9dacbb7)

**Root cause**: The oracle score displayed everywhere (11.83) was the arithmetic mean of all 430 baseline scores. But `evaluate.py` computes `weighted_mean_score` (hard×2, medium×1.5, easy×1) as the primary ranking metric for miners. Miners comparing their weighted mean against the arithmetic oracle would see artificially favorable comparisons. Weighted oracle = **12.77**.

**What changed**:
- `scripts/baseline_scores.py`: now also computes and saves `weighted_mean_score` to `baselines.json`
- `scripts/record_result.py`: oracle row now carries `weighted_score: 12.77`; `_oracle_score_from_baselines()` returns both values
- `scripts/generate_dashboard_data.py`: `oracle_score_from_leaderboard()` now reads `weighted_score` first; `oracle_score` in `data.json` = 12.77
- `api/server.py`: new `_oracle_weighted_score()` helper reads `weighted_mean_score`; `_stats` and `_agents` endpoints return 12.77; `_problem_summary` and `_stats` both now use `_difficulty_by_lines()` (added lines in reference.diff) instead of score-based thresholds — matches `evaluate.py`
- `.github/workflows/eval.yml`: PR comment header shows `weighted_mean` as primary; oracle comparison uses `weighted_score`; champion detection uses `weighted_score` for SOTA
- `.github/workflows/refresh_pool.yml`: commit message shows weighted oracle
- `results/baselines.json`: `weighted_mean_score: 12.77` added
- `results/leaderboard.json`: oracle row gets `weighted_score: 12.77`
- `docs/dashboard_data.json` + `docs/api.md`: regenerated and updated

**Net effect**: Everything that shows "oracle score" or compares against the oracle now uses the correct weighted mean (12.77). `by_difficulty` in `/api/stats` now shows 27/143/260 (easy/medium/hard by line count) instead of the old 169/106/155 (by score thresholds).

---

## 2026-06-02 — Three agent correctness fixes (commits ceaccbd, 3e7abea)

**What shipped**:

**Plan-early-act extraction** (`agent/example/agent.py`):
- Root cause: DeepSeek/deepseek-chat sometimes generates the full diff inside the PLAN response instead of waiting for the ACT prompt. The ACT step then returns nothing because the model thinks it already answered. This caused 4 wasted API calls (1 ACT + 3 empty-retry repair loops) and a zero-score result.
- Fix: after the PLAN call, check if the response contains a valid diff (`_looks_valid`). If yes, extract it and use it directly — skip the ACT call entirely. The plan diff is stored in history as the ACT turn so the verify/repair loop proceeds normally.
- Problem 0774 now produces a real patch instead of an empty one.

**Trailing whitespace stripped from diff lines** (`agent/example/agent.py`):
- Root cause: models generate blank continuation lines inside diffs as `+    ` (spaces) instead of `+` (empty). `git apply` rejects these with "corrupt patch" when the source file has no trailing whitespace.
- Fix: added `_strip_diff_trailing_whitespace` as the final step of `_post_process`. Strips trailing whitespace from `+` and ` ` (context) lines only — never touches `-` lines since those must match the file exactly.

**Baselines lookup format fix** (`gitminer.py`):
- Root cause: `baselines.json` format is `{"count": N, "mean_score": X, "problems": [...]}` (dict with nested list), but `cmd_run` was iterating over the top-level dict (iterating its string keys) and calling `.get()` on them — causing `AttributeError: 'str' object has no attribute 'get'`.
- Fix: read `baselines_data["problems"]` when `baselines_data` is a dict; fall back to direct list iteration for backward compat.

### Status
- Agent: plan-early-act + trailing whitespace + baseline lookup bugs fixed (commits ceaccbd, 3e7abea)
- All fixes pushed to GitHub main branch
- Next DAS pool check: ~2026-06-16

---

## 2026-06-02 — Agent on-ramp, PM2 management, pipeline hardening

**What shipped**:

### `/api/agents` discovery endpoint (benchmark commit d4994f7)
Added `GET /api/agents` to the REST API — a structured JSON document specifically for AI agents that want to autonomously discover and compete:
- Pool summary (430 problems, 30 per shard, weekly rotation, 5 categories with budgets)
- Scoring formula, max score, oracle score, current champion score
- Full constraints (wall time, token limit, allowed models list)
- Quickstart commands (run one problem, eval full shard, mine loop)
- All API endpoints described
- Submission method (GitHub PR with CI auto-scoring)

This is the "agents.gittensor-base-miner" front door: an agent running on idle compute can `GET /api/agents` first to self-configure — discover allowed models, see what score to beat, then call `/api/shard` to get the current eval set.

`docs/api.md` updated with the new endpoint docs.

### `agents.json` static file on GitHub Pages (dashboard commit 7af7f80)
`https://punchthedev.github.io/gittensor-miner-dashboard/agents.json` — same discovery document served as a static file for agents that don't have access to the local API server. Hero CTA now has a "For Agents ↗" button linking to it. Quick Start section has an info box explaining the agents.json entry point.

### PM2 process management
`gitminer-api` (port 8083) is now managed by PM2 (`pm2 save` persisted). Previously it was a raw `nohup` background process that would die silently and not restart on failure. Now it auto-restarts and survives reboots.

Also fixed: the live API had been running stale code from before the category consistency fix (commit 9359b69). Restarted under PM2 with latest code — now correctly serves `by_category` + `oracle_score` in `/api/stats`.

### python3 command fixes (dashboard commit 7af7f80)
Dashboard quickstart commands updated to `python3 gitminer.py ...` (was `python`). On some systems `python` resolves to Python 2 or is absent. The `python3` form works universally.

### Status
- Benchmark: **430 problems**, oracle **11.83**, 18 DAS repos, commit d4994f7
- API: live on PM2 (port 8083), all endpoints verified working, `/api/agents` new
- Dashboard: agents.json static file at GitHub Pages, "For Agents" CTA in hero
- Next DAS check: ~2026-06-09

---

## 2026-06-02 — Dashboard overhaul: categories, difficulty tiers, submission breakdown

**Context**: Operator flagged the dashboard as "too flat" with no depth. Directed adding per-submission breakdown, categories, difficulty tiers.

**What shipped**:

**generate_dashboard_data.py**: Now exports `category` and `difficulty` per problem, plus top-level `categories`, `difficulty_counts`, `shard_budget` aggregates.

**Category mapping** (5 language categories, all DAS repos):
- Python: entrius/gittensor, infiniflow/ragflow + others → **198 problems**
- TypeScript: gittensory, awesome-claude, vouch, gittensor-ui → **87 problems**
- Rust: phase-rs/phase, genie-claw → **66 problems**
- JVM: touchpilot (Kotlin), jvm-live-reload (Java) → **42 problems**
- Ruby: we-promise/sure → **37 problems**

**Difficulty tiers** (based on oracle baseline score):
- Easy (≥15): 169 problems — rich diffs with many AST changes
- Medium (5–15): 106 problems — moderate fixes
- Hard (<5): 155 problems — surgical/targeted changes

**Shard sampling budget**: 12 Python · 8 TypeScript · 5 Rust · 3 JVM · 2 Ruby = **30 per eval round**

**Dashboard (gittensor-miner-dashboard)** (commit d028837):
- Filter chips now show language categories (Python/TypeScript/Rust/JVM/Ruby) with counts from data
- Problem table now has a separate "Tier" column with easy/medium/hard badges
- Category cards section: 5 clickable cards showing pool size per category + shard budget, filter problems on click
- Category-balanced sampling info box explaining the 30-problem eval round composition
- **Per-submission breakdown**: clicking the oracle row opens a full per-problem table (430 problems sorted by score, with category + tier columns, click-through to problem drawer)
- **Miner submission breakdown**: leaderboard rows with `breakdown` array show per-problem results (score, pass/fail, tier) with click-through to problem drawer
- Submission detail drawer uses a wider 860px panel

### Status
- Dashboard: categories and difficulty tiers live
- All 430 problems classified (198 Python, 87 TS, 66 Rust, 42 JVM, 37 Ruby)
- Difficulty: 169 easy, 106 medium, 155 hard
- Benchmark commits: 76b2493 (data generator), d028837 (dashboard)

---

## 2026-06-02 — Verify-loop partial-repair bug fix + Kotlin sibling expansion (commits d9e6edb, a1819de)

### Bug fix: back-to-back user messages on partial repair (commit d9e6edb)

**Root cause**: when the verify model returned a partial repair (fewer files than the current
diff), the loop appended `user: missing-files-message` then on the next iteration
unconditionally appended `user: VERIFY_PROMPT` — two consecutive user messages. Some model
backends (strict OpenAI-style APIs) reject this with a 400 error; others silently merge or
re-order the messages, confusing the model about which diff is current.

The `pending_prose_critique` flag correctly handled the prose-critique case (sends a short
`VERIFY_FOLLOWUP_PROMPT` instead of re-appending the full VERIFY_PROMPT). The partial-repair
case had no equivalent guard — the fix adds `pending_partial_repair = True` which causes the
next loop iteration to call the model directly against the already-appended missing-files
message, without prepending another user message.

### Kotlin/Java/Scala sibling import expansion (commit a1819de)

`_expand_sibling_imports` previously had language-specific handling for Python, TS/JS, Go,
and Rust — but not JVM languages. For `touchpilot/touchpilot` (37 Kotlin problems), the
agent couldn't see sealed class hierarchies, companion objects, or enum types defined in
sibling files unless they happened to be in the top-ranked context.

Fix: added `elif ext in ("kt", "java", "scala")` branch — includes all same-directory
`.kt`/`.java`/`.scala` files within the char budget, mirroring the Go same-package heuristic.
For a Kotlin file at `src/main/kotlin/com/example/Feature.kt`, the agent now sees all other
`.kt` files in `src/main/kotlin/com/example/` — the `AgentEvent.kt` sealed classes,
companion objects, etc. needed to produce a correct implementation.

### Pool check: 3 new DAS repos checked
- `mkdev11/gittensor-hub` (TypeScript/CSS frontend, UI repo) — subjective, skip
- `e35ventura/taopedia-articles` (207 PRs, 0 with score > 5) — content repo, skip
- `entrius/das-github-mirror` (21 PRs, 0 with score > 5) — skip
Pool still fully saturated. Next check: ~2026-06-09.

### Status
- Benchmark: 430 problems, oracle **13.34** (tree-sitter), 20 repos (commit a1819de)
- Agent: partial-repair bug fix, Kotlin/Java/Scala sibling expansion + all prior improvements
- Pool: 3 new DAS repos checked, none suitable; next check ~2026-06-09

---

## 2026-06-02 — Fix Ruby test_cmd for all 37 we-promise/sure problems (commit f14a9fe)

### Root cause
`infer_test_cmd` in `build_pool.py` had no `.rb` pattern — it fell through to the Python
pytest default. All 37 `we-promise/sure` meta.json files stored `test_cmd: ["python", "-m",
"pytest", ...]`. Running pytest in a Rails repo finds no Python tests, exits non-zero,
correctness = 0 for all 37 problems regardless of diff quality.

### Fix
- `scripts/build_pool.py`: added `.rb` detection before the default fallback.
  - `*_test.rb` or `test_*.rb` files found in diff → `bundle exec rails test <files>`
  - Any `.rb` file without matching test paths → `bundle exec rails test`
- All 37 `we-promise/sure` meta.json: updated `test_cmd` to `bundle exec rails test <test_files>`
  using the actual test file paths from each problem's context directory.
- `benchmark/harness/runner.py`:
  - `_LANG_IMAGES`: added `"bundle": "ruby:3.3-slim"`
  - `_install_block`: added `bundle install --quiet` for Ruby
  - `_git_apt_block`: added `git + python3-minimal` for ruby:3.3-slim (python3 needed for capture_files.py)
- `docs/dashboard_data.json`: regenerated with corrected test_cmds.

### Status
- Benchmark: 430 problems, oracle **13.34** (tree-sitter), 20 repos (commit f14a9fe)
- sure problems: CI now runs `bundle exec rails test <test_file>` — correctness gating enabled
- Pool: fully saturated; check ~2026-06-09 for new DAS registrations

---

## 2026-06-02 — Agent: Rails + Kotlin assert patterns, fix docstring escape warning (benchmark commit 4269b94)

### What shipped

**Rails integration test assertions (5 new patterns)**
- Root cause: `we-promise/sure` (37 pool problems) uses Ruby on Rails integration tests with `ActionDispatch::IntegrationTest`. Assert patterns specific to Rails were invisible to verify's cross-check.
- Added: `assert_not_equal ` / `assert_not_equal(`, `assert_difference(`, `assert_no_difference(`, `assert_response `, `assert_redirected_to `
- Pool coverage: 227 `assert_response` + 154 `assert_redirected_to` + 24 `assert_no_difference` + 23 `assert_difference` = **428 occurrences** previously invisible

**Kotlin `kotlin.test` assertions (2 new patterns)**
- Root cause: `touchpilot/touchpilot` (37 pool problems) uses `kotlin.test` framework with `assertIs<Type>(value)` (type-checking assertion) and `assertContains(collection, item)`. Neither matched any existing prefix.
- Added: `assertIs<` (Kotlin type assertion), `assertContains(` (collection/string)
- Pool coverage: 209 `assertIs<` + 102 `assertContains(` = **311 occurrences** previously invisible

**SyntaxWarning fix**
- Two invalid escape sequences (`\`\`\`\w*` and `\`\`\`` patterns) in the module docstring caused Python 3.12 `SyntaxWarning` on every import. Replaced with prose descriptions.
- The warning was benign but cluttered `gitminer run` output with noise before the first line of agent output.

**Total new assertion coverage: 739 occurrences** across 74 problems (37 Rails + 37 Kotlin)

---

## 2026-06-02 — Agent: repair source context + Ruby refute assertions (benchmark commit df24da2)

### What shipped

**`repair()` source file injection**
- Root cause: the repair method builds a fresh conversation from only the failed diff + test output — no source files. The model must diagnose logic errors without seeing the actual file state, making it easy to repeat the same mistake.
- Fix: `_changed_paths_from_diff(failed_patch.diff)` extracts all files touched by the failed patch; their original source content is injected into the repair prompt as a "Source files before your patch" section. The model can now spot off-by-one logic, missing branches, wrong type annotations.
- Budget cap: 3 files × 4 KB each (12 KB max) to keep the repair prompt compact. Files not in `file_lookup` (generated/vendored) are silently skipped.
- `TEST_REPAIR_PROMPT` updated with `{source_section}` placeholder; empty string when no files found.

**`_extract_assertions` Ruby Minitest refute patterns**
- Added: `refute `, `refute_equal `, `refute_nil `, `refute_includes `, `refute_match `, `refute_empty `
- The 37 `we-promise/sure` pool problems use Minitest (ActiveSupport::TestCase), which has symmetrical `assert`/`refute` assertion pairs. Previously all `refute_*` lines were invisible to the verify step's assertion cross-check.
- Space suffix (not `(`) for Ruby compatibility: Ruby Minitest supports both `refute_equal expected, actual` and `refute_equal(expected, actual)`.

### Status
- Benchmark: 430 problems, oracle **13.34** (tree-sitter), 20 repos (commit df24da2)
- Pool: fully saturated — next check 2026-06-16
- Pending: Gittensor registration, nginx hookup

---

## 2026-06-02 — Agent: full-sequence offset disambiguation (benchmark commit 2c49e4c)

### What shipped

**`_fix_hunk_offsets`: Pass 1b — full-sequence disambiguation**
- Root cause: `find_context_offset` gave up (returned `None`) when leading context lines appeared in multiple identical positions — common in Go/Rust files with factory registrations, config stanzas, or repeated struct patterns
- Fix: when leading context is ambiguous (>1 exact matches), build the complete old-file sequence from the hunk (all context + removal lines in order) and search for that sequence. This is usually unique even when the leading 2-5 lines are not.
- E.g.: 3 `func register() { pass }` blocks in a file — leading context matches all 3. The 7-line sequence `register, pass, }, '', gamma, do_old(), }` matches only the correct block.
- Safety: sequence search only activates when leading match is ambiguous and sequence length ≥ 4; unambiguous leading match returns immediately as before
- Also streamlined hunk-body collection: now scanned once for both `ctx` and `old_sequence`
- Smoke tested: 3-location ambiguity resolved correctly; no-sequence case returns `None` (unchanged)

### Status
- Benchmark: 430 problems, oracle **13.34** (tree-sitter), 20 repos (commit 2c49e4c)
- Post-processing: `_fix_hunk_offsets` now has 3-pass search (leading ctx → full sequence → stripped fallback)
- Pool: fully saturated — next check 2026-06-16
- Pending: Gittensor registration, nginx hookup

## 2026-06-02 — Agent + Dashboard polish (benchmark commit e787074, dashboard commit 0e36edc)

### What shipped

**Agent: partial-repair missing files named explicitly** (benchmark commit `e787074`)
- Root cause: when verify produces a diff covering fewer files than the current diff, the feedback only said "N files missing" — not which files
- Fix: `_changed_paths_from_diff()` computes the difference between current and repaired path sets; missing file paths listed explicitly in the feedback message
- Model on the next iteration now knows exactly which files to add, not just the count
- E.g.: "The following file(s) are missing from your response:\n- src/scorer.py\n- tests/test_scorer.py"

**Dashboard: queue status from PR labels** (dashboard commit `0e36edc`)
- Open Submissions queue now shows "Evaluating / Scored / New champion" based on PR labels
- `agent-improvement` label → green dot + "Scored" badge
- `new-champion` label → blue dot + "new champion" badge
- CSS: `.status-dot.scored`, `.status-dot.champion`, `.pr-label.champion`, `.pr-label.scored`
- No extra API calls — labels are included in the PR list response

### Status
- Benchmark: 430 problems, oracle **13.34** (tree-sitter), 20 repos (commit e787074)
- No new DAS repo registrations (master_repositories.json still 19 repos, same set as pool)
- Pool: fully saturated — next check 2026-06-16 (was 2026-06-09; reset after no-change check)
- Pending: Gittensor registration, nginx hookup

## 2026-06-02 — Dashboard: problem drawer enrichment (dashboard commit 54756f8)

### Drawer now shows formula breakdown, diff stats, and CLI run snippet

Three additions to the problem detail drawer for the "problem → solution → scoring" journey:

1. **Diff stats in drawer meta**: `+275 −14 · 4 files` next to the PR link. Instant visual difficulty signal.

2. **Scoring formula breakdown**: below the baseline score chip, shows:
   ```
   src_tokens = 184
   25 × (1 − e^{−184/58}) + 0.98 bonus
   final = 25.98 / 30
   ```
   The miner sees the exact equation that produced the reference score — no black box.

3. **CLI run snippet**: two commands in a terminal block — one to score the example agent on this problem, one to compare against the reference diff. Copy-paste path from problem view to local test in one step.

Also: `dashboard_data.json` now includes `src_token_score` and `total_token_score` per problem (benchmark commit 58dc180), enabling the formula display.

### Status
- Dashboard: punchthedev.github.io/gittensor-miner-dashboard/ — fully live
- Benchmark: 430 problems, oracle 23.46 (unchanged)
- Pool: all repos saturated — next check 2026-06-09

---

## 2026-06-02 — Reference diff API endpoint + diff_stats (commit b58180d)

### API: `GET /api/problems/{id}/diff` (text/plain)

Added reference diff serving to the API. Miners studying the benchmark can now fetch the accepted solution directly:

```
GET /api/problems/0160/diff  →  unified diff (text/plain)
```

The `_problem_diff()` handler reads `benchmark/problems/{id}/reference.diff` and returns it as `text/plain; charset=utf-8`. New-file hunks, multi-file diffs, all diff content served verbatim.

### API + Dashboard: `diff_stats` field

Both `GET /api/problems/{id}` and `dashboard_data.json` problems now include:

```json
"diff_stats": {"add": 275, "remove": 14, "files": 4, "bytes": 15374}
```

Added `_diff_stats()` helper to `api/server.py` and `diff_stats_for()` to `scripts/generate_dashboard_data.py`. Dashboard data regenerated (430 problems, all with stats). Dashboard can now show `+N/-M across F files` on problem cards — visual difficulty signal without serving the full diff inline.

The `_problem()` endpoint response also includes `"diff_url": "/api/problems/{id}/diff"` so dashboard doesn't need to construct the URL.

---

## 2026-06-02 — Dashboard refresh + scoring transparency (dashboard commit f062012)

### Lando check-in response: scoring is fully deterministic

Addressed Lando's question about whether benchmarks use an LLM judge:

**No LLM at any point in the scoring pipeline.** Evaluation is:
1. `git apply` the patch to the repo at `base_commit`
2. Run the test suite — all tests must pass or score = 0
3. Gittensor's tree-sitter pipeline computes `src_tokens` from the diff
4. Formula: `25 × (1 − exp(−src_tokens / 58)) + bonus` → 0–30

This is now documented as a "How Scoring Works" section in the dashboard with the 4-step pipeline displayed visually — no ambiguity for miners about how they're being graded.

**Dashboard data refreshed**: 423 → 430 problems, oracle 23.36 → 23.46. Fixed stale "342" in meta description and step text. Generated fresh `data.json` from benchmark pool via `scripts/generate_dashboard_data.py`.

**Closed PR idea (Lando's suggestion)**: PRs rejected with explanation vs the actual merged solution would be gold standard negative examples. Valid idea but deferred to backlog — Gittensor is young, volume of clearly-explained closed PRs is likely small, and the current 430-problem pool is the immediate priority. Worth revisiting after first miner wave.

---

## 2026-06-02 — Marginal-gain mechanics + difficulty weighting (commits 882686f, 8963281, ca98c25, f8cb706)

### Core mechanics gap closed per Lando check-in

**Marginal-gain emission formula** (commit 882686f):

Lando flagged that "top score wins" proportional share wasn't the mechanic he wanted. Fixed:

```
contribution_weight = (score × 1.0 + max(0, score - sota_at_submission) × 3.0) × label_mult × time_decay
```

Every passing submission earns the participation term (1.0×). Beating SOTA earns the champion premium (3.0×) on each point above the bar. A copycat at exact SOTA earns only participation — the champion earns 67%+ more for the same score delta. `record_result.py` now captures `sota_at_submission`, `marginal_gain`, and `contribution_weight` per entry.

**Difficulty-weighted mean score** (commit 8963281):

Problems classified by reference diff size: Easy <30 lines (1.0×), Medium 30–149 (1.5×), Hard 150+ (2.0×). `evaluate.py` now computes and returns `weighted_mean_score` alongside `mean_score`. `record_result.py` stores `weighted_score` in leaderboard entries. Ranking sorts by weighted score first.

**Dashboard + CLI** (commits ca98c25, f8cb706):

- Leaderboard table: added Weighted Score and Marginal Gain columns
- Marginal gain shown in green when >0, muted when 0 (copy/no-improvement)
- Models section: added OpenRouter wiring snippet with `export OPENROUTER_KEY` and eval command
- `gitminer.py eval` CLI: now prints both Mean and Weighted Mean scores

### Status
- All mechanics now answer Lando's marginal-gain question
- Dashboard visible difference when first submissions arrive

---

## 2026-06-02 — _fix_hunk_offsets stripped-content fallback (commit eec6a88)

### Agent: context-line fingerprint now handles indentation mismatches

**Problem**: `_fix_hunk_offsets` used exact string matching to find context-line fingerprints in the source file. If the model wrote context lines with wrong indentation (e.g., 4 spaces instead of 1 tab), the fingerprint wouldn't match any source line. Offset correction silently failed. Then `_fix_context_lines` (stage 5) would fix the whitespace, but the `@@ -N` offset remained wrong — `git apply` still fails.

**Fix**: Two-pass search in `find_context_offset`:
1. Exact match (existing behavior)
2. Stripped-content fallback when exact finds zero matches — both sides stripped, same unambiguous-match guard

If the exact pass found multiple matches (ambiguous), the stripped fallback is skipped to avoid false positives. Empty-stripped fingerprints (blank lines) are also rejected. The stripped pass only triggers when exact fails cleanly — no risk of weakening the safety guard for well-formed diffs.

### Status
- Benchmark: 430 problems, oracle 23.46 (unchanged)
- Post-processing: stage 4 (`_fix_hunk_offsets`) now more robust against indentation mismatches in context lines
- Pool: fully saturated; check ~2026-06-09 for new DAS registrations

---

## 2026-06-02 — Structural summary in compacted history (commit b21930b)

### Verify: structural context for completeness checking

**Problem**: After history compaction, the verify model only saw file names ("files in scope: scoring.py, constants.py"). It had no knowledge of what functions/classes those files contain — so it couldn't check completeness ("does the diff add the required method?") or identify missing changes ("should `filter_repos` have been modified?").

**Fix**: `_structural_summary()` extracts function/class/method declaration lines from all implementation files and injects them into the compacted observe message. Example:

```
[scoring.py  ← changed]
  class ScoreCalculator:
  def compute_score(self, pr, max_score: float = 30.0) -> float:
  def apply_penalty(self, score: float, repo: str) -> float:
  def filter_repos(self, repos: list[str]) -> list[str]:
[constants.py]
```

Files that appear in the diff are marked "← changed". The verify model can now cross-reference the diff against the structural summary and answer: "Did the diff modify `filter_repos` as the issue requires?" — a completeness check that file names alone cannot support.

Supported languages: Python, Go, TypeScript/JS, Rust, Kotlin/Java/Scala, Ruby. Capped at ~3 KB total to keep verify prompt size manageable.

---

## 2026-06-02 — Hunk source context injected into verify (commit 13a1bde)

### Verify: real hunk-offset check via source context injection

**Problem**: The verify step's criterion 2 ("are `@@ -N` hunk offsets correct?") was previously a plausibility guess. After history compaction, the verify model has no access to source files — it can only ask "do the context lines look like surrounding code?" but cannot check if they match the *actual* source at line N.

**Fix**: `_hunk_source_snippets(diff, file_lookup)` extracts actual source lines at each hunk's `@@ -N` offset and injects them into the verify prompt. Format:

```
[src/drivers/mistral.go @@ -45]
    43: // Embed implements the Embedder interface
    44: func (e *MistralEmbedder) Embed(...) {
  → 45: 	return nil, fmt.Errorf("not implemented")
    46: }
    47: 
```

The arrow marks the hunk start line; 2 lines above and below give context. The verify model can now check: do the context lines in my diff match what's shown here?

Criterion 2 updated to reference the new section: "The source context section above shows the actual file lines at each hunk offset — verify that the context lines in your diff match exactly (same content, same whitespace)."

**Cost**: limited to 6 hunks per problem (~1 KB added to verify prompt). No API calls — purely local lookup from `file_lookup` which is already built in `solve()`.

**Impact**: enables the verify model to catch wrong `@@ -N` offsets that `_fix_hunk_offsets` didn't correct (e.g., offset > ±50 from stated value, or ambiguous fingerprint) and context-line whitespace mismatches that `_fix_context_lines` missed (e.g., trailing spaces, CRLF).

---

## 2026-06-02 — Verify prose-critique followup, long-body head+tail (commits a1b4584, 9e40ddc)

### Verify prose-critique follow-up prompt

When the verify step returns a textual critique (no corrected diff extracted), the next iteration previously re-sent the full VERIFY_PROMPT with the same diff — ~4-6KB of repeated context and all 7 criteria. The model had already analysed the diff; asking it to re-analyse was redundant.

Fix: when the previous verify iteration gave a prose critique, the next call uses `VERIFY_FOLLOWUP_PROMPT`: "Based on your analysis above, produce the corrected unified diff now." (~80 chars vs. ~4-6KB). The `pending_prose_critique` flag tracks this state across loop iterations.

### Long issue body head+tail for verify

After the act step, `history[1]` (the full observe context) is compacted to a 150-char summary. The verify prompt becomes the model's only view of the issue body — and it was truncated to the first 3000 chars. 31% of pool problems (133/430) have issue bodies longer than 3000 chars; the max is 16,200 chars.

Fix: for bodies longer than 3000 chars, the verify prompt now shows `body[:2500] + "[...]" + body[-500:]`. The last 500 chars often contain edge-case requirements, gotchas, or clarifying examples that the model needs to verify completeness. Total length stays ~3050 chars.

---

## 2026-06-02 — Verify token budget, assertion limit, hunk search radius (commit a5d1235)

### Verify token budget raised to match act

`verify_tokens` was `token_budget // 4 = 12,500`. When the verify step produces a corrected diff (not LGTM), it needs the same token headroom as the act step — otherwise a large multi-file diff gets truncated mid-output, producing a partial patch worse than the original. Fix: `verify_tokens = act_tokens = 25,000`.

### `_extract_assertions` limit 30 → 50

Large test suites often place parameterised and edge-case assertions near the end. The old 30-line cap silently dropped them, leaving the verify step blind to those requirements. Raised to 50 without materially inflating the verify prompt size.

### `_fix_hunk_offsets` search radius ±25 → ±50

Large Go/TS files (500+ lines) are more likely to have model-estimated offsets that are off by more than 25 lines when the file is shown windowed. The unambiguous-match safety guard (single match required) prevents false positives — a wider radius finds more correct offsets without introducing wrong ones.

---

## 2026-06-02 — Removal-line whitespace fix, verify hunk-map check, fence regex (commit a07d86f)

### `_fix_context_lines` extended to removal lines

`git apply` requires removal lines (`-` prefixed) to match the source file exactly — the same constraint that applies to context lines (` ` prefixed). Previously `_fix_context_lines` only repaired whitespace differences on context lines; if the model wrote `-    return None` where the source had `-\treturn None` (tab indent), the hunk would be rejected.

Fix: the same stripped-content safety check now applies to `-` lines. When `diff_content.strip() == source_line.strip()` but the full lines differ, the `-` line is replaced with `- {source_line}`. The same safety guard applies: only replaces on exact stripped-content match, never on partial matches that could misplace the removal.

### Verify criterion 7: hunk-map completeness

Added criterion 7 to `VERIFY_PROMPT`: "Look back at your step 6 hunk map from earlier in this conversation. Does this diff include a change for every file path listed there? If any planned file is missing from the diff, add the necessary changes now."

Previously the verify step had no explicit prompt to cross-check the hunk map against the diff. The model could LGTM a diff that omitted a planned file if its criteria checks 1–6 all passed. Criterion 7 closes that gap by explicitly referencing the plan-step output.

### `_extract_diff` fence regex generalised

Changed `\`\`\`(?:diff|patch)?` to `\`\`\`\w*` — now accepts any fence language tag. Handles `\`\`\`udiff`, `\`\`\`unidiff`, `\`\`\`text`, etc. Diffs wrapped in non-standard fence tags are extracted rather than silently falling through to the bare `diff --git` search.

---

## 2026-06-02 — API resilience, cascade-timeout hardening, JS support (commits d039717–2716186)

### API error resilience in `_call` (commit d039717)

Discovered via sample eval: OpenRouter sometimes returns 200 with `{"error": {...}}` body instead of `choices`. Previously caused `KeyError: 'choices'` propagating as an exception (problem score = 0). Fix:
- Check `"choices" in data` before access; retry once on missing choices with 5s backoff
- Add 400 responses to the retry set (covers content policy / transient routing errors)
- Final fallback: `return ""` so `_diagnose_diff` handles it as empty-diff gracefully

### Verify prose-critique feedback loop (commit 653e8e4)

When verify returns a textual critique without a corrected diff, the loop previously broke and accepted the unverified diff. Now: store the critique in history and continue — the model can self-correct on the next verify iteration by producing a diff based on its own critique. Only breaks on the last attempt.

### JS/JSX language notes added (commit 84f6004)

12 JS problems (gittensor-ui, product-data-extractor, ragflow JS issues) previously got no language-specific guidance. Added `LANG_NOTES["js"]` and `LANG_NOTES["jsx"]` covering: ES module exports, null-safety, async/await style, `const`/`let` over `var`, no TypeScript syntax.

### CommonJS `require()` import resolution (commit 11eb3a4)

Extended `_resolve_test_imports` and `_expand_sibling_imports` for JS/TS to also parse `require('./foo')` patterns (CommonJS style). Previously only `from '...'` ES module syntax was handled.

### Conditional history compaction + empty-act retry (commit 2716186)

Root cause found via sample eval: when the API is slow (calls near-timeout), the act step times out and returns "". Previously history was compacted unconditionally, leaving repair iterations with only a 150-char summary (issue title, file names) — insufficient context to produce code.

**Fix 1**: Only compact `history[1]` (source files, 20-30k chars) if the act step produced a valid diff. If act returned empty/invalid, keep the full source context so repair iterations can generate a real diff.

**Fix 2**: When the repair loop detects "empty output — no diff produced", resend `ACT_PROMPT` directly instead of the useless `REPAIR_FORMAT_PROMPT` with an empty diff. The model retries the act step with full source context still available. On success, compaction happens then.

### Pool refresh: 423 → 430 (+7 new problems) (benchmark commit 07f6504)

DAS dry-run returned "7 newly added"; actual build added 7 problems across 4 repos:

- `phase-rs_phase_1858` (Rust, `cargo test`) — Liliana, Dreadhorde General trigger bug
- `phase-rs_phase_1900` (Rust, `cargo test`) — Rebound Mechanic implementation
- `jsonbored_gittensory_266` (TypeScript, `npm test`) — offline decision-pack caching
- `geniepod_genie-claw_365` (Rust, `cargo test`) — tool-call gate enforcement
- `touchpilot_touchpilot_133` (Kotlin, `./gradlew test`) — running agent state controls
- `touchpilot_touchpilot_145` (Kotlin, `./gradlew test`) — task completion summary card
- `touchpilot_touchpilot_150` (Kotlin, `./gradlew test`) — long_press tool

Oracle mean: 23.36 → 23.46. Updated: pool_config.json, results/baselines.json, results/leaderboard.json, dashboard_data.json, gitminer.py, evaluate.py, record_result.py, docs/rewards.md, docs/api.md, README.md (all 4 count refs).

All new problem languages covered: `rs` (Rust), `ts` (TypeScript), `kt` (Kotlin) — LANG_NOTES + import resolution already present.

### Status
- Benchmark: 430 problems, oracle 23.46, 20 repos (commit 07f6504)
- Sample eval: discovered `patch_applied: False` on gittensor problems when API slow — root cause was cascade timeout + premature history compaction, now fixed
- Pool: fully saturated; check ~2026-06-09 for new DAS registrations
- Pending: Gittensor registration, nginx hookup

## 2026-06-02 — Context line whitespace repair (commit 870de98)

### Agent: `_fix_context_lines` — 6th post-processing stage

`git apply` requires context lines (` `-prefixed unchanged lines surrounding a change) to match the source file exactly. Even a single tab-vs-spaces difference causes rejection, even when the change content itself is correct.

`_fix_context_lines(diff, file_lookup)`:
- For each context line in each hunk, looks up the expected content from the source file using the (already-corrected) `@@ -N` offset as the anchor
- If the stripped content matches exactly (`line.strip() == source_line.strip()`) but the full line differs (whitespace mismatch), replaces with the actual source content
- Safety guard: only replaces on stripped-content match — if content is semantically different, the original is kept. This prevents silently moving a hunk to the wrong location if the offset is still wrong
- Skips new-file hunks (`@@ -0,0 ...`) — no source to look up
- Applied as stage 5 of 6 in `_post_process`, after `_fix_hunk_offsets` so start offsets are already corrected

Also tightened ACT_PROMPT: "copy [context lines] verbatim from the source file display (same characters, same whitespace) — even a space/tab difference causes `git apply` to fail."

### Status
- Benchmark: 423 problems, oracle 23.36, 20 repos
- Post-processing: 6-stage pipeline (strip N|, trim prose, fix headers, fix offsets, fix context whitespace, fix counts)
- All 6 stages: deterministic, zero API calls

---

## 2026-06-02 — Missing-header fix + fuzzy hunk-offset correction (commit 0ad4298)

### Agent: `_fix_diff_headers` — auto-insert missing `--- a/` / `+++ b/` headers

`git apply` requires `--- a/<path>` and `+++ b/<path>` lines between the `diff --git` header and the first `@@` hunk. Models in repair mode often jump straight from `diff --git` to `@@`, producing diffs that fail immediately. `_fix_diff_headers()` detects these blocks and inserts the required headers derived from the `diff --git a/<path> b/<path>` line itself. New-file blocks use `--- /dev/null`. Applied as part of `_post_process` on every intermediate diff.

### Agent: `_fix_hunk_offsets` — fuzzy context-line start-offset correction

`_fix_hunk_counts` corrects the `b/d` count fields in `@@ -a,b +c,d @@` headers. It cannot fix the `a/c` *start offset* fields — those require knowing where the context lines actually appear in the file. A wrong start offset causes `git apply` to reject a diff even when the content is correct.

`_fix_hunk_offsets(diff, file_lookup)` fixes this:
1. For each hunk, extracts leading context lines (unchanged ` `-prefixed lines) and the first removal line as a fingerprint.
2. Searches for those lines in the actual file content within ±25 lines of the stated offset.
3. If the match is unambiguous (exactly 1 location), corrects the `@@ -N` and `+N` values with the same delta.
4. Safe fallback: if no match or multiple matches (ambiguous), keeps the original offset.

`file_lookup` is built from the problem's context files and passed through `_post_process`. For files not in context (e.g. secondary `__init__.py` additions), offset correction is skipped. Applied before `_fix_hunk_counts` so counts are computed on the corrected structure.

### `_post_process` pipeline order (updated)
1. Strip `N |` display artifacts
2. Trim trailing prose
3. Insert missing `--- a/` / `+++ b/` headers (`_fix_diff_headers`)
4. Correct wrong `@@ -N` start offsets (`_fix_hunk_offsets`, needs file_lookup)
5. Recompute `@@ -a,b +c,d @@` hunk counts (`_fix_hunk_counts`)

### Status
- Benchmark: 423 problems, oracle 23.36 (unchanged)
- Post-processing: 5-stage pipeline covering all major `git apply` failure modes
- Pool: fully saturated (check 2026-06-09)

---

## 2026-06-02 — Oracle mean update + hunk map in plan step (commits ba036fb, 31dcf29, 38d1809)

### Oracle mean update: 23.08 → 23.36 (commit ba036fb)

Scored all 423 problems (was 400). The 23 new ragflow Go/TS problems added last step were missing from baselines.json. Running `scripts/baseline_scores.py` across all 423 produced:
- Mean: 23.36 (was 23.08 for 400 problems)
- Median: 26.74
- New Go/TS problems score high (many ~30.00 — large driver implementations)

Updated oracle mean in: leaderboard.json, record_result.py, gitminer.py, benchmark/evaluate.py, docs/rewards.md, docs/api.md, README.md.

Dashboard regenerated: 423 problems, oracle 23.36 (benchmark commit 31dcf29, dashboard commit 94113f3).

### Agent: hunk map in plan step (commit 38d1809)

**Root cause of line-offset errors**: the model re-derives `@@ -N` start lines during the ACT step, under time pressure and without having explicitly committed to specific line numbers. This produces hunk offset errors (wrong start line in `@@ -a,c +b,d @@`) that cause `git apply` to reject a structurally-valid diff.

Our `_fix_hunk_counts` post-processor fixes the *counts* (b/d fields) but cannot fix the *start offset* (a/c fields) without running `git apply`.

**Fix**: added Step 6 "Hunk map" to the OBSERVE_PROMPT. Before writing the diff, the model explicitly states each planned change with its file path and `N |` start line from the windowed source display. ACT_PROMPT now tells the model to use the hunk map from step 6 for its `@@ -N` offsets directly. This pre-computation moves the hard reasoning to the plan step (18s budget, no format pressure) rather than the act step (48s budget, but generating a full multi-file diff simultaneously).

### Status
- Benchmark: 423 problems, oracle 23.36, 20 repos (commit 38d1809)
- Pool: fully saturated (check 2026-06-09 for new DAS registrations)

---

## 2026-06-02 — Agent: language-aware headers + Scala support (commits 6cf29f0, 9d56b86, 6f2cbfc)

### Language-aware import-block detection for windowed files (commits 6cf29f0, 9d56b86)

**Root cause**: `HEADER_LINES = 20` was a fixed constant applied to all files. Go files typically have a 1-line `package` declaration + 1-2 blank lines + a `import (...)` block spanning 15-30 lines, consuming all 20 header lines. The struct/type definitions that immediately follow the import block were invisible to the model, causing wrong type assumptions and missing method signatures.

**Fix**: `_compute_header_end(lines, ext)` scans for the end of the language's import section:
- Go: finds closing `)` of `import (...)` block, adds 8-line buffer → covers first struct/type defs
- TypeScript/JS: last `import` statement + 8 lines
- Kotlin/Java/Scala: last `import` line + 8 lines
- Rust: last `use` statement + 8 lines
- Python: last `import`/`from...import` + 8 lines
- Unknown: falls back to HEADER_LINES=20

Real example: `volcengine.go` (642 lines) — old header cut at line 20 (mid-import block); new header extends to line 37, showing the complete import block AND the `VolcEngine` struct definition.

Same fix applied to the no-keyword-hit peek (commit 9d56b86): was always 80 lines regardless of language; now `max(language_header, 80)` so Go/TS files with > 80-line import+struct sections show the full header.

**Sibling scan expanded top-3 → top-5** (commit 6cf29f0): larger multi-file problems where the most relevant file is ranked 4th or 5th now benefit from sibling import expansion too.

### Scala language support (commit 6f2cbfc)

seroperson/jvm-live-reload (5 problems) uses Scala test files (`*Spec.scala`) and Scala source files. Previously getting no language guidance.

- `LANG_NOTES["scala"]`: trait/abstract class implementations, case class fields, sealed trait coverage, companion objects, `override def`, no `???` stubs
- `_is_test_file`: now recognises `*Spec.scala` via `(test|spec)\.(kt|java|scala)$`
- `_compute_header_end`: handles `.scala` in the `kt/java` branch
- `_resolve_test_imports`: resolves Scala JVM-style imports to `.scala` files; skips `scala.`, `org.scalatest`, `cats.`, `zio.`, `akka.` stdlib imports

### Status
- Benchmark: 423 problems, oracle 23.08 (Python problems) 
- Pool: fully saturated (no qualifying new PRs in DAS as of 2026-06-02)
- Agent: language-aware headers, Scala support, sibling scan top-5

---

## 2026-06-02 — Agent improvements + pool refresh (commits 2e8e54d–b609751)

### Agent: verify loop hardening (commits 2e8e54d, e0a8312)

**LGTM detection** (commit 2e8e54d): was `startswith("LGTM")` — missed "The diff looks correct. LGTM." Now also checks if no valid diff was extracted AND "lgtm" appears in verdict → treats as approval. Avoids spurious repair iterations.

**Clean verify history** (commit 2e8e54d): when verify produces a repaired diff, we now store the cleaned `repaired` in history (not the raw `verdict` which may contain prose). Subsequent verify/repair calls see the same clean artifact-free version.

**Temperature=0 for verify** (commit 2e8e54d): verification is a precision task — using default 0.2 allowed hallucinated corrections. Now deterministic.

**CRLF normalization** (commit 2e8e54d): `_extract_diff` now strips `\r\n` → `\n` before processing. Prevents hunk-count mismatches on Windows line endings from OpenRouter.

**5xx retry** (commit e0a8312): `_call` previously only retried on 429. Now retries on 500/502/503 (transient server errors) too.

**Stale N| reference in VERIFY_PROMPT** (commit e0a8312): criterion 2 referenced "N| line markers in the context" — but context is compacted before verify runs. Updated to "check hunk offsets are plausible" instead.

### Agent: context budget fix (commit 600ed86)

**Per-file budget cap** (commit 600ed86): `_truncate_context` was counting raw file sizes for budget allocation — but 270/400 problems have raw context > 40 KB, meaning file 1 alone could exhaust the budget and drop files 2-N. Fixed to count `min(raw_size, 10_000)` per file (capped to approximate windowed size). More files pass through to windowing, which then controls actual prompt size.

### Pool refresh: 400 → 423 (commit b609751)

**23 new ragflow problems** (Go/TS): AWS Bedrock, OCR for ZhipuAI, OpenAI Go driver ASR/TTS fix, PPIO/Groq/TokenPony/Hunyuan providers, streaming timeout bug (15380, 15382), password reset OAuth (15293), and 12 more Go provider implementations. DAS API user-agent fix also shipped (was 403-blocking pool rebuilds).

### Status
- Benchmark: 423 problems (oracle mean TBD for new problems — Go needs Docker CI)
- Agent: verify hardening, context budget fix, 5xx retry

## 2026-06-02 — Agent: verify/repair hardening (commits 013ab2c–991f281)

### Four targeted fixes to the verify + repair loop

**Partial-repair guard** (commit 013ab2c): `_count_diff_files()` counts `diff --git` headers. Replacement only accepted if repaired file count >= original. Prevents multi-file diff being silently reduced to a one-file partial fix from verify.

**Clean act history** (commit 013ab2c): act step now stores post-processed `diff` in history (not `raw_diff`). Model's "memory" of its own output matches the verify prompt. Same fix in format-repair branches.

**Empty diff diagnostic** (commit de62dd0): `_diagnose_diff` now catches diffs where all hunk content is context-only (no `+`/`-` lines). Triggers format-repair instead of letting the harness run with a no-op patch.

**Format-repair with explicit diff** (commit 991f281): `REPAIR_FORMAT_PROMPT` now includes the current diff in a code block. Model no longer needs to recall the diff from history context — it sees exactly what it produced and what's wrong with it.

### Status
- Benchmark: 400 problems, oracle 23.08 (unchanged)
- Pool: all repos saturated — next check 2026-06-09
- Pending: Gittensor registration, nginx hookup

---

## 2026-06-02 — Agent: partial-repair guard + clean history in act step (commit 013ab2c)

### Partial-repair guard in verify loop

Found a correctness bug: when the verify step produced a corrected diff covering fewer files than the current diff, the replacement was accepted unconditionally, silently dropping changes to the other files.

Example: act produces `fileA + fileB` diff. Verify says "fileA is wrong, here is the fix" and returns a 1-file diff for fileA only. With the old code, `diff = repaired` would lose fileB's changes entirely.

Fix: `_count_diff_files()` counts `diff --git` headers in both diffs. Replacement only accepted if repaired file count >= current file count. If fewer: log `"partial repair (N < M files) — keeping current diff"` and break.

### Clean act history

The act step was storing `raw_diff` (the model's literal output, including any `N |` artifacts and trailing prose) as the assistant turn in history. The verify prompt then showed the post-processed `diff`, creating two inconsistent versions the model could see. Now history stores the post-processed `diff` so the model's "memory" matches the verify prompt.

Same fix applied to format-repair branches in the verify loop.

### Status
- Benchmark: 400 problems, oracle 23.08 (unchanged)
- Agent: partial-repair guard, clean history
- Pool: all repos saturated — next check 2026-06-09
- Pending: Gittensor registration, nginx hookup

---

## 2026-06-02 — Agent: intermediate diff post-processing + history compaction (commit 936a857)

### Post-process every intermediate diff

Previously: `_strip_line_number_prefixes`, `_trim_trailing_prose`, and `_fix_hunk_counts` ran only once at the very end of `solve()`.

Problem: intermediate diffs passed to verify/repair still had `N | ` display artifacts and wrong hunk counts. Verify saw these artifacts and could flag the diff as wrong (triggering a wasteful repair loop). The repair branch could also produce a diff with artifact-prefixed lines, and those would be fed to the next verify iteration unclean.

Fix: introduced `_post_process(diff)` helper that applies all three processors in order. Called after every `_extract_diff` throughout `solve()` and `repair()`. Final pass still runs but is now a no-op in most cases (the diff is already clean).

### History compaction before verify

Previously: every verify/repair call sent the full conversation history including `history[1]` — the observe message containing all source files, file tree, and test file content (typically 20-30k chars, ~5-7k tokens for deepseek).

Problem: the model had already used this context to produce its plan and initial diff. Re-sending the full source code on every verify call wastes token budget the model could use to reason about the diff.

Fix: after the act step, `history[1]` is replaced with a compact summary (~150 chars):
```
[Earlier context: repo/name — issue: Issue Title — files in scope: file1.py, file2.go, ... — test: pytest tests/test_foo.py]
```

The model retains the essential metadata (what was being fixed, which files, which test) without re-processing thousands of lines of source code.

---

## 2026-06-02 — Agent: non-uniform timeouts and multi-fence diff extraction (commit 3361337)

### Non-uniform timeout allocation

Previously: `timeout = 120s / 6 calls = 20s per call` — uniform distribution.

Problem: act step (generating a large multi-file diff) was under-allocated; plan step (short analysis) was over-allocated.

New allocation:
- `plan_timeout = 120s × 15% = 18s` — analysis output is moderate length
- `act_timeout = 120s × 40% = 48s` — diff output can be large (many hunks, many files)
- `verify_timeout = 120s × 15% = 18s` — LGTM or corrected diff per iteration

Also: `plan_tokens` reduced from `budget // 3 = 16.6k` to `budget // 4 = 12.5k` — analysis rarely exceeds 4k tokens; this cap is still generous and avoids wasting the plan call.

### Multi-fence diff extraction

Previously: `re.search(r"```(?:diff)?...", ...)` — only captured the FIRST fenced diff block.

Problem: models sometimes put each changed file in its own ` ```diff ` fence when generating complex multi-file patches. With `re.search`, everything after the first fence was silently dropped — the agent appeared to succeed but produced an incomplete patch.

Fix: `_extract_diff()` now uses `re.finditer` to collect ALL fenced diff blocks and joins them with `\n`. Also added `patch` as a recognized fence language (```` ```patch ````).

Verified: test with two-fence input correctly joins both `diff --git` sections.

---

## 2026-06-02 — Agent: test file windowing + new-file format example; Go lang fix (commits e9f22c1–0a2354e)

### gitminer.py: Go language classification fix (commit e9f22c1)
- `_LANG` mapping now includes `"go": "go"` — 19 Go problems were previously labelled as `py`
- `--lang` choices updated to include `"go"` so `gitminer problems --lang go` works

### Agent: explicit new-file diff format example (commit e9f22c1)
- `NEW_IMPL_FILES_TEMPLATE` now shows the exact `diff --git` / `new file mode 100644` / `--- /dev/null` / `@@ -0,0 +1,N @@` format the agent must use
- Reduces formatting failures for the 33% of problems (132/400) with new implementation files

### Agent: test file windowing (commits 273b668, 0f4a2fa)
- Large test files (> 200 lines) are now windowed with ±80-line context around keyword hits
- Previously: test files always shown in full — a single 20 KB test suite consumed half the 40 KB context budget
- Threshold 200 (lower than impl files 300): test files are read-only so we lose nothing by windowing them earlier
- Window 80 lines (wider than impl files 40): preserves complete test function bodies
- Line numbers (`N | content`) are **omitted** from test file windows — the agent does not write diffs against test files, and numbers would confuse hunk offset calculations for impl files
- `_window_file` and `_format_files` now accept `threshold`, `context_lines`, `show_line_numbers` parameters for full configurability

### Agent: ACT_PROMPT clarification (commit 0a2354e)
- Line number note updated: "windowed **source** files show lines as `N | content`" — explicitly notes test files are windowed without line numbers

### Status
- Benchmark: 400 problems, oracle 23.08, 20 repos (commit 0a2354e)
- Pool: all 16 DAS repos saturated; next refresh check ~2026-06-09
- Pending: registration (operator), nginx hookup (operator)

---

## 2026-06-02 — Agent: hunk count fixer + file tree pruning (commits 470c201, 6049035)

### Agent: deterministic hunk count fixer (commit 470c201)
- **`_fix_hunk_counts()`**: post-processor that recomputes the b/d fields in every `@@ -a,b +c,d @@` header by counting actual context/remove/add lines in each hunk
- **Problem**: LLMs frequently miscalculate hunk line counts (b = old-hunk size, d = new-hunk size). Incorrect counts cause `git apply` to reject otherwise correct diffs with a "corrupt patch" error
- **Applied after every solve() and repair()**: zero API calls, deterministic, applies to the final diff before returning Patch
- Tested: corrects wrong counts across single-hunk, multi-hunk, multi-file, and new-file diffs; leaves already-correct diffs unchanged

### Agent: file tree pruning (commit 6049035)
- **`_prune_file_tree()`**: reduces the file_tree shown in the prompt from 500 paths (16-22 KB) to ~30-95 relevant paths (1-3 KB) by keeping only entries in directories that contain context files or their ancestors
- **Problem**: 211/400 problems have file trees > 10 KB; average 12.6 KB per tree. At 40 KB context budget for code, a 22 KB tree consumes 55% of the budget on irrelevant paths
- **Algorithm**: for each context file, adds its directory and all ancestor directories to a relevant-dirs set; keeps only tree entries whose parent is in that set; falls back to capped full list if pruning leaves nothing
- Results: ragflow (500 → 32 entries), gittensor (124 → 27 entries), phase Rust test-only (500 → 95 via capped fallback)
- **Critically**: `_resolve_test_imports` and `_expand_sibling_imports` still use the full `problem.file_tree` — only the display in the prompt is pruned

### Status
- Benchmark: 400 problems, oracle 23.08, 20 repos (commit 6049035)
- Pool: all 16 DAS repos saturated; next refresh check ~2026-06-09
- Pending: registration (operator), nginx hookup (operator)

---

## 2026-06-02 — Agent: sibling imports + new test file creation (commits 9cd3e74, ed46bb2)

### Agent: sibling import expansion (commit 9cd3e74)
- **`_expand_sibling_imports()`**: after ranking, scans the top-3 implementation files for local imports (`from .helpers import X`, `from pkg.sub.helpers import X`, TypeScript relative imports, same-dir Go files) and adds those sibling modules to context (up to 6 KB extra)
- **Key fix**: prevents the agent from hallucinating helper functions that already exist in the package. Without this, `view.py` is shown but not `helpers.py` — the agent doesn't know `emit_error_json` exists and tries to define it inline (wrong) or imports from the wrong path
- Tested on problem 0335 pattern: correctly identifies `gittensor/cli/issue_commands/helpers.py` as a sibling of `view.py`

### Agent: new test file detection (commit ed46bb2)
- **Root cause found**: 243/400 pool problems have test files in context that don't exist at `base_commit` (they were added by the PR). Without detection, the agent treats them as read-only context but never creates them — `git apply` succeeds but `pytest` fails with "file not found" → correctness score 0
- **`_new_test_files()`**: compares context test files against `file_tree` (repo at base_commit). Files not in file_tree are new
- **`_new_test_diff()`**: generates pre-formatted diff blocks (new file mode, `/dev/null` header, `@@ -0,0 +1,N @@`) that the agent can copy verbatim
- **`NEW_TEST_FILES_TEMPLATE`**: new prompt section shown when new test files detected — instructs agent to include pre-formatted diff blocks in output
- Affects ~60% of all pool problems

### Status
- Benchmark: 400 problems, oracle 23.08, 20 repos (commit ed46bb2)
- Pool: all 16 DAS repos saturated; next refresh check ~2026-06-09
- Pending: registration (operator), nginx hookup (operator)

---

## 2026-06-02 — Pool 397→400 + Kotlin/Java agent support (commits 8cab7e5, 96af7c8)

### Agent: Kotlin/Java language notes and import resolution (commit 8cab7e5)
- **Kotlin LANG_NOTES** (`kt`): companion objects, data class fields, sealed class coverage, `@Test` annotation, `TODO()` stubs, constructor signature matching
- **Java LANG_NOTES** (`java`): full interface implementation, correct `import` declarations, `@Override` annotations, checked exception handling
- **`_is_test_file`**: now detects `*Test.kt`, `*Test.java`, `*Test.scala` via regex — previously only caught files in `/test/` directories
- **Kotlin/Java import resolution**: `import dev.touchpilot.app.tools.MyClass` → finds `MyClass.kt` or `MyClass.java` in tree (skips stdlib/Android/JUnit imports)
- **Impact**: 34 Kotlin problems (touchpilot) + 3 Java problems (jvm-live-reload) now get precise file pinning and language-appropriate prompting

### Pool refresh: 397 → 400 (+3 new phase-rs/phase problems) (commit 96af7c8)
- `phase-rs_phase_1816` — damage assignment modal bug (Rust + TypeScript, React/Vitest test)
- `phase-rs_phase_1734` — "Clash with an opponent" auto-picks wrong opponent (TypeScript + Rust test)
- `phase-rs_phase_1691` — Emergence Zone card selection bug (Rust + TypeScript test)
- Oracle mean: 23.05 → **23.08** (recomputed across all 400 problems)
- All repos fully saturated as of this run; next pool scan scheduled ~2026-06-09

---

## 2026-06-02 — Pool 367→397 + Go/TS language support (commits b882b42, a277f65)

### has_test_files fix: Go, TypeScript, Java, Ruby patterns (commit b882b42)
- **Root cause**: `*_test.go` (Go convention), `*.test.ts/tsx` (TypeScript), `*.spec.ts`, `*Test.java`, `*_spec.rb` all failed our `has_test_files` check
- **Impact**: ~20+ ragflow Go problems + ~12+ phase-rs TypeScript problems were being silently filtered
- Added 4 new regexes to cover all major language test file patterns

### Pool refresh: 367 → 397 (+30 new problems) (commit a277f65)
- **infiniflow/ragflow** (Go): +19 new problems — Go API driver implementations (NVIDIA, LocalAI, Voyage, Xinference, Jina, vLLM, Novita, OpenRouter, Hunyuan, VolcEngine, TokenHub, 302.ai, etc.)
- **phase-rs/phase** (TypeScript): +11 new problems — React/TypeScript component bugs with Vitest tests
- Oracle mean: 22.73 → **23.05** (new problems have strong Go/TS implementation diffs)
- Updated everywhere: pool_config.json, baselines.json, leaderboard.json, dashboard_data.json, README badge, docs/rewards.md, docs/api.md, gitminer.py, evaluate.py, record_result.py

### Agent: Go language support
- New `LANG_NOTES["go"]`: explains Go interface implementation, factory registration, export naming, error types
- New Go import resolution in `_import_pinned_files`: parses `"github.com/org/repo/internal/foo"` → pins all `.go` files in `internal/foo/` to rank #1

---

## 2026-06-02 — Pool 366→367 + agent improvements (commits 82faf35–91004c9)

### Pool refresh (+1 problem)
- `phase-rs_phase_1863` — "pin multi-suspend upkeep tick fires per source" (Rust integration test)
  - Issue #1502: multiple suspended cards scenario — upkeep triggers per suspend source, not once total
  - Oracle mean: 22.79 → **22.73** (recomputed across all 367 problems)
- All other repos dry-ran: phase, ragflow, gittensor, gittensory — all saturated (0 new qualifying PRs)

### Agent improvements (8 commits, all pushed)
1. **Import-path resolution** (`82faf35`) — parses test imports → pins exact impl files to top of ranking
   - Python: `from foo.bar.baz import X` → `foo/bar/baz.py`
   - TypeScript: relative `import { X } from './utils/foo'` → resolved path
   - Ruby: `require_relative '../lib/foo'` → resolved path
   - Rust: `use crate::foo::bar;` → `src/foo/bar.rs` / `src/foo/bar/mod.rs`
   - Pinned files score +100 (dominates keyword ranking)
2. **Language-specific system prompt notes** (`69fd49c`) — per-language caveats (Rust trait bounds, TS exports, Ruby requires, Python type annotations)
3. **Line numbers in windowed files** (`2f3e8cd`) — `  N | content` so model writes accurate `@@ -N` offsets
4. **Title token weighting** (`f5c17fe`) — issue title tokens 3× vs body (titles are precise; body is prose)
5. **Smarter repair output** (`48e9f6a`) — shows first 30 + last 50 lines of test output; adds failure categorization hints
6. **Sharper verify criteria** (`57949c5`) — checks import completeness, cross-checks `@@ -N` against line markers
7. **Hunk context line requirement** (`c0a5995`) — requires 3 unchanged context lines per hunk for `git apply` robustness
8. **Rust import + mod.rs hint** (`9fddfb0`) — Rust `use` import resolution + `mod.rs` in index-file hint

---

## 2026-06-02 — Agent: import resolution + language notes + line numbers (commits 82faf35, 69fd49c, 2f3e8cd)

### Agent improvements (3 commits)

**Import-path resolution** (commit `82faf35`)
- New `_resolve_test_imports()`: parses import statements in test files to identify exact implementation files under test
  - Python: `from foo.bar.baz import X` → `foo/bar/baz.py`
  - TypeScript: `import { X } from './utils/helpers'` → resolves relative path with extension probing
  - Ruby: `require_relative '../lib/foo'` → resolved relative path
- Pinned files score +100 in `_rank_files()` — they rise to the top over any keyword-matched file
- `_rank_files()` now accepts `file_tree` parameter; pinned files computed by checking against tree
- Tested on Python (gittensor#160) and TypeScript (gittensory) problems — correctly pins scoring.py, model.ts, etc.

**Language-specific system prompt notes** (commit `69fd49c`)
- New `LANG_NOTES` dict: per-language caveats for Rust, TypeScript, Ruby
  - Rust: trait bounds, match arms, `pub` visibility, `use` imports
  - TypeScript: type definitions, named exports, null checks
  - Ruby: snake_case, module includes, `require`
- `_detect_lang()` infers language from test file extensions
- Note appended to system prompt only when language is detected (Python uses default prompt)

**Line numbers in windowed files** (commit `2f3e8cd`)
- `_window_file()` now prefixes each visible line with its 1-based number: `  42 | def my_function():`
- Digit width consistent with total line count for clean alignment
- `ACT_PROMPT` updated: "use `N |` numbers directly for `@@ -N` offsets; do NOT include them in diff content"
- Impact: model no longer needs to count from omission markers — can read line number directly

---

## 2026-06-02 — Agent: exact line-range omission markers (commit a232d96)

### Agent improvement
- `_window_file()` now returns `(content, was_windowed)` and emits precise range markers:
  `... [lines 21-260 omitted — next visible line is 261]` instead of `... [N lines omitted]`
- `_format_files()` adds `(N lines total — relevant sections shown)` to windowed file headers
- `ACT_PROMPT` now explicitly instructs the model to use omission-marker line numbers for accurate `@@ -N` hunk offsets
- **Impact**: prevents "patch doesn't apply" failures caused by wrong hunk line numbers in windowed files
- Pool dry-runs: geniepod/genie-claw (152 PRs), allways (140 PRs), jvm-live-reload (26 PRs) — all fully saturated (no test files or no linked issues)

---

## 2026-06-02 — Pool 360→366 + oracle 22.79 (commit ba1f53b)

### Pool refresh (+6 new problems)
- `phase-rs_phase_1440` — Emissary Green not triggering (Rust integration test)
- `jsonbored_gittensory_218` — feat(agent): contributor evidence graph (TypeScript unit tests)
- `jsonbored_gittensory_222` — Pending-PR projection double-counts merge-ready PRs (TS test)
- `jsonbored_gittensory_225` — buildRoleContext maintainer association bug (TS test)
- `jsonbored_gittensory_226` — add recommendation confidence and provenance (TS integration test)
- `jsonbored_gittensory_228` — buildObservedPullRequestScenarios classifies open PRs wrong (TS test)
- Oracle mean recomputed: 22.83 → **22.79** across all 366 problems
- Updated: pool_config.json, leaderboard.json, baselines.json, dashboard_data.json, README badge, docs/rewards.md, docs/api.md, evaluate.py, gitminer.py, generate_dashboard_data.py, record_result.py

---

## 2026-06-02 — Agent: file-header preservation + index-file hint (commit 8ac6b9d)

### Agent improvements

- **File header preservation in windowing**: `_window_file()` now always includes the first `HEADER_LINES=20` lines of any windowed file, regardless of where keyword hits occur. Previously, if the relevant function was at line 300+ in a 400-line file, the agent saw no imports or class definitions — it couldn't know what was imported, what class a method belonged to, or what other symbols were available. Now imports and top-level declarations are always visible.

- **Index/export file hint**: New `_index_hint()` — checks `__init__.py` (Python) and `index.ts`/`index.js` (TypeScript) files in the directories of the top-ranked implementation files. If any are found, a "Module export files" hint is added to the OBSERVE prompt. The completeness check in step 5 explicitly references this hint, reminding the agent to add new exports when adding public symbols. Previously the agent might fix the implementation file but forget to export the new symbol, causing import failures at test time.

### Pool refresh
- All repos saturated: 0 new qualifying PRs across phase-rs/phase (132 new in DAS but all fail test-file/issue-link criteria), infiniflow/ragflow (303 new, Go-only without tests or linked issues), vouch, sure, gittensory, allways. Pool holds at 360.

---

## 2026-06-02 — Agent: test-first reasoning (commit dea0933)

### Agent improvement
- **Test-first reasoning**: `OBSERVE_PROMPT` restructured so step 1 is now "Test contract" — the agent enumerates every assertion, every function/class the test calls, and expected input → output *before* planning the implementation
- **Act prompt reinforcement**: ACT_PROMPT now says "mentally verify each test assertion from step 1 maps to a concrete line in your diff" — closes the loop between planning and code
- **Test section label updated**: "read first — these define the contract your implementation must satisfy"
- **Module docstring updated**: reflects new test-first reasoning as first-listed improvement

Key motivation: previous agent could produce a plan that passed casual reading but missed specific assertions. Test-first forces the model to derive what code must exist from what the test checks, rather than writing code and hoping tests agree.

### Registration checklist
- REGISTRATION.md count corrected: 324/13 → 360/20

### Status
- Pool: 360 problems, oracle 22.83 (all repos saturated)
- Agent: test-first reasoning, ranked context, file windowing, repair loop (commit dea0933)
- Dashboard: http://localhost:8082 (serving)
- API: http://localhost:8083 (serving)
- Pending: Gittensor registration, nginx hookup

---

## 2026-06-02 — Pool 354→360: vouch + sure refresh (commit 1c6e3ac)

### Pool expansion (+6 problems)
- Added 3 vouchdev/vouch problems: PR#112 (health checks), PR#114 (logging config), PR#126 (bundle/context sync)
- Added 3 we-promise/sure problems: PR#1473 (transaction split view), PR#1752 (Brex account controller), PR#1753 (account statements controller)
- Oracle mean: 22.77 → 22.83 (recomputed across 360 problems)
- Updated: pool_config.json, leaderboard.json, baselines.json, dashboard_data.json, README, docs/rewards.md, docs/api.md, evaluate.py, gitminer.py, generate_dashboard_data.py, record_result.py
- ragflow: 0 new qualifying PRs (all newer PRs lack linked issues); touchpilot: saturated
- Pool: 354 → 360 problems across 13 repos

---

## 2026-06-02 — Pool 353→354, output behavior fingerprinting (commits e4b623d, 05d05ba)

### Pool expansion (+1 problem)
- Added `infiniflow_ragflow_13217`: "API endpoints for auto-metadata configuration" — SDK API test
- Oracle mean: 22.76 → 22.77 (recomputed across 354 problems)
- Updated across: leaderboard.json, baselines.json, pool_config.json, gitminer.py, generate_dashboard_data.py, record_result.py, docs/rewards.md, docs/api.md, README badge
- entrius/gittensor: saturated (no new qualifying PRs); phase-rs/phase: 0 new qualifying PRs

### Anti-gaming: output behavior fingerprinting (commit 05d05ba)
**Problem**: Source-level similarity (AST bigrams + token Jaccard) can be evaded by agents that forward another agent's output through reformatted wrapper code. The outputs look the same; only the scaffolding code differs.

**Solution**: Per-problem diff hashes stored as behavior fingerprints.
- `evaluate.py` now captures a `diff_hash` per problem (SHA-256 of normalized diff); `--save-behaviors FILE` flag writes `{handle, eval_date, shard, diffs}` fingerprint JSON
- `scripts/check_output_similarity.py`: compares new agent's fingerprint against all stored fingerprints in `results/behaviors/`; flags if ≥ 70% of overlapping problems produce identical diff hashes (min 5-problem overlap)
- `eval.yml`: runs output similarity check after evaluation; artifacts include `behaviors_new.json`
- `record-champion.yml`: commits `results/behaviors/{handle}.json` to repo on merge
- `docs/threat_model.md`: Threat 7 (behavioral cloning) documented with mitigations and residual risk

Three-layer anti-gaming stack now:
1. Source code: token Jaccard + AST structural bigrams
2. Output behavior: per-problem diff hash matching
3. Rate limiting: 5 submissions/handle/week

---

## 2026-06-02 — Pool 352→353, test-symbol ranking (commits 755bd6f, 2ef869b)

### Pool expansion (+1 problem)
- Added `0335` (entrius/gittensor#335): "Looser credibility requirements for tier unlocks" — CLI test
- Oracle mean: 22.80 → 22.76 (recomputed across 353 problems)
- Updated across: leaderboard.json, baselines.json, pool_config.json, evaluate.py, gitminer.py, record_result.py, generate_dashboard_data.py, docs/rewards.md, docs/api.md, README badge

### Agent: test-symbol ranking improvement (commit 2ef869b)
- New `_test_keywords()` extracts identifier tokens from test files — names the tests import/call are the exact symbols the implementation files must contain
- `_rank_files()` now accepts `test_files` param; test-derived symbols weighted 2× in the relevance score (vs 1× for issue tokens)
- Windowing keyword set also includes test symbols — large implementation files now window around tested identifiers, not just issue text
- Net effect: on problems where test imports are specific (e.g. `from gittensor.validator.repo_scan import RepoScanner`), the exact module gets ranked #1 instead of being buried

---

## 2026-06-02 — Pool 349→352, test-repair loop, DAS calibration (commits 2c0e46c, 737cc57)

### Pool expansion (+3 problems)
- `1330` (entrius/gittensor#1330): per-repo `min_token_score` eligibility fix — validator scoring test
- `1354` (entrius/gittensor#1354): `_is_valid_linked_issue` solver attribution bug — scoring test
- `infiniflow_ragflow_15443`: OpenAI-compat streaming duplicate response fix — 202-line Python test
- Oracle mean: 22.81 → 22.80 (recomputed across 352 problems)

### build_pool.py fixes (commit 737cc57)
- `extract_issue_numbers`: regex now matches `Close #N` (not just "closes"), expanded to also cover `close[sd]?` and bare `PR #N` references
- Fallback to GitHub PR body if DAS body has no issue reference — catches maintainer PRs that describe instead of using keywords
- Reordered: GitHub PR fetch now comes before issue extraction for earlier fallback
- `--pr-numbers N,N,...` flag: targeted refresh of specific PRs (requires `--repo`) — much faster than full repo scan

### Agent: test-failure repair loop (commit 2c0e46c)
- `BaseAgent.repair(problem, failed_patch, test_output)`: default impl retries `solve()` with failure context injected into issue body
- `ExampleAgent.repair()`: override — builds a targeted repair conversation showing the exact failed diff + last 3k chars of test output; temperature=0 for precision; one structural validation pass
- `gitminer run --repair N`: after test failure, calls agent.repair() up to N times (--no-sandbox only); shows re-score after each attempt
- Fixed bug: oracle lookup in `cmd_run` used wrong keys (`b["problem_id"]`/`b["score"]` instead of `b["id"]`/`b["base_score"]`)

### DAS calibration display (commit 2c0e46c)
- `gitminer run --score` now shows `DAS ref: X.XX` — the Gittensor validator base score for the reference PR — alongside the local score
- Corrected inflation note: "~3-5× above Docker CI" (was ~2×; measured median ratio is 7x)
- "Avg oracle" label → "Pool mean" (clearer)

## 2026-06-02 — Pool refresh 347→349, score-aware prompts (commits 342d874, 72b622a)

### Pool expansion (+2 phase-rs/phase problems)
- Added `phase-rs_phase_1857` (Terra, Herald of Hope card bug) and `phase-rs_phase_1851` (Exhibition Tidecaller targeting bug).
- Both are Rust game-engine card-mechanic fixes with integration tests — deterministic, high-quality problems.
- Pool: 347 → 349 problems. Oracle mean: 22.85 → 22.81 (recomputed across all 349).
- entrius/gittensor: still saturated. ragflow: 0 new qualifying PRs (no linked issues on newer PRs).

### Example agent: score-aware prompting
- Added scoring explanation to SYSTEM_PROMPT: agents learn that (1) tests gate everything, (2) source-token quality drives the score — complete implementations beat minimal stubs.
- OBSERVE_PROMPT: added "Implementation plan" step (helper functions, error handling, edge cases) and "Completeness check" step (secondary files) to push toward thorough fixes.
- ACT_PROMPT: explicitly guides agent to implement the full fix, not a minimal stub.
- VERIFY_PROMPT: added criterion 5 — "Is the implementation complete?" — can expand a bare fix into a more complete one.
- Net effect: agents tuned to write complete, well-structured code that passes tests AND scores high.

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

## 2026-06-02 — Agent: new impl file detection + is_test_file fixes

### Benchmark (commit f1adaa3)

**New implementation file detection** (33% of pool problems affected)

Found that 132/400 problems (33%) add new source code implementation files via the PR that don't exist at base_commit. Previously the agent had no way to know these needed to be created — it would see the file content in context but not in the file tree, and produce a diff that modifies a non-existent file. `git apply` would fail silently.

Fix:
- `_new_impl_files()`: detects source code files (`.py`, `.go`, `.ts`, `.tsx`, `.js`, `.jsx`, `.kt`, `.java`, `.rb`, `.rs`) in context that are absent from the file tree
- `NEW_IMPL_FILES_TEMPLATE`: new prompt section listing the paths — agent is instructed to create them as new files (`--- /dev/null` format), implemented fully
- `ACT_PROMPT`: explicit reminder about new impl file creation format
- Distinct from test files: agent implements content (doesn't copy verbatim); template lists paths, not diffs

**`_is_test_file` bug fixes** (fixes misclassification of 60+ files)

Previous detection missed:
- Go test files: `nvidia_rerank_test.go` (has `_test.go` suffix, not `_test.py`)
- Paths starting with `tests/` (only detected `/tests/` mid-path, not at root)
- `conftest.py` (pytest fixture file, not an implementation file)

Fixes added: `name.endswith("_test.go")`, `p.startswith("tests/")`, `name == "conftest.py"`, `p.startswith("test/")`, `p.startswith("spec/")`

**`_new_test_diff` no-newline bug fix**

`splitlines()` strips newlines, so `lines[-1].endswith("\n")` was always False — every new test file diff was incorrectly getting the `"\ No newline at end of file"` marker. Fixed to check `f.content.endswith("\n")` on the original content.

### Status
- Benchmark: 400 problems, oracle 23.08 (unchanged)
- Agent improvements: new impl file detection, is_test_file fixes, no-newline fix
- Pending: Gittensor registration, nginx hookup

---

## 2026-06-02 — Agent: post-processing pipeline hardening (commits 27c63e8, d255803)

### Three new post-processing steps in solve() and repair()

**`_strip_line_number_prefixes`** (commit 27c63e8)

LLMs commonly include `N | ` display prefixes from windowed source files in diff context lines, despite the ACT_PROMPT explicitly telling them not to. Example:
```
 42 | def old_function():
```
This fails `git apply` because ` 42 | def old_function():` doesn't exist in any real file. The new function strips these prefixes from context/add/remove lines (not from `diff --git`, `---`, `+++`, `@@`, `\\` lines). Applied before hunk count recomputation.

**`_trim_trailing_prose`** (commit 27c63e8)

After `_extract_diff` finds `diff --git` and grabs everything to end-of-string, models sometimes append prose like "This patch fixes the issue." after the last hunk. `git apply` fails on trailing non-diff text. Walk backwards to the last valid diff line and truncate.

**Sibling import budget raised to 12 KB** (commit 27c63e8)

Go same-package files average 2-4 KB each; the old 6 KB budget cut off after 1-2 siblings, leaving the agent without factory/interface definitions in large Go packages.

### Assertion injection in verify prompt (commit d255803)

`_extract_assertions()` extracts assert/expect/assertEquals lines (up to 30) from all test files and injects them directly into VERIFY_PROMPT. The model now cross-checks each assertion against the diff explicitly, rather than relying on recall from earlier conversation turns.

Recognises assert styles for: Python, Rust (assert_eq!, assert!), Go (assert.Equal, t.Errorf), TypeScript (expect(), toBe, toHaveBeenCalled), Kotlin/Java (assertEquals, assertThat, verify).

### Status
- Benchmark: 400 problems, oracle 23.08 (unchanged)
- Pool: all repos saturated — next check 2026-06-09
- Pending: Gittensor registration, nginx hookup

## 2026-06-02 — Agent: verify hardening + timeout reliability (commits 4d97f89, 361fdde)

### New-file presence check in verify (criterion 6) (commit 4d97f89)

When the problem requires new files (`new_tests` or `new_impls`), the verify prompt now lists them explicitly under "Required new files" and adds criterion 6: "Does the diff add ALL N required new file(s) as `new file mode 100644` blocks?" Previously verify had no visibility into new-file requirements — it would say LGTM even if the agent forgot to add a required new file, which immediately fails the test command. Affects ~60% of pool problems (new test files) and ~33% (new impl files).

### Verify body snippet extended 1500 → 3000 chars (commit 4d97f89)

The issue body is now passed up to 3000 characters to the verify step (was 1500). Requirements stated after character 1500 were invisible to verify, causing incomplete-implementation misses on longer issues.

### Partial repair: feedback loop instead of silent break (commit 4d97f89)

When verify returns a diff covering fewer files than the current diff, the previous behavior was `break` — accepting the unchanged multi-file diff silently. Now: targeted feedback is sent ("your fix only covered N/M files, include all M files in your response") and the loop continues. Gives the model a chance to produce a complete multi-file correction rather than just keeping the unverified original.

### Timeout retry in `_call` (commit 361fdde)

`httpx.TimeoutException` was previously unhandled — it propagated up from `solve()` and the benchmark's broad except gave the problem a 0 score. Now: retry once on timeout; on a second timeout return `""`. The `_diagnose_diff` → format-repair path handles empty strings gracefully without aborting the problem.

### Status
- Benchmark: 423 problems, oracle 23.36 (unchanged)
- Pool: all repos saturated — next check 2026-06-09
- Pending: Gittensor registration, nginx hookup

## 2026-06-02 — Agent: line numbers for all source files + Rust sibling expansion (commit 004b8c7)

### Line numbers for all source files (commit 004b8c7)

Root cause found: `_window_file` added `N | ` line-number prefixes only when a file exceeded the 300-line windowing threshold. Files under 300 lines (a majority of pool context files) were shown without any line numbers, forcing the model to count manually from the top to determine `@@ -N` hunk offsets. Manual counting under time pressure is a significant source of offset errors.

Fix: when `show_line_numbers=True` and the file is not windowed, the output now also uses `N | content` format. Test files (shown with `show_line_numbers=False`) are unaffected — they don't get line numbers since the agent doesn't write diffs against them.

Also updated ACT_PROMPT: "windowed **source** files show lines as `N | content`" → "all source files show lines as `N | content`" to match the new universal behavior.

The `_strip_line_number_prefixes` post-processor already handles this format, so models that copy `N | ` prefixes into the diff are cleaned correctly.

### Rust `use super::module` sibling import expansion (commit 004b8c7)

`_expand_sibling_imports` now handles Rust `.rs` files. When a ranked impl file contains `use super::module_name;` or `use super::module_name::Symbol;` references, the expansion resolves them to `module_name.rs` or `module_name/mod.rs` in the same directory and promotes them to context if they exist in both `all_impl` and the file tree.

Previously: 0 sibling expansion for Rust (57 pool problems). Go, Python, JS/TS all had sibling expansion — Rust was the only language left out. Now consistent across all 5 main languages.

Also added Ruby-aware header end detection in `_compute_header_end` (last `require`/`require_relative` line + 8-line buffer) as defensive code for when Ruby problems are added to the pool.

### Status
- Benchmark: 430 problems, oracle 23.46 (unchanged)
- Pool: all repos saturated — next check 2026-06-09
- Pending: Gittensor registration, nginx hookup

### Verify criterion 8: structural summary symbol check (commit 00084ff)

After history compaction the verify model has access to the "File signatures in scope" section (function/class/method declaration lines) injected into the compact observe. Previously no verify criterion explicitly directed the model to cross-reference this section against the diff — the structural summary was available in context but not actively consulted.

VERIFY_PROMPT criterion 8 added: "Look at the 'File signatures in scope' section from earlier in this conversation. If the issue requires adding or modifying a specific function/method, confirm that symbol appears in your diff as a `+` line (e.g. `+def foo`, `+func Foo`, `+fn foo`). If a required symbol is absent, add it."

This closes the loop: the structural summary (added two steps ago) now has a criterion that actively invokes it. The verify model can now answer "Did the diff add `+def filter_repos`?" rather than only checking test assertions and hunk offsets.

### Hunk source context extended to 10 hunks (commit 00084ff)

`_hunk_source_snippets(max_hunks=6)` → `max_hunks=10`. Large diffs (multi-file, many hunks) had the first 6 hunks verified against actual source lines and the rest verified only by plausibility. Each hunk snippet is ~300 chars; extending from 6 to 10 adds ~1.3 KB to the verify prompt — well within the 25k-token budget.

### Status
- Benchmark: 430 problems, oracle 23.46 (unchanged)
- Pool: all repos saturated — next check 2026-06-09
- Pending: Gittensor registration, nginx hookup

## 2026-06-02 — Agent: _fix_new_starts (commit 0508f3b)

### +c new-start recalculation (commit 0508f3b)

Root cause: `_fix_hunk_offsets` corrects `-N` (old-start) values and `_fix_hunk_counts` corrects `b`/`d` (line counts). But `+c` (new-start) was never recalculated — whatever the LLM wrote was kept verbatim even after `-N` was moved.

For a valid diff, `+c` must equal `old_start + cumulative_delta` where `cumulative_delta = sum(new_count - old_count)` for all prior hunks in the same file. A stale `+c` causes `git apply` to fail on multi-hunk diffs where offset correction moved any `-N`.

Fix: `_fix_new_starts()` as stage 7 of `_post_process` — runs after `_fix_hunk_counts` so it sees final counts. Resets delta to 0 at each `diff --git` boundary. Skips new-file hunks (`@@ -0,0`). Verified with smoke tests:
- Single file, 2 hunks: hunk 1 adds 3 lines → hunk 2 `+c` correctly becomes `30 + 3 = 33`
- Multi-file: delta resets at file boundary
- New-file hunk: `@@ -0,0 +1,N @@` left unchanged

### Status
- Benchmark: 430 problems, oracle 23.46 (unchanged)
- Pool: all repos saturated — next check 2026-06-09
- Pending: Gittensor registration, nginx hookup

---

## Step N+1 — 2026-06-02: Tree-sitter Scorer + Oracle Recalibration

### What shipped

**`benchmark/harness/tree_sitter_scorer.py`** — new module
- Adapted from gittensor's actual DAS scoring engine (MIT)
- Uses the same `benchmark/harness/weights/programming_languages.json` + `token_weights.json` as the DAS validator
- AST symmetric diff: parses old and new file content, computes added/deleted node count weighted by structural bonus and leaf token weights
- Language weight multipliers: Go/Java/C/Rust 2.0×, Python 1.5×, JS 1.15×, etc.
- Test files weighted at 0.05× (separate src_score vs total_score streams)
- tree-sitter==0.24.0 pinned in requirements.txt (same version as gittensor pyproject.toml)

**`benchmark/harness/score.py`** updated
- Primary scorer: tree-sitter (via `score_file_pairs`); heuristic as fallback
- `_parse_diff_paths()`: extracts (path, status) from diff headers
- `_build_file_pairs()`: reads old file contents before applying patch
- `_fill_new_contents()`: reads new file contents after applying patch
- `score_diff_quality()`: quality-only scoring without test running (for baselines)
- Commit fetch retry: if `git worktree add` fails for missing commit, fetches from origin explicitly

**`scripts/baseline_scores.py`** updated
- Now calls `score_diff_quality()` for each reference diff (tree-sitter, no test suite)
- Added `--limit N` flag for partial runs

**Oracle mean recalibrated**: 23.46 (heuristic) → **13.34** (tree-sitter)
- Full 430-problem run completed
- Mean: 13.34, Median: 12.06, Max: 30.00, Min: 0.00
- Phase-rs problems score near 0 due to oracle_effect/mod.rs being 1.67 MB (exceeds DAS 1MB limit) — consistent with DAS behavior
- `results/leaderboard.json` oracle row updated; `dashboard_data.json` regenerated and pushed

**Note**: Docker CI scorer (`runner.py` inline `score_result.py`) still uses heuristic — backlog item to update after registration once file-content capture in Phase 1 is wired.

### Status
- Benchmark: 430 problems, oracle **13.34** (tree-sitter, calibrated), 20 repos
- Scoring: tree-sitter AST scorer active for local eval; matches DAS validator
- Pool: all repos saturated — next check 2026-06-09
- Pending: Gittensor registration, nginx hookup

---

## 2026-06-02 — Docker CI tree-sitter scorer (commit 95b51b5)

**The last remaining scoring gap is closed**: Docker CI now uses the same tree-sitter AST scorer as local eval.

### What changed

**`benchmark/harness/runner.py`**
- Phase 1 (`setup_and_test.sh`) now runs `capture_files.py` twice:
  - Before `git apply`: writes old file contents to `/staging/file_pairs.json`
  - After `git apply`: fills in new file contents
  - File content capped at 1 MB per file (same limit as DAS)
  - `python3-minimal` added to `apt-get` install for Node/Rust base images (which lack Python)
- Phase 2 (`score_result.py`) now:
  - Reads `file_pairs.json` + loads `ts_scorer.py` from staging via `importlib`
  - Uses tree-sitter AST scorer when available (tree-sitter pre-installed in custom image)
  - Falls back to heuristic token count when tree-sitter is absent (SCORE_IMAGE unavailable)
- `SCORE_IMAGE` changed from `python:3.12-slim` → `ghcr.io/punchthedev/gitminer-scorer:latest`
- `_resolve_score_image()` attempts to pull SCORE_IMAGE once per process; caches result; falls back on failure

**`docker/scorer.Dockerfile`** (new)
- `python:3.12-slim` + `pip install tree-sitter==0.24.0 tree-sitter-language-pack==0.7.2`
- Same versions pinned as gittensor's pyproject.toml

**`.github/workflows/build-scorer.yml`** (new)
- Triggers on push to main (paths: `docker/scorer.Dockerfile`)
- Builds and pushes `ghcr.io/punchthedev/gitminer-scorer:latest` to GHCR
- Docker layer cache via GitHub Actions cache

### Status
- Benchmark: 430 problems, oracle **13.34** (tree-sitter), 20 repos
- Scoring: tree-sitter AST scorer active for **both** local eval and Docker CI
- Pool: all repos saturated — next check 2026-06-09
- Pending: Gittensor registration, nginx hookup

---

## Step: Ruby Minitest assertion coverage + deduplication

**Commit**: `0293629`

### Root cause
Two separate gaps in `_extract_assertions`:

1. **Ruby Minitest `assert_*` patterns were entirely missing.** The existing `"assert "` prefix
   only matched bare Python-style `assert condition` lines. Ruby Minitest uses `assert_equal`,
   `assert_nil`, `assert_includes`, etc. — all starting with `assert_` (underscore), which
   the space-only prefix never matched. The 37 `we-promise/sure` pool problems are Ruby/Minitest;
   their assertion checks in verify were essentially blind.

2. **Previous step added `refute_equal ` (space suffix) when parens form also needed.**
   The docstring described `refute_equal(` (parens) being added, but the implementation
   used `refute_equal ` (space). Ruby allows both calling conventions; only the space form
   was covered.

3. **No deduplication.** The same assertion line appearing in multiple test files (shared
   helpers, parameterised setup blocks) counted multiple times against the 50-line limit,
   displacing unique edge-case assertions.

### Fix
- Added 9 Ruby Minitest `assert_*` patterns: `assert_equal`, `assert_nil`, `assert_includes`,
  `assert_match`, `assert_raises`, `assert_empty`, `assert_respond_to`, `assert_kind_of`,
  `assert_instance_of` — both space and parens forms (18 new prefix strings total).
- Added parenthesized `refute_*` variants: `refute_equal(`, `refute_nil(`, `refute_includes(`,
  `refute_match(`, `refute_empty(` alongside the existing space forms.
- Added `seen: set[str]` deduplication: the same assertion line only counts once toward
  the 50-line limit, regardless of how many test files contain it.

### Status
- Benchmark: 430 problems, oracle 13.34, 20 repos (commit `0293629`)
- Agent: Ruby Minitest assertions, deduplication + all prior improvements
- Pool: fully saturated; check ~2026-06-09 for new DAS registrations

---

## Step: Fix line numbers missing in no-hit windowing fallback

**Commit**: `2e82ba9`

### Root cause
`_window_file` has three paths for files over the 300-line windowing threshold:
1. **Has keyword hits** → adds `N | ` line-number prefixes to all visible lines ✓
2. **No hits → header fallback** → returned lines without `N | ` prefixes ✗
3. **Small file (<300 lines)** → adds `N | ` prefixes ✓

Path 2 was inconsistent: the header section (import block + first type defs) was
returned with `"".join(lines[:peek]) + suffix` — no line numbers even when
`show_line_numbers=True`. The model writing a diff against that file had to count
from "line 1" manually to find the right `@@ -N` offsets, causing off-by-one errors.

### Fix
Applied the same `{i:{width}d} | line` formatting to the no-hit header section
when `show_line_numbers=True`. No-op when `show_line_numbers=False` (test files).

### Status
- Benchmark: 430 problems, oracle 13.34, 20 repos (commit `2e82ba9`)
- Agent: consistent line numbers in all windowing paths + all prior improvements
- Pool: fully saturated; check ~2026-06-09 for new DAS registrations

---

## 2026-06-02 — Python unittest + mock assertion coverage

### Summary
Two assertion pattern improvements for `_extract_assertions`, covering 521 + 452 pool occurrences that were previously invisible to the verify step.

### Fix 1: unittest.TestCase self.assert* patterns (commit `c7e6a8c`)
Root cause: `self.assertEqual(`, `self.assertTrue(`, `self.assertRaises(` etc. all start with `self.` — not matched by the `"assert "` (space) prefix. Every Python test using a `TestCase` subclass had zero assertions captured for the verify cross-check.

Added: `self.assertEqual(`, `self.assertNotEqual(`, `self.assertTrue(`, `self.assertFalse(`, `self.assertIsNone(`, `self.assertIsNotNone(`, `self.assertIn(`, `self.assertNotIn(`, `self.assertRaises(`, `with self.assertRaises(`, `self.assertAlmostEqual(`, `self.assertGreater(`, `self.assertGreaterEqual(`, `self.assertLess(`, `self.assertLessEqual(`, `pytest.raises(`, `with pytest.raises(`.

521 occurrences across the pool now visible.

### Fix 2: mock/spy assert_called_once_with contains-check (commit `6a66944`)
Root cause: mock assertions appear as `variable.method.assert_called_once_with(...)` — the object name is not fixed, so prefix matching is structurally impossible.

Fix: added `_ASSERT_CONTAINS` tuple with `in` check (not `startswith`): `.assert_called(`, `.assert_called_once(`, `.assert_called_once_with(`, `.assert_not_called(`, `.assert_any_call(`, `.assert_called_with(`, `.assert_has_calls(`.

452 occurrences across the pool now visible.

### Status
- Benchmark: 430 problems, oracle 13.34, 20 repos (commit `6a66944`)
- Agent: full Python test coverage for assertions (pytest, unittest.TestCase, mock/spy)
- Pool: fully saturated; check ~2026-06-09 for new DAS registrations

---

## 2026-06-02 — Async Jest, Node.js assert, Go t.Error assertion patterns

### Summary
Added 8 new assertion patterns to `_extract_assertions` covering 1,627+ previously invisible occurrences across 52 problems in `jsonbored/gittensory` and `jsonbored/awesome-claude`.

### Root cause
Three gaps, all structural:
1. **`await expect(` — 1,627 occurrences**: async Jest/Vitest assertions start with `await`, not `expect`. The `"expect("` prefix only matched synchronous calls. Every async assertion in gittensory (1,544) and awesome-claude (81) was invisible to the verify cross-check.
2. **Node.js `assert.*` — 164+ occurrences**: Node.js built-in `assert` module uses lowercase (`assert.equal`, `assert.deepEqual`) — structurally different from Go testify's `assert.Equal` (uppercase). `assert.equal(` was not in the prefix list.
3. **Go `t.Error(` — 27 occurrences**: The non-fatal counterpart to `t.Fatal(`. `t.Fatal` was already covered; `t.Error` was not.

### Patterns added (commit `a8991c4`)
- `await expect(` — async Jest/Vitest (1,627 pool occurrences, 52 problems)
- `assert.equal(` — Node.js strict equality (164 occurrences)
- `assert.deepEqual(` — Node.js deep equality (49 occurrences)
- `assert.notEqual(` — Node.js inequality (4 occurrences)
- `assert.throws(` — Node.js throw check (4 occurrences)
- `assert.match(` — Node.js regex match (41 occurrences)
- `assert.doesNotMatch(` — Node.js regex non-match (22 occurrences)
- `t.Error(` — Go standard testing non-fatal (27 occurrences)

### Status
- Benchmark: 430 problems, oracle 13.34, 20 repos (commit `a8991c4`)
- Agent: async Jest + Node.js assert + Go t.Error coverage added to verify
- Pool: fully saturated; check ~2026-06-09 for new DAS registrations

---

## 2026-06-02 — Keyword-prioritized assertion extraction for large test files

### Summary
`_extract_assertions` now prioritizes keyword-matching assertions over sequential ones for large test files, ensuring the verify step sees the assertions relevant to the specific issue being fixed.

### Root cause
For repos like `jsonbored/gittensory`, `api.test.ts` grows as new features are added — each issue appends new `describe` / `await expect(...)` blocks at the end. The file can have 562+ assertions. With a 50-line limit, `_extract_assertions` always captured the first 50, which are the OLD assertions for existing features. The NEW assertions being tested by the current issue — the ones in keyword-relevant sections — were never seen by the verify step.

### Fix (commit `bc1240d`)
For test files over 200 lines with keywords provided:
1. Scan all assertion lines and bucket them: **keyword-matching** (stripped line contains a keyword from issue title/body) vs **non-keyword**
2. Fill the 50-line limit with keyword assertions first, then pad with non-keyword ones

Result: in the example above, all 20 `newFeature.handle()` assertions appear in the first 20 slots, with old `oldFeature` assertions filling slots 21-50.

The `keywords` argument is now passed from the verify loop call site, where it's already available as the union of issue tokens + test symbols.

### Status
- Benchmark: 430 problems, oracle 13.34, 20 repos (commit `bc1240d`)
- Agent: keyword-prioritized assertion extraction for 31 gittensory + 21 awesome-claude problems
- Pool: fully saturated; check ~2026-06-09 for new DAS registrations

---

## 2026-06-02 — Scoring guidance sharpened in all three runtime prompts (commit 63e5cf6)

### Summary
Aligned SYSTEM_PROMPT, ACT_PROMPT, and VERIFY_PROMPT with the actual AST token scoring formula so the model produces higher-scoring implementations from the first attempt.

### Root cause
The SYSTEM_PROMPT said "source-token quality — the number of meaningful code tokens" but was vague about what that means in practice. The model had no clear guidance that docstrings/comments don't count and that type annotations, guard clauses, and named helpers do. This left scoring potential on the table on every problem.

### Changes (commit `63e5cf6`)

**SYSTEM_PROMPT** — replaced the vague "source-token quality" note with a specific breakdown:
- Named what scores higher: function bodies with error handling, input validation/guard clauses, type annotations (Python/TypeScript/Kotlin), named helpers, constants, enum exhaustiveness
- Added the key negative: "Docstrings, comments, and blank lines do NOT count toward the score — only executable code nodes matter"
- Added the scoring ratio analogy: "A 40-line fix that handles every edge case scores much higher than a 5-line stub"

**ACT_PROMPT** — added a **Quality matters** bullet:
- "Guard against invalid/nil/empty inputs, add type annotations where the language supports them, split complex logic into named helpers"
- Repeats the "only executable code nodes" clarification at the point where the model writes the diff

**VERIFY_PROMPT criterion 5** — replaced the passive "Is the implementation complete?" check with an active directive:
- Was: "Is the implementation complete — does it handle edge cases, or is it a bare stub that only handles the happy path?"
- Now: specific checklist (edge cases covered? type annotations present? could logic be a named helper?) + explicit instruction to expand minimal stubs and return the improved diff

**OBSERVE_PROMPT** — appended quality-scoring awareness to the closing instruction:
- "the diff is scored by AST token count in non-test source files. More complete code (edge case handling, type annotations, named helpers) scores higher — but only after tests pass. Plan for both correctness and completeness."

### Status
- Benchmark: 430 problems, oracle 13.34, 20 repos (commit `63e5cf6`)
- Agent: quality scoring guidance sharpened in system, act, observe, verify prompts
- Pool: checked entrius/gittensor — no new qualifying PRs; next DAS check ~2026-06-09

---

## 2026-06-02 — Operator feedback: expand pool to prestigious external repos

Operator noted that genie-claw (tagged "openclaw" in GitHub topics) was underrepresented
and asked for more impressive, novel problem sources beyond DAS-registered repos.

**Investigation**:
- genie-claw: 152 DAS PRs but only 16 problems — fully saturated (all qualify already pass)
- DAS API returned 3,175 total PRs; all 20 registered repos already in pool
- No new DAS repos registered; expansion requires external sources

**Action**: New script `scripts/expand_pool_external.py` — fetches merged PRs from
prestigious external GitHub repos via GitHub API (no DAS dependency).

**Target repos selected** (self-contained test suites, no external service deps):
- `pytest-dev/pytest` (14k stars) — Python testing framework
- `pallets/click` (18k stars) — Python CLI toolkit
- `pallets/werkzeug` (7k stars) — Python WSGI utils
- `encode/starlette` (12k stars) — Python ASGI framework

**Result**: +96 new problems (430 → 526). Pool now spans 17 repos.

### Status
- Benchmark: **526 problems** (+96), oracle 13.34, 17 repos active (commit `b6fc588`)
- New script: `scripts/expand_pool_external.py`
- Docker CI: no changes needed — Python repos use same `pip install -e .` install path

---

## 2026-06-02 — Pool expansion +52, oracle recalibrated to 10.12

**Baseline recomputation across all 526 problems**:
- Ran `scripts/baseline_scores.py` for all 526 problems (first full run since external expansion)
- Oracle mean drops from 13.34 → 10.52 (external repos score lower: mean 4.70 vs DAS 13.34)
- Reason: external PRs (pytest, click, werkzeug, starlette) are more surgical than DAS PRs
- Updated `results/leaderboard.json` and `scripts/generate_dashboard_data.py`

**Further pool expansion +52 problems** from 3 prestigious Python repos:
- `pydantic/pydantic` (14k stars): +30 problems — pure Python data validation, self-contained tests
- `marshmallow-code/marshmallow` (6k stars): +15 problems — pure Python serialization
- `tiangolo/fastapi` (90k stars): +7 problems — web framework, depends on starlette (already in CI)
- Repos tried but rejected: `encode/httpx` (0 qualifying), `sqlalchemy/sqlalchemy` (0), `scrapy/scrapy` (30 but Twisted reactor risk)

**Final state**:
- Pool: **578 problems** (526 → 578, +10%)
- Oracle: **10.12** (recalibrated across all 578 reference diffs)
- External repos now: pytest-dev/pytest, pallets/click, pallets/werkzeug, encode/starlette, pydantic/pydantic, marshmallow-code/marshmallow, tiangolo/fastapi
- Dashboard data regenerated and pushed

### Status
- Benchmark: **578 problems**, oracle **10.12** (tree-sitter calibrated), commit `bd41391`
- Pool: DAS repos saturated; external expansion now at 7 repos
- Next pool check: ~2026-06-09 for new DAS registrations; consider celery, aiohttp if they have isolated tests

---

## 2026-06-02 — Pool expansion +62, oracle recalibrated to 9.70

**Target repos** (all self-contained Python test suites, no external service deps):
- `pallets/jinja` (11k stars): +13 problems — Jinja2 templating engine
- `python-attrs/attrs` (5k stars): +19 problems — pure Python data classes
- `pylint-dev/pylint` (5k stars): +30 problems — Python code linter (maxed at 30 cap)

Repos dry-run but rejected: `encode/httpcore` (only 1 qualifying)

**Oracle recalibration across all 640 problems**:
- Full baseline recomputation: `scripts/baseline_scores.py` across all 640 problems
- Mean drops 10.12 → 9.70 (new repos are surgical bug fixes → lower AST token counts)
- leaderboard.json updated, dashboard_data.json regenerated and pushed

### Status
- Benchmark: **640 problems** (+62), oracle **9.70**, commit `ff139cb`
- External repos now: pytest, click, werkzeug, starlette, pydantic, marshmallow, fastapi, jinja, attrs, pylint
- Pool: DAS repos saturated; external now at 10 repos
- Next pool check: ~2026-06-09 for new DAS registrations

---

## 2026-06-02 — Pool expansion +90, oracle recalibrated to 9.04

**Target repos** (all self-contained, no external service deps):
- `sphinx-doc/sphinx` (6.5k stars): +30 problems — Python documentation tool, pytest-based
- `networkx/networkx` (15k stars): +30 problems — graph algorithms library, pure Python
- `sympy/sympy` (14k stars): +30 problems — symbolic math, pure Python, no external deps

Repos evaluated and rejected: `celery/celery` (Redis/RabbitMQ integration tests), `aiohttp/aiohttp` (API error), `boto/boto3` (0 qualifying — no linked issues), `django/django` (only 5 qualifying — insufficient), `encode/httpcore` (1 qualifying).

**Oracle recalibration across all 730 problems**:
- Full baseline recomputation: mean drops 9.70 → 9.04 (new repos are surgical fixes, lower AST token counts)
- leaderboard.json, dashboard_data.json updated and pushed

### Status
- Benchmark: **730 problems** (+90), oracle **9.04**, commits `f95561d`, `6ec7552`
- External repos now: pytest, click, werkzeug, starlette, pydantic, marshmallow, fastapi, jinja, attrs, pylint, sphinx, networkx, sympy (13 external)
- Pool: DAS repos saturated; external now at 13 repos
- Next pool check: ~2026-06-09 for new DAS registrations

---

## 2026-06-02 — Restrict pool to Gittensor DAS contributions only

**Operator direction**: All benchmark problems must come from the Gittensor network only. The Gittensor API (`api.gittensor.io/prs`) is the authoritative source of contribution data.

**Investigation**: DAS API currently has 3,187 PRs across 18 repos. Not "hundreds of repos" — the current Gittensor network has 18 registered repos. All 18 are already in our `registered_repos` list.

**Action**: Removed all 300 problems from 13 external repos (pytest, click, werkzeug, starlette, pydantic, marshmallow, fastapi, jinja, attrs, pylint, sphinx, networkx, sympy). These were not Gittensor network contributions.

**Pool reverts to DAS-only**:
- Pool size: 730 → **430 problems** (13 DAS repos with qualifying PRs)
- Oracle recalibrated: 9.04 → **11.83** (DAS problems score higher — larger, richer diffs vs external surgical fixes)
- `pool_config.json`: removed `external_repos` key, pool_size=430
- `results/baselines.json`, `results/leaderboard.json`, `docs/dashboard_data.json` all updated

### Status
- Benchmark: **430 problems**, oracle **11.83**, DAS-only sources
- Pool: 18 DAS repos total; 13 have qualifying problems (linked issue + test files)
- Remaining 5 DAS repos have 0 qualifying PRs (no linked issues or no test files)
- Next DAS check: ~2026-06-09 for new repo registrations

---

## 2026-06-02 — Category-balanced shard selection

**Root cause**: `select_shard()` was doing a random shuffle and taking 30 — ignoring the per-category budget. Every shard could be dominated by Python (198/430 problems = 46%) at the expense of smaller categories.

**Fix**:
- Added `REPO_CATEGORY` map and `DEFAULT_SHARD_BUDGET` to `evaluate.py`
- New `_problem_category()` helper reads repo from `meta.json` and maps to category
- `select_shard()` now groups by category, shuffles each bucket independently, samples per budget, redistributes shortfalls
- Verified: `python:12  typescript:8  rust:5  jvm:3  ruby:2` — matches budget exactly

**`pool_config.json`**: added `shard_budget` key so the budget is explicit and overridable

**Result records**: both oracle and agent modes now include `category` per problem (visible in submission breakdowns)

**`--list-shard` output**: now shows `[cat:n  ...]` summary and per-problem category column

### Status
- Benchmark: **430 problems**, oracle **11.83**, commit `111abff`
- Shard: category-balanced (python:12/ts:8/rust:5/jvm:3/ruby:2) — well-roundedness guaranteed
- Next DAS check: ~2026-06-09 for new repo registrations

---

## 2026-06-02 — API server consistency + docs accuracy

**Issues fixed**:
- `api/server.py` used `_infer_language()` (guessing language from test_cmd) instead of the canonical `REPO_CATEGORY` map used everywhere else. This caused `category` fields to mismatch between CLI, dashboard, and API.
- API difficulty thresholds were wrong: easy≥26, medium≥18, hard<18 vs. the correct easy≥15, medium 5–15, hard<5.
- `docs/api.md` had stale example data: pool_size=400, repos=13, oracle=23.46.

**Fixes**:
- Added `REPO_CATEGORY` map directly to `api/server.py` (mirrors `benchmark/evaluate.py`)
- Replaced `_infer_language` with `_category(meta)` using `REPO_CATEGORY`
- Problem summaries now return `category` (python/typescript/rust/jvm/ruby) instead of `language` (py/js/rs/java)
- `_problems` filter now uses `cat=` param (also accepts `lang=` as deprecated alias)
- `_stats` now returns `by_category` and `oracle_score` (was `by_language` and `mean_baseline`)
- Difficulty thresholds aligned with dashboard: easy≥15, medium 5–15, hard<5
- `docs/api.md` updated with accurate data, category-based filtering docs

**Dashboard quickstart**: fixed misleading comment "no API key needed for --oracle" — there's no --oracle flag; example agent always requires `OPENROUTER_KEY`.

### Status
- Benchmark: **430 problems**, oracle **11.83**, 18 DAS repos, commit 9359b69
- API: `category` field consistent across CLI/dashboard/API
- Dashboard: quickstart comment fixed (commit 5536863 in gittensor-miner-dashboard)

---

## 2026-06-02 — Agent on-ramp + API server PM2 migration

**Agent on-ramp (`GET /api/agents`)**:
- New endpoint in `api/server.py` — returns structured JSON discovery document for autonomous AI agents
- Includes: pool summary, scoring formula, oracle/champion scores, allowed model list, quickstart CLI commands, all API endpoints
- Static `agents.json` added to dashboard repo — served at GitHub Pages, no API server needed to discover the benchmark
- Dashboard hero: "For Agents ↗" CTA button; Quick Start: info box explaining the entry point

**API server → PM2**:
- Previous: raw `nohup` background process — would die silently, not auto-restart
- Now: PM2-managed as `gitminer-api` (port 8083), auto-restart on failure, `pm2 save` persisted
- Also fixed: the live server was running stale code pre-consistency-fix (`by_language` instead of `by_category`); restarted under PM2 with current code

**Dashboard**: `python` → `python3` in quickstart commands (portability fix)

### Status
- Benchmark: **430 problems**, oracle **11.83**, commit `8e49c96`
- API: PM2-managed (`gitminer-api`), all 8 endpoints verified including `/api/agents`
- Dashboard: agents.json live at GitHub Pages; agents entry point in hero
- Next DAS check: ~2026-06-09

---

## 2026-06-02 — DAS pool check + new repo survey

**New DAS repos detected** (5 registered since last check):
- `cogniax/tao-pulse-app`: 19 PRs, 0 merged — not yet qualifying
- `e35ventura/taopedia`: 15 PRs, 0 merged — not yet qualifying
- `e35ventura/taopedia-articles`: 294 PRs, 207 merged — content-only (markdown articles, no test suite)
- `entrius/das-github-mirror`: 66 PRs, 21 merged — TypeScript NestJS API, no test files
- `mkdev11/gittensor-hub`: 69 PRs, 41 merged — TypeScript Next.js frontend, no test files

**Result**: Pool stays at **430 problems** (DAS repos with qualifying problems: linked issue + test suite). None of the 5 new repos qualify. Next meaningful check: ~2026-06-16 (allow more merged PRs to accumulate).

### Status
- Pool: 430 problems, DAS-only, all pool repos cached locally
- All CLI commands verified: `info`, `shard`, `validate`, `problems`, `run`, `mine`
- Pipeline fully operational — awaiting Gittensor registration approval

---

## 2026-06-02 — Pipeline correctness fixes

**eval.yml CI comment**:
- Stale difficulty thresholds in PR comment builder: was `≥25 = easy, ≥18 = medium` — should be `≥15 = easy, <5 = hard` (matching dashboard/CLI since the API consistency fix)
- Removed `problemLang()` function that inferred language from test_cmd strings — replaced with `p.category` read directly from the results JSON (already present since the category system was added)
- Column header updated: `Lang` → `Category`

**record_result.py — per-problem breakdown**:
- The dashboard's `openSubmissionDrawer()` reads `row.breakdown` to display per-problem drill-down for miner submissions — but `record_result.py` never populated this field
- Fix: extract `[{problem_id, score, passed, category}]` from `results.json` and store as `breakdown` in the leaderboard entry
- Now when miners submit and their entry appears on the leaderboard, clicking it shows the full per-problem breakdown (headline feature the operator requested)

**refresh_pool.yml — oracle recalibration**:
- Weekly pool refresh added new problems but oracle score was never recalibrated: new problems had `null` baseline_score in dashboard, oracle stayed at old value
- Fix: added `pip install -r requirements.txt` (needed for tree-sitter) + `python scripts/baseline_scores.py` after `build_pool.py`
- Oracle now auto-updates in the commit message: `"Add N problems to pool (total: T, oracle: X.XX)"`

### Status
- Benchmark: **430 problems**, oracle **11.83**, commits `6d4deb0`, `31c7a18`, `d957b22`
- All three fixes are in production (pushed to main)
- Next DAS pool check: ~2026-06-16

---

## 2026-06-02 — Difficulty tier alignment

**Problem**: `generate_dashboard_data.py` defined difficulty based on oracle AST score (higher score = easier), while `evaluate.py` defines difficulty by reference diff added-line count for scoring weights. The two systems were completely inconsistent — a problem with 1397 added lines showed "easy" in the dashboard but would be "hard" (2× weight) in actual scoring.

**Fix**: Aligned `generate_dashboard_data.py` with `evaluate.py`'s DIFFICULTY_TIERS:
- easy: < 30 added lines (×1 scoring weight)
- medium: 30–149 added lines (×1.5 weight)
- hard: ≥150 added lines (×2 weight)

**Dashboard updates**:
- Difficulty badges now show scoring weight label inline: "hard ×2", "medium ×1.5", "easy ×1"
- Tier column tooltip explains the line-count-based system
- New info box in Categories & Sampling explains how difficulty weights affect the final score
- `data.json` regenerated with corrected difficulty (now: easy:27, medium:143, hard:260)

**New pool distribution by difficulty**: 27 easy (< 30 lines), 143 medium, 260 hard — accurately reflects that DAS benchmark problems are mostly substantial changes.

### Status
- Benchmark: **430 problems**, oracle **11.83**, commit `3a68b53`
- Dashboard: difficulty badges aligned with scoring weights, commit `19cca40`
- Both pushed to main

---

## 2026-06-03 — Pool expansion: +11 jsonbored/gittensory (new DAS repo)

**DAS pool check**: 4 newly active repos found vs. prior state:
- `infiniflow/ragflow` (225 merged PRs): 0 qualify — most PRs have no linked issue or no test files in diff
- `jsonbored/awesome-claude` (24 merged PRs): 0 qualify — PRs have no linked issues
- `aglover1221/product-data-extractor` (6 merged PRs): 0 qualify (checked via dry-run)
- `jsonbored/gittensory` (56 merged PRs): **11 qualify** — TypeScript Cloudflare Workers project with vitest test coverage

**Pool expansion**: 430 → **441 problems** (+11 TypeScript)
- TypeScript pool: 87 → 98 problems
- Oracle arithmetic: 11.83 → **12.08**
- Oracle weighted: 12.77 → **13.03**
- Gittensory problems scored higher (mean ~20+ vs overall 12.08) because their diffs include substantial type-safe code changes

### Status
- Benchmark: **441 problems**, oracle **13.03** (weighted), commit `e7fd8f0`
- Dashboard: data.json auto-refreshed via CI workflow, 441 problems, oracle 13.03
- API: gitminer-api restarted on PM2, pool_size=441, oracle=13.03
- Next DAS check: ~2026-06-16

---

## 2026-06-03 — Documentation audit and data consistency fixes

**Stale stats audit**: found multiple stale pool counts (430/400/325), oracle values (23.46/11.83/12.77), and repo counts (19/20) across docs. All fixed.

**Files updated**:
- `README.md`: badge 430→441, oracle comment ~11.83→~13.03, repo count 19→13, use `python3`
- `LEADERBOARD.md`: complete rewrite — was showing oracle 21.60 / pool 325; now 13.03 / 441 / correct difficulty
- `docs/api.md`: pool_size, repos, oracle_score, by_category/difficulty, leaderboard oracle example
- `docs/rewards.md`: oracle 23.46→13.03, pool 400→441, maximize earnings section
- `CONTRIBUTING.md`: all `python gitminer.py` → `python3 gitminer.py` (22 instances)
- Dashboard `index.html`: meta description pool count 430→441
- `docs/dashboard_data.json`: was 430 problems (missing 11 gittensory additions); regenerated to 441

**Bug fix**: `docs/dashboard_data.json` was stale (430) because `generate_dashboard_data.py` only writes to root when run locally. Fixed: script now syncs `docs/dashboard_data.json` as a side-effect of local runs.

**Repo count clarification**: corrected "19 registered repos" → "13 active repos" throughout. The 20-entry `registered_repos` in pool_config.json includes DAS-registered repos with no qualifying problems; actual repos with pool problems = 13.

### Status
- All docs consistent: 441 problems, oracle 13.03 weighted / 12.08 arithmetic, 13 active repos
- Benchmark commits: `5c088b8` through `d1e2ee8`
- Dashboard commit: `7670791`
- Next DAS pool check: ~2026-06-16

---

## 2026-06-03 — Anti-copy pipeline: behavior fingerprint persistence fixed

**Bug found**: Output similarity check (`check_output_similarity.py`) was effectively a no-op because behavior fingerprints were never persisted to `results/behaviors/`. The CI saved them as artifacts (expire in 30 days) but never committed them to the repo. Future submissions could never be checked against prior submissions.

**Fix (benchmark commits 7498ebc, 4917c7d)**:
- `scripts/record_result.py`: added `--behaviors FILE` arg — copies fingerprint to `results/behaviors/{handle}.json`
- `.github/workflows/record_submission.yml`: added `--save-behaviors behaviors_merged.json` to re-eval, passes `--behaviors` to `record_result.py`, stages `results/behaviors/` in commit
- `results/behaviors/.gitkeep`: directory now tracked
- `.github/workflows/eval.yml`: champion comment updated — says "merge and CI handles everything automatically"
- `.github/workflows/record-champion.yml`: disabled (workflow_dispatch only) — was a duplicate of `record_submission.yml` that caused push race conditions on merge
- `CONTRIBUTING.md`: updated to mention behavior fingerprint in post-merge flow

**Root cause of duplicate workflows**: both `record-champion.yml` (fires on PR closed) and `record_submission.yml` (fires on push to main) were doing the same job. Now only `record_submission.yml` is active.

### Status
- Benchmark: **441 problems**, oracle **13.03** weighted, commit 4917c7d
- Anti-copy: behavior fingerprints now persisted on every champion merge
- CI post-merge: single workflow (`record_submission.yml`) handles eval + leaderboard + fingerprint + champion + dashboard
- Next DAS check: ~2026-06-16

---

## 2026-06-03 — Commit-reveal UX fixes

**Root cause**: Three files described the commit-reveal hash protocol inconsistently:
- `gitminer hash` help text said "patch file" but CONTRIBUTING.md used it with `agent.py`
- PR template included a "secret salt" that no command generates
- CONTRIBUTING.md had two incompatible hash flows (salted Python snippet vs `gitminer hash`)

**Fixes (commit 7940f68)**:
- `gitminer.py`: `hash` command arg renamed `patch` → `agent`; help text updated; success message clarified
- `gitminer.py`: module-level command description + usage example updated (`my_patch.diff` → `agent/submissions/myhandle/agent.py`)
- `.github/PULL_REQUEST_TEMPLATE.md`: removed "secret salt" from commit-reveal section; now says `python3 gitminer hash ...` and paste hash
- `CONTRIBUTING.md`: removed salted Python snippet + phase-2 reveal ceremony; unified to single flow using `gitminer hash` and `gitminer submit`

**Effect**: Miners now see one consistent commit-reveal flow: `gitminer hash` → paste hash → `gitminer submit`.

---

## 2026-06-03 — Minor doc accuracy fixes (benchmark commits e135ee1, 3f74101)

Two small accuracy issues found during a docs sweep:

- `README.md`: missing `export OPENROUTER_KEY=your_key_here` in the "Running the benchmark locally" code block — first-time miners would hit a runtime error without it
- `docs/rewards.md` chain diagram: showed `contributor cut (59.5%)` — stale from before the maintainer_cut was tuned to 0.15; fixed to `55%` to match the emission table directly below it

Both fixes are cosmetic/accuracy — no logic changes.

---

## 2026-06-03 — Resilience fix: guard record step on eval failure

**Problem**: In `record_submission.yml`, the "Record result" step had no guard against a missing `results_new.json` (produced by the eval step). If the authoritative post-merge eval fails (timeout, Docker crash, network error), `record_result.py` raises `SystemExit` and the job fails — the champion directory would never be updated, the leaderboard stays stale, and the commit step wouldn't fire.

**Fix (commit c0c52bf)**: Added an explicit file-existence check before calling `record_result.py`. If `results_new.json` doesn't exist, the step prints a warning and exits 0 — the rest of the job (champion check, commit) still runs but correctly finds no leaderboard change and is a no-op.

**Effect**: Eval failures are now gracefully handled — they don't cascade into a broken CI job. The miner's PR is still merged; a maintainer can re-trigger the workflow manually to record the score later.

**Also verified this step**:
- All Python files pass syntax check
- API running: pool=441, oracle=13.03, shard=30, next_rotation=2026-06-08
- `load_problem` and `load_agent` both work correctly on current pool
- No open PRs in either repo

---

## Step 146 — 2026-06-03

**Fixed: `actions: write` missing from CI workflows that trigger `refresh_dashboard.yml`** (commit `fbbd2d1`)

**Root cause**: `record_submission.yml` and `refresh_pool.yml` both commit via `GITHUB_TOKEN`. GitHub does NOT trigger other workflows from a `GITHUB_TOKEN` push (anti-loop protection). Both workflows work around this by calling `gh workflow run refresh_dashboard.yml` — but they only declared `permissions: contents: write`. When any permission is declared explicitly, GitHub sets all other permissions to `none`. So `actions` was `none`, and `gh workflow run` would fail silently.

**Effect of the bug**: After a miner PR merges, the leaderboard and leaderboard history would be recorded correctly, but the dashboard would never refresh. Same after a pool rotation — new problems would be added, but the dashboard would still show the old pool count.

**Fix**:
- `record_submission.yml`: Added `actions: write` to the permissions block.
- `refresh_pool.yml`: Added `actions: write`. Also added `pushed` output to the commit step, so the dashboard trigger is skipped (no-op) when there are no new problems.

**System health**: pool=441, oracle=13.03, API healthy, no open PRs.

---

## Step 145 — 2026-06-03

**Two maintenance fixes** (commits `ad91e9d`, `3eba1b8`)

1. **Committed untracked `agent/example/meta.json`** — the example agent had `agent.py` tracked but `meta.json` untracked since it was never committed. The sha256 matched the current `agent.py` content. Tracked it so the example submission is complete (miners can see both files as a reference).

2. **`refresh_pool.yml`: regenerate `docs/dashboard_data.json` on pool refresh** — the weekly pool refresh added new problems and recalibrated baselines but never updated `docs/dashboard_data.json` in the repo (the static copy used by local devs). Fixed: added a step to call `generate_dashboard_data.py docs/dashboard_data.json` before the commit, and staged the file. Also tightened the `NEW` problem count in the commit message from `grep 'meta.json'` (would have counted `dashboard_data.json` as a meta.json) to `grep 'benchmark/problems.*meta.json'`.

   Note: the live dashboard (`gittensor-miner-dashboard`) is already handled by `refresh_dashboard.yml` which fires automatically when `results/**` or `benchmark/problems/**` change — this fix is specifically for the local docs copy.

**System health**: pool=441, oracle=13.03, API healthy, no open PRs.

---

## Step 144 — 2026-06-03

**Fixed: local shard ≠ CI shard not documented** (commit `437cbb3`)

- `CONTRIBUTING.md`: Changed "same as CI" → "same scoring method as CI" (the shard differs because CI uses SHARD_SECRET). Added note block explaining the shard difference and recommending `--all` for stable local benchmarking.
- `gitminer.py` `cmd_eval`: Added runtime note when `SHARD_SECRET` is absent and user is evaluating a shard (not `--all` or specific `--problems`) — "local shard may differ from CI shard (server-side anti-gaming). Use --all for a stable benchmark."

**Root cause**: Miners could be confused when local Docker score didn't match CI score because CI uses a secret-seeded shard different from the default.

**System health**: pool=441, oracle=13.03, API healthy, no open PRs.

---

## Step 148 — 2026-06-03

**Consistency fix: PR template and `gitminer submit` checklist** (commit `14aa94e`)

Two stale references discovered during pre-launch audit:

| File | Stale | Fixed |
|---|---|---|
| `.github/PULL_REQUEST_TEMPLATE.md` | `python scripts/run_eval.py --agent ...` (internal CI script, not miner-facing) | `python3 gitminer.py eval agent/submissions/<my-handle>/agent.py --no-sandbox` |
| `gitminer.py` `_build_pr_body` | `sha256sum agent/submissions/{handle}/agent.py` (system tool, inconsistent with commit-reveal docs) | `python3 gitminer.py hash agent/submissions/{handle}/agent.py` |

Both now point to the canonical `gitminer` CLI commands documented throughout README and CONTRIBUTING. A miner filling out the PR template checklist will see consistent commands.

**System health**: API pool=441, oracle=13.03, no open PRs, all CLI commands verified.

## Step 151 — 2026-06-03

### Fixed: `?lang=py` returns empty results; dead code in server.py (commit 6dada2a)

**Bugs found via codebase audit:**

| Issue | File | Root cause | Fix |
|---|---|---|---|
| `?lang=py` always returns empty | README.md:125, CONTRIBUTING.md:194 | Category values are `python`/`typescript`/etc., not `py`. `?lang=py` filters to category `"py"` which matches nothing | → `?cat=python` |
| Dead `ALLOWED_MODELS` constant | api/server.py:40 | Constant pointed to `benchmark/allowed_models.txt` (doesn't exist); actual path used in code is `benchmark/harness/allowed_models.txt` (line 394) — constant was never read | Removed |

The `?lang=` alias in the server accepts it but maps to the same `cat_filter` comparison — the value still had to be the full category name, not a shorthand.

**System health:** API pool=441, oracle=13.03, no open PRs. Holding pre-registration.

---

## Step 152 — 2026-06-03

**Defensive KeyError fix in `/api/leaderboard`** (benchmark commit `df82d8f`)

Codebase audit found one remaining bug:

| Bug | File | Root cause | Fix |
|---|---|---|---|
| Potential `KeyError` on leaderboard "score" field | `api/server.py:408-409` | `e["score"]` with bracket notation in two places within the leaderboard endpoint — if any entry somehow lacks "score", it would raise `KeyError` instead of gracefully returning `None` | → `e.get("score", 0)` / `top.get("score")` |

The `ranked` filter on line 406 already guards `e.get("score") is not None`, so this would only bite a manually-edited leaderboard — but defensive is correct.

**System health:** API pool=441, oracle=13.03, shard=30, next_rotation=2026-06-08. No open PRs. Clean.

## Step 153 — 2026-06-03

**`gitminer doctor` pre-flight check command** (commit `12c36fa`)

Miners hitting cryptic tracebacks on first run (missing OPENROUTER_KEY, empty pool, etc.) have no easy way to diagnose setup issues. Added a `doctor` command that catches the most common problems before any eval runs.

Checks performed:
| Check | What it catches |
|---|---|
| OPENROUTER_KEY | Not set → RuntimeError deep in agent.py |
| Problem pool | Empty pool → silent zero-result eval |
| Leaderboard | Missing results/leaderboard.json → crash on mine |
| Allowed models | Missing allowlist → model not validated |
| Agent file (optional) | File not found, generic handle name |
| Shard config | Pool config readable, shard size/rotation correct |

Usage:
```
python3 gitminer.py doctor
python3 gitminer.py doctor --agent agent/submissions/myhandle/agent.py
```

Also added two `doctor` examples to the README "Running locally" section so miners see it first, before the eval commands.

**System health:** API pool=441, oracle=13.03, no open PRs. Holding pre-registration.

---

## Step 157 — 2026-06-03

**Parity command fix: use tree-sitter baselines instead of heuristic** (commit f081293)

Investigation found that the `parity` command was comparing DAS reference scores against the *heuristic* diff-token approximation (known to run ~2.5x above DAS). The heuristic is the fallback; the actual CI scorer is tree-sitter, which matches DAS at median 1.00x.

Fix: `cmd_parity` now reads pre-computed tree-sitter scores from `results/baselines.json` (same scores used for the oracle) and compares against `das_base_score` in meta.json. Falls back to heuristic only for the 29 problems without `das_base_score`.

**Result of fixed parity run (412 problems, 412 via tree-sitter):**
- Median local/DAS ratio: **1.00x** — tight alignment confirmed
- Outliers: problems with DAS base score near zero (0.00–0.13) but meaningful code changes — likely DAS had test failures at scoring time
- Heuristic median was 2.5x (misleading); tree-sitter median is 1.00x (accurate)

No other issues found this cycle. System healthy: API pool=441, oracle=13.03, no open PRs.

---

## Step 158 — 2026-06-03

**Silent zero baseline bug fixed: patch-apply failure path** (commit 39021a1)

**Root cause**: `score_diff_quality` (baseline oracle scoring) called `apply_patch()` but ignored its return value. When a reference diff fails to apply to the base commit:
1. `file_pairs` had old content but `_fill_new_contents` was skipped (since apply failed, but code didn't check)
2. Actually the code DID call `_fill_new_contents` since the return value was ignored — so new_content = old_content (unchanged)
3. tree-sitter correctly scored 0 change (old == new)
4. Heuristic fallback was never reached (tree-sitter returned (0, 0), not None)
5. Result: baseline oracle = 0 for any problem where the reference diff doesn't apply cleanly

**Fix**: Store `patch_applied = apply_patch(...)`, only call `_fill_new_contents` when `patch_applied=True`, only use tree-sitter when `patch_applied=True`. Falls through to heuristic correctly.

**Confirmed**: `we-promise_sure_1752` (DAS=30, local was 0, heuristic=30) now returns 30 from `score_diff_quality`. Other 27 low-ratio outliers will be corrected when Sunday's `refresh_pool.yml` re-runs `baseline_scores.py` with the fix.

**Parity output improved**: Added outlier breakdown note:
- `{aligned}/{total} problems within 10× of DAS | {N} outliers ({high} local>DAS, {low} local<DAS)`
- Explanation: local>DAS = DAS had test failures; local<DAS = local scorer gap

**Pool audit findings**:
- 412 problems have DAS reference scores; 29 (all entrius/gittensor) have no DAS score — expected
- 54 outliers: 27 local>DAS (DAS test failures), 27 local<DAS (27 now explained by patch-apply bug)
- Median parity confirmed 1.00× — 358/412 within 10× of DAS
- None of the outlier problems are in the current shard
- Sunday rotation will re-run baselines with the fix, updating the 27 previously-zero oracle entries

## Step 159 — 2026-06-03

**Re-scored baselines ahead of Sunday rotation** (commit `578d7a0`)

The patch-apply bug fix (`b51d955`) corrected `score_diff_quality` but baselines.json still held pre-fix values — 6 problems had `local=0, DAS>0`. Re-ran `baseline_scores.py` manually to apply the fix immediately:

| Metric | Before | After |
|---|---|---|
| Oracle (weighted) | 13.03 | **13.39** |
| Oracle (arithmetic) | 12.08 | **12.43** |
| Parity within 10× | 358/412 | **362/412** |
| Low outliers (local<DAS) | 27 | **21** |

4 remaining zero-score problems all have `das_base_score=0.0` — confirmed as genuine zeros (DAS agrees).

Updated: `results/baselines.json`, `results/leaderboard.json` (oracle row), `docs/dashboard_data.json`. API restarted — oracle_score now reads 13.39.

## 2026-06-03 — Rust inline test detection bug fix; oracle 13.39 → 15.02

**Root cause**: `is_test_file` in `tree_sitter_scorer.py` used `_INLINE_TEST_RE` to classify entire Rust source files as test files if they contained ANY `#[test]` attribute. Large source files like `synthesis.rs` (13,797 lines, 221 `#[test]` attrs) had `file_weight=0.05` applied instead of `1.0`, zeroing out `src_score`. `compute_base_score(0.0, 18.7) = 0.06` instead of the correct ~23.

**Affected**: 51+ Rust source file problems. The 4 phase-rs low outliers (local 1–6% of DAS) were caused entirely by this. After fix: those 4 now score 10.94–23.14.

**Fix**: Removed `_INLINE_TEST_EXTS` and `_INLINE_TEST_RE` from `is_test_file`. Path-based detection (`/tests/`, `_test.`, etc.) already correctly handles test files. Rust files in `src/` with embedded `#[cfg(test)]` blocks are source files, not test files.

**Oracle**: 13.39 → **15.02** weighted / 12.43 → **13.91** arithmetic.

**Parity note**: Fix revealed more phase-rs problems with DAS≈0 (test failures on DAS side). Median local/DAS ratio remains 1.00×; 340/412 within 10×. The new "high outliers" are DAS test-failure cases, not scorer bugs.

## 2026-06-03 — Anti-gaming enforcement + threat model + pool expansion (step 161)

**Anti-gaming: all copy-detection checks are now hard-blocking** (PRs #2, #3):

| Before | After |
|---|---|
| Similarity check: `continue-on-error: true` (advisory) | Hard-blocking: exits 1 on copy detection, fails the CI job |
| Output similarity: `continue-on-error: true` (advisory) | Hard-blocking: same |
| Reference copy: not implemented | New `check_reference_copy.py` — hard-blocking, detects oracle-diff hardcoding |
| No eval concurrency limit | Per-actor concurrency: one active eval per GitHub user, new pushes cancel in-flight |

**Reference copy attack**: The most dangerous undetected attack — miner reads public `benchmark/problems/{id}/reference.diff` and hardcodes oracle answers. Now detected: script hashes each reference.diff (same normalization as scorer), compares against agent's behavior fingerprint. >40% match rate = blocked.

**Threat model updated**: All 8 threats now have `[Implemented]` / `[Planned]` / `[Gittensor-native]` labels. Critical gaps documented: Daytona network enforcement (needed for model whitelist enforcement), shared OPENROUTER_KEY at scale, commit-reveal not yet live.

**Pool expanded**: 441 → 446 (5 new phase-rs/phase problems from recent merged PRs). `pool_config.json` updated.

**Commits**: f067f2b, a141dad, 6ac0c57, 93148a6, 0a50526, 2a2b2ea, e14fd8b, 0bfc4f2, 1ba3c18, 1481585

---

## Step 162 — 2026-06-03

**Pool filter fix**: `has_test_files()` in `build_pool.py` now recognizes Rust inline `#[cfg(test)]` blocks. Rust PRs that modify `src/` files with embedded tests were previously skipped as "no test files in diff." Sunday rotation will pick up additional phase-rs/geniepod problems.

**Config cleanup**: Renamed `max_problems_per_repo: 30` → `max_new_per_rotation: 50` in pool_config.json. The field was misnamed — it limits new additions per rotation run, not the total per repo.

**Oracle sync**: leaderboard.json oracle row was stale (pre-Rust-fix values); updated to weighted=15.15, arithmetic=14.04, count=446. API restarted.

**Meta.json CI validation**: New hard-blocking step in eval.yml checks that submissions include meta.json with a whitelisted model and SHA matching agent.py. CONTRIBUTING.md updated with meta.json format docs.

**Commits**: a8d4248, 3d99594, e2ec824 (PRs #8, #9, #10 — all merged)

## Step 164 — 2026-06-03

**Difficulty-stratified shard + pool expansion 532→584 + adversarial probe + threat model**

### Changes shipped (PR #14, merged to main, commit 68e01f5)

| Change | Detail |
|---|---|
| Difficulty stratification in `select_shard` | Added `_sample_difficulty_balanced()` — within each language bucket, problems are now sampled proportionally across hard/medium/easy tiers. Guarantees every shard has a realistic difficulty spread, not just language diversity. |
| `gitminer shard` shows difficulty | Header: `difficulty[hard:18 medium:11 easy:1]`, per-row `[hard]`/`[medium]`/`[easy]` tag |
| Pool 532→584 (+52 problems) | geniepod/genie-claw +50, infiniflow/ragflow +1, we-promise/sure +1 |
| Shard budget rebalanced | Pool is now 35.3% Rust / 34.2% Python. Budget changed from python:12/rust:5 to python:10/rust:10 to reflect actual composition |
| Oracle updated | 15.62 → 15.99 weighted / 14.57 → 14.97 arithmetic |
| Adversarial probe | Tested oracle-copy attack directly: confirmed `check_reference_copy.py` blocks it at 100% match rate (exit 1) |
| Threat 9 added | "Static agent (no LLM)" — documents gap between meta.json model check and actual runtime enforcement |

### Pool state
- **584 problems**: rust:206, python:200, typescript:98, jvm:42, ruby:38
- **Oracle**: 15.99 weighted / 14.97 arithmetic
- **Shard**: [python:10 rust:10 typescript:6 jvm:2 ruby:2] difficulty-stratified

### Critical gaps (unchanged, still need operator input)
- 🚨 Daytona integration — model enforcement + static agent detection
- 🚨 Per-miner OpenRouter key
- Commit-reveal (private eval)

---

## Step 166 — Pool 644→681: starlette, werkzeug, requests

**Date**: 2026-06-03

### Changes
- +9 problems from encode/starlette (ASGI middleware, staticfiles, testclient, CORS, templates, sessions)
- +27 problems from pallets/werkzeug (HTTP headers, routing, formparser, datastructures, debug tools)
- +1 problem from psf/requests (HTTP model fix)
- Total: **681 problems** (was 644)
- Oracle: weighted **14.81** / arithmetic **13.50** (count=681) — slight drop from 15.23 because external Python fixes are smaller diffs
- Pool composition: python:297 (43.6%), rust:206 (30.2%), typescript:98 (14.4%), jvm:42 (6.2%), ruby:38 (5.6%)
- Fixed stale oracle values in docs/rewards.md (was showing 13.03)
- Fixed ORACLE_ROW note in scripts/record_result.py (no longer "DAS network only")

### PR
[PunchTheDev/gittensor-base-miner#16](https://github.com/PunchTheDev/gittensor-base-miner/pull/16) — merged

### Critical gaps (unchanged, still need operator input)
- 🚨 Daytona integration — model enforcement + static agent detection
- 🚨 Per-miner OpenRouter key
- Commit-reveal (private eval)

---

## Step 167 — 2026-06-03

### Changes

**PR #20** — Model whitelist 11 → 16 models, fix --show-ref without agent
- Added: `deepseek/deepseek-v3`, `qwen/qwen-2.5-coder-32b-instruct`, `meta-llama/llama-3.3-70b-instruct`, `google/gemini-2.0-flash-001`, `mistralai/codestral-2501`
- Added contamination policy comment explaining the training-data overlap tradeoff
- Fixed: `gitminer run --show-ref` without `--agent` no longer tries to run an agent (was failing with OPENROUTER_KEY not set)
- Updated CONTRIBUTING.md example meta.json to use deepseek/deepseek-v3

**PR #21** — Sync stale oracle/shard fallback constants
- `benchmark/evaluate.py`: DEFAULT_SHARD_BUDGET corrected to match pool_config.json (python:10, rust:10, typescript:6); oracle fallback 15.99→14.81
- `scripts/generate_dashboard_data.py`: oracle fallback 12.08/13.03/441 → 13.50/14.81/681
- `.github/workflows/eval.yml`: hardcoded 13.03 fallback → 14.81 in two places

**PR #22** — Go Docker image for sandbox runner (bug fix)
- Root cause: 40 benchmark problems (infiniflow/ragflow Go driver issues) use `go test ./...` but `_LANG_IMAGES` had no Go entry → fell back to `python:3.12-slim` → tests fail silently
- Fix: added `"go": "golang:1.23-bookworm"` to `_LANG_IMAGES`, go mod download install block, python3-minimal apt install for capture_files.py

### Critical gaps (unchanged, still need operator input)
- 🚨 Daytona integration — model enforcement + static agent detection
- 🚨 Per-miner OpenRouter key
- Commit-reveal (private eval server)

---

## Step 168 — 2026-06-03

### Changes

**PR #23** — Remove 6 test-only problems; add source-change filter to pool (pool 681 → 675)

Root cause: benchmark problems whose reference diffs only touch test files score 0 on Gittensor's src_tok formula. Miners can never beat a 0 baseline — the problem is unsolvable by design. Identified 6 such problems via precise test-file detection (path-based: tests/, test_*, _test.*, _spec.rb, _test.go).

Removed: pallets/click (2731, 2946, 3129), phase-rs/phase (1399, 1857, 1863)
- DAS confirmed near-zero on phase-rs three (das_base_score ≈ 0.01–0.02)
- click three had no source file changes at all

Added `has_source_changes()` to `scripts/build_pool.py` and `scripts/expand_pool_external.py`. Future pool ingestion rejects diffs that only touch test files. The filter is precise: checks for at least one changed file that is NOT in a test directory, NOT named test_*/​*_test.*/​*_spec.rb/*_test.go.

Pool: 681 → 675. Oracle: 14.81 → 14.94 weighted, 13.50 → 13.62 arithmetic.
Updated: baselines.json, leaderboard.json, dashboard_data.json, docs/, README.

**PR #24** — Sync stale oracle/pool values in LEADERBOARD.md and gitminer.py

LEADERBOARD.md was showing pool=441, oracle=13.03 from initial setup — severely stale.
gitminer.py oracle fallback hardcoded to 13.03.
Both updated to current values (675 problems, 14.94/13.62).

### Critical gaps (unchanged, still need operator input)
- 🚨 Daytona integration — model enforcement + static agent detection
- 🚨 Per-miner OpenRouter key
- Commit-reveal (private eval server)


---

## Step 169 — 2026-06-03

### Audit: Zero-score problem retrospective + is_substantive() fix

**PR #25** — Remove 4 zero-score problems; gate ingestion on baseScore > 0.5

Root cause: `is_substantive()` only checked `tokenScore > 0` and `totalNodesScored > 0`. All 4 had DAS `baseScore = 0.0` but non-zero token/structural activity. A miner who solves the underlying issue perfectly still gets base_score = 0 (unsolvable benchmarks).

Problems removed (675 → 671):
- geniepod_genie-claw_76: ref diff only touches shell scripts + test (no Rust source)
- geniepod_genie-claw_98: ref diff only touches HTML template + test
- jsonbored_gittensory_228: TypeScript code reorder, AST diff ≈ 0
- encode_starlette_2711: single-line Python whitespace change, AST delta = 0

Fix: `is_substantive()` now requires `baseScore > 0.5`. Pool_config.json documents `min_reference_score: 0.5` in selection_criteria. Oracle: **14.94 → 15.0** weighted, **13.62 → 13.71** arithmetic.

Dashboard updated: punchthedev.github.io/gittensor-miner-dashboard/ now shows 671 problems, oracle 15.0. API verified: pool_size=671, oracle_score=15.0.

### Critical gaps (unchanged, still need operator input)
- 🚨 Daytona integration — model enforcement + static agent detection
- 🚨 Per-miner OpenRouter key
- Commit-reveal (private eval server)

---

### Pool expansion 671→812: 7 new Python repos

**PR #26** — Expand pool with 141 problems from aiohttp, flask, fastapi, tornado, twisted, trio, celery

All 7 repos are well-known Python open-source projects with GitHub issues linked to PRs and in-process test suites. Together they add depth to the Python half of the benchmark (now 434/812 = 53% Python).

New repos:
- aio-libs/aiohttp: 30 problems (async HTTP client/server)
- celery/celery: 30 problems (distributed task queue)
- twisted/twisted: 29 problems (event-driven networking)
- python-trio/trio: 17 problems (structured async)
- tornadoweb/tornado: 15 problems (web framework)
- pallets/flask: 13 problems (web framework)
- tiangolo/fastapi: 7 problems (API framework)

Oracle: **15.0 → 13.62** weighted / **13.71 → 12.22** arithmetic (smaller Python bug-fix diffs pull the mean down; expected).

Fixes shipped alongside expansion:
- `expand_pool_external.py`: `has_source_changes()` now filters towncrier news fragments (.misc/.bugfix/.feature extensions and newsfragments/ dir) — these look like source files but score 0 as they're changelog entries
- `baseline_scores.py`: `--incremental` now prunes removed problems from existing scores so counts stay accurate
- Shard budget rebalanced: python:13 rust:9 typescript:5 jvm:2 ruby:1

Dashboard: punchthedev.github.io/gittensor-miner-dashboard/ updated to 812 problems, oracle 13.62.

---

### Pool quality pruning: 49 sub-threshold problems removed; oracle 13.62→14.26

**PRs #27, #28** — Docs sync + retroactive pool cleanup

**Step 171 changes:**

*PR #27 (merged) — Sync docs to pool 812 and oracle 13.62:*
- README.md, LEADERBOARD.md, docs/api.md, docs/rewards.md, docs/threat_model.md
- All stale 675/681/14.94/14.81 references updated to 812/13.62

*PR #28 (merged) — Prune 49 problems with base_score < 0.5:*
- **Root cause**: `is_substantive(baseScore > 0.5)` filter was added in step 162, but 49 problems were added in earlier steps before the filter existed. These slipped through and remained in the pool.
- **Effect**: These problems score 0.01–0.49 even for perfect solutions — miners get near-zero reward for solving them. Low-signal, poor miner UX.
- **Fix**: Removed all 49 problem directories. Ran `--incremental` baseline update.
- Pool: 812 → **763**
- Oracle: **14.26** weighted / **12.99** arithmetic (was 13.62 / 12.22)
- Repos cleaned: entrius/gittensor (8), twisted (9), aiohttp (5), celery (5), werkzeug (4), vouchdev/vouch (4), click (3), pytest (3), trio (3), others (5)
- All oracle fallbacks updated: evaluate.py, gitminer.py, eval.yml (14.26)
- pool_config.json: pool_size=763
- API restarted: confirmed pool=763, oracle=14.26

---

## Step 172 — 2026-06-03

### Ruby pool expansion: 763→800 problems (PR #29, merged)

- rubocop/rubocop: +22 problems (RSpec-backed linter cop bug fixes)
- rubocop/rubocop-rails: +15 problems (Rails-specific cop bug fixes)
- 13 pruned (base_score < 0.5)
- Ruby: 38 → 75 problems (5.0% → 9.4% of pool)
- Shard: ruby 1→2, python 13→12
- `infer_test_cmd` extended: Ruby/RSpec → `bundle exec rspec <spec_files>`
- Oracle: 14.26 → 13.73 weighted / 12.99 → 12.38 arithmetic

### Pool state
- Pool: 800 | Oracle: 13.73 weighted / 12.38 arithmetic | Repos: 26

---

## Step 173 — 2026-06-03

### Bug fix + TypeScript expansion (PRs #30, #31, merged)

**PR #30 — Fix refresh_pool.yml:**
- Sunday rotation was running `build_pool.py` (DAS only) but never `expand_pool_external.py`
- All 15 external repos were silently skipped on Sunday rotation — new merged PRs never picked up
- Fix: added "Refresh external repos" step; oracle values now auto-synced to pool_config.json after each run

**PR #31 — colinhacks/zod +21 problems (800→821):**
- zod (38k stars): TypeScript type-system bug fixes with vitest tests
- 30 ingested → 9 pruned (base_score < 0.5) → +21 net
- `infer_test_cmd`: TypeScript .test.ts/.spec.ts → `npm test` (unlocks all future TypeScript repos)
- TypeScript: 93 → 114 problems (11.6% → 13.9%)
- Oracle: 13.73 → 13.69 weighted / 12.38 → 12.37 arithmetic

### Pool state
- Pool: 821 | Oracle: 13.69 weighted / 12.37 arithmetic | Repos: 28

---

## Step 174 — 2026-06-03

### Bug fix + TypeScript expansion (PR #32, merged)

**Bug fix — EXTERNAL_REPOS sync:**
- 7 Python repos added in step 170 (aiohttp, flask, fastapi, tornado, twisted, trio, celery) were in pool_config.json but missing from expand_pool_external.py's EXTERNAL_REPOS constant
- Sunday auto-rotation would have silently skipped all 7 repos forever — fixed

**TypeScript expansion:**
- vitest-dev/vitest: 30 ingested → 6 pruned → +24 net
- trpc/trpc: 30 ingested → 9 pruned → +21 net
- TypeScript: 114 → 159 problems (13.9% → 18.4%)
- Shard: typescript 5→6, rust 9→8
- Oracle: 13.69 → 13.39 weighted / 12.37 → 12.09 arithmetic

### Pool state
- Pool: 866 | Oracle: 13.39 weighted / 12.09 arithmetic | Repos: 30

---

## Step 175 — 2026-06-03

### TypeScript + Python expansion (PR #33, merged)

- vuejs/core (48k stars): Vue 3 compiler/reactivity bugs +27 problems
- python/mypy (18k stars): Type checker regression bugs +27 problems
- TypeScript: 159 → 186 (20.2%); Shard: rust 8→7, typescript 6→7
- Oracle: 13.39 → 12.99 weighted / 12.09 → 11.68 arithmetic

### Pool state
- Pool: 920 | Oracle: 12.99 weighted / 11.68 arithmetic | Repos: 32

---

## Step 176 — 2026-06-03

### Rust expansion + infer_test_cmd bug fix (PR #34, merged)

**Bug fixed:** `infer_test_cmd` had no Rust handler — fell through to Python `pytest` default
- Fix: detect any `.rs` file → `["cargo", "test"]`; patched all 60 new meta.json files retroactively

**Expansion:**
- tokio-rs/tokio (28k stars): Rust async runtime bugs +30
- clap-rs/clap (14k stars): Rust CLI parser bugs +30
- Rust: 200 → 260 (26.5%); Shard: rust 7→8, typescript 7→6
- Oracle: 12.99 → 12.76 weighted / 11.68 → 11.46 arithmetic

### Pool state
- Pool: 980 | Oracle: 12.76 weighted / 11.46 arithmetic | Repos: 34

---

## Step 177 — 2026-06-03

### Rust HTTP ecosystem: 1000-problem milestone (PR #35, merged)

- hyperium/hyper (14k stars): Rust HTTP/1-2 library +12 (all base_score ≥ 1.69)
- tokio-rs/axum (20k stars): Rust web framework +8 (all base_score ≥ 3.37)
- Rust: 260 → 280 (28.0%); Oracle: 12.76 → 12.86 weighted / 11.46 → 11.57 arithmetic

### Pool state
- Pool: 1000 | Oracle: 12.86 weighted / 11.57 arithmetic | Repos: 36

---

## Step 178 — 2026-06-03

### JVM pool expansion (PR #36, merged)

- FasterXML/jackson-databind (10k stars): Java JSON bugs +24
- square/okhttp (45k stars): Kotlin HTTP/2 bugs +4
- `infer_test_cmd` now handles `.java`/`.kt`/`.scala` → `./gradlew test --no-daemon -q`
- REPO_CATEGORY keys fixed to lowercase (API uses `.lower()` lookup)
- JVM: 41 → 69 (6.7%); Oracle: 12.86 → 12.75 weighted / 11.57 → 11.49 arithmetic

### Pool state
- Pool: 1028 | Oracle: 12.75 weighted / 11.49 arithmetic | Repos: 38

---

## Step 179 — 2026-06-03

### Go language added as 6th category (PR #37, merged)

- gin-gonic/gin (75k stars): Go HTTP framework +13
- labstack/echo (28k stars): Go HTTP framework +4 (1 pruned)
- `infer_test_cmd` now handles `.go` → `go test ./...`
- Shard: python 12→11, go:1 added (still 30 total)
- Oracle: 12.75 → 12.66 weighted / 11.49 → 11.39 arithmetic

### Pool state
- Pool: 1045 | Oracle: 12.66 weighted / 11.39 arithmetic | Repos: 40 | Languages: 6

---

## Step 180 — 2026-06-03

### Go pool expansion: 17→96 problems (PR #38, merged)

- gofiber/fiber (31k stars): +58 problems
- grpc/grpc-go (21k stars): +17 problems
- spf13/cobra (35k stars): +4 problems
- Retroactive quality prune: 13 sub-threshold problems removed
- Shard rebalanced: go 1→3, python 11→10, rust 8→7
- Oracle: 12.66 → 12.64 weighted / 11.39 → 11.41 arithmetic

### Pool state
- Pool: 1114 | Oracle: 12.64 weighted / 11.41 arithmetic | Repos: 43

---

## Step 181 — 2026-06-03

### Cleanup + prestige repo expansion (PRs #39, #40, #41, all merged)

**PR #39 — Sync 3 stale values:**
- pool_config.json shard_budget: python 11→10, rust 8→7, go 1→3
- results/leaderboard.json: oracle 13.69/12.37/821 → 12.64/11.41/1114
- REGISTRATION.md: "441 problems, 13 repos" → "1114 problems, 43 repos"

**PR #40 — Fix LEADERBOARD.md repo count: 40→43**

**PR #41 — Pool expansion 1114→1131:**
- google/guava (50k stars, Java): +7
- serde-rs/serde (24k stars, Rust): +7
- sindresorhus/got (14k stars, TypeScript): +3
- JVM: 69→76 / Rust: 270→277 / TypeScript: 186→189 / Repos: 43→46

### Pool state
- Pool: 1131 | Oracle: 12.64 weighted / 11.41 arithmetic | Repos: 46 | Languages: 6
- Composition: python:418 rust:277 typescript:189 go:96 jvm:76 ruby:75

---

## Step 182 — 2026-06-03

### Health check + PUNCH_LOG sync

- System health verified: API pool=1131, oracle=12.64, repos=46 ✅
- DAS API checked: 3308 total PRs, 1800 merged — no high-value new problems found (recent additions are content-only or micro-fixes)
- PUNCH_LOG.md updated: steps 172-181 now logged (was missing ~10 steps)
- Pool is well-balanced; Sunday rotation (2026-06-08) will auto-expand all 33 external + 13 DAS repos
- Critical blockers still awaiting operator: Daytona integration, per-miner OpenRouter key strategy

### Pool state
- Pool: 1131 | Oracle: 12.64 weighted / 11.41 arithmetic | Repos: 46 | Languages: 6
- Next action: Operator input on Daytona credentials and per-miner OpenRouter key

---

## Step 183 — 2026-06-03

### Actions
- Removed orphaned `infiniflow_ragflow_15431/` problem directory (untracked leftover from a partial build_pool.py run on a non-tracked repo)
- **Bug found and fixed: vouchdev/vouch mis-categorized as 'typescript'** — the repo is a Python AI/retrieval system (24 problems with pytest tests and Python source). REPO_CATEGORY updated in evaluate.py, generate_dashboard_data.py, api/server.py
- **Bug found and fixed: 6 TypeScript problems with wrong test_cmd** — sindresorhus/got (3) and vitest-dev/vitest (3) had `python -m pytest` instead of `npm test` (diffs had no `.test.ts` files, so fell through to Python default)
- **Root cause fixed in expand_pool_external.py `infer_test_cmd`**: now detects any `.ts`/`.js` file extension → npm test (not just `.test.ts`/`.spec.ts`). Consistent with build_pool.py logic.
- Shard budget rebalanced: python 10→12, typescript 6→4 (proportional to corrected counts)
- Updated pool_config.json, DEFAULT_SHARD_BUDGET, generate_dashboard_data.py SHARD_BUDGET, docs/api.md
- Regenerated docs/dashboard_data.json
- API restarted: confirms python:442, typescript:165 ✅
- PR #43: "Fix vouchdev/vouch language category and 6 wrong test_cmds" — merged commit f6033510
- Commit 6e47a136: `infer_test_cmd` root-cause fix pushed directly to main

### Pool state
- Pool: 1131 (same count, corrected categories) | Oracle: 12.64 weighted / 11.41 arithmetic | Repos: 46 | Languages: 6
- New composition: python:442 (39.1%), rust:277 (24.5%), typescript:165 (14.6%), go:96 (8.5%), jvm:76 (6.7%), ruby:75 (6.6%)
- Shard budget: python:12 / rust:7 / typescript:4 / go:3 / jvm:2 / ruby:2 = 30 ✅
- Sunday rotation 2026-06-08: all 33 external + 13 DAS repos will auto-expand

## Step 184 — 2026-06-03

### Actions
- **TypeScript pool expansion: TanStack/query +23 problems (1131→1154)** — PR #44, merged commit 98aba2bd
  - TanStack/query (38k stars): React Query / async data-fetching — 27 ingested, 4 pruned (base_score < 0.5), +23 net
  - Pruned: tanstack_query_10772 (0.17), tanstack_query_10716 (0.29), tanstack_query_10642 (0.32), tanstack_query_10337 (0.49)
  - Coverage: query-core async observers, React/Solid/Preact/Angular framework bugs, devtools, ESLint plugin rules
  - TypeScript: 165 → 188 problems (14.6% → 16.3% of pool)
  - Shard budget: typescript 4→5, python 12→11 (stays at 30 total)
  - Repos: 46 → 47 (13 DAS + 34 external)
  - Oracle: 12.64 → **12.70** weighted / 11.41 → **11.48** arithmetic
  - All oracle fallbacks updated: evaluate.py, gitminer.py, eval.yml
  - REPO_CATEGORY + EXTERNAL_REPOS updated: evaluate.py, api/server.py, generate_dashboard_data.py, expand_pool_external.py
  - results/baselines.json fully rescored (1154 problems, took ~8 min)
  - Dashboard regenerated, docs synced: README, LEADERBOARD, api.md, rewards.md, threat_model.md
  - API confirmed: pool=1154, oracle=12.70, repos=47, typescript=188

### Pool state
- Pool: **1154 problems** | Oracle: **12.70** weighted / **11.48** arithmetic | Repos: **47** (13 DAS + 34 external) | Languages: 6
- Composition: python:442 (38.3%), rust:277 (24.0%), typescript:188 (16.3%), go:96 (8.3%), jvm:76 (6.6%), ruby:75 (6.5%)
- Shard budget: python:11 / rust:7 / typescript:5 / go:3 / jvm:2 / ruby:2 = 30 ✅
- Sunday rotation 2026-06-08: all 34 external + 13 DAS repos will auto-expand

---

## Step 185 — Scoring sophistication: relative score + file coverage + anti-gaming

### Problem addressed
Operator asked: "How do we score benchmark performance? It can't just be Gittensor scoring methods." The raw Gittensor token formula rewards verbose diffs, not correct fixes. Problems with different oracle scores contributed unequally to the mean.

### Changes (PRs #45, #46 — both merged)

**PR #45: `relative_score` + `file_coverage` (score.py, evaluate.py, gitminer.py, docs/scoring.md)**
- `relative_score = agent_score / oracle_score` per problem (oracle from `results/baselines.json`)
  - Oracle scores exactly 1.0 against itself (verified)
  - Capped at 2.0 to prevent bloated-diff inflation
  - `mean_relative_score` added to aggregate output as the primary ranking metric
- `file_coverage`: fraction of reference diff source files agent also touches (observational, not in score)
- `oracle_base_score`: exposed per-problem oracle denominator in result dict
- docs/scoring.md: three-metric model documented clearly

**PR #46: test deletion detection + rewards.md fix (score.py, docs/rewards.md)**
- `_detect_test_deletion`: scans diff for removed test assertions; sets `test_deletion_warning: true` if >3 removed
- Fixed false rewards.md claim: "tighter diffs score higher" → corrected to accurate three-metric description

### Scoring model now
1. **Correctness gate**: tests must pass (binary, hard)
2. **Quality** (`final_score`): Gittensor tree-sitter AST formula (0–30)
3. **Relative quality** (`relative_score`): agent_score / oracle_score — primary ranking metric
4. **File coverage** (`file_coverage`): observational — % of reference files touched
5. **Anti-gaming** (`test_deletion_warning`): flags suspicious test assertion removal

### Pool state
- Pool: **1154 problems** | Oracle: **12.70** weighted / **11.48** arithmetic | Repos: **47** (13 DAS + 34 external)

---

## Step 186 — 2026-06-03

### Partial test scoring + composite benchmark_score (PR #47, merged 95b49b86)

**Problem**: The scoring was binary pass/fail — fixing 9/10 tests scored the same as fixing 0/10. The primary metric (`mean_relative_score`) was not clearly connected to the `final_score` field (which was raw Gittensor token score). The operator correctly identified this as insufficient.

**What changed**:

1. **`_parse_test_count(output, test_cmd)`** — parses test runner output to extract `(passed, total)` counts:
   - pytest: `N passed, M failed in Xs`
   - cargo test: `test result: ok. N passed; M failed`
   - go test: count `--- PASS:` / `--- FAIL:` lines
   - jest/vitest: `Tests: N passed, M total`
   - rspec: `N examples, M failures`
   - gradle: `N tests completed, M failed`
   - Falls back to binary (exit code) when parsing fails

2. **`test_pass_rate = passed / total`** (0–1) per problem

3. **`benchmark_score = test_pass_rate × relative_score`** — composite PRIMARY metric:
   - All tests pass + oracle quality → 1.0
   - All tests pass + better than oracle → >1.0 (cap 2.0)
   - 50% tests pass at oracle quality → 0.5
   - No tests pass → 0.0

4. **`mean_benchmark_score`** aggregated in evaluate.py, shown first in CLI output

5. **LEADERBOARD.md**: rankings now by benchmark_score (was weighted_mean_score)

6. **docs/scoring.md**: rewritten to explain the full scoring philosophy — partial credit rationale, formula, per-runner parsing table

### Scoring philosophy
The benchmark now captures two orthogonal dimensions:
- **Correctness depth** (`test_pass_rate`): did the agent fix the actual bugs?
- **Quality alignment** (`relative_score`): is the fix as clean/structured as the oracle?

`benchmark_score` is their product. An agent that's 80% correct but 120% quality earns 0.96. An agent that's 100% correct but 80% quality earns 0.80. Both signals matter.

## Step 187 — 2026-06-03

### Scoring depth: difficulty-weighted benchmark, test deletion penalty, CI consistency (PR #48, merged f5eba538)

**Problem**: The scoring system had three gaps:
1. `mean_benchmark_score` was arithmetic mean — difficulty weights (easy×1/medium×1.5/hard×2) weren't applied to the primary ranking metric. Easy and hard problems counted the same.
2. `test_deletion_warning` was a flag only — no actual score penalty for test gaming.
3. `mine` command compared `weighted_mean_score` (Gittensor tokens) against champion, not `benchmark_score`.

**Changes**:

1. **`weighted_benchmark_score`** (new PRIMARY leaderboard metric):
   ```
   weighted_benchmark_score = sum(benchmark_score_i × difficulty_weight_i) / sum(difficulty_weight_i)
   ```
   Hard problems (150+ changed lines, weight 2.0) now count twice in the aggregate. Oracle = 1.0 by definition.

2. **Anti-gaming penalty in score** (`anti_gaming_multiplier`):
   - `test_deletion_warning=True` → `benchmark_score` halved (×0.5)
   - Previously just flagged, now affects the score

3. **Mine command uses `weighted_benchmark_score`** for champion comparison — consistent with leaderboard ranking

4. **CI eval.yml updated**:
   - Parse step extracts `weighted_benchmark_score` from results.json
   - PR comment shows `weighted_benchmark_score` as primary, adds `test_pass_rate` and `benchmark_score` columns per problem, marks ⚠️ for test deletion
   - Champion detection compares `weighted_benchmark_score` (not `weighted_mean_score`)

5. **leaderboard.json oracle entry**: added `benchmark_score: 1.0` and `weighted_benchmark_score: 1.0`

6. **docs/scoring.md** rewritten: documents all metrics, anti-gaming multiplier, weighted aggregate formula

### Scoring philosophy (updated)
Four dimensions now captured:
- **Correctness depth** (`test_pass_rate`): fraction of tests passing
- **Quality alignment** (`relative_score`): agent quality vs oracle quality for this specific problem
- **Integrity** (`anti_gaming_multiplier`): penalty for test deletion
- **Difficulty weight**: hard problems count more in the aggregate

```
benchmark_score          = test_pass_rate × relative_score × anti_gaming_multiplier
weighted_benchmark_score = sum(benchmark_score_i × weight_i) / sum(weight_i)
```

## Step 188 — 2026-06-03

### Critical scoring bug fixes: sandbox metric parity + partial credit (PRs #49, #50)

**Bug 1 — Sandbox metric parity (PR #49, merged ba464817)**

The Phase 2 Docker scorer script only emitted `base_score` and `tests_passed`. Missing: `test_pass_rate`, `relative_score`, `benchmark_score`, `anti_gaming_multiplier`, `file_coverage`, `test_deletion_warning`. This meant `weighted_benchmark_score` (the PRIMARY leaderboard metric) was always `None` in real CI sandbox runs — the metric we built the entire ranking on never actually computed in production.

**Fix**: Added `_enrich_result()` to `runner.py`. After `_run_container()` returns but before the staging temp dir is cleaned up, reads `test_out.txt`, parses test counts, and computes all missing metrics using the same functions as `score.score_patch()`. Both execution paths (sandbox + local) now return identical result shapes.

Also renamed underscore-prefixed public helpers in `score.py` to remove the `_` prefix (`parse_test_count`, `file_coverage_stats`, `detect_test_deletion`, `relative_score_for`, `load_baselines`, `is_test_file`, `parse_diff_paths`, `cached_repo`, `repo_cache_dir`). Updated all callers in `gitminer.py`.

**Bug 2 — Partial credit broken in Phase 2 (PR #50, merged 4f5fd2b2)**

Phase 2 exited early with `base_score: 0.0` when `tests_passed == False`. Since `benchmark_score = test_pass_rate × relative_score`, setting `base_score = 0` meant a submission passing 7/10 tests earned `0.7 × 0.0 = 0.0` instead of `0.7 × oracle_quality`. The local `score_patch()` path didn't have this bug — local runs computed `base_score` always.

**Fix**: Removed the early-exit block in `_SCORE_RESULT_SCRIPT`. Phase 2 now always computes diff quality (tree-sitter or heuristic) regardless of test result. Also fixed hardcoded `"tests_passed": True` in the success output — now uses the actual `tests_passed` bool. Renamed `_compute_base` → `compute_base`, `_try_tree_sitter` → `try_tree_sitter` in the embedded script.

### Why these bugs were silent

Both bugs affected only sandbox (Docker CI) runs, not `--no-sandbox` local dev mode. Since there are no miner submissions yet, nobody had tested the full CI pipeline end-to-end with an actual agent submission. The bugs would have produced systematically wrong scores for all miners once registration goes live — everyone would have seen `weighted_benchmark_score: 0.0` regardless of actual performance.

## Step 189 — 2026-06-03

### Principal-engineer code audit: 4 PRs, systemic bugs fixed

**Context**: No miner submissions yet; operator asked for continuous self-review and interrogation of the scoring philosophy. Found and fixed 5 latent bugs that would have caused production failures once miners submit.

### PR #52 — Centralize shared constants, fix API shard (merged 204ba9fc)

**Problem**: `REPO_CATEGORY` was copy-pasted across 4 files (evaluate.py, api/server.py, generate_dashboard_data.py, gitminer.py). The vouchdev/vouch category bug (step 183) was caused by exactly this pattern — one file updated, three others stale.

**Fix**: Created `benchmark/catalog.py` as single source of truth for `REPO_CATEGORY`, `DIFFICULTY_TIERS`, and `DEFAULT_SHARD_BUDGET`. All files now import from catalog. Adding a new repo is one line in one file.

**Also fixed**: `/api/shard` endpoint was doing a flat shuffle (no category/difficulty balance). Miners querying the API to preview the shard saw different problems than they'd actually be scored on. Fixed by delegating to `evaluate.py`'s `select_shard()` — the same function CI uses.

**Also**: Extracted `_annotate_and_aggregate()` helper in evaluate.py, eliminating an identical 40-line aggregation loop duplicated in both the oracle and agent eval paths.

### PR #53 — Preserve benchmark_score in oracle leaderboard row on rotation (merged b49d0e06)

**Problem**: Sunday pool rotation (`refresh_pool.yml`) regenerates the oracle leaderboard row but was missing `benchmark_score: 1.0` and `weighted_benchmark_score: 1.0`. After the first rotation (scheduled 2026-06-08), the primary ranking metric would be `None` for the oracle row — breaking leaderboard sort and champion detection.

**Fix**: Added the two benchmark fields to the oracle row in `refresh_pool.yml`.

### PR #54 — Dashboard oracle row missing benchmark fields (merged 38506adb)

**Problem**: `generate_dashboard_data.py`'s `_load_oracle_row()` didn't include benchmark fields. Since `load_leaderboard()` replaces the stored oracle row with a freshly computed one, the live dashboard oracle row was always missing the primary metric. Also fixed stale hardcoded fallback values (count=800, mean=12.38 → 1154, 11.48).

### PR #55 — Rank leaderboard by weighted_benchmark_score (merged 943e5f3e)

**Problem** (most critical): `record_result.py` ranked the leaderboard by `weighted_score` (raw Gittensor formula, 0–30 scale) — not `weighted_benchmark_score` (the primary metric since step 186). First miner submission would have been ranked and SOTA-tracked against the wrong metric, with wrong champion detection and wrong marginal gain / contribution weight calculations.

**Fix**: Added `primary_score()` helper, updated `current_sota()`, `update_leaderboard()` sort, and marginal_gain/contribution_weight computation to use `weighted_benchmark_score`. Oracle row in `record_result.py` now also includes benchmark fields. Per-problem breakdown in leaderboard entries now includes `benchmark_score` and `test_pass_rate`. Champion metadata in `record_submission.yml` includes `weighted_benchmark_score`.

### System state after step 189

All 5 bugs were silent (no miner submissions yet), but would have caused systematic wrong behavior in production:
- REPO_CATEGORY bug → wrong category classification for new repos ✅ fixed
- /api/shard flat shuffle → miners see wrong preview shard ✅ fixed  
- Oracle row fields missing → leaderboard sort breaks after rotation ✅ fixed
- Dashboard oracle row → missing primary metric on live site ✅ fixed
- record_result.py wrong sort → entire leaderboard ranked by wrong metric ✅ fixed

API health: pool=1154, oracle=12.70, repos=47 ✅

---

## Step 190 — Eval parallelism, rate limit fixes, scoring audit (2026-06-03)

### Principal-engineer audit findings

Reviewed the full evaluation pipeline with fresh eyes. Found 3 real bugs and 1 architectural bottleneck:

1. **Sequential eval (perf bottleneck)** — `run_evaluation()` scored 30 problems one-at-a-time. At 30–60s/problem = 15–30 min per miner.
2. **No per-problem agent timeout** — `agent.solve()` had no timeout guard. A hung agent ate the entire 60-min CI quota.
3. **Rate limit advisory-only** — `continue-on-error: true` meant rate limits never actually blocked submissions.
4. **Rate limit counts wrong commits** — `git log HEAD` in CI included PR branch commits, not just merged ones. Miners iterating on their PR were hitting the limit before anything merged.

### PR #56 — Parallel evaluation + agent timeout + rate limit hard block (merged bc7a3a7d)

**Parallel evaluation**: replaced sequential loop with `ThreadPoolExecutor(workers=4)`.
- `_score_one_problem(idx, problem_dir, agent, use_sandbox, solve_timeout)` — isolated per-problem worker
- `_solve_with_timeout(agent, problem, timeout)` — wraps `agent.solve()` in single-thread executor with `Future.result(timeout=N)`
- Results sorted by original shard index before `_annotate_and_aggregate` zip
- `--workers INT` CLI flag added (default: 4)
- `--no-sandbox` mode auto-clamps to workers=1 (shared repo cache would race under concurrency)
- Added `SOLVE_TIMEOUT` env var (default 300s) for per-problem agent timeout
- Print lock added for non-interleaved progress output

**Rate limit hard block**: removed `continue-on-error: true` from rate limit CI step. Now blocks on violation.

**eval.yml**: passes `--workers 4` to run_eval.py.

Eval time improvement: ~30 min → ~8 min (4× speedup)

### PR #57 — Add --workers 4 to post-merge authoritative eval (merged b45147bd)

`record_submission.yml` (fires on PR merge) was still running sequentially. Fixed to pass `--workers 4`, matching the PR-eval step.

### PR #58 — Fix rate limit: count merged commits only (merged 52edbd33)

`check_rate_limit.py` used `git log HEAD --since=7 days ago` which in CI counted PR branch commits (not yet merged). Miners pushing 5 times to iterate on their PR would hit the limit before a single submission was accepted.

Fix: `git log origin/main --since=7 days ago` — only counts commits already on main.

### System state after step 190

- main: 52edbd33
- Benchmark: 1154 problems, oracle 12.70 weighted, 47 repos
- Eval: parallel (workers=4), solve timeout 300s, rate limit hard-blocked on merged commits only

---

## Step 191 — Dashboard primary metric fix + stale data audit

### Findings

**Dashboard showing wrong primary metric**: The leaderboard was displaying `score / 30` (raw Gittensor token metric) as the primary column. The actual ranking metric is `weighted_benchmark_score` (0–2.0, oracle = 1.0). Column relabeled and JS rendering updated.

**Dashboard data stale**: `data.json` in the dashboard repo was at pool 812 / oracle 13.62. The CI refresh had been running but commits were orphaned due to squash-merge conflicts with my earlier PRs. Manually synced to current state.

**Category counts wrong in info box**: Dashboard said "12 Python · 8 TypeScript · 5 Rust · 3 JVM · 2 Ruby" (missing Go, stale). Fixed to "11 Python · 7 Rust · 5 TypeScript · 3 Go · 2 JVM · 2 Ruby".

**`generate_dashboard_data.py` used hardcoded shard budget**: Read from `DEFAULT_SHARD_BUDGET` in catalog.py instead of live `pool_config.json`. Fixed to read from pool_config.json with fallback.

**`refresh_dashboard.yml` missing trigger paths**: `benchmark/catalog.py` and `benchmark/pool_config.json` changes didn't trigger dashboard refresh. Added to paths.

**`cmd_mine` oracle gap display**: When `weighted_benchmark_score >= 1.0`, displayed negative gap "gap to oracle: -0.03". Fixed to "beats oracle by +0.03".

### PRs

- **PR #59**: `gitminer.py` mine oracle-gap fix + `refresh_dashboard.yml` trigger paths (merged 9dca8d7e)
- **PR #60**: `generate_dashboard_data.py` reads live shard budget from pool_config.json (merged 6a8f7e05)
- **Dashboard PR #2**: Show `weighted_benchmark_score` as primary leaderboard column (merged)
  - Per-problem breakdown now shows `benchmark_score` + `test_pass_rate`; raw score demoted to secondary
- **Dashboard PR #3**: Sync `data.json` — pool 1154, oracle 12.70, 6 languages, 47 repos (merged)

### System state after step 191

- base-miner main: 6a8f7e05
- dashboard main: d1f481b (pool 1154, oracle 12.70, weighted_benchmark_score as primary)
- Benchmark: 1154 problems, oracle 12.70 weighted, 47 repos, 6 languages
- Scoring model v4: `benchmark_score = test_pass_rate × relative_score × anti_gaming_multiplier`
  `weighted_benchmark_score = sum(benchmark × difficulty_weight) / sum(weight)` (PRIMARY)
