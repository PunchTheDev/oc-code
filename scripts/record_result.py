"""Record a scored evaluation result into results/ for leaderboard + history tracking.

Usage:
    python scripts/record_result.py --results results.json --handle alice --model claude-3-5-haiku
    python scripts/record_result.py --results results.json --handle alice --behaviors behaviors.json

Writes/updates:
  results/leaderboard.json          — ranked table, re-sorted after each addition
  results/history.json              — append-only SOTA-over-time log
  results/behaviors/{handle}.json   — behavior fingerprint for future anti-copy checks (if --behaviors given)

Ranking metric: weighted_benchmark_score (PRIMARY — difficulty-weighted correctness × quality).
Falls back to weighted_mean_score for entries that predate the benchmark_score schema.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from datetime import date

REPO_ROOT = pathlib.Path(__file__).parent.parent
RESULTS_DIR = REPO_ROOT / "results"
COMMITMENTS_FILE = RESULTS_DIR / "commitments.json"


def _lookup_commitment(handle: str, agent_hash: str) -> dict | None:
    """Return the earliest commitment for (handle, agent_hash), or None."""
    if not COMMITMENTS_FILE.exists():
        return None
    try:
        store = json.loads(COMMITMENTS_FILE.read_text())
    except Exception:
        return None
    records = store.get(handle, [])
    matches = [r for r in records if r.get("agent_hash") == agent_hash]
    if not matches:
        return None
    return min(matches, key=lambda r: r.get("timestamp", float("inf")))


def _oracle_scores_from_baselines() -> tuple[float, float]:
    """Read oracle arithmetic and weighted mean from baselines.json."""
    baseline_file = RESULTS_DIR / "baselines.json"
    try:
        data = json.loads(baseline_file.read_text())
        mean = round(float(data["mean_score"]), 2)
        weighted = round(float(data.get("weighted_mean_score") or mean), 2)
        return mean, weighted
    except Exception:
        return 11.49, 12.64


_oracle_mean, _oracle_weighted = _oracle_scores_from_baselines()

ORACLE_ROW = {
    "rank": None,
    "agent": "Oracle (accepted solution)",
    "score": _oracle_mean,
    "weighted_score": _oracle_weighted,
    # benchmark_score and weighted_benchmark_score are always 1.0 for the oracle
    # — it defines the 1.0 baseline for the primary ranking metric.
    # test_quality_factor = 1.0 by definition (oracle matches its own assertions).
    "benchmark_score": 1.0,
    "weighted_benchmark_score": 1.0,
    "test_quality_factor": 1.0,
    "model": "—",
    "date": "—",
    "note": (
        f"Oracle baseline: weighted_benchmark_score=1.0 (definition). "
        f"Weighted mean {_oracle_weighted} (arithmetic {_oracle_mean}) across "
        f"accepted solutions (DAS + external prestige repos)"
    ),
}


def load_json(path: pathlib.Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return default


def primary_score(entry: dict) -> float:
    """Return the primary ranking metric for a leaderboard entry.

    weighted_benchmark_score is the canonical metric. Falls back to
    weighted_score (raw Gittensor formula) for entries that predate the
    benchmark_score schema (step 186+).
    """
    wbs = entry.get("weighted_benchmark_score")
    if wbs is not None and isinstance(wbs, (int, float)):
        return float(wbs)
    ws = entry.get("weighted_score") or entry.get("score")
    return float(ws) if ws is not None else 0.0


def current_sota(leaderboard: list[dict]) -> float:
    """Best primary score among real (ranked) entries."""
    real = [primary_score(r) for r in leaderboard if r.get("rank") is not None]
    return max((s for s in real if s > 0), default=0.0)


# Crown margin constants.
# To earn non-zero marginal gain a submission must beat SOTA by at least
# crown_threshold(sota). The required absolute margin decays linearly to zero
# as SOTA approaches the theoretical ceiling, so near the top even small
# genuine improvements are rewarded while LLM variance alone can't steal the
# crown when SOTA is low.
_CROWN_BASE_MARGIN = 0.02  # 2 pp required when SOTA is at zero
_CROWN_CEILING = 2.0       # theoretical max benchmark_score


def crown_threshold(sota: float) -> float:
    """Minimum score needed to earn any marginal gain.

    margin = BASE × (ceiling - sota) / ceiling
    At sota=0.0 → need +0.02; at sota=1.0 → need +0.01; at sota=1.9 → need +0.001.
    """
    margin = _CROWN_BASE_MARGIN * max(_CROWN_CEILING - sota, 0.0) / _CROWN_CEILING
    return sota + margin


def marginal_gain(score: float, sota: float) -> float:
    """Genuine score delta above the crown threshold; zero if below threshold.

    Submissions that copy the leader or beat it only via LLM variance earn
    zero marginal gain — their contribution_weight collapses to the
    participation term.
    """
    return max(0.0, score - crown_threshold(sota))


def contribution_weight(score: float, sota: float, champion_mult: float = 3.0, participation_mult: float = 1.0) -> float:
    """
    Emission weight for this submission.

    contribution_weight = (score × participation_mult
                          + marginal_gain(score, sota) × champion_mult)

    marginal_gain is zero unless the submission clears the decaying crown
    threshold, so a clone of the leader earns only the participation term.
    A genuine improvement above the threshold earns disproportionately more.
    Label multiplier and time decay are applied by the Gittensor validator
    on top of this weight.
    """
    return score * participation_mult + marginal_gain(score, sota) * champion_mult


def update_leaderboard(leaderboard: list[dict], entry: dict) -> list[dict]:
    """Upsert by agent handle, re-rank by weighted_benchmark_score descending."""
    handle = entry["agent"]
    rows = [r for r in leaderboard if r.get("rank") is None or r.get("agent") != handle]
    rows.append(entry)
    oracle = [r for r in rows if r.get("rank") is None]
    real = sorted(
        [r for r in rows if r.get("rank") is not None],
        key=primary_score,
        reverse=True,
    )
    for i, r in enumerate(real, 1):
        r["rank"] = i
    return oracle + real


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True, help="Path to evaluation results.json")
    ap.add_argument("--handle", required=True, help="Miner handle / agent name")
    ap.add_argument("--model", default="—", help="Model used by the agent")
    ap.add_argument("--note", default="", help="Optional note")
    ap.add_argument("--behaviors", metavar="FILE",
                    help="Behavior fingerprint JSON from --save-behaviors; saved to results/behaviors/ for future anti-copy checks")
    ap.add_argument("--agent-file", metavar="FILE",
                    help="Path to the agent.py being scored — used for commit-reveal hash verification")
    ap.add_argument("--pr-number", type=int, metavar="N",
                    help="GitHub PR number — stored so the leaderboard can link to the agent's source code")
    args = ap.parse_args()

    results_path = pathlib.Path(args.results)
    if not results_path.exists():
        raise SystemExit(f"results file not found: {results_path}")

    results = json.loads(results_path.read_text())
    mean_score = results.get("mean_score")
    if mean_score is None:
        raise SystemExit("results.json missing mean_score field")

    weighted_mean = results.get("weighted_mean_score", mean_score)
    benchmark_score = results.get("mean_benchmark_score")
    weighted_benchmark = results.get("weighted_benchmark_score")
    shard_week = results.get("shard_week")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    lb_file = RESULTS_DIR / "leaderboard.json"
    hist_file = RESULTS_DIR / "history.json"

    leaderboard = load_json(lb_file, [ORACLE_ROW])
    history = load_json(hist_file, [])

    if not any(r.get("agent") == "Oracle (accepted solution)" for r in leaderboard):
        leaderboard.insert(0, ORACLE_ROW)

    today = date.today().isoformat()

    raw_problems = results.get("problems", [])
    breakdown = [
        {
            "problem_id": p.get("problem_id", ""),
            "score": round(float(p.get("final_score", 0.0)), 4),
            "benchmark_score": round(float(p.get("benchmark_score", 0.0)), 4) if p.get("benchmark_score") is not None else None,
            "test_pass_rate": round(float(p.get("test_pass_rate", 0.0)), 4) if p.get("test_pass_rate") is not None else None,
            "test_quality_factor": round(float(p.get("test_quality_factor", 1.0)), 4) if p.get("test_quality_factor") is not None else None,
            "efficiency_factor": round(float(p.get("efficiency_factor", 1.0)), 4) if p.get("efficiency_factor") is not None else None,
            "tokens_used": int(p.get("tokens_used", 0)),
            "passed": bool(p.get("tests_passed", False)),
            "category": p.get("category", ""),
            "difficulty": p.get("difficulty", ""),
        }
        for p in raw_problems
    ]

    entry: dict = {
        "rank": 1,  # placeholder — update_leaderboard will re-rank
        "agent": args.handle,
        "score": round(float(mean_score), 4),
        "weighted_score": round(float(weighted_mean), 4),
        "model": args.model,
        "date": today,
        "note": args.note,
        "breakdown": breakdown,
    }

    if benchmark_score is not None:
        entry["benchmark_score"] = round(float(benchmark_score), 4)
    if weighted_benchmark is not None:
        entry["weighted_benchmark_score"] = round(float(weighted_benchmark), 4)
    if shard_week is not None:
        entry["shard_week"] = int(shard_week)

    # Link back to source code for flywheel: champion code gets open-sourced
    repo_base = "https://github.com/PunchTheDev/gittensor-base-miner"
    if args.pr_number:
        entry["pr_url"] = f"{repo_base}/pull/{args.pr_number}"
        entry["agent_code_url"] = f"{repo_base}/blob/main/agent/submissions/{args.handle}/agent.py"

    # Aggregate token efficiency across all problems
    entry["total_tokens_used"] = sum(b["tokens_used"] for b in breakdown)
    if breakdown:
        entry["avg_efficiency_factor"] = round(
            sum(b["efficiency_factor"] if b["efficiency_factor"] is not None else 1.0 for b in breakdown)
            / len(breakdown),
            4,
        )
    else:
        entry["avg_efficiency_factor"] = 1.0

    # Commit-reveal: check for a pre-PR hash commitment
    if args.agent_file:
        agent_path = pathlib.Path(args.agent_file)
        if agent_path.exists():
            agent_hash = hashlib.sha256(agent_path.read_bytes()).hexdigest()
            commitment = _lookup_commitment(args.handle, agent_hash)
            if commitment:
                entry["commit_hash"] = agent_hash
                entry["commit_timestamp"] = commitment["iso"]
                print(f"  Commit-reveal: commitment found at {commitment['iso']} (hash {agent_hash[:12]}…)")
            else:
                entry["commit_hash"] = agent_hash
                entry["commit_timestamp"] = None
                print(f"  Commit-reveal: no pre-PR commitment found for hash {agent_hash[:12]}… — submission unverified")
        else:
            print(f"  WARNING: --agent-file not found: {agent_path}")

    prev_sota = current_sota(leaderboard)
    my_primary = primary_score(entry)
    threshold = crown_threshold(prev_sota)
    gain = marginal_gain(my_primary, prev_sota)
    weight = contribution_weight(my_primary, prev_sota)

    entry["sota_at_submission"] = round(prev_sota, 4)
    entry["crown_threshold"] = round(threshold, 4)
    entry["marginal_gain"] = round(gain, 4)
    entry["contribution_weight"] = round(weight, 4)

    leaderboard = update_leaderboard(leaderboard, entry)
    new_sota = current_sota(leaderboard)

    lb_file.write_text(json.dumps(leaderboard, indent=2))

    # Append to per-agent submission history (all submissions, never replaced)
    agent_dir = RESULTS_DIR / "agents" / args.handle
    agent_dir.mkdir(parents=True, exist_ok=True)
    agent_hist_file = agent_dir / "history.json"
    agent_history = load_json(agent_hist_file, [])
    agent_entry = {k: v for k, v in entry.items() if k != "rank"}
    agent_history.append(agent_entry)
    agent_hist_file.write_text(json.dumps(agent_history, indent=2))

    wbs_str = f" / weighted_benchmark={weighted_benchmark:.4f}" if weighted_benchmark is not None else ""
    print(f"Leaderboard updated: {args.handle} scored weighted={weighted_mean:.4f}{wbs_str} / arithmetic={mean_score:.4f}")
    print(f"  SOTA at submission: {prev_sota:.4f}  |  marginal gain: {gain:.4f}  |  weight: {weight:.4f}")
    print(f"  Agent history: {len(agent_history)} submission(s) saved to {agent_hist_file}")

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
        print(f"Primary score {my_primary:.4f} below current SOTA {prev_sota:.4f} — history unchanged")

    if args.behaviors:
        behaviors_path = pathlib.Path(args.behaviors)
        if behaviors_path.exists():
            behaviors_dir = RESULTS_DIR / "behaviors"
            behaviors_dir.mkdir(parents=True, exist_ok=True)
            dest = behaviors_dir / f"{args.handle}.json"
            dest.write_text(behaviors_path.read_text())
            print(f"Behavior fingerprint saved: {dest}")
        else:
            print(f"WARNING: --behaviors file not found: {behaviors_path} — skipping fingerprint save")


if __name__ == "__main__":
    main()
