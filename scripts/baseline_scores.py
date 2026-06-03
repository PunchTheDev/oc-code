"""
Score all reference diffs and write results/baselines.json.

Reference diffs are known-correct (merged PRs), so we skip the test-running
phase and score only on diff quality.

Scoring path (primary): tree-sitter AST scorer — same weights JSON used by
the DAS validator. Scores should closely match validator output.
Fallback: heuristic diff-token count (runs ~2× above DAS, used when
tree_sitter is not installed).

Baselines serve two purposes:
  1. Oracle mean: mean baseline across the pool = expected reference quality.
  2. Per-problem upper bound: a submission scoring above baseline on a
     problem either found a better fix or is gaming the scorer.

Usage:
    python scripts/baseline_scores.py [--out results/baselines.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PROBLEMS_DIR = REPO_ROOT / "benchmark" / "problems"
RESULTS_DIR = REPO_ROOT / "results"

sys.path.insert(0, str(REPO_ROOT))
from benchmark.harness.score import score_diff_quality
from benchmark.evaluate import problem_difficulty


def _count_added_lines(ref_path: Path) -> int:
    """Count lines starting with '+' (not '+++ ') in a unified diff."""
    return sum(
        1 for line in ref_path.read_text(errors="replace").splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )


def score_reference(problem_dir: Path) -> dict | None:
    meta_path = problem_dir / "meta.json"
    ref_path = problem_dir / "reference.diff"
    if not meta_path.exists() or not ref_path.exists():
        return None

    meta = json.loads(meta_path.read_text())

    try:
        src_tok, total_tok, base_score = score_diff_quality(problem_dir, ref_path)
    except Exception as e:
        print(f"  WARN: {problem_dir.name} — {e}", file=sys.stderr)
        return None

    added = _count_added_lines(ref_path)
    tier, weight = problem_difficulty(problem_dir)

    return {
        "id": meta["id"],
        "repo": meta.get("repo_name", ""),
        "pr": meta.get("pr_number"),
        "source_token_score": round(src_tok, 2),
        "total_token_score": round(total_tok, 2),
        "base_score": base_score,
        "added_lines": added,
        "difficulty": tier,
        "weight": weight,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Score all reference diffs")
    parser.add_argument("--out", default=str(RESULTS_DIR / "baselines.json"))
    parser.add_argument("--limit", type=int, default=0, help="Score only first N problems (0=all)")
    parser.add_argument("--incremental", action="store_true",
                        help="Only score problems not already in the output file; merge results")
    args = parser.parse_args()

    problems = sorted(p for p in PROBLEMS_DIR.iterdir() if p.is_dir())
    if args.limit:
        problems = problems[:args.limit]

    # Incremental mode: load existing scores and skip already-scored problems
    existing: dict[str, dict] = {}
    if args.incremental:
        dest_path = Path(args.out)
        if dest_path.exists():
            try:
                loaded = json.loads(dest_path.read_text())
                for entry in loaded.get("problems", []):
                    existing[entry["id"]] = entry
                print(f"Loaded {len(existing)} existing scores (incremental mode)")
            except Exception:
                pass

    baselines = list(existing.values()) if existing else []
    existing_ids = set(existing.keys())
    skipped = 0
    new_count = 0
    for i, problem_dir in enumerate(problems, 1):
        if problem_dir.name in existing_ids:
            continue
        print(f"[{i}/{len(problems)}] {problem_dir.name}", end="", flush=True)
        result = score_reference(problem_dir)
        if result is None:
            skipped += 1
            print(" SKIP")
            continue
        baselines.append(result)
        new_count += 1
        print(f" → {result['base_score']:.2f}")

    if not baselines:
        print("No problems scored.", file=sys.stderr)
        sys.exit(1)

    scores = [b["base_score"] for b in baselines]
    mean_score = round(sum(scores) / len(scores), 2)
    median_scores = sorted(scores)
    median_score = round(median_scores[len(median_scores) // 2], 2)

    # Weighted mean mirrors evaluate.py: hard×2, medium×1.5, easy×1
    w_total = w_count = 0.0
    for b in baselines:
        w = b.get("weight", 1.5)
        w_total += b["base_score"] * w
        w_count += w
    weighted_mean_score = round(w_total / w_count, 2) if w_count else mean_score

    out = {
        "count": len(baselines),
        "mean_score": mean_score,
        "weighted_mean_score": weighted_mean_score,
        "median_score": median_score,
        "max_score": round(max(scores), 2),
        "min_score": round(min(scores), 2),
        "scoring_method": "tree-sitter (Gittensor native) with heuristic fallback",
        "problems": baselines,
    }

    dest = Path(args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2))

    if args.incremental:
        print(f"\nAdded {new_count} new scores, {len(existing_ids)} carried over, {skipped} skipped")
    else:
        print(f"\nScored {len(baselines)} problems (skipped {skipped})")
    print(f"Mean: {mean_score:.2f} | Weighted mean: {weighted_mean_score:.2f} | "
          f"Median: {median_score:.2f} | Max: {out['max_score']:.2f} | Min: {out['min_score']:.2f}")
    print(f"Written to {dest}")


if __name__ == "__main__":
    main()
