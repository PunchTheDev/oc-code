"""
Scores a candidate patch against a benchmark problem.

Mirrors Gittensor's native scoring formula:
  base_score = MERGED_PR_BASE_SCORE * (1 - exp(-src_tok / scale))
             + min(total_score / CONTRIBUTION_SCORE_FOR_FULL_BONUS, 1) * MAX_CONTRIBUTION_BONUS

  where:
    MERGED_PR_BASE_SCORE = 25  (cap on quality term)
    MAX_CONTRIBUTION_BONUS = 5  (cross-category bonus cap)
    SRC_TOK_SATURATION_SCALE = 58.0 (per-repo overridable; default)
    CONTRIBUTION_SCORE_FOR_FULL_BONUS = 1500

Correctness gates everything: tests must pass before quality is computed.
Final score is the base_score (0–30 scale, same as Gittensor native).

Full precision scoring uses Gittensor's tree-sitter pipeline in Docker CI.
This local implementation approximates src_tok via a token-counting heuristic
on the unified diff. The approximation is accurate enough for development
iteration; the authoritative score comes from CI.

Usage:
    python benchmark/harness/score.py --problem benchmark/problems/930/ --patch my.diff
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Gittensor native constants (gittensor/constants.py)
MERGED_PR_BASE_SCORE = 25
SRC_TOK_SATURATION_SCALE = 58.0
MAX_CONTRIBUTION_BONUS = 5
CONTRIBUTION_SCORE_FOR_FULL_BONUS = 1500


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


def run_tests(repo_dir: Path, test_cmd: list[str]) -> tuple[bool, str]:
    """Run the test suite. Returns (passed, output)."""
    result = subprocess.run(
        test_cmd,
        cwd=repo_dir,
        capture_output=True,
        text=True,
        timeout=300,
    )
    passed = result.returncode == 0
    output = result.stdout + result.stderr
    return passed, output


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

    Accuracy: within ~15% of native tree-sitter scoring on typical Python diffs.
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


def score_patch(problem_dir: Path, patch_path: Path) -> dict:
    meta = load_problem_meta(problem_dir)
    saturation_scale = float(meta.get("src_tok_saturation_scale", SRC_TOK_SATURATION_SCALE))

    with tempfile.TemporaryDirectory() as tmpdir:
        repo_dir = Path(tmpdir) / "repo"

        # Clone repo at base commit
        subprocess.run(
            ["git", "clone", meta["repo_url"], str(repo_dir)],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "checkout", meta["base_commit"]],
            cwd=repo_dir, check=True, capture_output=True,
        )

        # Apply patch
        patch_applied = apply_patch(repo_dir, patch_path)
        if not patch_applied:
            return {
                "problem_id": meta["id"],
                "patch_applied": False,
                "tests_passed": False,
                "source_token_score": 0.0,
                "base_score": 0.0,
                "final_score": 0.0,
            }

        # Run tests — correctness gates everything
        raw_cmd = meta.get("test_cmd", ["python3", "-m", "pytest", "--tb=short", "-q"])
        test_cmd = [
            ("python3" if c == "python" and not shutil.which("python") else c)
            for c in raw_cmd
        ]
        tests_passed, test_output = run_tests(repo_dir, test_cmd)

        if not tests_passed:
            return {
                "problem_id": meta["id"],
                "patch_applied": True,
                "tests_passed": False,
                "test_output": test_output[-2000:],
                "source_token_score": 0.0,
                "base_score": 0.0,
                "final_score": 0.0,
            }

        # Quality scoring (tests passed)
        diff_text = patch_path.read_text()
        src_tok, total_tok = approximate_src_token_score(diff_text, saturation_scale)
        base_score = compute_base_score(src_tok, total_tok, saturation_scale)

        return {
            "problem_id": meta["id"],
            "patch_applied": True,
            "tests_passed": True,
            "source_token_score": round(src_tok, 2),
            "total_token_score": round(total_tok, 2),
            "base_score": base_score,
            # final_score = base_score * (time_decay * review_quality * label * issue)
            # Multipliers require GitHub API data; local scoring sets them to 1.0
            "multipliers": {"time_decay": 1.0, "review_quality": 1.0, "label": 1.0, "issue": 1.0},
            "final_score": base_score,
            "scoring_note": "local approximation — CI uses Gittensor tree-sitter pipeline for authoritative score",
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
