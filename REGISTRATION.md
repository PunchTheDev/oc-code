# Launch Checklist

Everything the operator needs to do to register this repo on Gittensor and go live. All code is ready. These are the remaining human-side steps.

---

## 1. GitHub Secrets (benchmark repo)

**Status:** `SHARD_SECRET` and `DASHBOARD_DEPLOY_TOKEN` are already set as repository secrets (set by Punch). `OPENROUTER_KEY` is set in the "Github Actions Environment" — the CI workflows now reference that environment, so it will be available automatically.

Only remaining secret: confirm `OPENROUTER_KEY` in the "Github Actions Environment" is the correct production key.

Go to: `https://github.com/PunchTheDev/gittensor-base-miner/settings/environments/16104198406/edit`

| Secret | Status | Notes |
|--------|--------|-------|
| `OPENROUTER_KEY` | Set (environment) | Verify this is your production OpenRouter key |
| `DASHBOARD_DEPLOY_TOKEN` | Set (repo) | Uses current gh auth token — rotate if needed |
| `SHARD_SECRET` | Set (repo) | Random 32-byte hex, set by Punch |

---

## 2. Frozen model

**Updated per operator preference:** default model is now `deepseek/deepseek-chat` via OpenRouter (much cheaper than claude-haiku; good at code tasks).

Full allowed list is in `benchmark/harness/allowed_models.txt`. Miners can use any whitelisted model — the point is that scaffolding wins, not raw model power.

---

## 3. Gittensor registration

1. Read the registration docs: https://docs.gittensor.io/register-repository.html
2. Submit the repo: `https://github.com/PunchTheDev/gittensor-base-miner`
3. When prompted, the hyperparameter config is at `hyperparameters.json` in the repo root. You can paste it directly or reference the file.
4. Wait for team approval. Once approved, confirm with Punch so the Discord milestone post can go out.

---

## 4. Verify CI is working post-secrets

After adding secrets, open a test PR (or manually trigger workflows):

```bash
# Trigger the dashboard refresh manually to confirm DASHBOARD_DEPLOY_TOKEN works
gh workflow run refresh_dashboard.yml --repo PunchTheDev/gittensor-base-miner
```

Check: https://punchthedev.github.io/gittensor-miner-dashboard/ updates within a few minutes.

The eval workflow (`eval.yml`) fires automatically on PRs. Once a miner opens a PR, the CI comment should appear with a score out of 30.

---

## 5. Announce

Once registered and CI is live:
- Post in the Gittensor Discord / relevant channels with the repo link and a brief description of the benchmark
- The README and CONTRIBUTING.md are ready for public eyes; no further doc work needed

---

## Summary

| Step | Who | Status |
|------|-----|--------|
| `OPENROUTER_KEY` (environment) | Operator | Verify existing key is correct |
| `DASHBOARD_DEPLOY_TOKEN` (repo) | Punch | Done |
| `SHARD_SECRET` (repo) | Punch | Done |
| Frozen model set to deepseek/deepseek-chat | Punch | Done |
| Gittensor registration + approval | Operator | Pending |
| Trigger test workflow run | Operator | After verifying OPENROUTER_KEY |
| Announce | Operator | After approval |

All code, docs, and CI are complete. The benchmark has 1114 problems across 43 repos (13 DAS + 30 external), a live dashboard, and a fully audited CI pipeline.
