"""
Reference agent: ranked-context observe → plan → act → verify loop.

Demonstrates the scaffolding pattern — same frozen model, better wrapper.
Miners compete to outperform this baseline.

Improvements over a naive single-shot approach:
- Context files ranked by keyword relevance to the issue — most relevant first,
  over-long context truncated rather than blindly dumped into the prompt
- Explicit file-and-line hypothesis required in the planning turn so the act
  turn has a precise target
- Structural diff validation beyond the basic `@@` presence check — catches
  malformed hunk headers before committing to the result
- Wider repair window (3 attempts, up from 2) with targeted feedback per failure mode
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
relevant source files, and your job is to produce a correct, minimal fix \
as a valid unified diff.
"""

OBSERVE_PROMPT = """\
## Issue: {title}

{body}

## Repository: {repo}

## Test command
```
{test_cmd}
```
The scoring harness runs this command on your patched repo. Your fix must make it pass.

## File tree
```
{tree}
```

## Context files (ranked by relevance)
{files}

---

Analyse the issue carefully. Answer in order:

1. **Root cause** — one or two sentences.
2. **Hypothesis** — which specific file(s) and line range(s) need to change?
3. **Minimal change** — describe what the change is, no code yet.
4. **Test check** — will `{test_cmd_short}` pass with this change? Why?

Be concise and precise.
"""

ACT_PROMPT = """\
Based on your analysis above, produce the unified diff.

Requirements:
- Start with `diff --git a/<path> b/<path>`
- Include `--- a/<path>` and `+++ b/<path>` headers
- Each hunk starts with `@@ -<start>,<count> +<start>,<count> @@`
- Only touch the lines identified in your hypothesis
- No refactors, no style fixes, no unrelated changes
- Output ONLY the diff — no markdown fences, no prose
"""

VERIFY_PROMPT = """\
Issue: {title}

You produced this diff:

```diff
{diff}
```

Check it against these criteria:
1. Does the diff address the root cause described in the issue above?
2. Is every `@@` hunk header syntactically correct (line numbers make sense)?
3. Are there missing changes or accidental deletions?

If the diff is correct and complete, respond with exactly: LGTM

If it needs fixing, respond with the corrected diff only (no prose, starts with `diff --git`).
"""

REPAIR_FORMAT_PROMPT = """\
The diff you produced is not a valid unified diff.

Problem: {problem}

Please output a valid unified diff starting with `diff --git` and containing \
at least one `@@` hunk. Nothing else.
"""


# ---------------------------------------------------------------------------
# Context ranking
# ---------------------------------------------------------------------------


def _rank_files(files: list[FileContext], issue_title: str, issue_body: str) -> list[FileContext]:
    """Return files sorted by keyword relevance to the issue, most relevant first."""
    issue_text = (issue_title + " " + issue_body).lower()

    # Explicit file paths mentioned in the issue — strong relevance signal
    mentioned_paths = set(re.findall(r"[\w/.-]+\.(?:py|ts|js|rs|go|java|kt|rb|cpp|c|h)", issue_text))

    # Identifier tokens from the issue (snake_case, camelCase, UPPER_CASE)
    raw_tokens = re.findall(r"\b([a-z_][a-z0-9_]{3,}|[A-Z][A-Za-z0-9]{3,})\b", issue_title + " " + issue_body)
    keywords = {t.lower() for t in raw_tokens}

    def score(f: FileContext) -> float:
        path_lower = f.path.lower()
        # High bonus if the file is explicitly mentioned
        path_score = 20.0 * sum(1 for mp in mentioned_paths if mp in path_lower)
        # Test files get a small boost — the issue often relates to what they assert
        test_bonus = 3.0 if ("/test" in path_lower or "_test." in path_lower or "test_" in path_lower.split("/")[-1]) else 0.0
        # Keyword density in file content (identifiers > 4 chars to reduce noise)
        content_lower = f.content.lower()
        keyword_hits = sum(1 for kw in keywords if len(kw) > 4 and kw in content_lower)
        return path_score + test_bonus + keyword_hits

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


def _format_files(files: list[FileContext]) -> str:
    parts = []
    for f in files:
        lang = f.language or ""
        parts.append(f"### {f.path}\n```{lang}\n{f.content}\n```")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Diff validation
# ---------------------------------------------------------------------------


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

        # --- Rank and truncate context files ---
        ranked = _rank_files(problem.context_files, problem.issue_title, problem.issue_body)
        selected = _truncate_context(ranked)
        dropped = len(problem.context_files) - len(selected)
        if dropped > 0:
            log.append(f"[context] {len(selected)}/{len(problem.context_files)} files selected (dropped {dropped} low-relevance files)")

        # --- Turn 1: Observe + Plan ---
        test_cmd_str = " ".join(problem.test_cmd) if problem.test_cmd else "pytest"
        test_cmd_short = problem.test_cmd[-1] if problem.test_cmd else "pytest"
        observe_user = OBSERVE_PROMPT.format(
            title=problem.issue_title,
            body=problem.issue_body,
            repo=problem.repo_name,
            test_cmd=test_cmd_str,
            test_cmd_short=test_cmd_short,
            tree="\n".join(problem.file_tree),
            files=_format_files(selected),
        )
        history: list[dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
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
            verify_user = VERIFY_PROMPT.format(
                diff=diff,
                title=problem.issue_title,
                body=problem.issue_body,
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
