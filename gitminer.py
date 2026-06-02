#!/usr/bin/env python3
"""
gitminer — CLI for the Gittensor Base-Miner Benchmark.

Subcommands:
    eval     Score an agent against the current shard (or all problems)
    cache    Pre-warm the local repo cache (speeds up --no-sandbox evals)
    hash     Compute the commit-reveal SHA-256 hash for a patch file
    shard    Print the current week's 30-problem shard IDs
    submit   Validate an agent, generate its commit-reveal hash, and print (or open) a PR

Usage:
    python gitminer.py eval agent/submissions/myhandle/agent.py
    python gitminer.py eval agent/submissions/myhandle/agent.py --no-sandbox
    python gitminer.py eval agent/submissions/myhandle/agent.py --all
    python gitminer.py eval agent/submissions/myhandle/agent.py --problems 930,986
    python gitminer.py cache
    python gitminer.py hash my_patch.diff
    python gitminer.py shard
    python gitminer.py submit agent/submissions/myhandle/agent.py
    python gitminer.py submit agent/submissions/myhandle/agent.py --model claude-3-5-haiku-20241022 --open-pr
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).parent
sys.path.insert(0, str(REPO_ROOT))


def _oracle_mean() -> float:
    """Read the oracle (reference-diff baseline) mean from leaderboard.json."""
    try:
        lb = json.loads((REPO_ROOT / "results" / "leaderboard.json").read_text())
        oracle = next((r for r in lb if r.get("handle") == "oracle"), None)
        if oracle:
            return float(oracle.get("mean_score", 22.79))
    except Exception:
        pass
    return 22.79  # fallback


def cmd_eval(args: argparse.Namespace) -> None:
    from benchmark.evaluate import run_evaluation

    problem_ids = args.problems.split(",") if args.problems else None
    results = run_evaluation(
        agent_path=args.agent,
        problem_ids=problem_ids,
        use_sandbox=not args.no_sandbox,
        use_all=args.all,
    )

    problems = results.get("problems", [])
    if not problems:
        print("\nNo scores recorded.")
        return

    # Gather stats
    scores = [r.get("final_score", 0.0) for r in problems]
    passed = [r for r in problems if r.get("tests_passed")]
    failed = [r for r in problems if not r.get("tests_passed") and not r.get("error")]
    errored = [r for r in problems if r.get("error")]

    mean = sum(scores) / len(scores)
    oracle = _oracle_mean()

    # Read language info from meta.json for each problem
    pool_dir = REPO_ROOT / "benchmark" / "problems"
    lang_map: dict[str, str] = {}
    for r in problems:
        pid = r.get("problem_id", "")
        meta_path = pool_dir / str(pid) / "meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
                runner = meta.get("test_cmd", ["python"])[0]
                lang = {"npm": "JS", "cargo": "Rust", "./gradlew": "Java"}.get(runner, "Python")
                lang_map[pid] = lang
            except Exception:
                lang_map[pid] = "?"

    # Per-language pass rates
    lang_stats: dict[str, list] = {}
    for r in problems:
        pid = r.get("problem_id", "")
        lang = lang_map.get(pid, "?")
        if lang not in lang_stats:
            lang_stats[lang] = []
        lang_stats[lang].append(r.get("tests_passed", False))

    print(f"\n{'─'*54}")
    print(f"  Problems evaluated : {len(problems)} ({len(passed)} passed, {len(failed)} failed, {len(errored)} errors)")
    print(f"  Mean score         : {mean:.2f} / 30.00")
    print(f"  Oracle mean        : {oracle:.2f} / 30.00  (reference diffs)")
    delta = mean - oracle
    arrow = "▲" if delta >= 0 else "▼"
    print(f"  vs oracle          : {arrow} {abs(delta):.2f}")

    if len(lang_stats) > 1:
        print(f"\n  Pass rate by language:")
        for lang in sorted(lang_stats):
            bits = lang_stats[lang]
            n_pass = sum(bits)
            print(f"    {lang:8s}: {n_pass}/{len(bits)}")

    if failed or errored:
        print(f"\n  Failed problems:")
        for r in failed[:10]:
            pid = r.get("problem_id", "?")
            test_out = r.get("test_output", "")
            # Show first failing line from test output
            hint = ""
            for line in test_out.splitlines():
                if "FAILED" in line or "Error" in line or "assert" in line.lower():
                    hint = f"  → {line.strip()[:60]}"
                    break
            print(f"    [{pid}]{hint}")
        for r in errored[:5]:
            pid = r.get("problem_id", "?")
            print(f"    [{pid}] ERROR: {r.get('error', '')[:60]}")
        if len(failed) + len(errored) > 15:
            print(f"    ... and {len(failed) + len(errored) - 15} more (see --output for full details)")

    print(f"{'─'*54}")

    if args.output:
        out = Path(args.output)
        out.write_text(json.dumps(results, indent=2))
        print(f"  Results saved to   : {out}")


def cmd_hash(args: argparse.Namespace) -> None:
    patch_path = Path(args.patch)
    if not patch_path.exists():
        print(f"Error: patch file not found: {patch_path}", file=sys.stderr)
        sys.exit(1)

    content = patch_path.read_bytes()
    sha = hashlib.sha256(content).hexdigest()
    print(sha)
    print(f"\nCommit this hash before submitting your agent.")
    print(f"The hash proves you had the agent at this point — copy it into your PR description.")


def cmd_shard(args: argparse.Namespace) -> None:
    from benchmark.evaluate import select_shard, load_pool_config, POOL_DIR

    config = load_pool_config()
    all_problem_dirs = sorted(p.parent for p in POOL_DIR.glob("*/meta.json"))
    if not all_problem_dirs:
        print("No problems found. Run scripts/build_pool.py to populate benchmark/problems/")
        sys.exit(1)

    shard = select_shard(all_problem_dirs, config)
    print(f"Current weekly shard ({len(shard)} problems):")
    for d in shard:
        import json as _json
        meta = _json.loads((d / "meta.json").read_text())
        print(f"  {meta['id']:<32}  {meta['repo_name']}  —  {meta['issue_title'][:55]}")


def _derive_handle(agent_path: Path) -> str:
    parts = agent_path.parts
    if "submissions" in parts:
        idx = parts.index("submissions")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return agent_path.parent.name


def _build_pr_body(handle: str, sha: str, model: str) -> str:
    return f"""## Agent submission

**Handle:** {handle}
**SHA-256 (commit-reveal):** `{sha}`
**Model:** {model}

## Approach
<!-- Describe your agent's scaffolding: observe→plan→act loop, memory, tools, retries, reflection. -->

## Results (local eval)
<!-- Paste output from: gitminer eval agent/submissions/{handle}/agent.py --no-sandbox -->

## Checklist
- [ ] Agent inherits `BaseAgent` and implements `solve(problem: Problem) -> Patch`
- [ ] Model is listed in `benchmark/harness/allowed_models.txt`
- [ ] SHA-256 above matches: `sha256sum agent/submissions/{handle}/agent.py`
- [ ] Ran `gitminer eval` locally with no errors
"""


def cmd_parity(args: argparse.Namespace) -> None:
    """Compare local scorer output against embedded DAS reference scores."""
    import json as _json
    import math as _math
    from benchmark.evaluate import POOL_DIR
    from benchmark.harness.score import approximate_src_token_score, compute_base_score

    problems = sorted(POOL_DIR.glob("*/meta.json"))
    rows = []
    skipped = 0

    for meta_path in problems:
        meta = _json.loads(meta_path.read_text())
        if "das_base_score" not in meta:
            skipped += 1
            continue
        ref_diff = meta_path.parent / "reference.diff"
        if not ref_diff.exists():
            skipped += 1
            continue

        das_base = float(meta["das_base_score"])
        diff_text = ref_diff.read_text()
        src_tok, total_tok = approximate_src_token_score(diff_text)
        local_base = compute_base_score(src_tok, total_tok)
        ratio = local_base / max(das_base, 0.001)
        rows.append((meta["id"], das_base, local_base, ratio))

    if not rows:
        print("No problems with DAS reference scores found.")
        return

    rows.sort(key=lambda r: abs(r[3] - 1), reverse=True)
    limit = args.top if hasattr(args, "top") else 20

    print(f"Local vs DAS score calibration ({len(rows)} problems, {skipped} skipped)\n")
    print(f"{'Problem ID':<42} {'DAS Base':>9} {'Local':>8} {'Ratio':>7}")
    print("─" * 72)
    for pid, das, local, ratio in rows[:limit]:
        flag = " ← outlier" if ratio > 10 or ratio < 0.5 else ""
        print(f"{pid:<42} {das:>9.2f} {local:>8.2f} {ratio:>6.1f}×{flag}")

    ratios = [r[3] for r in rows]
    median_ratio = sorted(ratios)[len(ratios) // 2]
    print("─" * 72)
    print(f"Median local/DAS ratio: {median_ratio:.1f}×  "
          f"(local scores typically read {median_ratio:.0f}× higher than DAS reference)")


def cmd_submit(args: argparse.Namespace) -> None:
    import subprocess as _sp

    agent_path = Path(args.agent)
    if not agent_path.exists():
        print(f"Error: agent file not found: {agent_path}", file=sys.stderr)
        sys.exit(1)

    # Validate agent loads correctly
    try:
        from benchmark.evaluate import load_agent
        load_agent(str(agent_path))
        print(f"Agent loaded successfully: {agent_path}")
    except Exception as exc:
        print(f"Agent failed to load: {exc}", file=sys.stderr)
        sys.exit(1)

    content = agent_path.read_bytes()
    sha = hashlib.sha256(content).hexdigest()
    handle = _derive_handle(agent_path)
    model = args.model or "claude-3-5-haiku-20241022"
    pr_body = _build_pr_body(handle, sha, model)
    branch = f"submission/{handle}"

    print(f"\nAgent SHA-256: {sha}")

    # Write meta.json so CI can populate the leaderboard model column
    import json as _json
    meta_path = agent_path.parent / "meta.json"
    meta_path.write_text(_json.dumps({"handle": handle, "model": model, "sha256": sha}, indent=2))

    if args.open_pr:
        # Stage, commit, push, and open PR automatically
        try:
            _sp.run(["git", "checkout", "-b", branch], check=True)
        except _sp.CalledProcessError:
            # Branch may already exist
            _sp.run(["git", "checkout", branch], check=True)

        _sp.run(["git", "add", str(agent_path), str(meta_path)], check=True)
        _sp.run(
            ["git", "commit", "-m", f"Submit {handle} agent\n\nagent-sha256: {sha}"],
            check=True,
        )
        _sp.run(["git", "push", "-u", "origin", branch], check=True)
        _sp.run(
            [
                "gh", "pr", "create",
                "--title", f"[Submission] {handle}",
                "--body", pr_body,
            ],
            check=True,
        )
        return

    # Default: print everything the miner needs to run manually
    print(f"\n{'─'*60}")
    print("Run these commands to open your submission PR:\n")
    print(f"  git checkout -b {branch}")
    print(f"  git add {agent_path} {meta_path}")
    print(f'  git commit -m "Submit {handle} agent\n\nagent-sha256: {sha}"')
    print(f"  git push -u origin {branch}")
    print()
    print("Then open a PR with this body (or run with --open-pr to automate):\n")
    print("─" * 60)
    print(pr_body)
    print("─" * 60)


def cmd_cache(args: argparse.Namespace) -> None:
    """Pre-warm the local repo cache used by --no-sandbox eval."""
    import json as _json
    from benchmark.harness.score import _cached_repo, _repo_cache_dir

    pool_dir = REPO_ROOT / "benchmark" / "problems"
    meta_files = sorted(pool_dir.glob("*/meta.json"))
    if not meta_files:
        print("No problems found. Run scripts/build_pool.py first.")
        return

    urls: dict[str, int] = {}
    for mf in meta_files:
        meta = _json.loads(mf.read_text())
        url = meta.get("repo_url", "")
        if url:
            urls[url] = urls.get(url, 0) + 1

    cache_dir = _repo_cache_dir()
    print(f"Cache location: {cache_dir}")
    print(f"Repos to cache: {len(urls)} ({len(meta_files)} problems)\n")

    for i, (url, count) in enumerate(sorted(urls.items()), 1):
        repo_name = "/".join(url.rstrip("/").split("/")[-2:])
        print(f"[{i}/{len(urls)}] {repo_name} ({count} problems)...", end=" ", flush=True)
        try:
            _cached_repo(url)
            print("ok")
        except Exception as e:
            print(f"FAILED: {e}")

    print(f"\nDone. Future --no-sandbox evals skip clone for cached repos.")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="gitminer",
        description="Gittensor Base-Miner Benchmark CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # eval
    p_eval = sub.add_parser("eval", help="Score an agent against the benchmark")
    p_eval.add_argument("agent", help="Path to the agent Python file")
    p_eval.add_argument("--no-sandbox", action="store_true",
                        help="Skip Docker sandbox (faster, less accurate — for local dev)")
    p_eval.add_argument("--all", action="store_true",
                        help="Evaluate against all pool problems (default: current 30-problem shard)")
    p_eval.add_argument("--problems", metavar="IDS",
                        help="Comma-separated problem IDs to evaluate (e.g. 930,986)")
    p_eval.add_argument("--output", metavar="FILE",
                        help="Save full results JSON to FILE")
    p_eval.set_defaults(func=cmd_eval)

    # cache
    p_cache = sub.add_parser(
        "cache",
        help="Pre-warm local repo cache — clone all pool repos once so --no-sandbox eval is fast",
    )
    p_cache.set_defaults(func=cmd_cache)

    # hash
    p_hash = sub.add_parser("hash", help="Compute commit-reveal SHA-256 for a patch file")
    p_hash.add_argument("patch", help="Path to the unified diff / patch file")
    p_hash.set_defaults(func=cmd_hash)

    # shard
    p_shard = sub.add_parser("shard", help="Print current week's 30-problem shard")
    p_shard.set_defaults(func=cmd_shard)

    # parity
    p_parity = sub.add_parser(
        "parity",
        help="Compare local scorer output against DAS reference scores",
    )
    p_parity.add_argument(
        "--top",
        type=int,
        default=20,
        metavar="N",
        help="Show top N most divergent problems (default: 20)",
    )
    p_parity.set_defaults(func=cmd_parity)

    # submit
    p_submit = sub.add_parser(
        "submit",
        help="Validate agent and print (or open) a PR submission",
    )
    p_submit.add_argument("agent", help="Path to the agent Python file")
    p_submit.add_argument(
        "--model",
        metavar="MODEL_ID",
        help="Model ID to embed in the PR body (default: claude-3-5-haiku-20241022)",
    )
    p_submit.add_argument(
        "--open-pr",
        action="store_true",
        help="Create branch, commit, push, and open the PR via gh (requires gh CLI)",
    )
    p_submit.set_defaults(func=cmd_submit)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
