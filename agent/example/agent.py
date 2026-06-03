"""
Reference agent: ranked-context observe → plan → act → verify loop.

Demonstrates the scaffolding pattern — same frozen model, better wrapper.
Miners compete to outperform this baseline.

Scoring model: correctness gates quality. Tests must pass first; then the
score is driven by `benchmark_score = test_pass_rate × relative_score ×
anti_gaming_multiplier × test_quality_factor`. `relative_score` is the
agent's AST token score divided by the oracle's, so complete, well-structured
implementations earn more than minimal stubs that barely pass tests.

Improvements over a naive single-shot approach:
- Test-first reasoning: plan step analyzes what each test assertion requires before
  deciding what to implement — anchors the implementation to the ground truth
- Import-path resolution: test file import statements are parsed to identify the
  exact implementation files under test; those files are pinned to the top of the
  ranked list (Python ``from foo.bar import X``, TypeScript relative imports, Ruby
  require_relative) — more reliable than keyword matching alone
- Context files ranked by keyword relevance: issue tokens + test-file symbols
  (names the tests import/call are 2× weighted — they pinpoint the module under test)
  over-long context truncated rather than blindly dumped into the prompt
- Large files windowed to relevant sections only (±40 lines around keyword hits)
  so more files fit in the context budget without blowing the token limit;
  omission markers show exact line ranges (e.g. "lines 21-260 omitted — next
  visible line is 261") so the model can write accurate @@ -N hunk offsets
- Explicit file-and-line hypothesis required plus secondary-file completeness
  check so the implementation is thorough, not minimal
- Language-specific system-prompt notes: Go/Rust/TypeScript/Ruby/Python/Kotlin/Java
  remind the model of language conventions (trait bounds, exports, type hints,
  companion objects, interface implementations) that generic instructions miss
- Score-aware prompting: system prompt and act prompt explain that complete
  implementations score higher than stubs
- Structural diff validation beyond the basic `@@` presence check — catches
  malformed hunk headers before committing to the result; windowed files now
  show `N | line content` so the model can read `@@ -N` offsets directly
- Issue title tokens weighted 3× over body tokens in file ranking (titles name
  the exact function/module; bodies describe the symptom)
- Repair loop shows first+last lines of test output (assertion error at top,
  summary at bottom) rather than only the last N lines
- Verify criteria cross-check `@@ -N` line numbers against `N |` markers,
  check for missing imports, and expand bare stubs
- Wider repair window (3 attempts, up from 2) with failure-mode categorization
- Structured reasoning log for transparency
- `_is_test_file` detects Kotlin/Java/Scala test classes (e.g. FooTest.kt)
- Kotlin/Java import resolution in `_resolve_test_imports`: maps `import dev.foo.Bar`
  to `Bar.kt` or `Bar.java` in the file tree
- Sibling import expansion: after ranking, scans the top-3 implementation files for
  local imports (``from .helpers import X``, ``from pkg.sub.helpers import X``,
  TypeScript relative imports, same-dir Go files) and adds those sibling modules to
  context (up to 6 KB). Prevents the agent from hallucinating helper functions that
  already exist in the package.
- New test file detection: compares context test files against file_tree (repo state
  at base_commit). Files that are in context but NOT in file_tree are new files added
  by the PR — they don't exist yet and must be created in the diff. The agent is
  shown pre-formatted diff blocks to copy verbatim. Affects ~60% of pool problems.
- Test file windowing: large test files (> 200 lines) are windowed with a ±80-line
  context window around keyword hits, preventing a single large test suite from
  consuming most of the 40 KB context budget. The threshold is lower than for impl
  files (200 vs 300) and the window wider (80 vs 40) to preserve complete test
  function bodies. Files that fit in 200 lines are shown in full.
- New implementation file detection: same logic applied to non-test source files.
  When a PR adds a new implementation file (e.g. a new Go driver or Python module),
  the agent is explicitly notified to create it, with a concrete format example
  (``new file mode 100644``, ``--- /dev/null`` header, ``@@ -0,0 +1,N @@``).
  Affects ~33% of pool problems.
- Hunk count auto-fix: after every diff generation, `_fix_hunk_counts()` recomputes
  the b/d fields in each `@@ -a,b +c,d @@` header from the actual content lines.
  LLMs frequently miscalculate these counts; incorrect counts cause `git apply` to
  reject otherwise correct diffs. This is a deterministic post-processor — no API
  calls, no model changes.
- Line-number prefix stripping: `_strip_line_number_prefixes()` removes `N | `
  display artifacts from diff content lines. When source files show `  42 | def foo():`,
  models sometimes copy that prefix into the diff context lines, causing git apply to
  fail because ` 42 | def foo():` doesn't exist in any real file. Applied before hunk
  count recomputation so counts reflect the final content.
- Trailing prose trimming: `_trim_trailing_prose()` removes non-diff text after the
  last hunk line. Models sometimes append an explanation like "This patch fixes the
  issue." after the final hunk; git apply rejects that trailing text. Applied after
  extraction, before hunk count fix.
- Sibling import budget raised to 12 KB (from 6 KB): Go same-package files average
  2-4 KB each; the old limit cut off after 1-2 files, leaving the agent without
  factory or interface definitions it needs.
- Rust sibling import expansion: `_expand_sibling_imports` now handles `use super::module`
  patterns in `.rs` files, resolving to `module.rs` or `module/mod.rs` in the same
  directory. Previously Rust problems got no sibling expansion — 57 pool problems affected.
- Kotlin/Java/Scala sibling expansion: `_expand_sibling_imports` now includes same-directory
  `.kt`/`.java`/`.scala` files for JVM problems. JVM classes in the same Gradle source dir
  share the same package and reference each other directly; the same-directory heuristic
  mirrors the Go same-package approach. Affects 37 touchpilot/touchpilot Kotlin problems.
- Assertion injection in verify: `_extract_assertions()` pulls the assert/expect/assertEquals
  lines (up to 50) from test files and injects them directly into the verify prompt. The
  model no longer relies on conversation context to recall what assertions must pass —
  they're explicitly listed so the model can check each one against the diff.
- Non-uniform timeout allocation: plan gets 15% of wall-clock budget (~18s), act gets 40%
  (~48s), each verify/repair gets 15% (~18s). Previously uniform budget (120s/6=20s) was
  too tight for act (large multi-file diffs) and wasted time on plan (short analysis output).
- Multi-fence diff extraction: `_extract_diff()` now collects ALL fenced diff blocks and
  joins them. When models split each changed file into its own ` ```diff ` block, the
  previous `re.search` only captured the first block and silently dropped the rest.
- Post-process every intermediate diff: `_post_process()` (strip N| artifacts + trim
  trailing prose + fix hunk counts) is called after every `_extract_diff` throughout the
  solve and repair loops, not only at the end. Verify always sees clean, artifact-free
  diffs with correct hunk counts — eliminating spurious format-repair iterations caused by
  the model copying display prefixes into its own output and then reacting to them.
- History compaction before verify: after the act step, `history[1]` (the observe message
  containing all source files + file tree, typically 20-30k chars) is replaced with a
  compact summary (~150 chars). The model has already used the full context to produce its
  plan and diff; re-sending it on every verify/repair call wastes token budget the model
  could use to reason about the diff. The compact version preserves essential metadata:
  repo name, issue title, files in scope, and test command.
- Partial-repair guard in verify: when the verify step produces a corrected diff that covers
  fewer files than the current diff, the replacement is rejected and the current diff is kept.
  Without this guard, a partial correction (e.g. the model fixes only fileA out of a
  fileA+fileB diff) would silently drop fileB's changes, producing a worse patch than before.
- Language-aware header in windowed files: `_compute_header_end()` scans the file for the
  end of its import block (Go `import (...)`, Python `from … import`, TypeScript `import`,
  Rust `use`, Kotlin/Java/Scala `import`) and always includes that block plus a post-import
  buffer of 8 lines. The old fixed HEADER_LINES=20 cut off mid-import-block in Go files
  (which routinely have 25-40-line import sections), so the model never saw struct/type
  definitions that immediately follow. Now the header extends as far as needed to cover the
  full import section and the first top-level type declarations. Same fix applied to the
  no-keyword-hit peek (was always 80 lines; now max(language_header, 80)).
- Sibling import scan expanded from top 3 to top 5 ranked files: larger multi-file problems
  where the most relevant file is ranked 4th or 5th now benefit from sibling expansion too.
- JavaScript / JSX support: LANG_NOTES["js"] and ["jsx"] added — covers export/module
  patterns, null-safety, and async style reminders for JS problems (gittensor-ui,
  product-data-extractor, ragflow JS issues); previously these got no language guidance.
- Scala support: LANG_NOTES["scala"] with trait/sealed/case-class reminders;
  `_is_test_file` recognises `*Spec.scala`; `_compute_header_end` handles `.scala` imports;
  `_resolve_test_imports` resolves Scala JVM-style imports to `.scala` source files.
- Hunk map in plan step (step 6): asks the model to list each planned change with its
  file path and `N |` start line before writing the diff, pre-computing `@@ -N` offsets
  so the ACT step can use them directly rather than re-deriving under time pressure. ACT
  prompt references the hunk map to focus attention on using the pre-computed line numbers.
- Line numbers for small (non-windowed) files: `_window_file` now adds `N | ` prefixes
  even for files under the 300-line windowing threshold. Previously only windowed files
  showed line numbers — small files required the model to count manually to determine
  `@@ -N` offsets, causing off-by-one errors. All implementation source files now show
  consistent `N | content` formatting regardless of size.
- Missing `--- a/` / `+++ b/` header auto-insert: `_fix_diff_headers()` detects file blocks
  that jump straight from `diff --git` to a `@@` hunk without the required path headers and
  inserts them. `git apply` requires these headers; models in repair mode often omit them.
  New-file blocks use `--- /dev/null` for the old path. Applied as part of `_post_process`.
- Fuzzy hunk-offset correction: `_fix_hunk_offsets()` takes the context files as a lookup
  and, for each hunk, extracts 2+ consecutive context lines (unchanged lines before/after
  the change), searches for them within ±30 lines of the stated `@@ -N` offset in the
  actual file content, and corrects N if the match is unambiguous. Handles off-by-N errors
  that `_fix_hunk_counts` cannot fix (it only corrects b/d counts, not the start offset).
  Safe fallback: if no match or multiple matches, the original N is kept.
- Context line whitespace repair: `_fix_context_lines()` replaces context lines that differ
  from the source only in whitespace (tabs vs spaces, stripped trailing whitespace). `git
  apply` rejects hunks where context lines don't match exactly — even a single space/tab
  difference causes failure. Applied after `_fix_hunk_offsets` so the start offset is
  already correct; only replaces when the stripped content matches exactly (safety guard
  ensures we never silently move a hunk to the wrong location). This is stage 5 of 6 in
  `_post_process`.
- Verify: new-file presence check (criterion 6): when the problem requires new files to be
  created (`new_tests` or `new_impls`), the verify prompt lists them explicitly and asks the
  model to confirm each is present as a `new file mode 100644` diff block. Previously verify
  had no way to know about required new files — it would say LGTM even if the agent forgot to
  add a file. Affects ~60% of pool problems (new test files) and ~33% (new impl files).
- Verify body snippet extended 1500 → 3000 chars: issue requirements stated after character
  1500 were invisible to the verify step, causing it to miss completeness checks for longer
  issue bodies.
- Partial repair: feedback loop instead of silent break: when verify returns a valid diff that
  covers fewer files than the current diff, previously the loop would break and submit the
  multi-file original silently. Now it sends targeted feedback ("your fix only covered N/M
  files, include all M") and continues the verify loop — giving the model a chance to produce
  a complete multi-file correction.
- Timeout retry in `_call`: previously an `httpx.TimeoutException` propagated as an unhandled
  exception, causing the entire problem to fail with 0. Now the call is retried once on timeout;
  on a second timeout the function returns `""`, which `_diagnose_diff` catches as an empty diff
  and the format-repair loop handles gracefully rather than aborting.
- `_fix_context_lines` extended to removal lines: `git apply` requires `-` (removal) lines to
  match the source exactly, not just context (` `) lines. The same whitespace-correction logic
  now applies to removal lines — if the stripped content matches but whitespace differs, the `-`
  line is replaced with `- {source_line}`. Same safety guard: only replaces on exact stripped-
  content match to avoid silently misplacing the removal.
- Verify criterion 7: hunk-map completeness check added to `VERIFY_PROMPT`. Explicitly asks the
  model to look back at its step 6 hunk map and confirm every planned file appears in the diff.
  Previously the model could LGTM a diff that omitted a file it had planned to change.
- `_extract_diff` fence regex generalised: was triple-backtick(?:diff|patch)? — now accepts any
  fence language tag (triple-backtick + any word chars). Handles text, udiff, unidiff fences, etc.
  so diffs wrapped in non-standard fences are extracted rather than silently dropped.
- API error resilience in `_call`: OpenRouter sometimes returns a 200 with an error body
  (e.g. `{"error": {"message": "No endpoints found..."}}` instead of `choices`) — previously
  this caused a `KeyError: 'choices'` that propagated as an exception, scoring the problem 0.
  Now `_call` checks for `choices` presence and retries once; on a second failure returns `""`.
  Also retries 400 responses (content policy, transient routing errors) once before giving up.
- Verify prose-critique feedback loop: when the verify step returns a textual critique but no
  corrected diff, previously the loop broke immediately — accepting the unverified diff. Now the
  critique is stored in history and the loop continues, letting the model self-correct by
  producing a diff on the next iteration (still within the budgeted MAX_REPAIR_ATTEMPTS calls).
- Conditional history compaction: the observe message (source files, 20-30k chars) is now
  only compacted to a 150-char summary if the act step produced a valid diff. When the act step
  times out or returns empty, the source files are kept in context so repair iterations can
  produce a correct diff from scratch. Without this, API-timeout cascades left all repair
  attempts with only the issue title and file names — insufficient to write code.
- Empty-act retry: when the repair loop detects "empty output — no diff produced" (act step
  returned nothing), instead of sending the useless REPAIR_FORMAT_PROMPT with an empty diff
  to fix, it resends ACT_PROMPT directly — giving the model another full act-step attempt
  with the complete source-file context still available. Triggers a history compaction on
  success so subsequent verify steps don't re-process the full source context.
- Plan-early-act extraction: when the model produces a valid diff inside the PLAN response
  (i.e. acts before the explicit ACT prompt), extract it directly and skip the ACT API call.
  Previously the ACT step returned nothing because the model thought it already answered in
  the plan — causing 3 empty-retry repair loops and a wasted API budget. Now the plan diff
  is detected via `_looks_valid`, stored in history as the ACT turn, and passed directly to
  verify. Saves 4 API calls (~1 ACT + 3 empty-retries) on this failure mode.
- Trailing whitespace stripped from `+` and context diff lines: added `_strip_diff_trailing_whitespace`
  as the final step of `_post_process`. Models generate blank continuation lines as `+    ` (with
  spaces) instead of `+` (empty), causing `git apply` to fail with "corrupt patch" when the source
  file lacks matching trailing whitespace. Safe to strip `+`/` ` lines; `-` lines are never touched
  (they must match the file exactly for git apply to work).
- Verify token budget raised to match act: `verify_tokens = act_tokens` (was `token_budget //
  4`). When the verify step must produce a corrected diff rather than LGTM, it needs the same
  token headroom as the act step. The old 12,500-token cap could truncate a large multi-file
  corrected diff, producing a partial patch worse than the original.
- `_extract_assertions` limit raised from 30 to 50: large test suites often place edge-case
  assertions near the end (parameterised tests, negative cases). The old 30-line cap silently
  dropped them, leaving the verify step blind to those requirements. 50 covers the typical
  test suite without materially inflating the verify prompt size.
- `_fix_hunk_offsets` search radius expanded from ±25 to ±50: large Go/TS files (500+ lines)
  are more likely to have offsets that are more than 25 lines off when the model estimates from
  a windowed view. The unambiguous-match safety guard (single match required) prevents false
  positives — a wider radius finds more correct offsets without introducing wrong ones.
- Verify prose-critique follow-up: when the verify step returns a textual critique (no corrected
  diff extracted), the next iteration previously re-sent the full VERIFY_PROMPT with the same
  diff (~4-6KB repeated context) and all 7 criteria. Now it sends VERIFY_FOLLOWUP_PROMPT — a
  short "produce the corrected diff now" message (~80 chars). The model already has its analysis
  in context; asking it to output the diff is more directed and saves significant token budget
  on every prose-critique retry path.
- Verify body snippet: head + tail for long issues. The full observe context is compacted
  after the act step, leaving the verify prompt as the model's only view of the issue body.
  Previously `body[:3000]` could miss requirements near the end of a long issue (31% of
  pool problems exceed 3000 chars; max 16200). Now shows `body[:2500] + "[...]" + body[-500:]`
  for bodies > 3000 chars — preserving both the opening requirements and the trailing edge-case
  details/gotchas. Total length stays ~3000 chars.
- Hunk source context injected into verify: `_hunk_source_snippets()` extracts the actual
  source file lines at each hunk's `@@ -N` offset and injects them into the verify prompt.
  After history compaction the verify model has no access to source files, so criterion 2
  (hunk offset check) was previously a plausibility guess — "do the context lines look like
  surrounding code?" — rather than a real check. Now the verify prompt shows e.g.:
  `[src/drivers/mistral.go @@ -45] → 45: return nil, fmt.Errorf("not implemented")`, giving
  the model what it needs to spot wrong offsets and context-line whitespace mismatches that
  `_fix_hunk_offsets` / `_fix_context_lines` post-processors may not have caught. Limited
  to 6 hunks (~1 KB addition to the verify prompt) to keep token usage small.
- Structural summary in compact history: `_structural_summary()` extracts function/class/method
  declaration lines from implementation files and injects them into the compacted observe
  message used during verify/repair. Previously, after history compaction the verify model
  only saw file names ("files in scope: scoring.py, constants.py") with no knowledge of
  what functions/classes those files contain. The structural summary shows e.g.:
  `[scoring.py ← changed] / def compute_score / def apply_penalty / def filter_repos`
  so the verify model can check: "Does the diff add every required symbol?" and "Is there
  a function that should have been modified but wasn't?" — completeness checks that file
  names alone cannot support. Prioritises changed files (marked "← changed") over unchanged
  ones; capped at ~3 KB total so it doesn't blow the verify prompt size budget. Functions
  `_extract_file_signatures()` and `_changed_paths_from_diff()` support this.
- Verify criterion 8: structural summary symbol check. VERIFY_PROMPT now explicitly asks the
  model to look at the "File signatures in scope" section in the compacted history and confirm
  that any function/method required by the issue appears in the diff as a `+` line. Previously
  the structural summary was injected into history but no criterion directed the verify model
  to cross-reference it against the diff. Now the model actively checks: "Is `+def foo` (or
  `+func Foo`, `+fn foo`) present?" before LGTMing — catching cases where the plan added a
  symbol to the hunk map but the act step forgot to implement it.
- Hunk source context extended to 10 hunks (was 6): `_hunk_source_snippets` now covers the
  first 10 hunks across all files instead of 6. For large diffs (multi-file, many hunks) the
  old cap left the later hunks without source verification — the verify model could only
  plausibility-check their offsets rather than comparing against actual source lines. At ~300
  chars per hunk snippet the increase adds ~1.3 KB to the verify prompt, well within budget.
- `_fix_hunk_offsets` stripped-content fallback: `find_context_offset` previously used exact
  string matching for context-line fingerprints. If the model wrote context lines with wrong
  indentation (tabs vs spaces), the fingerprint wouldn't match the source, and offset correction
  silently failed. Then `_fix_context_lines` would fix the whitespace, but the offset remained
  wrong — `git apply` still fails with a wrong `@@ -N`. Fix: two-pass search — exact first,
  then stripped-content fallback when exact finds zero matches. Same unambiguous-match guard
  (exactly one match required) applies to both passes. If the exact pass was ambiguous (multiple
  matches), the stripped fallback is skipped to avoid false positives. Empty-stripped fingerprints
  are also rejected to prevent trivial matches on blank lines.
- `_fix_new_starts`: recalculates the `+c` (new-file start line) for every hunk after
  `_fix_hunk_offsets` and `_fix_hunk_counts` have corrected `-N` and counts. The `+c` field
  was previously never touched — whatever the LLM wrote was kept verbatim. But `+c` must equal
  `old_start + cumulative_delta` where cumulative_delta = sum(new_count - old_count) for all
  prior hunks in the same file. A stale `+c` causes `git apply` to fail on multi-hunk diffs
  where the LLM wrote offsets before or after offset correction moved them. Stage 7 of
  `_post_process`; runs after `_fix_hunk_counts` so it sees the final corrected counts.
  New-file hunks (`@@ -0,0`) are skipped.
- `repair()` source file injection: the repair method now injects original source file content
  for all files touched by the failed diff. Previously the model repaired blind — it saw the
  diff it produced and the test error, but not the actual file state. With source context it
  can spot off-by-one logic errors, missing branches, and wrong type annotations. Capped at
  3 files × 4 KB each (12 KB max) to keep the repair prompt compact. Files not in the problem
  context (e.g. generated or vendored files) are silently skipped.
- `_extract_assertions` Ruby Minitest `refute` patterns: added `refute `, `refute_equal `,
  `refute_nil `, `refute_includes `, `refute_match `, `refute_empty `, plus parenthesized
  `refute_equal(`, `refute_nil(`, `refute_includes(`, `refute_match(`, `refute_empty(`.
  The 37 `we-promise/sure` pool problems use Minitest, which has symmetrical
  `assert`/`refute` negation assertions.
- `_extract_assertions` Ruby Minitest `assert_*` patterns: added `assert_equal`,
  `assert_nil`, `assert_includes`, `assert_match`, `assert_raises`, `assert_empty`,
  `assert_respond_to`, `assert_kind_of`, `assert_instance_of` — both space and parens forms.
  Previously `assert ` only matched bare `assert condition`; Minitest's `assert_equal expected,
  actual` starts with `assert_` (underscore), so was silently skipped. All 37 `we-promise/sure`
  pool problems are now covered for both `assert_*` and `refute_*` patterns.
- `_extract_assertions` deduplication: the same assertion line appearing in multiple test files
  now counts only once toward the 50-line limit. Cross-file duplicate assertions (shared helpers,
  parameterised test setup blocks) no longer waste lines that could show unique edge cases.
- `_window_file` no-hit path now adds line numbers when `show_line_numbers=True`: when a long
  file has no keyword matches, the header fallback (import block + first type defs) was returned
  without `N | ` line-number prefixes — inconsistent with every other windowing path. Fixed: the
  same `{i:{width}d} | line` format is now applied to the no-hit header section too, so the
  model sees consistent line numbers regardless of whether keyword hits were found.
- `_extract_assertions` Python unittest.TestCase patterns: added `self.assertEqual(`,
  `self.assertNotEqual(`, `self.assertTrue(`, `self.assertFalse(`, `self.assertIsNone(`,
  `self.assertIsNotNone(`, `self.assertIn(`, `self.assertNotIn(`, `self.assertRaises(`,
  `self.assertAlmostEqual(`, `self.assertGreater(`, `self.assertGreaterEqual(`,
  `self.assertLess(`, `self.assertLessEqual(`, plus `pytest.raises(` (both direct and `with` forms).
  Root cause: `self.assert*` does not start with `assert ` (has `self.` prefix), so every
  Python test that uses `unittest.TestCase` subclass methods was silently skipped, leaving
  the verify step blind to the actual test requirements.  521 occurrences in pool.
- `_fix_diff_headers` new-file `--- /dev/null` correction: for blocks with `new file mode 100644`,
  the old `---` line is now corrected to `--- /dev/null` if the model wrote `--- a/<path>` instead.
  Previously the function only inserted `--- /dev/null` when the `---` line was absent entirely.
  If the model wrote `--- a/newfile.py` (wrong), git apply tries to read a file that doesn't exist
  yet and fails with "no such file or directory".  226/430 pool problems require new files (53%).
- `_extract_assertions` mock/spy assertion contains-check: added secondary `_ASSERT_CONTAINS`
  tuple checked via `in` (not `startswith`), covering `mock_obj.assert_called_once_with(...)`,
  `.assert_not_called()`, `.assert_any_call()`, `.assert_has_calls()`.  Root cause: mock
  assertions appear as `variable.method.assert_*()` — the variable name is not fixed, so prefix
  matching is impossible.  452 occurrences in pool; now visible to the verify cross-check.
- `_extract_assertions` async Jest/Vitest + Node.js assert module patterns: added
  `await expect(` (async Jest/Vitest expectations — 1,627 occurrences in pool across 52
  problems, completely invisible before), `assert.equal(`, `assert.deepEqual(`,
  `assert.notEqual(`, `assert.throws(`, `assert.match(`, `assert.doesNotMatch(` (Node.js
  built-in assert module, distinct from Go testify's `assert.Equal`), and `t.Error(` (Go
  standard testing non-fatal counterpart to `t.Fatal`).  Root causes: `await expect(` starts
  with `await`, not `expect`, so the bare `expect(` prefix missed every async assertion;
  Node.js `assert.*` uses lowercase which doesn't match testify's `assert.Equal(` (uppercase).
  Affected repos: jsonbored/gittensory (31 problems), jsonbored/awesome-claude (21 problems),
  infiniflow/ragflow async test suites, and any Go test using `t.Error`.
- `_extract_assertions` keyword-windowing for large test files: when `keywords` is provided
  and a test file exceeds 200 lines, `_window_file` (±80 lines around keyword hits) is applied
  before scanning for assertions. Root cause: for large test files like `api.test.ts` in
  jsonbored/gittensory (562 assertions per file), `_extract_assertions` previously always
  captured the FIRST 50 assertion lines — the old, existing tests at the top of the file.
  The newly-added assertions being tested by the specific issue appear AFTER the existing ones,
  typically in a keyword-relevant section (they reference the new function/endpoint name from
  the issue title). Windowing ensures the 50 captured assertions are from the correct region,
  giving the verify step meaningful ground truth to cross-check the diff against.
  Passes `keywords` to `_extract_assertions` at the call site in the verify loop.
- Verify loop: `pending_partial_repair` flag prevents back-to-back user messages. When the
  model returns a partial repair (fewer files than the current diff), the loop appends a
  "missing files" user message and sets `pending_partial_repair = True`. On the next
  iteration, the loop calls the model directly without prepending another user message —
  previously it appended VERIFY_PROMPT a second time, creating two consecutive user messages
  which can cause a 400 error on strict backends (e.g. DeepSeek via OpenRouter) and confuses
  the model about which diff is current.  Root cause: the `pending_prose_critique` mechanism
  handled the prose-critique case correctly, but the symmetric partial-repair case had no
  corresponding guard.
- Assertion pre-extraction in plan step: `_extract_assertions()` is now called before the
  OBSERVE_PROMPT is sent, and the extracted assertions are injected as
  `PLAN_ASSERTIONS_SECTION_TEMPLATE` between the test files and source files sections.
  This gives the model a concise, deduplicated checklist of what the tests actually assert
  before it performs its step-1 analysis (test contract), reducing the risk that a large
  windowed test file causes the model to miss critical assertion lines that were outside
  the keyword-matched window. The section is omitted when no recognizable assertions are
  found (older test styles without standard assert functions).
"""

from __future__ import annotations

import os
import re
import textwrap
import time

import httpx

from agent.base import BaseAgent, FileContext, Patch, Problem

DEFAULT_MODEL = os.environ.get("BENCHMARK_MODEL", "deepseek/deepseek-chat")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
REFERER = "https://github.com/PunchTheDev/gittensor-base-miner"

MAX_REPAIR_ATTEMPTS = 3
# Worst-case call count: plan + act + verify + repair × MAX_REPAIR_ATTEMPTS
MAX_CALLS = 3 + MAX_REPAIR_ATTEMPTS

# Context window guards: never send more than this many files or chars of context.
MAX_CONTEXT_FILES = 20
MAX_CONTEXT_CHARS = 40_000

# Per-file size cap used in budget accounting: files over the windowing threshold
# (300 lines ≈ 12 KB typical) get windowed down to ~6-10 KB in the prompt.
# Counting raw size for budget dramatically underestimates how many files can fit
# (270/400 pool problems exceed 40 KB raw but compress to ~20 KB windowed).
# Using this cap lets the ranker pass more files through to the windowing step.
MAX_FILE_BUDGET_CHARS = 10_000


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an expert software engineer. You receive a GitHub issue and the \
relevant source files, and your job is to produce a correct, complete fix \
as a valid unified diff.

Scoring note: your patch is scored on (1) test correctness — it must pass — \
and (2) AST token quality — the count of meaningful code nodes you add to \
non-test source files. Correctness is the gate; quality determines your rank.

What scores higher: complete function bodies with proper error handling, \
input validation and guard clauses for invalid/empty/boundary inputs, type \
annotations (Python, TypeScript, Kotlin), named helper functions, well-named \
constants, and enum/match exhaustiveness. A 40-line fix that handles every \
edge case scores much higher than a 5-line stub with the same test pass rate. \
Docstrings, comments, and blank lines do NOT count toward the score — only \
executable code nodes matter.
"""

OBSERVE_PROMPT = """\
## Issue: {title}

{body}

## Repository: {repo}

## Scoring test command
```
{test_cmd}
```
The harness runs this command to determine correctness. Your patch must make it pass.

## File tree
```
{tree}
```
{init_hint}{test_section}{new_test_section}{plan_assertions_section}## Source files (ranked by relevance)
{impl_files}

---

Analyse this test-first, then plan. Answer in order:

1. **Test contract** — what exactly does the test assert? List each assertion, \
   the function/class/method it calls, the expected input → output or behaviour. \
   This is the ground truth your implementation must satisfy.
2. **Root cause** — given the test contract, what is currently missing or wrong in \
   the source files?
3. **Hypothesis** — which specific file(s) and line range(s) need to change? Be exact. \
   If "New test files" are listed above, your diff must also add them. \
   If "New implementation files" are listed above, your diff must create each one.
4. **Implementation plan** — starting from the test contract, describe what you will \
   add/change: function signatures, return types, helper logic, error handling, \
   edge cases. Every assertion in the test must map to something in your plan.
5. **Completeness check** — what secondary files or side effects (imports, exports, \
   constants, type annotations) also need updating? If you add a new public symbol, \
   check whether any `__init__.py` or `index.ts`/`index.js` listed in the \
   "Module export files" section above needs a new export line.
6. **Hunk map** — for every change you plan, state: file path, the `N |` start line \
   from the source display above, and what's being added/removed. Example: \
   `mistral.go:45 — replace Embed stub with real HTTP call (adds ~30 lines)`. \
   This pre-computes your `@@ -N` offsets so the diff is correct on the first try.

Be precise and thorough — a complete implementation that handles all test cases and \
edge cases scores higher than a minimal stub. Remember: the diff is scored by AST \
token count in non-test source files. More complete code (edge case handling, type \
annotations, named helpers) scores higher — but only after tests pass. Plan for \
both correctness and completeness.
"""

TEST_SECTION_TEMPLATE = """\
## Test files (read first — these define the contract your implementation must satisfy)
{test_files}

"""

NEW_TEST_FILES_TEMPLATE = """\
## New test files — MUST be added to your diff

These test files were added by the PR and do NOT exist in the repo at base commit. \
The harness runs `{test_cmd}` after applying your diff — if these files are missing \
from the diff, the test command fails immediately with a "file not found" error and \
correctness score is 0.

Copy the diff blocks below verbatim into your output (after your implementation \
changes) — do not modify their content:

{new_test_diffs}

"""

NEW_IMPL_FILES_TEMPLATE = """\
## New implementation files — MUST be created in your diff

These source files do NOT exist in the repo at base commit — they are new files \
added by this PR. Your diff must add each one as a new file. If any are missing, \
the test command will fail with an import or "file not found" error.

Files to create:
{new_impl_paths}

Use this exact format for each new file (replace N with total lines added):

```
diff --git a/path/to/file.ext b/path/to/file.ext
new file mode 100644
index 0000000..0000000
--- /dev/null
+++ b/path/to/file.ext
@@ -0,0 +1,N @@
+first line of file
+second line
+...
```

Implement each file fully based on the issue requirements and test contract — do \
not leave stubs. The source files section above shows the expected structure.
"""

ACT_PROMPT = """\
Based on your analysis above, produce the unified diff.

Before writing: use the hunk map from step 6 of your analysis — each entry gives \
you the file path and `@@ -N` start line directly. Cross-check every test assertion \
from step 1 maps to a concrete line in your diff; add any that are missing.

Requirements:
- Start with `diff --git a/<path> b/<path>`
- Include `--- a/<path>` and `+++ b/<path>` headers
- Each hunk starts with `@@ -<start>,<count> +<start>,<count> @@`
- **Line numbers**: all source files show lines as `  N | content`. Use \
  these numbers directly for `@@ -N` offsets. The numbers are display-only — do \
  NOT include ` N | ` in your diff; write the actual file content only. Test files \
  do not have line numbers since you do not write diffs against them.
- **Context lines**: include exactly 3 unchanged lines before and after each \
  change — copy them verbatim from the source file display (same characters, \
  same whitespace) — even a space/tab difference causes `git apply` to fail
- Every test assertion from your plan must be satisfied by your diff
- Include helper functions, proper error handling, and secondary file changes
- **New test files**: if the prompt shows "New test files", include them verbatim \
  as new-file additions (see format in that section)
- **New implementation files**: if the prompt shows "New implementation files", \
  add each one as a new file (`new file mode 100644`, `--- /dev/null`, \
  `+++ b/<path>`, `@@ -0,0 +1,N @@`) — implement fully, no stubs
- Do NOT change unrelated logic, but do implement the full fix as described
- **Quality matters**: the diff is scored by AST token count in non-test files. \
  Guard against invalid/nil/empty inputs, add type annotations where the language \
  supports them, split complex logic into named helpers. More complete code = \
  higher score. Docstrings and comments do NOT count — only executable code nodes.
- Output ONLY the diff — no markdown fences, no prose
"""

VERIFY_PROMPT = """\
Issue: {title}

{body}

Test command that must pass: `{test_cmd}`
{assertions_section}{new_files_section}\
You produced this diff:

```diff
{diff}
```
{hunk_source_section}
Check it against these criteria:
1. Does the diff satisfy every test assertion listed above? Map each one to a concrete line.
2. Are `@@ -N` hunk offsets correct? The source context section above shows the actual \
   file lines at each hunk offset — verify that the context lines in your diff match \
   exactly (same content, same whitespace). Wrong offsets cause `git apply` to fail.
3. Are there missing changes or accidental deletions that would break unrelated tests?
4. Are all new symbols, functions, or classes properly imported in every file that uses them?
5. Is the implementation production-quality? Specifically: are edge cases handled \
   (invalid/nil/empty inputs, boundary values, error paths)? Are type annotations \
   present where the language supports them (Python, TypeScript, Kotlin)? Could a \
   named helper function make the logic clearer while adding meaningful tokens? \
   If the implementation is a minimal stub that only handles the happy path — expand \
   it so it handles real-world usage, then return the improved diff.
6. {new_files_check}
7. Look back at your step 6 hunk map from earlier in this conversation. Does this diff \
   include a change for every file path listed there? If any planned file is missing \
   from the diff, add the necessary changes now.
8. Earlier in this conversation there is a "File signatures in scope" section listing \
   functions and methods in each file. If the issue requires adding or modifying a \
   specific function/method, confirm that symbol appears in your diff as a '+' line \
   (e.g. `+def foo`, `+func Foo`, `+fn foo`). If a required symbol is absent, add it.

If the diff is correct and complete, respond with exactly: LGTM

If it needs fixing, respond with the corrected diff only (no prose, starts with `diff --git`).
If the implementation is a bare minimum that should be more thorough, expand it and respond with the improved diff.
"""

HUNK_SOURCE_SECTION_TEMPLATE = """\

Source context at hunk offsets (actual file lines — verify your diff context lines match):
{snippets}
"""

NEW_FILES_VERIFY_SECTION_TEMPLATE = """\
Required new files (each MUST appear in the diff as `new file mode 100644`):
{files}

"""

ASSERTIONS_SECTION_TEMPLATE = """\
Key test assertions (from context — each must pass after your diff):
```
{assertions}
```

"""

PLAN_ASSERTIONS_SECTION_TEMPLATE = """\
## Test assertions (auto-extracted — use these in step 1 of your plan)
```
{assertions}
```

"""

TEST_REPAIR_PROMPT = """\
Your patch was applied but the test suite failed.

Issue: {title}

Test command: `{test_cmd}`

Your diff:
```diff
{diff}
```

Test output:
```
{test_output}
```
{source_section}\
Diagnose the failure. The most common causes are:
- Wrong logic: assertion error shows expected vs actual value
- Missing symbol: `ImportError`, `NameError`, or `AttributeError` — add the import or define the symbol
- Wrong line numbers in diff: hunk didn't apply → check file line numbers
- Incomplete implementation: test calls a function/method that isn't defined yet

Then produce a corrected unified diff that fixes the root cause and makes the tests pass.

Requirements:
- Start with `diff --git a/<path> b/<path>`
- Include correct `--- a/<path>` and `+++ b/<path>` headers
- Each hunk starts with `@@ -<start>,<count> +<start>,<count> @@`
- Output ONLY the diff — no markdown fences, no prose
"""

REPAIR_FORMAT_PROMPT = """\
The diff you produced is not a valid unified diff.

Problem: {problem}

Your last diff:
```
{diff}
```

Fix the specific problem listed above and output a corrected unified diff \
starting with `diff --git` and containing at least one `@@` hunk. Nothing else.
"""

VERIFY_FOLLOWUP_PROMPT = """\
Based on your analysis above, produce the corrected unified diff now.
Do not repeat the analysis. Output ONLY the diff — starts with `diff --git`, \
no markdown fences, no prose.
"""

# Language-specific notes appended to SYSTEM_PROMPT when detected
LANG_NOTES: dict[str, str] = {
    "py": (
        "This is a Python codebase. Key reminders: add type annotations "
        "(parameters and return types) to new or modified functions — they improve "
        "readability and score; add docstrings to new public functions/classes; "
        "ensure all new imports appear at the top of the file; handle edge cases "
        "with explicit guard clauses rather than silent fallbacks."
    ),
    "rs": (
        "This is a Rust codebase. Key reminders: trait bounds must be satisfied; "
        "match all enum variants; do not leave `todo!()` or `unimplemented!()` stubs; "
        "add `pub` to functions/structs that must be reachable from tests; "
        "import new symbols with `use` in every file that references them."
    ),
    "ts": (
        "This is a TypeScript codebase. Key reminders: update type definitions and "
        "interfaces when you add or change fields; add named exports for new symbols; "
        "check `index.ts` files for re-exports; strict null checks are on — "
        "handle undefined/null at every call site."
    ),
    "tsx": (
        "This is a TypeScript/React codebase. Key reminders: update prop types; "
        "add exports for new components; handle null/undefined in JSX expressions."
    ),
    "js": (
        "This is a JavaScript codebase. Key reminders: add named exports for new "
        "symbols (`export function foo` or `export const foo`); check `index.js` "
        "files for re-exports; handle undefined/null at every call site; do not "
        "use TypeScript syntax (no type annotations, no `interface`); use `const`/"
        "`let` — never `var`; use `async/await` or `.then()` consistently with the "
        "surrounding code style."
    ),
    "jsx": (
        "This is a JavaScript/React codebase. Key reminders: add exports for new "
        "components; handle undefined/null in JSX expressions; use prop-types if "
        "the existing codebase does; no TypeScript syntax."
    ),
    "rb": (
        "This is a Ruby codebase. Key reminders: follow snake_case naming; "
        "include modules where methods are defined; use `attr_accessor`/`attr_reader` "
        "for new fields; ensure `require` or `require_relative` for any new file."
    ),
    "go": (
        "This is a Go codebase. Key reminders: implement every method required by the "
        "interface the test calls (check *_test.go files for the full signature set); "
        "register the new driver in the factory function (often in factory.go) if the "
        "test uses a factory or enum lookup; export names start with a capital letter; "
        "add necessary imports with the exact package path shown in existing imports; "
        "return named error types, not bare strings; zero-value structs must satisfy "
        "interface constraints — all methods must be implemented, no `panic(\"TODO\")`."
    ),
    "kt": (
        "This is a Kotlin/Android codebase. Key reminders: data classes must declare "
        "all fields the tests access; sealed classes and enums must cover every variant "
        "the tests reference; companion object constants (e.g. tool names) must match "
        "exactly what the test checks; add `@Test` annotation to new test helpers when "
        "asked; do not leave `TODO()` stubs — implement the full body; add the correct "
        "`import` for any new class or function you reference; if the test instantiates "
        "a class directly, ensure its primary constructor matches what the test uses."
    ),
    "java": (
        "This is a Java codebase. Key reminders: implement every method of any interface "
        "the test uses — no partial implementations; add the correct `import` statements "
        "at the top of every file that references a new class; public classes must match "
        "their filename exactly; use `@Override` on interface method implementations; "
        "checked exceptions must be declared or caught — don't swallow them silently."
    ),
    "scala": (
        "This is a Scala codebase. Key reminders: traits and abstract classes must have "
        "all abstract methods implemented — no partial overrides; use `override def` for "
        "trait implementations; case classes auto-generate equals/hashCode/copy; "
        "companion objects hold factory methods and implicits; add the correct `import` "
        "for any new symbol; sealed traits must cover every subcase the pattern-matches "
        "reference; avoid `???` (NotImplementedError) stubs — implement fully."
    ),
}


def _detect_lang(test_files: list) -> str | None:
    """Return the dominant file extension from test files, or None."""
    from collections import Counter
    exts = Counter(
        f.path.rsplit(".", 1)[-1].lower()
        for f in test_files
        if "." in f.path
    )
    if not exts:
        return None
    top, _ = exts.most_common(1)[0]
    return top


# ---------------------------------------------------------------------------
# Context ranking
# ---------------------------------------------------------------------------


def _new_test_files(
    test_files: list[FileContext],
    file_tree: list[str] | None,
) -> list[FileContext]:
    """Return test files that are NOT present in the file tree at base commit.

    These are files added by the PR itself — they don't exist when the harness
    checks out base_commit, so the agent's diff must create them.  The test
    command will fail with "file not found" if they are absent.
    """
    if not file_tree:
        return []
    tree_set = set(file_tree)
    return [f for f in test_files if f.path not in tree_set]


def _new_impl_files(
    impl_files: list[FileContext],
    file_tree: list[str] | None,
) -> list[FileContext]:
    """Return non-test source files that are NOT present in the file tree at base commit.

    These are new files added by the PR — they must be created in the diff.
    Only returns files with code extensions (not config or data files).
    """
    if not file_tree:
        return []
    CODE_EXTS = {".py", ".go", ".ts", ".tsx", ".js", ".jsx", ".kt", ".java", ".rb", ".rs"}
    tree_set = set(file_tree)
    return [
        f for f in impl_files
        if f.path not in tree_set
        and any(f.path.endswith(ext) for ext in CODE_EXTS)
    ]


def _format_new_test_files(files: list[FileContext]) -> str:
    """Render new test files in a format that makes it easy to copy into a diff."""
    parts = []
    for f in files:
        lang = f.language or ""
        parts.append(f"### {f.path}\n```{lang}\n{f.content}\n```")
    return "\n\n".join(parts)


def _new_test_diff(files: list[FileContext]) -> str:
    """Build the diff hunks for new test files so the model can copy them exactly.

    Generating the diff here (rather than asking the model to reconstruct it)
    eliminates a whole class of formatting errors when the model tries to
    re-encode the file line-by-line in diff format.
    """
    parts = []
    for f in files:
        lines = f.content.splitlines()
        n = len(lines)
        hunk_lines = [f"+{ln}" for ln in lines]
        # splitlines() strips newlines, so check the original content directly
        if lines and not f.content.endswith("\n"):
            no_newline = "\\ No newline at end of file"
        else:
            no_newline = None
        body = "\n".join(hunk_lines)
        block = (
            f"diff --git a/{f.path} b/{f.path}\n"
            f"new file mode 100644\n"
            f"index 0000000..0000000\n"
            f"--- /dev/null\n"
            f"+++ b/{f.path}\n"
            f"@@ -0,0 +1,{n} @@\n"
            f"{body}"
        )
        if no_newline:
            block += f"\n{no_newline}"
        parts.append(block)
    return "\n".join(parts)


def _is_test_file(f: FileContext) -> bool:
    """Return True if this file is a test/spec file (not source to modify)."""
    p = f.path.lower()
    name = p.rsplit("/", 1)[-1]
    return (
        # In a test directory (leading or mid-path)
        p.startswith("test/") or p.startswith("tests/") or p.startswith("spec/") or p.startswith("specs/")
        or "/test/" in p or "/tests/" in p or "/spec/" in p or "/specs/" in p
        # Python: test_foo.py, foo_test.py
        or name.startswith("test_") or name.endswith("_test.py")
        # Go: foo_test.go
        or name.endswith("_test.go")
        # TypeScript/JS: foo.test.ts, foo.spec.tsx
        or ".test." in name or ".spec." in name
        # Ruby: foo_spec.rb
        or name.startswith("spec_") or name.endswith("_spec.rb")
        # Kotlin/Java/Scala: FooTest.kt, FooTest.java, FooSpec.scala
        or re.search(r"(test|spec)\.(kt|java|scala)$", name) is not None
        # pytest conftest
        or name == "conftest.py"
    )


def _test_keywords(test_files: list[FileContext]) -> set[str]:
    """Extract identifier tokens from test files to guide implementation file ranking.

    The names the tests import, instantiate, or call are the exact symbols the
    implementation files must contain — treating them as high-signal keywords
    lets the ranker surface the right files faster than issue text alone.
    """
    combined = " ".join(f.content for f in test_files)
    raw = re.findall(r"\b([a-z_][a-z0-9_]{3,}|[A-Z][A-Za-z0-9]{3,})\b", combined)
    return {t.lower() for t in raw}


def _resolve_test_imports(
    test_files: list[FileContext],
    file_tree: list[str],
) -> set[str]:
    """Return file paths that test files directly import, confirmed against the file tree.

    Tests import exactly what they test — resolving those imports gives a near-certain
    list of the implementation files that need changing.

    Handles:
    - Python: ``from foo.bar.baz import X`` → ``foo/bar/baz.py``
    - TypeScript/JS: ``import { X } from './utils/helpers'`` → resolved relative path
    - Ruby: ``require_relative '../lib/foo'`` → resolved relative path
    - Rust: ``use crate::foo::bar;`` → ``src/foo/bar.rs`` or ``src/foo/bar/mod.rs``
    - Kotlin/Java/Scala: ``import dev.foo.bar.MyClass`` → ``src/main/.../MyClass.kt|java|scala``
    """
    tree_set = set(file_tree)
    resolved: set[str] = set()

    for tf in test_files:
        path = tf.path
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        test_dir = path.rsplit("/", 1)[0] if "/" in path else ""
        content = tf.content

        if ext == "py":
            for m in re.finditer(r"^(?:from|import)\s+([\w.]+)", content, re.MULTILINE):
                candidate = m.group(1).replace(".", "/") + ".py"
                if candidate in tree_set:
                    resolved.add(candidate)

        elif ext in ("ts", "tsx", "js", "jsx"):
            # ES module: `from './foo'`; CommonJS: `require('./foo')`
            for m in re.finditer(r"""(?:from|require\()\s*['"]([^'"]+)['"]""", content):
                raw = m.group(1)
                if not raw.startswith("."):
                    continue
                parts = (test_dir + "/" + raw).split("/")
                norm: list[str] = []
                for seg in parts:
                    if seg == "..":
                        if norm:
                            norm.pop()
                    elif seg and seg != ".":
                        norm.append(seg)
                base = "/".join(norm)
                for suffix in (".ts", ".tsx", ".js", ".jsx", "/index.ts", "/index.js"):
                    candidate = base + suffix
                    if candidate in tree_set:
                        resolved.add(candidate)
                        break

        elif ext == "rb":
            for m in re.finditer(r"""require(?:_relative)?\s+['"]([^'"]+)['"]""", content):
                raw = m.group(1)
                base_raw = (test_dir + "/" + raw) if not raw.startswith("/") else raw.lstrip("/")
                parts = base_raw.split("/")
                norm = []
                for seg in parts:
                    if seg == "..":
                        if norm:
                            norm.pop()
                    elif seg and seg != ".":
                        norm.append(seg)
                base = "/".join(norm)
                for suffix in ("", ".rb"):
                    candidate = base + suffix
                    if candidate in tree_set:
                        resolved.add(candidate)
                        break

        elif ext == "rs":
            # `use crate::foo::bar;` or `use super::baz;` or `use engine::game::X;`
            # Heuristic: strip crate-level prefix and try src/<path>.rs or src/<path>/mod.rs
            for m in re.finditer(r"^use\s+([\w:]+)", content, re.MULTILINE):
                module = m.group(1)
                # Drop leading crate:: or super:: — we only know the path segments
                segments = re.split(r"::", module)
                # Skip single-segment (e.g. `use std;`) and crate/super keywords
                segments = [s for s in segments if s not in ("crate", "super", "self", "std", "core")]
                if len(segments) < 2:
                    continue
                # Try src/<segments>.rs and src/<segments>/mod.rs
                path_base = "src/" + "/".join(segments)
                for suffix in (".rs", "/mod.rs"):
                    candidate = path_base + suffix
                    if candidate in tree_set:
                        resolved.add(candidate)
                        break
                # Also try without "src/" prefix — some crates are flat
                path_base2 = "/".join(segments)
                for suffix in (".rs", "/mod.rs"):
                    candidate = path_base2 + suffix
                    if candidate in tree_set:
                        resolved.add(candidate)
                        break

        elif ext == "go":
            # `import "github.com/org/repo/internal/foo"` → files in internal/foo/
            # Extract the part after the module root (trim github.com/org/repo/ prefix)
            for m in re.finditer(r'"([^"]+)"', content):
                raw = m.group(1)
                if raw.startswith("github.com/") or raw.startswith("golang.org/"):
                    # Drop up to the 3rd path segment (org/repo), keep the rest
                    parts = raw.split("/")
                    if len(parts) > 3:
                        local_path = "/".join(parts[3:])
                        # Match any .go file in that directory
                        for f in tree_set:
                            if f.startswith(local_path + "/") and f.endswith(".go"):
                                resolved.add(f)

        elif ext in ("kt", "java", "scala"):
            # `import dev.touchpilot.app.tools.AndroidToolRetryPolicy` →
            # look for any file named `AndroidToolRetryPolicy.kt` or `.java` anywhere
            # in the tree (JVM packages don't map 1:1 to directory paths across projects).
            # Same pattern applies for Scala imports.
            for m in re.finditer(r"^import\s+([\w.]+)", content, re.MULTILINE):
                fqn = m.group(1)
                # Skip standard library and well-known third-party packages
                if fqn.startswith(("kotlin.", "java.", "android.", "androidx.",
                                    "org.junit", "kotlin.test", "org.mockito",
                                    "io.mockk", "com.google", "scala.", "org.scalatest",
                                    "cats.", "zio.", "akka.")):
                    continue
                class_name = fqn.rsplit(".", 1)[-1]
                if not class_name or not class_name[0].isupper():
                    continue  # skip package-level imports without a class name
                # Match any .kt, .java, or .scala file whose basename matches the class name
                for f in tree_set:
                    basename = f.rsplit("/", 1)[-1]
                    if basename in (class_name + ".kt", class_name + ".java", class_name + ".scala"):
                        resolved.add(f)
                        break

    return resolved


def _expand_sibling_imports(
    selected: list[FileContext],
    all_impl: list[FileContext],
    file_tree: list[str],
    char_budget: int = 12_000,
) -> list[FileContext]:
    """Add sibling modules that top-ranked files locally import from.

    When a high-priority file imports from a sibling module in the same
    package (e.g. ``from gittensor.cli.issue_commands.helpers import X`` or
    ``from .helpers import X``), the sibling likely contains utilities the
    agent should use rather than redefine.  Without this expansion the agent
    has no way to discover that ``emit_error_json`` already exists in
    ``helpers.py``, so it either hallucinates a definition or omits the import.

    Adds at most ``char_budget`` additional characters of sibling content so
    the overall context budget isn't blown.  Budget is 12 KB (raised from 6 KB)
    because Go same-package files average 2-4 KB each, so 6 KB only allowed
    one or two siblings before cutting off — insufficient for packages with
    multiple factory/interface files.
    """
    all_by_path = {f.path: f for f in all_impl}
    already = {f.path for f in selected}
    tree_set = set(file_tree)
    added: list[FileContext] = []
    chars_used = 0

    for f in selected[:5]:  # follow imports from top 5 ranked files
        ext = f.path.rsplit(".", 1)[-1].lower() if "." in f.path else ""
        file_dir = f.path.rsplit("/", 1)[0] if "/" in f.path else ""
        content = f.content

        siblings: list[str] = []

        if ext == "py":
            # Relative: ``from .helpers import X`` → sibling in same dir
            for m in re.finditer(r"^from\s+(\.[\w.]*)\s+import", content, re.MULTILINE):
                raw = m.group(1).lstrip(".")
                if raw:
                    candidate = (file_dir + "/" if file_dir else "") + raw.replace(".", "/") + ".py"
                    if candidate in tree_set and candidate not in already:
                        siblings.append(candidate)
            # Absolute within same package: ``from pkg.sub.helpers import X``
            pkg_prefix = file_dir.replace("/", ".")
            for m in re.finditer(r"^from\s+([\w.]+)\s+import", content, re.MULTILINE):
                raw = m.group(1)
                if not raw.startswith(".") and pkg_prefix and raw.startswith(pkg_prefix + "."):
                    tail = raw[len(pkg_prefix) + 1:]
                    candidate = file_dir + "/" + tail.replace(".", "/") + ".py"
                    if candidate in tree_set and candidate not in already:
                        siblings.append(candidate)

        elif ext in ("ts", "tsx", "js", "jsx"):
            # ES module: `from './helpers'`; CommonJS: `require('./helpers')`
            for m in re.finditer(r"""(?:from|require\()\s*['"](\.[^'"]+)['"]""", content):
                raw = m.group(1)
                parts = (file_dir + "/" + raw).split("/")
                norm: list[str] = []
                for seg in parts:
                    if seg == "..":
                        if norm:
                            norm.pop()
                    elif seg and seg != ".":
                        norm.append(seg)
                base = "/".join(norm)
                for suffix in (".ts", ".tsx", ".js", ".jsx"):
                    candidate = base + suffix
                    if candidate in tree_set and candidate not in already:
                        siblings.append(candidate)
                        break

        elif ext == "go":
            # Same-package Go files are in the same directory — include all .go
            # source files in the directory that aren't test files.
            for path in tree_set:
                if (
                    path.startswith(file_dir + "/")
                    and path.endswith(".go")
                    and not path.endswith("_test.go")
                    and path not in already
                ):
                    siblings.append(path)

        elif ext == "rs":
            # Rust: `use super::module_name;` references a sibling in the same dir.
            # `use super::module_name::Symbol;` — same, just one level deeper.
            for m in re.finditer(r"^use\s+super::([a-z_][a-z0-9_]*)", content, re.MULTILINE):
                mod_name = m.group(1)
                for suffix in (f"{mod_name}.rs", f"{mod_name}/mod.rs"):
                    candidate = (file_dir + "/" if file_dir else "") + suffix
                    if candidate in tree_set and candidate not in already:
                        siblings.append(candidate)
                        break

        elif ext in ("kt", "java", "scala"):
            # JVM languages: classes in the same source directory share the same
            # package and reference each other directly without explicit import paths
            # that resolve neatly to file paths (Gradle source sets, nested packages).
            # Simplest and safest heuristic: include all same-extension files in
            # the same directory — mirrors the Go same-package approach.
            for path in tree_set:
                if (
                    path.startswith(file_dir + "/")
                    and path.endswith(f".{ext}")
                    and path not in already
                ):
                    siblings.append(path)

        for sib_path in siblings:
            sib = all_by_path.get(sib_path)
            if sib is None:
                continue
            size = len(sib.path) + len(sib.content)
            if chars_used + size > char_budget:
                break
            added.append(sib)
            already.add(sib_path)
            chars_used += size

    return added


def _prune_file_tree(
    file_tree: list[str],
    context_files: list[FileContext],
    char_cap: int = 3_000,
) -> list[str]:
    """Return a compact, relevant subset of the repository file tree.

    Large repos (ragflow, phase) have 500+ entries in file_tree.  At ~32 chars
    per path that's 16+ KB of prompt budget showing paths the agent will never
    touch.  This function keeps only paths that share a directory with a context
    file (or an ancestor of that directory), so the agent sees the local package
    structure without the full repo listing.

    Falls back to a character-capped prefix of the full tree if no useful
    context can be derived.
    """
    def _cap(paths: list[str], cap: int, total_count: int) -> list[str]:
        result: list[str] = []
        used = 0
        for p in paths:
            ln = len(p) + 1
            if used + ln > cap:
                omitted = total_count - len(result)
                if omitted > 0:
                    result.append(f"... ({omitted} more files)")
                break
            result.append(p)
            used += ln
        return result

    if not context_files or not file_tree:
        return _cap(file_tree, char_cap, len(file_tree))

    # Build set of relevant directory prefixes from context files:
    # for each context file, its directory and all ancestor directories.
    # Root-level context files mark "" as relevant.
    relevant_dirs: set[str] = set()
    for f in context_files:
        parts = f.path.split("/")
        # Root-level file: add empty string so root-level siblings are visible
        if len(parts) == 1:
            relevant_dirs.add("")
        for depth in range(1, len(parts)):
            relevant_dirs.add("/".join(parts[:depth]))

    # Keep tree entries whose immediate parent directory is in relevant_dirs
    kept = [
        p for p in file_tree
        if (p.rsplit("/", 1)[0] if "/" in p else "") in relevant_dirs
    ]

    # If pruning reduced the list meaningfully, cap and return the relevant subset
    if 0 < len(kept) < len(file_tree) * 0.7:
        return _cap(kept, char_cap, len(kept))

    # Pruning had little effect, or kept is empty (all context is in a test dir
    # with no siblings in the tree) — fall back to capped full list
    return _cap(file_tree, char_cap, len(file_tree))


def _index_hint(top_files: list[FileContext], file_tree: list[str]) -> str:
    """Return a prompt hint listing __init__.py / index.ts|js files in the same
    directories as the top implementation files.

    When a new public symbol is added to a Python module, callers typically
    import from the package `__init__.py`. Similarly for TypeScript `index.ts`.
    This hint reminds the agent to check whether those files need a new export.
    """
    # Collect directory paths of the top-ranked files (up to first 5)
    dirs: list[str] = []
    seen: set[str] = set()
    for f in top_files[:5]:
        d = f.path.rsplit("/", 1)[0] if "/" in f.path else ""
        if d not in seen:
            dirs.append(d)
            seen.add(d)

    index_names = {"__init__.py", "index.ts", "index.js", "index.tsx", "mod.rs"}
    found: list[str] = []
    tree_set = set(file_tree)
    for d in dirs:
        for name in index_names:
            path = f"{d}/{name}" if d else name
            if path in tree_set:
                found.append(path)

    if not found:
        return ""
    paths = ", ".join(f"`{p}`" for p in found)
    return (
        f"\n**Module export files** (may need a new export if you add a public symbol): "
        f"{paths}\n\n"
    )


def _rank_files(
    files: list[FileContext],
    issue_title: str,
    issue_body: str,
    test_files: list[FileContext] | None = None,
    file_tree: list[str] | None = None,
) -> list[FileContext]:
    """Return files sorted by keyword relevance to the issue, most relevant first.

    Test files are excluded here — they're shown in a separate section.
    Files directly imported by test files receive the highest boost (they are
    almost certainly the files that need changing). Secondary signals: file
    paths mentioned in the issue text, and keyword density from both issue
    tokens and identifier tokens extracted from test files.
    """
    issue_text = (issue_title + " " + issue_body).lower()

    # Explicit file paths mentioned in the issue — strong relevance signal
    mentioned_paths = set(re.findall(r"[\w/.-]+\.(?:py|ts|js|rs|go|java|kt|rb|cpp|c|h)", issue_text))

    # Identifier tokens from the issue (snake_case, camelCase, UPPER_CASE)
    # Title tokens weighted 3×: issue titles are precise ("fix RepoScanner.scan") vs
    # body prose that often describes the symptom rather than the cause.
    title_raw = re.findall(r"\b([a-z_][a-z0-9_]{3,}|[A-Z][A-Za-z0-9]{3,})\b", issue_title)
    body_raw = re.findall(r"\b([a-z_][a-z0-9_]{3,}|[A-Z][A-Za-z0-9]{3,})\b", issue_body)
    title_kws = {t.lower() for t in title_raw}
    body_kws = {t.lower() for t in body_raw}

    # Additional keywords from test files — tested symbols are in the impl files
    test_kws = _test_keywords(test_files) if test_files else set()

    # Direct imports from test files: near-certain signal for which file needs changing
    import_pinned = (
        _resolve_test_imports(test_files, file_tree)
        if test_files and file_tree else set()
    )

    def score(f: FileContext) -> float:
        # Pin directly-imported files to the top of the list
        import_bonus = 100.0 if f.path in import_pinned else 0.0
        path_lower = f.path.lower()
        # High bonus if the file is explicitly mentioned in the issue text
        path_score = 20.0 * sum(1 for mp in mentioned_paths if mp in path_lower)
        content_lower = f.content.lower()
        # Title hits weighted 3× — titles name the exact function/module being fixed
        title_hits = sum(1 for kw in title_kws if len(kw) > 4 and kw in content_lower)
        body_hits = sum(1 for kw in body_kws if len(kw) > 4 and kw in content_lower)
        # Test-derived symbols: paths/names from test imports/calls — weighted 2×
        test_hits = sum(1 for kw in test_kws if len(kw) > 4 and kw in content_lower)
        return import_bonus + path_score + 3.0 * title_hits + body_hits + 2.0 * test_hits

    return sorted(files, key=score, reverse=True)


def _truncate_context(files: list[FileContext]) -> list[FileContext]:
    """Limit files sent to the LLM: at most MAX_CONTEXT_FILES files,
    or until estimated context budget hits MAX_CONTEXT_CHARS.

    Budget is counted using capped sizes (MAX_FILE_BUDGET_CHARS per file)
    rather than raw sizes.  Large files are windowed before being sent to the
    model, so a 50 KB file typically only occupies 6-10 KB in the prompt.
    Using raw sizes as the budget would drop files 2-N for any problem where
    file 1 alone exceeds 40 KB, even though the windowed prompt would be fine.
    """
    selected: list[FileContext] = []
    total_chars = 0
    for f in files:
        if len(selected) >= MAX_CONTEXT_FILES:
            break
        # Use the smaller of raw size or per-file cap for budget accounting:
        # large files will be windowed, so they occupy far less prompt space.
        file_chars = min(len(f.path) + len(f.content), MAX_FILE_BUDGET_CHARS)
        if total_chars + file_chars > MAX_CONTEXT_CHARS and selected:
            break
        selected.append(f)
        total_chars += file_chars
    return selected


HEADER_LINES = 20  # fallback header size for unknown languages


def _compute_header_end(lines: list[str], ext: str) -> int:
    """Return how many lines from the top to always include in a windowed file.

    The header must cover the entire import section so the model can see:
    (a) what symbols are already imported (avoids duplicate imports), and
    (b) the type/struct/class definitions that follow imports.

    Go import blocks (`import (...)`) can span 25-40 lines.  With the old
    fixed HEADER_LINES=20 the model never saw the struct definitions that
    immediately follow the import block, causing wrong type assumptions.

    Strategy: scan for the last import-related line and add a post-import
    buffer so at least the first few top-level declarations are visible too.
    Falls back to HEADER_LINES when the language is unknown or the file is
    shorter than the computed end.
    """
    n = len(lines)
    POST_IMPORT_BUFFER = 8  # show a few lines after imports end

    if ext == "go":
        # Go: find the closing `)` of the import block, or the last bare import line.
        # Also include the `package` declaration and any top-level `var`/`const` blocks.
        last_import = 0
        in_import_block = False
        for i, raw in enumerate(lines):
            stripped = raw.strip()
            if stripped.startswith("import ("):
                in_import_block = True
                last_import = i
            elif in_import_block and stripped == ")":
                last_import = i
                in_import_block = False
            elif stripped.startswith("import ") and not in_import_block:
                last_import = i
        return min(n, last_import + 1 + POST_IMPORT_BUFFER)

    if ext in ("ts", "tsx", "js", "jsx"):
        # TypeScript/JS: last `import` statement line.
        last_import = 0
        for i, raw in enumerate(lines):
            stripped = raw.strip()
            if stripped.startswith("import ") or stripped.startswith("import{") or stripped.startswith("import *"):
                last_import = i
        return min(n, last_import + 1 + POST_IMPORT_BUFFER)

    if ext in ("kt", "java", "scala"):
        # Kotlin/Java/Scala: last `import` line.
        last_import = 0
        for i, raw in enumerate(lines):
            if raw.strip().startswith("import "):
                last_import = i
        return min(n, last_import + 1 + POST_IMPORT_BUFFER)

    if ext == "rs":
        # Rust: last `use ` statement.
        last_use = 0
        for i, raw in enumerate(lines):
            if raw.strip().startswith("use "):
                last_use = i
        return min(n, last_use + 1 + POST_IMPORT_BUFFER)

    if ext == "py":
        # Python: last `import` or `from ... import` line.
        last_import = 0
        for i, raw in enumerate(lines):
            stripped = raw.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                last_import = i
        return min(n, last_import + 1 + POST_IMPORT_BUFFER)

    if ext == "rb":
        # Ruby: last `require` or `require_relative` line.
        last_require = 0
        for i, raw in enumerate(lines):
            stripped = raw.strip()
            if stripped.startswith("require ") or stripped.startswith("require_relative "):
                last_require = i
        return min(n, last_require + 1 + POST_IMPORT_BUFFER)

    # Unknown extension — fall back to fixed constant
    return min(n, HEADER_LINES)


def _window_file(
    content: str,
    keywords: set[str],
    context_lines: int = 40,
    threshold: int = 300,
    show_line_numbers: bool = True,
    ext: str = "",
) -> tuple[str, bool]:
    """Return the relevant sections of a file and whether windowing was applied.

    For files over `threshold` lines, finds all lines containing keyword hits and
    emits a ±context_lines window around each hit cluster. Omitted regions
    are replaced with markers showing the exact line range, e.g.:
        ... [lines 21-260 omitted — next visible line is 261]

    This lets the model write accurate @@ -261,N +261,N @@ hunk headers without
    guessing offsets.

    The first HEADER_LINES lines are always included — they contain imports,
    module-level declarations, and class definitions the model needs to produce
    correct code (e.g. to know what's imported, what class a method belongs to).

    Returns (windowed_content, was_windowed).
    """
    lines = content.splitlines(keepends=True)
    if len(lines) <= threshold:
        if show_line_numbers:
            # Even for small (non-windowed) files, add line numbers so the model
            # can read @@ -N offsets directly without counting from the top.
            # Format matches windowed output: "  42 | line content"
            width = len(str(len(lines)))
            numbered = []
            for i, line in enumerate(lines, start=1):
                numbered.append(f"{i:{width}d} | {line}" if line.endswith("\n") else f"{i:{width}d} | {line}\n")
            return "".join(numbered), False
        return content, False

    # Mark which lines contain a keyword hit
    hit = [False] * len(lines)
    for i, line in enumerate(lines):
        l = line.lower()
        if any(kw in l for kw in keywords if len(kw) > 3):
            hit[i] = True

    if not any(hit):
        # No hits — return the header section (import block + first type defs).
        # Use language-aware detection so Go/TS files show past their large import
        # blocks; fall back to 80 lines when the header is smaller than that.
        peek = max(_compute_header_end(lines, ext), min(80, len(lines)))
        peek = min(peek, len(lines))
        suffix = f"\n... [lines {peek + 1}-{len(lines)} omitted — no keyword hits in this file]"
        if show_line_numbers:
            width = len(str(len(lines)))
            numbered = []
            for i, line in enumerate(lines[:peek], start=1):
                numbered.append(f"{i:{width}d} | {line}" if line.endswith("\n") else f"{i:{width}d} | {line}\n")
            return "".join(numbered) + suffix, True
        return "".join(lines[:peek]) + suffix, True

    # Force the header section into the window set so imports/class defs are visible.
    # Use language-aware detection so Go/TS/Kotlin files include the full import
    # block — their imports can run 25-40 lines, exceeding the old fixed cap.
    header_end = _compute_header_end(lines, ext)

    # Expand each hit into a window and merge overlapping windows
    windows: list[tuple[int, int]] = []

    # Seed with the header window
    windows.append((0, header_end))

    for i, is_hit in enumerate(hit):
        if is_hit:
            start = max(0, i - context_lines)
            end = min(len(lines), i + context_lines + 1)
            if windows and start <= windows[-1][1]:
                windows[-1] = (windows[-1][0], max(windows[-1][1], end))
            else:
                windows.append((start, end))

    parts = []
    prev_end = 0
    width = len(str(len(lines)))  # digit width for consistent alignment
    for start, end in windows:
        if start > prev_end:
            # Show exact line range so model can calculate accurate hunk offsets
            parts.append(
                f"... [lines {prev_end + 1}-{start} omitted"
                f" — next visible line is {start + 1}]\n"
            )
        for i, line in enumerate(lines[start:end], start=start + 1):
            # Prefix each visible line with its 1-based number so the model can
            # write accurate @@ -N hunk offsets without counting from the top.
            # Format: "  42 | actual line content"  (numbers are display-only)
            # For test files (show_line_numbers=False) we omit the numbers since
            # the agent does not write diffs against test files.
            if show_line_numbers:
                parts.append(f"{i:{width}d} | {line}" if line.endswith("\n") else f"{i:{width}d} | {line}\n")
            else:
                parts.append(line if line.endswith("\n") else line + "\n")
        prev_end = end
    if prev_end < len(lines):
        parts.append(
            f"... [lines {prev_end + 1}-{len(lines)} omitted"
            f" — end of file ({len(lines)} lines total)]\n"
        )

    return "".join(parts), True


def _format_files(
    files: list[FileContext],
    keywords: set[str] | None = None,
    context_lines: int = 40,
    threshold: int = 300,
    show_line_numbers: bool = True,
) -> str:
    parts = []
    for f in files:
        lang = f.language or ""
        # Derive file extension for language-aware header computation
        ext = f.path.rsplit(".", 1)[-1].lower() if "." in f.path else ""
        if keywords:
            content, windowed = _window_file(
                f.content, keywords,
                context_lines=context_lines,
                threshold=threshold,
                show_line_numbers=show_line_numbers,
                ext=ext,
            )
            total_lines = f.content.count("\n") + 1
            header = (
                f"### {f.path} ({total_lines} lines total — relevant sections shown)"
                if windowed
                else f"### {f.path}"
            )
        else:
            content = f.content
            header = f"### {f.path}"
        parts.append(f"{header}\n```{lang}\n{content}\n```")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Diff validation
# ---------------------------------------------------------------------------


def _extract_assertions(
    test_files: list[FileContext],
    limit: int = 50,
    keywords: set[str] | None = None,
) -> str:
    """Extract assertion lines from test files for the verify prompt.

    Assertions are the ground truth the diff must satisfy.  Injecting them
    directly into the verify prompt lets the model check each one explicitly
    rather than relying on the conversation context from the observe step.

    Caps at `limit` lines to keep the verify prompt compact.  Recognises
    assert styles for Python (pytest + unittest.TestCase self.assert*), Rust,
    Go (testify + t.Error/t.Fatal), TypeScript/Jest (sync + async await expect),
    Kotlin (kotlin.test), Java, Ruby Minitest, Rails integration tests,
    Node.js built-in assert module, and Python mock/spy assertions (contains check).

    When `keywords` is provided and a test file exceeds 200 lines, the content
    is windowed to keyword-relevant sections (±80 lines) before scanning for
    assertions.  This ensures that for large test files (e.g. a 562-assertion
    api.test.ts), we capture the assertions around the NEWLY added test cases
    (which are keyword-relevant) rather than always returning the first 50
    lines of the file (which cover old, existing tests).
    """
    _ASSERT_PREFIXES = (
        "assert ",          # Python / general
        "assert_eq!",       # Rust
        "assert_ne!",       # Rust
        "assert!(",         # Rust
        "expect(",          # JS/TS
        "toEqual",          # Jest/Vitest
        "toBe(",            # Jest/Vitest
        "toHaveBeenCalled",
        "toBeNull(",        # Jest/Vitest
        "toBeUndefined(",
        "toContain(",
        "toMatchObject(",
        "toThrow(",
        "assertEquals(",    # JUnit / Kotlin
        "assertTrue(",
        "assertFalse(",
        "assertThat(",
        "assertNotNull(",
        "assertNull(",
        "verify(",          # Kotlin mockk / Go mock
        "if got",           # Go-style: if got != want { t.Errorf... }
        "t.Errorf(",
        "t.Fatalf(",
        "t.Fatal(",         # Go
        "assert.Equal(",    # testify (Go)
        "assert.NoError(",
        "assert.Error(",
        "assert.True(",
        "assert.False(",
        "assert.Nil(",
        "assert.NotNil(",
        "assert.Contains(",
        "assert.Len(",
        "assert.Empty(",
        "assert.NotEmpty(",
        "require.Equal(",
        "require.NoError(",
        "require.Error(",
        "require.True(",
        "require.False(",
        "require.Nil(",
        "require.NotNil(",
        "require.Contains(",
        "require.Len(",
        # Python unittest.TestCase self.assert* — not matched by bare "assert " (has "self." prefix)
        "self.assertEqual(",
        "self.assertNotEqual(",
        "self.assertTrue(",
        "self.assertFalse(",
        "self.assertIsNone(",
        "self.assertIsNotNone(",
        "self.assertIn(",
        "self.assertNotIn(",
        "self.assertRaises(",
        "with self.assertRaises(",
        "self.assertAlmostEqual(",
        "self.assertGreater(",
        "self.assertGreaterEqual(",
        "self.assertLess(",
        "self.assertLessEqual(",
        # pytest exception assertion — both direct call and `with` context manager forms
        "pytest.raises(",
        "with pytest.raises(",
        # Ruby Minitest assert_* (assert_ prefix — NOT matched by bare "assert ")
        "assert_equal ",    "assert_equal(",
        "assert_nil ",      "assert_nil(",
        "assert_includes ", "assert_includes(",
        "assert_match ",    "assert_match(",
        "assert_raises ",   "assert_raises(",
        "assert_empty ",    "assert_empty(",
        "assert_respond_to ", "assert_respond_to(",
        "assert_kind_of ",  "assert_kind_of(",
        "assert_instance_of ", "assert_instance_of(",
        # Ruby / Rails additional patterns
        "assert_not_equal ",   "assert_not_equal(",   # Rails / ActiveSupport
        "assert_difference(",                          # Rails: assert_difference("Model.count", 1)
        "assert_no_difference(",                       # Rails: assert_no_difference("Model.count")
        "assert_response ",                            # Rails integration: assert_response :created
        "assert_redirected_to ",                       # Rails: assert_redirected_to root_path
        # Ruby Minitest refute_* — both space and parens calling conventions
        "refute ",             # bare: `refute value`, `refute obj.nil?`
        "refute_equal ",   "refute_equal(",
        "refute_nil ",     "refute_nil(",
        "refute_includes ","refute_includes(",
        "refute_match ",   "refute_match(",
        "refute_empty ",   "refute_empty(",
        # Kotlin kotlin.test — not matched by bare "assert" (no space/paren suffix)
        "assertIs<",           # type assertion: assertIs<AgentEvent.FinalAnswer>(result)
        "assertContains(",     # collection/string contains: assertContains(list, item)
        # Jest / Vitest async assertions — `await expect(promise).resolves.toBe(…)`
        # The bare `expect(` prefix above only captures synchronous calls starting with
        # `expect(`; async variants start with `await`, so they need a separate prefix.
        "await expect(",
        # Node.js built-in `assert` module (lowercase) — distinct from testify `assert.Equal`
        # These appear in JS/TS test suites that import `assert` from 'node:assert'.
        "assert.equal(",       # strict equality
        "assert.deepEqual(",   # deep structural equality
        "assert.notEqual(",    # strict not-equal
        "assert.throws(",      # sync throw check
        "assert.match(",       # regex match (Node 16+)
        "assert.doesNotMatch(", # regex non-match
        # Go standard `testing.T` non-fatal assertion variant
        # `t.Fatal` is already covered; `t.Error` is the non-aborting counterpart.
        "t.Error(",
    )
    # Mock/spy assertions: `mock_obj.assert_called_once_with(...)` — variable name varies
    # so we can't match by prefix.  Check if the stripped line contains these substrings.
    _ASSERT_CONTAINS = (
        ".assert_called(",
        ".assert_called_once(",
        ".assert_called_once_with(",
        ".assert_not_called(",
        ".assert_any_call(",
        ".assert_called_with(",
        ".assert_has_calls(",
    )
    lines: list[str] = []
    seen: set[str] = set()

    def is_assertion(s: str) -> bool:
        return any(s.startswith(p) for p in _ASSERT_PREFIXES) or any(p in s for p in _ASSERT_CONTAINS)

    for f in test_files:
        content = f.content
        kw_assertions: list[str] = []   # assertion lines that contain a keyword
        other_assertions: list[str] = []  # assertion lines without keywords

        if keywords and content.count("\n") > 200:
            # Large test file: scan line-by-line and bucket assertions as
            # keyword-relevant vs non-keyword.  Fill the limit with keyword
            # assertions first so that newly-added test cases (which reference
            # the new function/endpoint in the issue title) are always captured,
            # even when the file has hundreds of existing unrelated assertions
            # before them.
            kw_lower = {kw for kw in keywords if len(kw) > 3}
            for raw in content.splitlines():
                stripped = raw.strip()
                if stripped in seen or not is_assertion(stripped):
                    continue
                line_lower = stripped.lower()
                if kw_lower and any(kw in line_lower for kw in kw_lower):
                    kw_assertions.append(stripped)
                else:
                    other_assertions.append(stripped)
            # Keyword assertions first, then fill remainder with non-keyword ones
            for s in kw_assertions + other_assertions:
                if s not in seen:
                    lines.append(s)
                    seen.add(s)
                if len(lines) >= limit:
                    break
        else:
            # Small file or no keywords: scan in file order (original behaviour)
            for raw in content.splitlines():
                stripped = raw.strip()
                if stripped not in seen and is_assertion(stripped):
                    lines.append(stripped)
                    seen.add(stripped)
                if len(lines) >= limit:
                    break

        if len(lines) >= limit:
            break
    return "\n".join(lines)


def _trim_test_output(output: str, head: int = 30, tail: int = 50) -> str:
    """Return the first `head` + last `tail` lines of test output with a gap marker.

    Pytest and cargo test put the assertion failure near the top (most useful for
    diagnosing the wrong logic) and the summary at the bottom. Showing both ends
    beats showing only the last N lines, especially for long test suites.
    """
    lines = output.splitlines()
    if len(lines) <= head + tail:
        return output
    omitted = len(lines) - head - tail
    top = "\n".join(lines[:head])
    bottom = "\n".join(lines[-tail:])
    return f"{top}\n... [{omitted} lines omitted] ...\n{bottom}"


_LINE_NUM_PREFIX = re.compile(r"^([+ -])\s*\d+\s+\|\s?")


def _strip_line_number_prefixes(diff: str) -> str:
    """Remove `N | ` display artifacts from diff content lines.

    When source files are shown with `  N | content` line numbers, LLMs
    sometimes copy those prefixes into the diff despite the instruction not to.
    git apply then rejects the hunk because ` 42 | def foo():` doesn't appear
    in any real file.

    This strips the `N | ` portion while keeping the leading ` `/`+`/`-` marker,
    so the actual file content is preserved.  Only touches diff content lines —
    `diff --git`, `--- `, `+++ `, `@@ `, and `\\ ` lines are left untouched.
    """
    skip_prefixes = ("diff --git", "--- ", "+++ ", "@@ ", "\\ ")
    result = []
    for line in diff.splitlines():
        if any(line.startswith(p) for p in skip_prefixes):
            result.append(line)
            continue
        m = _LINE_NUM_PREFIX.match(line)
        result.append(m.group(1) + line[m.end():] if m else line)
    return "\n".join(result)


def _trim_trailing_prose(diff: str) -> str:
    """Remove non-diff text that appears after the last hunk line.

    `_extract_diff` grabs everything from the first `diff --git` to the end
    of the string.  If the model appended an explanation like "This patch
    makes the tests pass." after the final hunk, git apply fails on that
    trailing text.  Walk backwards to the last real diff line and truncate.
    """
    lines = diff.splitlines()
    diff_starts = ("diff --git", "--- ", "+++ ", "@@ ", "\\ No newline")
    for i in range(len(lines) - 1, -1, -1):
        line = lines[i]
        if line and (
            line[0] in (" ", "+", "-")
            or any(line.startswith(p) for p in diff_starts)
        ):
            return "\n".join(lines[: i + 1])
    return diff


def _looks_valid(diff: str) -> bool:
    """Must start with `diff --git` and contain at least one hunk."""
    return diff.startswith("diff --git") and "@@" in diff


def _count_diff_files(diff: str) -> int:
    """Return the number of distinct files in a unified diff."""
    return len(re.findall(r"^diff --git ", diff, re.MULTILINE))


def _fix_diff_headers(diff: str) -> str:
    """Insert missing --- a/path and +++ b/path headers in each file block.

    `git apply` requires `--- a/<path>` and `+++ b/<path>` lines between the
    `diff --git` line and the first `@@` hunk.  Models in repair mode often
    skip these, jumping straight from `diff --git` to `@@`.  Without them
    git apply exits with "patch does not apply".

    Also fixes `--- a/path` → `--- /dev/null` for new-file blocks: when the
    model writes `new file mode 100644` but uses the file path instead of
    `/dev/null` for the old path, `git apply` fails trying to read the
    non-existent original.

    Blocks with correct headers are left untouched.
    """
    lines = diff.splitlines()
    result: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^diff --git a/(.*) b/(.*)$", line)
        if not m:
            result.append(line)
            i += 1
            continue
        a_path, b_path = m.group(1), m.group(2)
        result.append(line)
        i += 1
        # Collect the meta-lines that follow: index, mode, new file mode, etc.
        # Stop before --- / +++ / @@ / diff --git so we can inspect what follows.
        meta: list[str] = []
        is_new_file = False
        while i < len(lines) and not lines[i].startswith("---") and not lines[i].startswith("+++") and not lines[i].startswith("@@") and not lines[i].startswith("diff --git"):
            if lines[i].startswith("new file"):
                is_new_file = True
            meta.append(lines[i])
            i += 1
        result.extend(meta)
        # Check whether --- / +++ are already present as the next lines
        # (they weren't in meta — the loop stopped before them).
        has_minus = i < len(lines) and lines[i].startswith("---")
        has_plus = (i + 1) < len(lines) and lines[i + 1].startswith("+++") if has_minus else (i < len(lines) and lines[i].startswith("+++"))

        if has_minus:
            minus_line = lines[i]
            # For new-file blocks, the old path must be /dev/null.
            # The model sometimes writes `--- a/<path>` instead — fix it.
            if is_new_file and minus_line != "--- /dev/null":
                result.append("--- /dev/null")
            else:
                result.append(minus_line)
            i += 1
        elif i < len(lines) and lines[i].startswith("@@"):
            # --- is missing entirely — insert correct old path
            old_path = "/dev/null" if is_new_file else f"a/{a_path}"
            result.append(f"--- {old_path}")

        # Now handle +++
        if i < len(lines) and lines[i].startswith("+++"):
            result.append(lines[i])
            i += 1
        elif not has_plus and i < len(lines) and lines[i].startswith("@@"):
            result.append(f"+++ b/{b_path}")
    return "\n".join(result)


def _fix_hunk_offsets(diff: str, file_lookup: dict[str, str]) -> str:
    """Correct wrong @@ -N start offsets by matching context lines.

    LLMs produce the plan hunk map under reasoning pressure and sometimes
    get the start line off by a few lines.  `_fix_hunk_counts` corrects the
    b/d counts but cannot fix N (the start line of the old hunk).  A wrong N
    causes `git apply` to fail even when the content is correct.

    Algorithm per hunk:
      1. Extract the first two consecutive context lines (` `-prefixed).
      2. Search the file for those two consecutive lines within ±50 lines of N.
      3. If found at a different offset, rewrite @@ -N accordingly.

    Only files present in `file_lookup` are checked.  New-file hunks
    (@@ -0,0 ...) are skipped.  If the search finds multiple matches or no
    match, the original N is kept (safe fallback).
    """
    _SEARCH_RADIUS = 50    # lines either side of stated offset to search
    _MIN_CTX_LINES = 1    # minimum context lines needed before trying correction

    def find_context_offset(
        file_lines: list[str],
        ctx: list[str],
        stated_n: int,
        old_sequence: list[str] | None = None,
    ) -> int | None:
        """Return the 1-indexed line where ctx[0] starts, or None if ambiguous.

        Requires len(ctx) >= 2 for leading-context matching so a single common
        line (e.g. '}' or '') doesn't produce false positives.  For single-line
        context (usually a removal line used as fingerprint), still tries but
        accepts only an unambiguous match within ±10 lines.

        Three-pass: exact leading-context match; full-sequence match when leading
        context is ambiguous (matches the complete set of old-file lines the hunk
        touches — context + removals — to uniquely locate repetitive blocks);
        stripped-content fallback for indentation mismatches.
        """
        if not ctx:
            return None
        radius = _SEARCH_RADIUS if len(ctx) >= 2 else 10
        lo = max(0, stated_n - radius - 1)
        hi = min(len(file_lines), stated_n + radius)

        # Pass 1: exact leading-context match
        matches: list[int] = []
        for idx in range(lo, hi):
            if file_lines[idx] == ctx[0]:
                if all(
                    idx + j < len(file_lines) and file_lines[idx + j] == ctx[j]
                    for j in range(len(ctx))
                ):
                    matches.append(idx + 1)
        if len(matches) == 1:
            return matches[0]

        # Pass 1b: full-sequence disambiguation.
        # When leading context is ambiguous (repetitive blocks in Go/Rust factory files,
        # config stanzas, etc.), search for the complete old-file line sequence that the
        # hunk covers: context lines + removal lines, in order.  This sequence is usually
        # unique even when the leading lines alone are not.
        if len(matches) > 1 and old_sequence and len(old_sequence) >= 4:
            seq_matches: list[int] = []
            seq_lo = max(0, stated_n - radius - 1)
            seq_hi = min(len(file_lines) - len(old_sequence) + 1, stated_n + radius)
            for idx in range(seq_lo, seq_hi):
                if (
                    file_lines[idx] == old_sequence[0]
                    and all(
                        file_lines[idx + j] == old_sequence[j]
                        for j in range(len(old_sequence))
                    )
                ):
                    seq_matches.append(idx + 1)
            if len(seq_matches) == 1:
                return seq_matches[0]

        # Pass 2: stripped-content fallback (handles tab/space indentation mismatches)
        if matches:
            return None  # exact pass was ambiguous — don't retry with weaker criterion
        ctx_stripped = [c.strip() for c in ctx]
        # Skip trivial fingerprints that would produce false positives when stripped
        if not ctx_stripped[0]:
            return None
        matches2: list[int] = []
        for idx in range(lo, hi):
            if file_lines[idx].strip() == ctx_stripped[0]:
                if all(
                    idx + j < len(file_lines)
                    and file_lines[idx + j].strip() == ctx_stripped[j]
                    for j in range(len(ctx))
                ):
                    matches2.append(idx + 1)
        if len(matches2) == 1:
            return matches2[0]
        return None

    lines = diff.split("\n")
    result: list[str] = []
    file_lines: list[str] | None = None
    i = 0
    while i < len(lines):
        line = lines[i]
        m_git = re.match(r"^diff --git a/(.*) b/(.*)$", line)
        if m_git:
            b_path = m_git.group(2)
            content = file_lookup.get(b_path) or file_lookup.get(m_git.group(1))
            file_lines = content.splitlines() if content else None
            result.append(line)
            i += 1
            continue
        m_hunk = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,\d+)? @@(.*)", line)
        if m_hunk and file_lines is not None:
            old_start = int(m_hunk.group(1))
            old_b = int(m_hunk.group(2)) if m_hunk.group(2) else 1
            new_start = m_hunk.group(3)
            suffix = m_hunk.group(4)
            if old_start == 0:
                # New-file hunk — nothing to correct
                result.append(line)
                i += 1
                continue
            # Collect all hunk lines first (for leading ctx + old_sequence below)
            hunk_body: list[str] = []
            jb = i + 1
            while jb < len(lines):
                hl = lines[jb]
                if hl.startswith("diff --git") or hl.startswith("@@"):
                    break
                hunk_body.append(hl)
                jb += 1
            # Leading context lines (unchanged lines before the first +/-)
            ctx: list[str] = []
            for hl in hunk_body:
                if len(ctx) >= 5:
                    break
                if hl.startswith(" "):
                    ctx.append(hl[1:])
                else:
                    break
            # If fewer than 2 leading context lines, also try the first removal line
            # as a fingerprint (deletion must exist at the stated location).
            if len(ctx) < 2:
                for hl in hunk_body:
                    if hl.startswith("-") and not hl.startswith("---"):
                        ctx_fallback = ctx + [hl[1:]]
                        if len(ctx_fallback) >= 1:
                            ctx = ctx_fallback
                        break
                    if hl.startswith(" "):
                        continue
                    break
            # Full old-file sequence: context + removal lines in hunk order.
            # Used as a stronger fingerprint when leading context alone is ambiguous.
            old_sequence: list[str] = []
            for hl in hunk_body:
                if hl.startswith(" "):
                    old_sequence.append(hl[1:])
                elif hl.startswith("-") and not hl.startswith("---"):
                    old_sequence.append(hl[1:])
                # + lines are new content — not in old file, so not part of the sequence
            if len(ctx) >= _MIN_CTX_LINES:
                correct = find_context_offset(
                    file_lines, ctx, old_start,
                    old_sequence=old_sequence if len(old_sequence) >= 4 else None,
                )
                if correct is not None and correct != old_start:
                    # Recompute new_start with the same delta; counts come from m_hunk
                    delta = correct - old_start
                    corrected_new = int(new_start) + delta
                    m_new_count = re.match(r"^@@ -\d+(?:,\d+)? \+\d+(?:,(\d+))? @@", line)
                    new_count = m_new_count.group(1) if m_new_count and m_new_count.group(1) else "1"
                    line = f"@@ -{correct},{old_b} +{corrected_new},{new_count} @@{suffix}"
            result.append(line)
            i += 1
            continue
        result.append(line)
        i += 1
    return "\n".join(result)


def _fix_context_lines(diff: str, file_lookup: dict[str, str]) -> str:
    """Replace context/removal lines that differ from the source only in whitespace.

    `git apply` matches context lines and removal lines exactly — even a tab-vs-spaces
    difference causes it to reject an otherwise correct hunk.  This most often happens
    when:
      - The model writes leading spaces where the source has tabs (or vice versa)
      - The model strips trailing whitespace that the source retains

    Safety rule: only replace a line when its stripped content matches the source
    exactly (so we never silently move a change to the wrong location).

    Applied after `_fix_hunk_offsets` so the `@@ -N` start offsets are already
    corrected; using corrected offsets to look up source lines is reliable.
    New-file hunks (`@@ -0,0 ...`) are skipped — there is no source to compare.
    """
    lines = diff.split("\n")
    result: list[str] = []
    file_lines: list[str] | None = None
    hunk_old_start: int = 0
    line_cursor: int = 0  # tracks current position in the old file (1-indexed)

    i = 0
    while i < len(lines):
        line = lines[i]

        m_git = re.match(r"^diff --git a/(.*) b/(.*)$", line)
        if m_git:
            b_path = m_git.group(2)
            content = file_lookup.get(b_path) or file_lookup.get(m_git.group(1))
            file_lines = content.splitlines() if content else None
            hunk_old_start = 0
            line_cursor = 0
            result.append(line)
            i += 1
            continue

        m_hunk = re.match(r"^@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@", line)
        if m_hunk:
            hunk_old_start = int(m_hunk.group(1))
            line_cursor = hunk_old_start
            result.append(line)
            i += 1
            continue

        # Context line or removal line: both must match the source exactly for git apply.
        is_context = line.startswith(" ")
        is_removal = line.startswith("-") and not line.startswith("---")
        if (
            (is_context or is_removal)
            and file_lines is not None
            and hunk_old_start > 0          # inside a real hunk (not new-file)
            and line_cursor >= 1
            and line_cursor <= len(file_lines)
        ):
            source_line = file_lines[line_cursor - 1]  # 0-indexed
            diff_content = line[1:]  # strip leading space or minus
            # Replace only when stripped content matches — ensures correct location
            if diff_content.strip() == source_line.strip() and diff_content != source_line:
                prefix = " " if is_context else "-"
                result.append(prefix + source_line)
                line_cursor += 1
                i += 1
                continue

        # Advance line_cursor for context and removal lines
        if line.startswith(" ") or (line.startswith("-") and not line.startswith("---")):
            line_cursor += 1
        # `+` lines don't advance old-file cursor

        result.append(line)
        i += 1

    return "\n".join(result)


def _extract_file_signatures(content: str, lang: str) -> list[str]:
    """Return declaration lines (function/class/method) from a source file.

    Extracts structural top-level names so the verify step can confirm the
    diff adds the expected symbols without re-reading the full file content.
    Only returns short declaration lines — long signatures are trimmed.
    """
    lines = content.splitlines()
    sigs: list[str] = []
    pat: re.Pattern | None = None

    if lang == "py":
        # Match both top-level and class-body declarations (indented methods)
        pat = re.compile(r"^\s*(class\s+\w|def\s+\w|async def\s+\w)")
    elif lang == "go":
        pat = re.compile(r"^(func\s+|type\s+\w+\s+(struct|interface))")
    elif lang in ("ts", "tsx", "js", "jsx"):
        pat = re.compile(
            r"^\s*(export\s+(function|class|interface|type|const|let|enum)\s+\w|"
            r"(async\s+)?function\s+\w|class\s+\w|"
            r"(public|private|protected|async|static)(\s+(public|private|protected|async|static))*\s+\w+\s*\()"
        )
    elif lang == "rs":
        pat = re.compile(
            r"^\s*(pub(\s*\(\s*crate\s*\))?\s+(async\s+)?(fn|struct|enum|trait|type)\s+|"
            r"(async\s+)?fn\s+\w|impl\s+)"
        )
    elif lang in ("kt", "java", "scala"):
        pat = re.compile(
            r"^\s*(fun\s+\w|(suspend\s+)?fun\s+\w|class\s+\w|data class\s+\w|"
            r"interface\s+\w|object\s+\w|enum class\s+\w|abstract class\s+\w|"
            r"(public|private|protected|override)\s+(fun|class|interface)\s+\w)"
        )
    elif lang == "rb":
        pat = re.compile(r"^\s*(def\s+\w|class\s+\w|module\s+\w)")

    if pat is None:
        return []

    for line in lines:
        if pat.match(line.rstrip()):
            trimmed = line.rstrip()
            # Trim very long lines (e.g. long parameter lists)
            if len(trimmed) > 80:
                trimmed = trimmed[:77] + "..."
            sigs.append("  " + trimmed.lstrip())

    return sigs


def _structural_summary(
    impl_files: list[FileContext],
    changed_paths: set[str],
    max_chars: int = 3000,
) -> str:
    """Build a compact structural summary of implementation files.

    Prioritises files that appear in the diff so the verify step can check
    those files for completeness. Other files get just their path listed.

    The summary replaces the raw source content in the compacted history,
    giving the verify model enough structural context to answer:
    "Does the diff add every required function/method to the right file?"
    without re-reading full file bodies.
    """
    parts: list[str] = []
    chars_used = 0

    # Show signatures for changed files first, then others
    ordered = sorted(impl_files, key=lambda f: (f.path not in changed_paths, f.path))

    for f in ordered:
        if chars_used >= max_chars:
            break
        ext = f.path.rsplit(".", 1)[-1].lower() if "." in f.path else ""
        sigs = _extract_file_signatures(f.content, ext)

        if sigs:
            header = f.path + ("  ← changed" if f.path in changed_paths else "")
            block = f"[{header}]\n" + "\n".join(sigs[:12])  # cap per-file at 12
        else:
            block = f"[{f.path}]"

        if chars_used + len(block) > max_chars:
            # Add header-only if full block doesn't fit
            block = f"[{f.path}]"
        parts.append(block)
        chars_used += len(block) + 1

    return "\n".join(parts)


def _changed_paths_from_diff(diff: str) -> set[str]:
    """Return the set of file paths that appear in a unified diff."""
    paths: set[str] = set()
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            m = re.match(r"^diff --git a/.+ b/(.+)$", line)
            if m:
                paths.add(m.group(1))
        elif line.startswith("+++ b/"):
            paths.add(line[6:].strip())
    return paths


def _hunk_source_snippets(
    diff: str,
    file_lookup: dict[str, str],
    max_hunks: int = 10,
) -> str:
    """Return formatted source lines around each hunk's @@ -N offset.

    After history compaction the verify model cannot see source files.  Injecting
    the actual source lines at each hunk's stated start offset lets the model
    perform a real check: do the context lines in the diff match the source?

    A mismatch signals a wrong @@ -N offset (git apply will reject the hunk
    even if the content is correct).  Limited to max_hunks to keep the verify
    prompt compact; covers the first N hunks across all files in the diff.
    """
    if not file_lookup or not diff:
        return ""

    current_file: str | None = None
    hunk_count = 0
    snippets: list[str] = []

    for line in diff.splitlines():
        if line.startswith("diff --git "):
            m = re.match(r"^diff --git a/.+ b/(.+)$", line)
            if m:
                current_file = m.group(1)
        elif line.startswith("+++ b/"):
            current_file = line[6:].strip()
        elif line.startswith("@@ -") and current_file and hunk_count < max_hunks:
            m = re.match(r"^@@ -(\d+)", line)
            if not m:
                continue
            start = int(m.group(1))
            if start == 0:
                continue  # new-file hunk — no source to show

            src = file_lookup.get(current_file) or file_lookup.get(
                current_file.rsplit("/", 1)[-1] if "/" in current_file else current_file
            )
            if not src:
                continue

            src_lines = src.splitlines()
            total = len(src_lines)
            if start > total:
                continue

            lo = max(0, start - 3)  # 2 lines before hunk start (0-indexed: start-3 to start-1)
            hi = min(total, start + 2)  # 2 lines at/after hunk start

            ctx: list[str] = []
            for i in range(lo, hi):
                marker = "→" if i == start - 1 else " "
                ctx.append(f"  {marker} {i + 1}: {src_lines[i]}")

            snippets.append(f"[{current_file} @@ -{start}]\n" + "\n".join(ctx))
            hunk_count += 1

    if not snippets:
        return ""

    return HUNK_SOURCE_SECTION_TEMPLATE.format(snippets="\n\n".join(snippets))


def _strip_diff_trailing_whitespace(diff: str) -> str:
    """Strip trailing whitespace from added and context diff lines.

    Models frequently generate blank continuation lines as '+    ' (with spaces)
    instead of '+' (empty). These cause `git apply` to fail with "corrupt patch"
    when the source file doesn't have matching trailing whitespace. Safe to strip:
    we only touch `+` and ` ` (context) lines — never `-` (removed) lines since
    those must match the file exactly.
    """
    lines = diff.split("\n")
    cleaned = []
    for line in lines:
        if line.startswith("+") or line.startswith(" "):
            cleaned.append(line.rstrip())
        else:
            cleaned.append(line)
    return "\n".join(cleaned)


def _post_process(diff: str, file_lookup: dict[str, str] | None = None) -> str:
    """Strip display artifacts, trim trailing prose, fix headers and hunk metadata.

    Applied after every _extract_diff call so that intermediate diffs
    fed back into the verify/repair loop are always clean.

    Pipeline order:
      1. Strip N| display artifacts (must be first — counts computed on clean content)
      2. Trim trailing prose
      3. Insert missing --- a/ +++ b/ headers (before hunk offset correction)
      4. Correct wrong @@ -N start offsets via context-line matching (needs headers)
      5. Fix context lines that differ from source only in whitespace (safe: strip-match guard)
      6. Recompute @@ -a,b +c,d counts from actual hunk content
      7. Recalculate +c new-start from corrected -N + cumulative per-file delta
      8. Strip trailing whitespace from added/context diff lines (model artifact)
    """
    diff = _strip_line_number_prefixes(diff)
    diff = _trim_trailing_prose(diff)
    diff = _fix_diff_headers(diff)
    if file_lookup:
        diff = _fix_hunk_offsets(diff, file_lookup)
        diff = _fix_context_lines(diff, file_lookup)
    diff = _fix_hunk_counts(diff)
    diff = _fix_new_starts(diff)
    diff = _strip_diff_trailing_whitespace(diff)
    return diff


def _fix_hunk_counts(diff: str) -> str:
    """Rewrite @@ -a,b +c,d @@ headers with accurate line counts.

    LLMs frequently miscalculate b (old-hunk line count) and d (new-hunk line
    count).  This post-processor counts the actual ` `, `-`, `+` lines in each
    hunk and rewrites the header, increasing the probability that `git apply`
    succeeds without changing any of the actual content.
    """
    lines = diff.split("\n")
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)", line)
        if not m:
            result.append(line)
            i += 1
            continue
        old_start = m.group(1)
        new_start = m.group(2)
        suffix = m.group(3)

        # Count context/remove/add lines that belong to this hunk
        old_count = 0
        new_count = 0
        j = i + 1
        while j < len(lines):
            hl = lines[j]
            if hl.startswith("diff --git") or re.match(r"^@@ ", hl):
                break
            if hl.startswith("-") and not hl.startswith("---"):
                old_count += 1
            elif hl.startswith("+") and not hl.startswith("+++"):
                new_count += 1
            elif hl.startswith(" "):
                old_count += 1
                new_count += 1
            # backslash no-newline markers and blank lines: not content
            j += 1

        result.append(f"@@ -{old_start},{old_count} +{new_start},{new_count} @@{suffix}")
        i += 1  # consume only the @@ line; hunk content processed normally
    return "\n".join(result)


def _fix_new_starts(diff: str) -> str:
    """Recalculate +c (new-file start line) for each hunk from corrected -N + cumulative delta.

    After _fix_hunk_offsets corrects -N and _fix_hunk_counts corrects b/d counts, the +c
    values may still be stale — they reflect whatever the LLM wrote, not the mathematically
    correct position.  Wrong +c values cause `git apply` to reject valid hunks.

    The correct +c for each hunk is: old_start + sum(new_count - old_count) for all
    previous hunks in the same file.  New-file hunks (@@ -0,0 ...) are skipped since
    they have no old file to count from.
    """
    lines = diff.split("\n")
    result: list[str] = []
    cumulative_delta = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"^diff --git", line):
            cumulative_delta = 0  # reset per file
            result.append(line)
            i += 1
            continue
        m = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)", line)
        if m:
            old_start = int(m.group(1))
            old_count = int(m.group(2)) if m.group(2) else 1
            new_count = int(m.group(4)) if m.group(4) else 1
            suffix = m.group(5)
            if old_start == 0:
                # New-file hunk: +c is always 1 when adding a whole file; skip recalc
                result.append(line)
                i += 1
                continue
            correct_new = old_start + cumulative_delta
            result.append(f"@@ -{old_start},{old_count} +{correct_new},{new_count} @@{suffix}")
            cumulative_delta += new_count - old_count
            i += 1
            continue
        result.append(line)
        i += 1
    return "\n".join(result)


def _diagnose_diff(diff: str) -> str:
    """Return a short description of the first structural problem found."""
    if not diff.strip():
        return "empty output — no diff produced"
    if not diff.startswith("diff --git"):
        return "does not start with `diff --git a/... b/...`"
    if "@@" not in diff:
        return "missing hunk header — no `@@ -N,N +N,N @@` line found"
    # Check that every `@@` line has the expected format
    for line in diff.splitlines():
        if line.startswith("@@"):
            if not re.match(r"@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@", line):
                return f"malformed hunk header: {line!r}"
    # Check that the diff actually changes something (at least one + or - line)
    has_change = any(
        (ln.startswith("+") and not ln.startswith("+++"))
        or (ln.startswith("-") and not ln.startswith("---"))
        for ln in diff.splitlines()
    )
    if not has_change:
        return "diff contains only context lines — no lines were added or removed"
    return ""


# ---------------------------------------------------------------------------
# LLM client
# ---------------------------------------------------------------------------


def _call(
    messages: list[dict[str, str]],
    model: str,
    api_key: str,
    max_tokens: int,
    timeout: float,
    temperature: float = 0.2,
) -> str:
    """Call the OpenRouter API. Retries once on 429, 5xx, timeout, or missing choices."""
    for attempt in range(2):
        try:
            resp = httpx.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": REFERER,
                },
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
                timeout=timeout,
            )
        except httpx.TimeoutException:
            if attempt == 0:
                time.sleep(2)
                continue
            return ""  # second timeout — caller handles empty string gracefully
        if attempt == 0 and resp.status_code in (400, 429, 500, 502, 503):
            retry_after = int(resp.headers.get("retry-after", "5"))
            time.sleep(min(retry_after, 10))
            continue
        if resp.status_code >= 400:
            return ""  # non-retriable error — return empty, score gracefully as 0
        data = resp.json()
        if "choices" not in data:
            # OpenRouter returned an error body (e.g. "No endpoints found")
            # instead of a completion — retry once then return empty string.
            if attempt == 0:
                time.sleep(5)
                continue
            return ""
        return data["choices"][0]["message"]["content"]
    return ""


def _extract_diff(text: str) -> str:
    """Pull the unified diff out of LLM output, stripping markdown fences.

    Handles two common model failure modes:
    1. Single fenced block: ` ```diff\\ndiff --git ...\\n``` `
    2. Multiple fenced blocks: model puts each changed file in its own block.
       `re.search` would only capture the first block — we join all of them.
    Also matches ` ```patch ` fences (less common but valid).
    """
    text = text.strip().replace("\r\n", "\n").replace("\r", "\n")
    fences = list(re.finditer(r"```\w*\s*\n(diff --git.+?)```", text, re.DOTALL))
    if fences:
        return "\n".join(m.group(1).strip() for m in fences)
    idx = text.find("diff --git")
    if idx != -1:
        return text[idx:].strip()
    return text


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class ExampleAgent(BaseAgent):
    """
    Ranked-context observe → plan → act → verify agent.

    Turn 1: rank context files by relevance, then analyse the issue to produce
            an explicit file-and-line hypothesis.
    Turn 2: produce the unified diff targeting the hypothesis.
    Turn 3+: verify structural correctness; repair with targeted feedback if wrong
             (up to MAX_REPAIR_ATTEMPTS).
    """

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.model = model

    def solve(self, problem: Problem) -> Patch:
        api_key = os.environ.get("OPENROUTER_KEY", "")
        if not api_key:
            raise RuntimeError("OPENROUTER_KEY environment variable not set")

        if problem.allowed_models and self.model not in problem.allowed_models:
            raise RuntimeError(
                f"Model '{self.model}' is not in the allowed list: {problem.allowed_models}"
            )

        # Allocate wall-clock budget non-uniformly:
        #   plan  15% — analysis output is moderate length (500-2000 tokens)
        #   act   40% — diff output can be large (many hunks across many files)
        #   each verify/repair  15% — LGTM or corrected diff (must fit full diff)
        # With default 120s: plan=18s, act=48s, each verify=18s (×3 = 54s) → 120s total.
        total_time = float(problem.time_limit_seconds)
        plan_timeout = total_time * 0.15
        act_timeout = total_time * 0.40
        verify_timeout = total_time * 0.15
        token_budget = problem.output_token_budget
        plan_tokens = token_budget // 4    # analysis rarely exceeds 12k tokens
        act_tokens = token_budget // 2
        # Verify needs same budget as act: when it produces a corrected diff rather
        # than LGTM, it must be able to output the full diff without truncation.
        # token_budget // 4 was too small for large multi-file corrections.
        verify_tokens = act_tokens

        log: list[str] = []

        # --- Split and rank context files ---
        test_files = [f for f in problem.context_files if _is_test_file(f)]
        impl_files = [f for f in problem.context_files if not _is_test_file(f)]
        ranked_impl = _rank_files(impl_files, problem.issue_title, problem.issue_body, test_files, problem.file_tree)
        selected_impl = _truncate_context(ranked_impl)
        # Add sibling modules that top-ranked files import from (up to 6 KB extra).
        # This ensures the agent sees helper utilities that already exist in the
        # package (e.g. emit_error_json in helpers.py) instead of hallucinating them.
        siblings = _expand_sibling_imports(selected_impl, impl_files, problem.file_tree or [])
        if siblings:
            selected_impl = selected_impl + siblings
            log.append(f"[context] sibling-import expansion: {[s.path for s in siblings]}")
        dropped = len(impl_files) - len(selected_impl)
        if dropped > 0:
            log.append(f"[context] {len(selected_impl)}/{len(impl_files)} impl files selected (dropped {dropped} low-relevance)")
        if test_files:
            log.append(f"[context] {len(test_files)} test file(s) shown separately")
        if problem.file_tree and test_files:
            pinned = _resolve_test_imports(test_files, problem.file_tree)
            if pinned:
                log.append(f"[context] import-pinned: {sorted(pinned)}")

        # Build keyword set for windowing large files — union of issue tokens + test symbols
        raw_tokens = re.findall(r"\b([a-z_][a-z0-9_]{3,}|[A-Z][A-Za-z0-9]{3,})\b", problem.issue_title + " " + problem.issue_body)
        keywords = {t.lower() for t in raw_tokens} | _test_keywords(test_files)

        # Identify new test files: present in context but not in the file tree at base_commit.
        # These files don't exist yet — the agent's diff must add them, or the test harness
        # cannot find the test file and the correctness score is 0.
        new_tests = _new_test_files(test_files, problem.file_tree)
        if new_tests:
            log.append(f"[context] new test files (must be created in diff): {[f.path for f in new_tests]}")

        new_impls = _new_impl_files(selected_impl, problem.file_tree)
        if new_impls:
            log.append(f"[context] new impl files (must be created in diff): {[f.path for f in new_impls]}")

        # Build test section. Large test files are windowed (threshold=200 lines,
        # context_lines=80) to avoid consuming most of the context budget on
        # boilerplate; the wider window ensures complete test functions are visible.
        test_cmd_str = " ".join(problem.test_cmd) if problem.test_cmd else "pytest"
        test_cmd_short = problem.test_cmd[-1] if problem.test_cmd else "pytest"

        test_section = (
            TEST_SECTION_TEMPLATE.format(
                test_files=_format_files(
                    test_files, keywords,
                    context_lines=80, threshold=200, show_line_numbers=False,
                )
            )
            if test_files else ""
        )
        new_test_section = (
            NEW_TEST_FILES_TEMPLATE.format(
                test_cmd=test_cmd_str,
                new_test_diffs=_new_test_diff(new_tests),
            )
            if new_tests else ""
        )
        new_impl_section = (
            NEW_IMPL_FILES_TEMPLATE.format(
                new_impl_paths="\n".join(f"- {f.path}" for f in new_impls),
            )
            if new_impls else ""
        )

        # --- Turn 1: Observe + Plan ---
        init_hint = _index_hint(selected_impl, problem.file_tree)
        if init_hint:
            log.append(f"[context] index-file hint: {init_hint.strip()}")

        # Build language-specific system prompt suffix
        lang = _detect_lang(test_files) or _detect_lang(selected_impl)
        lang_note = LANG_NOTES.get(lang or "", "")
        system_content = SYSTEM_PROMPT + ("\n\n" + lang_note if lang_note else "")
        if lang_note:
            log.append(f"[context] language detected: {lang}")

        # Prune file tree to only paths in directories of context files.
        # Large repos (ragflow, phase) have 500 paths (16-22 KB) in the raw tree.
        # Showing the full tree wastes context budget; the pruned view covers
        # all directories the agent needs to reason about import paths.
        all_context = test_files + selected_impl
        pruned_tree = _prune_file_tree(problem.file_tree, all_context)
        raw_tree_len = sum(len(p) for p in problem.file_tree)
        pruned_tree_len = sum(len(p) for p in pruned_tree if not p.startswith("..."))
        if raw_tree_len > pruned_tree_len + 200:
            log.append(
                f"[context] file tree pruned: {len(pruned_tree)} paths "
                f"({pruned_tree_len} chars, saved {raw_tree_len - pruned_tree_len} chars)"
            )

        # Pre-extract assertions for the plan step.  Injecting them as a quick-reference
        # checklist before the source files helps the model's step-1 analysis (test contract)
        # be more accurate — especially for keyword-windowed test files where the most
        # relevant assertions may be scattered across hundreds of lines.
        plan_assertions_text = _extract_assertions(test_files, keywords=keywords) if test_files else ""
        plan_assertions_section = (
            PLAN_ASSERTIONS_SECTION_TEMPLATE.format(assertions=plan_assertions_text)
            if plan_assertions_text else ""
        )
        if plan_assertions_text:
            n_assertions = plan_assertions_text.count("\n") + 1
            log.append(f"[context] {n_assertions} assertions injected into plan step")

        observe_user = OBSERVE_PROMPT.format(
            title=problem.issue_title,
            body=problem.issue_body,
            repo=problem.repo_name,
            test_cmd=test_cmd_str,
            test_cmd_short=test_cmd_short,
            tree="\n".join(pruned_tree),
            init_hint=init_hint,
            test_section=test_section,
            new_test_section=new_test_section + new_impl_section,
            plan_assertions_section=plan_assertions_section,
            impl_files=_format_files(selected_impl, keywords),
        )
        history: list[dict[str, str]] = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": observe_user},
        ]
        plan = _call(history, self.model, api_key, plan_tokens, plan_timeout)
        log.append(f"[plan]\n{plan}")
        history.append({"role": "assistant", "content": plan})

        # --- Turn 2: Act ---
        # temperature=0 for diff generation: format precision matters more than creativity
        # Build lookup for context-line hunk-offset correction.
        # Maps both a/path and b/path keys so _fix_hunk_offsets can look up
        # file content regardless of which path form the model uses.
        file_lookup: dict[str, str] = {}
        for f in all_context:
            file_lookup[f.path] = f.content
            if "/" in f.path:
                file_lookup[f.path.rsplit("/", 1)[-1]] = f.content

        def pp(d: str) -> str:
            return _post_process(d, file_lookup)

        # Check if plan response already contains a valid diff (model "acts early").
        # When this happens, the ACT step returns nothing because the model thinks
        # it already answered. Extract the plan diff directly and skip ACT.
        plan_diff = pp(_extract_diff(plan))
        if _looks_valid(plan_diff):
            log.append("[diff v0 (from plan — skipped ACT)]\n" + plan_diff)
            diff = plan_diff
            history.append({"role": "user", "content": ACT_PROMPT})
            history.append({"role": "assistant", "content": diff})
        else:
            history.append({"role": "user", "content": ACT_PROMPT})
            raw_diff = _call(history, self.model, api_key, act_tokens, act_timeout, temperature=0)
            diff = pp(_extract_diff(raw_diff))
            log.append(f"[diff v0]\n{diff}")
            history.append({"role": "assistant", "content": diff})

        # --- Compact history before verify ---
        # The observe_user message (history[1]) contains all source files and the
        # full file tree — typically 20-30k chars.  The model has already used this
        # context to produce its plan and diff.  Replacing it with a compact summary
        # reduces the context sent on every verify/repair call, freeing token budget
        # for the model to reason about the diff itself rather than re-processing
        # source files it has already analysed.
        #
        # IMPORTANT: only compact if the act step produced a valid diff.  If the
        # act step returned empty (API timeout/error), the repair iterations need
        # the full source-file context to have any chance of producing a correct
        # diff — compacting here would leave them with only the issue title and
        # file names, which is insufficient to write accurate code.
        # Build structural summary for compaction: function/class signatures from
        # implementation files give the verify step enough context to check that
        # the diff adds the expected symbols — without re-sending full file bodies.
        # Prioritise files that appear in the diff (mark them "← changed").
        changed_paths = _changed_paths_from_diff(diff)
        struct_summary = _structural_summary(selected_impl, changed_paths)
        compact_observe = (
            f"[Earlier context: {problem.repo_name} — issue: {problem.issue_title} — "
            f"test: {test_cmd_str}]\n\n"
            f"File signatures in scope:\n{struct_summary}"
        )
        if _looks_valid(diff):
            history[1] = {"role": "user", "content": compact_observe}
            log.append(f"[context] history compacted with structural summary ({len(struct_summary)} chars, {len(changed_paths)} changed files)")
        else:
            log.append("[context] history NOT compacted (act returned empty/invalid — keeping source context)")

        # --- Turn 3+: Verify + Repair ---
        # Track when the previous verify iteration returned a prose critique
        # (no corrected diff). In that case, use a short targeted follow-up
        # ("produce the diff now") instead of resending the full VERIFY_PROMPT
        # — saves 3-5KB of repeated context and is more directive.
        #
        # pending_partial_repair: set when the model returned fewer files than
        # the current diff.  The missing-files feedback was already appended as
        # a user message; the next iteration must call the model without adding
        # another user message first (avoids back-to-back user messages that
        # confuse some model backends and lead to a 400 error).
        pending_prose_critique = False
        pending_partial_repair = False

        for attempt in range(MAX_REPAIR_ATTEMPTS):
            problem_desc = _diagnose_diff(diff)

            if problem_desc:
                # Structural problem — give targeted feedback before asking for repair.
                # Special case: if the diff is empty (act step timed out / API error),
                # resend ACT_PROMPT instead of REPAIR_FORMAT_PROMPT — the model has
                # nothing to fix and needs to produce the diff from scratch using the
                # source files still in context.
                pending_prose_critique = False
                pending_partial_repair = False
                if "empty output" in problem_desc:
                    history.append({"role": "user", "content": ACT_PROMPT})
                    log.append(f"[repair {attempt} (empty-retry act)]")
                else:
                    repair_msg = REPAIR_FORMAT_PROMPT.format(problem=problem_desc, diff=diff)
                    history.append({"role": "user", "content": repair_msg})
                raw_diff = _call(history, self.model, api_key, act_tokens, act_timeout, temperature=0)
                diff = pp(_extract_diff(raw_diff))
                log.append(f"[repair {attempt} (format)]\n{diff}")
                history.append({"role": "assistant", "content": diff})
                # Compact history after a successful empty-retry: the repair produced
                # a real diff, so subsequent verify calls no longer need source files.
                if "empty output" in problem_desc and _looks_valid(diff):
                    history[1] = {"role": "user", "content": compact_observe}
                    log.append("[context] history compacted after empty-retry success")
                continue

            # Diff looks structurally valid — ask for semantic verification.
            # Three cases for the user message to send:
            #   1. pending_partial_repair: missing-files message already appended;
            #      call the model without adding another user message.
            #   2. pending_prose_critique: prose critique was given; send a short
            #      "produce the diff now" follow-up instead of the full VERIFY_PROMPT.
            #   3. Normal: send the full VERIFY_PROMPT.
            if pending_partial_repair:
                log.append(f"[verify {attempt} (followup after partial repair)]")
                pending_partial_repair = False
            elif pending_prose_critique:
                history.append({"role": "user", "content": VERIFY_FOLLOWUP_PROMPT})
                log.append(f"[verify {attempt} (followup after prose critique)]")
            else:
                # First verify call, or previous call produced a corrected diff:
                # inject extracted assertions so the model can cross-check each one.
                # For long issue bodies, show first 2500 chars + last 500 chars so
                # requirements stated near the end (edge cases, gotchas) are visible.
                # The model's full observe turn is compacted after the act step, so
                # the verify prompt is the only place the model sees issue body text.
                body_raw = problem.issue_body or ""
                if len(body_raw) > 3000:
                    body_snippet = body_raw[:2500] + "\n[...]\n" + body_raw[-500:]
                else:
                    body_snippet = body_raw
                assertions_text = _extract_assertions(test_files, keywords=keywords)
                assertions_section = (
                    ASSERTIONS_SECTION_TEMPLATE.format(assertions=assertions_text)
                    if assertions_text else ""
                )
                # New-file requirements: remind verify if any files must be created.
                required_new = [f.path for f in new_tests] + [f.path for f in new_impls]
                if required_new:
                    new_files_section = NEW_FILES_VERIFY_SECTION_TEMPLATE.format(
                        files="\n".join(f"- `{p}`" for p in required_new)
                    )
                    new_files_check = (
                        f"Does the diff add ALL {len(required_new)} required new file(s) listed above "
                        f"as `new file mode 100644` blocks? Missing any file means the test command fails."
                    )
                else:
                    new_files_section = ""
                    new_files_check = "N/A (no new files required)"
                # Hunk source context: show actual source lines at each @@ -N offset
                # so criterion 2 is a real check rather than a plausibility guess.
                # Limited to 6 hunks (~1 KB) to keep the verify prompt compact.
                hunk_source_section = _hunk_source_snippets(diff, file_lookup)
                if hunk_source_section:
                    log.append("[verify] hunk source context injected")
                verify_user = VERIFY_PROMPT.format(
                    diff=diff,
                    title=problem.issue_title,
                    body=body_snippet,
                    test_cmd=test_cmd_str,
                    assertions_section=assertions_section,
                    new_files_section=new_files_section,
                    new_files_check=new_files_check,
                    hunk_source_section=hunk_source_section,
                )
                history.append({"role": "user", "content": verify_user})
            pending_prose_critique = False
            verdict = _call(history, self.model, api_key, verify_tokens, verify_timeout, temperature=0)
            log.append(f"[verify {attempt}]\n{verdict}")

            repaired = pp(_extract_diff(verdict))
            # LGTM: model approved the diff (no valid diff extracted) or explicitly said LGTM.
            # Check for LGTM before checking for a repaired diff — if the model both says
            # "LGTM" and includes a diff, we treat it as approval (not a replacement).
            if verdict.strip().upper().startswith("LGTM"):
                break
            if not _looks_valid(repaired) and "lgtm" in verdict.lower():
                log.append(f"[verify {attempt}] LGTM detected (non-leading position)")
                break

            if _looks_valid(repaired):
                # Only replace if repaired diff covers at least as many files as the
                # current diff.  If it covers fewer, the model returned a partial
                # correction (e.g. only the one file it fixed) and replacing would
                # silently drop changes to the other files.
                if _count_diff_files(repaired) >= _count_diff_files(diff):
                    diff = repaired
                    pending_partial_repair = False
                    log.append(f"[diff v{attempt + 1}]\n{diff}")
                    # Store the cleaned diff in history — not the raw verdict which may
                    # contain prose mixed with the diff.  Subsequent verify/repair calls
                    # see the same artifact-free version they would produce via _post_process.
                    history.append({"role": "assistant", "content": repaired})
                else:
                    # Partial repair: model only fixed some files. Keep the current diff
                    # but give targeted feedback naming the missing files explicitly so
                    # the next verify pass knows exactly which files to include.
                    n_cur = _count_diff_files(diff)
                    n_rep = _count_diff_files(repaired)
                    cur_paths = _changed_paths_from_diff(diff)
                    rep_paths = _changed_paths_from_diff(repaired)
                    missing_paths = sorted(cur_paths - rep_paths)
                    log.append(
                        f"[verify {attempt}] partial repair ({n_rep} < {n_cur} files) — "
                        f"missing: {missing_paths}"
                    )
                    missing_list = "\n".join(f"- {p}" for p in missing_paths)
                    history.append({"role": "assistant", "content": repaired})
                    history.append({
                        "role": "user",
                        "content": (
                            f"Your corrected diff only covers {n_rep} file(s) but the original "
                            f"diff touched {n_cur} file(s). The following file(s) are missing "
                            f"from your response:\n\n{missing_list}\n\n"
                            f"You must include ALL {n_cur} files. Produce a complete unified diff."
                        ),
                    })
                    # The missing-files message is now the last user turn.
                    # Signal the next iteration to call the model directly without
                    # prepending another user message (avoids back-to-back user msgs).
                    pending_partial_repair = True
            else:
                # Prose critique without a corrected diff.
                # Store the critique in history so the next verify iteration sees it.
                # Use VERIFY_FOLLOWUP_PROMPT on the next call (shorter, more directed)
                # rather than re-sending the full VERIFY_PROMPT with the same diff.
                # Only continue if we have iterations remaining — on the last
                # attempt, break and keep the current diff.
                pending_partial_repair = False
                if attempt < MAX_REPAIR_ATTEMPTS - 1:
                    history.append({"role": "assistant", "content": verdict})
                    pending_prose_critique = True
                    log.append(f"[verify {attempt}] prose critique — followup next iteration")
                else:
                    break

        # Final post-process pass to catch any artifacts introduced after the last
        # repair step (e.g. by the prose-critique branch above).
        diff = pp(diff)

        reasoning = f"model={self.model}\n\n" + "\n\n".join(log)
        return Patch(diff=diff, reasoning=reasoning)

    def repair(self, problem: Problem, failed_patch: Patch, test_output: str) -> Patch:
        """
        Targeted repair: extend the conversation with the test failure output and
        ask the model to produce a corrected diff.

        Called by `gitminer run --repair N` after a local test run fails.
        Not used in CI scoring — the benchmark scores the first solve() result.
        """
        api_key = os.environ.get("OPENROUTER_KEY", "")
        if not api_key:
            raise RuntimeError("OPENROUTER_KEY environment variable not set")

        test_cmd_str = " ".join(problem.test_cmd) if problem.test_cmd else "pytest"
        act_timeout = float(problem.time_limit_seconds) * 0.40
        act_tokens = problem.output_token_budget // 2

        log: list[str] = [f"[repair] test failure detected, starting targeted repair"]

        # Build file_lookup for hunk-offset correction (same as solve())
        file_lookup: dict[str, str] = {}
        for f in problem.context_files:
            file_lookup[f.path] = f.content
            if "/" in f.path:
                file_lookup[f.path.rsplit("/", 1)[-1]] = f.content

        def pp(d: str) -> str:
            return _post_process(d, file_lookup)

        # Inject source file context for files touched by the failed diff.
        # Without this the model must reason about the failure blind — it can see
        # the diff it produced and the test error, but not the actual file state.
        # Providing the original source files (before patch) lets the model spot
        # off-by-one logic errors, missing branches, and wrong type annotations.
        # Limited to files in file_lookup (those in the problem context) and capped
        # at 3 files × 4 KB each to keep the repair prompt compact.
        diff_paths = _changed_paths_from_diff(failed_patch.diff)
        repair_source_parts: list[str] = []
        chars_used = 0
        for path in sorted(diff_paths):
            src = file_lookup.get(path) or file_lookup.get(
                path.rsplit("/", 1)[-1] if "/" in path else path
            )
            if not src:
                continue
            snippet = src[:4000] if len(src) > 4000 else src
            if chars_used + len(snippet) > 12_000:
                break
            ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
            repair_source_parts.append(f"### {path}\n```{ext}\n{snippet}\n```")
            chars_used += len(snippet)
            if len(repair_source_parts) >= 3:
                break

        source_section = ""
        if repair_source_parts:
            source_section = (
                "\nSource files before your patch (check your logic against these):\n\n"
                + "\n\n".join(repair_source_parts)
                + "\n\n"
            )

        # Build a fresh conversation focused on the failure — cheaper than a full re-solve
        repair_user = TEST_REPAIR_PROMPT.format(
            title=problem.issue_title,
            test_cmd=test_cmd_str,
            diff=failed_patch.diff,
            test_output=_trim_test_output(test_output),
            source_section=source_section,
        )
        history: list[dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": repair_user},
        ]
        raw_diff = _call(history, self.model, api_key, act_tokens, act_timeout, temperature=0)
        diff = pp(_extract_diff(raw_diff))
        log.append(f"[repair diff]\n{diff}")

        # One structural validation pass
        if not _looks_valid(diff):
            problem_desc = _diagnose_diff(diff)
            history.append({"role": "assistant", "content": diff})
            history.append({"role": "user", "content": REPAIR_FORMAT_PROMPT.format(problem=problem_desc, diff=diff)})
            raw_diff = _call(history, self.model, api_key, act_tokens, act_timeout, temperature=0)
            diff = pp(_extract_diff(raw_diff))
            log.append(f"[repair format fix]\n{diff}")

        reasoning = (failed_patch.reasoning or "") + "\n\n" + f"model={self.model}\n\n" + "\n\n".join(log)
        return Patch(diff=diff, reasoning=reasoning)
