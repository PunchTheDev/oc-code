"""
Docker-sandboxed problem runner.

Executes scoring for a single benchmark problem inside an isolated container:
  - Hard time limit enforced via subprocess timeout + docker kill
  - Memory cap via --memory
  - Setup phase: network allowed for git clone / apt-get / pip install
  - Score phase: network blocked (--network none) — scorer only reads staging files
  - Secrets (OPENROUTER_KEY etc.) never passed to containers — no model cheating
  - Ephemeral: container is removed after each run (--rm)

Usage:
    from benchmark.harness.runner import run_in_sandbox
    result = run_in_sandbox(problem_dir, patch_path)

For local development without Docker, score.score_patch() is called directly.
Daytona CI integration lives in ci/daytona.yml and calls this module.
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
EVAL_IMAGE = "python:3.12-slim"
KILL_GRACE = 15  # seconds docker waits after stop signal before SIGKILL


def _docker_available() -> bool:
    return shutil.which("docker") is not None


def run_in_sandbox(problem_dir: Path, patch_path: Path) -> dict:
    """
    Score a patch in an isolated Docker container.

    Falls back to in-process scoring when Docker is unavailable (local dev mode).
    Return dict matches score.score_patch() exactly.
    """
    if not _docker_available():
        from benchmark.harness.score import score_patch
        return score_patch(problem_dir, patch_path)

    meta = json.loads((problem_dir / "meta.json").read_text())
    time_limit: int = meta.get("time_limit_seconds", 120)

    with tempfile.TemporaryDirectory(prefix="bminer_") as staging:
        staging_path = Path(staging)
        _prepare_staging(staging_path, meta, patch_path)
        return _run_container(staging_path, meta, time_limit)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _prepare_staging(staging: Path, meta: dict, patch_path: Path) -> None:
    """Write all files the container needs into the staging directory."""
    shutil.copy(patch_path, staging / "candidate.diff")
    (staging / "meta.json").write_text(json.dumps(meta))

    # Shell script: clone → checkout → install → apply → test → emit exit code
    test_cmd = " ".join(meta.get("test_cmd", ["python", "-m", "pytest", "--tb=short", "-q"]))
    (staging / "setup_and_test.sh").write_text(textwrap.dedent(f"""\
        #!/usr/bin/env bash
        set -euo pipefail
        export DEBIAN_FRONTEND=noninteractive

        apt-get update -qq >/dev/null
        apt-get install -y -qq git >/dev/null

        git clone --quiet {meta["repo_url"]} /repo
        cd /repo
        git checkout --quiet {meta["base_commit"]}

        # Install deps (best-effort)
        pip install pytest --quiet >/dev/null 2>&1 || true
        if [ -f pyproject.toml ]; then
            pip install -e ".[dev]" --quiet >/dev/null 2>&1 || \
            pip install -e . --quiet >/dev/null 2>&1 || true
        elif [ -f requirements.txt ]; then
            pip install -r requirements.txt --quiet >/dev/null 2>&1 || true
        fi

        # Apply patch — write outcome so scorer can read it
        if git apply /staging/candidate.diff; then
            echo "applied" > /staging/patch_status
        else
            echo "failed" > /staging/patch_status
            exit 0
        fi

        # Run tests — capture output + exit code
        {test_cmd} > /staging/test_out.txt 2>&1
        echo $? > /staging/test_rc
    """))
    (staging / "setup_and_test.sh").chmod(0o755)

    # Python scorer: reads results from staging, prints JSON, exits 0 always.
    # Self-contained stdlib-only script — runs inside bare python:3.12-slim container.
    # Mirrors score.py's Gittensor formula; keep in sync when score.py changes.
    #
    # Escaping note: this string is written via write_text(), so each \\ in this
    # source becomes a single \ in the file. Regex patterns use single-char classes
    # and avoid quote chars to sidestep double-escaping.
    (staging / "score_result.py").write_text(textwrap.dedent("""\
        import json, math, pathlib, re, sys

        MERGED_PR_BASE_SCORE = 25
        SRC_TOK_SATURATION_SCALE = 58.0
        MAX_CONTRIBUTION_BONUS = 5
        CONTRIBUTION_SCORE_FOR_FULL_BONUS = 1500

        staging = pathlib.Path("/staging")

        patch_status = (staging / "patch_status").read_text().strip() if (staging / "patch_status").exists() else "failed"
        meta_raw = (staging / "meta.json").read_text() if (staging / "meta.json").exists() else "{}"
        meta = json.loads(meta_raw)
        problem_id = meta.get("id", "unknown")

        if patch_status != "applied":
            print(json.dumps({"problem_id": problem_id, "patch_applied": False,
                               "tests_passed": False, "base_score": 0.0, "final_score": 0.0}))
            sys.exit(0)

        test_rc = int((staging / "test_rc").read_text().strip()) if (staging / "test_rc").exists() else 1
        tests_passed = test_rc == 0
        test_out = (staging / "test_out.txt").read_text(errors="replace") if (staging / "test_out.txt").exists() else ""

        if not tests_passed:
            print(json.dumps({"problem_id": problem_id, "patch_applied": True, "tests_passed": False,
                               "test_output": test_out[-2000:], "base_score": 0.0, "final_score": 0.0}))
            sys.exit(0)

        saturation_scale = float(meta.get("src_tok_saturation_scale", SRC_TOK_SATURATION_SCALE))

        # Token scoring — approximates score.py's Gittensor formula
        # Structural keywords get a 1.5x bonus; comments and blanks are skipped.
        STRUCT_WORDS = ("def ", "class ", "async def ", "fn ", "impl ", "struct ",
                        "func ", "interface ", "enum ", "trait ", "type ")
        SKIP_STARTS = ("#", "//", "/*", "*", "<!--", "pass", "...")
        DELIM = re.compile(r"[\\s()\\[\\]{},;:=<>!&|.@#$%^~]+")

        patch_text = (staging / "candidate.diff").read_text()
        src_score = 0.0
        total_score = 0.0
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
            total_score += line_score
            if not in_test:
                src_score += line_score

        initial = MERGED_PR_BASE_SCORE * (1.0 - math.exp(-src_score / saturation_scale))
        bonus_pct = min(1.0, total_score / CONTRIBUTION_SCORE_FOR_FULL_BONUS)
        base_score = round(initial + bonus_pct * MAX_CONTRIBUTION_BONUS, 2)

        print(json.dumps({
            "problem_id": problem_id,
            "patch_applied": True,
            "tests_passed": True,
            "source_token_score": round(src_score, 2),
            "total_token_score": round(total_score, 2),
            "base_score": base_score,
            "final_score": base_score,
        }))
    """))


def _run_container(staging: Path, meta: dict, time_limit: int) -> dict:
    problem_id = meta["id"]
    container_name = f"bminer_{problem_id}_{os.getpid()}"
    host_timeout = time_limit + KILL_GRACE + 60

    # Phase 1: setup + test
    # Network is allowed here so git clone, apt-get, and pip install succeed.
    # OPENROUTER_KEY and other secrets are not passed to the container, so the
    # agent's patch cannot call external model APIs even with network access.
    setup_cmd = [
        "docker", "run", "--rm",
        "--name", container_name,
        "--memory", MEMORY_LIMIT,
        "--cpus", CPU_LIMIT,
        "--stop-timeout", str(KILL_GRACE),
        "-v", f"{staging}:/staging",
        EVAL_IMAGE,
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

    # Phase 2: score from artifacts written to staging
    score_cmd = [
        "docker", "run", "--rm",
        "--network", "none",
        "-v", f"{staging}:/staging",
        EVAL_IMAGE,
        "python3", "/staging/score_result.py",
    ]

    try:
        score_proc = subprocess.run(
            score_cmd,
            capture_output=True,
            text=True,
            timeout=30,
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
