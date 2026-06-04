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
import threading
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

# Efficiency scoring constants.
# Agents that use <= EFFICIENCY_THRESHOLD output tokens earn a 1.0 multiplier.
# Above that, the multiplier decays linearly to EFFICIENCY_FLOOR at the
# DEFAULT_TOKEN_BUDGET ceiling.  Agents that don't report tokens (tokens_used=0)
# receive 1.0 — no penalty for not tracking.
EFFICIENCY_THRESHOLD = 10_000   # output tokens below this → factor = 1.0
EFFICIENCY_FLOOR = 0.85         # minimum multiplier (15% penalty at budget cap)
DEFAULT_TOKEN_BUDGET = 50_000   # matches Problem.output_token_budget default


def repo_cache_dir() -> Path:
    """Return (and create) the gitminer repo cache directory."""
    cache = Path(os.environ.get("GITMINER_CACHE", Path.home() / ".cache" / "gitminer" / "repos"))
    cache.mkdir(parents=True, exist_ok=True)
    return cache


# Per-repo locks prevent concurrent threads from racing on the initial clone.
# The outer lock protects the lock-dictionary itself.
_clone_locks: dict[str, threading.Lock] = {}
_clone_locks_mutex = threading.Lock()


def cached_repo(repo_url: str) -> Path:
    """
    Return a path to a local clone of repo_url.

    On first call: git clone into ~/.cache/gitminer/repos/{owner}_{repo}.
    On subsequent calls: git fetch to pull in new commits (best-effort).
    Thread-safe: a per-repo lock prevents concurrent threads from racing
    on the initial clone when multiple workers evaluate problems from the
    same repository simultaneously.
    """
    parts = repo_url.rstrip("/").split("/")
    key = "_".join(parts[-2:])  # owner_repo
    cached = repo_cache_dir() / key

    if not cached.exists():
        with _clone_locks_mutex:
            if key not in _clone_locks:
                _clone_locks[key] = threading.Lock()
        with _clone_locks[key]:
            if not cached.exists():  # double-check after acquiring lock
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


# --- Test count parsers (per test runner) -----------------------------------

# pytest: "5 passed, 2 failed, 1 error in 3.4s"  or  "5 passed in 1.2s"
_PYTEST_SUMMARY_RE = re.compile(
    r"=+\s*(?:(\d+)\s+passed)?.*?(?:(\d+)\s+failed)?.*?(?:(\d+)\s+error(?:s)?)?\s*=+"
)
_PYTEST_PASSED_RE = re.compile(r"(\d+)\s+passed")
_PYTEST_FAILED_RE = re.compile(r"(\d+)\s+(?:failed|error)")

# cargo test: "test result: ok. 10 passed; 0 failed; 0 ignored"
_CARGO_RE = re.compile(r"test result:.*?(\d+)\s+passed;\s*(\d+)\s+failed")

# go test: count "--- PASS:" and "--- FAIL:" lines
_GO_PASS_RE = re.compile(r"^--- PASS:", re.MULTILINE)
_GO_FAIL_RE = re.compile(r"^--- FAIL:", re.MULTILINE)

# jest/vitest: "Tests: 2 failed, 8 passed, 10 total"
_JEST_RE = re.compile(r"Tests?:.*?(\d+)\s+passed.*?(\d+)\s+total", re.DOTALL)
_JEST_TOTAL_RE = re.compile(r"(\d+)\s+total")
_JEST_PASSED_RE = re.compile(r"(\d+)\s+passed")
_JEST_FAILED_RE = re.compile(r"(\d+)\s+failed")

# rspec: "10 examples, 2 failures"
_RSPEC_RE = re.compile(r"(\d+)\s+examples?,\s*(\d+)\s+failures?")

# gradle: "10 tests completed, 2 failed"
_GRADLE_RE = re.compile(r"(\d+)\s+tests?\s+completed,\s*(\d+)\s+failed")


def parse_test_count(output: str, test_cmd: list[str]) -> tuple[int, int]:
    """Parse test runner output to extract (tests_passed, tests_total).

    Returns (0, 0) when parsing fails — callers should treat this as unknown,
    not as 'zero tests passed'. The caller uses the subprocess return code to
    determine pass/fail when count is unavailable.

    Supports: pytest, cargo test, go test, jest/vitest, rspec, gradle.
    """
    runner = test_cmd[0] if test_cmd else ""

    # cargo test
    if runner == "cargo" or "cargo" in runner:
        for m in _CARGO_RE.finditer(output):
            p, f = int(m.group(1)), int(m.group(2))
            return p, p + f

    # go test
    if runner == "go" or runner.endswith("/go"):
        n_pass = len(_GO_PASS_RE.findall(output))
        n_fail = len(_GO_FAIL_RE.findall(output))
        if n_pass + n_fail > 0:
            return n_pass, n_pass + n_fail

    # gradle
    if "./gradlew" in runner or "gradlew" in runner:
        m = _GRADLE_RE.search(output)
        if m:
            total, failed = int(m.group(1)), int(m.group(2))
            return total - failed, total

    # rspec
    if runner in ("rspec", "bundle") or "rspec" in output:
        m = _RSPEC_RE.search(output)
        if m:
            total, failures = int(m.group(1)), int(m.group(2))
            return total - failures, total

    # jest / vitest (npm test)
    if runner in ("npm", "npx", "yarn", "bun") or "jest" in output or "vitest" in output:
        total_m = _JEST_TOTAL_RE.search(output)
        passed_m = _JEST_PASSED_RE.search(output)
        if total_m and passed_m:
            return int(passed_m.group(1)), int(total_m.group(1))

    # pytest (default for python repos and many others)
    passed_m = _PYTEST_PASSED_RE.search(output)
    passed = int(passed_m.group(1)) if passed_m else 0
    failed_ms = _PYTEST_FAILED_RE.findall(output)
    failed = sum(int(x) for x in failed_ms)
    if passed + failed > 0:
        return passed, passed + failed

    return 0, 0


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

    cached = cached_repo(meta["repo_url"])
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


def score_patch(problem_dir: Path, patch_path: Path, tokens_used: int = 0) -> dict:
    meta = load_problem_meta(problem_dir)
    saturation_scale = float(meta.get("src_tok_saturation_scale", SRC_TOK_SATURATION_SCALE))

    # Use a cached clone so repeated evals on the same repo skip the network round-trip.
    # Each problem gets an isolated git worktree checked out at the exact base commit.
    cached = cached_repo(meta["repo_url"])

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
            return _score_in_worktree(problem_dir, worktree, meta, patch_path, saturation_scale, tokens_used)
        finally:
            subprocess.run(
                ["git", "-C", str(cached), "worktree", "remove", "--force", str(worktree)],
                capture_output=True,
            )


def parse_diff_paths(diff_text: str) -> list[tuple[str, str]]:
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

    paths = parse_diff_paths(diff_text)
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


_TEST_PATH_RE = re.compile(
    r"(/test|^test|_test\.|test_[^/]*\.[a-z]+$|spec\.|\.spec\.|\.test\.)",
    re.IGNORECASE,
)


def is_test_file(path: str) -> bool:
    return bool(_TEST_PATH_RE.search(path))


def file_coverage_stats(problem_dir: Path, agent_diff_text: str) -> dict:
    """
    Measure what fraction of the reference diff's source files the agent also touches.

    Scores 0.0–1.0 where 1.0 = agent changed every non-test file the reference changed.
    Test files are excluded (they vary legitimately). Returns None when coverage cannot
    be computed (reference.diff missing or touches only test files).

    This is an observational signal, not part of final_score. An agent that identifies
    a different but correct fix touching different files is not penalized.
    """
    ref_diff_path = problem_dir / "reference.diff"
    if not ref_diff_path.exists():
        return {"file_coverage": None, "reference_source_files": 0, "agent_files_matched": 0}

    ref_diff_text = ref_diff_path.read_text(errors="replace")
    ref_src_paths = {p for p, _ in parse_diff_paths(ref_diff_text) if not is_test_file(p)}
    agent_src_paths = {p for p, _ in parse_diff_paths(agent_diff_text) if not is_test_file(p)}

    if not ref_src_paths:
        return {"file_coverage": None, "reference_source_files": 0, "agent_files_matched": 0}

    matched = len(ref_src_paths & agent_src_paths)
    return {
        "file_coverage": round(matched / len(ref_src_paths), 3),
        "reference_source_files": len(ref_src_paths),
        "agent_files_matched": matched,
    }


_BASELINES_CACHE: "dict[str, float] | None" = None


def load_baselines() -> "dict[str, float]":
    """Return {problem_id: base_score} from results/baselines.json (loaded once)."""
    global _BASELINES_CACHE
    if _BASELINES_CACHE is not None:
        return _BASELINES_CACHE

    baselines_path = _REPO_ROOT / "results" / "baselines.json"
    mapping: dict[str, float] = {}
    if baselines_path.exists():
        try:
            data = json.loads(baselines_path.read_text())
            for entry in data.get("problems", []):
                pid = entry.get("id")
                score = entry.get("base_score")
                if pid and score is not None:
                    mapping[pid] = float(score)
        except Exception:
            pass

    _BASELINES_CACHE = mapping
    return mapping


def relative_score_for(base_score: float, meta: dict) -> float | None:
    """
    Compute relative benchmark score: agent_score / oracle_score.

    Oracle is our own tree-sitter scorer's output on the reference diff for this
    problem (from results/baselines.json). This ensures the oracle scores 1.0 by
    definition and all agents are measured on the same scale.

    Returns None when the oracle baseline is unavailable or zero.

    Interpretation:
      1.0  = exactly matches oracle quality
      >1.0 = agent produced a higher-quality fix than the accepted solution
      <1.0 = agent's fix has lower quality signal than the accepted solution
    Capped at 2.0 so verbose diffs can't inflate scores unboundedly.
    """
    pid = meta.get("id", "")
    baselines = load_baselines()
    oracle = baselines.get(pid, 0.0)
    if oracle <= 0.0:
        return None
    return round(min(base_score / oracle, 2.0), 4)


_TEST_ASSERTION_RE = re.compile(
    r"\b(assert|assertEqual|assertRaises|assertTrue|assertFalse|assertIn|assertIs"
    r"|expect\(|it\(|test\(|describe\(|@Test|func Test|#\[test\]"
    r"|should\.|must\.|spec\.)\b"
)


def detect_test_deletion(diff_text: str) -> dict:
    """
    Detect if a diff suspiciously removes test assertions or test functions.

    Scans removed lines (-) in test files for assertion patterns. A high count
    of removed assertions is a red flag that the agent gamed the test suite
    (deleted or commented out failing assertions to force a pass).

    Returns a dict with:
      - test_assertions_removed (int): removed assertion lines in test files
      - test_deletion_warning (bool): True if removal count exceeds threshold
    """
    in_test = False
    removed_assertions = 0

    for line in diff_text.splitlines():
        if line.startswith("diff --git"):
            path_match = re.search(r"b/(.+)$", line)
            in_test = bool(path_match and is_test_file(path_match.group(1)))
            continue

        if not in_test:
            continue
        if line.startswith("-") and not line.startswith("---"):
            content = line[1:].strip()
            if content and _TEST_ASSERTION_RE.search(content):
                removed_assertions += 1

    # Flag when more than 3 test assertions removed — triggers graduated penalty.
    return {
        "test_assertions_removed": removed_assertions,
        "test_deletion_warning": removed_assertions > 3,
    }


def test_assertion_delta(problem_dir: Path, agent_diff_text: str) -> dict:
    """
    Measure how many test assertions the agent added vs. the reference.

    When a reference PR adds assertions that verify the fix, a good agent should
    add similar tests. An agent that fixes code without adding any tests is more
    likely to be fragile or incomplete.

    Returns a dict with:
      - ref_assertions_added (int): assertions added in reference diff
      - agent_assertions_added (int): assertions added in agent diff
      - test_coverage_ratio (float|None): agent/reference ratio (None when ref added 0)
        1.0 = agent added as many test assertions as the reference
        0.0 = agent added none (when reference added >0)
        None = reference added no assertions (no test expectation signal)

    Observational only — does not affect benchmark_score. Informational signal
    to identify agents that never write tests.
    """
    def count_added_assertions(diff_text: str) -> int:
        in_test = False
        count = 0
        for line in diff_text.splitlines():
            if line.startswith("diff --git"):
                path_match = re.search(r"b/(.+)$", line)
                in_test = bool(path_match and is_test_file(path_match.group(1)))
                continue
            if not in_test:
                continue
            if line.startswith("+") and not line.startswith("+++"):
                content = line[1:].strip()
                if content and _TEST_ASSERTION_RE.search(content):
                    count += 1
        return count

    ref_diff_path = problem_dir / "reference.diff"
    if not ref_diff_path.exists():
        return {"ref_assertions_added": 0, "agent_assertions_added": 0, "test_coverage_ratio": None}

    ref_count = count_added_assertions(ref_diff_path.read_text(errors="replace"))
    agent_count = count_added_assertions(agent_diff_text)

    ratio = round(min(1.0, agent_count / ref_count), 3) if ref_count > 0 else None

    return {
        "ref_assertions_added": ref_count,
        "agent_assertions_added": agent_count,
        "test_coverage_ratio": ratio,
    }


def compute_test_quality_factor(test_coverage_ratio: "float | None") -> float:
    """
    Convert test_coverage_ratio to a score multiplier (0.85–1.0).

    When the reference diff added assertions, an agent that matches earns 1.0;
    one that adds none earns 0.85 (15% penalty for not testing the fix).
    When the reference added no assertions (ratio=None), factor is 1.0 — no signal.

    Design: smooth linear floor so partial test coverage earns partial credit.
      ratio=1.0 → 1.0  (agent matches reference test coverage)
      ratio=0.5 → 0.925
      ratio=0.0 → 0.85 (min penalty; does not zero-out benchmark_score)
      ratio=None → 1.0 (no expectation set by reference)
    """
    if test_coverage_ratio is None:
        return 1.0
    return round(0.85 + 0.15 * min(test_coverage_ratio, 1.0), 4)


def compute_efficiency_factor(
    tokens_used: int,
    budget: int = DEFAULT_TOKEN_BUDGET,
) -> float:
    """
    Convert raw LLM output token count to a score multiplier (0.85–1.0).

    Rationale: an agent that achieves the same quality with fewer tokens is a
    better agent — it costs less to run and scales to more problems in parallel.
    Efficiency measures scaffolding quality, not model size.

    Design: linear decay from 1.0 at or below EFFICIENCY_THRESHOLD to
    EFFICIENCY_FLOOR at the budget ceiling.

      tokens ≤ 10 000  → 1.0   (efficient)
      tokens = 30 000  → 0.925
      tokens = 50 000  → 0.85  (budget-exhausted)
      tokens = 0       → 1.0   (not tracked — no penalty)

    Does not zero-out benchmark_score; agents have a floor even when wasteful.
    """
    if tokens_used <= 0 or tokens_used <= EFFICIENCY_THRESHOLD:
        return 1.0
    max_excess = max(budget - EFFICIENCY_THRESHOLD, 1)
    excess = min(tokens_used - EFFICIENCY_THRESHOLD, max_excess)
    factor = 1.0 - (1.0 - EFFICIENCY_FLOOR) * (excess / max_excess)
    return round(max(factor, EFFICIENCY_FLOOR), 4)


def _score_in_worktree(
    problem_dir: Path, repo_dir: Path, meta: dict, patch_path: Path, saturation_scale: float,
    tokens_used: int = 0,
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
            "tests_passed_count": 0,
            "tests_total_count": 0,
            "test_pass_rate": 0.0,
            "source_token_score": 0.0,
            "base_score": 0.0,
            "relative_score": 0.0,
            "benchmark_score": 0.0,
            "tokens_used": tokens_used,
            "efficiency_factor": compute_efficiency_factor(tokens_used),
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
    n_passed, n_total = parse_test_count(test_output, test_cmd)

    # test_pass_rate: fraction of tests that pass.
    # When parsing fails (n_total=0), fall back to binary: 1.0 if all tests
    # pass (by return code), 0.0 otherwise. This is a conservative fallback.
    if n_total > 0:
        test_pass_rate = round(n_passed / n_total, 4)
    else:
        test_pass_rate = 1.0 if tests_passed else 0.0
        n_passed = n_total = 0  # unknown, leave as 0

    # Primary: tree-sitter AST scorer (matches DAS scoring engine).
    # Computed even on partial test pass so quality can be combined with
    # test_pass_rate in benchmark_score.
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
    rel_score = relative_score_for(base_score, meta)
    coverage = file_coverage_stats(problem_dir, diff_text)
    deletion_info = detect_test_deletion(diff_text)

    # Anti-gaming multiplier: graduated penalty for test assertion deletion.
    # ≤3 removed → 1.0 (noise tolerance). 4–8 → linear decay from 1.0 → 0.5.
    # >8 removed → floor 0.5. Graduated to avoid the binary cliff where removing
    # 4 assertions is penalised identically to removing 40.
    removed = deletion_info["test_assertions_removed"]
    if removed <= 3:
        anti_gaming_multiplier = 1.0
    elif removed <= 8:
        anti_gaming_multiplier = round(1.0 - 0.1 * (removed - 3), 4)  # 0.9 → 0.5
    else:
        anti_gaming_multiplier = 0.5

    # test_quality_factor: 0.85–1.0 multiplier based on test assertion coverage.
    # Agents that add test assertions proportional to the reference earn 1.0;
    # agents that add none (when the reference did) earn 0.85.
    assertion_info = test_assertion_delta(problem_dir, diff_text)
    tqf = compute_test_quality_factor(assertion_info["test_coverage_ratio"])

    # efficiency_factor: 0.85–1.0 multiplier based on output token usage.
    # Agents using ≤10 000 tokens earn 1.0; budget-exhausted agents earn 0.85.
    # When tokens_used=0 (not tracked), factor is 1.0 — no penalty.
    token_budget = int(meta.get("output_token_budget", DEFAULT_TOKEN_BUDGET))
    eff = compute_efficiency_factor(tokens_used, token_budget)

    # benchmark_score: composite primary leaderboard metric.
    #   = test_pass_rate × relative_score × anti_gaming_multiplier
    #     × test_quality_factor × efficiency_factor
    # Correctness depth × quality alignment × integrity × test coverage × token efficiency.
    # Oracle earns 1.0 by definition (oracle does not report tokens → eff=1.0).
    benchmark_score = round(
        test_pass_rate * (rel_score or 0.0) * anti_gaming_multiplier * tqf * eff, 4
    )

    return {
        "problem_id": problem_id,
        "patch_applied": True,
        "tests_passed": tests_passed,
        # Granular test counts (0 = parse failed / unknown, not "zero tests")
        "tests_passed_count": n_passed,
        "tests_total_count": n_total,
        "test_pass_rate": test_pass_rate,
        "tests_skipped_locally": all_skipped,
        "test_output": test_output[-2000:] if not tests_passed else None,
        "source_token_score": round(src_tok, 2),
        "total_token_score": round(total_tok, 2),
        "scoring_method": scoring_method,
        "base_score": base_score,
        # relative_score: agent quality / oracle quality for this problem.
        # 1.0 = matches accepted solution quality, >1.0 = better, <1.0 = lower quality.
        "relative_score": rel_score,
        "oracle_base_score": load_baselines().get(meta.get("id", ""), 0.0),
        # benchmark_score: PRIMARY per-problem metric.
        #   = test_pass_rate × relative_score × anti_gaming_multiplier × test_quality_factor
        # Combined into weighted_benchmark_score at the shard level (hard×2 / medium×1.5 / easy×1).
        "benchmark_score": benchmark_score,
        "anti_gaming_multiplier": anti_gaming_multiplier,
        # test_quality_factor: 0.85–1.0 multiplier — rewards agents that add test assertions
        # proportional to the reference. 1.0 when reference added no assertions (no expectation).
        "test_quality_factor": tqf,
        # efficiency_factor: 0.85–1.0 multiplier — rewards token-efficient agents.
        # 1.0 when tokens_used=0 (not tracked). Decays linearly above 10k tokens.
        "tokens_used": tokens_used,
        "efficiency_factor": eff,
        # file_coverage: fraction of reference-diff source files the agent also touches.
        # Observational only — a different-but-correct fix needn't touch the same files.
        **coverage,
        # Anti-gaming: flag suspicious test assertion removals (reflected in anti_gaming_multiplier).
        **deletion_info,
        # test_coverage_ratio: agent/reference assertion ratio (None when reference added 0).
        **assertion_info,
        # Multipliers (time_decay, review_quality, label, issue) require GitHub
        # API data — local scoring sets them to 1.0 as a conservative estimate.
        "multipliers": {"time_decay": 1.0, "review_quality": 1.0, "label": 1.0, "issue": 1.0},
        # final_score: Gittensor native score (0–30). Retained for backward compat
        # and direct comparison to on-chain emissions scoring.
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
