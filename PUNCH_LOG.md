# Punch Log — Gittensor Base-Miner Flywheel

Milestone trail for the base-miner benchmark. Discord is the primary channel; this file is the audit trail.

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
