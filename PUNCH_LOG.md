# Punch Log — Gittensor Base-Miner Flywheel

Milestone trail for the base-miner benchmark. Discord is the primary channel; this file is the audit trail.

---

## 2026-06-02 — Reference diff API endpoint + diff_stats (commit b58180d)

### API: `GET /api/problems/{id}/diff` (text/plain)

Added reference diff serving to the API. Miners studying the benchmark can now fetch the accepted solution directly:

```
GET /api/problems/0160/diff  →  unified diff (text/plain)
```

The `_problem_diff()` handler reads `benchmark/problems/{id}/reference.diff` and returns it as `text/plain; charset=utf-8`. New-file hunks, multi-file diffs, all diff content served verbatim.

### API + Dashboard: `diff_stats` field

Both `GET /api/problems/{id}` and `dashboard_data.json` problems now include:

```json
"diff_stats": {"add": 275, "remove": 14, "files": 4, "bytes": 15374}
```

Added `_diff_stats()` helper to `api/server.py` and `diff_stats_for()` to `scripts/generate_dashboard_data.py`. Dashboard data regenerated (430 problems, all with stats). Dashboard can now show `+N/-M across F files` on problem cards — visual difficulty signal without serving the full diff inline.

The `_problem()` endpoint response also includes `"diff_url": "/api/problems/{id}/diff"` so dashboard doesn't need to construct the URL.

---

## 2026-06-02 — Dashboard refresh + scoring transparency (dashboard commit f062012)

### Lando check-in response: scoring is fully deterministic

Addressed Lando's question about whether benchmarks use an LLM judge:

**No LLM at any point in the scoring pipeline.** Evaluation is:
1. `git apply` the patch to the repo at `base_commit`
2. Run the test suite — all tests must pass or score = 0
3. Gittensor's tree-sitter pipeline computes `src_tokens` from the diff
4. Formula: `25 × (1 − exp(−src_tokens / 58)) + bonus` → 0–30

This is now documented as a "How Scoring Works" section in the dashboard with the 4-step pipeline displayed visually — no ambiguity for miners about how they're being graded.

**Dashboard data refreshed**: 423 → 430 problems, oracle 23.36 → 23.46. Fixed stale "342" in meta description and step text. Generated fresh `data.json` from benchmark pool via `scripts/generate_dashboard_data.py`.

**Closed PR idea (Lando's suggestion)**: PRs rejected with explanation vs the actual merged solution would be gold standard negative examples. Valid idea but deferred to backlog — Gittensor is young, volume of clearly-explained closed PRs is likely small, and the current 430-problem pool is the immediate priority. Worth revisiting after first miner wave.

---

## 2026-06-02 — Marginal-gain mechanics + difficulty weighting (commits 882686f, 8963281, ca98c25, f8cb706)

### Core mechanics gap closed per Lando check-in

**Marginal-gain emission formula** (commit 882686f):

Lando flagged that "top score wins" proportional share wasn't the mechanic he wanted. Fixed:

```
contribution_weight = (score × 1.0 + max(0, score - sota_at_submission) × 3.0) × label_mult × time_decay
```

Every passing submission earns the participation term (1.0×). Beating SOTA earns the champion premium (3.0×) on each point above the bar. A copycat at exact SOTA earns only participation — the champion earns 67%+ more for the same score delta. `record_result.py` now captures `sota_at_submission`, `marginal_gain`, and `contribution_weight` per entry.

**Difficulty-weighted mean score** (commit 8963281):

Problems classified by reference diff size: Easy <30 lines (1.0×), Medium 30–149 (1.5×), Hard 150+ (2.0×). `evaluate.py` now computes and returns `weighted_mean_score` alongside `mean_score`. `record_result.py` stores `weighted_score` in leaderboard entries. Ranking sorts by weighted score first.

**Dashboard + CLI** (commits ca98c25, f8cb706):

- Leaderboard table: added Weighted Score and Marginal Gain columns
- Marginal gain shown in green when >0, muted when 0 (copy/no-improvement)
- Models section: added OpenRouter wiring snippet with `export OPENROUTER_KEY` and eval command
- `gitminer.py eval` CLI: now prints both Mean and Weighted Mean scores

### Status
- All mechanics now answer Lando's marginal-gain question
- Dashboard visible difference when first submissions arrive

---

## 2026-06-02 — _fix_hunk_offsets stripped-content fallback (commit eec6a88)

### Agent: context-line fingerprint now handles indentation mismatches

**Problem**: `_fix_hunk_offsets` used exact string matching to find context-line fingerprints in the source file. If the model wrote context lines with wrong indentation (e.g., 4 spaces instead of 1 tab), the fingerprint wouldn't match any source line. Offset correction silently failed. Then `_fix_context_lines` (stage 5) would fix the whitespace, but the `@@ -N` offset remained wrong — `git apply` still fails.

**Fix**: Two-pass search in `find_context_offset`:
1. Exact match (existing behavior)
2. Stripped-content fallback when exact finds zero matches — both sides stripped, same unambiguous-match guard

If the exact pass found multiple matches (ambiguous), the stripped fallback is skipped to avoid false positives. Empty-stripped fingerprints (blank lines) are also rejected. The stripped pass only triggers when exact fails cleanly — no risk of weakening the safety guard for well-formed diffs.

### Status
- Benchmark: 430 problems, oracle 23.46 (unchanged)
- Post-processing: stage 4 (`_fix_hunk_offsets`) now more robust against indentation mismatches in context lines
- Pool: fully saturated; check ~2026-06-09 for new DAS registrations

---

## 2026-06-02 — Structural summary in compacted history (commit b21930b)

### Verify: structural context for completeness checking

**Problem**: After history compaction, the verify model only saw file names ("files in scope: scoring.py, constants.py"). It had no knowledge of what functions/classes those files contain — so it couldn't check completeness ("does the diff add the required method?") or identify missing changes ("should `filter_repos` have been modified?").

**Fix**: `_structural_summary()` extracts function/class/method declaration lines from all implementation files and injects them into the compacted observe message. Example:

```
[scoring.py  ← changed]
  class ScoreCalculator:
  def compute_score(self, pr, max_score: float = 30.0) -> float:
  def apply_penalty(self, score: float, repo: str) -> float:
  def filter_repos(self, repos: list[str]) -> list[str]:
[constants.py]
```

Files that appear in the diff are marked "← changed". The verify model can now cross-reference the diff against the structural summary and answer: "Did the diff modify `filter_repos` as the issue requires?" — a completeness check that file names alone cannot support.

Supported languages: Python, Go, TypeScript/JS, Rust, Kotlin/Java/Scala, Ruby. Capped at ~3 KB total to keep verify prompt size manageable.

---

## 2026-06-02 — Hunk source context injected into verify (commit 13a1bde)

### Verify: real hunk-offset check via source context injection

**Problem**: The verify step's criterion 2 ("are `@@ -N` hunk offsets correct?") was previously a plausibility guess. After history compaction, the verify model has no access to source files — it can only ask "do the context lines look like surrounding code?" but cannot check if they match the *actual* source at line N.

**Fix**: `_hunk_source_snippets(diff, file_lookup)` extracts actual source lines at each hunk's `@@ -N` offset and injects them into the verify prompt. Format:

```
[src/drivers/mistral.go @@ -45]
    43: // Embed implements the Embedder interface
    44: func (e *MistralEmbedder) Embed(...) {
  → 45: 	return nil, fmt.Errorf("not implemented")
    46: }
    47: 
```

The arrow marks the hunk start line; 2 lines above and below give context. The verify model can now check: do the context lines in my diff match what's shown here?

Criterion 2 updated to reference the new section: "The source context section above shows the actual file lines at each hunk offset — verify that the context lines in your diff match exactly (same content, same whitespace)."

**Cost**: limited to 6 hunks per problem (~1 KB added to verify prompt). No API calls — purely local lookup from `file_lookup` which is already built in `solve()`.

**Impact**: enables the verify model to catch wrong `@@ -N` offsets that `_fix_hunk_offsets` didn't correct (e.g., offset > ±50 from stated value, or ambiguous fingerprint) and context-line whitespace mismatches that `_fix_context_lines` missed (e.g., trailing spaces, CRLF).

---

## 2026-06-02 — Verify prose-critique followup, long-body head+tail (commits a1b4584, 9e40ddc)

### Verify prose-critique follow-up prompt

When the verify step returns a textual critique (no corrected diff extracted), the next iteration previously re-sent the full VERIFY_PROMPT with the same diff — ~4-6KB of repeated context and all 7 criteria. The model had already analysed the diff; asking it to re-analyse was redundant.

Fix: when the previous verify iteration gave a prose critique, the next call uses `VERIFY_FOLLOWUP_PROMPT`: "Based on your analysis above, produce the corrected unified diff now." (~80 chars vs. ~4-6KB). The `pending_prose_critique` flag tracks this state across loop iterations.

### Long issue body head+tail for verify

After the act step, `history[1]` (the full observe context) is compacted to a 150-char summary. The verify prompt becomes the model's only view of the issue body — and it was truncated to the first 3000 chars. 31% of pool problems (133/430) have issue bodies longer than 3000 chars; the max is 16,200 chars.

Fix: for bodies longer than 3000 chars, the verify prompt now shows `body[:2500] + "[...]" + body[-500:]`. The last 500 chars often contain edge-case requirements, gotchas, or clarifying examples that the model needs to verify completeness. Total length stays ~3050 chars.

---

## 2026-06-02 — Verify token budget, assertion limit, hunk search radius (commit a5d1235)

### Verify token budget raised to match act

`verify_tokens` was `token_budget // 4 = 12,500`. When the verify step produces a corrected diff (not LGTM), it needs the same token headroom as the act step — otherwise a large multi-file diff gets truncated mid-output, producing a partial patch worse than the original. Fix: `verify_tokens = act_tokens = 25,000`.

### `_extract_assertions` limit 30 → 50

Large test suites often place parameterised and edge-case assertions near the end. The old 30-line cap silently dropped them, leaving the verify step blind to those requirements. Raised to 50 without materially inflating the verify prompt size.

### `_fix_hunk_offsets` search radius ±25 → ±50

Large Go/TS files (500+ lines) are more likely to have model-estimated offsets that are off by more than 25 lines when the file is shown windowed. The unambiguous-match safety guard (single match required) prevents false positives — a wider radius finds more correct offsets without introducing wrong ones.

---

## 2026-06-02 — Removal-line whitespace fix, verify hunk-map check, fence regex (commit a07d86f)

### `_fix_context_lines` extended to removal lines

`git apply` requires removal lines (`-` prefixed) to match the source file exactly — the same constraint that applies to context lines (` ` prefixed). Previously `_fix_context_lines` only repaired whitespace differences on context lines; if the model wrote `-    return None` where the source had `-\treturn None` (tab indent), the hunk would be rejected.

Fix: the same stripped-content safety check now applies to `-` lines. When `diff_content.strip() == source_line.strip()` but the full lines differ, the `-` line is replaced with `- {source_line}`. The same safety guard applies: only replaces on exact stripped-content match, never on partial matches that could misplace the removal.

### Verify criterion 7: hunk-map completeness

Added criterion 7 to `VERIFY_PROMPT`: "Look back at your step 6 hunk map from earlier in this conversation. Does this diff include a change for every file path listed there? If any planned file is missing from the diff, add the necessary changes now."

Previously the verify step had no explicit prompt to cross-check the hunk map against the diff. The model could LGTM a diff that omitted a planned file if its criteria checks 1–6 all passed. Criterion 7 closes that gap by explicitly referencing the plan-step output.

### `_extract_diff` fence regex generalised

Changed `\`\`\`(?:diff|patch)?` to `\`\`\`\w*` — now accepts any fence language tag. Handles `\`\`\`udiff`, `\`\`\`unidiff`, `\`\`\`text`, etc. Diffs wrapped in non-standard fence tags are extracted rather than silently falling through to the bare `diff --git` search.

---

## 2026-06-02 — API resilience, cascade-timeout hardening, JS support (commits d039717–2716186)

### API error resilience in `_call` (commit d039717)

Discovered via sample eval: OpenRouter sometimes returns 200 with `{"error": {...}}` body instead of `choices`. Previously caused `KeyError: 'choices'` propagating as an exception (problem score = 0). Fix:
- Check `"choices" in data` before access; retry once on missing choices with 5s backoff
- Add 400 responses to the retry set (covers content policy / transient routing errors)
- Final fallback: `return ""` so `_diagnose_diff` handles it as empty-diff gracefully

### Verify prose-critique feedback loop (commit 653e8e4)

When verify returns a textual critique without a corrected diff, the loop previously broke and accepted the unverified diff. Now: store the critique in history and continue — the model can self-correct on the next verify iteration by producing a diff based on its own critique. Only breaks on the last attempt.

### JS/JSX language notes added (commit 84f6004)

12 JS problems (gittensor-ui, product-data-extractor, ragflow JS issues) previously got no language-specific guidance. Added `LANG_NOTES["js"]` and `LANG_NOTES["jsx"]` covering: ES module exports, null-safety, async/await style, `const`/`let` over `var`, no TypeScript syntax.

### CommonJS `require()` import resolution (commit 11eb3a4)

Extended `_resolve_test_imports` and `_expand_sibling_imports` for JS/TS to also parse `require('./foo')` patterns (CommonJS style). Previously only `from '...'` ES module syntax was handled.

### Conditional history compaction + empty-act retry (commit 2716186)

Root cause found via sample eval: when the API is slow (calls near-timeout), the act step times out and returns "". Previously history was compacted unconditionally, leaving repair iterations with only a 150-char summary (issue title, file names) — insufficient context to produce code.

**Fix 1**: Only compact `history[1]` (source files, 20-30k chars) if the act step produced a valid diff. If act returned empty/invalid, keep the full source context so repair iterations can generate a real diff.

**Fix 2**: When the repair loop detects "empty output — no diff produced", resend `ACT_PROMPT` directly instead of the useless `REPAIR_FORMAT_PROMPT` with an empty diff. The model retries the act step with full source context still available. On success, compaction happens then.

### Pool refresh: 423 → 430 (+7 new problems) (benchmark commit 07f6504)

DAS dry-run returned "7 newly added"; actual build added 7 problems across 4 repos:

- `phase-rs_phase_1858` (Rust, `cargo test`) — Liliana, Dreadhorde General trigger bug
- `phase-rs_phase_1900` (Rust, `cargo test`) — Rebound Mechanic implementation
- `jsonbored_gittensory_266` (TypeScript, `npm test`) — offline decision-pack caching
- `geniepod_genie-claw_365` (Rust, `cargo test`) — tool-call gate enforcement
- `touchpilot_touchpilot_133` (Kotlin, `./gradlew test`) — running agent state controls
- `touchpilot_touchpilot_145` (Kotlin, `./gradlew test`) — task completion summary card
- `touchpilot_touchpilot_150` (Kotlin, `./gradlew test`) — long_press tool

Oracle mean: 23.36 → 23.46. Updated: pool_config.json, results/baselines.json, results/leaderboard.json, dashboard_data.json, gitminer.py, evaluate.py, record_result.py, docs/rewards.md, docs/api.md, README.md (all 4 count refs).

All new problem languages covered: `rs` (Rust), `ts` (TypeScript), `kt` (Kotlin) — LANG_NOTES + import resolution already present.

### Status
- Benchmark: 430 problems, oracle 23.46, 20 repos (commit 07f6504)
- Sample eval: discovered `patch_applied: False` on gittensor problems when API slow — root cause was cascade timeout + premature history compaction, now fixed
- Pool: fully saturated; check ~2026-06-09 for new DAS registrations
- Pending: Gittensor registration, nginx hookup

## 2026-06-02 — Context line whitespace repair (commit 870de98)

### Agent: `_fix_context_lines` — 6th post-processing stage

`git apply` requires context lines (` `-prefixed unchanged lines surrounding a change) to match the source file exactly. Even a single tab-vs-spaces difference causes rejection, even when the change content itself is correct.

`_fix_context_lines(diff, file_lookup)`:
- For each context line in each hunk, looks up the expected content from the source file using the (already-corrected) `@@ -N` offset as the anchor
- If the stripped content matches exactly (`line.strip() == source_line.strip()`) but the full line differs (whitespace mismatch), replaces with the actual source content
- Safety guard: only replaces on stripped-content match — if content is semantically different, the original is kept. This prevents silently moving a hunk to the wrong location if the offset is still wrong
- Skips new-file hunks (`@@ -0,0 ...`) — no source to look up
- Applied as stage 5 of 6 in `_post_process`, after `_fix_hunk_offsets` so start offsets are already corrected

Also tightened ACT_PROMPT: "copy [context lines] verbatim from the source file display (same characters, same whitespace) — even a space/tab difference causes `git apply` to fail."

### Status
- Benchmark: 423 problems, oracle 23.36, 20 repos
- Post-processing: 6-stage pipeline (strip N|, trim prose, fix headers, fix offsets, fix context whitespace, fix counts)
- All 6 stages: deterministic, zero API calls

---

## 2026-06-02 — Missing-header fix + fuzzy hunk-offset correction (commit 0ad4298)

### Agent: `_fix_diff_headers` — auto-insert missing `--- a/` / `+++ b/` headers

`git apply` requires `--- a/<path>` and `+++ b/<path>` lines between the `diff --git` header and the first `@@` hunk. Models in repair mode often jump straight from `diff --git` to `@@`, producing diffs that fail immediately. `_fix_diff_headers()` detects these blocks and inserts the required headers derived from the `diff --git a/<path> b/<path>` line itself. New-file blocks use `--- /dev/null`. Applied as part of `_post_process` on every intermediate diff.

### Agent: `_fix_hunk_offsets` — fuzzy context-line start-offset correction

`_fix_hunk_counts` corrects the `b/d` count fields in `@@ -a,b +c,d @@` headers. It cannot fix the `a/c` *start offset* fields — those require knowing where the context lines actually appear in the file. A wrong start offset causes `git apply` to reject a diff even when the content is correct.

`_fix_hunk_offsets(diff, file_lookup)` fixes this:
1. For each hunk, extracts leading context lines (unchanged ` `-prefixed lines) and the first removal line as a fingerprint.
2. Searches for those lines in the actual file content within ±25 lines of the stated offset.
3. If the match is unambiguous (exactly 1 location), corrects the `@@ -N` and `+N` values with the same delta.
4. Safe fallback: if no match or multiple matches (ambiguous), keeps the original offset.

`file_lookup` is built from the problem's context files and passed through `_post_process`. For files not in context (e.g. secondary `__init__.py` additions), offset correction is skipped. Applied before `_fix_hunk_counts` so counts are computed on the corrected structure.

### `_post_process` pipeline order (updated)
1. Strip `N |` display artifacts
2. Trim trailing prose
3. Insert missing `--- a/` / `+++ b/` headers (`_fix_diff_headers`)
4. Correct wrong `@@ -N` start offsets (`_fix_hunk_offsets`, needs file_lookup)
5. Recompute `@@ -a,b +c,d @@` hunk counts (`_fix_hunk_counts`)

### Status
- Benchmark: 423 problems, oracle 23.36 (unchanged)
- Post-processing: 5-stage pipeline covering all major `git apply` failure modes
- Pool: fully saturated (check 2026-06-09)

---

## 2026-06-02 — Oracle mean update + hunk map in plan step (commits ba036fb, 31dcf29, 38d1809)

### Oracle mean update: 23.08 → 23.36 (commit ba036fb)

Scored all 423 problems (was 400). The 23 new ragflow Go/TS problems added last step were missing from baselines.json. Running `scripts/baseline_scores.py` across all 423 produced:
- Mean: 23.36 (was 23.08 for 400 problems)
- Median: 26.74
- New Go/TS problems score high (many ~30.00 — large driver implementations)

Updated oracle mean in: leaderboard.json, record_result.py, gitminer.py, benchmark/evaluate.py, docs/rewards.md, docs/api.md, README.md.

Dashboard regenerated: 423 problems, oracle 23.36 (benchmark commit 31dcf29, dashboard commit 94113f3).

### Agent: hunk map in plan step (commit 38d1809)

**Root cause of line-offset errors**: the model re-derives `@@ -N` start lines during the ACT step, under time pressure and without having explicitly committed to specific line numbers. This produces hunk offset errors (wrong start line in `@@ -a,c +b,d @@`) that cause `git apply` to reject a structurally-valid diff.

Our `_fix_hunk_counts` post-processor fixes the *counts* (b/d fields) but cannot fix the *start offset* (a/c fields) without running `git apply`.

**Fix**: added Step 6 "Hunk map" to the OBSERVE_PROMPT. Before writing the diff, the model explicitly states each planned change with its file path and `N |` start line from the windowed source display. ACT_PROMPT now tells the model to use the hunk map from step 6 for its `@@ -N` offsets directly. This pre-computation moves the hard reasoning to the plan step (18s budget, no format pressure) rather than the act step (48s budget, but generating a full multi-file diff simultaneously).

### Status
- Benchmark: 423 problems, oracle 23.36, 20 repos (commit 38d1809)
- Pool: fully saturated (check 2026-06-09 for new DAS registrations)

---

## 2026-06-02 — Agent: language-aware headers + Scala support (commits 6cf29f0, 9d56b86, 6f2cbfc)

### Language-aware import-block detection for windowed files (commits 6cf29f0, 9d56b86)

**Root cause**: `HEADER_LINES = 20` was a fixed constant applied to all files. Go files typically have a 1-line `package` declaration + 1-2 blank lines + a `import (...)` block spanning 15-30 lines, consuming all 20 header lines. The struct/type definitions that immediately follow the import block were invisible to the model, causing wrong type assumptions and missing method signatures.

**Fix**: `_compute_header_end(lines, ext)` scans for the end of the language's import section:
- Go: finds closing `)` of `import (...)` block, adds 8-line buffer → covers first struct/type defs
- TypeScript/JS: last `import` statement + 8 lines
- Kotlin/Java/Scala: last `import` line + 8 lines
- Rust: last `use` statement + 8 lines
- Python: last `import`/`from...import` + 8 lines
- Unknown: falls back to HEADER_LINES=20

Real example: `volcengine.go` (642 lines) — old header cut at line 20 (mid-import block); new header extends to line 37, showing the complete import block AND the `VolcEngine` struct definition.

Same fix applied to the no-keyword-hit peek (commit 9d56b86): was always 80 lines regardless of language; now `max(language_header, 80)` so Go/TS files with > 80-line import+struct sections show the full header.

**Sibling scan expanded top-3 → top-5** (commit 6cf29f0): larger multi-file problems where the most relevant file is ranked 4th or 5th now benefit from sibling import expansion too.

### Scala language support (commit 6f2cbfc)

seroperson/jvm-live-reload (5 problems) uses Scala test files (`*Spec.scala`) and Scala source files. Previously getting no language guidance.

- `LANG_NOTES["scala"]`: trait/abstract class implementations, case class fields, sealed trait coverage, companion objects, `override def`, no `???` stubs
- `_is_test_file`: now recognises `*Spec.scala` via `(test|spec)\.(kt|java|scala)$`
- `_compute_header_end`: handles `.scala` in the `kt/java` branch
- `_resolve_test_imports`: resolves Scala JVM-style imports to `.scala` files; skips `scala.`, `org.scalatest`, `cats.`, `zio.`, `akka.` stdlib imports

### Status
- Benchmark: 423 problems, oracle 23.08 (Python problems) 
- Pool: fully saturated (no qualifying new PRs in DAS as of 2026-06-02)
- Agent: language-aware headers, Scala support, sibling scan top-5

---

## 2026-06-02 — Agent improvements + pool refresh (commits 2e8e54d–b609751)

### Agent: verify loop hardening (commits 2e8e54d, e0a8312)

**LGTM detection** (commit 2e8e54d): was `startswith("LGTM")` — missed "The diff looks correct. LGTM." Now also checks if no valid diff was extracted AND "lgtm" appears in verdict → treats as approval. Avoids spurious repair iterations.

**Clean verify history** (commit 2e8e54d): when verify produces a repaired diff, we now store the cleaned `repaired` in history (not the raw `verdict` which may contain prose). Subsequent verify/repair calls see the same clean artifact-free version.

**Temperature=0 for verify** (commit 2e8e54d): verification is a precision task — using default 0.2 allowed hallucinated corrections. Now deterministic.

**CRLF normalization** (commit 2e8e54d): `_extract_diff` now strips `\r\n` → `\n` before processing. Prevents hunk-count mismatches on Windows line endings from OpenRouter.

**5xx retry** (commit e0a8312): `_call` previously only retried on 429. Now retries on 500/502/503 (transient server errors) too.

**Stale N| reference in VERIFY_PROMPT** (commit e0a8312): criterion 2 referenced "N| line markers in the context" — but context is compacted before verify runs. Updated to "check hunk offsets are plausible" instead.

### Agent: context budget fix (commit 600ed86)

**Per-file budget cap** (commit 600ed86): `_truncate_context` was counting raw file sizes for budget allocation — but 270/400 problems have raw context > 40 KB, meaning file 1 alone could exhaust the budget and drop files 2-N. Fixed to count `min(raw_size, 10_000)` per file (capped to approximate windowed size). More files pass through to windowing, which then controls actual prompt size.

### Pool refresh: 400 → 423 (commit b609751)

**23 new ragflow problems** (Go/TS): AWS Bedrock, OCR for ZhipuAI, OpenAI Go driver ASR/TTS fix, PPIO/Groq/TokenPony/Hunyuan providers, streaming timeout bug (15380, 15382), password reset OAuth (15293), and 12 more Go provider implementations. DAS API user-agent fix also shipped (was 403-blocking pool rebuilds).

### Status
- Benchmark: 423 problems (oracle mean TBD for new problems — Go needs Docker CI)
- Agent: verify hardening, context budget fix, 5xx retry

## 2026-06-02 — Agent: verify/repair hardening (commits 013ab2c–991f281)

### Four targeted fixes to the verify + repair loop

**Partial-repair guard** (commit 013ab2c): `_count_diff_files()` counts `diff --git` headers. Replacement only accepted if repaired file count >= original. Prevents multi-file diff being silently reduced to a one-file partial fix from verify.

**Clean act history** (commit 013ab2c): act step now stores post-processed `diff` in history (not `raw_diff`). Model's "memory" of its own output matches the verify prompt. Same fix in format-repair branches.

**Empty diff diagnostic** (commit de62dd0): `_diagnose_diff` now catches diffs where all hunk content is context-only (no `+`/`-` lines). Triggers format-repair instead of letting the harness run with a no-op patch.

**Format-repair with explicit diff** (commit 991f281): `REPAIR_FORMAT_PROMPT` now includes the current diff in a code block. Model no longer needs to recall the diff from history context — it sees exactly what it produced and what's wrong with it.

### Status
- Benchmark: 400 problems, oracle 23.08 (unchanged)
- Pool: all repos saturated — next check 2026-06-09
- Pending: Gittensor registration, nginx hookup

---

## 2026-06-02 — Agent: partial-repair guard + clean history in act step (commit 013ab2c)

### Partial-repair guard in verify loop

Found a correctness bug: when the verify step produced a corrected diff covering fewer files than the current diff, the replacement was accepted unconditionally, silently dropping changes to the other files.

Example: act produces `fileA + fileB` diff. Verify says "fileA is wrong, here is the fix" and returns a 1-file diff for fileA only. With the old code, `diff = repaired` would lose fileB's changes entirely.

Fix: `_count_diff_files()` counts `diff --git` headers in both diffs. Replacement only accepted if repaired file count >= current file count. If fewer: log `"partial repair (N < M files) — keeping current diff"` and break.

### Clean act history

The act step was storing `raw_diff` (the model's literal output, including any `N |` artifacts and trailing prose) as the assistant turn in history. The verify prompt then showed the post-processed `diff`, creating two inconsistent versions the model could see. Now history stores the post-processed `diff` so the model's "memory" matches the verify prompt.

Same fix applied to format-repair branches in the verify loop.

### Status
- Benchmark: 400 problems, oracle 23.08 (unchanged)
- Agent: partial-repair guard, clean history
- Pool: all repos saturated — next check 2026-06-09
- Pending: Gittensor registration, nginx hookup

---

## 2026-06-02 — Agent: intermediate diff post-processing + history compaction (commit 936a857)

### Post-process every intermediate diff

Previously: `_strip_line_number_prefixes`, `_trim_trailing_prose`, and `_fix_hunk_counts` ran only once at the very end of `solve()`.

Problem: intermediate diffs passed to verify/repair still had `N | ` display artifacts and wrong hunk counts. Verify saw these artifacts and could flag the diff as wrong (triggering a wasteful repair loop). The repair branch could also produce a diff with artifact-prefixed lines, and those would be fed to the next verify iteration unclean.

Fix: introduced `_post_process(diff)` helper that applies all three processors in order. Called after every `_extract_diff` throughout `solve()` and `repair()`. Final pass still runs but is now a no-op in most cases (the diff is already clean).

### History compaction before verify

Previously: every verify/repair call sent the full conversation history including `history[1]` — the observe message containing all source files, file tree, and test file content (typically 20-30k chars, ~5-7k tokens for deepseek).

Problem: the model had already used this context to produce its plan and initial diff. Re-sending the full source code on every verify call wastes token budget the model could use to reason about the diff.

Fix: after the act step, `history[1]` is replaced with a compact summary (~150 chars):
```
[Earlier context: repo/name — issue: Issue Title — files in scope: file1.py, file2.go, ... — test: pytest tests/test_foo.py]
```

The model retains the essential metadata (what was being fixed, which files, which test) without re-processing thousands of lines of source code.

---

## 2026-06-02 — Agent: non-uniform timeouts and multi-fence diff extraction (commit 3361337)

### Non-uniform timeout allocation

Previously: `timeout = 120s / 6 calls = 20s per call` — uniform distribution.

Problem: act step (generating a large multi-file diff) was under-allocated; plan step (short analysis) was over-allocated.

New allocation:
- `plan_timeout = 120s × 15% = 18s` — analysis output is moderate length
- `act_timeout = 120s × 40% = 48s` — diff output can be large (many hunks, many files)
- `verify_timeout = 120s × 15% = 18s` — LGTM or corrected diff per iteration

Also: `plan_tokens` reduced from `budget // 3 = 16.6k` to `budget // 4 = 12.5k` — analysis rarely exceeds 4k tokens; this cap is still generous and avoids wasting the plan call.

### Multi-fence diff extraction

Previously: `re.search(r"```(?:diff)?...", ...)` — only captured the FIRST fenced diff block.

Problem: models sometimes put each changed file in its own ` ```diff ` fence when generating complex multi-file patches. With `re.search`, everything after the first fence was silently dropped — the agent appeared to succeed but produced an incomplete patch.

Fix: `_extract_diff()` now uses `re.finditer` to collect ALL fenced diff blocks and joins them with `\n`. Also added `patch` as a recognized fence language (```` ```patch ````).

Verified: test with two-fence input correctly joins both `diff --git` sections.

---

## 2026-06-02 — Agent: test file windowing + new-file format example; Go lang fix (commits e9f22c1–0a2354e)

### gitminer.py: Go language classification fix (commit e9f22c1)
- `_LANG` mapping now includes `"go": "go"` — 19 Go problems were previously labelled as `py`
- `--lang` choices updated to include `"go"` so `gitminer problems --lang go` works

### Agent: explicit new-file diff format example (commit e9f22c1)
- `NEW_IMPL_FILES_TEMPLATE` now shows the exact `diff --git` / `new file mode 100644` / `--- /dev/null` / `@@ -0,0 +1,N @@` format the agent must use
- Reduces formatting failures for the 33% of problems (132/400) with new implementation files

### Agent: test file windowing (commits 273b668, 0f4a2fa)
- Large test files (> 200 lines) are now windowed with ±80-line context around keyword hits
- Previously: test files always shown in full — a single 20 KB test suite consumed half the 40 KB context budget
- Threshold 200 (lower than impl files 300): test files are read-only so we lose nothing by windowing them earlier
- Window 80 lines (wider than impl files 40): preserves complete test function bodies
- Line numbers (`N | content`) are **omitted** from test file windows — the agent does not write diffs against test files, and numbers would confuse hunk offset calculations for impl files
- `_window_file` and `_format_files` now accept `threshold`, `context_lines`, `show_line_numbers` parameters for full configurability

### Agent: ACT_PROMPT clarification (commit 0a2354e)
- Line number note updated: "windowed **source** files show lines as `N | content`" — explicitly notes test files are windowed without line numbers

### Status
- Benchmark: 400 problems, oracle 23.08, 20 repos (commit 0a2354e)
- Pool: all 16 DAS repos saturated; next refresh check ~2026-06-09
- Pending: registration (operator), nginx hookup (operator)

---

## 2026-06-02 — Agent: hunk count fixer + file tree pruning (commits 470c201, 6049035)

### Agent: deterministic hunk count fixer (commit 470c201)
- **`_fix_hunk_counts()`**: post-processor that recomputes the b/d fields in every `@@ -a,b +c,d @@` header by counting actual context/remove/add lines in each hunk
- **Problem**: LLMs frequently miscalculate hunk line counts (b = old-hunk size, d = new-hunk size). Incorrect counts cause `git apply` to reject otherwise correct diffs with a "corrupt patch" error
- **Applied after every solve() and repair()**: zero API calls, deterministic, applies to the final diff before returning Patch
- Tested: corrects wrong counts across single-hunk, multi-hunk, multi-file, and new-file diffs; leaves already-correct diffs unchanged

### Agent: file tree pruning (commit 6049035)
- **`_prune_file_tree()`**: reduces the file_tree shown in the prompt from 500 paths (16-22 KB) to ~30-95 relevant paths (1-3 KB) by keeping only entries in directories that contain context files or their ancestors
- **Problem**: 211/400 problems have file trees > 10 KB; average 12.6 KB per tree. At 40 KB context budget for code, a 22 KB tree consumes 55% of the budget on irrelevant paths
- **Algorithm**: for each context file, adds its directory and all ancestor directories to a relevant-dirs set; keeps only tree entries whose parent is in that set; falls back to capped full list if pruning leaves nothing
- Results: ragflow (500 → 32 entries), gittensor (124 → 27 entries), phase Rust test-only (500 → 95 via capped fallback)
- **Critically**: `_resolve_test_imports` and `_expand_sibling_imports` still use the full `problem.file_tree` — only the display in the prompt is pruned

### Status
- Benchmark: 400 problems, oracle 23.08, 20 repos (commit 6049035)
- Pool: all 16 DAS repos saturated; next refresh check ~2026-06-09
- Pending: registration (operator), nginx hookup (operator)

---

## 2026-06-02 — Agent: sibling imports + new test file creation (commits 9cd3e74, ed46bb2)

### Agent: sibling import expansion (commit 9cd3e74)
- **`_expand_sibling_imports()`**: after ranking, scans the top-3 implementation files for local imports (`from .helpers import X`, `from pkg.sub.helpers import X`, TypeScript relative imports, same-dir Go files) and adds those sibling modules to context (up to 6 KB extra)
- **Key fix**: prevents the agent from hallucinating helper functions that already exist in the package. Without this, `view.py` is shown but not `helpers.py` — the agent doesn't know `emit_error_json` exists and tries to define it inline (wrong) or imports from the wrong path
- Tested on problem 0335 pattern: correctly identifies `gittensor/cli/issue_commands/helpers.py` as a sibling of `view.py`

### Agent: new test file detection (commit ed46bb2)
- **Root cause found**: 243/400 pool problems have test files in context that don't exist at `base_commit` (they were added by the PR). Without detection, the agent treats them as read-only context but never creates them — `git apply` succeeds but `pytest` fails with "file not found" → correctness score 0
- **`_new_test_files()`**: compares context test files against `file_tree` (repo at base_commit). Files not in file_tree are new
- **`_new_test_diff()`**: generates pre-formatted diff blocks (new file mode, `/dev/null` header, `@@ -0,0 +1,N @@`) that the agent can copy verbatim
- **`NEW_TEST_FILES_TEMPLATE`**: new prompt section shown when new test files detected — instructs agent to include pre-formatted diff blocks in output
- Affects ~60% of all pool problems

### Status
- Benchmark: 400 problems, oracle 23.08, 20 repos (commit ed46bb2)
- Pool: all 16 DAS repos saturated; next refresh check ~2026-06-09
- Pending: registration (operator), nginx hookup (operator)

---

## 2026-06-02 — Pool 397→400 + Kotlin/Java agent support (commits 8cab7e5, 96af7c8)

### Agent: Kotlin/Java language notes and import resolution (commit 8cab7e5)
- **Kotlin LANG_NOTES** (`kt`): companion objects, data class fields, sealed class coverage, `@Test` annotation, `TODO()` stubs, constructor signature matching
- **Java LANG_NOTES** (`java`): full interface implementation, correct `import` declarations, `@Override` annotations, checked exception handling
- **`_is_test_file`**: now detects `*Test.kt`, `*Test.java`, `*Test.scala` via regex — previously only caught files in `/test/` directories
- **Kotlin/Java import resolution**: `import dev.touchpilot.app.tools.MyClass` → finds `MyClass.kt` or `MyClass.java` in tree (skips stdlib/Android/JUnit imports)
- **Impact**: 34 Kotlin problems (touchpilot) + 3 Java problems (jvm-live-reload) now get precise file pinning and language-appropriate prompting

### Pool refresh: 397 → 400 (+3 new phase-rs/phase problems) (commit 96af7c8)
- `phase-rs_phase_1816` — damage assignment modal bug (Rust + TypeScript, React/Vitest test)
- `phase-rs_phase_1734` — "Clash with an opponent" auto-picks wrong opponent (TypeScript + Rust test)
- `phase-rs_phase_1691` — Emergence Zone card selection bug (Rust + TypeScript test)
- Oracle mean: 23.05 → **23.08** (recomputed across all 400 problems)
- All repos fully saturated as of this run; next pool scan scheduled ~2026-06-09

---

## 2026-06-02 — Pool 367→397 + Go/TS language support (commits b882b42, a277f65)

### has_test_files fix: Go, TypeScript, Java, Ruby patterns (commit b882b42)
- **Root cause**: `*_test.go` (Go convention), `*.test.ts/tsx` (TypeScript), `*.spec.ts`, `*Test.java`, `*_spec.rb` all failed our `has_test_files` check
- **Impact**: ~20+ ragflow Go problems + ~12+ phase-rs TypeScript problems were being silently filtered
- Added 4 new regexes to cover all major language test file patterns

### Pool refresh: 367 → 397 (+30 new problems) (commit a277f65)
- **infiniflow/ragflow** (Go): +19 new problems — Go API driver implementations (NVIDIA, LocalAI, Voyage, Xinference, Jina, vLLM, Novita, OpenRouter, Hunyuan, VolcEngine, TokenHub, 302.ai, etc.)
- **phase-rs/phase** (TypeScript): +11 new problems — React/TypeScript component bugs with Vitest tests
- Oracle mean: 22.73 → **23.05** (new problems have strong Go/TS implementation diffs)
- Updated everywhere: pool_config.json, baselines.json, leaderboard.json, dashboard_data.json, README badge, docs/rewards.md, docs/api.md, gitminer.py, evaluate.py, record_result.py

### Agent: Go language support
- New `LANG_NOTES["go"]`: explains Go interface implementation, factory registration, export naming, error types
- New Go import resolution in `_import_pinned_files`: parses `"github.com/org/repo/internal/foo"` → pins all `.go` files in `internal/foo/` to rank #1

---

## 2026-06-02 — Pool 366→367 + agent improvements (commits 82faf35–91004c9)

### Pool refresh (+1 problem)
- `phase-rs_phase_1863` — "pin multi-suspend upkeep tick fires per source" (Rust integration test)
  - Issue #1502: multiple suspended cards scenario — upkeep triggers per suspend source, not once total
  - Oracle mean: 22.79 → **22.73** (recomputed across all 367 problems)
- All other repos dry-ran: phase, ragflow, gittensor, gittensory — all saturated (0 new qualifying PRs)

### Agent improvements (8 commits, all pushed)
1. **Import-path resolution** (`82faf35`) — parses test imports → pins exact impl files to top of ranking
   - Python: `from foo.bar.baz import X` → `foo/bar/baz.py`
   - TypeScript: relative `import { X } from './utils/foo'` → resolved path
   - Ruby: `require_relative '../lib/foo'` → resolved path
   - Rust: `use crate::foo::bar;` → `src/foo/bar.rs` / `src/foo/bar/mod.rs`
   - Pinned files score +100 (dominates keyword ranking)
2. **Language-specific system prompt notes** (`69fd49c`) — per-language caveats (Rust trait bounds, TS exports, Ruby requires, Python type annotations)
3. **Line numbers in windowed files** (`2f3e8cd`) — `  N | content` so model writes accurate `@@ -N` offsets
4. **Title token weighting** (`f5c17fe`) — issue title tokens 3× vs body (titles are precise; body is prose)
5. **Smarter repair output** (`48e9f6a`) — shows first 30 + last 50 lines of test output; adds failure categorization hints
6. **Sharper verify criteria** (`57949c5`) — checks import completeness, cross-checks `@@ -N` against line markers
7. **Hunk context line requirement** (`c0a5995`) — requires 3 unchanged context lines per hunk for `git apply` robustness
8. **Rust import + mod.rs hint** (`9fddfb0`) — Rust `use` import resolution + `mod.rs` in index-file hint

---

## 2026-06-02 — Agent: import resolution + language notes + line numbers (commits 82faf35, 69fd49c, 2f3e8cd)

### Agent improvements (3 commits)

**Import-path resolution** (commit `82faf35`)
- New `_resolve_test_imports()`: parses import statements in test files to identify exact implementation files under test
  - Python: `from foo.bar.baz import X` → `foo/bar/baz.py`
  - TypeScript: `import { X } from './utils/helpers'` → resolves relative path with extension probing
  - Ruby: `require_relative '../lib/foo'` → resolved relative path
- Pinned files score +100 in `_rank_files()` — they rise to the top over any keyword-matched file
- `_rank_files()` now accepts `file_tree` parameter; pinned files computed by checking against tree
- Tested on Python (gittensor#160) and TypeScript (gittensory) problems — correctly pins scoring.py, model.ts, etc.

**Language-specific system prompt notes** (commit `69fd49c`)
- New `LANG_NOTES` dict: per-language caveats for Rust, TypeScript, Ruby
  - Rust: trait bounds, match arms, `pub` visibility, `use` imports
  - TypeScript: type definitions, named exports, null checks
  - Ruby: snake_case, module includes, `require`
- `_detect_lang()` infers language from test file extensions
- Note appended to system prompt only when language is detected (Python uses default prompt)

**Line numbers in windowed files** (commit `2f3e8cd`)
- `_window_file()` now prefixes each visible line with its 1-based number: `  42 | def my_function():`
- Digit width consistent with total line count for clean alignment
- `ACT_PROMPT` updated: "use `N |` numbers directly for `@@ -N` offsets; do NOT include them in diff content"
- Impact: model no longer needs to count from omission markers — can read line number directly

---

## 2026-06-02 — Agent: exact line-range omission markers (commit a232d96)

### Agent improvement
- `_window_file()` now returns `(content, was_windowed)` and emits precise range markers:
  `... [lines 21-260 omitted — next visible line is 261]` instead of `... [N lines omitted]`
- `_format_files()` adds `(N lines total — relevant sections shown)` to windowed file headers
- `ACT_PROMPT` now explicitly instructs the model to use omission-marker line numbers for accurate `@@ -N` hunk offsets
- **Impact**: prevents "patch doesn't apply" failures caused by wrong hunk line numbers in windowed files
- Pool dry-runs: geniepod/genie-claw (152 PRs), allways (140 PRs), jvm-live-reload (26 PRs) — all fully saturated (no test files or no linked issues)

---

## 2026-06-02 — Pool 360→366 + oracle 22.79 (commit ba1f53b)

### Pool refresh (+6 new problems)
- `phase-rs_phase_1440` — Emissary Green not triggering (Rust integration test)
- `jsonbored_gittensory_218` — feat(agent): contributor evidence graph (TypeScript unit tests)
- `jsonbored_gittensory_222` — Pending-PR projection double-counts merge-ready PRs (TS test)
- `jsonbored_gittensory_225` — buildRoleContext maintainer association bug (TS test)
- `jsonbored_gittensory_226` — add recommendation confidence and provenance (TS integration test)
- `jsonbored_gittensory_228` — buildObservedPullRequestScenarios classifies open PRs wrong (TS test)
- Oracle mean recomputed: 22.83 → **22.79** across all 366 problems
- Updated: pool_config.json, leaderboard.json, baselines.json, dashboard_data.json, README badge, docs/rewards.md, docs/api.md, evaluate.py, gitminer.py, generate_dashboard_data.py, record_result.py

---

## 2026-06-02 — Agent: file-header preservation + index-file hint (commit 8ac6b9d)

### Agent improvements

- **File header preservation in windowing**: `_window_file()` now always includes the first `HEADER_LINES=20` lines of any windowed file, regardless of where keyword hits occur. Previously, if the relevant function was at line 300+ in a 400-line file, the agent saw no imports or class definitions — it couldn't know what was imported, what class a method belonged to, or what other symbols were available. Now imports and top-level declarations are always visible.

- **Index/export file hint**: New `_index_hint()` — checks `__init__.py` (Python) and `index.ts`/`index.js` (TypeScript) files in the directories of the top-ranked implementation files. If any are found, a "Module export files" hint is added to the OBSERVE prompt. The completeness check in step 5 explicitly references this hint, reminding the agent to add new exports when adding public symbols. Previously the agent might fix the implementation file but forget to export the new symbol, causing import failures at test time.

### Pool refresh
- All repos saturated: 0 new qualifying PRs across phase-rs/phase (132 new in DAS but all fail test-file/issue-link criteria), infiniflow/ragflow (303 new, Go-only without tests or linked issues), vouch, sure, gittensory, allways. Pool holds at 360.

---

## 2026-06-02 — Agent: test-first reasoning (commit dea0933)

### Agent improvement
- **Test-first reasoning**: `OBSERVE_PROMPT` restructured so step 1 is now "Test contract" — the agent enumerates every assertion, every function/class the test calls, and expected input → output *before* planning the implementation
- **Act prompt reinforcement**: ACT_PROMPT now says "mentally verify each test assertion from step 1 maps to a concrete line in your diff" — closes the loop between planning and code
- **Test section label updated**: "read first — these define the contract your implementation must satisfy"
- **Module docstring updated**: reflects new test-first reasoning as first-listed improvement

Key motivation: previous agent could produce a plan that passed casual reading but missed specific assertions. Test-first forces the model to derive what code must exist from what the test checks, rather than writing code and hoping tests agree.

### Registration checklist
- REGISTRATION.md count corrected: 324/13 → 360/20

### Status
- Pool: 360 problems, oracle 22.83 (all repos saturated)
- Agent: test-first reasoning, ranked context, file windowing, repair loop (commit dea0933)
- Dashboard: http://localhost:8082 (serving)
- API: http://localhost:8083 (serving)
- Pending: Gittensor registration, nginx hookup

---

## 2026-06-02 — Pool 354→360: vouch + sure refresh (commit 1c6e3ac)

### Pool expansion (+6 problems)
- Added 3 vouchdev/vouch problems: PR#112 (health checks), PR#114 (logging config), PR#126 (bundle/context sync)
- Added 3 we-promise/sure problems: PR#1473 (transaction split view), PR#1752 (Brex account controller), PR#1753 (account statements controller)
- Oracle mean: 22.77 → 22.83 (recomputed across 360 problems)
- Updated: pool_config.json, leaderboard.json, baselines.json, dashboard_data.json, README, docs/rewards.md, docs/api.md, evaluate.py, gitminer.py, generate_dashboard_data.py, record_result.py
- ragflow: 0 new qualifying PRs (all newer PRs lack linked issues); touchpilot: saturated
- Pool: 354 → 360 problems across 13 repos

---

## 2026-06-02 — Pool 353→354, output behavior fingerprinting (commits e4b623d, 05d05ba)

### Pool expansion (+1 problem)
- Added `infiniflow_ragflow_13217`: "API endpoints for auto-metadata configuration" — SDK API test
- Oracle mean: 22.76 → 22.77 (recomputed across 354 problems)
- Updated across: leaderboard.json, baselines.json, pool_config.json, gitminer.py, generate_dashboard_data.py, record_result.py, docs/rewards.md, docs/api.md, README badge
- entrius/gittensor: saturated (no new qualifying PRs); phase-rs/phase: 0 new qualifying PRs

### Anti-gaming: output behavior fingerprinting (commit 05d05ba)
**Problem**: Source-level similarity (AST bigrams + token Jaccard) can be evaded by agents that forward another agent's output through reformatted wrapper code. The outputs look the same; only the scaffolding code differs.

**Solution**: Per-problem diff hashes stored as behavior fingerprints.
- `evaluate.py` now captures a `diff_hash` per problem (SHA-256 of normalized diff); `--save-behaviors FILE` flag writes `{handle, eval_date, shard, diffs}` fingerprint JSON
- `scripts/check_output_similarity.py`: compares new agent's fingerprint against all stored fingerprints in `results/behaviors/`; flags if ≥ 70% of overlapping problems produce identical diff hashes (min 5-problem overlap)
- `eval.yml`: runs output similarity check after evaluation; artifacts include `behaviors_new.json`
- `record-champion.yml`: commits `results/behaviors/{handle}.json` to repo on merge
- `docs/threat_model.md`: Threat 7 (behavioral cloning) documented with mitigations and residual risk

Three-layer anti-gaming stack now:
1. Source code: token Jaccard + AST structural bigrams
2. Output behavior: per-problem diff hash matching
3. Rate limiting: 5 submissions/handle/week

---

## 2026-06-02 — Pool 352→353, test-symbol ranking (commits 755bd6f, 2ef869b)

### Pool expansion (+1 problem)
- Added `0335` (entrius/gittensor#335): "Looser credibility requirements for tier unlocks" — CLI test
- Oracle mean: 22.80 → 22.76 (recomputed across 353 problems)
- Updated across: leaderboard.json, baselines.json, pool_config.json, evaluate.py, gitminer.py, record_result.py, generate_dashboard_data.py, docs/rewards.md, docs/api.md, README badge

### Agent: test-symbol ranking improvement (commit 2ef869b)
- New `_test_keywords()` extracts identifier tokens from test files — names the tests import/call are the exact symbols the implementation files must contain
- `_rank_files()` now accepts `test_files` param; test-derived symbols weighted 2× in the relevance score (vs 1× for issue tokens)
- Windowing keyword set also includes test symbols — large implementation files now window around tested identifiers, not just issue text
- Net effect: on problems where test imports are specific (e.g. `from gittensor.validator.repo_scan import RepoScanner`), the exact module gets ranked #1 instead of being buried

---

## 2026-06-02 — Pool 349→352, test-repair loop, DAS calibration (commits 2c0e46c, 737cc57)

### Pool expansion (+3 problems)
- `1330` (entrius/gittensor#1330): per-repo `min_token_score` eligibility fix — validator scoring test
- `1354` (entrius/gittensor#1354): `_is_valid_linked_issue` solver attribution bug — scoring test
- `infiniflow_ragflow_15443`: OpenAI-compat streaming duplicate response fix — 202-line Python test
- Oracle mean: 22.81 → 22.80 (recomputed across 352 problems)

### build_pool.py fixes (commit 737cc57)
- `extract_issue_numbers`: regex now matches `Close #N` (not just "closes"), expanded to also cover `close[sd]?` and bare `PR #N` references
- Fallback to GitHub PR body if DAS body has no issue reference — catches maintainer PRs that describe instead of using keywords
- Reordered: GitHub PR fetch now comes before issue extraction for earlier fallback
- `--pr-numbers N,N,...` flag: targeted refresh of specific PRs (requires `--repo`) — much faster than full repo scan

### Agent: test-failure repair loop (commit 2c0e46c)
- `BaseAgent.repair(problem, failed_patch, test_output)`: default impl retries `solve()` with failure context injected into issue body
- `ExampleAgent.repair()`: override — builds a targeted repair conversation showing the exact failed diff + last 3k chars of test output; temperature=0 for precision; one structural validation pass
- `gitminer run --repair N`: after test failure, calls agent.repair() up to N times (--no-sandbox only); shows re-score after each attempt
- Fixed bug: oracle lookup in `cmd_run` used wrong keys (`b["problem_id"]`/`b["score"]` instead of `b["id"]`/`b["base_score"]`)

### DAS calibration display (commit 2c0e46c)
- `gitminer run --score` now shows `DAS ref: X.XX` — the Gittensor validator base score for the reference PR — alongside the local score
- Corrected inflation note: "~3-5× above Docker CI" (was ~2×; measured median ratio is 7x)
- "Avg oracle" label → "Pool mean" (clearer)

## 2026-06-02 — Pool refresh 347→349, score-aware prompts (commits 342d874, 72b622a)

### Pool expansion (+2 phase-rs/phase problems)
- Added `phase-rs_phase_1857` (Terra, Herald of Hope card bug) and `phase-rs_phase_1851` (Exhibition Tidecaller targeting bug).
- Both are Rust game-engine card-mechanic fixes with integration tests — deterministic, high-quality problems.
- Pool: 347 → 349 problems. Oracle mean: 22.85 → 22.81 (recomputed across all 349).
- entrius/gittensor: still saturated. ragflow: 0 new qualifying PRs (no linked issues on newer PRs).

### Example agent: score-aware prompting
- Added scoring explanation to SYSTEM_PROMPT: agents learn that (1) tests gate everything, (2) source-token quality drives the score — complete implementations beat minimal stubs.
- OBSERVE_PROMPT: added "Implementation plan" step (helper functions, error handling, edge cases) and "Completeness check" step (secondary files) to push toward thorough fixes.
- ACT_PROMPT: explicitly guides agent to implement the full fix, not a minimal stub.
- VERIFY_PROMPT: added criterion 5 — "Is the implementation complete?" — can expand a bare fix into a more complete one.
- Net effect: agents tuned to write complete, well-structured code that passes tests AND scores high.

---

## 2026-06-02 — Pool refresh 343→347, score breakdown (commit cdb7b4c)

### Pool expansion (+4 ragflow problems)
- Added `infiniflow_ragflow_15116`, `15118`, `15266`, `15359` — all real API bug fixes with unit tests.
- Pool: 343 → 347 problems. Oracle mean: 22.84 → 22.85.
- Checked entrius/gittensor: 0 new qualifying PRs (saturated at #1407).

### `gitminer run --score` — detailed scoring breakdown
- **Test failure**: now shows last 20 lines of test output so miners know exactly what broke.
- **Test pass**: shows source-token score with ASCII progress bar `[████████░░░░░░░░░░░░]` alongside the final score.
- **Oracle delta**: comparison against this problem's oracle (reference diff score) with ± color.
- **Mean oracle**: comparison against the pool-wide oracle mean (22.85).
- Color-coded: green = beating reference, red = below, cyan = informational.

---

## 2026-06-02 — Context file tree, gitminer info (commits 7238f6e, 0b2e016)

### Context file tree in dashboard drawer
- `generate_dashboard_data.py` now enumerates each problem's `context/` directory and includes `context_files` and `test_files` lists in `data.json`.
- Problem drawer now shows a "Context files — what your agent sees" section: every file listed with 📄 (source) or 🧪 (test) icons. Test files are highlighted in green.
- Summary line: "3 source · 1 test" — miners immediately know what they're working with before cloning anything.
- data.json regenerated and pushed (dashboard commit `0b2e016`).

### `gitminer info ID`
- New CLI command: rich terminal view of a single problem.
- Shows: issue title, repo/PR/issue links, merged date, issue body (truncated), test command, per-problem scores (baseline + DAS), context file tree (source vs test), quick-copy run commands.
- Example: `python gitminer.py info 0463`

### Pool refresh
- Dry-run confirms pool still at 342 problems, 0 new qualifying PRs.

---

## 2026-06-02 — Reward loop closed, docs/rewards.md (commit b6a314f)

### Auto-labeling in CI (`eval.yml`)
- CI now applies `agent-improvement` (2.0× multiplier) automatically on every scored PR.
- If score beats current SOTA: `new-champion` label added + celebration comment posted.
- Labels are created in the repo on first run if they don't exist.
- `issues: write` permission added to the job.

### Auto-record on merge (`record-champion.yml`)
- New workflow fires when an `agent-improvement` PR is merged to main.
- Downloads the eval artifact from the PR; falls back to re-eval if artifact expired.
- Calls `record_result.py` and commits updated `leaderboard.json` / `history.json` back to main.
- Regenerates `data.json` for the dashboard co-located at `../gittensor-miner-dashboard`.

### `docs/rewards.md`
- Full earnings model: score → label → Gittensor emission → TAO.
- Explains label multipliers, time decay, open PR threshold, eligibility requirements.
- Strategy section: how to maximize earnings (beat oracle, submit early, hard problems, tight diffs).
- Hyperparameter reference table linked to official docs.

### API server
- Running persistently at port 8083 (`nohup gitminer.py serve-api`).
- Dashboard docker-compose updated to include `api` service (port 8083) alongside `dashboard` (port 8082).

---

## 2026-06-02 — REST API + mine daemon (commit 019ab38)

### REST API (`api/server.py`, `gitminer serve-api`)

Added a full JSON REST API so miners can fetch benchmark data programmatically — no scraping needed:

- `GET /api/health` — liveness + pool size
- `GET /api/stats` — pool-level stats (language/difficulty distribution, mean baseline, repo count)
- `GET /api/shard` — current weekly 30-problem shard with rotation date
- `GET /api/problems` — paginated, filterable problem list (`?lang=py&difficulty=hard&limit=10&q=search`)
- `GET /api/problems/{id}` — full problem detail (meta, file tree, context paths, DAS scores)
- `GET /api/leaderboard` — ranked submissions

The server uses Python stdlib only (ThreadingHTTPServer + json) — no new deps. CORS-open for browser clients. Launch with `python gitminer.py serve-api [--host HOST] [--port PORT]`.

### Mine daemon (`gitminer mine`)

Added `mine` subcommand — the "idle compute" product concept:

- Runs your agent against the current shard (same eval as CI)
- If you beat the champion: prints commit-reveal hash + step-by-step PR instructions
- `--loop` mode sleeps until next shard rotation (Monday 00:00 UTC) and repeats
- The pitch: point it at your agent and walk away — your machine contributes code, earns TAO, and improves the network's best coding agent

```bash
python gitminer.py mine --agent agent/submissions/myhandle/agent.py --loop
```

### Docs and README

- `docs/api.md`: full API reference with endpoint descriptions, query params, example responses, Python snippet
- README: updated badge (342 problems), added "idle compute" vision paragraph, API + mine examples in CLI section, repo structure updated
- CONTRIBUTING.md: new "Autonomous mining" and "REST API" sections

---

## 2026-06-01 — Repo scaffold live

**Milestone: Initial repo structure created and pushed to GitHub.**

What was built:
- `agent/base.py`: `BaseAgent` interface (Problem → Patch)
- `agent/example/`: minimal single-shot reference agent
- `benchmark/harness/score.py`: local scoring approximation (correctness gate + quality heuristic)
- `benchmark/evaluate.py`: full evaluation runner
- `scripts/curate_problems.py`: tooling to pull benchmark problems from real Gittensor merged PRs
- `docs/scoring.md`: scoring mechanics
- `docs/hyperparameters.md`: full hyperparameter config rationale
- `docs/threat_model.md`: anti-gaming threat model (6 threats, 18 mitigations)
- `hyperparameters.json`: live Gittensor repo config (ready for registration submission)
- `.github/` templates: PR template with commit-reveal, issue templates

**Next steps:**
1. Curate the first batch of ~30 benchmark problems from real Gittensor merged PRs.
2. Run `scripts/curate_problems.py --repo entrius/gittensor` once GitHub API access is confirmed.
3. Test the harness end-to-end with the example agent on one problem.
4. Post Discord milestone once first agent scores across problems.

**Open decision (non-blocking, going with defaults):**
- Frozen model: defaulting to `anthropic/claude-3-5-haiku` via OpenRouter. If a different model or Chutes/whitelist is preferred, please confirm.
- Gittensor scoring engine: using an approximation for local dev. Need location of the validator's native scoring engine to wire it in for CI. Going with approximation until then.

---

## 2026-06-01 — Phase 5: GitHub Actions CI

**Milestone: `.github/workflows/eval.yml` live (commit `3f3dc5e`).**

What was built:
- `detect` job: diffs PR against base, finds `agent/submissions/*/agent.py` changes, extracts handle
- `evaluate` job: sets up Python 3.12, installs deps, runs `scripts/run_eval.py` in Docker sandbox, posts formatted score table as a PR comment (upserts to avoid spam)
- Results uploaded as workflow artifact (30-day retention)
- `agent/submissions/` directory created — the expected landing zone for miner submissions
- Workflow skips gracefully for non-agent PRs (docs, harness changes, etc.)

Comment format: mean score + per-problem pass/fail table + collapsed run details block.

**Remaining:** Phase 6 (Gittensor registration) is on the operator side. Flywheel is ready to receive submissions.

---

## 2026-06-01 — Smoke test + harness hardening (commit `aeb6004`)

**Milestone: End-to-end smoke test confirmed. Harness fixes pushed.**

Ran `score_patch()` on problem 1033 (reference.diff as input). Surfaced two bugs:

1. **test_cmd ran full suite** — all 30 meta.json had `["python", "-m", "pytest", "--tb=short", "-q"]` with no file scope. Each problem's reference.diff already names the exact test files to run. Updated all 30 to scope the test_cmd (e.g. problem 1033 now runs only `tests/validator/oss_contributions/mirror/test_scoring.py`). Result: CI runs ~10x faster per problem; local dev doesn't collect tests that require unrelated heavy deps.

2. **Tests always skipped locally** — Gittensor test files use `pytest.importorskip('gittensor.validator...')` which fires because `bittensor` (a heavy dep) isn't installed locally. pytest exits with code 5 (no tests collected). `run_tests()` treated this as failure. Fixed: `run_tests()` now returns an `all_skipped` flag; exit code 5 with no failures is a soft pass. Result adds `tests_skipped_locally: true` to the score JSON and an honest `scoring_note`. Docker CI installs full deps via pyproject.toml so tests actually run there.

**Confirmed smoke test output (problem 1033, reference.diff):**
```json
{
  "patch_applied": true,
  "tests_passed": true,
  "tests_skipped_locally": true,
  "source_token_score": 12.0,
  "final_score": 4.83,
  "scoring_note": "tests skipped locally (missing heavy deps e.g. bittensor) — quality score estimated from diff; Docker CI runs full correctness check"
}
```

**Waiting on operator:**
1. `OPENROUTER_KEY` as a GitHub Actions secret (CI can't run actual agents without it)
2. `hyperparameters.json` submission to Gittensor team for registration
3. Confirm frozen model preference (default: `claude-3-5-haiku` via OpenRouter)

---

## 2026-06-02 — Pool 325, Product Polished, Awaiting Registration

**Milestone: benchmark is feature-complete and ready for Gittensor registration.**

### What's live

- **325 curated problems** across 20 Gittensor-registered repos — all post-cutoff (merged 2026+), all with linked issues, test files, and DAS reference scores where available.
- **Shard rotation**: 30 problems/eval, deterministic weekly seed so all evaluators see the same shard.
- **Sandboxed harness**: Docker-per-problem, correctness gates before quality scoring, Gittensor's exact scoring formula (constants from `constants.py`).
- **CI pipeline**: eval on PR (score comment upserted), record on merge, champion agent updated on new SOTA, weekly pool refresh (Sunday 02:00 UTC).
- **Static dashboard** live at https://punchthedev.github.io/gittensor-miner-dashboard/ — leaderboard, SOTA chart, problem browser with DAS reference scores + diff viewer, live submission queue.
- **`gitminer` CLI**: `eval`, `hash`, `shard`, `submit`, `parity` subcommands.
- **SOTA-grade docs**: README with badges, CONTRIBUTING.md, threat model, hyperparameter rationale.

### Calibration note

Local harness over-estimates DAS reference scores by median 3.4×. Root cause: tree-sitter counts AST nodes with language weights; local heuristic counts raw diff tokens. Dashboard now shows this note inline in the problem drawer. CI is authoritative.

### Dashboard improvements (dashboard commits c2fb53b, 2cc0f67)

- Reference diff now **auto-loads** when the problem drawer opens — fetched from `raw.githubusercontent.com` (no GitHub API rate limit). Removed the "Load Reference Diff" button.
- Issue bodies now **rendered as markdown** — fenced code blocks, inline code, bold/italic, headings, links, lists. Previously raw escaped text.

### Waiting on operator

1. Verify `OPENROUTER_KEY` in GitHub Actions Environment is the correct production key.
2. Gittensor registration — team handles approval; hyperparameters.json is ready.

---

## 2026-06-02 — CLI DX improvements

- **Repo cache for local eval** (commit 7da8450): `score.py` now maintains `~/.cache/gitminer/repos/` — one clone per unique repo, then git worktrees per problem. Cuts 30-problem `--no-sandbox` eval time dramatically after first run.
- **`gitminer cache`** (commit 7da8450): pre-warms the cache across all 325 problems' repos with progress output.
- **`gitminer problems`** (commit dd41305): list/filter/sort all 325 problems by language, difficulty, repo, or text search. Reads baselines.json for difficulty tier.
- **Better eval summary** (commit b796e28): shows pass rate, language breakdown (Python/JS/Rust/Java pass counts), and failed problem list with test failure hint.

---

## 2026-06-02 — Test file context: agents can now see what tests to pass

- **Problem.test_cmd exposed** (commit aa40095): `test_cmd` field added to the `Problem` dataclass and populated from `meta.json`. Agents now know exactly which test command the harness will run.
- **Test files added to context** (commit aa40095): `build_pool.py` now includes test files referenced in `test_cmd` alongside source files. For newly-added test files (which don't exist at `base_commit`), the content is extracted from the diff itself.
- **42 existing problems enriched** (commit aa40095): `scripts/enrich_test_context.py` retroactively added test files to 42 Python problems (17 entrius/gittensor, 21 infiniflow/ragflow, 4 vouchdev/vouch). Agents on these problems now see the test expectations they must satisfy.
- **Example agent updated** (commit aa40095): `OBSERVE_PROMPT` now shows the test command and asks the model to confirm the fix will pass it in the planning turn.
- **Stray `--output` files removed** from both benchmark and dashboard repos (generate_dashboard_data.py arg bug, already fixed in code).

---

## 2026-06-02 — Eval CI enrichment + oracle score sync

- **Richer eval PR comment** (commit 85da967 → e798f43): CI comment now shows per-problem language (py/js/rs/java), difficulty (easy/medium/hard), baseline ceiling score, and a "vs Baseline" delta column. Summary line shows "N/M beat baseline" and oracle score for direct comparison.
- **Oracle score synced to 22.77** (commit e798f43, c98d80d): leaderboard.json, record_result.py, and generate_dashboard_data.py now all use 22.77 (actual mean of 324 reference diffs). Was 21.60 in leaderboard/record, 22.79 in dashboard generator — all consistent now.
- **Fixed generate_dashboard_data.py arg parsing** (commit 652c46c): CLI `--output path` silently wrote to a file named `--output`. Fixed to use argparse positional arg.
- Dashboard data.json regenerated (dashboard commit 9da35e9).

### Waiting on operator

1. Verify `OPENROUTER_KEY` in GitHub Actions Environment is the correct production key.
2. Gittensor registration — team handles approval; hyperparameters.json is ready.

---

## 2026-06-02 — CLI DX: validate + leaderboard commands

- **`gitminer validate`** (commits 487ede7, daa9456): new command that applies a patch to a problem's base commit and reports PASS/FAIL with diff stat. Uses the repo cache for speed. `--run-tests` also runs the problem's test command locally. Fills the gap between generating a patch and running a full 30-problem eval.
- **`gitminer leaderboard`** (commit 69e7b04): prints current rankings in the terminal without needing to visit the dashboard. Shows oracle score and dashboard link when no ranked submissions exist yet.
- **`--no-sandbox` calibration note** (commit daa9456): eval output now shows a reminder that local heuristic scores run 3–5× above Docker CI scores, so miners interpret them correctly.

### Waiting on operator

1. Verify `OPENROUTER_KEY` in GitHub Actions Environment is the correct production key.
2. Gittensor registration — team handles approval; hyperparameters.json is ready.

---

## 2026-06-02 — Test file enrichment: 217 → 324/324 coverage

- **Extended enrich_test_context.py** (commit 7c38605): added a second pass that scans `reference.diff` for test file paths across all languages (npm, cargo, gradlew, Ruby, Kotlin, etc.). Newly-added test files extracted from the diff; pre-existing ones fetched from GitHub.
- **Enriched 66 more problems**: 217 → 289 problems with test files (by filename), and actually 324/324 when checking full paths (many enriched files live in `tests/` directories).
- **build_pool.py updated** (commit a69f5ac): future pool additions now automatically include test files found in diffs for all languages, not just Python pytest.
- All 324 problems now have test files in context — agents can see what they need to pass.

### Waiting on operator

1. Verify `OPENROUTER_KEY` in GitHub Actions Environment is the correct production key.
2. Gittensor registration — team handles approval; hyperparameters.json is ready.

---

## 2026-06-02 — Oracle eval mode + pool_config fix

- **`gitminer eval --oracle`** (commit a310fc8): new calibration mode that scores reference diffs directly through the full pipeline without any agent or API key. Expected mean ~22.77 / 30. Useful for: (1) verifying the scoring pipeline is wired correctly before spending API credits, (2) giving miners a pipeline smoke test.
- **Fixed `pool_config.json pool_size`** (commit a310fc8): was 325 (stale from before the empty-body problem removal); corrected to 324.
- **Fixed `_oracle_mean()` lookup** (commit a310fc8): was looking for `handle == "oracle"` but leaderboard uses `agent == "Oracle (accepted solution)"`.

### Waiting on operator

1. Verify `OPENROUTER_KEY` in GitHub Actions Environment is the correct production key.
2. Gittensor registration — team handles approval; hyperparameters.json is ready.

---

## 2026-06-02 — gitminer run: single-problem dev loop

Added `gitminer run` command (commit dddee08) — the missing inner development loop tool.

**Why:** Miners had no fast way to inspect what their agent actually produces for a specific problem. The only option was `eval --problems ID`, which runs the full pipeline but shows only a score, not the patch. Dev iteration was slow.

**What ships:**
- `gitminer run --problem ID [--agent PATH]` — runs agent on one problem, prints the generated diff with ANSI color
- `--show-ref` — prints the reference diff below for side-by-side comparison
- `--score [--no-sandbox]` — scores the patch inline, shows baseline delta
- `--output FILE` — saves the patch to disk for `validate` or manual inspection
- `--verbose` — prints the agent's internal reasoning log
- `_print_diff()` helper with color output (red/green/cyan, no-op when not a TTY)

**README + CONTRIBUTING.md** updated with examples.

Pending: OPENROUTER_KEY verification, Gittensor registration.

---

## 2026-06-02 — Improved example agent + calibration correction

### Example agent upgrade (commit 1722327)

Rewrote `agent/example/agent.py` with three meaningful improvements over the old observe→plan→act→verify baseline:

1. **Context file ranking** — `_rank_files()` scores each file by keyword overlap with the issue (paths mentioned, identifiers extracted). Most relevant files go first. `_truncate_context()` caps at 20 files / 40k chars — agents no longer dump all context blindly.

2. **Structural diff validation** — `_diagnose_diff()` goes beyond the basic `@@` presence check. It parses each hunk header against `@@ -N,N +N,N @@` and returns a precise description of the first problem found. The repair loop uses this targeted feedback instead of a generic "invalid diff" message.

3. **Wider repair window** — 3 attempts (up from 2), with format vs. semantic failures handled separately so repair effort isn't wasted on the wrong problem.

### Calibration correction

Updated all 3-5× calibration notes to reflect actual measured data: local scores run ~2× above DAS (measured across 289 reference diffs with known DAS scores: local mean 23.47 vs DAS mean 10.78). Updated in `score.py`, `gitminer.py`, and `results/baselines.json`.

Pending: OPENROUTER_KEY verification, Gittensor registration.

---

## 2026-06-02 — Pool quality, dashboard fix, agent tuning

### Pool quality (benchmark commits 331df8c, 834388e)

- **Removed problem 1187** (entrius/gittensor PR #1187): deletion-only refactor (removes dead `get_github_id` wrapper). Scores 0 on token-overlap regardless of correctness — unusable as a benchmark problem.
- **Added `has_additions()` guard to `build_pool.py`**: future problems must add ≥5 lines. Deletion-only diffs are now filtered out at ingestion.
- Pool: 343 → 342 problems. Oracle mean updated: 22.76 → 22.83.
- Synced oracle score across leaderboard.json, record_result.py, evaluate.py, gitminer.py, generate_dashboard_data.py.

### Dashboard overhaul (dashboard commit f068d1b — previous step)

- Fixed critical `pl is not defined` crash that prevented entire page from rendering.
- Full UI overhaul: loading spinner, sticky header + Submit CTA, gradient stat cards, rank medals, dedicated Allowed Models pill grid, dynamic pool count, table surface cards, graceful error state.
- Docker deployment files added (Dockerfile, docker-compose.yml, systemd unit).

### Example agent tuning (commit 834388e)

- **Verify turn grounded**: VERIFY_PROMPT now shows the original issue title so the model knows what it's validating against (was verifying diff in isolation).
- **temperature=0 for diff turns**: act and repair calls use temp=0 for format precision; planning turn keeps 0.2 for open-ended reasoning.

Pending: nginx hookup, Gittensor registration.

### Example agent: verify prompt enriched (commit 018c97f)

- **Issue body in verify**: VERIFY_PROMPT previously silently discarded `body=problem.issue_body` (passed but not in template). Now shows first 1500 chars of issue body in the verify turn — model has full problem context when checking its diff.
- **Test command in verify**: Added `Test command that must pass: \`{test_cmd}\`` before the diff and as criterion 4. Model now explicitly checks its patch will pass the scoring test, not just that it compiles.
- Scope: small but closed a real gap — the verify turn was semantically disconnected from the problem except for the title.

### Pool refresh audit (2026-06-02)

- Checked new entrius/gittensor PRs: 1360, 1364, 1374, 1381, 1408, 1418 — none qualify.
  - 1360 (bound inline-test regex): has test files, no linked issue in body → skip
  - 1364, 1374 (CLI fixes): linked issue, no test files → skip  
  - 1381, 1408 (issue-discovery fixes): has test files, no linked issue → skip
- Full dry-run: 0 new qualifying problems across all 20 registered repos. Pool remains at 342.

Pending: Gittensor registration (operator action).

## 2026-06-02 — Dashboard hero redesign + agent file windowing

### Dashboard (commit 26a6b76)
- **Hero section**: "Ship code. Earn TAO. Improve the network." — big headline, 2-line pitch, live stats bar (pool size, oracle score, SOTA), 3 CTAs
- **How it works**: 4-step visual (Browse → Build → Submit → Earn) as connected panel grid
- **Quick start terminal block**: 3 commands with syntax coloring, no copy confusion
- **REST API info box**: one-liner explaining the API is available, links to docs/api.md
- **Model pills**: now show short name (e.g. `deepseek-chat`) with full ID in tooltip — was showing verbose `deepseek/deepseek-chat`
- **Leaderboard section**: count badge + "no submissions yet" CTA box when empty
- **Meta**: better title + description tag for SEO/share previews

### Benchmark (commit b5f613b)
- **File content windowing**: `_window_file()` in example agent — for files >300 lines, shows only ±40-line windows around keyword hits with `... [N lines omitted]` markers; lets more files fit in the 40k-char context budget
- **README stale counts fixed**: 324 → 342 in 3 places

### Status
- Dashboard: http://localhost:8082 (serving, commit 26a6b76)
- API: http://localhost:8083 (serving)
- Pool: 342 problems, oracle 22.83
- Pending: Gittensor registration, nginx hookup

## 2026-06-02 — Agent: new impl file detection + is_test_file fixes

### Benchmark (commit f1adaa3)

**New implementation file detection** (33% of pool problems affected)

Found that 132/400 problems (33%) add new source code implementation files via the PR that don't exist at base_commit. Previously the agent had no way to know these needed to be created — it would see the file content in context but not in the file tree, and produce a diff that modifies a non-existent file. `git apply` would fail silently.

Fix:
- `_new_impl_files()`: detects source code files (`.py`, `.go`, `.ts`, `.tsx`, `.js`, `.jsx`, `.kt`, `.java`, `.rb`, `.rs`) in context that are absent from the file tree
- `NEW_IMPL_FILES_TEMPLATE`: new prompt section listing the paths — agent is instructed to create them as new files (`--- /dev/null` format), implemented fully
- `ACT_PROMPT`: explicit reminder about new impl file creation format
- Distinct from test files: agent implements content (doesn't copy verbatim); template lists paths, not diffs

**`_is_test_file` bug fixes** (fixes misclassification of 60+ files)

Previous detection missed:
- Go test files: `nvidia_rerank_test.go` (has `_test.go` suffix, not `_test.py`)
- Paths starting with `tests/` (only detected `/tests/` mid-path, not at root)
- `conftest.py` (pytest fixture file, not an implementation file)

Fixes added: `name.endswith("_test.go")`, `p.startswith("tests/")`, `name == "conftest.py"`, `p.startswith("test/")`, `p.startswith("spec/")`

**`_new_test_diff` no-newline bug fix**

`splitlines()` strips newlines, so `lines[-1].endswith("\n")` was always False — every new test file diff was incorrectly getting the `"\ No newline at end of file"` marker. Fixed to check `f.content.endswith("\n")` on the original content.

### Status
- Benchmark: 400 problems, oracle 23.08 (unchanged)
- Agent improvements: new impl file detection, is_test_file fixes, no-newline fix
- Pending: Gittensor registration, nginx hookup

---

## 2026-06-02 — Agent: post-processing pipeline hardening (commits 27c63e8, d255803)

### Three new post-processing steps in solve() and repair()

**`_strip_line_number_prefixes`** (commit 27c63e8)

LLMs commonly include `N | ` display prefixes from windowed source files in diff context lines, despite the ACT_PROMPT explicitly telling them not to. Example:
```
 42 | def old_function():
```
This fails `git apply` because ` 42 | def old_function():` doesn't exist in any real file. The new function strips these prefixes from context/add/remove lines (not from `diff --git`, `---`, `+++`, `@@`, `\\` lines). Applied before hunk count recomputation.

**`_trim_trailing_prose`** (commit 27c63e8)

After `_extract_diff` finds `diff --git` and grabs everything to end-of-string, models sometimes append prose like "This patch fixes the issue." after the last hunk. `git apply` fails on trailing non-diff text. Walk backwards to the last valid diff line and truncate.

**Sibling import budget raised to 12 KB** (commit 27c63e8)

Go same-package files average 2-4 KB each; the old 6 KB budget cut off after 1-2 siblings, leaving the agent without factory/interface definitions in large Go packages.

### Assertion injection in verify prompt (commit d255803)

`_extract_assertions()` extracts assert/expect/assertEquals lines (up to 30) from all test files and injects them directly into VERIFY_PROMPT. The model now cross-checks each assertion against the diff explicitly, rather than relying on recall from earlier conversation turns.

Recognises assert styles for: Python, Rust (assert_eq!, assert!), Go (assert.Equal, t.Errorf), TypeScript (expect(), toBe, toHaveBeenCalled), Kotlin/Java (assertEquals, assertThat, verify).

### Status
- Benchmark: 400 problems, oracle 23.08 (unchanged)
- Pool: all repos saturated — next check 2026-06-09
- Pending: Gittensor registration, nginx hookup

## 2026-06-02 — Agent: verify hardening + timeout reliability (commits 4d97f89, 361fdde)

### New-file presence check in verify (criterion 6) (commit 4d97f89)

When the problem requires new files (`new_tests` or `new_impls`), the verify prompt now lists them explicitly under "Required new files" and adds criterion 6: "Does the diff add ALL N required new file(s) as `new file mode 100644` blocks?" Previously verify had no visibility into new-file requirements — it would say LGTM even if the agent forgot to add a required new file, which immediately fails the test command. Affects ~60% of pool problems (new test files) and ~33% (new impl files).

### Verify body snippet extended 1500 → 3000 chars (commit 4d97f89)

The issue body is now passed up to 3000 characters to the verify step (was 1500). Requirements stated after character 1500 were invisible to verify, causing incomplete-implementation misses on longer issues.

### Partial repair: feedback loop instead of silent break (commit 4d97f89)

When verify returns a diff covering fewer files than the current diff, the previous behavior was `break` — accepting the unchanged multi-file diff silently. Now: targeted feedback is sent ("your fix only covered N/M files, include all M files in your response") and the loop continues. Gives the model a chance to produce a complete multi-file correction rather than just keeping the unverified original.

### Timeout retry in `_call` (commit 361fdde)

`httpx.TimeoutException` was previously unhandled — it propagated up from `solve()` and the benchmark's broad except gave the problem a 0 score. Now: retry once on timeout; on a second timeout return `""`. The `_diagnose_diff` → format-repair path handles empty strings gracefully without aborting the problem.

### Status
- Benchmark: 423 problems, oracle 23.36 (unchanged)
- Pool: all repos saturated — next check 2026-06-09
- Pending: Gittensor registration, nginx hookup

## 2026-06-02 — Agent: line numbers for all source files + Rust sibling expansion (commit 004b8c7)

### Line numbers for all source files (commit 004b8c7)

Root cause found: `_window_file` added `N | ` line-number prefixes only when a file exceeded the 300-line windowing threshold. Files under 300 lines (a majority of pool context files) were shown without any line numbers, forcing the model to count manually from the top to determine `@@ -N` hunk offsets. Manual counting under time pressure is a significant source of offset errors.

Fix: when `show_line_numbers=True` and the file is not windowed, the output now also uses `N | content` format. Test files (shown with `show_line_numbers=False`) are unaffected — they don't get line numbers since the agent doesn't write diffs against them.

Also updated ACT_PROMPT: "windowed **source** files show lines as `N | content`" → "all source files show lines as `N | content`" to match the new universal behavior.

The `_strip_line_number_prefixes` post-processor already handles this format, so models that copy `N | ` prefixes into the diff are cleaned correctly.

### Rust `use super::module` sibling import expansion (commit 004b8c7)

`_expand_sibling_imports` now handles Rust `.rs` files. When a ranked impl file contains `use super::module_name;` or `use super::module_name::Symbol;` references, the expansion resolves them to `module_name.rs` or `module_name/mod.rs` in the same directory and promotes them to context if they exist in both `all_impl` and the file tree.

Previously: 0 sibling expansion for Rust (57 pool problems). Go, Python, JS/TS all had sibling expansion — Rust was the only language left out. Now consistent across all 5 main languages.

Also added Ruby-aware header end detection in `_compute_header_end` (last `require`/`require_relative` line + 8-line buffer) as defensive code for when Ruby problems are added to the pool.

### Status
- Benchmark: 430 problems, oracle 23.46 (unchanged)
- Pool: all repos saturated — next check 2026-06-09
- Pending: Gittensor registration, nginx hookup

### Verify criterion 8: structural summary symbol check (commit 00084ff)

After history compaction the verify model has access to the "File signatures in scope" section (function/class/method declaration lines) injected into the compact observe. Previously no verify criterion explicitly directed the model to cross-reference this section against the diff — the structural summary was available in context but not actively consulted.

VERIFY_PROMPT criterion 8 added: "Look at the 'File signatures in scope' section from earlier in this conversation. If the issue requires adding or modifying a specific function/method, confirm that symbol appears in your diff as a `+` line (e.g. `+def foo`, `+func Foo`, `+fn foo`). If a required symbol is absent, add it."

This closes the loop: the structural summary (added two steps ago) now has a criterion that actively invokes it. The verify model can now answer "Did the diff add `+def filter_repos`?" rather than only checking test assertions and hunk offsets.

### Hunk source context extended to 10 hunks (commit 00084ff)

`_hunk_source_snippets(max_hunks=6)` → `max_hunks=10`. Large diffs (multi-file, many hunks) had the first 6 hunks verified against actual source lines and the rest verified only by plausibility. Each hunk snippet is ~300 chars; extending from 6 to 10 adds ~1.3 KB to the verify prompt — well within the 25k-token budget.

### Status
- Benchmark: 430 problems, oracle 23.46 (unchanged)
- Pool: all repos saturated — next check 2026-06-09
- Pending: Gittensor registration, nginx hookup

## 2026-06-02 — Agent: _fix_new_starts (commit 0508f3b)

### +c new-start recalculation (commit 0508f3b)

Root cause: `_fix_hunk_offsets` corrects `-N` (old-start) values and `_fix_hunk_counts` corrects `b`/`d` (line counts). But `+c` (new-start) was never recalculated — whatever the LLM wrote was kept verbatim even after `-N` was moved.

For a valid diff, `+c` must equal `old_start + cumulative_delta` where `cumulative_delta = sum(new_count - old_count)` for all prior hunks in the same file. A stale `+c` causes `git apply` to fail on multi-hunk diffs where offset correction moved any `-N`.

Fix: `_fix_new_starts()` as stage 7 of `_post_process` — runs after `_fix_hunk_counts` so it sees final counts. Resets delta to 0 at each `diff --git` boundary. Skips new-file hunks (`@@ -0,0`). Verified with smoke tests:
- Single file, 2 hunks: hunk 1 adds 3 lines → hunk 2 `+c` correctly becomes `30 + 3 = 33`
- Multi-file: delta resets at file boundary
- New-file hunk: `@@ -0,0 +1,N @@` left unchanged

### Status
- Benchmark: 430 problems, oracle 23.46 (unchanged)
- Pool: all repos saturated — next check 2026-06-09
- Pending: Gittensor registration, nginx hookup
