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
import hashlib
import importlib.util
import json
import os
import random
import sys
import time
from datetime import date, timedelta
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent
POOL_DIR = Path(__file__).parent / "problems"
POOL_CONFIG_PATH = Path(__file__).parent / "pool_config.json"


def load_pool_config() -> dict:
    if POOL_CONFIG_PATH.exists():
        return json.loads(POOL_CONFIG_PATH.read_text())
    return {"shard_size": 30, "rotation_policy": "weekly", "rotation_seed": 42}


def select_shard(all_problem_dirs: list[Path], config: dict) -> list[Path]:
    """Pick a deterministic shard from the pool according to rotation policy."""
    shard_size = config.get("shard_size", 30)
    policy = config.get("rotation_policy", "weekly")
    base_seed = config.get("rotation_seed", 42)

    if shard_size >= len(all_problem_dirs):
        return all_problem_dirs

    if policy == "fixed":
        seed = base_seed
    elif policy == "weekly":
        # Week number since epoch — changes every 7 days
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
    pool = list(all_problem_dirs)
    rng.shuffle(pool)
    return sorted(pool[:shard_size])


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


def run_evaluation(
    agent_path: str | None = None,
    problem_ids: list[str] | None = None,
    use_sandbox: bool = True,
    use_all: bool = False,
    use_oracle: bool = False,
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
    # Used for pipeline calibration; expected mean is ~22.76 (the stored oracle baseline).
    if use_oracle:
        print("Oracle mode: scoring reference diffs to verify pipeline calibration.")
        print(f"Expected mean: ~22.76 / 30.00 (stored oracle baseline)\n")
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

        total = sum(r["final_score"] for r in results)
        mean = total / len(results) if results else 0.0
        return {
            "mean_score": round(mean, 4),
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

    results = []
    for problem_dir in selected:
        problem = load_problem(problem_dir)

        print(f"  [{problem.id}] {problem.issue_title[:60]}...")
        start = time.time()
        try:
            patch = agent.solve(problem)
            elapsed = time.time() - start

            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".diff", mode="w", delete=False) as f:
                f.write(patch.diff)
                patch_path = Path(f.name)

            if not use_sandbox:
                from benchmark.harness.score import score_patch
                score = score_patch(problem_dir, patch_path)
            else:
                from benchmark.harness.runner import run_in_sandbox
                score = run_in_sandbox(problem_dir, patch_path)
            patch_path.unlink()

            score["elapsed_seconds"] = round(elapsed, 2)
            results.append(score)
            status = "PASS" if score.get("tests_passed") else "FAIL"
            print(f"       {status}  final_score={score['final_score']}  ({elapsed:.1f}s)")

        except Exception as e:
            elapsed = time.time() - start
            results.append({
                "problem_id": problem.id,
                "error": str(e),
                "final_score": 0.0,
                "elapsed_seconds": round(elapsed, 2),
            })
            print(f"       ERROR: {e}")

    total = sum(r["final_score"] for r in results)
    mean = total / len(results) if results else 0.0
    return {
        "mean_score": round(mean, 4),
        "problems_evaluated": len(results),
        "pool_size": len(all_problem_dirs),
        "shard_size": len(selected),
        "rotation_policy": config.get("rotation_policy", "weekly"),
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
    parser.add_argument("--no-sandbox", action="store_true",
                        help="Skip Docker sandbox (local dev mode)")
    parser.add_argument("--oracle", action="store_true",
                        help="Score reference diffs (calibration check, no agent needed)")
    args = parser.parse_args()

    if args.list_shard:
        all_dirs = sorted(POOL_DIR.glob("*/meta.json"))
        shard = select_shard([p.parent for p in all_dirs], config)
        print(f"Current shard ({config.get('rotation_policy', 'weekly')}, "
              f"{len(shard)}/{len(all_dirs)} problems):")
        for d in shard:
            meta = json.loads((d / "meta.json").read_text())
            print(f"  {d.name:30s}  {meta['repo_name']}  #{meta['pr_number']}")
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
    )

    pool_info = f"{results['shard_size']}/{results['pool_size']} problems"
    print(f"\nMean score: {results['mean_score']} ({pool_info})")

    if args.output:
        Path(args.output).write_text(json.dumps(results, indent=2))
        print(f"Results written to {args.output}")

    sys.exit(0 if results["mean_score"] > 0 else 1)


if __name__ == "__main__":
    main()
