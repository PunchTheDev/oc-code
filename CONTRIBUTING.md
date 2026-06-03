# Contributing

This guide walks you through submitting a base-miner agent end-to-end.

## What you're building

An agent that implements `BaseAgent.solve(problem: Problem) -> Patch`. The harness
replays real Gittensor issues and grades your agent's diff against the reference
solution using Gittensor's native scoring formula. Scaffolding is the game — the
frozen model is fixed, your wrapper around it is what competes.

## Setup

```bash
git clone https://github.com/PunchTheDev/gittensor-base-miner
cd gittensor-base-miner
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export OPENROUTER_KEY=your_key_here
```

Docker must be running for the sandboxed harness. If you want to skip Docker during
development, pass `--no-sandbox` (see below).

## Write your agent

Create a directory under `agent/submissions/<your-handle>/` and add two files:

**`meta.json`** — required metadata (CI validates this before eval):
```json
{
  "handle": "<your-handle>",
  "model": "deepseek/deepseek-v3",
  "sha256": "<sha256 of your agent.py — run: python3 gitminer.py hash agent.py>"
}
```

The `model` field must be a model listed in `benchmark/harness/allowed_models.txt`.
The `sha256` must match your `agent.py` at submission time (commit-reveal integrity).

**`agent.py`** — your agent implementation. Must subclass `BaseAgent` from `agent.base`:

```python
from agent.base import BaseAgent, Patch, Problem

class MyAgent(BaseAgent):
    def solve(self, problem: Problem) -> Patch:
        # problem.issue_title, problem.issue_body — what to fix
        # problem.context_files — relevant source files at base_commit
        # problem.allowed_models — whitelist of callable model IDs
        ...
        return Patch(diff="...unified diff...", reasoning="optional notes")
```

See `agent/example/agent.py` for a reference implementation with an
observe → plan → act → verify loop. Beat it.

### Constraints enforced by the harness

| Constraint | Limit |
|---|---|
| Models | Whitelist in `benchmark/harness/allowed_models.txt` |
| Wall time | 120 s per problem |
| Output tokens | 50 000 per problem |
| Network | Blocked — model API only |
| External state | None — no disk reads outside sandbox |

## Run the benchmark locally

**Pre-warm the repo cache (recommended before first `--no-sandbox` run):**
```bash
python3 gitminer.py cache
```
Clones all pool repos once into `~/.cache/gitminer/repos/`. Subsequent `--no-sandbox`
evals use git worktrees instead of cloning, cutting a 30-problem run from ~20 min to
a few minutes. Set `GITMINER_CACHE=/path/to/dir` to override the cache location.

**Run your agent on a single problem (fastest development loop):**
```bash
python3 gitminer.py run --problem 0463 --agent agent/submissions/<your-handle>/agent.py
```
Prints the patch your agent produces for one problem. Add flags to go deeper:
```bash
# Compare side-by-side with the reference diff and score inline
python3 gitminer.py run --problem 0463 --agent agent/submissions/<your-handle>/agent.py \
    --show-ref --score --no-sandbox

# Save the patch to a file for inspection or validation
python3 gitminer.py run --problem 0463 --output my_fix.diff

# Print the agent's internal reasoning log
python3 gitminer.py run --problem 0463 --verbose
```

**With Docker sandbox (same scoring method as CI):**
```bash
python3 gitminer.py eval agent/submissions/<your-handle>/agent.py
```

**Without Docker (faster, less isolated — development only):**
```bash
python3 gitminer.py eval agent/submissions/<your-handle>/agent.py --no-sandbox
```

> **Note on shard vs local:** CI evaluates on a different 30-problem shard than
> your local run (a server-side secret shifts the selection to prevent overfitting).
> Use `--all` for a stable local benchmark that doesn't vary by shard:
> ```bash
> python3 gitminer.py eval agent/submissions/<your-handle>/agent.py --all
> ```
> The authoritative score is always the one CI posts in your PR comment.

**Subset of problems:**
```bash
python3 gitminer.py eval agent/submissions/<your-handle>/agent.py --problems 930,986,1033
```

**Save results to a file:**
```bash
python3 gitminer.py eval agent/submissions/<your-handle>/agent.py --output results.json
```

**Validate a single patch applies cleanly (quick sanity check):**
```bash
python3 gitminer.py validate --problem 0463 --patch my_fix.diff
python3 gitminer.py validate --problem 0463 --patch my_fix.diff --run-tests
```
Applies the diff to the problem's base commit and shows the diff stat. `--run-tests`
also runs the problem's test command locally (requires deps installed in your environment).
Useful for verifying a generated patch before running a full eval.

Scores are on the 0–30 scale matching Gittensor's native formula. The leaderboard
shows the current champion's score — that's the number to beat.

## Commit-reveal flow

Public PRs are visible to everyone, so we use a two-phase commit-reveal to establish first-to-commit credit.

### Phase 1 — hash before pushing (when you open the PR)

Before pushing your agent file, generate and record its hash:

```bash
python3 gitminer.py hash agent/submissions/<your-handle>/agent.py
```

Paste the printed SHA-256 into the `reveal-hash:` field of your PR description **before** pushing the agent file.

### Phase 2 — automatic verification (after merge)

Once your PR merges, anyone can verify your hash by re-running the same command against the merged file. The hash proves you held this version at open time — preventing post-eval copying for first-to-commit credit.

## PR format

Run `gitminer submit` to auto-generate the PR body and branch with the correct format. Fill in your local eval results and a brief description of your approach in the generated body.

If submitting manually, use the PR template and include:
- `reveal-hash:` — your SHA-256 hash (from `gitminer hash`)
- Your local eval score
- The model ID you used (must be on the whitelist)
- A sentence on what your scaffolding does differently

## After you open the PR

CI automatically runs the full benchmark in Docker and posts a score table as a
comment. If the score is a new leaderboard high, maintainers merge the PR.
The `record_submission` workflow then re-scores your agent, updates the leaderboard,
SOTA history, and behavior fingerprint, and promotes your agent to `agent/champion/` automatically.
You don't need to do anything else — the [live dashboard](https://punchthedev.github.io/gittensor-miner-dashboard/)
reflects the updated standings within minutes of the merge.

## Adding benchmark problems

To propose a new problem (a real Gittensor issue with a merged PR and tests), open
an issue using the `Problem Proposal` template. Maintainers review it against the
curation criteria in `docs/scoring.md` and add it if it qualifies.

## Autonomous mining (daemon mode)

Once your agent works locally, you can run it as a continuous background process.
`gitminer mine` scores your agent against the current shard and tells you if you
beat the champion. In `--loop` mode it sleeps until the next shard rotation and
runs again automatically — your machine earns TAO whenever it's idle.

```bash
# One-shot: run now and print result
python3 gitminer.py mine --agent agent/submissions/<your-handle>/agent.py --no-sandbox

# Daemon mode: run every week when the shard rotates
python3 gitminer.py mine --agent agent/submissions/<your-handle>/agent.py --loop
```

If you beat the champion, the daemon prints a commit-reveal hash and step-by-step
PR instructions. From there it's the same submit flow above.

## REST API

The benchmark exposes a JSON API for scripting, dashboards, and custom tooling.

```bash
# Start the API server
python3 gitminer.py serve-api          # http://localhost:8083

# Useful calls
curl http://localhost:8083/api/shard
curl http://localhost:8083/api/problems/0463
curl "http://localhost:8083/api/problems?cat=python&difficulty=hard&limit=10"
curl http://localhost:8083/api/leaderboard
```

See [docs/api.md](docs/api.md) for the full reference.

## Code standards

- Keep your submission self-contained under `agent/submissions/<your-handle>/`.
- A `requirements.txt` inside your directory is fine for extra dependencies.
- No shell scripts that bypass the `BaseAgent` interface.
- `solve()` must be deterministic enough to re-run — avoid non-seeded randomness.
