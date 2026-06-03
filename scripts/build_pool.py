"""
Build and refresh the benchmark problem pool using the Gittensor DAS API.

Primary source: api.gittensor.io/prs — all scored merged PRs across every
registered repo, with Gittensor's own scoring breakdown already computed.

For each candidate PR we:
  1. Fetch the PR body from DAS (/prs/details) and extract linked GitHub issues.
  2. Pull the actual diff + issue body from GitHub (diffs aren't in DAS).
  3. Apply quality filters and write the problem file.

DAS API gives us 1300+ merged PRs across all registered repos in one request,
avoiding GitHub rate-limit pagination entirely for discovery.

Usage:
    # Build / refresh the full pool
    python scripts/build_pool.py

    # Target a single repo
    python scripts/build_pool.py --repo phase-rs/phase

    # Dry run — show what would be added without writing
    python scripts/build_pool.py --dry-run

    # Override output directory
    python scripts/build_pool.py --output benchmark/problems

    # Limit new problems added per repo
    python scripts/build_pool.py --limit-per-repo 20
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import time
import urllib.request
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent
POOL_CONFIG_PATH = REPO_ROOT / "benchmark" / "pool_config.json"
DAS_API = "https://api.gittensor.io"
DAS_RATE_DELAY = 0.25  # seconds between DAS requests (50 req/10s limit)


def load_pool_config() -> dict:
    return json.loads(POOL_CONFIG_PATH.read_text())


def das_get(path: str) -> dict | list:
    url = f"{DAS_API}{path}"
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        # DAS API returns 403 to non-browser user-agents; use a standard one.
        "User-Agent": "Mozilla/5.0 (compatible; gittensor-base-miner/build_pool)",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def gh_api(endpoint: str) -> dict | list:
    result = subprocess.run(
        ["gh", "api", endpoint],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def gh_diff(repo: str, pr_number: int) -> str:
    result = subprocess.run(
        ["gh", "api", f"repos/{repo}/pulls/{pr_number}",
         "--header", "Accept: application/vnd.github.diff"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout


def extract_issue_numbers(body: str) -> list[int]:
    # Match standard GitHub close keywords (with/without trailing s/d/ed)
    # and "PR #N" references (maintainer PRs often say "PR #N fixed the bug")
    pattern = r"(?:fix(?:es|ed)?|close[sd]?|resolve[sd]?|closes?)\s+#(\d+)"
    found = [int(m) for m in re.findall(pattern, body or "", re.IGNORECASE)]
    if not found:
        # Fallback: bare "PR #N" reference — maintainers often say "PR #N added..."
        found = [int(m) for m in re.findall(r"\bPR\s+#(\d+)\b", body or "")]
    return found


def has_test_files(diff: str) -> bool:
    return bool(
        re.search(r"^diff --git a/test", diff, re.MULTILINE)
        or re.search(r"^diff --git .*/test_", diff, re.MULTILINE)
        or re.search(r"^diff --git .*/tests?/", diff, re.MULTILINE)
        or re.search(r"^diff --git .*/spec/", diff, re.MULTILINE)
        # Go: *_test.go
        or re.search(r"^diff --git .+_test\.go\b", diff, re.MULTILINE)
        # JS/TS: *.test.{ts,tsx,js,jsx} and *.spec.{ts,tsx,js,jsx}
        or re.search(r"^diff --git .+\.(test|spec)\.[jt]sx?", diff, re.MULTILINE)
        # Java: *Test.java, *Tests.java, *TestCase.java
        or re.search(r"^diff --git .+Tests?(?:Case)?\.java\b", diff, re.MULTILINE)
        # Ruby: *_spec.rb
        or re.search(r"^diff --git .+_spec\.rb\b", diff, re.MULTILINE)
        # Rust: inline tests — #[cfg(test)] blocks live in src/ files, not separate test files.
        # If the diff touches .rs files and the hunk text includes #[test] or #[cfg(test)],
        # the module has embedded unit tests that cargo test will execute.
        or (
            bool(re.search(r"^diff --git .+\.rs\b", diff, re.MULTILINE))
            and bool(re.search(r"#\[(?:cfg\(test\)|test)\]", diff))
        )
    )


def has_additions(diff: str) -> bool:
    """True if the diff adds at least 5 lines of code (not deletion-only).

    Deletion-only diffs score 0 on our token-overlap metric regardless of
    whether the agent solves the problem correctly, so they make bad benchmarks.
    """
    added = [
        line for line in diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]
    return len(added) >= 5


def is_substantive(pr: dict) -> bool:
    """True if the PR has meaningful scored code changes."""
    return (
        pr.get("totalNodesScored", 0) > 0
        and float(pr.get("tokenScore", 0)) > 0
    )


def get_file_tree(repo: str, commit: str) -> list[str]:
    try:
        data = gh_api(f"repos/{repo}/git/trees/{commit}?recursive=1")
        return [item["path"] for item in data.get("tree", []) if item["type"] == "blob"]
    except Exception:
        return []


def extract_added_file(diff: str, path: str) -> str | None:
    """
    Extract the full content of a newly-added file from a unified diff.
    Used as a fallback when the file doesn't exist at base_commit.
    """
    pattern = re.compile(
        r"diff --git a/" + re.escape(path) + r" b/" + re.escape(path) +
        r".*?(?=\ndiff --git |\Z)",
        re.DOTALL,
    )
    match = pattern.search(diff)
    if not match or "--- /dev/null" not in match.group(0):
        return None

    lines = []
    in_hunk = False
    for line in match.group(0).splitlines():
        if line.startswith("@@"):
            in_hunk = True
            continue
        if not in_hunk:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            lines.append(line[1:])
        elif line.startswith("\\"):
            pass
        elif not line.startswith("-"):
            lines.append(line)
    return "\n".join(lines) if lines else None


def select_context_files(
    repo: str, base_commit: str, diff: str, test_cmd: list[str] | None = None, max_files: int = 15
) -> list[dict]:
    changed_paths = re.findall(r"^diff --git a/(.+) b/", diff, re.MULTILINE)
    context_files = []
    fetched: set[str] = set()

    # Include source files changed in the diff.
    for path in changed_paths[:max_files]:
        if path in fetched:
            continue
        try:
            data = gh_api(f"repos/{repo}/contents/{path}?ref={base_commit}")
            content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            context_files.append({"path": path, "content": content})
            fetched.add(path)
        except Exception:
            # File may be newly added in this PR; extract from diff as fallback.
            content = extract_added_file(diff, path)
            if content is not None:
                context_files.append({"path": path, "content": content})
            fetched.add(path)

    # Include test files so agents know what they must satisfy.
    # First: explicit test file args in Python pytest commands.
    if test_cmd and test_cmd[0] == "python" and len(test_cmd) > 4:
        test_paths = [arg for arg in test_cmd[4:] if arg.endswith(".py") and not arg.startswith("-")]
        for path in test_paths[:3]:
            if path in fetched:
                continue
            try:
                data = gh_api(f"repos/{repo}/contents/{path}?ref={base_commit}")
                content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
                context_files.append({"path": path, "content": content})
            except Exception:
                content = extract_added_file(diff, path)
                if content is not None:
                    context_files.append({"path": path, "content": content})
            fetched.add(path)

    # Second: test files found in the diff (all languages).
    # Agents benefit from seeing what test assertions they need to pass.
    test_paths_in_diff = [
        p for p in changed_paths
        if (
            "test" in p.rsplit("/", 1)[-1].lower()
            or "spec" in p.rsplit("/", 1)[-1].lower()
            or "/tests/" in p
            or "/test/" in p
            or p.startswith("tests/")
            or p.startswith("test/")
        )
    ]
    for path in test_paths_in_diff[:3]:
        if path in fetched:
            continue
        try:
            data = gh_api(f"repos/{repo}/contents/{path}?ref={base_commit}")
            content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            context_files.append({"path": path, "content": content})
        except Exception:
            content = extract_added_file(diff, path)
            if content is not None:
                context_files.append({"path": path, "content": content})
        fetched.add(path)

    return context_files


def infer_test_cmd(repo: str, diff: str) -> list[str]:
    test_files = re.findall(
        r"^diff --git a/((?:[^/\s]*/)*(test_[^/\s]*\.py|[^/\s]*_test\.py))",
        diff, re.MULTILINE,
    )
    specific = [m[0] for m in test_files if m[0].endswith(".py")][:5]

    if specific:
        return ["python", "-m", "pytest", "--tb=short", "-q"] + specific

    if re.search(r"\.(rs)\b", diff):
        return ["cargo", "test"]
    if re.search(r"\.(ts|tsx|js|jsx)\b", diff):
        return ["npm", "test", "--", "--passWithNoTests"]
    if re.search(r"\.(java|kt)\b", diff):
        return ["./gradlew", "test"]
    if re.search(r"\.(go)\b", diff):
        return ["go", "test", "./..."]

    # Ruby / Rails — detect *_test.rb or test_*.rb files in diff
    rb_tests = re.findall(
        r"^diff --git a/((?:[^/\s]*/)*(?:test_[^/\s]*\.rb|[^/\s]*_test\.rb))",
        diff, re.MULTILINE,
    )
    if rb_tests:
        return ["bundle", "exec", "rails", "test"] + rb_tests[:5]
    if re.search(r"\.rb\b", diff):
        return ["bundle", "exec", "rails", "test"]

    return ["python", "-m", "pytest", "--tb=short", "-q"]


def make_problem_id(repo: str, pr_number: int) -> str:
    owner, name = repo.split("/", 1)
    # Legacy compat: entrius/gittensor keeps the bare PR number
    if repo == "entrius/gittensor":
        return f"{pr_number:04d}"
    return f"{owner}_{name}_{pr_number}"


def curate_pr(
    pr: dict,
    output_dir: Path,
    cutoff_date: str,
    dry_run: bool,
) -> bool:
    repo = pr["repository"]
    pr_number = pr["pullRequestNumber"]
    problem_id = make_problem_id(repo, pr_number)
    problem_out = output_dir / problem_id

    if (problem_out / "meta.json").exists():
        return False  # already in pool

    # Time-segmentation guard
    merged_at = pr.get("mergedAt", "")
    if not merged_at or merged_at < cutoff_date:
        print(f"  Skip {repo}#{pr_number}: before cutoff ({merged_at[:10] if merged_at else 'null'})")
        return False

    # Fetch PR body from DAS to extract linked issue
    try:
        time.sleep(DAS_RATE_DELAY)
        details = das_get(f"/prs/details?repo={repo}&number={pr_number}")
    except Exception as exc:
        print(f"  Skip {repo}#{pr_number}: DAS details failed ({exc})")
        return False

    body = details.get("description", "") or ""
    issue_numbers = extract_issue_numbers(body)

    # Fetch PR from GitHub for base_commit + fallback issue extraction
    try:
        pr_data = gh_api(f"repos/{repo}/pulls/{pr_number}")
    except subprocess.CalledProcessError:
        print(f"  Skip {repo}#{pr_number}: PR fetch failed")
        return False

    # If DAS body has no linked issue, fall back to GitHub PR body
    if not issue_numbers:
        gh_body = pr_data.get("body", "") or ""
        issue_numbers = extract_issue_numbers(gh_body)
    if not issue_numbers:
        print(f"  Skip {repo}#{pr_number}: no linked issue")
        return False

    # Fetch full issue from GitHub
    issue_number = issue_numbers[0]
    try:
        issue_data = gh_api(f"repos/{repo}/issues/{issue_number}")
    except subprocess.CalledProcessError:
        print(f"  Skip {repo}#{pr_number}: issue #{issue_number} fetch failed")
        return False

    # Reject issues with no meaningful body — agent has nothing to work from
    issue_body = issue_data.get("body") or ""
    if len(issue_body.strip()) < 50:
        print(f"  Skip {repo}#{pr_number}: issue body too short ({len(issue_body)} chars)")
        return False

    # Fetch diff from GitHub (not in DAS)
    try:
        diff = gh_diff(repo, pr_number)
    except subprocess.CalledProcessError:
        print(f"  Skip {repo}#{pr_number}: diff fetch failed")
        return False

    if not has_test_files(diff):
        print(f"  Skip {repo}#{pr_number}: no test files in diff")
        return False

    if not has_additions(diff):
        print(f"  Skip {repo}#{pr_number}: deletion-only diff (scores 0 on token-overlap)")
        return False

    if dry_run:
        print(f"  [DRY RUN] {repo}#{pr_number}: {issue_data['title'][:60]}")
        return True

    base_commit = pr_data["base"]["sha"]
    file_tree = get_file_tree(repo, base_commit)
    test_cmd = infer_test_cmd(repo, diff)
    context_files = select_context_files(repo, base_commit, diff, test_cmd=test_cmd)

    problem_out.mkdir(parents=True, exist_ok=True)
    context_out = problem_out / "context"
    context_out.mkdir(exist_ok=True)

    meta = {
        "id": problem_id,
        "repo_name": repo,
        "repo_url": f"https://github.com/{repo}",
        "base_commit": base_commit,
        "pr_number": pr_number,
        "issue_number": issue_number,
        "issue_title": issue_data["title"],
        "issue_body": issue_body,
        "merged_at": merged_at,
        "test_cmd": test_cmd,
        "time_limit_seconds": 120,
        "output_token_budget": 50_000,
        "file_tree": file_tree[:500],
        # Reference scores from DAS — used as labels, not re-computed
        "das_score": pr.get("score"),
        "das_base_score": pr.get("baseScore"),
        "das_token_score": pr.get("tokenScore"),
        "das_structural_score": pr.get("structuralScore"),
        "das_total_nodes": pr.get("totalNodesScored"),
    }
    (problem_out / "meta.json").write_text(json.dumps(meta, indent=2))

    for cf in context_files:
        out_path = context_out / cf["path"]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(cf["content"])

    (problem_out / "reference.diff").write_text(diff)

    print(f"  + {repo}#{pr_number}: {issue_data['title'][:60]}")
    return True


def fetch_das_pool(target_repo: str | None = None) -> list[dict]:
    """Fetch all merged, substantively-scored PRs from the DAS API."""
    print("Fetching scored PRs from DAS API...")
    prs = das_get("/prs")
    print(f"  {len(prs)} total PRs in DAS")

    candidates = [
        pr for pr in prs
        if pr.get("prState") == "MERGED"
        and is_substantive(pr)
        and (target_repo is None or pr["repository"].lower() == target_repo.lower())
    ]
    print(f"  {len(candidates)} merged+scored candidates")
    return candidates


def build_repo(
    repo: str,
    prs: list[dict],
    output_dir: Path,
    cutoff_date: str,
    limit_per_repo: int,
    dry_run: bool,
) -> int:
    repo_prs = [pr for pr in prs if pr["repository"].lower() == repo.lower()]
    if not repo_prs:
        return 0

    print(f"\n--- {repo} ({len(repo_prs)} candidates) ---")
    added = 0
    for pr in repo_prs:
        if added >= limit_per_repo:
            break
        if curate_pr(pr, output_dir, cutoff_date, dry_run):
            added += 1

    return added


def main() -> None:
    cfg = load_pool_config()

    parser = argparse.ArgumentParser(description="Build/refresh the benchmark problem pool from DAS API")
    parser.add_argument("--repo", help="Curate a single repo (default: all)")
    parser.add_argument("--pr-numbers", metavar="N,N,...",
                        help="Comma-separated PR numbers to curate (requires --repo)")
    parser.add_argument("--output", default=cfg["pool_dir"], help="Pool output directory")
    parser.add_argument("--limit-per-repo", type=int, default=50,
                        help="Max new problems per repo per run (default: 50; overridden by max_new_per_rotation in pool_config.json when called from refresh_pool.yml)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be added without writing files")
    args = parser.parse_args()

    if args.pr_numbers and not args.repo:
        parser.error("--pr-numbers requires --repo")

    output_dir = REPO_ROOT / args.output
    output_dir.mkdir(parents=True, exist_ok=True)
    cutoff = cfg["model_cutoff_date"]

    target_pr_numbers: set[int] | None = None
    if args.pr_numbers:
        target_pr_numbers = {int(n.strip()) for n in args.pr_numbers.split(",")}

    candidates = fetch_das_pool(target_repo=args.repo)

    # Filter to specific PR numbers if requested
    if target_pr_numbers is not None:
        candidates = [pr for pr in candidates if pr.get("pullRequestNumber") in target_pr_numbers]
        print(f"  Filtered to {len(candidates)} specific PRs: {sorted(target_pr_numbers)}")

    if args.repo:
        repos = [args.repo]
    else:
        # Deduplicate repo names preserving order from DAS response
        seen: set[str] = set()
        repos = []
        for pr in candidates:
            r = pr["repository"]
            if r not in seen:
                seen.add(r)
                repos.append(r)

    total = 0
    for repo in repos:
        added = build_repo(repo, candidates, output_dir, cutoff, args.limit_per_repo, args.dry_run)
        total += added

    existing = len(list(output_dir.glob("*/meta.json")))
    print(f"\nPool: {existing} total problems ({total} newly added)")
    print(f"Output: {output_dir}")


if __name__ == "__main__":
    main()
