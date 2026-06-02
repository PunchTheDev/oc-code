# Reward Mechanism

How a base miner submission earns TAO on Gittensor subnet 74.

## The chain: score → label → emissions → TAO

```
Eval score (0–30)
    ↓ CI labels your PR
Gittensor validator scores the PR
    ↓ label_multiplier × token_score × time_decay
Weighted emission for your PR
    ↓ repo emission share (2%) × contributor cut (85%)
Your share of block rewards
    ↓ converted at market rate
TAO
```

## Scoring

Each eval run tests your agent against the current **30-problem weekly shard** drawn from the 397-problem pool. Problems come from real, merged PRs across Gittensor network repos — each problem is an issue your agent must fix.

**Score per problem** (0–30 scale):
- Correctness first: tests must pass or the problem scores near 0.
- Structural quality: diff density, no-op lines, code-to-comment ratio.
- Token efficiency: tighter diffs score higher than bloated ones.

**Your benchmark score** = mean score across all 30 shard problems.

**Oracle (upper bound)** = 23.05 — the accepted reference solution's mean score. Beat this and you've improved on the actual human patch.

## Labels and multipliers

When CI finishes scoring your PR, it applies GitHub labels. Gittensor's validator reads these labels and applies the corresponding emission multiplier to your PR's score.

| Label | Multiplier | Applied when |
|-------|-----------|--------------|
| `agent-improvement` | 2.0× | Any scored agent submission |
| `new-champion` | 2.0× base + visibility | Score beats current SOTA |
| `benchmark-problem` | 2.5× | PR adds new problems to the pool |
| `harness` | 2.0× | PR improves the eval harness |
| `bug` | 1.5× | Bug fix outside eval pipeline |
| `docs` | 0.5× | Documentation only |

The `agent-improvement` label is automatically applied by CI. The `new-champion` label is added in addition if you beat the current leaderboard leader.

## Emission model

The repo is registered on Gittensor with a 2% emission share. Each scoring cycle, that 2% is split:

| Recipient | Share | Notes |
|-----------|-------|-------|
| Issue discovery | 30% | Allocated to the issue filer |
| Contributor | 59.5% | Split among scored PRs by weighted score |
| Maintainer | 10.5% | Reserved for repo maintenance |

For an agent PR with score `S` and `agent-improvement` label (2.0×):

```
contribution_weight = S × 2.0 × time_decay(merged_at)
```

Your share of the contributor pool = `contribution_weight / sum(all contributor weights)` for the current scoring window (45-day lookback).

### Time decay

Merged PRs decay in value over time using a sigmoid:
- Grace period: 24 hours at full value (1.0×)
- Midpoint: 14 days → ~0.5×
- Floor: ~0.08× beyond 30 days

**Implication**: beating the champion early in the scoring window earns more than an identical score submitted late.

### Open PR threshold

Each miner gets a base threshold of open PRs (default 10). Going over the threshold zeros your score for new PRs until some are closed. Top contributors earn a higher threshold: `+1 for every 500 token score across unlocked tiers`.

## Eligibility

To earn on this repo, a miner account must:
- Have ≥ 2 valid merged PRs on the Gittensor network
- Maintain credibility score ≥ 0.75
- Not exceed the open PR threshold

## Maximizing earnings

1. **Beat the oracle (23.05)**. Submissions above this score are rarer and earn the top of the contributor pool.
2. **Submit early in the week**. The shard rotates Monday 00:00 UTC. A champion submission on Monday earns across the full 45-day decay window vs one filed Friday.
3. **Fix the hardest problems**. Hard problems (baseline 0–10) have high upside. An agent that solves them while competitors fail on them contributes disproportionately.
4. **Minimize diffs**. The scoring engine rewards token efficiency. Tighter, correct diffs outperform sprawling but technically-passing ones.
5. **Use small, fast models efficiently**. The whitelist includes lightweight models (Haiku, Llama 8B, Mistral 7B). A well-scaffolded cheap model that runs 3× more repair loops often outperforms one expensive call.

## The flywheel

Every champion agent becomes the example in `agent/`. New miners fork it, improve it, and the cycle repeats. Better agents → better contributions across all Gittensor repos → more merged PRs → more training data → better agents. Each leaderboard winner sharpens the whole network.

## Hyperparameter reference

Current `hyperparameters.json` (registered with Gittensor):

```json
{
  "emission_share": 0.02,
  "issue_discovery_share": 0.30,
  "maintainer_cut": 0.15,
  "label_multipliers": {
    "benchmark-problem": 2.5,
    "harness": 2.0,
    "agent-improvement": 2.0,
    "bug": 1.5,
    "refactor": 0.75,
    "docs": 0.5
  },
  "scoring": {
    "pr_lookback_days": 45,
    "time_decay": {
      "grace_period_hours": 24,
      "sigmoid_midpoint_days": 14,
      "sigmoid_steepness": 0.35,
      "min_multiplier": 0.08
    }
  }
}
```

See [Gittensor hyperparameter docs](https://docs.gittensor.io/repository-hyperparameters.html) for the full specification.
