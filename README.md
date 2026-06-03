# Gittensor Base-Miner Benchmark

[![Dashboard](https://img.shields.io/badge/dashboard-live-brightgreen)](https://punchthedev.github.io/gittensor-miner-dashboard/)
[![Pool](https://img.shields.io/badge/pool-1131%20problems-blue)](benchmark/problems/)
[![CI](https://github.com/PunchTheDev/gittensor-base-miner/actions/workflows/eval.yml/badge.svg)](https://github.com/PunchTheDev/gittensor-base-miner/actions/workflows/eval.yml)
[![License](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

**[Live leaderboard](https://punchthedev.github.io/gittensor-miner-dashboard/)** — see current rankings, pool stats, and the full problem browser.
**[REST API](docs/api.md)** — fetch problems, shard, and leaderboard data programmatically.

A competitive benchmark where miners build the best autonomous agent for contributing to open-source software — scored by replaying real merged Gittensor pull requests.

The winning agent becomes the canonical base miner for [Gittensor (SN74)](https://github.com/entrius/gittensor), a Bittensor subnet that incentivizes software development.

> **Idle compute, earning continuously.** Point `gitminer mine` at your agent
> and it runs every week when a new shard rotates in — your machine contributes
> code, earns TAO, and sharpens the best open-source coding agent on the
> network. Agentic development as infrastructure.

---

## What you're building

Gittensor rewards miners who contribute quality code to whitelisted open-source repositories. This benchmark measures **agent scaffolding skill**: given a frozen, whitelisted LLM, how well can you engineer the wrapper around it to produce correct, high-quality code patches?

Each submission is an agent that receives a GitHub issue and repository context, then produces a pull request. It's scored by replaying a curated set of real Gittensor issues against their accepted solutions — using Gittensor's own scoring engine as the judge.

The champion agent lives in `agent/champion/` and is updated each time a miner beats the current record.

---

## How scoring works

1. A curated pool of 1131 real issues is held in `benchmark/problems/`, spanning 46 active repos across 6 language categories. Each eval round uses a rotating 30-problem shard.
2. Each issue has a recorded "correct" solution (the merged PR diff) used as a reference signal.
3. Your agent checks out the repo at the pre-issue commit, reads the issue, and produces a patch.
4. Scoring is done by Gittensor's native engine: tests passing + issue requirements covered, then code quality/density.
5. **Correctness gates quality** — a passing test suite is required before quality metrics count.
6. Your agent's score = mean score across all problems. Beat the current champion to win.

### Anti-gaming

- **Commit-reveal**: Submit a SHA-256 hash of your agent first; the harness evaluates privately; only then is your score published.
- **Time-segmented problems**: All benchmark problems come from PRs merged *after* the agent's model knowledge cutoff, making memorization impossible.
- **Marginal reward**: Rewards are proportional to margin over the current leader, not absolute score. Copying earns near zero.
- **Similarity checks**: Submissions are compared against prior submissions; near-duplicates are flagged.

See [docs/threat_model.md](docs/threat_model.md) for the full threat model.

---

## Submission interface

Your agent must implement the `BaseAgent` interface in `agent/base.py`:

```python
from agent.base import BaseAgent, Problem, Patch

class MyAgent(BaseAgent):
    def solve(self, problem: Problem) -> Patch:
        ...
```

A `Problem` contains the issue body, repository context (file tree + relevant file contents), and constraints (model whitelist, time limit, token budget). A `Patch` is a unified diff string.

See `agent/example/` for the baseline reference implementation — a full observe→plan→act loop with context ranking, hunk repair, and diff post-processing. Fork it as your starting point.

---

## Running the benchmark locally

```bash
# Install dependencies
pip install -r requirements.txt
export OPENROUTER_KEY=your_key_here   # required to run agents (get one at openrouter.ai)

# Verify your environment is set up correctly (run this first)
python3 gitminer.py doctor
python3 gitminer.py doctor --agent agent/submissions/yourhandle/agent.py

# Show the current 30-problem weekly shard
python3 gitminer.py shard

# Run your agent on one problem and inspect the patch it produces (fast dev loop)
python3 gitminer.py run --problem 0463 --agent agent/submissions/yourhandle/agent.py
python3 gitminer.py run --problem 0463 --show-ref --score --no-sandbox   # compare to reference + score inline
python3 gitminer.py run --problem 0463 --score --no-sandbox --repair 3   # if tests fail, agent repairs with test output (up to 3 attempts)

# Evaluate your agent against the shard (no Docker)
python3 gitminer.py eval agent/submissions/yourhandle/agent.py --no-sandbox

# Calibration check: score reference diffs to verify the full pipeline (no agent or API key needed)
python3 gitminer.py eval --oracle --no-sandbox   # expected weighted mean: ~12.64 / 30.00

# Evaluate against all 1131 pool problems
python3 gitminer.py eval agent/submissions/yourhandle/agent.py --all

# Evaluate against specific problem IDs
python3 gitminer.py eval agent/submissions/yourhandle/agent.py --problems 930,986

# Validate that a patch applies cleanly to a problem's base commit (quick sanity check)
python3 gitminer.py validate --problem 0463 --patch my_fix.diff

# Browse the current leaderboard in the terminal
python3 gitminer.py leaderboard

# Generate commit-reveal hash for your agent before submitting
python3 gitminer.py hash agent/submissions/yourhandle/agent.py

# Validate agent and print PR submission steps
python3 gitminer.py submit agent/submissions/yourhandle/agent.py

# --- Pool exploration ---

# List and filter benchmark problems
python3 gitminer.py problems                                    # all 1000 problems
python3 gitminer.py problems --cat python --difficulty hard     # filter by language/difficulty
python3 gitminer.py problems --repo ragflow --limit 10          # filter by repo name
python3 gitminer.py problems --search "rate limit"              # full-text search

# Check local scorer calibration vs. DAS reference scores (maintainer tool)
python3 gitminer.py parity                                      # top 20 most divergent problems
python3 gitminer.py parity --top 50                             # show 50 rows

# --- Idle mining (daemon mode) ---

# Run once against the current shard; auto-submit if you beat the champion
python3 gitminer.py mine --agent agent/submissions/yourhandle/agent.py --no-sandbox

# Daemon mode: run once per shard rotation (weekly), sleep in between
python3 gitminer.py mine --agent agent/submissions/yourhandle/agent.py --loop

# --- REST API (for scripting / external tooling) ---

# Start the JSON API server on port 8083
python3 gitminer.py serve-api

# Example: fetch this week's shard in a shell script
curl http://localhost:8083/api/shard
curl http://localhost:8083/api/problems/0463
curl "http://localhost:8083/api/problems?cat=python&difficulty=hard&limit=10"
curl http://localhost:8083/api/leaderboard
```

See [docs/api.md](docs/api.md) for the full API reference.

---

## Repository structure

```
agent/
  base.py              # BaseAgent interface and data types
  champion/            # current champion agent (populated after first winner)
  example/             # baseline reference implementation (observe → plan → act loop)
  submissions/         # miner agent landing zone
benchmark/
  problems/            # 1131 curated historical issues (one dir per PR id))
  harness/             # replay and scoring pipeline
  evaluate.py          # evaluation runner (used by gitminer and CI)
  pool_config.json     # pool/shard configuration
api/
  server.py            # REST API server (serve-api subcommand)
scripts/
  build_pool.py        # DAS API-based pool builder and refresher
docs/
  api.md               # REST API reference
  scoring.md           # scoring mechanics explained
  hyperparameters.md   # Gittensor hyperparameter configuration for this repo
  threat_model.md      # anti-gaming threat model
gitminer.py            # CLI: eval / run / validate / leaderboard / hash / shard / problems / parity / submit / mine / serve-api
CONTRIBUTING.md        # how to submit
hyperparameters.json   # live Gittensor repo hyperparameter config
```

---

## Leaderboard

See [LEADERBOARD.md](LEADERBOARD.md) for current rankings. Beat the champion to take the contributor share of emissions.

---

## Rewards

Understand exactly how your benchmark score converts to TAO: [docs/rewards.md](docs/rewards.md).

The short version: CI labels your PR `agent-improvement` (2.0× multiplier). Beat the current champion and `new-champion` is added. Gittensor's validator reads the label and weights your PR accordingly in the 45-day emission window.

## Hyperparameters

This repo is registered on Gittensor (SN74). See [docs/hyperparameters.md](docs/hyperparameters.md) for how rewards are distributed and why each parameter was chosen.

---

## License

MIT
