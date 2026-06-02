"""Generate data.json for the static dashboard from the current problem pool."""

import json
import pathlib
import sys
from datetime import date

REPO_ROOT = pathlib.Path(__file__).parent.parent
PROBLEMS_DIR = REPO_ROOT / "benchmark" / "problems"
RESULTS_DIR = REPO_ROOT / "results"

ORACLE_ROW = {
    "rank": None,
    "agent": "Oracle (accepted solution)",
    "score": 22.77,
    "model": "—",
    "date": "—",
    "note": "Mean baseline (local heuristic)",
}


def load_baselines() -> dict[str, float]:
    """Load per-problem baseline scores from results/baselines.json."""
    baseline_file = RESULTS_DIR / "baselines.json"
    if not baseline_file.exists():
        return {}
    try:
        data = json.loads(baseline_file.read_text())
        return {p["id"]: p["base_score"] for p in data.get("problems", [])}
    except Exception:
        return {}


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
        problems.append(
            {
                "id": pid,
                "repo": repo,
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
                "baseline_score": baselines.get(pid),
                "test_cmd": meta.get("test_cmd") or [],
                "base_commit": meta.get("base_commit", ""),
                "pr_url": f"https://github.com/{repo}/pull/{pr}",
                "issue_url": f"https://github.com/{repo}/issues/{issue}" if issue else None,
            }
        )
    return problems


def load_leaderboard():
    """Load leaderboard from results/leaderboard.json, fall back to oracle-only."""
    lb_file = RESULTS_DIR / "leaderboard.json"
    if lb_file.exists():
        try:
            rows = json.loads(lb_file.read_text())
            # Ensure oracle row is always present at top
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


def main(out_path: str | None = None):
    problems = load_problems()
    leaderboard = load_leaderboard()
    history = load_history()

    by_repo: dict[str, int] = {}
    for p in problems:
        by_repo[p["repo"]] = by_repo.get(p["repo"], 0) + 1

    data = {
        "generated_at": date.today().isoformat(),
        "pool_size": len(problems),
        "shard_size": 30,
        "oracle_score": 22.77,
        "repos": by_repo,
        "leaderboard": leaderboard,
        "history": history,
        "problems": problems,
    }

    dest = pathlib.Path(out_path) if out_path else pathlib.Path("dashboard_data.json")
    dest.write_text(json.dumps(data, indent=2))
    print(f"Wrote {len(problems)} problems, {len(leaderboard)} leaderboard rows, "
          f"{len(history)} history entries to {dest}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
