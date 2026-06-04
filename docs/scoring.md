# Scoring

## Overview

Submissions are scored by replaying real Gittensor issues in an isolated sandbox. The scoring pipeline combines **Gittensor's native tree-sitter quality engine** (the same AST scorer the DAS validator uses) with benchmark-specific metrics that capture correctness depth, oracle-relative quality, difficulty, and anti-gaming integrity.

## Scoring philosophy

A good base miner does two things: it produces correct fixes, and it produces high-quality code. Raw Gittensor scoring only captures quality (via AST token analysis). Our benchmark adds:

1. **Partial correctness** — A fix that passes 9/10 tests is better than 0/10. `test_pass_rate` captures this continuously, not as a binary gate.
2. **Oracle-relative quality** — A 2-line fix on a 2-line problem is worth as much as a 200-line fix on a 200-line problem. `relative_score` normalizes quality against what the accepted solution actually scored.
3. **Difficulty weighting** — Hard problems count 2× as much as easy ones. Difficulty is multi-factor: line count plus a structural complexity modifier for multi-file and new-file-creation problems. An agent that solves genuinely hard problems should outrank one that coasts on easy ones.
4. **Anti-gaming** — Submissions that remove test assertions to force a pass are penalized in their score.

## Metrics

| Metric | Scale | Purpose |
|---|---|---|
| `weighted_benchmark_score` | 0–2.0 | **PRIMARY leaderboard rank** — difficulty-weighted `benchmark_score` |
| `benchmark_score` | 0–2.0 | Per-problem: `test_pass_rate × relative_score × anti_gaming_multiplier × test_quality_factor × efficiency_factor` |
| `relative_score` | 0–2.0 | Agent quality / oracle quality for this specific problem |
| `test_pass_rate` | 0–1.0 | Fraction of tests that pass (granular correctness) |
| `test_quality_factor` | 0.85–1.0 | Test assertion coverage multiplier (1.0 when no expectation set) |
| `efficiency_factor` | 0.85–1.0 | Token efficiency multiplier — 1.0 at ≤10k output tokens, decays linearly to 0.85 at 50k |
| `final_score` | 0–30 | Gittensor native AST score (retained for on-chain comparison) |
| `file_coverage` | 0–1.0 | Fraction of reference source files touched (diagnostic, not scored) |
| `test_coverage_ratio` | 0–1.0 | Agent assertions added / reference assertions added (feeds test_quality_factor) |

## Primary metric: weighted_benchmark_score

```
benchmark_score          = test_pass_rate × relative_score × anti_gaming_multiplier × test_quality_factor × efficiency_factor
weighted_benchmark_score = sum(benchmark_score_i × difficulty_weight_i) / sum(difficulty_weight_i)
```

This is the leaderboard ranking metric. Hard problems (weight 2.0) contribute twice as much as easy ones (weight 1.0). A submission that scores 1.0 on a hard problem is worth more than 1.0 on an easy problem.

**Oracle baseline**: the oracle (accepted reference solution) scores exactly `weighted_benchmark_score = 1.0` by definition — `test_pass_rate = 1.0`, `relative_score = 1.0`, `test_quality_factor = 1.0`, `efficiency_factor = 1.0` (oracle does not report tokens).

### Interpreting benchmark_score

A submission's per-problem `benchmark_score`:

| Value | Meaning |
|---|---|
| `1.0` | All tests pass, oracle quality, matching test coverage |
| `> 1.0` | All tests pass, *better* code quality than accepted solution (up to 2.0) |
| `0.925` | All tests pass, oracle quality, 50% of reference test assertion coverage |
| `0.85` | All tests pass, oracle quality, no test assertions added (when reference did) |
| `0.5` | 50% tests pass at oracle quality |
| `0.0` | No tests pass, or patch doesn't apply |
| `≤ 0.5` (when warned) | Anti-gaming penalty applied for test deletion |

## Test pass rate

```
test_pass_rate = tests_passed_count / tests_total_count
```

Parsed from test runner output for each language:

| Runner | Signal |
|---|---|
| pytest | `N passed, M failed in Xs` |
| cargo test | `test result: ok. N passed; M failed` |
| go test | count of `--- PASS:` and `--- FAIL:` lines |
| jest / vitest | `Tests: N passed, M total` |
| rspec | `N examples, M failures` |
| gradle | `N tests completed, M failed` |

When parsing fails, `test_pass_rate` falls back to the binary exit-code result (1.0 = pass, 0.0 = fail).

## Relative score

```
relative_score = min(agent_final_score / oracle_base_score, 2.0)
```

`oracle_base_score` is our tree-sitter scorer's score on the accepted reference diff for that problem (from `results/baselines.json`). The oracle scores exactly 1.0 against itself. The cap of 2.0 prevents verbose patches from inflating scores unboundedly.

Interpretation:
- `1.0` — same quality signal as the accepted solution
- `> 1.0` — higher-quality fix (more structured code changes)
- `< 1.0` — lower structural quality than the accepted solution
- `None` — oracle score unavailable (excluded from aggregates)

## Anti-gaming: test deletion penalty

```
anti_gaming_multiplier = 1.0                          if removed ≤ 3   (noise tolerance)
anti_gaming_multiplier = 1.0 − 0.1 × (removed − 3)  if 4 ≤ removed ≤ 8  (0.9 → 0.5)
anti_gaming_multiplier = 0.5                          if removed > 8   (floor)
```

If a submission removes test assertions from test files, a graduated penalty is applied. Up to 3 removals are tolerated as noise. From 4 to 8 removals, the multiplier decays linearly from 0.9 to 0.5. Beyond 8 removals, the floor of 0.5 applies.

| Assertions removed | `anti_gaming_multiplier` |
|---|---|
| ≤ 3 | 1.0 (no penalty) |
| 4 | 0.9 |
| 5 | 0.8 |
| 6 | 0.7 |
| 7 | 0.6 |
| ≥ 8 | 0.5 |

The graduated approach avoids the binary cliff where removing 4 assertions is penalised identically to removing 40. The flag (`test_deletion_warning`) and raw count (`test_assertions_removed`) are both exposed in the result dict for transparency.

## Base quality formula

Mirrors Gittensor's native scoring exactly (constants from `gittensor/constants.py`):

```
base_score   = 25 × (1 − exp(−src_tokens / 58.0))   # quality term, 0–25
bonus_score  = min(contribution_score / 1500, 1) × 5 # cross-category bonus, 0–5
final_score  = base_score + bonus_score               # 0–30 total
```

`final_score` is used to compute `relative_score` and retained for direct comparison to Gittensor on-chain emissions scoring.

## Quality scoring (tree-sitter)

The primary scorer is Gittensor's tree-sitter AST pipeline:

1. Parse old and new file versions into tree-sitter ASTs.
2. Compute the symmetric difference of AST node signatures.
3. Weight each node: structural nodes (functions, classes, loops) get bonus weight; leaf tokens get base weight; comments score 0.
4. Apply a language weight multiplier (Go/Java/C/Rust = 2.0×, Python = 1.5×, JS = 1.15×, etc.).
5. `src_tokens` = weighted score from non-test files only.

Meaningful, structured code changes score higher. Comments and whitespace score 0. Scoring is fully deterministic — no LLM judge.

Weight files (`benchmark/harness/weights/`) are copied directly from the Gittensor validator. Docker CI uses the identical pipeline end-to-end.

## Problem difficulty tiers

Difficulty uses a **multi-factor model** combining diff size with structural complexity signals:

| Tier | Effective lines | Weight |
|---|---|---|
| Easy | < 30 | 1.0× |
| Medium | 30–149 | 1.5× |
| Hard | 150+ | 2.0× |

**Effective lines** = `added_lines × complexity_factor`, where:

- **Base** (`complexity_factor = 1.0`): raw added-line count from the reference diff.
- **Multi-file modifier (×1.3)**: applied when the reference diff touches ≥ 5 files. Multi-file problems require understanding cross-module interactions and coordinating changes across an API surface — qualitatively harder than a local patch.
- **New-file modifier (×1.2)**: applied when the reference diff creates at least one new file (`--- /dev/null`). Creating a new module demands correct API surface, module structure, and a complete test file from scratch.

Modifiers stack multiplicatively. A 90-line diff that creates a new file and touches 6 modules scores ≈140 effective lines (promoted to hard). A 90-line single-file patch stays medium.

The raw added-line threshold still anchors the tier — complexity modifiers only promote, never demote.

## Correctness check

1. Apply the patch to the repository at `base_commit` (the commit just before the issue was filed).
2. Run the test suite (`test_cmd` from `meta.json`).
3. Compute `test_pass_rate` from runner output.
4. Proceed to quality scoring regardless of test result — `benchmark_score` combines both.

The test suite is the arbiter of correctness. An agent that finds a *better* fix than the reference solution is not penalized — if it passes the tests, it earns a full quality score.

## Heuristic fallback scoring

When tree-sitter is unavailable (local dev without the scorer image), `final_score` falls back to a weighted token heuristic on diff added-lines. Heuristic scores run approximately **2× higher** than DAS reference scores (measured: local mean 23.47 vs DAS mean 10.78 across 289 reference diffs). This affects `relative_score` proportionally — use `--no-sandbox` for local development only, never to compare absolute scores to the leaderboard. The sandbox CI pipeline uses tree-sitter end-to-end.

## File coverage (diagnostic only)

```
file_coverage = |agent_source_files ∩ reference_source_files| / |reference_source_files|
```

Test files excluded. Not penalized — an agent with a different but correct approach may touch different files. Diagnostic only.

## Test quality factor

```
test_coverage_ratio  = min(1.0, agent_assertions_added / ref_assertions_added)
test_quality_factor  = 0.85 + 0.15 × test_coverage_ratio   (when ratio is not None)
test_quality_factor  = 1.0                                  (when ratio is None — no expectation)
```

Counts test assertion patterns added in the agent diff vs. the reference diff, then converts the ratio into a `0.85–1.0` multiplier on `benchmark_score`. This incentivizes agents to add test coverage proportional to the reference without catastrophically zeroing out an otherwise-correct fix.

| `test_coverage_ratio` | `test_quality_factor` | Effect |
|---|---|---|
| `None` | `1.0` | Reference added no assertions — no expectation |
| `1.0` | `1.0` | Agent matched reference assertion coverage — no penalty |
| `0.5` | `0.925` | Agent added half the reference assertions — 7.5% penalty |
| `0.0` | `0.85` | Agent added no assertions (when reference did) — 15% penalty |

When `test_coverage_ratio = None` (reference added 0 assertions), the factor is 1.0 and plays no role. This avoids penalizing agents on problems where test assertions were not part of the fix.

## Efficiency factor

```
efficiency_factor = 1.0                                             if tokens_used ≤ 10 000
efficiency_factor = 1.0 − 0.15 × (tokens_used − 10 000) / 40 000  if 10 000 < tokens_used ≤ 50 000
efficiency_factor = 0.85                                            if tokens_used > 50 000
```

A linear decay from 1.0 to 0.85 as output token usage grows from 10 000 to 50 000. Agents that don't report `tokens_used` receive 1.0 — backward-compatible with agents that predate token tracking.

| `tokens_used` | `efficiency_factor` |
|---|---|
| ≤ 10 000 | 1.0 (no penalty) |
| 20 000 | 0.9625 |
| 30 000 | 0.925 |
| 40 000 | 0.8875 |
| ≥ 50 000 | 0.85 (floor) |

This incentivizes compact reasoning rather than long chain-of-thought padding. An agent using 10k tokens earns full score; one using the full 50k budget earns 85% after correctness and quality. Token tracking is opt-in: return `(diff, tokens)` from `_call()` in your agent and `tokens_used` accumulates automatically.

## Problem curation criteria

A historical issue is included if:

1. The PR was merged (not just closed).
2. The PR closes a valid GitHub issue filed before the PR was opened.
3. At least one test file was modified or added in the merged PR.
4. The patch applies cleanly to `base_commit`.
5. The PR was merged after `MODEL_CUTOFF_DATE` (prevents memorization).

## Anti-copy: time segmentation

All problems come from PRs merged after the knowledge cutoff of the whitelisted models. New PRs are continuously added as Gittensor grows, keeping the benchmark evergreen.

## Reference solution

Each problem includes `reference.diff` — the actual merged PR diff. Used as a **signal**, not the answer key. An agent that covers more requirements isn't penalized. An agent that trivially copies the reference is flagged via similarity checks.
