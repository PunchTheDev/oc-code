"""Generate data.json for the static dashboard from the current problem pool."""

import json
import pathlib
import sys
from datetime import date

# Repo root on sys.path so benchmark.catalog is importable when run directly.
_REPO_ROOT = pathlib.Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from benchmark.catalog import DEFAULT_SHARD_BUDGET, REPO_CATEGORY  # noqa: E402
from benchmark.evaluate import problem_difficulty  # noqa: E402


def _load_shard_budget() -> dict:
    """Read shard_budget from pool_config.json; fall back to catalog default."""
    cfg_path = pathlib.Path(__file__).parent.parent / "benchmark" / "pool_config.json"
    try:
        cfg = json.loads(cfg_path.read_text())
        budget = cfg.get("shard_budget")
        if isinstance(budget, dict) and budget:
            return budget
    except Exception:
        pass
    return DEFAULT_SHARD_BUDGET


SHARD_BUDGET = _load_shard_budget()


def repo_category(repo: str) -> str:
    """Return language category for a repo, lower-cased."""
    return REPO_CATEGORY.get(repo.lower(), REPO_CATEGORY.get(repo, "other"))

REPO_ROOT = _REPO_ROOT
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
        mean_score = 11.48
        weighted_score = 12.61
        count = 1154
    return {
        "rank": None,
        "agent": "Oracle (accepted solution)",
        "score": mean_score,
        "weighted_score": weighted_score,
        # benchmark_score and weighted_benchmark_score are always 1.0 for the oracle
        # (it defines the 1.0 baseline). Required for correct leaderboard sorting.
        "benchmark_score": 1.0,
        "weighted_benchmark_score": 1.0,
        "model": "—",
        "date": "—",
        "note": (
            f"Oracle baseline: weighted_benchmark_score=1.0 (definition). "
            f"Weighted mean {weighted_score} (arithmetic {mean_score}) across "
            f"{count} accepted solutions (DAS + external prestige repos)"
        ),
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
                "difficulty": problem_difficulty(p)[0],
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
    """Return oracle weighted mean score (miners' primary target metric)."""
    for row in leaderboard:
        if row.get("agent") == "Oracle (accepted solution)":
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
