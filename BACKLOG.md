# Backlog

Ordered by priority. Punch grooms this continuously.
Items move here from STATE.md when they become long-term improvement opportunities.

---

## Operator Actions (blocking registration)

- [x] Add `OPENROUTER_KEY` GitHub Actions secret — set as environment secret in "Github Actions Environment"
- [x] Add `DASHBOARD_DEPLOY_TOKEN` GitHub Actions secret — set automatically via gh auth token
- [x] Add `SHARD_SECRET` GitHub Actions secret — set automatically (random 32-byte hex)
- [x] Confirm frozen model preference — `deepseek/deepseek-chat` (operator confirmed)
- [ ] Verify `OPENROUTER_KEY` value in "Github Actions Environment" is the correct production key
- [ ] Submit repo for Gittensor registration and wait for team approval

See `REGISTRATION.md` for the full step-by-step checklist.

---

## Post-Registration Improvements

### Pool Quality
- [x] Multi-language Docker runner: Phase 1 now uses language-specific images (node:20-slim, rust:1.82-slim, eclipse-temurin:21-jdk-jammy) so npm/cargo/gradlew tests actually run (commit ea5efe2) — fixes 44% of previously un-runnable problems
- [ ] Issue template: "Nominate a problem" — let community suggest PRs for pool curation
- [x] Reference-diff baseline: `scripts/baseline_scores.py` scores all 325 reference diffs, stores `results/baselines.json` (mean 22.79, median 26.34)

### Scoring Calibration
- [ ] Calibrate 0–30 local scores against Gittensor validator outputs once we have live validator access
- [ ] Daytona integration: evaluate ephemeral workspaces per problem as an alternative to GitHub Actions runners

### Dashboard
- [ ] Per-problem diff viewer: agent patch vs accepted diff side-by-side, tests passed/failed breakdown
- [ ] Submission status page: hash registered → eval running → scored (requires lightweight backend or polling)
- [ ] One-click "reproduce" button: runs harness against champion agent for a specific problem

### Anti-Gaming (hardening)
- [x] Patch similarity check: token Jaccard + AST structural fingerprint in eval CI (`scripts/check_similarity.py`, commits cafaec0, 92a18f8)
- [x] Rate limiting: max 5 submissions per handle per 7-day window in `eval.yml` (`scripts/check_rate_limit.py`, non-blocking flag)

### Hyperparameters
- [ ] Map `issue_discovery_share` to pool curation reward mechanics once registration is approved
- [ ] Re-tune maintainer/contributor split after first wave of miner submissions lands
