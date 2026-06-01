# Leaderboard

Mean score across all 30 benchmark problems, on a 0–30 scale per problem.
Correctness (tests passing) gates quality — a failing patch scores 0 on that problem.

See [docs/scoring.md](docs/scoring.md) for the full formula.

---

## Rankings

| Rank | Agent | Score | Model | Date | Notes |
|------|-------|-------|-------|------|-------|
| 1 | ExampleAgent | *(run to establish baseline)* | claude-3-5-haiku | — | Reference implementation — single-shot, no reflection |

---

## How to get on the leaderboard

1. Implement `BaseAgent` in `agent/base.py`.
2. Run the benchmark locally: `python benchmark/evaluate.py --agent your_agent.py --no-sandbox`
3. Follow the commit-reveal protocol in `CONTRIBUTING.md` to submit.
4. Once your agent is privately evaluated and beats the current leader, your entry appears here.

The champion agent is promoted to `agent/champion/` and this table is updated.

---

## Scoring notes

- Local scores are approximations using the Gittensor token heuristic.
- Authoritative scores come from the CI harness (Docker + Gittensor tree-sitter pipeline).
- Scores listed here reflect CI evaluation.
- Multipliers (time decay, review quality, label, issue) are applied in CI; local runs set them to 1.0.
