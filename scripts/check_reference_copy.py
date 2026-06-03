"""
Detect agents that return reference diffs verbatim.

The reference.diff for every problem is stored in the public repo, so a miner
could build an agent that reads benchmark/problems/{id}/reference.diff and
returns it directly, scoring oracle-level without doing any real reasoning.

This check compares each diff hash in the behavior fingerprint against the
normalized hash of the reference.diff for that problem. If the match rate
exceeds the threshold, the submission is flagged.

Note: a match on ONE or two problems is expected by chance (the agent and the
reference may independently produce the same minimal fix). A pattern across
many problems is the signal.

Exit codes:
  0  — match rate below threshold (clean)
  1  — match rate exceeds threshold (likely hardcoding reference diffs)
  2  — usage error (fingerprint not found, etc.)

Usage:
    python scripts/check_reference_copy.py --fingerprint behaviors_new.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PROBLEMS_DIR = REPO_ROOT / "benchmark" / "problems"

DEFAULT_THRESHOLD = 0.15   # flag if >15% of shard problems match reference exactly
# (At 30 problems: 5 matches triggers. At 40%, 12 matches were needed — far too lenient.)
MIN_PROBLEMS = 5           # need at least this many evaluated problems to check


def _diff_hash(diff_text: str) -> str:
    """Same normalization as evaluate.py._diff_hash."""
    lines = [ln.rstrip() for ln in diff_text.splitlines()]
    normalized = "\n".join(lines).strip()
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def write_summary(lines: list[str]) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a") as f:
            f.write("\n".join(lines) + "\n")
    else:
        print("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fingerprint", required=True,
                        help="Path to behavior fingerprint JSON from eval")
    parser.add_argument("--problems-dir", default=str(PROBLEMS_DIR),
                        help="Directory containing benchmark problems")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help=f"Match rate above which submission is flagged (default: {DEFAULT_THRESHOLD})")
    parser.add_argument("--min-problems", type=int, default=MIN_PROBLEMS,
                        help=f"Minimum problems required to run check (default: {MIN_PROBLEMS})")
    args = parser.parse_args()

    fp_path = Path(args.fingerprint)
    if not fp_path.exists():
        print(f"ERROR: fingerprint not found: {fp_path}", file=sys.stderr)
        sys.exit(2)

    fp = json.loads(fp_path.read_text())
    handle = fp.get("handle", fp_path.stem)
    agent_diffs: dict[str, str] = fp.get("diffs", {})

    if len(agent_diffs) < args.min_problems:
        msg = (f"Reference copy check: only {len(agent_diffs)} problems in fingerprint "
               f"(need {args.min_problems}) — skipping.")
        print(msg)
        write_summary([f"## Reference Copy Check", msg])
        sys.exit(0)

    problems_dir = Path(args.problems_dir)
    matches: list[str] = []
    checked: list[str] = []

    for problem_id, agent_hash in agent_diffs.items():
        if not agent_hash:
            continue
        ref_path = problems_dir / problem_id / "reference.diff"
        if not ref_path.exists():
            continue
        ref_hash = _diff_hash(ref_path.read_text())
        checked.append(problem_id)
        if agent_hash == ref_hash:
            matches.append(problem_id)

    if not checked:
        msg = "Reference copy check: no reference diffs found for evaluated problems — skipping."
        print(msg)
        write_summary(["## Reference Copy Check", msg])
        sys.exit(0)

    match_rate = len(matches) / len(checked)

    report: list[str] = [
        "## Reference Copy Check",
        f"Compared `{handle}` output diffs against reference diffs for **{len(checked)}** evaluated problems.",
        f"Threshold: >{args.threshold:.0%} match rate flags as likely hardcoding",
        "",
    ]

    if match_rate > args.threshold:
        report.append(
            f"> **BLOCKED** — {len(matches)}/{len(checked)} problems ({match_rate:.1%}) "
            f"match the reference diff exactly. This strongly indicates the agent is returning "
            f"stored reference diffs rather than reasoning about the problem."
        )
        report.append("")
        report.append("Matching problems: " + ", ".join(f"`{p}`" for p in sorted(matches)))
        report.append("")
        report.append(
            "Submissions must use an LLM agent scaffold to reason about the code — "
            "returning reference diffs verbatim is not a valid submission."
        )
        write_summary(report)
        print("\n".join(report), file=sys.stderr)
        sys.exit(1)

    report.append(
        f"✓ {len(matches)}/{len(checked)} reference matches ({match_rate:.1%}) — "
        f"below threshold. No hardcoding detected."
    )
    write_summary(report)
    print(f"Reference copy check: {len(matches)}/{len(checked)} matches ({match_rate:.1%}) — clean.")
    sys.exit(0)


if __name__ == "__main__":
    main()
