"""
Scores a candidate patch against a benchmark problem.

Mirrors Gittensor's native scoring formula exactly:
  base_score = MERGED_PR_BASE_SCORE * (1 - exp(-src_tok / scale))
             + min(total_score / CONTRIBUTION_SCORE_FOR_FULL_BONUS, 1) * MAX_CONTRIBUTION_BONUS

  where:
    MERGED_PR_BASE_SCORE = 25  (cap on quality term)
    MAX_CONTRIBUTION_BONUS = 5  (cross-category bonus cap)
    SRC_TOK_SATURATION_SCALE = 58.0 (per-repo overridable; default)
    CONTRIBUTION_SCORE_FOR_FULL_BONUS = 1500

Correctness gates everything: tests must pass before quality is computed.
Final score is the base_score (0–30 scale, same as Gittensor native).

Scoring path (primary): uses the actual Gittensor tree-sitter AST scorer
from benchmark/harness/tree_sitter_scorer.py — same weights JSON, same
structural/leaf node taxonomy. Produces scores that match DAS output.

Fallback (when tree_sitter is unavailable): heuristic token count on the
diff. Heuristic scores run ~2× above DAS; flag is set in scoring_note.

Usage:
    python benchmark/harness/score.py --problem benchmark/problems/930/ --patch my.diff
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Ensure repo root is on sys.path so benchmark.harness imports work whether
# this module is run as a script or imported as a package.
_REPO_ROOT = Path(__file__).parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Gittensor native constants (gittensor/constants.py)
MERGED_PR_BASE_SCORE = 25
SRC_TOK_SATURATION_SCALE = 58.0
MAX_CONTRIBUTION_BONUS = 5
CONTRIBUTION_SCORE_FOR_FULL_BONUS = 1500


def _repo_cache_dir() -> Path:
    """Return (and create) the gitminer repo cache directory."""
    cache = Path(os.environ.get("GITMINER_CACHE", Path.home() / ".cache" / "gitminer" / "repos"))
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def _cached_repo(repo_url: str) -> Path:
    """
    Return a path to a local bare-ish clone of repo_url.

    On first call: git clone into ~/.cache/gitminer/repos/{owner}_{repo}.
    On subsequent calls: git fetch to pull in new commits (best-effort).
    This eliminates repeated full clones when evaluating multiple problems
    from the same repository.
    """
    parts = repo_url.rstrip("/").split("/")
    key = "_".join(parts[-2:])  # owner_repo
    cached = _repo_cache_dir() / key

    if not cached.exists():
        subprocess.run(
            ["git", "clone", "--quiet", repo_url, str(cached)],
            check=True, capture_output=True,
        )
    else:
        subprocess.run(
            ["git", "-C", str(cached), "fetch", "--quiet", "--all"],
            capture_output=True,  # best-effort — don't fail when offline
        )

    return cached


def load_problem_meta(problem_dir: Path) -> dict:
    meta_path = problem_dir / "meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"meta.json not found in {problem_dir}")
    return json.loads(meta_path.read_text())


def apply_patch(repo_dir: Path, patch_path: Path) -> bool:
    """Apply a unified diff. Returns True if apply succeeded."""
    abs_patch = str(patch_path.resolve())
    result = subprocess.run(
        ["git", "apply", "--check", abs_patch],
        cwd=repo_dir,
        capture_output=True,
    )
    if result.returncode != 0:
        return False
    subprocess.run(
        ["git", "apply", abs_patch],
        cwd=repo_dir,
        check=True,
    )
    return True


def run_tests(repo_dir: Path, test_cmd: list[str]) -> tuple[bool, str, bool]:
    """Run the test suite. Returns (passed, output, all_skipped).

    all_skipped is True when pytest exits with code 5 (no tests collected —
    typically because importorskip fired due to missing heavy deps like
    bittensor). Docker CI installs full deps so this never happens there.
    Local --no-sandbox mode treats all_skipped as a soft pass so miners can
    still receive diff-quality scores during development.
    """
    result = subprocess.run(
        test_cmd,
        cwd=repo_dir,
        capture_output=True,
        text=True,
        timeout=300,
    )
    output = result.stdout + result.stderr
    # returncode 5 = no tests collected (all skipped via importorskip)
    all_skipped = result.returncode == 5 and "failed" not in output.lower()
    passed = result.returncode == 0 or all_skipped
    return passed, output, all_skipped


# Words to skip when tokenizing added diff lines (noise, not signal)
_SKIP_PATTERNS = re.compile(
    r"^(#|//|/\*|\*|<!--|\"\"\"|'''|pass$|\.\.\.)"
)

# Structural node types that get higher weight in tree-sitter scoring
_STRUCTURAL_RE = re.compile(
    r"\b(def |class |async def |fn |impl |struct |func |interface |"
    r"enum |trait |type |const |let |var |pub |protected |private )\b"
)


def approximate_src_token_score(diff_text: str, saturation_scale: float = SRC_TOK_SATURATION_SCALE) -> tuple[float, float]:
    """
    Approximate Gittensor's src_token_score and total_score from a unified diff.

    Returns (source_token_score, total_score) where:
      - source_token_score drives the main base_score curve
      - total_score drives the cross-category contribution bonus

    The approximation counts meaningful code tokens in added lines using a
    weighted heuristic. Structural constructs (def/class/fn/struct/...) get
    higher weight (≈2–3x leaf identifiers), matching tree-sitter's structural
    node bonus weights.

    Accuracy: rough estimate only. Local scores typically run ~2× higher than
    DAS reference scores (measured: local mean 23.47 vs DAS mean 10.78 across
    289 reference diffs). Use for relative iteration only; CI gives authoritative scores.
    """
    lines = diff_text.splitlines()
    src_score = 0.0
    total_score = 0.0
    in_test_file = False

    for line in lines:
        # Track which file we're in
        if line.startswith("diff --git"):
            path_match = re.search(r"b/(.+)$", line)
            if path_match:
                path = path_match.group(1)
                in_test_file = (
                    "/test" in path or
                    path.startswith("test") or
                    "_test." in path or
                    "test_" in path.split("/")[-1] or
                    "spec." in path.lower()
                )
            continue

        if not line.startswith("+") or line.startswith("+++"):
            continue

        content = line[1:].strip()
        if not content or _SKIP_PATTERNS.match(content):
            continue

        # Count tokens: split on whitespace and punctuation, filter noise
        tokens = re.split(r"[\s\(\)\[\]{},;:=<>!&|.\"\'`@#$%^~\\]+", content)
        meaningful = [t for t in tokens if len(t) > 1 and not t.isdigit()]
        if not meaningful:
            continue

        # Base weight per meaningful token
        token_count = len(meaningful)

        # Structural bonus: lines with structural constructs score higher
        structural_bonus = 0.0
        if _STRUCTURAL_RE.search(content):
            structural_bonus = token_count * 1.5  # matches ~2x structural weight

        line_score = token_count + structural_bonus

        total_score += line_score
        if not in_test_file:
            src_score += line_score

    return src_score, total_score


def compute_base_score(
    source_token_score: float,
    total_score: float,
    saturation_scale: float = SRC_TOK_SATURATION_SCALE,
) -> float:
    """
    Gittensor base_score formula (gittensor/validator/oss_contributions/mirror/scoring.py):

        initial = MERGED_PR_BASE_SCORE * (1 - exp(-src_tok / scale))
        bonus_pct = min(total_score / CONTRIBUTION_SCORE_FOR_FULL_BONUS, 1.0)
        base_score = initial + bonus_pct * MAX_CONTRIBUTION_BONUS
    """
    initial = MERGED_PR_BASE_SCORE * (1.0 - math.exp(-source_token_score / saturation_scale))
    bonus_pct = min(1.0, total_score / CONTRIBUTION_SCORE_FOR_FULL_BONUS)
    contribution_bonus = round(bonus_pct * MAX_CONTRIBUTION_BONUS, 2)
    return round(initial + contribution_bonus, 2)


def score_diff_quality(problem_dir: Path, patch_path: Path) -> tuple[float, float, float]:
    """
    Compute tree-sitter quality score without running tests.

    Used by baseline_scores.py to score reference diffs quickly.
    Returns (source_token_score, total_token_score, base_score).
    Falls back to heuristic if tree-sitter is unavailable.
    """
    meta = load_problem_meta(problem_dir)
    saturation_scale = float(meta.get("src_tok_saturation_scale", SRC_TOK_SATURATION_SCALE))
    diff_text = patch_path.read_text()

    cached = _cached_repo(meta["repo_url"])
    base_commit = meta["base_commit"]

    with tempfile.TemporaryDirectory(prefix="bminer_qual_") as tmpdir:
        worktree = Path(tmpdir) / "repo"
        r = subprocess.run(
            ["git", "-C", str(cached), "worktree", "add",
             "--detach", "--force", str(worktree), base_commit],
            capture_output=True,
        )
        if r.returncode != 0:
            # Commit may be missing from cached clone — fetch it explicitly.
            subprocess.run(
                ["git", "-C", str(cached), "fetch", "--quiet", "origin", base_commit],
                capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(cached), "worktree", "add",
                 "--detach", "--force", str(worktree), base_commit],
                check=True, capture_output=True,
            )
        patch_applied = False
        try:
            file_pairs = _build_file_pairs(worktree, diff_text)
            patch_applied = apply_patch(worktree, patch_path)
            if patch_applied and file_pairs is not None:
                _fill_new_contents(worktree, file_pairs)
        finally:
            subprocess.run(
                ["git", "-C", str(cached), "worktree", "remove", "--force", str(worktree)],
                capture_output=True,
            )

    # Try tree-sitter (only when patch applied — else new == old, delta is zero)
    if patch_applied and file_pairs is not None:
        try:
            from benchmark.harness.tree_sitter_scorer import score_file_pairs, available
            if available():
                result = score_file_pairs(file_pairs)
                if result is not None:
                    src_tok, total_tok = result
                    return src_tok, total_tok, compute_base_score(src_tok, total_tok, saturation_scale)
        except Exception:
            pass

    # Fallback: heuristic
    src_tok, total_tok = approximate_src_token_score(diff_text, saturation_scale)
    return src_tok, total_tok, compute_base_score(src_tok, total_tok, saturation_scale)


def score_patch(problem_dir: Path, patch_path: Path) -> dict:
    meta = load_problem_meta(problem_dir)
    saturation_scale = float(meta.get("src_tok_saturation_scale", SRC_TOK_SATURATION_SCALE))

    # Use a cached clone so repeated evals on the same repo skip the network round-trip.
    # Each problem gets an isolated git worktree checked out at the exact base commit.
    cached = _cached_repo(meta["repo_url"])

    base_commit = meta["base_commit"]

    with tempfile.TemporaryDirectory(prefix="bminer_") as tmpdir:
        worktree = Path(tmpdir) / "repo"

        r = subprocess.run(
            ["git", "-C", str(cached), "worktree", "add",
             "--detach", "--force", str(worktree), base_commit],
            capture_output=True,
        )
        if r.returncode != 0:
            subprocess.run(
                ["git", "-C", str(cached), "fetch", "--quiet", "origin", base_commit],
                capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(cached), "worktree", "add",
                 "--detach", "--force", str(worktree), base_commit],
                check=True, capture_output=True,
            )
        try:
            return _score_in_worktree(worktree, meta, patch_path, saturation_scale)
        finally:
            subprocess.run(
                ["git", "-C", str(cached), "worktree", "remove", "--force", str(worktree)],
                capture_output=True,
            )


def _parse_diff_paths(diff_text: str) -> list[tuple[str, str]]:
    """Return [(path, status)] from diff headers. Status: 'added'|'removed'|'modified'."""
    results = []
    current_old: str | None = None
    current_new: str | None = None
    is_new = False
    is_removed = False

    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            if current_new is not None:
                status = "added" if is_new else ("removed" if is_removed else "modified")
                path = current_new if current_new != "/dev/null" else (current_old or "")
                path = path.removeprefix("b/")
                results.append((path, status))
            current_old = None
            current_new = None
            is_new = False
            is_removed = False
        elif line.startswith("--- "):
            current_old = line[4:]
        elif line.startswith("+++ "):
            current_new = line[4:]
        elif line.startswith("new file mode"):
            is_new = True
        elif line.startswith("deleted file mode"):
            is_removed = True

    if current_new is not None:
        status = "added" if is_new else ("removed" if is_removed else "modified")
        path = current_new if current_new != "/dev/null" else (current_old or "")
        path = path.removeprefix("b/")
        results.append((path, status))

    return results


def _read_file_safe(path: Path) -> str | None:
    """Read a file as text; return None on error or if binary."""
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def _build_file_pairs(repo_dir: Path, diff_text: str) -> "list | None":
    """
    Extract old/new file content pairs for tree-sitter scoring.

    Must be called BEFORE applying the patch (to capture old content).
    Returns a list of FilePair objects, or None if the import fails.
    """
    try:
        from benchmark.harness.tree_sitter_scorer import FilePair
    except ImportError:
        return None

    paths = _parse_diff_paths(diff_text)
    pairs = []

    for rel_path, status in paths:
        abs_path = repo_dir / rel_path
        if status == "added":
            pairs.append(FilePair(rel_path, old_content=None, new_content=None))
        elif status == "removed":
            old = _read_file_safe(abs_path)
            pairs.append(FilePair(rel_path, old_content=old, new_content=None))
        else:
            old = _read_file_safe(abs_path)
            pairs.append(FilePair(rel_path, old_content=old, new_content=None))

    return pairs


def _fill_new_contents(repo_dir: Path, pairs: list) -> None:
    """Fill new_content on each FilePair after the patch has been applied."""
    for pair in pairs:
        if pair.new_content is None and pair.old_content is not None or \
                pair.new_content is None and pair.old_content is None:
            abs_path = repo_dir / pair.path
            pair.new_content = _read_file_safe(abs_path)


def _score_in_worktree(
    repo_dir: Path, meta: dict, patch_path: Path, saturation_scale: float
) -> dict:
    problem_id = meta["id"]
    diff_text = patch_path.read_text()

    # Capture old file contents before applying the patch.
    file_pairs = _build_file_pairs(repo_dir, diff_text)

    patch_applied = apply_patch(repo_dir, patch_path)
    if not patch_applied:
        return {
            "problem_id": problem_id,
            "patch_applied": False,
            "tests_passed": False,
            "source_token_score": 0.0,
            "base_score": 0.0,
            "final_score": 0.0,
        }

    # Capture new file contents after applying the patch.
    if file_pairs is not None:
        _fill_new_contents(repo_dir, file_pairs)

    raw_cmd = meta.get("test_cmd", ["python3", "-m", "pytest", "--tb=short", "-q"])
    test_cmd = [
        ("python3" if c == "python" and not shutil.which("python") else c)
        for c in raw_cmd
    ]
    tests_passed, test_output, all_skipped = run_tests(repo_dir, test_cmd)

    if not tests_passed:
        return {
            "problem_id": problem_id,
            "patch_applied": True,
            "tests_passed": False,
            "test_output": test_output[-2000:],
            "source_token_score": 0.0,
            "base_score": 0.0,
            "final_score": 0.0,
        }

    # Primary: tree-sitter AST scorer (matches DAS scoring engine)
    tree_sitter_result = None
    if file_pairs is not None:
        try:
            from benchmark.harness.tree_sitter_scorer import score_file_pairs, available
            if available():
                tree_sitter_result = score_file_pairs(file_pairs)
        except Exception:
            pass

    if tree_sitter_result is not None:
        src_tok, total_tok = tree_sitter_result
        scoring_method = "tree-sitter"
        scoring_note = "Gittensor native tree-sitter AST scorer (matches DAS)"
    else:
        # Fallback: heuristic diff-token count
        src_tok, total_tok = approximate_src_token_score(diff_text, saturation_scale)
        scoring_method = "heuristic"
        scoring_note = (
            "heuristic diff-token approximation (~2× above DAS) — "
            "install tree-sitter and tree-sitter-language-pack for accurate scoring"
        )

    if all_skipped:
        scoring_note += (
            " | tests skipped locally (missing heavy deps) — "
            "Docker CI runs full correctness check"
        )

    base_score = compute_base_score(src_tok, total_tok, saturation_scale)

    return {
        "problem_id": problem_id,
        "patch_applied": True,
        "tests_passed": True,
        "tests_skipped_locally": all_skipped,
        "source_token_score": round(src_tok, 2),
        "total_token_score": round(total_tok, 2),
        "scoring_method": scoring_method,
        "base_score": base_score,
        # Multipliers (time_decay, review_quality, label, issue) require GitHub
        # API data — local scoring sets them to 1.0 as a conservative estimate.
        "multipliers": {"time_decay": 1.0, "review_quality": 1.0, "label": 1.0, "issue": 1.0},
        "final_score": base_score,
        "scoring_note": scoring_note,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Score a patch against a benchmark problem")
    parser.add_argument("--problem", required=True, help="Path to problem directory")
    parser.add_argument("--patch", required=True, help="Path to unified diff file")
    args = parser.parse_args()

    result = score_patch(Path(args.problem), Path(args.patch))
    print(json.dumps(result, indent=2))

    if not result["tests_passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
