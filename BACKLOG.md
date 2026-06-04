# Backlog

Three pillars — every item below is evaluated against all three:
1. **Beautiful** — clean, intentional, nothing ugly or dumped.
2. **Seamless** — consistent terms and numbers everywhere; nothing contradicts anything else.
3. **Understandable instantly** — a first-timer gets it with zero explanation.

Ordered by priority. Punch grooms this every loop. Only mark ✅ when all 3 pillars pass.

---

## Operator Actions (blocking registration)

- [x] Add `OPENROUTER_KEY` GitHub Actions secret
- [x] Add `DASHBOARD_DEPLOY_TOKEN` GitHub Actions secret
- [x] Add `SHARD_SECRET` GitHub Actions secret
- [x] Confirm frozen model preference — `deepseek/deepseek-chat`
- [x] Verify `OPENROUTER_KEY` in "Github Actions Environment"
- [ ] Submit repo for Gittensor registration (team approval)

See `REGISTRATION.md` for the full checklist.

---

## Critical UX / Architecture (from operator review — message.txt)

### Routes — 404 on direct load (all pages)
- [x] `/scoring`, `/problems`, `/leaderboard`, `/mining` 404 when pasted into browser or refreshed
- **Fix**: replace `python3 -m http.server` with a SPA-aware server that returns `index.html` for all unknown paths
- **Pillar**: Seamless (shareable URLs), Understandable (first-timer pasting a link gets a broken page)

### Oracle — three different definitions on one site
- [x] Hero says `Oracle 12.64/30`; stat card says `12.64 — beat 1.0 to win`; Scoring page says `Oracle = 1.0`; sample problems say `oracle 25.6/30`
- **Fix**: ONE coherent story: per-problem scores are raw 0–30; the pool-level target is `weighted_benchmark_score = 1.0`. Remove `12.64/30` from hero and stat card. Let "oracle" always mean the normalized 1.0 target.
- **Pillar**: Seamless (same number everywhere), Understandable (what do I need to beat?)

### relative_score — gameable metric not defended
- [x] Metric description now explains weighted AST nodes (functions ×3, classes ×3, branches ×2) and that correctness gates first. "Penalizes bloated diffs that add unhelpful complexity." — metric is transparent and defended. Future: supplement with judge-pass signal (see Post-Registration > Scoring).
- **Pillar**: Understandable ✅ (now clearly explained), Seamless ✅ (consistent with formula)

### Champion code — not surfaced on Leaderboard
- [x] Leaderboard shows handle + score but NOT the agent code that achieved SOTA
- **Fix**: Add "View code ↗" link to champion's agent source (GitHub PR or repo path). Flywheel: winner's code gets open-sourced so the next person forks and beats it by a decaying margin.
- **Pillar**: Understandable (why is this the best?), Beautiful (the flywheel story lands visually)

### Swagger — API docs are a static HTML table
- [x] The "For Agents" section is a hand-rolled table. No try-it, no schema, no versioning.
- **Fix**: Serve Swagger UI from `/api/docs` or `/docs` via the API server. OpenAPI spec already partially exists in `server.py`.
- **Pillar**: Beautiful, Seamless (API is self-describing), Understandable (agents can explore endpoints live)

### Start Mining — not a true one-copy-paste on-ramp
- [x] Current page is multi-step but doesn't hand the agent the full ruleset or tell it to RALPH-loop
- **Fix**: One code block that an agent can copy, paste, and run. Includes API key wiring, model config, eval loop, auto-commit on beat. Describe the RALPH loop explicitly.
- **Pillar**: Understandable (first-timer gets to running in < 5 min), Seamless (no gaps between steps)

### Scoring formula — wall of text
- [x] The formula section is dense. A first-timer can't parse it in one glance.
- **Fix**: Lead with a visual (one-line formula in large mono font), then expand each factor below it. The interactive calculator is good — move it above the details table.
- **Pillar**: Beautiful (visual hierarchy), Understandable (formula first, details second)

---

## Dashboard — Per-page Component Audit (3-pillar teardown)

Each row: page → component → pillar violations → fix.

### Home
- [x] **Hero oracle stat** — `Oracle 12.64/30`: confusing — fixed to "Beat 1.0 to win" everywhere
- [x] **Sample Problems**: cards now show "oracle ref · X.X / 30" label with "oracle ref" prefix for clarity
- [x] **Language Distribution**: bars now have tooltip "N of M benchmark problems are Python — X% of the pool"
- [x] **"Ready to Mine?" CTA**: now reads "Clone the repo and run your first eval →"

### Problems
- [x] **Filter chips**: section count shows "X of N shown" when filtered — affordance visible
- [x] **Oracle score column**: column header tooltip explains "Accepted solution's raw benchmark_score (0–30). Higher = richer diff."
- [x] **Difficulty badge**: Tier column header tooltip explains "Scoring weight tier based on diff size: easy <30 lines (×1), medium 30–149 (×1.5), hard ≥150 (×2)"
- [x] **Mini score bars**: Ref/30 header now shows inline legend ■≥20 ■≥10 ■<10 with color coding

### Leaderboard
- [x] **SOTA chart**: x-axis now labeled "Submission date"; y-axis "weighted_benchmark_score (oracle = 1.0)"
- [x] **Champion agent code**: "code ↗" links shown when agent_code_url stored; oracle shows "example ↗"
- [x] **⚠ old shard badge**: now shows "⚠ prev pool" — clearer than "old shard"
- [x] **Benchmark column tooltip**: simplified to "PRIMARY: difficulty-weighted test_pass_rate × relative_quality. Oracle = 1.0. Scale 0–2.0."
- [x] **Per-agent sub-drawer**: score bar + Δ oracle inline (color-coded green/yellow/red vs 1.0 target)

### Scoring
- [x] **Formula layout**: formula-block first, then Score Calculator, then Factor Details — digestible order
- [x] **Score Calculator**: moved ABOVE the metric cards (now second section after formula)
- [x] **Metric cards**: each leads with a plain-English "Rewards: ..." or "Penalizes: ..." line (accent/red color)
- [x] **Pool Composition bars**: all 47 repos derive color from problem category (6 categories, all have colors defined). Verified via API stats: python/typescript/rust/jvm/go/ruby all present.

### Start Mining
- [x] **Quickstart steps**: step 3 now includes "Expect output: benchmark_score: X.XX"
- [x] **One-copy-paste block**: full bash block with RALPH-loop pattern in One-Copy-Paste Start section
- [x] **Model table**: info-box above grid explains "Competition is about scaffolding, not model budget. 5 cheap on-par OSS models. All via OpenRouter."
- [x] **"For Agents" API table**: Swagger UI at /docs live; link wired dynamically on Mining page

---

## Post-Registration Improvements

### Pool Quality
- [x] Multi-language Docker runner: language-specific images (node:20-slim, rust:1.82-slim, etc.)
- [x] Issue template: "Nominate a problem"
- [x] Reference-diff baseline: `results/baselines.json`
- [ ] Calibrate 0–30 scores against Gittensor validator outputs once we have live validator access
- [ ] Daytona integration: ephemeral workspaces per problem (needs credentials)

### Scoring
- [ ] Judge-pass correctness signal: run a lightweight LLM judge on agent output vs requirements (supplement AST relative_score)
- [ ] Hidden/edge test injection: add maintainer-only hidden tests per problem (reveal post-scoring)

### Anti-Gaming
- [x] Patch similarity check (token Jaccard + AST fingerprint)
- [x] Rate limiting (5 submissions / handle / 7-day window)
- [ ] Commit-reveal phase 2: private eval server (agent code hidden until after scoring)

### Hyperparameters
- [ ] Map `issue_discovery_share` to pool curation reward mechanics
- [ ] Re-tune maintainer/contributor split after first miner wave

### Infrastructure
- [ ] nginx hookup: apply `deploy/nginx-location.conf` (operator action)
- [ ] GitHub Actions Node.js 24 + results/agents/ fix — branch ready; operator needs `workflow` scope (deadline: 2026-06-16)
