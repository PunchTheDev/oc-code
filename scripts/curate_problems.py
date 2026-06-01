"""
Tooling for curating benchmark problems from real Gittensor merged PRs.

Selection criteria:
  - PR must be merged (not just closed)
  - PR must close a GitHub issue (linked via "Fixes #N" or "Closes #N")
  - Issue must have been filed before the PR was opened
  - At least one test file must be changed or added in the PR
  - Patch must be self-contained and apply cleanly to base_commit
  - Problem must fall after the agent model cutoff (time-segmentation)

Usage:
    python scripts/curate_problems.py --repo entrius/gittensor --output benchmark/problems/
    python scripts/curate_problems.py --repo entrius/gittensor --pr 123 --output benchmark/problems/
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


# Cutoff: only include PRs merged after this date to prevent memorization.
# Update this when the whitelisted model's training cutoff is known.
MODEL_CUTOFF_DATE = "2024-06-01"


def gh_get(endpoint: str) -> dict | list:
    result = subprocess.run(
        ["gh", "api", endpoint],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def extract_issue_numbers(body: str) -> list[int]:
    """Find 'Fixes #N', 'Closes #N', 'Resolves #N' in PR body."""
    pattern = r"(?:fixes|closes|resolves)\s+#(\d+)"
    return [int(m) for m in re.findall(pattern, body or "", re.IGNORECASE)]


def get_pr_diff(repo: str, pr_number: int) -> str:
    result = subprocess.run(
        ["gh", "api", f"repos/{repo}/pulls/{pr_number}", "--header", "Accept: application/vnd.github.diff"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout


def has_test_files(diff: str) -> bool:
    return bool(re.search(r"^diff --git a/test", diff, re.MULTILINE)
                or re.search(r"^diff --git .*/test_", diff, re.MULTILINE))


def get_file_tree(repo: str, commit: str) -> list[str]:
    """Get list of all file paths at a given commit."""
    result = subprocess.run(
        ["gh", "api", f"repos/{repo}/git/trees/{commit}?recursive=1"],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(result.stdout)
    return [item["path"] for item in data.get("tree", []) if item["type"] == "blob"]


def select_context_files(repo: str, base_commit: str, diff: str, max_files: int = 15) -> list[dict]:
    """Select the most relevant files for context from the diff."""
    changed_paths = re.findall(r"^diff --git a/(.+) b/", diff, re.MULTILINE)
    # Also grab a few key files (e.g. README, main module) if not already included
    context_files = []
    fetched = set()

    for path in changed_paths[:max_files]:
        if path in fetched:
            continue
        try:
            result = subprocess.run(
                ["gh", "api", f"repos/{repo}/contents/{path}?ref={base_commit}"],
                capture_output=True, text=True, check=True,
            )
            data = json.loads(result.stdout)
            import base64
            content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            context_files.append({"path": path, "content": content})
            fetched.add(path)
        except Exception:
            pass

    return context_files


def curate_pr(repo: str, pr_number: int, output_dir: Path, problem_id: str) -> bool:
    print(f"  Curating PR #{pr_number}...")

    pr_data = gh_get(f"repos/{repo}/pulls/{pr_number}")
    if pr_data.get("state") != "closed" or not pr_data.get("merged_at"):
        print(f"    Skip: not merged")
        return False

    merged_at = pr_data["merged_at"]
    if merged_at < MODEL_CUTOFF_DATE:
        print(f"    Skip: merged before cutoff ({merged_at})")
        return False

    issue_numbers = extract_issue_numbers(pr_data.get("body", ""))
    if not issue_numbers:
        print(f"    Skip: no linked issue")
        return False

    issue_data = gh_get(f"repos/{repo}/issues/{issue_numbers[0]}")
    if issue_data.get("created_at", "") >= pr_data.get("created_at", ""):
        print(f"    Skip: issue created after PR")
        return False

    diff = get_pr_diff(repo, pr_number)
    if not has_test_files(diff):
        print(f"    Skip: no test files in diff")
        return False

    # base_commit = the commit just before this PR's base
    base_commit = pr_data["base"]["sha"]
    file_tree = get_file_tree(repo, base_commit)
    context_files = select_context_files(repo, base_commit, diff)

    problem_out = output_dir / problem_id
    problem_out.mkdir(parents=True, exist_ok=True)
    context_out = problem_out / "context"
    context_out.mkdir(exist_ok=True)

    # Write meta.json
    meta = {
        "id": problem_id,
        "repo_name": repo,
        "repo_url": f"https://github.com/{repo}",
        "base_commit": base_commit,
        "pr_number": pr_number,
        "issue_number": issue_numbers[0],
        "issue_title": issue_data["title"],
        "issue_body": issue_data["body"] or "",
        "merged_at": merged_at,
        "test_cmd": ["python", "-m", "pytest", "--tb=short", "-q"],
        "time_limit_seconds": 120,
        "output_token_budget": 50_000,
        "file_tree": file_tree[:500],  # cap for JSON size
    }
    (problem_out / "meta.json").write_text(json.dumps(meta, indent=2))

    # Write context files
    for cf in context_files:
        out_path = context_out / cf["path"]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(cf["content"])

    # Write reference diff (the accepted solution — used as a signal, not the answer key)
    (problem_out / "reference.diff").write_text(diff)

    print(f"    OK: {issue_data['title'][:60]}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Curate benchmark problems from merged PRs")
    parser.add_argument("--repo", default="entrius/gittensor", help="GitHub repo (owner/name)")
    parser.add_argument("--pr", type=int, help="Curate a specific PR number")
    parser.add_argument("--output", default="benchmark/problems", help="Output directory")
    parser.add_argument("--limit", type=int, default=30, help="Max problems to curate")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.pr:
        curate_pr(args.repo, args.pr, output_dir, f"{args.pr:03d}")
        return

    # Fetch recent merged PRs (paginate until we have enough candidates)
    print(f"Fetching merged PRs from {args.repo}...")
    merged_prs = []
    for page in range(1, 6):
        prs = gh_get(f"repos/{args.repo}/pulls?state=closed&per_page=100&page={page}&sort=updated&direction=desc")
        if not prs:
            break
        page_merged = [pr for pr in prs if pr.get("merged_at")]
        merged_prs.extend(page_merged)
        if len(prs) < 100:
            break  # last page

    curated = 0
    for pr in merged_prs:
        if curated >= args.limit:
            break
        problem_id = f"{pr['number']:03d}"
        if (output_dir / problem_id / "meta.json").exists():
            print(f"  Skip #{pr['number']}: already curated")
            curated += 1
            continue
        if curate_pr(args.repo, pr["number"], output_dir, problem_id):
            curated += 1

    print(f"\nCurated {curated} problems to {output_dir}")


if __name__ == "__main__":
    main()
