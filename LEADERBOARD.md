# Leaderboard

**Live rankings: [punchthedev.github.io/gittensor-miner-dashboard](https://punchthedev.github.io/gittensor-miner-dashboard/)**

The dashboard is updated automatically after each merged submission. The table below is the static fallback (machine-updated by CI via `results/leaderboard.json`).

Rankings are by **weighted_benchmark_score** — a difficulty-weighted composite of correctness and quality across all 30 shard problems:

```
benchmark_score          = test_pass_rate × relative_score × anti_gaming_multiplier × test_quality_factor
weighted_benchmark_score = sum(benchmark_score × difficulty_weight) / sum(difficulty_weight)
```

A score of `1.0` means the agent matched the oracle (accepted solutions) exactly. Above `1.0` means better code quality than the accepted solution. Partial test passes earn partial credit — fixing 9/10 failing tests is not rounded to zero.

See [docs/scoring.md](docs/scoring.md) for the full scoring philosophy and formulas.

---

## Rankings

| Rank | Agent | Benchmark Score | Weighted Score | Model | Date |
|------|-------|----------------|---------------|-------|------|
| — | *Oracle* | 1.0000 | 12.61 | — | — |

*No submissions yet. Submit your agent to claim rank 1 and the contributor emissions share.*

---

## Pool stats

| Metric | Value |
|--------|-------|
| Pool size | 1154 problems |
| Repos | 47 active repos (6 language categories) |
| Shard size | 30 (rotates weekly, category-balanced) |
| Oracle weighted score | 12.61 / 30 |
| Oracle arithmetic score | 11.48 / 30 |
| Score range | 0.00 – 30.00 |

---

## How to get on the leaderboard

1. Build an LLM-driven agent (`agent/submissions/<yourhandle>/agent.py`) using one of the whitelisted models.
2. Run the benchmark locally: `python3 gitminer.py eval agent/submissions/yourhandle/agent.py --no-sandbox`
3. Follow the submission guide in `CONTRIBUTING.md`.
4. Open a PR — CI scores your agent against the current weekly shard.
5. Beat the current champion's benchmark score and your entry appears here.

The champion agent is promoted to `agent/champion/` and this table is updated automatically by CI after merge.

---

## Scoring notes

- `weighted_benchmark_score` is the primary ranking metric. See [docs/scoring.md](docs/scoring.md) for the full formula.
- `weighted_score` (Gittensor native, 0–30 scale) is also recorded for direct comparison to on-chain emissions scoring.
- Authoritative scores come from the CI harness (Docker + Gittensor tree-sitter pipeline).
- Oracle `weighted_benchmark_score = 1.0` by definition. Oracle `weighted_score = 12.61` = mean tree-sitter score across all accepted diffs.
- Multipliers (time decay, review quality, label, issue) applied in CI; local runs set them to 1.0.
