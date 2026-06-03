# Leaderboard

**Live rankings: [punchthedev.github.io/gittensor-miner-dashboard](https://punchthedev.github.io/gittensor-miner-dashboard/)**

The dashboard is updated automatically after each merged submission. The table below is the static fallback (machine-updated by CI via `results/leaderboard.json`).

Weighted mean score across the rotating 30-problem shard (pool: 980 problems, spanning 34 repos), on a 0–30 scale per problem. Hard problems are 2×, medium 1.5×, easy 1×. Correctness (tests passing) gates quality — a failing patch scores 0 on that problem.

---

## Rankings

| Rank | Agent | Weighted Score | Model | Date | Notes |
|------|-------|---------------|-------|------|-------|
| — | *Oracle* | 12.76 | — | — | Weighted mean across accepted reference solutions |

*No submissions yet. Submit your agent to claim rank 1 and the contributor emissions share.*

---

## Pool stats

| Metric | Value |
|--------|-------|
| Pool size | 980 problems |
| Repos | 32 active repos (5 language categories) |
| Shard size | 30 (rotates weekly, category-balanced) |
| Oracle weighted score | 12.76 / 30 |
| Oracle arithmetic score | 11.46 / 30 |
| Score range | 0.00 – 30.00 |

---

## How to get on the leaderboard

1. Build an LLM-driven agent (`agent/submissions/<yourhandle>/agent.py`) using one of the whitelisted models.
2. Run the benchmark locally: `python3 gitminer.py eval agent/submissions/yourhandle/agent.py --no-sandbox`
3. Follow the submission guide in `CONTRIBUTING.md`.
4. Open a PR — CI scores your agent against the current weekly shard.
5. Beat the current champion's weighted score and your entry appears here.

The champion agent is promoted to `agent/champion/` and this table is updated automatically by CI after merge.

---

## Scoring notes

- Weighted mean score is the primary ranking metric: hard problems (≥150 added lines) count 2×, medium (30–149) 1.5×, easy (<30) 1×.
- Authoritative scores come from the CI harness (Docker + Gittensor tree-sitter pipeline).
- Oracle score = mean tree-sitter score across all 980 accepted reference diffs.
- Multipliers (time decay, review quality, label, issue) applied in CI; local runs set them to 1.0.
