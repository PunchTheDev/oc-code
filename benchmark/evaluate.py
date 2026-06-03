"""
Main evaluation entry point for the Gittensor Base-Miner Benchmark.

Runs an agent against a shard (or all) benchmark problems and reports scores.

Shard selection pulls from the full pool in benchmark/problems/ according to
pool_config.json. By default the current weekly shard is used — the same 30
problems every CI run in a given week, rotating automatically.

Usage:
    # Score against the current weekly shard (default, matches CI)
    python benchmark/evaluate.py --agent agent/example/agent.py

    # Score against every problem in the pool
    python benchmark/evaluate.py --agent agent/example/agent.py --all

    # Score against specific problem IDs
    python benchmark/evaluate.py --agent agent/example/agent.py --problems 1033,1034

    # Score without Docker sandbox (local dev)
    python benchmark/evaluate.py --agent agent/example/agent.py --no-sandbox

    # Print the current shard IDs without running
    python benchmark/evaluate.py --list-shard
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import os
import random
import sys
import tempfile
import threading
import time
from datetime import date
from pathlib import Path

from benchmark.catalog import DIFFICULTY_TIERS, DEFAULT_SHARD_BUDGET, REPO_CATEGORY


REPO_ROOT = Path(__file__).parent.parent
POOL_DIR = Path(__file__).parent / "problems"
POOL_CONFIG_PATH = Path(__file__).parent / "pool_config.json"


def problem_difficulty(problem_dir: Path) -> tuple[str, float]:
    """Return (tier_name, weight) for a problem based on reference diff size."""
    ref = problem_dir / "reference.diff"
    if not ref.exists():
        return "medium", 1.5

    added = sum(
        1 for line in ref.read_text(errors="replace").splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    for name, threshold, weight in DIFFICULTY_TIERS:
        if threshold is None or added < threshold:
            return name, weight
    return "hard", 2.0


def _problem_category(problem_dir: Path) -> str:
    """Return the language category for a problem, based on its repo."""
    try:
        meta = json.loads((problem_dir / "meta.json").read_text())
        repo = meta.get("repo_name", "").lower()
        return REPO_CATEGORY.get(repo, "python")
    except Exception:
        return "python"


def _diff_hash(diff_text: str) -> str:
    """Return a stable SHA-256 of the normalized diff.

    Strips trailing whitespace from each line and sorts hunks by file path so
    minor formatting differences don't produce different hashes for the same
    logical change.
    """
    lines = [ln.rstrip() for ln in diff_text.splitlines()]
    normalized = "\n".join(lines).strip()
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def load_pool_config() -> dict:
    if POOL_CONFIG_PATH.exists():
        return json.loads(POOL_CONFIG_PATH.read_text())
    return {"shard_size": 30, "rotation_policy": "weekly", "rotation_seed": 42}


def _sample_difficulty_balanced(pool: list[Path], n: int) -> list[Path]:
    """Sample n problems from pool, proportionally balanced across difficulty tiers.

    Within each tier (hard/medium/easy), samples proportionally to the tier's
    share of the pool. Hard problems are prioritised in tie-breaking so every
    shard is guaranteed to include challenging problems.

    The pool must be pre-shuffled by the caller for randomness.
    """
    if n <= 0:
        return []
    if n >= len(pool):
        return pool[:]

    # Sub-group by difficulty; pool is already shuffled by the caller.
    by_tier: dict[str, list[Path]] = {}
    for d in pool:
        tier, _ = problem_difficulty(d)
        by_tier.setdefault(tier, []).append(d)

    total = len(pool)
    # Prioritise hard → medium → easy so the last partial slot goes to hard problems.
    tier_order = [t for t in ("hard", "medium", "easy") if t in by_tier]

    selected: list[Path] = []
    remaining = n

    for i, tier in enumerate(tier_order):
        tier_pool = by_tier[tier]
        if i == len(tier_order) - 1:
            # Last tier absorbs any rounding remainder.
            want = remaining
        else:
            want = round(n * len(tier_pool) / total)
        take = min(want, len(tier_pool), remaining)
        selected.extend(tier_pool[:take])
        remaining -= take
        if remaining == 0:
            break

    return selected


def select_shard(all_problem_dirs: list[Path], config: dict) -> list[Path]:
    """Pick a deterministic, category- and difficulty-balanced shard from the pool.

    Problems are first grouped by language category and sampled according to
    shard_budget (from pool_config.json, or DEFAULT_SHARD_BUDGET). Within each
    category bucket, problems are further sampled proportionally across difficulty
    tiers (hard/medium/easy) so every shard contains a realistic spread.

    If a category has fewer problems than its budget, the remainder is
    redistributed to other categories proportionally.
    """
    shard_size = config.get("shard_size", 30)
    policy = config.get("rotation_policy", "weekly")
    base_seed = config.get("rotation_seed", 42)
    budget = config.get("shard_budget", DEFAULT_SHARD_BUDGET)

    if shard_size >= len(all_problem_dirs):
        return all_problem_dirs

    if policy == "fixed":
        seed = base_seed
    elif policy == "weekly":
        epoch = date(2024, 1, 1)
        week_number = (date.today() - epoch).days // 7
        seed = base_seed ^ week_number
    else:  # per_eval
        seed = random.randint(0, 2**32)

    # CI anti-gaming: SHARD_SECRET env var (GitHub secret) XORs into the seed
    # so miners cannot predict the evaluated shard from public parameters alone.
    secret = os.environ.get("SHARD_SECRET", "")
    if secret:
        secret_int = int(hashlib.sha256(secret.encode()).hexdigest()[:8], 16)
        seed ^= secret_int

    rng = random.Random(seed)

    # Group and shuffle each category bucket independently.
    by_category: dict[str, list[Path]] = {}
    for d in all_problem_dirs:
        cat = _problem_category(d)
        by_category.setdefault(cat, []).append(d)
    for cat in by_category:
        rng.shuffle(by_category[cat])

    # First pass: take up to budget from each budgeted category,
    # sampling difficulty-proportionally within each bucket.
    selected: list[Path] = []
    cats = list(budget.keys())
    taken: dict[str, int] = {}
    shortfall = 0
    for cat in cats:
        pool = by_category.get(cat, [])
        want = budget.get(cat, 0)
        take = min(want, len(pool))
        selected.extend(_sample_difficulty_balanced(pool, take))
        taken[cat] = take
        shortfall += want - take

    # Second pass: fill any shortfall from remaining problems in over-budget cats.
    if shortfall > 0:
        for cat in cats:
            pool = by_category.get(cat, [])
            extras = pool[taken[cat]:]
            if extras:
                give = min(shortfall, len(extras))
                selected.extend(_sample_difficulty_balanced(extras, give))
                shortfall -= give
                if shortfall == 0:
                    break

    # Final pass: pick up any "other" category problems if still short.
    if shortfall > 0:
        others = by_category.get("other", [])
        if others:
            selected.extend(others[:shortfall])

    return sorted(selected[:shard_size])


def load_agent(agent_path: str):
    spec = importlib.util.spec_from_file_location("submission", agent_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    from agent.base import BaseAgent
    for name in dir(module):
        obj = getattr(module, name)
        try:
            if isinstance(obj, type) and issubclass(obj, BaseAgent) and obj is not BaseAgent:
                return obj()
        except TypeError:
            pass

    raise ValueError(f"No BaseAgent subclass found in {agent_path}")


def load_problem(problem_dir: Path):
    from agent.base import FileContext, Problem

    meta = json.loads((problem_dir / "meta.json").read_text())
    context_files = []
    context_dir = problem_dir / "context"
    if context_dir.exists():
        for f in sorted(context_dir.rglob("*")):
            if f.is_file():
                rel = f.relative_to(context_dir)
                ext = f.suffix.lstrip(".")
                context_files.append(FileContext(
                    path=str(rel),
                    content=f.read_text(errors="replace"),
                    language=ext,
                ))

    allowed_models_path = Path(__file__).parent / "harness" / "allowed_models.txt"
    allowed_models = [
        line.strip() for line in allowed_models_path.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]

    return Problem(
        id=meta["id"],
        issue_title=meta["issue_title"],
        issue_body=meta["issue_body"],
        repo_name=meta["repo_name"],
        base_commit=meta["base_commit"],
        context_files=context_files,
        file_tree=meta.get("file_tree", []),
        test_cmd=meta.get("test_cmd", []),
        allowed_models=allowed_models,
        time_limit_seconds=meta.get("time_limit_seconds", 120),
        output_token_budget=meta.get("output_token_budget", 50_000),
    )


def _annotate_and_aggregate(results: list[dict], selected: list[Path]) -> dict:
    """Annotate each result with difficulty/category and return aggregate metrics.

    Mutates result dicts in-place (adds difficulty, difficulty_weight, category).
    Returns a dict of aggregate metrics suitable for merging into the eval output.
    """
    mean = sum(r["final_score"] for r in results) / len(results) if results else 0.0

    weighted_total = weighted_count = 0.0
    rel_total = rel_count = 0
    bench_total = bench_count = 0
    bench_weighted_total = bench_weighted_count = 0.0

    for r, d in zip(results, selected):
        tier, w = problem_difficulty(d)
        r["difficulty"] = tier
        r["difficulty_weight"] = w
        r["category"] = _problem_category(d)
        weighted_total += r["final_score"] * w
        weighted_count += w
        rel = r.get("relative_score")
        if rel is not None and isinstance(rel, (int, float)):
            rel_total += rel
            rel_count += 1
        bench = r.get("benchmark_score")
        if bench is not None and isinstance(bench, (int, float)):
            bench_total += bench
            bench_count += 1
            bench_weighted_total += bench * w
            bench_weighted_count += w

    return {
        "mean_score": round(mean, 4),
        "weighted_mean_score": round(weighted_total / weighted_count, 4) if weighted_count else 0.0,
        "mean_relative_score": round(rel_total / rel_count, 4) if rel_count else None,
        "mean_benchmark_score": round(bench_total / bench_count, 4) if bench_count else None,
        # PRIMARY ranking metric: difficulty-weighted (hard×2 / medium×1.5 / easy×1).
        "weighted_benchmark_score": round(bench_weighted_total / bench_weighted_count, 4) if bench_weighted_count else None,
    }


_print_lock = threading.Lock()


def _solve_with_timeout(agent, problem, timeout_seconds: int):
    """Call agent.solve() with a hard per-problem timeout.

    Returns the Patch on success. Raises concurrent.futures.TimeoutError if the
    agent does not return within timeout_seconds. The underlying thread may
    continue running (Python can't forcibly kill threads), but the caller
    receives control immediately so other problems can proceed.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(agent.solve, problem).result(timeout=timeout_seconds)


def _score_one_problem(
    idx: int,
    problem_dir: Path,
    agent,
    use_sandbox: bool,
    solve_timeout: int,
) -> tuple[int, dict]:
    """Score a single problem and return (original_index, result_dict).

    Isolated so it can run in a thread pool alongside other problems.
    Logs a one-line summary to stdout under a lock to prevent interleaving.
    """
    problem = load_problem(problem_dir)
    pid = problem.id
    start = time.time()

    try:
        patch = _solve_with_timeout(agent, problem, solve_timeout)
        elapsed = time.time() - start

        with tempfile.NamedTemporaryFile(suffix=".diff", mode="w", delete=False) as f:
            f.write(patch.diff)
            patch_path = Path(f.name)

        try:
            if not use_sandbox:
                from benchmark.harness.score import score_patch
                score = score_patch(problem_dir, patch_path)
            else:
                from benchmark.harness.runner import run_in_sandbox
                score = run_in_sandbox(problem_dir, patch_path)

            score["diff_hash"] = _diff_hash(patch.diff)
        finally:
            patch_path.unlink(missing_ok=True)

        score["elapsed_seconds"] = round(elapsed, 2)

        status = "PASS" if score.get("tests_passed") else "FAIL"
        rel = score.get("relative_score")
        rel_str = f"  rel={rel:.2f}" if rel is not None else ""
        with _print_lock:
            print(f"  [{pid}] {status}  score={score['final_score']:.2f}{rel_str}  ({elapsed:.1f}s)")

        return idx, score

    except concurrent.futures.TimeoutError:
        elapsed = time.time() - start
        with _print_lock:
            print(f"  [{pid}] TIMEOUT  agent.solve exceeded {solve_timeout}s")
        return idx, {
            "problem_id": pid,
            "error": f"agent.solve() timed out after {solve_timeout}s",
            "final_score": 0.0,
            "relative_score": 0.0,
            "benchmark_score": 0.0,
            "elapsed_seconds": round(elapsed, 2),
            "timed_out": True,
        }
    except Exception as e:
        elapsed = time.time() - start
        with _print_lock:
            print(f"  [{pid}] ERROR  {e}")
        return idx, {
            "problem_id": pid,
            "error": str(e),
            "final_score": 0.0,
            "relative_score": 0.0,
            "benchmark_score": 0.0,
            "elapsed_seconds": round(elapsed, 2),
        }


def run_evaluation(
    agent_path: str | None = None,
    problem_ids: list[str] | None = None,
    use_sandbox: bool = True,
    use_all: bool = False,
    use_oracle: bool = False,
    workers: int = 4,
) -> dict:
    config = load_pool_config()
    all_problem_dirs = sorted(POOL_DIR.glob("*/meta.json"))
    if not all_problem_dirs:
        print("No problems found. Run scripts/build_pool.py to populate benchmark/problems/")
        sys.exit(1)

    all_problem_dirs = [p.parent for p in all_problem_dirs]

    if problem_ids:
        selected = [d for d in all_problem_dirs if d.name in problem_ids]
    elif use_all:
        selected = all_problem_dirs
    else:
        selected = select_shard(all_problem_dirs, config)

    # Oracle mode: score reference diffs directly — no agent call needed.
    # Used for pipeline calibration; expected weighted mean matches baselines.json.
    if use_oracle:
        _oracle_weighted = 12.70
        _oracle_arithmetic = 11.48
        _baselines_path = Path(__file__).parent.parent / "results" / "baselines.json"
        if _baselines_path.exists():
            try:
                _b = json.loads(_baselines_path.read_text())
                _oracle_weighted = _b.get("weighted_mean_score", _oracle_weighted)
                _oracle_arithmetic = _b.get("mean_score", _oracle_arithmetic)
            except Exception:
                pass
        print("Oracle mode: scoring reference diffs to verify pipeline calibration.")
        print(f"Expected weighted mean: ~{_oracle_weighted:.2f} / 30.00  (arithmetic: ~{_oracle_arithmetic:.2f})\n")
        results = []
        for problem_dir in selected:
            ref_diff = problem_dir / "reference.diff"
            meta = json.loads((problem_dir / "meta.json").read_text())
            pid = meta["id"]
            print(f"  [{pid}] {meta['issue_title'][:60]}...")
            if not ref_diff.exists():
                results.append({
                    "problem_id": pid,
                    "error": "reference.diff missing",
                    "final_score": 0.0,
                    "elapsed_seconds": 0.0,
                })
                print(f"       SKIP  (no reference.diff)")
                continue
            try:
                if not use_sandbox:
                    from benchmark.harness.score import score_patch
                    score = score_patch(problem_dir, ref_diff)
                else:
                    from benchmark.harness.runner import run_in_sandbox
                    score = run_in_sandbox(problem_dir, ref_diff)
                results.append(score)
                status = "PASS" if score.get("tests_passed") else "FAIL"
                print(f"       {status}  final_score={score['final_score']}")
            except Exception as e:
                results.append({
                    "problem_id": pid,
                    "error": str(e),
                    "final_score": 0.0,
                    "elapsed_seconds": 0.0,
                })
                print(f"       ERROR: {e}")

        agg = _annotate_and_aggregate(results, selected)
        return {
            **agg,
            "problems_evaluated": len(results),
            "pool_size": len(all_problem_dirs),
            "shard_size": len(selected),
            "rotation_policy": config.get("rotation_policy", "weekly"),
            "oracle_mode": True,
            "problems": results,
        }

    if not agent_path:
        print("Error: --agent is required unless using --oracle", file=sys.stderr)
        sys.exit(1)

    agent = load_agent(agent_path)

    # Default solve_timeout: from meta.json time_limit_seconds (120s) plus a
    # generous buffer for model API latency. Callers can override via workers.
    # Docker sandbox enforces its own time_limit separately; this timeout guards
    # against agent.solve() hanging before the sandbox even starts.
    solve_timeout = int(os.environ.get("SOLVE_TIMEOUT", "300"))

    # --no-sandbox mode shares a repo cache directory; concurrent git operations
    # on the same repo can conflict. Warn and clamp workers=1 for safety.
    effective_workers = workers
    if not use_sandbox and workers > 1:
        print(
            f"  [warn] --no-sandbox uses a shared repo cache; "
            f"forcing workers=1 to avoid git conflicts."
        )
        effective_workers = 1

    print(f"  Scoring {len(selected)} problems  [workers={effective_workers}, solve_timeout={solve_timeout}s]")

    # Run problems in parallel; collect (original_index, result) to preserve order.
    indexed_results: list[tuple[int, dict]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=effective_workers) as pool:
        futures = {
            pool.submit(_score_one_problem, idx, d, agent, use_sandbox, solve_timeout): idx
            for idx, d in enumerate(selected)
        }
        for future in concurrent.futures.as_completed(futures):
            try:
                idx, result = future.result()
            except Exception as e:
                idx = futures[future]
                meta = json.loads((selected[idx] / "meta.json").read_text())
                with _print_lock:
                    print(f"  [{meta['id']}] FATAL  {e}")
                result = {
                    "problem_id": meta["id"],
                    "error": str(e),
                    "final_score": 0.0,
                    "relative_score": 0.0,
                    "benchmark_score": 0.0,
                    "elapsed_seconds": 0.0,
                }
            indexed_results.append((idx, result))

    # Restore original shard order so _annotate_and_aggregate's zip is correct.
    indexed_results.sort(key=lambda x: x[0])
    results = [r for _, r in indexed_results]

    agg = _annotate_and_aggregate(results, selected)
    return {
        **agg,
        "problems_evaluated": len(results),
        "pool_size": len(all_problem_dirs),
        "shard_size": len(selected),
        "rotation_policy": config.get("rotation_policy", "weekly"),
        "workers": effective_workers,
        "problems": results,
    }


def main() -> None:
    config = load_pool_config()
    parser = argparse.ArgumentParser(description="Evaluate an agent on the base-miner benchmark")
    parser.add_argument("--agent", help="Path to agent .py file")
    parser.add_argument("--problems", help="Comma-separated problem IDs (overrides shard)")
    parser.add_argument("--all", action="store_true", help="Run all problems in the pool")
    parser.add_argument("--list-shard", action="store_true",
                        help="Print the current shard IDs and exit")
    parser.add_argument("--output", help="Write JSON results to this file")
    parser.add_argument("--save-behaviors", metavar="FILE",
                        help="Write behavior fingerprint (per-problem diff hashes) to FILE")
    parser.add_argument("--no-sandbox", action="store_true",
                        help="Skip Docker sandbox (local dev mode)")
    parser.add_argument("--oracle", action="store_true",
                        help="Score reference diffs (calibration check, no agent needed)")
    parser.add_argument("--workers", type=int, default=4,
                        help="Parallel problem workers (default: 4; use 1 for sequential)")
    args = parser.parse_args()

    if args.list_shard:
        all_dirs = sorted(POOL_DIR.glob("*/meta.json"))
        shard = select_shard([p.parent for p in all_dirs], config)
        by_cat: dict[str, int] = {}
        for d in shard:
            cat = _problem_category(d)
            by_cat[cat] = by_cat.get(cat, 0) + 1
        cat_summary = "  ".join(f"{c}:{n}" for c, n in sorted(by_cat.items()))
        print(f"Current shard ({config.get('rotation_policy', 'weekly')}, "
              f"{len(shard)}/{len(all_dirs)} problems)  [{cat_summary}]:")
        for d in shard:
            meta = json.loads((d / "meta.json").read_text())
            cat = _problem_category(d)
            print(f"  {d.name:30s}  [{cat:12s}]  {meta['repo_name']}  #{meta['pr_number']}")
        return

    if not args.oracle and not args.agent:
        parser.error("--agent is required unless using --oracle or --list-shard")

    problem_ids = args.problems.split(",") if args.problems else None

    label = "oracle (reference diffs)" if args.oracle else args.agent
    print(f"Evaluating: {label}")
    results = run_evaluation(
        agent_path=args.agent,
        problem_ids=problem_ids,
        use_sandbox=not args.no_sandbox,
        use_all=args.all,
        use_oracle=args.oracle,
        workers=args.workers,
    )

    pool_info = f"{results['shard_size']}/{results['pool_size']} problems"
    wbench = results.get("weighted_benchmark_score")
    bench = results.get("mean_benchmark_score")
    if wbench is not None:
        pct = round(wbench * 100, 1)
        print(f"\nWeighted benchmark:  {wbench}  ({pct}% — PRIMARY: difficulty-weighted test_pass_rate × quality/oracle)")
    if bench is not None:
        pct = round(bench * 100, 1)
        print(f"Benchmark score:     {bench}  ({pct}% — arithmetic mean benchmark_score)")
    print(f"Mean score:          {results['mean_score']} ({pool_info})")
    print(f"Weighted mean score: {results['weighted_mean_score']} (easy×1 / medium×1.5 / hard×2)")
    rel = results.get("mean_relative_score")
    if rel is not None:
        pct = round(rel * 100, 1)
        print(f"Relative score:      {rel}  ({pct}% of oracle — 1.0 = matches accepted solution)")

    if args.output:
        Path(args.output).write_text(json.dumps(results, indent=2))
        print(f"Results written to {args.output}")

    if args.save_behaviors and not args.oracle:
        handle = Path(args.agent).parent.name if args.agent else "unknown"
        diffs = {
            r["problem_id"]: r.get("diff_hash", "")
            for r in results.get("problems", [])
            if "diff_hash" in r
        }
        fingerprint = {
            "handle": handle,
            "eval_date": date.today().isoformat(),
            "shard": [r["problem_id"] for r in results.get("problems", [])],
            "diffs": diffs,
        }
        Path(args.save_behaviors).write_text(json.dumps(fingerprint, indent=2))
        print(f"Behavior fingerprint written to {args.save_behaviors}")

    sys.exit(0 if results["mean_score"] > 0 else 1)


if __name__ == "__main__":
    main()
