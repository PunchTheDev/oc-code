"""
Reference agent: ranked-context observe → plan → act → verify loop.

Demonstrates the scaffolding pattern — same frozen model, better wrapper.
Miners compete to outperform this baseline.

Scoring model: correctness gates quality. Tests must pass first; then the
score is driven by the number of meaningful source-code tokens in the diff
(Gittensor's src_token_score formula). This agent is tuned to produce
complete, well-structured implementations — not minimal one-liners — because
a thorough fix that passes tests scores significantly higher than a bare stub.

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
- Language-specific notes: Rust/TypeScript/Ruby system-prompt additions remind
  the model of language conventions (trait bounds, exports, require statements)
  that generic instructions miss
- Score-aware prompting: system prompt and act prompt explain that complete
  implementations score higher than stubs
- Structural diff validation beyond the basic `@@` presence check — catches
  malformed hunk headers before committing to the result
- Wider repair window (3 attempts, up from 2) with targeted feedback per failure mode
- Verify turn also checks implementation completeness — may expand a bare fix
- Structured reasoning log for transparency
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


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an expert software engineer. You receive a GitHub issue and the \
relevant source files, and your job is to produce a correct, complete fix \
as a valid unified diff.

Scoring note: your patch is scored on (1) test correctness — it must pass — \
and (2) source-token quality — the number of meaningful code tokens you add \
to non-test files. A complete, well-structured implementation that covers all \
edge cases and adds clear helper logic scores higher than a one-liner that \
technically passes but leaves the fix fragile or incomplete.
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
{init_hint}{test_section}
## Source files (ranked by relevance)
{impl_files}

---

Analyse this test-first, then plan. Answer in order:

1. **Test contract** — what exactly does the test assert? List each assertion, \
   the function/class/method it calls, the expected input → output or behaviour. \
   This is the ground truth your implementation must satisfy.
2. **Root cause** — given the test contract, what is currently missing or wrong in \
   the source files?
3. **Hypothesis** — which specific file(s) and line range(s) need to change? Be exact.
4. **Implementation plan** — starting from the test contract, describe what you will \
   add/change: function signatures, return types, helper logic, error handling, \
   edge cases. Every assertion in the test must map to something in your plan.
5. **Completeness check** — what secondary files or side effects (imports, exports, \
   constants, type annotations) also need updating? If you add a new public symbol, \
   check whether any `__init__.py` or `index.ts`/`index.js` in the hint below \
   needs a new export line.

Be precise and thorough — a complete implementation that handles all test cases and \
edge cases scores higher than a minimal stub.
"""

TEST_SECTION_TEMPLATE = """\
## Test files (read first — these define the contract your implementation must satisfy)
{test_files}

"""

ACT_PROMPT = """\
Based on your analysis above, produce the unified diff.

Before writing: mentally verify each test assertion from step 1 of your analysis \
maps to a concrete line in your diff. If any assertion is unaccounted for, add it.

Requirements:
- Start with `diff --git a/<path> b/<path>`
- Include `--- a/<path>` and `+++ b/<path>` headers
- Each hunk starts with `@@ -<start>,<count> +<start>,<count> @@`
- **Line numbers**: windowed files show lines as `  N | content`. Use these \
  numbers directly for `@@ -N` offsets. The numbers are display-only — do NOT \
  include ` N | ` in your diff's context or change lines; they must match the \
  actual file content
- **Context lines**: include exactly 3 unchanged lines before and after each \
  change — this is required for `git apply` to locate the change correctly
- Every test assertion from your plan must be satisfied by your diff
- Include helper functions, proper error handling, and secondary file changes
- Do NOT change unrelated logic, but do implement the full fix as described
- Higher-quality, complete implementations score better than minimal stubs
- Output ONLY the diff — no markdown fences, no prose
"""

VERIFY_PROMPT = """\
Issue: {title}

{body}

Test command that must pass: `{test_cmd}`

You produced this diff:

```diff
{diff}
```

Check it against these criteria:
1. Does the diff address every assertion in the test file, not just the surface symptom?
2. Are `@@ -N` line numbers accurate? Cross-check with `N |` line markers in the context.
3. Are there missing changes or accidental deletions that would break unrelated tests?
4. Are all new symbols, functions, or classes properly imported in every file that uses them?
5. Is the implementation complete — does it handle edge cases, or is it a bare stub that \
   only handles the happy path?

If the diff is correct and complete, respond with exactly: LGTM

If it needs fixing, respond with the corrected diff only (no prose, starts with `diff --git`).
If the implementation is a bare minimum that should be more thorough, expand it and respond with the improved diff.
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

Please output a valid unified diff starting with `diff --git` and containing \
at least one `@@` hunk. Nothing else.
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
    "rb": (
        "This is a Ruby codebase. Key reminders: follow snake_case naming; "
        "include modules where methods are defined; use `attr_accessor`/`attr_reader` "
        "for new fields; ensure `require` or `require_relative` for any new file."
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


def _is_test_file(f: FileContext) -> bool:
    """Return True if this file is a test/spec file (not source to modify)."""
    p = f.path.lower()
    name = p.rsplit("/", 1)[-1]
    return (
        "/test/" in p or "/tests/" in p or "/spec/" in p or "/specs/" in p
        or name.startswith("test_") or name.endswith("_test.py")
        or ".test." in name or ".spec." in name
        or name.startswith("spec_") or name.endswith("_spec.rb")
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
            for m in re.finditer(r"""from\s+['"]([^'"]+)['"]""", content):
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

    return resolved


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
    or until cumulative character count hits MAX_CONTEXT_CHARS."""
    selected: list[FileContext] = []
    total_chars = 0
    for f in files:
        if len(selected) >= MAX_CONTEXT_FILES:
            break
        file_chars = len(f.path) + len(f.content)
        if total_chars + file_chars > MAX_CONTEXT_CHARS and selected:
            break
        selected.append(f)
        total_chars += file_chars
    return selected


HEADER_LINES = 20  # always shown at top of a windowed file (imports, class defs, etc.)


def _window_file(content: str, keywords: set[str], context_lines: int = 40) -> tuple[str, bool]:
    """Return the relevant sections of a file and whether windowing was applied.

    For files over 300 lines, finds all lines containing keyword hits and
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
    if len(lines) <= 300:
        return content, False

    # Mark which lines contain a keyword hit
    hit = [False] * len(lines)
    for i, line in enumerate(lines):
        l = line.lower()
        if any(kw in l for kw in keywords if len(kw) > 3):
            hit[i] = True

    if not any(hit):
        # No hits — return first N lines as a peek (includes header naturally)
        peek = min(80, len(lines))
        suffix = f"\n... [lines {peek + 1}-{len(lines)} omitted — no keyword hits in this file]"
        return "".join(lines[:peek]) + suffix, True

    # Force the header section into the window set so imports/class defs are visible
    header_end = min(HEADER_LINES, len(lines))

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
        # Prefix each visible line with its 1-based number so the model can
        # write accurate @@ -N hunk offsets without counting from the top.
        # Format: "  42 | actual line content"  (numbers are display-only)
        for i, line in enumerate(lines[start:end], start=start + 1):
            parts.append(f"{i:{width}d} | {line}" if line.endswith("\n") else f"{i:{width}d} | {line}\n")
        prev_end = end
    if prev_end < len(lines):
        parts.append(
            f"... [lines {prev_end + 1}-{len(lines)} omitted"
            f" — end of file ({len(lines)} lines total)]\n"
        )

    return "".join(parts), True


def _format_files(files: list[FileContext], keywords: set[str] | None = None) -> str:
    parts = []
    for f in files:
        lang = f.language or ""
        if keywords:
            content, windowed = _window_file(f.content, keywords)
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


def _looks_valid(diff: str) -> bool:
    """Must start with `diff --git` and contain at least one hunk."""
    return diff.startswith("diff --git") and "@@" in diff


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
    """Call the OpenRouter API. Retries once on 429 (rate limit)."""
    for attempt in range(2):
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
        if resp.status_code == 429 and attempt == 0:
            retry_after = int(resp.headers.get("retry-after", "5"))
            time.sleep(min(retry_after, 10))
            continue
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    resp.raise_for_status()
    return ""


def _extract_diff(text: str) -> str:
    """Pull the unified diff out of LLM output, stripping markdown fences."""
    text = text.strip()
    fence = re.search(r"```(?:diff)?\s*\n(diff --git.+?)```", text, re.DOTALL)
    if fence:
        return fence.group(1).strip()
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

        # Distribute wall-clock budget across all calls so we never exceed the limit
        # even in the worst case.
        timeout = float(problem.time_limit_seconds) / MAX_CALLS
        token_budget = problem.output_token_budget
        plan_tokens = token_budget // 3
        act_tokens = token_budget // 2
        verify_tokens = token_budget // 4

        log: list[str] = []

        # --- Split and rank context files ---
        test_files = [f for f in problem.context_files if _is_test_file(f)]
        impl_files = [f for f in problem.context_files if not _is_test_file(f)]
        ranked_impl = _rank_files(impl_files, problem.issue_title, problem.issue_body, test_files, problem.file_tree)
        selected_impl = _truncate_context(ranked_impl)
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

        # Build test section — always shown in full (usually small)
        test_section = (
            TEST_SECTION_TEMPLATE.format(test_files=_format_files(test_files))
            if test_files else ""
        )

        # --- Turn 1: Observe + Plan ---
        test_cmd_str = " ".join(problem.test_cmd) if problem.test_cmd else "pytest"
        test_cmd_short = problem.test_cmd[-1] if problem.test_cmd else "pytest"
        init_hint = _index_hint(selected_impl, problem.file_tree)
        if init_hint:
            log.append(f"[context] index-file hint: {init_hint.strip()}")

        # Build language-specific system prompt suffix
        lang = _detect_lang(test_files) or _detect_lang(selected_impl)
        lang_note = LANG_NOTES.get(lang or "", "")
        system_content = SYSTEM_PROMPT + ("\n\n" + lang_note if lang_note else "")
        if lang_note:
            log.append(f"[context] language detected: {lang}")

        observe_user = OBSERVE_PROMPT.format(
            title=problem.issue_title,
            body=problem.issue_body,
            repo=problem.repo_name,
            test_cmd=test_cmd_str,
            test_cmd_short=test_cmd_short,
            tree="\n".join(problem.file_tree),
            init_hint=init_hint,
            test_section=test_section,
            impl_files=_format_files(selected_impl, keywords),
        )
        history: list[dict[str, str]] = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": observe_user},
        ]
        plan = _call(history, self.model, api_key, plan_tokens, timeout)
        log.append(f"[plan]\n{plan}")
        history.append({"role": "assistant", "content": plan})

        # --- Turn 2: Act ---
        # temperature=0 for diff generation: format precision matters more than creativity
        history.append({"role": "user", "content": ACT_PROMPT})
        raw_diff = _call(history, self.model, api_key, act_tokens, timeout, temperature=0)
        diff = _extract_diff(raw_diff)
        log.append(f"[diff v0]\n{diff}")
        history.append({"role": "assistant", "content": raw_diff})

        # --- Turn 3+: Verify + Repair ---
        for attempt in range(MAX_REPAIR_ATTEMPTS):
            problem_desc = _diagnose_diff(diff)

            if problem_desc:
                # Structural problem — give targeted feedback before asking for repair
                repair_msg = REPAIR_FORMAT_PROMPT.format(problem=problem_desc)
                history.append({"role": "user", "content": repair_msg})
                raw_diff = _call(history, self.model, api_key, act_tokens, timeout, temperature=0)
                diff = _extract_diff(raw_diff)
                log.append(f"[repair {attempt} (format)]\n{diff}")
                history.append({"role": "assistant", "content": raw_diff})
                continue

            # Diff looks structurally valid — ask for semantic verification
            body_snippet = (problem.issue_body or "")[:1500]
            verify_user = VERIFY_PROMPT.format(
                diff=diff,
                title=problem.issue_title,
                body=body_snippet,
                test_cmd=test_cmd_str,
            )
            history.append({"role": "user", "content": verify_user})
            verdict = _call(history, self.model, api_key, verify_tokens, timeout)
            log.append(f"[verify {attempt}]\n{verdict}")

            if verdict.strip().upper().startswith("LGTM"):
                break

            repaired = _extract_diff(verdict)
            if _looks_valid(repaired):
                diff = repaired
                log.append(f"[diff v{attempt + 1}]\n{diff}")
                history.append({"role": "assistant", "content": verdict})
            else:
                # Prose critique without a new diff — accept current result
                break

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
        timeout = float(problem.time_limit_seconds) / MAX_CALLS
        act_tokens = problem.output_token_budget // 2

        log: list[str] = [f"[repair] test failure detected, starting targeted repair"]

        # Build a fresh conversation focused on the failure — cheaper than a full re-solve
        repair_user = TEST_REPAIR_PROMPT.format(
            title=problem.issue_title,
            test_cmd=test_cmd_str,
            diff=failed_patch.diff,
            test_output=_trim_test_output(test_output),
        )
        history: list[dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": repair_user},
        ]
        raw_diff = _call(history, self.model, api_key, act_tokens, timeout, temperature=0)
        diff = _extract_diff(raw_diff)
        log.append(f"[repair diff]\n{diff}")

        # One structural validation pass
        if not _looks_valid(diff):
            problem_desc = _diagnose_diff(diff)
            history.append({"role": "assistant", "content": raw_diff})
            history.append({"role": "user", "content": REPAIR_FORMAT_PROMPT.format(problem=problem_desc)})
            raw_diff = _call(history, self.model, api_key, act_tokens, timeout, temperature=0)
            diff = _extract_diff(raw_diff)
            log.append(f"[repair format fix]\n{diff}")

        reasoning = (failed_patch.reasoning or "") + "\n\n" + f"model={self.model}\n\n" + "\n\n".join(log)
        return Patch(diff=diff, reasoning=reasoning)
