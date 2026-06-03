# Reference agent

This is the baseline implementation every miner should read before building their own. Fork it, measure against it, beat it.

## What it does

The agent receives a GitHub issue and repository context, then produces a unified diff that fixes the issue. It follows an **observe → plan → act → verify** loop:

1. **Observe** — ranks files by relevance (issue keywords + symbols the test files import/call), windows large files to the relevant sections, resolves test imports to pinpoint the exact files under test.
2. **Plan** — reasons about what each test assertion requires before writing any code, producing a file-and-line hypothesis.
3. **Act** — generates a unified diff from the ranked context and the plan.
4. **Verify** — checks diff structure (hunk headers, line offsets, missing imports, bare stubs) and enters a repair loop (up to 3 attempts) if tests fail, feeding back test output each round.

## Scoring model

Correctness gates quality — tests must pass before quality metrics count. After that:

```
benchmark_score = test_pass_rate × relative_score × anti_gaming_multiplier × test_quality_factor
```

`relative_score` is the agent's AST token score divided by the oracle's — complete, well-structured implementations earn more than minimal stubs. `test_quality_factor` rewards adding test assertions alongside the fix. The example agent is tuned to produce thorough implementations, not one-liners.

## Running it

```bash
# Score the reference agent on one problem
python3 gitminer.py run --problem 0463 --agent agent/example/agent.py --score --no-sandbox

# Score against the full shard
python3 gitminer.py eval agent/example/agent.py --no-sandbox

# Compare your agent to this baseline
python3 gitminer.py eval agent/submissions/yourhandle/agent.py --no-sandbox
```

## Key design patterns to steal

- **Import-path resolution** (`_resolve_test_imports`): maps test `import` / `require_relative` statements to the exact implementation files. More reliable than keyword matching.
- **Windowed context** (`_window_file`): shows `±40 lines` around keyword hits with `N | content` line-number markers so the model can write accurate `@@ -N` hunk offsets.
- **New-file detection**: identifies test files not present in the repo at `base_commit` — the agent must create those files, not modify them.
- **Language-specific system prompts**: Go/Rust/TypeScript/Ruby/Python/Kotlin/Java each get convention reminders (trait bounds, exports, companion objects, etc.) that generic prompts miss.
- **Sibling import expansion**: after ranking the top-3 implementation files, local imports from those files are added to context (up to 6 KB) so the model doesn't hallucinate helpers that already exist.

## Interface

The agent must subclass `BaseAgent` from `agent/base.py` and implement `solve(problem: Problem) -> Patch`. See `base.py` for the full `Problem` and `Patch` data classes.
