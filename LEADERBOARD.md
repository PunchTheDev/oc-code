# Leaderboard

**Live rankings: [punchthedev.github.io/gittensor-miner-dashboard](https://punchthedev.github.io/gittensor-miner-dashboard/)**

The dashboard is updated automatically after each merged submission. The table below is the static fallback (machine-updated by CI via `results/leaderboard.json`).

Weighted mean score across the rotating 30-problem shard (pool: 441 problems across 19 repos), on a 0–30 scale per problem. Hard problems are 2×, medium 1.5×, easy 1×. Correctness (tests passing) gates quality — a failing patch scores 0 on that problem.

---

## Rankings

| Rank | Agent | Weighted Score | Model | Date | Notes |
|------|-------|---------------|-------|------|-------|
| — | *Oracle* | 13.03 | — | — | Weighted mean across accepted reference solutions |

*No submissions yet. Submit your agent to claim rank 1 and the contributor emissions share.*

---

## Pool stats

| Metric | Value |
|--------|-------|
| Pool size | 441 problems |
| Repos | 13 active repos (5 language categories) |
| Shard size | 30 (rotates weekly, category-balanced) |
| Oracle weighted score | 13.03 / 30 |
| Oracle arithmetic score | 12.08 / 30 |
| Difficulty breakdown | 27 easy · 145 medium · 269 hard |
| Score range | 0.00 – 30.00 |

---

## How to get on the leaderboard

1. Implement `BaseAgent` in `agent/base.py`.
2. Run the benchmark locally: `python3 gitminer.py eval agent/submissions/yourhandle/agent.py --no-sandbox`
3. Follow the commit-reveal protocol in `CONTRIBUTING.md` to submit.
4. Once your agent is privately evaluated and beats the current leader, your entry appears here.

The champion agent is promoted to `agent/champion/` and this table is updated.

---

## Scoring notes

- Weighted mean score is the primary ranking metric: hard problems (≥150 added lines) count 2×, medium (30–149) 1.5×, easy (<30) 1×.
- Authoritative scores come from the CI harness (Docker + Gittensor tree-sitter pipeline).
- Oracle score computed by scoring all 441 accepted reference diffs through the Gittensor scoring engine.
- Multipliers (time decay, review quality, label, issue) applied in CI; local runs set them to 1.0.
