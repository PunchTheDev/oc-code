"""
Docker-sandboxed problem runner.

Executes scoring for a single benchmark problem inside an isolated container:
  - Hard time limit enforced via subprocess timeout + docker kill
  - Memory cap via --memory
  - Phase 1 (setup + test): language-specific image — Python/Node/Rust/JDK;
    network allowed for git clone, package manager fetches, dep installs.
    Also captures old/new file contents for tree-sitter scoring.
  - Phase 2 (score): ghcr.io/punchthedev/gitminer-scorer:latest (tree-sitter
    pre-installed), network blocked (--network none). Reads staging files from
    Phase 1 and emits a JSON score.
  - Secrets (OPENROUTER_KEY etc.) never passed to containers — no model cheating
  - Ephemeral: container is removed after each run (--rm)

Repo cache mount (Phase 1 speedup):
  Before launching the Phase 1 container, run_in_sandbox() calls cached_repo()
  to ensure a local clone exists in ~/.cache/gitminer/repos/{owner_repo}. When
  it does, the clone is bind-mounted read-only at /gitminer_cache inside the
  container. setup_and_test.sh then does a fast local clone from /gitminer_cache
  instead of a network clone, eliminating a 10–90s round-trip per problem.
  If the commit isn't in the local cache (stale clone), the script falls back to
  fetching the exact commit from origin before checking out. Network-free fallback
  if Docker is unavailable: score.score_patch() is called directly.

Fallback chain:
  - If SCORE_IMAGE is unavailable, falls back to python:3.12-slim with heuristic
    token scoring (same as pre-tree-sitter behaviour).

Usage:
    from benchmark.harness.runner import run_in_sandbox
    result = run_in_sandbox(problem_dir, patch_path)

For local development without Docker, score.score_patch() is called directly.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path


MEMORY_LIMIT = "2g"
CPU_LIMIT = "2.0"

# Custom scorer image — python:3.12-slim + tree-sitter pre-installed.
# Built by .github/workflows/build-scorer.yml and pushed to GHCR.
# The fallback image uses the heuristic scorer when tree-sitter is absent.
SCORE_IMAGE = "ghcr.io/punchthedev/gitminer-scorer:latest"
SCORE_IMAGE_FALLBACK = "python:3.12-slim"

KILL_GRACE = 15  # seconds docker waits after stop signal before SIGKILL

# Language-specific Docker images for Phase 1 (clone → install deps → run tests).
_LANG_IMAGES: dict[str, str] = {
    "python": "python:3.12-slim",
    "npm":    "node:20-slim",
    "cargo":  "rust:1.82-slim",
    "./gradlew": "eclipse-temurin:21-jdk-jammy",
    "bundle": "ruby:3.3-slim",
    "go":     "golang:1.23-bookworm",
}

# Scorer assets bundled with the harness — copied to staging for Phase 2.
_HARNESS_DIR = Path(__file__).parent
_TS_SCORER_SRC = _HARNESS_DIR / "tree_sitter_scorer.py"
_WEIGHTS_DIR = _HARNESS_DIR / "weights"

# ---------------------------------------------------------------------------
# File-content capture script (runs in Phase 1, writes staging/file_pairs.json)
# ---------------------------------------------------------------------------
_CAPTURE_SCRIPT = '''\
#!/usr/bin/env python3
"""
Capture old/new file contents for tree-sitter scoring.

Called twice from setup_and_test.sh:
  python3 /staging/capture_files.py old /staging/candidate.diff
  python3 /staging/capture_files.py new /staging/candidate.diff

Writes /staging/file_pairs.json:
  {"old": {"path": "content"|null, ...}, "new": {"path": "content"|null, ...}}

File content is capped at 1 MB per file (same limit as the DAS scorer).
"""
import json, re, sys
from pathlib import Path

MAX_BYTES = 1_000_000
PHASE = sys.argv[1]          # "old" or "new"
DIFF_PATH = sys.argv[2]
REPO = Path("/repo")
STAGING = Path("/staging")
FP_PATH = STAGING / "file_pairs.json"


def _read(p: Path) -> "str | None":
    if not p.exists():
        return None
    try:
        raw = p.read_bytes()
        if len(raw) > MAX_BYTES:
            return None  # skip oversized files (matches DAS 1 MB limit)
        return raw.decode("utf-8", errors="replace")
    except Exception:
        return None


diff_text = Path(DIFF_PATH).read_text(errors="replace")
paths = []
for line in diff_text.splitlines():
    if line.startswith("diff --git "):
        m = re.search(r" b/(.+)$", line)
        if m:
            paths.append(m.group(1))

if PHASE == "old":
    data = {p: _read(REPO / p) for p in paths}
    FP_PATH.write_text(json.dumps({"old": data, "new": {}}))
elif PHASE == "new":
    try:
        existing = json.loads(FP_PATH.read_text())
    except Exception:
        existing = {"old": {}, "new": {}}
    existing["new"] = {p: _read(REPO / p) for p in paths}
    FP_PATH.write_text(json.dumps(existing))
'''

# ---------------------------------------------------------------------------
# Phase 2 scorer script (runs inside SCORE_IMAGE, network-isolated)
# ---------------------------------------------------------------------------
_SCORE_RESULT_SCRIPT = '''\
"""
Phase 2 scorer — reads staging artifacts from Phase 1, emits JSON score.

Primary: tree-sitter AST scorer (when ts_scorer.py + weights present in staging).
Fallback: heuristic diff-token count (always available, ~2x above DAS).

Always computes base_score from diff quality regardless of test result.
Partial test passes earn partial credit via test_pass_rate × relative_score
in the enrichment step — so quality must be scored even when tests fail.
"""
import json, math, pathlib, re, sys

MERGED_PR_BASE_SCORE = 25
SRC_TOK_SATURATION_SCALE = 58.0
MAX_CONTRIBUTION_BONUS = 5
CONTRIBUTION_SCORE_FOR_FULL_BONUS = 1500

staging = pathlib.Path("/staging")
patch_status = (staging / "patch_status").read_text().strip() if (staging / "patch_status").exists() else "failed"
meta = json.loads((staging / "meta.json").read_text()) if (staging / "meta.json").exists() else {}
problem_id = meta.get("id", "unknown")
saturation_scale = float(meta.get("src_tok_saturation_scale", SRC_TOK_SATURATION_SCALE))

if patch_status != "applied":
    print(json.dumps({"problem_id": problem_id, "patch_applied": False,
                       "tests_passed": False, "base_score": 0.0, "final_score": 0.0}))
    sys.exit(0)

test_rc = int((staging / "test_rc").read_text().strip()) if (staging / "test_rc").exists() else 1
tests_passed = test_rc == 0
test_out = (staging / "test_out.txt").read_text(errors="replace") if (staging / "test_out.txt").exists() else ""


def compute_base(src_tok: float, total_tok: float) -> float:
    initial = MERGED_PR_BASE_SCORE * (1.0 - math.exp(-src_tok / saturation_scale))
    bonus = round(min(1.0, total_tok / CONTRIBUTION_SCORE_FOR_FULL_BONUS) * MAX_CONTRIBUTION_BONUS, 2)
    return round(initial + bonus, 2)


# ---------------------------------------------------------------------------
# Primary: tree-sitter scorer
# ---------------------------------------------------------------------------
def try_tree_sitter() -> "tuple[float, float] | None":
    fp_path = staging / "file_pairs.json"
    ts_path = staging / "ts_scorer.py"
    if not fp_path.exists() or not ts_path.exists():
        return None

    try:
        import importlib.util, sys as _sys
        spec = importlib.util.spec_from_file_location("ts_scorer", str(ts_path))
        ts = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ts)
        # ts_scorer resolves _WEIGHTS_DIR as Path(__file__).parent / "weights",
        # which becomes /staging/weights/ — the weights we copied in _prepare_staging.

        if not ts.available():
            return None

        fp_data = json.loads(fp_path.read_text())
        old_map = fp_data.get("old", {})
        new_map = fp_data.get("new", {})

        pairs = [
            ts.FilePair(p, old_map.get(p), new_map.get(p))
            for p in set(old_map) | set(new_map)
        ]
        return ts.score_file_pairs(pairs)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Compute diff quality regardless of test result.
# benchmark_score = test_pass_rate × relative_score — so partial passes earn
# proportional credit when tests_passed is False but test_pass_rate > 0.
# ---------------------------------------------------------------------------
ts_result = try_tree_sitter()
if ts_result is not None:
    src_tok, total_tok = ts_result
    scoring_method = "tree-sitter"
else:
    # Fallback heuristic
    STRUCT_WORDS = ("def ", "class ", "async def ", "fn ", "impl ", "struct ",
                    "func ", "interface ", "enum ", "trait ", "type ")
    SKIP_STARTS = ("#", "//", "/*", "*", "<!--", "pass", "...")
    DELIM = re.compile(r"[\\s()\\[\\]{},;:=<>!&|.@#$%^~]+")

    patch_text = (staging / "candidate.diff").read_text(errors="replace")
    src_tok = 0.0
    total_tok = 0.0
    in_test = False

    for line in patch_text.splitlines():
        if line.startswith("diff --git"):
            m = re.search("b/(.+)$", line)
            if m:
                p = m.group(1)
                in_test = ("/test" in p or p.startswith("test") or
                           "_test." in p or p.split("/")[-1].startswith("test_") or "spec." in p)
            continue
        if not line.startswith("+") or line.startswith("+++"):
            continue
        content = line[1:].strip()
        if not content or any(content.startswith(s) for s in SKIP_STARTS):
            continue
        tokens = [t for t in DELIM.split(content) if len(t) > 1 and not t.isdigit()]
        if not tokens:
            continue
        is_structural = any(kw in content for kw in STRUCT_WORDS)
        line_score = len(tokens) * (2.5 if is_structural else 1.0)
        total_tok += line_score
        if not in_test:
            src_tok += line_score

    scoring_method = "heuristic"

base_score = compute_base(src_tok, total_tok)
print(json.dumps({
    "problem_id": problem_id,
    "patch_applied": True,
    "tests_passed": tests_passed,
    "test_output": test_out[-2000:] if not tests_passed else None,
    "source_token_score": round(src_tok, 2),
    "total_token_score": round(total_tok, 2),
    "scoring_method": scoring_method,
    "base_score": base_score,
    "final_score": base_score,
}))
'''


def _docker_available() -> bool:
    return shutil.which("docker") is not None


def run_in_sandbox(problem_dir: Path, patch_path: Path) -> dict:
    """
    Score a patch in an isolated Docker container.

    Falls back to in-process scoring when Docker is unavailable (local dev mode).
    Return dict matches score.score_patch() exactly — including all benchmark
    metrics (test_pass_rate, relative_score, benchmark_score, file_coverage,
    test_deletion_warning) that the Phase 2 script cannot compute internally.

    Metric enrichment reads test_out.txt from the staging dir before cleanup,
    then computes the full metric set using the same functions as score.score_patch().
    This ensures sandbox and local scoring paths return identical result shapes.

    Repo cache: before launching the container, warms the host repo cache so
    the Phase 1 container can clone locally (10–90× faster than a network clone).
    The cache path is bind-mounted read-only at /gitminer_cache inside the container.
    """
    if not _docker_available():
        from benchmark.harness.score import score_patch
        return score_patch(problem_dir, patch_path)

    meta = json.loads((problem_dir / "meta.json").read_text())
    time_limit: int = meta.get("time_limit_seconds", 120)

    # Warm the host repo cache so Phase 1 can do a fast local clone.
    # Best-effort: if the cache warm fails (no network, permission issue) we
    # fall back to the normal in-container network clone.
    cache_path: Path | None = None
    repo_url = meta.get("repo_url", "")
    if repo_url:
        try:
            from benchmark.harness.score import cached_repo
            cache_path = cached_repo(repo_url)
        except Exception:
            pass  # network unavailable — container will clone directly

    with tempfile.TemporaryDirectory(prefix="bminer_") as staging:
        staging_path = Path(staging)
        _prepare_staging(staging_path, meta, patch_path, cache_path=cache_path)
        result = _run_container(staging_path, meta, time_limit, cache_path=cache_path)
        # Enrich with full metrics before staging dir is cleaned up.
        result = _enrich_result(result, staging_path, problem_dir, patch_path, meta)

    return result


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _lang_image(test_cmd: list[str]) -> str:
    runner = test_cmd[0] if test_cmd else "python"
    return _LANG_IMAGES.get(runner, "python:3.12-slim")


def _install_block(test_cmd: list[str]) -> str:
    runner = test_cmd[0] if test_cmd else "python"

    if runner == "python":
        return textwrap.dedent("""\
            pip install pytest --quiet >/dev/null 2>&1 || true
            if [ -f pyproject.toml ]; then
                pip install -e ".[dev]" --quiet >/dev/null 2>&1 || \\
                pip install -e . --quiet >/dev/null 2>&1 || true
            elif [ -f requirements.txt ]; then
                pip install -r requirements.txt --quiet >/dev/null 2>&1 || true
            elif [ -f setup.py ]; then
                pip install -e . --quiet >/dev/null 2>&1 || true
            fi
        """)

    if runner == "npm":
        return textwrap.dedent("""\
            if [ -f package-lock.json ]; then
                npm ci --silent 2>/dev/null || npm install --silent 2>/dev/null || true
            else
                npm install --silent 2>/dev/null || true
            fi
        """)

    if runner == "cargo":
        return textwrap.dedent("""\
            cargo fetch --quiet 2>/dev/null || true
        """)

    if runner == "./gradlew":
        return textwrap.dedent("""\
            chmod +x gradlew
            ./gradlew dependencies --quiet 2>/dev/null || true
        """)

    if runner == "bundle":
        return textwrap.dedent("""\
            bundle install --quiet 2>/dev/null || true
        """)

    if runner == "go":
        return textwrap.dedent("""\
            if [ -f go.mod ]; then
                go mod download 2>/dev/null || true
            fi
        """)

    return ""


def _git_apt_block(runner: str) -> str:
    """Packages needed beyond git for the given runner's base image.

    python3-minimal is added for npm/cargo images so capture_files.py can run
    in Phase 1 to serialize file contents for the Phase 2 tree-sitter scorer.
    """
    if runner in ("npm", "cargo"):
        return (
            "apt-get update -qq >/dev/null && "
            "apt-get install -y -qq git python3-minimal >/dev/null"
        )
    if runner == "./gradlew":
        return (
            "git --version >/dev/null 2>&1 || "
            "(apt-get update -qq >/dev/null && apt-get install -y -qq git >/dev/null)"
        )
    if runner == "bundle":
        # ruby:3.3-slim — has ruby+bundler, needs git + python3 for capture_files.py
        return (
            "apt-get update -qq >/dev/null && "
            "apt-get install -y -qq git python3-minimal >/dev/null"
        )
    if runner == "go":
        # golang:1.23-bookworm — has go + git; needs python3-minimal for capture_files.py
        return (
            "apt-get update -qq >/dev/null && "
            "apt-get install -y -qq python3-minimal >/dev/null"
        )
    # python:3.12-slim — has python3, needs git
    return "apt-get update -qq >/dev/null && apt-get install -y -qq git >/dev/null"


def _prepare_staging(
    staging: Path,
    meta: dict,
    patch_path: Path,
    cache_path: "Path | None" = None,
) -> None:
    """Write all files the container needs into the staging directory.

    When cache_path is provided, setup_and_test.sh will clone from the
    bind-mounted /gitminer_cache (fast local copy) instead of the network.
    Falls back to a network clone if the required commit isn't in the cache.
    """
    shutil.copy(patch_path, staging / "candidate.diff")
    (staging / "meta.json").write_text(json.dumps(meta))

    # Copy tree-sitter scorer + weights so Phase 2 can use them without network.
    if _TS_SCORER_SRC.exists():
        shutil.copy(_TS_SCORER_SRC, staging / "ts_scorer.py")
    if _WEIGHTS_DIR.is_dir():
        staging_weights = staging / "weights"
        staging_weights.mkdir(exist_ok=True)
        for w in _WEIGHTS_DIR.iterdir():
            shutil.copy(w, staging_weights / w.name)

    # File-content capture script — runs in Phase 1 before/after git apply.
    (staging / "capture_files.py").write_text(_CAPTURE_SCRIPT)

    test_cmd: list[str] = meta.get("test_cmd", ["python", "-m", "pytest", "--tb=short", "-q"])
    test_cmd_str = " ".join(test_cmd)
    runner = test_cmd[0] if test_cmd else "python"

    git_block = _git_apt_block(runner)
    install_block = _install_block(test_cmd)

    repo_url = meta["repo_url"]
    base_commit = meta["base_commit"]

    # Clone block: use local cache mount when available (much faster), with
    # automatic fallback for stale caches that don't have the target commit.
    if cache_path is not None:
        clone_block = textwrap.dedent(f"""\
            if [ -d /gitminer_cache ]; then
                git clone --quiet /gitminer_cache /repo
                cd /repo
                if ! git checkout --quiet {base_commit} 2>/dev/null; then
                    # Commit not in local cache — fetch it from origin.
                    git remote set-url origin {repo_url}
                    git fetch --quiet --depth=1 origin {base_commit} || git fetch --quiet origin
                    git checkout --quiet {base_commit}
                fi
            else
                git clone --quiet {repo_url} /repo
                cd /repo
                git checkout --quiet {base_commit}
            fi""")
    else:
        clone_block = textwrap.dedent(f"""\
            git clone --quiet {repo_url} /repo
            cd /repo
            git checkout --quiet {base_commit}""")

    (staging / "setup_and_test.sh").write_text(textwrap.dedent(f"""\
        #!/usr/bin/env bash
        set -euo pipefail
        export DEBIAN_FRONTEND=noninteractive

        {git_block}

        {clone_block}

        # Install dependencies (best-effort)
        {install_block.rstrip()}

        # Capture old file contents BEFORE applying the patch.
        python3 /staging/capture_files.py old /staging/candidate.diff || true

        # Apply patch — write outcome so Phase 2 can read it.
        if git apply /staging/candidate.diff; then
            echo "applied" > /staging/patch_status
        else
            echo "failed" > /staging/patch_status
            exit 0
        fi

        # Capture new file contents AFTER applying the patch.
        python3 /staging/capture_files.py new /staging/candidate.diff || true

        # Run tests — capture output + exit code.
        {test_cmd_str} > /staging/test_out.txt 2>&1
        echo $? > /staging/test_rc
    """))
    (staging / "setup_and_test.sh").chmod(0o755)

    (staging / "score_result.py").write_text(_SCORE_RESULT_SCRIPT)


def _run_container(
    staging: Path,
    meta: dict,
    time_limit: int,
    cache_path: "Path | None" = None,
) -> dict:
    problem_id = meta["id"]
    container_name = f"bminer_{problem_id}_{os.getpid()}"
    host_timeout = time_limit + KILL_GRACE + 60

    test_cmd: list[str] = meta.get("test_cmd", ["python", "-m", "pytest", "--tb=short", "-q"])
    setup_image = _lang_image(test_cmd)

    # Phase 1: setup + test + file content capture.
    # Mount the host repo cache read-only when available so setup_and_test.sh
    # can clone locally instead of over the network (10–90× faster).
    setup_cmd = [
        "docker", "run", "--rm",
        "--name", container_name,
        "--memory", MEMORY_LIMIT,
        "--cpus", CPU_LIMIT,
        "--stop-timeout", str(KILL_GRACE),
        "-v", f"{staging}:/staging",
    ]
    if cache_path is not None and cache_path.exists():
        setup_cmd += ["-v", f"{cache_path}:/gitminer_cache:ro"]
    setup_cmd += [
        setup_image,
        "/bin/bash", "/staging/setup_and_test.sh",
    ]

    try:
        subprocess.run(
            setup_cmd,
            capture_output=True,
            text=True,
            timeout=host_timeout,
        )
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "kill", container_name], capture_output=True)
        return _timeout_result(problem_id)

    # Phase 2: score from staging artifacts.
    # Uses SCORE_IMAGE (tree-sitter pre-installed); falls back if image unavailable.
    score_image = _resolve_score_image()
    score_cmd = [
        "docker", "run", "--rm",
        "--network", "none",
        "-v", f"{staging}:/staging",
        score_image,
        "python3", "/staging/score_result.py",
    ]

    try:
        score_proc = subprocess.run(
            score_cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return _error_result(problem_id, "scorer timeout")

    for line in reversed(score_proc.stdout.splitlines()):
        line = line.strip()
        if line:
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue

    return _error_result(problem_id, score_proc.stderr[-300:] if score_proc.stderr else "no output")


_score_image_cache: str | None = None


def _resolve_score_image() -> str:
    """Return SCORE_IMAGE if it can be pulled, else fall back to plain python:3.12-slim."""
    global _score_image_cache
    if _score_image_cache is not None:
        return _score_image_cache

    r = subprocess.run(
        ["docker", "pull", "--quiet", SCORE_IMAGE],
        capture_output=True,
        timeout=120,
    )
    _score_image_cache = SCORE_IMAGE if r.returncode == 0 else SCORE_IMAGE_FALLBACK
    return _score_image_cache


def _timeout_result(problem_id: str) -> dict:
    return {
        "problem_id": problem_id,
        "patch_applied": False,
        "tests_passed": False,
        "base_score": 0.0,
        "final_score": 0.0,
        "error": "timeout",
    }


def _error_result(problem_id: str, detail: str) -> dict:
    return {
        "problem_id": problem_id,
        "patch_applied": False,
        "tests_passed": False,
        "base_score": 0.0,
        "final_score": 0.0,
        "error": detail,
    }


def _enrich_result(
    result: dict,
    staging: Path,
    problem_dir: Path,
    patch_path: Path,
    meta: dict,
) -> dict:
    """
    Add the full benchmark metric set to a sandbox result dict.

    The Phase 2 scorer script only emits base_score and tests_passed — it
    cannot access baselines.json or the reference diff from inside the
    network-isolated container. This function computes the remaining metrics
    (test_pass_rate, relative_score, benchmark_score, file_coverage,
    test_deletion_warning) using the staging directory artifacts after the
    container has exited but before the temp dir is cleaned up.

    Idempotent: if the result already has benchmark_score set, skips re-computation.
    Skips enrichment when patch_applied is False (nothing to score).
    """
    from benchmark.harness.score import (
        parse_test_count,
        load_baselines,
        file_coverage_stats,
        detect_test_deletion,
        test_assertion_delta,
        compute_test_quality_factor,
    )

    if not result.get("patch_applied"):
        # Ensure zero-value fields are present even for non-applied patches.
        result.setdefault("test_pass_rate", 0.0)
        result.setdefault("relative_score", None)
        result.setdefault("benchmark_score", 0.0)
        result.setdefault("anti_gaming_multiplier", 1.0)
        return result

    if "benchmark_score" in result:
        return result  # already enriched

    # --- test_pass_rate -------------------------------------------------------
    test_out = ""
    test_out_path = staging / "test_out.txt"
    if test_out_path.exists():
        test_out = test_out_path.read_text(errors="replace")

    test_cmd: list[str] = meta.get("test_cmd", ["python", "-m", "pytest"])
    n_passed, n_total = parse_test_count(test_out, test_cmd)
    tests_passed = result.get("tests_passed", False)

    if n_total > 0:
        test_pass_rate = round(n_passed / n_total, 4)
    else:
        # parse failed — binary fallback
        test_pass_rate = 1.0 if tests_passed else 0.0
        n_passed = n_total = 0

    result["tests_passed_count"] = n_passed
    result["tests_total_count"] = n_total
    result["test_pass_rate"] = test_pass_rate

    # --- relative_score -------------------------------------------------------
    base_score = result.get("base_score", 0.0)
    pid = meta.get("id", "")
    oracle = load_baselines().get(pid, 0.0)
    rel_score = round(min(base_score / oracle, 2.0), 4) if oracle > 0 else None
    result["relative_score"] = rel_score
    result["oracle_base_score"] = oracle

    # --- file_coverage + test_deletion ----------------------------------------
    diff_text = patch_path.read_text(errors="replace")
    result.update(file_coverage_stats(problem_dir, diff_text))
    deletion_info = detect_test_deletion(diff_text)
    result.update(deletion_info)

    # --- benchmark_score -------------------------------------------------------
    # Graduated anti-gaming: ≤3 removed → 1.0, 4–8 → linear 0.9→0.5, >8 → 0.5.
    # Mirrors score.py logic so sandbox and local runs are consistent.
    removed = deletion_info["test_assertions_removed"]
    if removed <= 3:
        anti_gaming = 1.0
    elif removed <= 8:
        anti_gaming = round(1.0 - 0.1 * (removed - 3), 4)
    else:
        anti_gaming = 0.5
    result["anti_gaming_multiplier"] = anti_gaming

    # --- test_assertion_delta + test_quality_factor ----------------------------
    assertion_info = test_assertion_delta(problem_dir, diff_text)
    result.update(assertion_info)
    tqf = compute_test_quality_factor(assertion_info["test_coverage_ratio"])
    result["test_quality_factor"] = tqf

    result["benchmark_score"] = round(test_pass_rate * (rel_score or 0.0) * anti_gaming * tqf, 4)

    return result
