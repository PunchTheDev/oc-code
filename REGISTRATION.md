# Launch Checklist

Everything the operator needs to do to register this repo on Gittensor and go live. All code is ready. These are the remaining human-side steps.

---

## 1. GitHub Secrets (benchmark repo)

Go to: `https://github.com/PunchTheDev/gittensor-base-miner/settings/secrets/actions`

Add two repository secrets:

| Secret | Value | Purpose |
|--------|-------|---------|
| `OPENROUTER_KEY` | OpenRouter API key | CI eval runs the example agent via OpenRouter |
| `DASHBOARD_DEPLOY_TOKEN` | PAT with `repo` scope on `gittensor-miner-dashboard` | CI pushes updated `data.json` to dashboard repo after each merged submission |

**Creating the PAT**: GitHub → Settings → Developer settings → Personal access tokens → Fine-grained → `gittensor-miner-dashboard` → Contents: read+write.

---

## 2. Confirm frozen model

Default: `anthropic/claude-3-5-haiku` via OpenRouter.

This is set in `benchmark/harness/allowed_models.txt`. If you want a different model (or multiple), update the file and tell Punch. The model choice affects the benchmark — it should be cheap enough for miners to run many eval rounds, capable enough to get non-trivial scores.

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
| Add `OPENROUTER_KEY` secret | Operator | Pending |
| Add `DASHBOARD_DEPLOY_TOKEN` secret | Operator | Pending |
| Confirm frozen model | Operator | Pending |
| Gittensor registration + approval | Operator | Pending |
| Trigger test workflow run after secrets | Operator | Pending |
| Announce | Operator | After approval |

All code, docs, and CI are complete. The benchmark has 325 problems across 20 repos, a live dashboard, and a fully audited CI pipeline. It is ready to go live.
