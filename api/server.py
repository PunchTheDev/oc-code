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
    GET /api/leaderboard         current ranked submissions
"""

from __future__ import annotations

import json
import hashlib
import os
import random
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


REPO_ROOT = Path(__file__).parent.parent
POOL_DIR = REPO_ROOT / "benchmark" / "problems"
POOL_CONFIG = REPO_ROOT / "benchmark" / "pool_config.json"
BASELINES = REPO_ROOT / "results" / "baselines.json"
LEADERBOARD = REPO_ROOT / "results" / "leaderboard.json"
ALLOWED_MODELS = REPO_ROOT / "benchmark" / "allowed_models.txt"

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}

# Mirrors benchmark/evaluate.py — repo → language category used everywhere else.
REPO_CATEGORY: dict[str, str] = {
    "entrius/gittensor": "python",
    "entrius/allways": "python",
    "entrius/das-github-mirror": "python",
    "entrius/allways-ui": "typescript",
    "entrius/gittensor-ui": "typescript",
    "entrius/oc-1": "typescript",
    "aglover1221/product-data-extractor": "python",
    "cogniax/tao-pulse-app": "typescript",
    "e35ventura/taopedia": "python",
    "e35ventura/taopedia-articles": "python",
    "geniepod/genie-claw": "rust",
    "infiniflow/ragflow": "python",
    "jsonbored/awesome-claude": "typescript",
    "jsonbored/gittensory": "typescript",
    "mkdev11/gittensor-hub": "typescript",
    "vouchdev/vouch": "typescript",
    "phase-rs/phase": "rust",
    "seroperson/jvm-live-reload": "jvm",
    "touchpilot/touchpilot": "jvm",
    "we-promise/sure": "ruby",
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


def _shard_ids(all_ids: list[str], config: dict) -> list[str]:
    shard_size = config.get("shard_size", 30)
    policy = config.get("rotation_policy", "weekly")
    base_seed = config.get("rotation_seed", 42)

    if shard_size >= len(all_ids):
        return all_ids

    if policy == "fixed":
        seed = base_seed
    elif policy == "weekly":
        epoch = date(2024, 1, 1)
        week_number = (date.today() - epoch).days // 7
        seed = base_seed ^ week_number
    else:
        seed = random.randint(0, 2**32)

    secret = os.environ.get("SHARD_SECRET", "")
    if secret:
        secret_int = int(hashlib.sha256(secret.encode()).hexdigest()[:8], 16)
        seed ^= secret_int

    rng = random.Random(seed)
    pool = list(all_ids)
    rng.shuffle(pool)
    return pool[:shard_size]


def _difficulty(base_score: float) -> str:
    if base_score >= 15:
        return "easy"
    if base_score >= 5:
        return "medium"
    return "hard"


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
        "difficulty": _difficulty(score),
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
        shard = _shard_ids(all_ids, config)

        by_category: dict[str, int] = {}
        by_difficulty: dict[str, int] = {}
        repos: set[str] = set()
        for pid in all_ids:
            meta = _load_meta(pid)
            if not meta:
                continue
            cat = _category(meta)
            by_category[cat] = by_category.get(cat, 0) + 1
            diff = _difficulty(baselines.get(pid, 0.0))
            by_difficulty[diff] = by_difficulty.get(diff, 0) + 1
            repos.add(meta.get("repo_name", ""))

        return {
            "pool_size": len(all_ids),
            "shard_size": len(shard),
            "repos": len(repos),
            "oracle_score": round(sum(scores) / len(scores), 2) if scores else 0,
            "by_category": by_category,
            "by_difficulty": by_difficulty,
            "rotation_policy": config.get("rotation_policy", "weekly"),
        }

    def _shard(self) -> dict:
        config = _pool_config()
        all_ids = _all_problem_ids()
        shard_ids = _shard_ids(all_ids, config)
        baselines = _baseline_map()

        epoch = date(2024, 1, 1)
        week_number = (date.today() - epoch).days // 7
        # Next rotation: next Monday
        today = date.today()
        days_to_monday = (7 - today.weekday()) % 7 or 7
        next_rotation = str(today.replace(day=today.day + days_to_monday) if days_to_monday else today)

        problems = []
        for pid in shard_ids:
            meta = _load_meta(pid)
            if meta:
                problems.append(_problem_summary(meta, baselines))

        return {
            "week": week_number,
            "shard_size": len(shard_ids),
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
    print("  GET /api/leaderboard         current leaderboard")
    print()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nAPI server stopped.")
