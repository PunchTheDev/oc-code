"""
Reference agent: observe → plan → act → verify loop.

Demonstrates the scaffolding pattern — same frozen model, better wrapper.
Miners compete to outperform this baseline.

Improvements over a naive single-shot approach:
- Explicit planning turn before generating a diff
- Self-critique pass that catches obvious diff errors and triggers a repair
- Structured reasoning log for transparency

The loop is intentionally shallow (max 2 repair attempts) so miners have
room to build richer loops with tool use, test feedback, and memory.
"""

from __future__ import annotations

import os
import re
import textwrap
import time

import httpx

from agent.base import BaseAgent, FileContext, Patch, Problem

DEFAULT_MODEL = os.environ.get("BENCHMARK_MODEL", "anthropic/claude-3-5-haiku")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
REFERER = "https://github.com/PunchTheDev/gittensor-base-miner"

MAX_REPAIR_ATTEMPTS = 2
# Number of LLM calls in worst case: plan + act + verify + repair × MAX_REPAIR_ATTEMPTS
MAX_CALLS = 3 + MAX_REPAIR_ATTEMPTS


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an expert software engineer. You receive a GitHub issue and the \
relevant source files, and your job is to produce a correct, minimal fix.
"""

OBSERVE_PROMPT = """\
## Issue: {title}

{body}

## Repository: {repo}

## File tree
```
{tree}
```

## Context files
{files}

---

Analyse the issue carefully. Answer these questions in order:

1. What is the root cause?
2. Which files and lines need to change?
3. What is the minimal correct change — no refactors, no style fixes?

Be concise and precise. Do not write any code yet.
"""

ACT_PROMPT = """\
Based on your analysis:

{plan}

Now produce the unified diff that fixes the issue.

Rules:
- Output ONLY the unified diff, starting with `diff --git`.
- No prose, no markdown code fences.
- Smallest correct change only — no refactors or unrelated fixes.
- The patch must apply cleanly and all tests must pass.
"""

VERIFY_PROMPT = """\
You just produced this diff:

```diff
{diff}
```

The issue was:

{title}

{body}

Review the diff carefully. Answer:
1. Does it address the root cause identified in your plan?
2. Are the `---` / `+++` headers and hunk offsets syntactically correct?
3. Are there any obviously wrong or missing changes?

If the diff is correct, respond with exactly: LGTM

If not, respond with a corrected diff starting with `diff --git` and nothing else.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_files(files: list[FileContext]) -> str:
    parts = []
    for f in files:
        lang = f.language or ""
        parts.append(f"### {f.path}\n```{lang}\n{f.content}\n```")
    return "\n\n".join(parts)


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


def _looks_valid(diff: str) -> bool:
    """Basic sanity: must start with `diff --git` and have at least one hunk."""
    return diff.startswith("diff --git") and "@@" in diff


# ---------------------------------------------------------------------------
# LLM client
# ---------------------------------------------------------------------------


def _call(
    messages: list[dict[str, str]],
    model: str,
    api_key: str,
    max_tokens: int,
    timeout: float,
) -> str:
    """Call the OpenRouter API. Retries once on 429 (rate limit) after a brief wait."""
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
                "temperature": 0.2,
            },
            timeout=timeout,
        )
        if resp.status_code == 429 and attempt == 0:
            retry_after = int(resp.headers.get("retry-after", "5"))
            time.sleep(min(retry_after, 10))
            continue
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    # Should not reach here, but satisfy type checker
    resp.raise_for_status()
    return ""


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class ExampleAgent(BaseAgent):
    """
    Observe → plan → act → verify agent.

    Turn 1: analyse the issue and identify the root cause and required changes.
    Turn 2: produce the unified diff.
    Turn 3+: self-critique; repair if the diff looks wrong (up to MAX_REPAIR_ATTEMPTS).
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

        # Distribute the wall-clock budget across all LLM calls so we can't
        # exceed time_limit_seconds even in the worst case (all calls slow).
        timeout = float(problem.time_limit_seconds) / MAX_CALLS
        token_budget = problem.output_token_budget
        plan_tokens = token_budget // 3
        act_tokens = token_budget // 2
        verify_tokens = token_budget // 4

        log: list[str] = []

        # --- Turn 1: Observe + Plan ---
        observe_user = OBSERVE_PROMPT.format(
            title=problem.issue_title,
            body=problem.issue_body,
            repo=problem.repo_name,
            tree="\n".join(problem.file_tree),
            files=_format_files(problem.context_files),
        )
        history: list[dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": observe_user},
        ]
        plan = _call(history, self.model, api_key, plan_tokens, timeout)
        log.append(f"[plan]\n{plan}")
        history.append({"role": "assistant", "content": plan})

        # --- Turn 2: Act ---
        act_user = ACT_PROMPT.format(plan=textwrap.shorten(plan, width=2000))
        history.append({"role": "user", "content": act_user})
        raw_diff = _call(history, self.model, api_key, act_tokens, timeout)
        diff = _extract_diff(raw_diff)
        log.append(f"[diff v0]\n{diff}")
        history.append({"role": "assistant", "content": raw_diff})

        # --- Turn 3+: Verify + Repair ---
        for attempt in range(MAX_REPAIR_ATTEMPTS):
            if _looks_valid(diff):
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
                    # Verdict was prose criticism, not a diff — accept what we have
                    break
            else:
                history.append({
                    "role": "user",
                    "content": (
                        "The diff you produced does not look like a valid unified diff "
                        "(must start with `diff --git` and contain at least one `@@` hunk). "
                        "Please output only the corrected unified diff."
                    ),
                })
                raw_diff = _call(history, self.model, api_key, act_tokens, timeout)
                diff = _extract_diff(raw_diff)
                log.append(f"[repair {attempt}]\n{diff}")
                history.append({"role": "assistant", "content": raw_diff})

        reasoning = f"model={self.model}\n\n" + "\n\n".join(log)
        return Patch(diff=diff, reasoning=reasoning)
