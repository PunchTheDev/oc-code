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

Create a directory under `agent/submissions/<your-handle>/` and add `agent.py`.
Your agent must subclass `BaseAgent` from `agent.base`:

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
python gitminer.py cache
```
Clones all pool repos once into `~/.cache/gitminer/repos/`. Subsequent `--no-sandbox`
evals use git worktrees instead of cloning, cutting a 30-problem run from ~20 min to
a few minutes. Set `GITMINER_CACHE=/path/to/dir` to override the cache location.

**With Docker sandbox (same as CI):**
```bash
python gitminer.py eval agent/submissions/<your-handle>/agent.py
```

**Without Docker (faster, less isolated — development only):**
```bash
python gitminer.py eval agent/submissions/<your-handle>/agent.py --no-sandbox
```

**Subset of problems:**
```bash
python gitminer.py eval agent/submissions/<your-handle>/agent.py --problems 930,986,1033
```

**Save results to a file:**
```bash
python gitminer.py eval agent/submissions/<your-handle>/agent.py --output results.json
```

**Validate a single patch applies cleanly (quick sanity check):**
```bash
python gitminer.py validate --problem 0463 --patch my_fix.diff
python gitminer.py validate --problem 0463 --patch my_fix.diff --run-tests
```
Applies the diff to the problem's base commit and shows the diff stat. `--run-tests`
also runs the problem's test command locally (requires deps installed in your environment).
Useful for verifying a generated patch before running a full eval.

Scores are on the 0–30 scale matching Gittensor's native formula. The leaderboard
shows the current champion's score — that's the number to beat.

## Commit-reveal flow

Public PRs are visible to everyone, so we use a two-phase process to prevent copying.

### Phase 1 — hash commit (when you open the PR)

Generate a hash of your agent source and a private salt:

```python
import hashlib, secrets

salt = secrets.token_hex(16)           # keep this — you need it for phase 2
source = open("agent/submissions/<your-handle>/agent.py").read()
h = hashlib.sha256((source + salt).encode()).hexdigest()
print(f"reveal-hash: {h}")
print(f"salt (private): {salt}")
```

Paste `reveal-hash: <hash>` into your PR description. Do **not** share the salt yet.

### Phase 2 — reveal (after scoring)

Once CI posts your score, share the salt in the PR so anyone can verify:

```python
import hashlib
source = open("agent/submissions/<your-handle>/agent.py").read()
assert hashlib.sha256((source + "<your-salt>").encode()).hexdigest() == "<your-hash>"
```

The reveal must happen within **7 days** of the score being posted.

You can also use `gitminer hash` to generate the SHA-256 hash of your agent file before submitting:

```bash
python gitminer.py hash agent/submissions/<your-handle>/agent.py
```

## PR format

Use the PR template. Fill in every section:

- `reveal-hash:` — your phase-1 hash (required)
- `Score on local eval:` — your best local score (no sandbox is fine)
- `Model used:` — exact model ID from the whitelist
- `Approach:` — a sentence or two on what makes your scaffolding better

A minimal PR that beats the leader on the full 30-problem suite with a clean hash
and a brief explanation is all that's needed.

## After you open the PR

CI automatically runs the full benchmark in Docker and posts a score table as a
comment. If the score is a new leaderboard high, maintainers merge the PR.
The `record_submission` workflow then re-scores your agent, updates the leaderboard
and SOTA history, and promotes your agent to `agent/champion/` automatically.
You don't need to do anything else — the [live dashboard](https://punchthedev.github.io/gittensor-miner-dashboard/)
reflects the updated standings within minutes of the merge.

## Adding benchmark problems

To propose a new problem (a real Gittensor issue with a merged PR and tests), open
an issue using the `Problem Proposal` template. Maintainers review it against the
curation criteria in `docs/scoring.md` and add it if it qualifies.

## Code standards

- Keep your submission self-contained under `agent/submissions/<your-handle>/`.
- A `requirements.txt` inside your directory is fine for extra dependencies.
- No shell scripts that bypass the `BaseAgent` interface.
- `solve()` must be deterministic enough to re-run — avoid non-seeded randomness.
