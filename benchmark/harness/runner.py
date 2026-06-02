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

    # Python scorer: reads results from staging, prints JSON, exits 0 always
    (staging / "score_result.py").write_text(textwrap.dedent("""\
        import json, math, pathlib, sys

        staging = pathlib.Path("/staging")

        patch_status = (staging / "patch_status").read_text().strip() if (staging / "patch_status").exists() else "failed"
        if patch_status != "applied":
            print(json.dumps({
                "patch_applied": False,
                "tests_passed": False,
                "correctness_score": 0.0,
                "quality_score": 0.0,
                "final_score": 0.0,
            }))
            sys.exit(0)

        test_rc = int((staging / "test_rc").read_text().strip()) if (staging / "test_rc").exists() else 1
        tests_passed = test_rc == 0
        test_out = (staging / "test_out.txt").read_text(errors="replace") if (staging / "test_out.txt").exists() else ""

        patch_text = (staging / "candidate.diff").read_text()
        added_lines = [l[1:] for l in patch_text.splitlines() if l.startswith("+") and not l.startswith("+++")]
        structural = {"def ": 2.0, "class ": 2.5, "async def ": 1.5, "fn ": 2.0, "impl ": 1.75, "func ": 2.0}
        tok = 0.0
        for line in added_lines:
            s = line.strip()
            if not s or s.startswith("#") or s.startswith("//"):
                continue
            w = 0.07
            for kw, kw_w in structural.items():
                if kw in s:
                    w = max(w, kw_w)
            tok += w

        quality = round(1.0 - math.exp(-tok / 58.0), 4)
        cs = 1.0 if tests_passed else 0.0

        meta = json.loads((staging / "meta.json").read_text())
        print(json.dumps({
            "problem_id": meta["id"],
            "patch_applied": True,
            "tests_passed": tests_passed,
            "test_output": test_out[-2000:] if not tests_passed else "",
            "correctness_score": cs,
            "quality_score": quality if tests_passed else 0.0,
            "final_score": round(cs * (0.5 + 0.5 * quality), 4),
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
        "correctness_score": 0.0,
        "quality_score": 0.0,
        "final_score": 0.0,
        "error": "timeout",
    }


def _error_result(problem_id: str, detail: str) -> dict:
    return {
        "problem_id": problem_id,
        "patch_applied": False,
        "tests_passed": False,
        "correctness_score": 0.0,
        "quality_score": 0.0,
        "final_score": 0.0,
        "error": detail,
    }
