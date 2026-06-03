"""
Expand the benchmark pool from prestigious external GitHub repos
not registered in the Gittensor DAS.

Sources problems from well-known open-source Python repos whose test
suites run in-process (no Redis, RabbitMQ, or other external services),
making them viable for Docker-based CI scoring.

Selection criteria (same as DAS pool):
  - PR merged after model_cutoff_date
  - PR body links to a GitHub issue (closes/fixes/resolves #N)
  - Diff includes test file changes
  - Diff has at least 5 added lines
  - Issue body is at least 50 chars

Usage:
    # Dry run — show qualifying problems without writing
    python scripts/expand_pool_external.py --dry-run

    # Target a single repo
    python scripts/expand_pool_external.py --repo pytest-dev/pytest

    # Limit per repo (default: 30)
    python scripts/expand_pool_external.py --limit-per-repo 20
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import time
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent
POOL_CONFIG_PATH = REPO_ROOT / "benchmark" / "pool_config.json"
GH_RATE_DELAY = 0.15  # seconds between GitHub API calls

# Prestigious external repos: self-contained test suites, active development,
# concrete bug-fix issues, high visibility.
EXTERNAL_REPOS = [
    # Python
    "pytest-dev/pytest",      # 14k stars — Python testing framework, perfect self-contained tests
    "pallets/click",          # 18k stars — Python CLI toolkit, no external deps
    "pallets/werkzeug",       # 7k stars  — Python WSGI utils, no external deps
    "encode/starlette",       # 12k stars — Python ASGI framework, asyncio only
    "psf/requests",           # 54k stars — Python HTTP, mocked in tests
    # Ruby
    "rubocop/rubocop",        # 13k stars — Ruby linter/formatter, RSpec tests, real cop bug-fixes
    "rubocop/rubocop-rails",  # 2k stars  — Rails-specific cops, same RSpec harness
]


def load_pool_config() -> dict:
    return json.loads(POOL_CONFIG_PATH.read_text())


def gh_api(endpoint: str) -> dict | list:
    result = subprocess.run(
        ["gh", "api", endpoint],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def gh_api_paginate(endpoint: str, per_page: int = 100, max_pages: int = 10) -> list[dict]:
    """Fetch all pages of a GitHub list endpoint."""
    results = []
    sep = "&" if "?" in endpoint else "?"
    for page in range(1, max_pages + 1):
        data = gh_api(f"{endpoint}{sep}per_page={per_page}&page={page}")
        if not data:
            break
        results.extend(data)
        if len(data) < per_page:
            break
        time.sleep(GH_RATE_DELAY)
    return results


def gh_diff(repo: str, pr_number: int) -> str:
    result = subprocess.run(
        ["gh", "api", f"repos/{repo}/pulls/{pr_number}",
         "--header", "Accept: application/vnd.github.diff"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout


def extract_issue_numbers(body: str) -> list[int]:
    pattern = r"(?:fix(?:es|ed)?|close[sd]?|resolve[sd]?|closes?)\s+#(\d+)"
    found = [int(m) for m in re.findall(pattern, body or "", re.IGNORECASE)]
    if not found:
        found = [int(m) for m in re.findall(r"\bPR\s+#(\d+)\b", body or "")]
    return found


def has_test_files(diff: str) -> bool:
    return bool(
        re.search(r"^diff --git a/test", diff, re.MULTILINE)
        or re.search(r"^diff --git .*/test_", diff, re.MULTILINE)
        or re.search(r"^diff --git .*/tests?/", diff, re.MULTILINE)
        or re.search(r"^diff --git .*/spec/", diff, re.MULTILINE)
        or re.search(r"^diff --git .+_test\.go\b", diff, re.MULTILINE)
        or re.search(r"^diff --git .+\.(test|spec)\.[jt]sx?", diff, re.MULTILINE)
        or re.search(r"^diff --git .+Tests?(?:Case)?\.java\b", diff, re.MULTILINE)
        or re.search(r"^diff --git .+_spec\.rb\b", diff, re.MULTILINE)
    )


def has_source_changes(diff: str) -> bool:
    """True if the diff modifies at least one non-test, non-changelog source file.

    Filters out test-only PRs — those score 0 for miners regardless of
    correctness because src_tok counts source file changes only.
    Also filters changelog/news-fragment files (towncrier .misc/.bugfix/.feature
    fragments, CHANGES.rst, etc.) which look like source paths but aren't code.
    """
    # Towncrier fragment extensions (never real source)
    _CHANGELOG_EXTS = {".misc", ".bugfix", ".feature", ".deprecation", ".removal",
                       ".doc", ".trivial", ".breaking"}
    # Changelog directories
    _CHANGELOG_DIRS = {"newsfragments", "news", "changelog", "changelogs", "changes"}

    for line in diff.splitlines():
        if not line.startswith("diff --git "):
            continue
        m = re.search(r" b/(.+)$", line)
        if not m:
            continue
        path = m.group(1)
        parts = path.lower().split("/")
        filename = parts[-1]
        # Skip test directories and files
        if any(d in ("tests", "test", "__tests__", "spec") for d in parts[:-1]):
            continue
        if filename.startswith("test_") or "_test." in filename:
            continue
        if ".spec." in filename or filename.endswith(".spec"):
            continue
        if re.search(r"tests?(?:case)?\.(?:java|kt|scala)$", filename):
            continue
        if filename.endswith("_spec.rb"):
            continue
        if filename.endswith("_test.go"):
            continue
        # Skip changelog / news fragment files
        if any(d in _CHANGELOG_DIRS for d in parts[:-1]):
            continue
        _, ext = os.path.splitext(filename)
        if ext in _CHANGELOG_EXTS:
            continue
        if filename in ("changelog.md", "changes.rst", "news.rst", "history.rst",
                        "history.md", "release-notes.md", "release_notes.md"):
            continue
        return True
    return False


def has_additions(diff: str) -> bool:
    added = [
        line for line in diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]
    return len(added) >= 5


def get_file_tree(repo: str, commit: str) -> list[str]:
    try:
        data = gh_api(f"repos/{repo}/git/trees/{commit}?recursive=1")
        return [item["path"] for item in data.get("tree", []) if item["type"] == "blob"]
    except Exception:
        return []


def extract_added_file(diff: str, path: str) -> str | None:
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
        elif not line.startswith("-") and not line.startswith("\\"):
            lines.append(line)
    return "\n".join(lines) if lines else None


def infer_test_cmd(repo: str, diff: str) -> list[str]:
    """Infer the test command from changed files in the diff.

    Handles Python (pytest), Ruby (bundle exec rspec), with Python as default.
    """
    changed = re.findall(r"^diff --git a/(.+) b/", diff, re.MULTILINE)

    # Ruby: _spec.rb files → bundle exec rspec <specs>
    spec_files = [p for p in changed if p.endswith("_spec.rb")][:5]
    if spec_files:
        return ["bundle", "exec", "rspec", "--format", "progress"] + spec_files

    # Python: test_*.py / *_test.py files → pytest <files>
    test_files = re.findall(
        r"^diff --git a/((?:[^/\s]*/)*(test_[^/\s]*\.py|[^/\s]*_test\.py))",
        diff, re.MULTILINE,
    )
    specific = [m[0] for m in test_files if m[0].endswith(".py")][:5]
    base = ["python", "-m", "pytest", "--tb=short", "-q"]
    if specific:
        return base + specific
    for pat in (r"^diff --git a/(tests?/[^/\s]+\.py)", r"^diff --git a/(testing/[^/\s]+\.py)"):
        hits = re.findall(pat, diff, re.MULTILINE)
        if hits:
            return base + list(dict.fromkeys(hits[:5]))
    return base


def select_context_files(
    repo: str, base_commit: str, diff: str, test_cmd: list[str] | None = None, max_files: int = 15
) -> list[dict]:
    changed_paths = re.findall(r"^diff --git a/(.+) b/", diff, re.MULTILINE)
    context_files = []
    fetched: set[str] = set()

    for path in changed_paths[:max_files]:
        if path in fetched:
            continue
        try:
            data = gh_api(f"repos/{repo}/contents/{path}?ref={base_commit}")
            content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            context_files.append({"path": path, "content": content})
            fetched.add(path)
        except Exception:
            content = extract_added_file(diff, path)
            if content is not None:
                context_files.append({"path": path, "content": content})
            fetched.add(path)

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


def make_problem_id(repo: str, pr_number: int) -> str:
    safe = repo.replace("/", "_").replace("-", "_").lower()
    return f"{safe}_{pr_number}"


def curate_github_pr(
    repo: str,
    pr_data: dict,
    output_dir: Path,
    cutoff_date: str,
    dry_run: bool,
) -> bool:
    """Curate a single GitHub PR (no DAS dependency)."""
    pr_number = pr_data["number"]
    problem_id = make_problem_id(repo, pr_number)
    problem_out = output_dir / problem_id

    if (problem_out / "meta.json").exists():
        return False

    merged_at = pr_data.get("merged_at") or ""
    if not merged_at or merged_at < cutoff_date:
        return False

    body = pr_data.get("body") or ""
    issue_numbers = extract_issue_numbers(body)
    if not issue_numbers:
        print(f"  Skip {repo}#{pr_number}: no linked issue")
        return False

    issue_number = issue_numbers[0]
    try:
        time.sleep(GH_RATE_DELAY)
        issue_data = gh_api(f"repos/{repo}/issues/{issue_number}")
    except subprocess.CalledProcessError:
        print(f"  Skip {repo}#{pr_number}: issue #{issue_number} fetch failed")
        return False

    issue_body = issue_data.get("body") or ""
    if len(issue_body.strip()) < 50:
        print(f"  Skip {repo}#{pr_number}: issue body too short ({len(issue_body)} chars)")
        return False

    try:
        time.sleep(GH_RATE_DELAY)
        diff = gh_diff(repo, pr_number)
    except subprocess.CalledProcessError:
        print(f"  Skip {repo}#{pr_number}: diff fetch failed")
        return False

    if not has_test_files(diff):
        print(f"  Skip {repo}#{pr_number}: no test files in diff")
        return False

    if not has_source_changes(diff):
        print(f"  Skip {repo}#{pr_number}: test-only diff (no source changes; scores 0)")
        return False

    if not has_additions(diff):
        print(f"  Skip {repo}#{pr_number}: deletion-only diff")
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
        # No DAS scores for external repos
        "das_score": None,
        "das_base_score": None,
        "das_token_score": None,
        "das_structural_score": None,
        "das_total_nodes": None,
        "external": True,
    }
    (problem_out / "meta.json").write_text(json.dumps(meta, indent=2))

    for cf in context_files:
        out_path = context_out / cf["path"]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(cf["content"])

    (problem_out / "reference.diff").write_text(diff)

    print(f"  + {repo}#{pr_number}: {issue_data['title'][:60]}")
    return True


def build_external_repo(
    repo: str,
    output_dir: Path,
    cutoff_date: str,
    limit_per_repo: int,
    dry_run: bool,
) -> int:
    print(f"\n--- {repo} ---")
    print(f"  Fetching merged PRs since {cutoff_date}...")

    try:
        all_prs = gh_api_paginate(
            f"repos/{repo}/pulls?state=closed&sort=updated&direction=desc",
            per_page=100,
            max_pages=15,
        )
    except subprocess.CalledProcessError as exc:
        print(f"  Failed to fetch PRs: {exc}")
        return 0

    # Filter to merged PRs after cutoff
    candidates = [
        pr for pr in all_prs
        if pr.get("merged_at") and pr["merged_at"] >= cutoff_date
    ]
    print(f"  {len(candidates)} merged PRs since cutoff (out of {len(all_prs)} closed)")

    added = 0
    for pr in candidates:
        if added >= limit_per_repo:
            break
        if curate_github_pr(repo, pr, output_dir, cutoff_date, dry_run):
            added += 1

    print(f"  Added {added} problems from {repo}")
    return added


def update_pool_config(repos: list[str]) -> None:
    """Add external repos to pool_config.json under external_repos."""
    cfg = json.loads(POOL_CONFIG_PATH.read_text())
    existing = set(cfg.get("external_repos", []))
    new_repos = [r for r in repos if r not in existing]
    if new_repos:
        cfg.setdefault("external_repos", []).extend(new_repos)
        POOL_CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
        print(f"\nAdded {len(new_repos)} repos to pool_config.json external_repos")


def main() -> None:
    cfg = load_pool_config()

    parser = argparse.ArgumentParser(
        description="Expand benchmark pool from external prestigious GitHub repos"
    )
    parser.add_argument("--repo", help="Target a single repo (default: all EXTERNAL_REPOS)")
    parser.add_argument("--output", default=cfg["pool_dir"], help="Pool output directory")
    parser.add_argument("--limit-per-repo", type=int, default=30,
                        help="Max new problems per repo (default: 30)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be added without writing files")
    args = parser.parse_args()

    output_dir = REPO_ROOT / args.output
    output_dir.mkdir(parents=True, exist_ok=True)
    cutoff = cfg["model_cutoff_date"]

    target_repos = [args.repo] if args.repo else EXTERNAL_REPOS

    total = 0
    for repo in target_repos:
        added = build_external_repo(repo, output_dir, cutoff, args.limit_per_repo, args.dry_run)
        total += added

    existing = len(list(output_dir.glob("*/meta.json")))
    print(f"\nPool: {existing} total problems ({total} newly {'would-be-' if args.dry_run else ''}added)")
    print(f"Output: {output_dir}")

    if not args.dry_run and total > 0:
        update_pool_config(target_repos)


if __name__ == "__main__":
    main()
