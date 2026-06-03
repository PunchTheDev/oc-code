"""Generate data.json for the static dashboard from the current problem pool."""

import json
import pathlib
import sys
from datetime import date

# Repo → language category mapping (all Gittensor DAS registered repos)
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
    "vouchdev/vouch": "python",
    "phase-rs/phase": "rust",
    "seroperson/jvm-live-reload": "jvm",
    "touchpilot/touchpilot": "jvm",
    "we-promise/sure": "ruby",
    # External prestige repos (not in Gittensor DAS — added via expand_pool_external.py)
    "pytest-dev/pytest": "python",
    "pallets/click": "python",
    "pallets/werkzeug": "python",
    "encode/starlette": "python",
    "psf/requests": "python",
    "aio-libs/aiohttp": "python",
    "pallets/flask": "python",
    "tiangolo/fastapi": "python",
    "tornadoweb/tornado": "python",
    "twisted/twisted": "python",
    "python-trio/trio": "python",
    "celery/celery": "python",
    # Ruby external repos
    "rubocop/rubocop": "ruby",
    "rubocop/rubocop-rails": "ruby",
    # TypeScript external repos
    "colinhacks/zod": "typescript",
    "vitest-dev/vitest": "typescript",
    "trpc/trpc": "typescript",
    "vuejs/core": "typescript",
    # Python external repos (continued)
    "python/mypy": "python",
    # Rust external repos
    "tokio-rs/tokio": "rust",
    "clap-rs/clap": "rust",
    "hyperium/hyper": "rust",
    "tokio-rs/axum": "rust",
    # JVM external repos
    "fasterxml/jackson-databind": "jvm",
    "square/okhttp": "jvm",
    # Go external repos
    "gin-gonic/gin": "go",
    "labstack/echo": "go",
    "gofiber/fiber": "go",
    "grpc/grpc-go": "go",
    "spf13/cobra": "go",
    "google/guava": "jvm",
    "serde-rs/serde": "rust",
    "sindresorhus/got": "typescript",
    "tanstack/query": "typescript",
}

# Shard sampling budget per category (sums to 30)
# Proportional to pool: python:38% rust:24% typescript:16% go:8% jvm:7% ruby:6%
SHARD_BUDGET: dict[str, int] = {
    "python": 11,
    "rust": 7,
    "typescript": 5,
    "ruby": 2,
    "jvm": 2,
    "go": 3,
}


def repo_category(repo: str) -> str:
    """Return language category for a repo, lower-cased."""
    return REPO_CATEGORY.get(repo.lower(), REPO_CATEGORY.get(repo, "other"))


def difficulty_tier(added_lines: int) -> str:
    """Classify a problem by difficulty based on reference diff added-line count.

    Mirrors evaluate.py DIFFICULTY_TIERS so dashboard badges match scoring weights:
      easy   < 30 added lines  (weight 1.0×) — surgical, targeted fixes
      medium  30–149            (weight 1.5×) — moderate changes
      hard   >= 150             (weight 2.0×) — substantial additions; highest scoring weight
    """
    if added_lines < 30:
        return "easy"
    if added_lines < 150:
        return "medium"
    return "hard"

REPO_ROOT = pathlib.Path(__file__).parent.parent
PROBLEMS_DIR = REPO_ROOT / "benchmark" / "problems"
RESULTS_DIR = REPO_ROOT / "results"

def _load_oracle_row() -> dict:
    baseline_file = RESULTS_DIR / "baselines.json"
    mean_score = weighted_score = None
    count = None
    if baseline_file.exists():
        try:
            data = json.loads(baseline_file.read_text())
            mean_score = round(data["mean_score"], 2)
            weighted_score = round(data.get("weighted_mean_score") or mean_score, 2)
            count = data["count"]
        except Exception:
            pass
    if mean_score is None:
        mean_score = 12.38
        weighted_score = 13.73
        count = 800
    return {
        "rank": None,
        "agent": "Oracle (accepted solution)",
        "score": mean_score,
        "weighted_score": weighted_score,
        "model": "—",
        "date": "—",
        "note": f"Weighted mean {weighted_score} (arithmetic {mean_score}) across {count} accepted solutions (DAS + external prestige repos)",
    }


ORACLE_ROW = _load_oracle_row()


def load_baselines() -> dict[str, dict]:
    """Load per-problem baseline data from results/baselines.json."""
    baseline_file = RESULTS_DIR / "baselines.json"
    if not baseline_file.exists():
        return {}
    try:
        data = json.loads(baseline_file.read_text())
        return {
            p["id"]: {
                "base_score": p["base_score"],
                "source_token_score": p.get("source_token_score"),
                "total_token_score": p.get("total_token_score"),
            }
            for p in data.get("problems", [])
        }
    except Exception:
        return {}


TEST_PATH_PATTERNS = (
    "test_", "_test.", ".test.", ".spec.", "/tests/", "/test/", "/spec/",
    "__tests__", "tests/", "test/",
)


def diff_stats_for(problem_dir: pathlib.Path) -> dict:
    """Return add/remove/files/bytes for the reference diff."""
    ref = problem_dir / "reference.diff"
    if not ref.exists():
        return {"add": 0, "remove": 0, "files": 0, "bytes": 0}
    content = ref.read_text(errors="replace")
    lines = content.splitlines()
    add = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
    remove = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
    files = sum(1 for l in lines if l.startswith("diff --git "))
    return {"add": add, "remove": remove, "files": files, "bytes": len(content.encode())}


def context_files_for(problem_dir: pathlib.Path) -> tuple[list[str], list[str]]:
    """Return (all_files, test_files) as sorted relative path lists."""
    ctx = problem_dir / "context"
    if not ctx.exists():
        return [], []
    all_files = sorted(
        str(f.relative_to(ctx))
        for f in ctx.rglob("*")
        if f.is_file()
    )
    test_files = [
        p for p in all_files
        if any(pat in p.replace("\\", "/") for pat in TEST_PATH_PATTERNS)
    ]
    return all_files, test_files


def load_problems():
    baselines = load_baselines()
    problems = []
    for p in sorted(PROBLEMS_DIR.iterdir()):
        meta_file = p / "meta.json"
        if not meta_file.exists():
            continue
        try:
            meta = json.loads(meta_file.read_text())
        except Exception:
            continue
        das = meta.get("das_score")
        das_f = float(das) if das is not None else None
        repo = meta.get("repo_name", "")
        pr = meta.get("pr_number")
        issue = meta.get("issue_number")
        issue_body = meta.get("issue_body") or ""
        pid = meta.get("id")
        ctx_files, test_files = context_files_for(p)
        stats = diff_stats_for(p)
        b_score = baselines.get(pid, {}).get("base_score") if isinstance(baselines.get(pid), dict) else baselines.get(pid)
        cat = repo_category(repo)
        problems.append(
            {
                "id": pid,
                "repo": repo,
                "category": cat,
                "difficulty": difficulty_tier(stats["add"]),
                "pr": pr,
                "issue": issue,
                "title": (meta.get("issue_title") or "")[:120],
                "issue_body": issue_body[:3000] + ("…" if len(issue_body) > 3000 else ""),
                "merged_at": meta.get("merged_at", ""),
                "das_score": das_f,
                "das_base_score": float(meta.get("das_base_score") or 0),
                "das_token_score": float(meta.get("das_token_score") or 0),
                "das_structural_score": float(meta.get("das_structural_score") or 0),
                "das_total_nodes": meta.get("das_total_nodes"),
                "baseline_score": b_score,
                "src_token_score": (baselines.get(pid) or {}).get("source_token_score"),
                "total_token_score": (baselines.get(pid) or {}).get("total_token_score"),
                "diff_stats": stats,
                "test_cmd": meta.get("test_cmd") or [],
                "base_commit": meta.get("base_commit", ""),
                "pr_url": f"https://github.com/{repo}/pull/{pr}",
                "issue_url": f"https://github.com/{repo}/issues/{issue}" if issue else None,
                "context_files": ctx_files,
                "test_files": test_files,
            }
        )
    return problems


def load_leaderboard():
    """Load leaderboard from results/leaderboard.json, fall back to oracle-only.

    The oracle row is always replaced with the freshly computed ORACLE_ROW so that
    scores stay in sync with baselines.json after pool rotations — not whatever was
    frozen in the stored file.
    """
    lb_file = RESULTS_DIR / "leaderboard.json"
    if lb_file.exists():
        try:
            rows = json.loads(lb_file.read_text())
            # Replace stored oracle row with fresh values from baselines.json
            rows = [ORACLE_ROW if r.get("agent") == "Oracle (accepted solution)" else r for r in rows]
            if not any(r.get("agent") == "Oracle (accepted solution)" for r in rows):
                rows.insert(0, ORACLE_ROW)
            return rows
        except Exception:
            pass
    return [ORACLE_ROW]


def load_history():
    """Load SOTA score history for chart: list of {date, score, agent} records."""
    history_file = RESULTS_DIR / "history.json"
    if history_file.exists():
        try:
            return json.loads(history_file.read_text())
        except Exception:
            pass
    return []


def load_allowed_models() -> list[str]:
    """Load the whitelist of allowed models from allowed_models.txt."""
    models_file = REPO_ROOT / "benchmark" / "harness" / "allowed_models.txt"
    if not models_file.exists():
        return []
    lines = models_file.read_text().splitlines()
    return [l.strip() for l in lines if l.strip() and not l.startswith("#")]


def oracle_score_from_leaderboard(leaderboard: list) -> float:
    """Read oracle weighted mean from the leaderboard entry (the metric miners compete on)."""
    for row in leaderboard:
        if row.get("agent") == "Oracle (accepted solution)":
            # Prefer weighted_score; fall back to score for backward compat
            ws = row.get("weighted_score")
            if ws is not None:
                return float(ws)
            if row.get("score") is not None:
                return float(row["score"])
    return ORACLE_ROW.get("weighted_score") or ORACLE_ROW["score"]


def main(out_path: str | None = None):
    problems = load_problems()
    leaderboard = load_leaderboard()
    history = load_history()
    allowed_models = load_allowed_models()

    by_repo: dict[str, int] = {}
    by_category: dict[str, int] = {}
    by_difficulty: dict[str, int] = {}
    for p in problems:
        by_repo[p["repo"]] = by_repo.get(p["repo"], 0) + 1
        by_category[p["category"]] = by_category.get(p["category"], 0) + 1
        by_difficulty[p["difficulty"]] = by_difficulty.get(p["difficulty"], 0) + 1

    oracle = oracle_score_from_leaderboard(leaderboard)

    data = {
        "generated_at": date.today().isoformat(),
        "pool_size": len(problems),
        "shard_size": 30,
        "shard_budget": SHARD_BUDGET,
        "oracle_score": oracle,
        "repos": by_repo,
        "categories": by_category,
        "difficulty_counts": by_difficulty,
        "leaderboard": leaderboard,
        "history": history,
        "allowed_models": allowed_models,
        "problems": problems,
    }

    dest = pathlib.Path(out_path) if out_path else pathlib.Path("docs/dashboard_data.json")
    json_str = json.dumps(data, indent=2)
    dest.write_text(json_str)
    print(f"Wrote {len(problems)} problems, {len(leaderboard)} leaderboard rows, "
          f"{len(history)} history entries to {dest}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("output", nargs="?", default=None, help="Output path for data.json")
    args = ap.parse_args()
    main(args.output)
