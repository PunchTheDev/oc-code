"""
Gittensor Base-Miner REST API

Serves benchmark data over HTTP so miners can programmatically fetch problems,
the current shard, the leaderboard, and pool statistics.

Usage:
    python gitminer.py serve-api               # defaults: host=0.0.0.0 port=8083
    python gitminer.py serve-api --port 9000

Endpoints:
    GET /api/health              liveness check
    GET /api/stats               pool-level statistics
    GET /api/shard               current weekly shard (30 problems)
    GET /api/problems            full problem list (filterable, paginated)
    GET /api/problems/{id}       one problem by ID (includes diff_stats)
    GET /api/problems/{id}/diff  raw unified diff of the accepted solution
    GET /api/leaderboard              current ranked submissions
    GET /api/agents/{handle}/history  full per-submission history for one agent
    GET /api/agents                   agent discovery document — structured onboarding for autonomous agents
"""

from __future__ import annotations

import json
import hashlib
import os
import random
import sys
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

# Add repo root to sys.path so benchmark.catalog is importable when running
# this file directly (e.g. python api/server.py) as well as via gitminer.py.
_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from benchmark.catalog import REPO_CATEGORY  # noqa: E402


REPO_ROOT = _REPO_ROOT
POOL_DIR = REPO_ROOT / "benchmark" / "problems"
POOL_CONFIG = REPO_ROOT / "benchmark" / "pool_config.json"
BASELINES = REPO_ROOT / "results" / "baselines.json"
LEADERBOARD = REPO_ROOT / "results" / "leaderboard.json"
AGENTS_DIR = REPO_ROOT / "results" / "agents"

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def _pool_config() -> dict:
    if POOL_CONFIG.exists():
        return json.loads(POOL_CONFIG.read_text())
    return {"shard_size": 30, "rotation_policy": "weekly", "rotation_seed": 42}


def _all_problem_ids() -> list[str]:
    if not POOL_DIR.exists():
        return []
    return sorted(p.name for p in POOL_DIR.iterdir() if p.is_dir())


def _load_meta(problem_id: str) -> dict | None:
    path = POOL_DIR / problem_id / "meta.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _baseline_map() -> dict[str, float]:
    """Returns {problem_id: base_score}."""
    if not BASELINES.exists():
        return {}
    data = json.loads(BASELINES.read_text())
    return {p["id"]: p["base_score"] for p in data.get("problems", [])}


def _oracle_weighted_score() -> float:
    """Returns the difficulty-weighted oracle mean (the metric miners compete on)."""
    if not BASELINES.exists():
        return 0.0
    try:
        data = json.loads(BASELINES.read_text())
        ws = data.get("weighted_mean_score")
        return float(ws) if ws is not None else float(data.get("mean_score", 0))
    except Exception:
        return 0.0


def _shard_problem_dirs(config: dict) -> list[Path]:
    """Return the category-balanced shard dirs, matching evaluate.py exactly."""
    from benchmark.evaluate import select_shard
    all_dirs = sorted(POOL_DIR.glob("*/meta.json"))
    if not all_dirs:
        return []
    return select_shard([p.parent for p in all_dirs], config)


def _difficulty_by_lines(problem_dir: Path) -> str:
    """Difficulty tier using the multi-factor model from evaluate.py.

    Matches the actual scoring weight used at eval time (multi-file and
    new-file multipliers can promote medium→hard).  Callers should always
    use this function rather than catalog.problem_tier directly.
    """
    from benchmark.evaluate import problem_difficulty
    name, _ = problem_difficulty(problem_dir)
    return name


def _category(meta: dict) -> str:
    repo = meta.get("repo_name", "").lower()
    return REPO_CATEGORY.get(repo, "python")


def _problem_summary(meta: dict, baselines: dict[str, float]) -> dict:
    pid = meta["id"]
    score = baselines.get(pid, 0.0)
    cat = _category(meta)
    return {
        "id": pid,
        "repo": meta.get("repo_name", ""),
        "pr": meta.get("pr_number"),
        "issue_number": meta.get("issue_number"),
        "issue_title": meta.get("issue_title", ""),
        "merged_at": meta.get("merged_at", ""),
        "category": cat,
        "difficulty": _difficulty_by_lines(POOL_DIR / pid),
        "baseline_score": round(score, 2),
        "test_cmd": meta.get("test_cmd", []),
    }


def _diff_stats(problem_id: str) -> dict:
    """Parse reference.diff and return add/remove/files counts."""
    ref = POOL_DIR / problem_id / "reference.diff"
    if not ref.exists():
        return {"add": 0, "remove": 0, "files": 0, "bytes": 0}
    content = ref.read_text(errors="replace")
    lines = content.splitlines()
    add = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
    remove = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
    files = sum(1 for l in lines if l.startswith("diff --git "))
    return {"add": add, "remove": remove, "files": files, "bytes": len(content.encode())}


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt: str, *args) -> None:  # quiet mode
        pass

    def do_OPTIONS(self) -> None:
        self._send(200, {})

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        qs = parse_qs(parsed.query)

        try:
            body = self._route(path, qs)
            if isinstance(body, str):
                self._send_text(200, body)
            else:
                self._send(200, body)
        except _NotFound as e:
            self._send(404, {"error": str(e)})
        except Exception as e:
            self._send(500, {"error": str(e)})

    def _route(self, path: str, qs: dict) -> Any:
        if path == "/api/health":
            return self._health()
        if path == "/api/stats":
            return self._stats()
        if path == "/api/shard":
            return self._shard()
        if path == "/api/leaderboard":
            return self._leaderboard()
        if path.startswith("/api/agents/") and path.endswith("/history"):
            handle = path[len("/api/agents/"):-len("/history")]
            if handle:
                return self._agent_history(handle)
        if path == "/api/agents":
            return self._agents()
        if path == "/api/problems":
            return self._problems(qs)
        if path.startswith("/api/problems/"):
            rest = path[len("/api/problems/"):]
            if rest.endswith("/diff"):
                pid = rest[: -len("/diff")]
                return self._problem_diff(pid)
            return self._problem(rest)
        raise _NotFound(f"Unknown endpoint: {path}")

    def _health(self) -> dict:
        return {
            "status": "ok",
            "pool_size": len(_all_problem_ids()),
            "version": "1.0",
        }

    def _stats(self) -> dict:
        baselines = _baseline_map()
        scores = list(baselines.values())
        config = _pool_config()
        all_ids = _all_problem_ids()
        shard = _shard_problem_dirs(config)

        by_category: dict[str, int] = {}
        by_difficulty: dict[str, int] = {}
        repos: set[str] = set()
        for pid in all_ids:
            meta = _load_meta(pid)
            if not meta:
                continue
            cat = _category(meta)
            by_category[cat] = by_category.get(cat, 0) + 1
            diff = _difficulty_by_lines(POOL_DIR / pid)
            by_difficulty[diff] = by_difficulty.get(diff, 0) + 1
            repos.add(meta.get("repo_name", ""))

        return {
            "pool_size": len(all_ids),
            "shard_size": len(shard),
            "repos": len(repos),
            "oracle_score": _oracle_weighted_score(),
            "by_category": by_category,
            "by_difficulty": by_difficulty,
            "rotation_policy": config.get("rotation_policy", "weekly"),
        }

    def _shard(self) -> dict:
        config = _pool_config()
        baselines = _baseline_map()
        shard_dirs = _shard_problem_dirs(config)

        epoch = date(2024, 1, 1)
        week_number = (date.today() - epoch).days // 7
        today = date.today()
        days_to_monday = (7 - today.weekday()) % 7 or 7
        next_rotation = str(today + timedelta(days=days_to_monday))

        problems = []
        for d in shard_dirs:
            meta = _load_meta(d.name)
            if meta:
                problems.append(_problem_summary(meta, baselines))

        return {
            "week": week_number,
            "shard_size": len(shard_dirs),
            "next_rotation": next_rotation,
            "problems": problems,
        }

    def _problems(self, qs: dict) -> dict:
        # Accept both `cat` (preferred) and `lang` (deprecated alias)
        cat_filter = qs.get("cat", qs.get("lang", [None]))[0]
        diff_filter = qs.get("difficulty", [None])[0]
        repo_filter = qs.get("repo", [None])[0]
        search = qs.get("q", [None])[0]
        try:
            limit = int(qs.get("limit", [100])[0])
            offset = int(qs.get("offset", [0])[0])
        except ValueError:
            limit, offset = 100, 0

        all_ids = _all_problem_ids()
        baselines = _baseline_map()
        results = []

        for pid in all_ids:
            meta = _load_meta(pid)
            if not meta:
                continue
            s = _problem_summary(meta, baselines)
            if cat_filter and s["category"] != cat_filter:
                continue
            if diff_filter and s["difficulty"] != diff_filter:
                continue
            if repo_filter and repo_filter.lower() not in s["repo"].lower():
                continue
            if search:
                q = search.lower()
                if q not in s["issue_title"].lower() and q not in s["repo"].lower():
                    continue
            results.append(s)

        total = len(results)
        page = results[offset : offset + limit]
        return {"total": total, "offset": offset, "limit": limit, "problems": page}

    def _problem(self, pid: str) -> dict:
        meta = _load_meta(pid)
        if not meta:
            raise _NotFound(f"Problem {pid!r} not found")
        baselines = _baseline_map()
        summary = _problem_summary(meta, baselines)
        # Include full file tree and context file paths (not content, to keep response light)
        context_dir = POOL_DIR / pid / "context"
        context_paths: list[str] = []
        if context_dir.exists():
            context_paths = sorted(
                str(p.relative_to(context_dir)) for p in context_dir.rglob("*") if p.is_file()
            )
        return {
            **summary,
            "base_commit": meta.get("base_commit", ""),
            "repo_url": meta.get("repo_url", f"https://github.com/{meta.get('repo_name','')}"),
            "issue_body": meta.get("issue_body", ""),
            "file_tree": meta.get("file_tree", []),
            "context_files": context_paths,
            "das_score": meta.get("das_score"),
            "das_token_score": meta.get("das_token_score"),
            "time_limit_seconds": meta.get("time_limit_seconds", 120),
            "output_token_budget": meta.get("output_token_budget", 50000),
            "diff_stats": _diff_stats(pid),
            "diff_url": f"/api/problems/{pid}/diff",
        }

    def _problem_diff(self, pid: str) -> str:
        ref = POOL_DIR / pid / "reference.diff"
        if not ref.exists():
            raise _NotFound(f"No reference diff for problem {pid!r}")
        return ref.read_text(errors="replace")

    def _agents(self) -> dict:
        """Discovery document for AI agents — structured onboarding for autonomous competitors."""
        config = _pool_config()
        baselines = _baseline_map()
        all_ids = _all_problem_ids()
        shard_dirs = _shard_problem_dirs(config)

        # Load allowed models
        allowed_models_path = REPO_ROOT / "benchmark" / "harness" / "allowed_models.txt"
        allowed_models = []
        if allowed_models_path.exists():
            for line in allowed_models_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    allowed_models.append(line)

        # Current leaderboard champion
        champion_score = None
        champion_agent = None
        if LEADERBOARD.exists():
            entries = json.loads(LEADERBOARD.read_text())
            ranked = [e for e in entries if e.get("rank") is not None and e.get("score") is not None]
            if ranked:
                top = max(ranked, key=lambda e: e.get("weighted_score") or e.get("score", 0))
                champion_score = top.get("weighted_score") or top.get("score")
                champion_agent = top.get("agent")

        oracle_score = _oracle_weighted_score()

        return {
            "name": "Gittensor Base Miner Benchmark",
            "description": (
                "A competitive benchmark on Gittensor subnet 74 (Bittensor). "
                "Build an AI agent that solves real GitHub issues from the Gittensor network. "
                "The agent with the highest well-rounded score across 30 sampled problems "
                "earns TAO mining emissions and becomes the new base miner for the subnet."
            ),
            "version": "1.0",
            "subnet": 74,
            "network": "Bittensor / Gittensor",
            "dashboard": "http://143.244.191.193:8082/",
            "repo": "https://github.com/PunchTheDev/gittensor-base-miner",
            "interface": {
                "class": "BaseAgent",
                "method": "solve(problem: Problem) -> Patch",
                "location": "agent/base.py",
                "example": "agent/example/agent.py",
            },
            "pool": {
                "total_problems": len(all_ids),
                "shard_size": len(shard_dirs),
                "rotation": config.get("rotation_policy", "weekly"),
                "categories": config.get("shard_budget", {}),
                "source": "Gittensor DAS network — real merged PRs from registered repos",
            },
            "scoring": {
                "primary_metric": "weighted_benchmark_score",
                "formula": "benchmark_score = test_pass_rate × relative_score × anti_gaming_multiplier × test_quality_factor",
                "weighted_formula": "weighted_benchmark_score = sum(benchmark_score × difficulty_weight) / sum(weight)",
                "difficulty_weights": {"easy": 1.0, "medium": 1.5, "hard": 2.0},
                "correctness_gates_quality": True,
                "oracle_score": oracle_score,
                "champion_score": champion_score,
                "champion_agent": champion_agent,
                "note": (
                    "Tests must pass first (test_pass_rate); then relative_score = "
                    "agent_token_score / oracle_token_score measures implementation quality. "
                    "anti_gaming_multiplier penalises similarity to prior submissions. "
                    "test_quality_factor (0.85–1.0) rewards agents that add test assertions. "
                    "oracle_score is the difficulty-weighted mean (hard×2/medium×1.5/easy×1). "
                    "Beat the champion weighted_benchmark_score across 30 problems to win."
                ),
            },
            "constraints": {
                "wall_time_s": 120,
                "output_tokens": 50000,
                "network": "blocked_except_model_api",
                "allowed_models": allowed_models,
            },
            "submission": {
                "method": "GitHub pull request",
                "url": "https://github.com/PunchTheDev/gittensor-base-miner/compare",
                "path": "agent/submissions/<your-handle>/agent.py",
                "ci": "automatic — CI scores your agent and posts results as a PR comment",
            },
            "quickstart": {
                "clone": "git clone https://github.com/PunchTheDev/gittensor-base-miner",
                "install": "pip install -r requirements.txt",
                "env": "export OPENROUTER_KEY=sk-or-...",
                "run_one": (
                    "python3 gitminer.py run "
                    "--problem 0463 "
                    "--agent agent/example/agent.py "
                    "--score --no-sandbox"
                ),
                "run_shard": (
                    "python3 gitminer.py eval "
                    "agent/submissions/<handle>/agent.py "
                    "--no-sandbox"
                ),
                "mine_loop": (
                    "python3 gitminer.py mine "
                    "--agent agent/submissions/<handle>/agent.py "
                    "--loop"
                ),
            },
            "api": {
                "base": "http://143.244.191.193:8083",
                "endpoints": {
                    "/api/shard": "Current 30-problem weekly eval set (category-balanced)",
                    "/api/problems": "Full pool (filterable: ?cat=python&difficulty=hard)",
                    "/api/problems/{id}": "Single problem detail with context files",
                    "/api/problems/{id}/diff": "Reference diff (accepted solution)",
                    "/api/leaderboard": "Ranked submissions",
                    "/api/stats": "Pool statistics and oracle score",
                    "/api/agents": "This document",
                },
            },
        }

    def _agent_history(self, handle: str) -> dict:
        hist_file = AGENTS_DIR / handle / "history.json"
        if not hist_file.exists():
            return {"handle": handle, "submissions": []}
        entries = json.loads(hist_file.read_text())
        # Strip per-problem breakdown from history entries to keep response small
        summary = [
            {k: v for k, v in e.items() if k != "breakdown"}
            for e in entries
        ]
        return {"handle": handle, "submissions": summary, "total": len(summary)}

    def _leaderboard(self) -> dict:
        if not LEADERBOARD.exists():
            return {"entries": []}
        entries = json.loads(LEADERBOARD.read_text())
        return {"entries": entries}

    def _send(self, status: int, body: Any) -> None:
        payload = json.dumps(body, indent=2).encode()
        self.send_response(status)
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_text(self, status: int, body: str) -> None:
        payload = body.encode()
        self.send_response(status)
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class _NotFound(Exception):
    pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def serve(host: str = "0.0.0.0", port: int = 8083) -> None:
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Gittensor Base-Miner API listening on http://{host}:{port}")
    print("  GET /api/health              liveness check")
    print("  GET /api/stats               pool statistics")
    print("  GET /api/shard               current weekly shard")
    print("  GET /api/problems            problem list (filterable)")
    print("  GET /api/problems/{id}       single problem detail")
    print("  GET /api/problems/{id}/diff  raw reference diff (text/plain)")
    print("  GET /api/leaderboard             current leaderboard")
    print("  GET /api/agents/{handle}/history per-agent submission history")
    print("  GET /api/agents                  agent discovery document")
    print()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nAPI server stopped.")
