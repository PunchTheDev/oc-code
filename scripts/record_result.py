"""Record a scored evaluation result into results/ for leaderboard + history tracking.

Usage:
    python scripts/record_result.py --results results.json --handle alice --model claude-3-5-haiku

Writes/updates:
  results/leaderboard.json  — ranked table, re-sorted after each addition
  results/history.json      — append-only SOTA-over-time log
"""

from __future__ import annotations

import argparse
import json
import pathlib
from datetime import date

REPO_ROOT = pathlib.Path(__file__).parent.parent
RESULTS_DIR = REPO_ROOT / "results"

ORACLE_ROW = {
    "rank": None,
    "agent": "Oracle (accepted solution)",
    "score": 22.76,
    "model": "—",
    "date": "—",
    "note": "Upper bound",
}


def load_json(path: pathlib.Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return default


def current_sota(leaderboard: list[dict]) -> float:
    """Best score among real (ranked) entries."""
    real = [r["score"] for r in leaderboard if r.get("rank") and r.get("score") is not None]
    return max(real) if real else 0.0


def update_leaderboard(leaderboard: list[dict], entry: dict) -> list[dict]:
    """Upsert by agent handle, re-rank by score descending."""
    handle = entry["agent"]
    # Remove existing entry for this handle
    rows = [r for r in leaderboard if r.get("rank") is None or r.get("agent") != handle]
    rows.append(entry)
    # Sort real entries by score descending
    oracle = [r for r in rows if r.get("rank") is None]
    real = sorted([r for r in rows if r.get("rank") is not None],
                  key=lambda r: r.get("score") or 0, reverse=True)
    for i, r in enumerate(real, 1):
        r["rank"] = i
    return oracle + real


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True, help="Path to evaluation results.json")
    ap.add_argument("--handle", required=True, help="Miner handle / agent name")
    ap.add_argument("--model", default="—", help="Model used by the agent")
    ap.add_argument("--note", default="", help="Optional note")
    args = ap.parse_args()

    results_path = pathlib.Path(args.results)
    if not results_path.exists():
        raise SystemExit(f"results file not found: {results_path}")

    results = json.loads(results_path.read_text())
    mean_score = results.get("mean_score")
    if mean_score is None:
        raise SystemExit("results.json missing mean_score field")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    lb_file = RESULTS_DIR / "leaderboard.json"
    hist_file = RESULTS_DIR / "history.json"

    leaderboard = load_json(lb_file, [ORACLE_ROW])
    history = load_json(hist_file, [])

    # Ensure oracle row present
    if not any(r.get("agent") == "Oracle (accepted solution)" for r in leaderboard):
        leaderboard.insert(0, ORACLE_ROW)

    today = date.today().isoformat()
    entry = {
        "rank": 1,  # placeholder — update_leaderboard will re-rank
        "agent": args.handle,
        "score": round(float(mean_score), 4),
        "model": args.model,
        "date": today,
        "note": args.note,
    }

    prev_sota = current_sota(leaderboard)
    leaderboard = update_leaderboard(leaderboard, entry)
    new_sota = current_sota(leaderboard)

    lb_file.write_text(json.dumps(leaderboard, indent=2))
    print(f"Leaderboard updated: {args.handle} scored {mean_score:.4f}")

    # Append to history if this beats or ties SOTA
    if new_sota >= prev_sota:
        hist_entry = {
            "date": today,
            "score": round(new_sota, 4),
            "agent": args.handle,
            "model": args.model,
        }
        history.append(hist_entry)
        hist_file.write_text(json.dumps(history, indent=2))
        if new_sota > prev_sota:
            print(f"New SOTA: {new_sota:.4f} (was {prev_sota:.4f})")
        else:
            print(f"SOTA unchanged at {new_sota:.4f}")
    else:
        print(f"Score {mean_score:.4f} below current SOTA {prev_sota:.4f} — history unchanged")


if __name__ == "__main__":
    main()
