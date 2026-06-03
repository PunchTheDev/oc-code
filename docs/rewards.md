# Reward Mechanism

How a base miner submission earns TAO on Gittensor subnet 74.

## The chain: score → label → emissions → TAO

```
Eval score (0–30)
    ↓ CI labels your PR
Marginal-gain formula
    (score + max(0, score - sota) × 3.0) × label_multiplier × time_decay
    ↓
Weighted emission for your PR
    ↓ repo emission share (2%) × contributor cut (55%)
Your share of block rewards
    ↓ converted at market rate
TAO
```

## Scoring

Each eval run tests your agent against the current **30-problem weekly shard** drawn from the 1123-problem pool. Problems come from real, merged PRs across Gittensor network repos and external prestige repos — each problem is an issue your agent must fix.

**Three metrics per problem:**
- `final_score` (0–30): Gittensor's native AST quality formula — rewards structured, meaningful code changes.
- `relative_score` (0–2.0): `agent_score / oracle_score` for this specific problem. 1.0 = matches accepted solution quality, >1.0 = beats it.
- `file_coverage` (0–1.0): fraction of the reference diff's source files the agent also touches (observational, not in score).

**Correctness gates everything.** Tests must pass or the problem scores 0.

**Benchmark score** = `mean_relative_score` across all 30 shard problems. This is the primary ranking metric — it normalizes every problem equally regardless of how large or small the accepted fix was.

**oracle baseline** = 1.0 (by definition) — the accepted reference diffs score exactly 1.0. Any agent scoring above 1.0 on average has produced higher-quality fixes than the original maintainers.

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
| Contributor | 55% | Split among scored PRs by weighted score |
| Maintainer | 15% | Reserved for repo maintenance |

### Marginal-gain formula

Rewards are **marginal**: a submission earns disproportionately more for advancing the benchmark than for matching or copying the leader.

```
marginal_gain    = max(0, score - sota_at_submission_time)
base_weight      = score × 1.0          # participation term — every passing submission
champion_bonus   = marginal_gain × 3.0  # champion term — earned only when you beat SOTA

contribution_weight = (base_weight + champion_bonus) × label_multiplier × time_decay(merged_at)
```

**Examples** (assuming current SOTA = 18.0, `agent-improvement` label = 2.0×, no time decay):

| Score | Marginal gain | base_weight | champion_bonus | raw weight | After 2.0× |
|-------|--------------|-------------|----------------|------------|-------------|
| 21.0 (new record) | 3.0 | 21.0 | 9.0 | 30.0 | **60.0** |
| 18.0 (exact copy) | 0.0 | 18.0 | 0.0 | 18.0 | 36.0 |
| 15.0 (below SOTA) | 0.0 | 15.0 | 0.0 | 15.0 | 30.0 |

A copycat that resubmits the leader's agent at score 18.0 earns 36 weight units. The new champion who pushed to 21.0 earns 60 — **67% more** despite a score only 17% higher. Every additional point above the bar earns the champion_bonus premium on that increment.

Your share of the contributor pool = `contribution_weight / sum(all contributor weights)` for the current scoring window (45-day lookback).

### Time decay

Merged PRs decay in value over time using a sigmoid:
- Grace period: 24 hours at full value (1.0×)
- Midpoint: 14 days → ~0.5×
- Floor: ~0.08× beyond 30 days

**Implication**: beating the champion early in the scoring window earns more than an identical score submitted late.

### Open PR threshold

Each miner gets a base threshold of 3 open PRs. Going over the threshold zeros your score for new PRs until some are closed. Top contributors earn a higher threshold: `+1 for every 250 token score`, up to a maximum of 15.

## Eligibility

To earn on this repo, a miner account must:
- Have ≥ 2 valid merged PRs on the Gittensor network
- Maintain credibility score ≥ 0.75
- Not exceed the open PR threshold

## Maximizing earnings

1. **Beat the oracle (12.64)**. Submissions above this score are rarer and earn the top of the contributor pool.
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
  "issue_discovery_share": 0.3,
  "maintainer_cut": 0.15,
  "trusted_label_pipeline": true,
  "default_label_multiplier": 0.0,
  "label_multipliers": {
    "benchmark-problem": 2.5,
    "harness": 2.0,
    "agent-improvement": 2.0,
    "bug": 1.5,
    "refactor": 0.75,
    "docs": 0.5
  },
  "eligibility": {
    "min_valid_merged_prs": 2,
    "min_credibility": 0.75,
    "excessive_pr_penalty_base_threshold": 3,
    "open_pr_threshold_token_score": 250.0,
    "max_open_pr_threshold": 15
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
