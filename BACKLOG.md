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
- [ ] `/scoring`, `/problems`, `/leaderboard`, `/mining` 404 when pasted into browser or refreshed
- **Fix**: replace `python3 -m http.server` with a SPA-aware server that returns `index.html` for all unknown paths
- **Pillar**: Seamless (shareable URLs), Understandable (first-timer pasting a link gets a broken page)

### Oracle — three different definitions on one site
- [ ] Hero says `Oracle 12.64/30`; stat card says `12.64 — beat 1.0 to win`; Scoring page says `Oracle = 1.0`; sample problems say `oracle 25.6/30`
- **Fix**: ONE coherent story: per-problem scores are raw 0–30; the pool-level target is `weighted_benchmark_score = 1.0`. Remove `12.64/30` from hero and stat card. Let "oracle" always mean the normalized 1.0 target.
- **Pillar**: Seamless (same number everywhere), Understandable (what do I need to beat?)

### relative_score — gameable metric not defended
- [ ] Metric description says "AST-node count" = code quality. More AST nodes can mean more bloat. Trivially gameable.
- **Fix**: Audit whether tree-sitter weighted AST is actually correlated with quality. If yes, surface the weighting detail; if not, replace with judge pass / hidden test correctness signal.
- **Pillar**: Understandable (does this metric mean what it says?), Seamless (can't have a metric we can't defend)

### Champion code — not surfaced on Leaderboard
- [ ] Leaderboard shows handle + score but NOT the agent code that achieved SOTA
- **Fix**: Add "View code ↗" link to champion's agent source (GitHub PR or repo path). Flywheel: winner's code gets open-sourced so the next person forks and beats it by a decaying margin.
- **Pillar**: Understandable (why is this the best?), Beautiful (the flywheel story lands visually)

### Swagger — API docs are a static HTML table
- [ ] The "For Agents" section is a hand-rolled table. No try-it, no schema, no versioning.
- **Fix**: Serve Swagger UI from `/api/docs` or `/docs` via the API server. OpenAPI spec already partially exists in `server.py`.
- **Pillar**: Beautiful, Seamless (API is self-describing), Understandable (agents can explore endpoints live)

### Start Mining — not a true one-copy-paste on-ramp
- [ ] Current page is multi-step but doesn't hand the agent the full ruleset or tell it to RALPH-loop
- **Fix**: One code block that an agent can copy, paste, and run. Includes API key wiring, model config, eval loop, auto-commit on beat. Describe the RALPH loop explicitly.
- **Pillar**: Understandable (first-timer gets to running in < 5 min), Seamless (no gaps between steps)

### Scoring formula — wall of text
- [ ] The formula section is dense. A first-timer can't parse it in one glance.
- **Fix**: Lead with a visual (one-line formula in large mono font), then expand each factor below it. The interactive calculator is good — move it above the details table.
- **Pillar**: Beautiful (visual hierarchy), Understandable (formula first, details second)

---

## Dashboard — Per-page Component Audit (3-pillar teardown)

Each row: page → component → pillar violations → fix.

### Home
- [ ] **Hero oracle stat** — `Oracle 12.64/30`: confusing (see oracle section above)
- [ ] **Sample Problems**: cards don't explain what "oracle 25.6/30" means in context. Add 1-line caption: "This problem's max raw score"
- [ ] **Language Distribution**: bars have no label explaining what "% of pool" means to a first-timer — add tooltip "N% of the 1123-problem benchmark is Python"
- [ ] **"Ready to Mine?" CTA**: button copy is generic — make it specific: "Clone the repo and run your first eval →"

### Problems
- [ ] **Filter chips**: do users know they can multi-filter? No affordance. Add "Showing X of 1123" count always visible.
- [ ] **Oracle score column**: "oracle 12.6/30" per problem — is this the per-problem benchmark_score for the reference diff? Make that explicit in column header tooltip.
- [ ] **Difficulty badge**: "Hard/Medium/Easy" — not explained anywhere on the page. Add tooltip: "Hard = 2× weight in your final score".
- [ ] **Mini score bars**: green/yellow/red — legend missing. Add a 3-cell legend below the table header.

### Leaderboard
- [ ] **SOTA chart**: x-axis dates have no label; y-axis "score" needs unit — "weighted_benchmark_score (oracle=1.0)"
- [ ] **Champion agent code**: not shown — fix per Critical section above
- [ ] **⚠ old shard badge**: tooltip explains it but badge itself is cryptic — change to "from prev pool rotation"
- [ ] **Benchmark column tooltip**: text is verbose and uses jargon. Simplify to "difficulty-weighted score; oracle = 1.0"
- [ ] **Per-agent sub-drawer**: shows per-problem scores — add visual bar, rank delta vs oracle per problem

### Scoring
- [ ] **Formula layout**: wall of text — fix per Critical section above
- [ ] **Score Calculator**: good, but placed below all the detail. Move it ABOVE the metric table.
- [ ] **Metric cards** (relative_score, anti_gaming, tqf, efficiency): each needs a 1-sentence plain-English "What this rewards" intro before the tech description.
- [ ] **Pool Composition bars**: repos without an explicit language tag fall through — verify all 47 repos have a color

### Start Mining
- [ ] **Quickstart steps**: step 3 ("run eval") shows a long command with no expected output. Add "You should see: benchmark_score: X.XX"
- [ ] **One-copy-paste block**: missing — fix per Critical section above
- [ ] **Model table**: no column explaining why these 5 models (not GPT-4o, not Claude). Add: "Competition is about agent scaffolding, not model budget. These 5 are cheap + on-par. Use OpenRouter."
- [ ] **"For Agents" API table**: static HTML — see Swagger fix above

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
