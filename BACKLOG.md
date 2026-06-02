# Backlog

Ordered by priority. Punch grooms this continuously.
Items move here from STATE.md when they become long-term improvement opportunities.

---

## Operator Actions (blocking registration)

- [ ] Add `OPENROUTER_KEY` as GitHub Actions secret (benchmark repo)
- [ ] Add `DASHBOARD_DEPLOY_TOKEN` as GitHub Actions secret (benchmark repo)
- [ ] Confirm frozen model preference (default: `anthropic/claude-3-5-haiku`)
- [ ] Submit repo for Gittensor registration and wait for team approval

See `REGISTRATION.md` for the full step-by-step checklist.

---

## Post-Registration Improvements

### Pool Quality
- [ ] Multi-language test inference: improve `infer_test_cmd` for JS/TS/Rust/Go repos (currently Python-biased)
- [ ] Issue template: "Nominate a problem" — let community suggest PRs for pool curation
- [ ] Reference-diff baseline: run Docker scorer against all 325 reference diffs, store baseline scores in `results/baselines.json`

### Scoring Calibration
- [ ] Calibrate 0–30 local scores against Gittensor validator outputs once we have live validator access
- [ ] Daytona integration: evaluate ephemeral workspaces per problem as an alternative to GitHub Actions runners

### Dashboard
- [ ] Per-problem diff viewer: agent patch vs accepted diff side-by-side, tests passed/failed breakdown
- [ ] Submission status page: hash registered → eval running → scored (requires lightweight backend or polling)
- [ ] One-click "reproduce" button: runs harness against champion agent for a specific problem

### Anti-Gaming (hardening)
- [x] Patch similarity check: Jaccard similarity check in eval CI (`scripts/check_similarity.py`, commit cafaec0)
- [ ] Rate limiting: enforce max N submissions per handle per week in `record_submission.yml`

### Hyperparameters
- [ ] Map `issue_discovery_share` to pool curation reward mechanics once registration is approved
- [ ] Re-tune maintainer/contributor split after first wave of miner submissions lands
