# Anti-Gaming Threat Model

**Implementation status**: each mitigation is marked with its current state:

- **Implemented** — code exists and is enforced
- **Planned** — described in design docs, not yet in CI
- **Gittensor-native** — handled by the DAS validator, not our CI

---

## Threat 1: Copying the current champion's source code

**Attack**: Miner reads the champion agent's code in `agent/champion/` and submits it with minor cosmetic edits.

**Mitigations**:
- **Similarity check — [Implemented, hard-blocking]**: `scripts/check_similarity.py` compares the incoming agent against all existing submissions using AST structural fingerprints + token Jaccard. Exceeding 85% similarity on either signal fails the CI job and blocks merge.
- **Marginal reward — [Gittensor-native]**: Rewards are proportional to margin over the current leader. A copy that earns the same score earns ~0 marginal reward.
- **Commit-reveal — [Planned]**: Miner submits a hash before the private eval. The source is not visible until after scoring. *Not yet implemented — current flow posts results publicly on PR open.*
- **First-to-commit credit — [Planned]**: In a tie, the earlier submission wins. *Not tracked in CI yet.*

**Residual risk**: Low for direct code copies (hard-blocked). Medium for functionally identical agents with different structure (caught by output similarity check).

---

## Threat 2: Hardcoding reference diffs (oracle-level cheating)

**Attack**: Miner clones the repo, reads `benchmark/problems/{id}/reference.diff` for all pool problems, and builds an agent that returns the stored reference diff for each problem ID it recognizes.

**Why this is the most dangerous attack**: It scores oracle-level without any real reasoning. All reference diffs are public in the repo, making this trivially executable.

**Mitigations**:
- **Reference copy check — [Implemented, hard-blocking]**: `scripts/check_reference_copy.py` hashes each reference diff using the same normalization as the scoring engine and compares against the agent's behavior fingerprint. If >40% of shard problems match the reference exactly, the CI job fails and blocks merge.
- **Unpredictable shard — [Implemented]**: The shard is selected using a `SHARD_SECRET` GitHub Actions secret. Miners can't predict which 30/1114 problems are evaluated — pre-computing all 1000 still yields no guarantee.
- **Time segmentation — [Implemented]**: New problems are continuously added from recently merged PRs. A hardcoded solution for today's pool becomes stale as the pool grows.

**Residual risk**: Medium. A miner who applies the reference diffs with minor modifications (comment changes, whitespace) might fall just below the 40% detection threshold. The unpredictable shard provides a second defense layer.

---

## Threat 3: Overfitting to known pool problems (without reference diffs)

**Attack**: Miner trains or fine-tunes on the 980 known benchmark problems to produce high-scoring patches without reasoning at runtime.

**Mitigations**:
- **Unpredictable shard — [Implemented]**: Only 30/1114 problems are evaluated, selected via SHARD_SECRET. Pre-fitting to all 1114 is expensive without any shard guarantee.
- **Time segmentation — [Implemented]**: Problems come from PRs merged after 2024-06-01. Pool rotates as new PRs merge, continuously adding problems the model hasn't seen.
- **Reference copy check — [Implemented]**: Catches near-verbatim memorization of the accepted solutions.

**Residual risk**: Medium for a very well-resourced miner. Mitigated primarily by pool growth — the more problems, the harder and more expensive to overfit.

---

## Threat 4: Using a non-whitelisted frontier model

**Attack**: Miner uses a frontier model (e.g., a non-whitelisted Claude or GPT variant) to get higher scores. The whitelist allows only specific models.

**Mitigations**:
- **Daytona sandbox network control — [Planned]**: During evaluation, only whitelisted model API endpoints would be reachable. *Not yet implemented — agent currently runs with full network access. Daytona integration is a backlog item.*
- **Allowed models list — [Interface only, not enforced]**: `allowed_models` is passed to `Problem`, but runtime enforcement requires network sandboxing.

**Residual risk**: High until Daytona (or equivalent) is integrated. Currently, any model can be called during eval. This is a known gap — the whitelist exists but has no runtime enforcement.

*This is a scale-readiness gap. Priority: high.*

---

## Threat 5: Sybil submissions

**Attack**: Miner creates multiple GitHub identities and submits essentially the same agent from each handle to accumulate leaderboard positions.

**Mitigations**:
- **Output behavior similarity — [Implemented, hard-blocking]**: `scripts/check_output_similarity.py` compares per-problem diff hashes across all submitted agents. If ≥70% of overlapping problems produce identical diffs, the CI job fails and blocks merge.
- **Gittensor credibility gate — [Gittensor-native]**: Each submitter needs ≥2 merged PRs and ≥75% credibility. Building multiple credible identities is expensive.

**Residual risk**: Low. Building multiple credible Gittensor identities requires real contribution work.

---

## Threat 6: LLM variance gaming (lucky-run exploitation)

**Attack**: Miner submits many times, exploiting non-determinism in model outputs to get a lucky high score.

**Mitigations**:
- **Rate limiting — [Implemented, advisory]**: `scripts/check_rate_limit.py` caps merges at 5/week. Currently advisory (logged, not hard-blocking) to avoid false-positive impact on legitimate resubmissions.
- **Deterministic eval seeds — [Implemented]**: The harness seeds the shard selection with `SHARD_SECRET + week_number`. Same agent, same week → same 30 problems.

**Residual risk**: Low. Deterministic seeds mean LLM randomness is the only remaining variance, and repeated submissions hit the rate limit.

---

## Threat 7: Behavioral cloning (output forwarding)

**Attack**: Miner writes an agent that calls a prior submission's API or uses a different code structure to produce the same output. Source-level similarity misses this.

**Mitigations**:
- **Output behavior fingerprinting — [Implemented, hard-blocking]**: `scripts/check_output_similarity.py` compares per-problem diff hashes. ≥70% identical diffs on ≥5 shared problems fails the CI job.
- **Reference copy check — [Implemented]**: Also catches agents forwarding the accepted solution's diff.

**Residual risk**: A miner who deliberately varies outputs problem-by-problem while using the same agent stays below the threshold. Rate limiting constrains calibration runs.

---

## Threat 8: CI flooding (resource exhaustion)

**Attack**: Miner pushes many PR updates rapidly to exhaust shared GitHub Actions minutes and the shared OPENROUTER_KEY budget.

**Mitigations**:
- **Per-actor CI concurrency — [Implemented]**: `eval.yml` limits each GitHub actor to one active eval run. New pushes cancel the in-flight eval.
- **Rate limiting — [Implemented, advisory]**: 5 merges/week cap per handle.

**Residual risk**: Medium. The shared OPENROUTER_KEY is a scale bottleneck — at 100+ concurrent miners, each using the CI key, budget burn is uncontrolled. *Planned fix: miners provide their own OpenRouter key, stored as a per-handle GitHub secret or submitted alongside the agent.*

---

## Threat 9: Static agent (no LLM, pre-computed answers)

**Attack**: Miner submits a `solve()` implementation that contains pre-computed diffs hardcoded by problem ID, or uses a lookup table rather than calling an LLM. The meta.json SHA check verifies the submitted code is what they claimed, but does not verify the code calls an LLM.

**Why this matters**: This is harder to detect than reference diff copying because the pre-computed answers may have been independently generated (e.g., by an LLM offline) rather than copied verbatim from `reference.diff`. A static lookup agent can score high without reasoning at runtime.

**Mitigations**:
- **Reference copy check — [Implemented]**: Catches pre-computed diffs identical to stored reference diffs.
- **Output behavior similarity — [Implemented]**: Catches static agents that produce the same outputs as a prior agent.
- **Meta.json model check — [Implemented, partial]**: Verifies the declared model is whitelisted, but does not verify the model was called. A static agent can declare `claude-3-5-haiku` in meta.json without using it.
- **Network monitoring — [Planned]**: Daytona integration would restrict outbound network to the whitelisted model API only, and could verify at least one API call was made per problem.

**Residual risk**: High until Daytona is integrated. A miner who pre-computes diffs with a good LLM offline and hard-codes them is undetectable without runtime network monitoring.

**Probe result**: Verified 2026-06-03 — a simulated oracle-copy agent (returning exact reference diffs) was correctly blocked by `check_reference_copy.py` (100.0% match rate, exit 1). A static agent returning pre-computed non-verbatim diffs would currently pass.

---

## Summary

| Threat | Severity | Implemented mitigations | Gaps |
|--------|----------|-------------------------|------|
| Champion code copy | High | Similarity check (hard-block) | Commit-reveal not yet live |
| Reference diff hardcoding | High | Reference copy check (hard-block) | Minor-modification evasion |
| Pool overfitting | Medium | Secret shard + time segmentation | Resource-heavy miners can pre-compute |
| Frontier model use | High | Allowed models list | **No runtime enforcement — Daytona needed** |
| Sybil submissions | Low | Output similarity (hard-block) + credibility gate | — |
| LLM variance gaming | Low | Deterministic seeds + rate limit | — |
| Behavioral cloning | Medium | Output fingerprint (hard-block) | Partial match evasion |
| CI flooding | Medium | Concurrency limit + rate limit | Shared API key at scale |
| Static agent (no LLM) | High | Reference copy check, output similarity | **No runtime LLM call verification — Daytona needed** |

### Critical gaps for launch readiness

1. **Frontier model enforcement + static agent detection**: No network sandboxing. Daytona integration required to restrict agent network access to whitelisted models only and verify at least one model API call was made per problem.
2. **Shared OPENROUTER_KEY**: All CI evals use the same key. Fine for 10 miners; dangerous at 100+. Fix: per-miner key registration.
3. **Commit-reveal**: Currently, scores are posted publicly as soon as eval runs. A miner who watches eval results can update their submission to exploit the visible benchmark. Private eval (hash-first) requires a two-phase PR flow.
