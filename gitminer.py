#!/usr/bin/env python3
"""
gitminer — CLI for the Gittensor Base-Miner Benchmark.

Subcommands:
    eval        Score an agent against the current shard (or all problems)
    run         Run an agent on one problem and print its patch (fast dev loop)
    validate    Check that a patch applies cleanly to a problem's base commit
    leaderboard Show current leaderboard in the terminal
    problems    List benchmark problems with optional filters
    cache       Pre-warm the local repo cache (speeds up --no-sandbox evals)
    hash        Compute the commit-reveal SHA-256 hash for a patch file
    shard       Print the current week's 30-problem shard IDs
    submit      Validate an agent, generate its commit-reveal hash, and print (or open) a PR

Usage:
    python gitminer.py eval agent/submissions/myhandle/agent.py
    python gitminer.py eval agent/submissions/myhandle/agent.py --no-sandbox
    python gitminer.py eval agent/submissions/myhandle/agent.py --all
    python gitminer.py eval agent/submissions/myhandle/agent.py --problems 930,986
    python gitminer.py eval --oracle --no-sandbox   # calibration: score reference diffs, expected mean ~22.77
    python gitminer.py run --problem 0463
    python gitminer.py run --problem 0463 --agent agent/submissions/myhandle/agent.py
    python gitminer.py run --problem 0463 --show-ref --score --no-sandbox
    python gitminer.py validate --problem 0463 --patch my_fix.diff
    python gitminer.py validate --problem 0463 --patch my_fix.diff --run-tests
    python gitminer.py problems
    python gitminer.py problems --lang py --difficulty hard --limit 10
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
        oracle = next((r for r in lb if "Oracle" in r.get("agent", "")), None)
        if oracle:
            return float(oracle.get("score", 22.77))
    except Exception:
        pass
    return 22.77  # fallback


def cmd_eval(args: argparse.Namespace) -> None:
    from benchmark.evaluate import run_evaluation

    use_oracle = getattr(args, "oracle", False)
    agent_path = getattr(args, "agent", None)

    if use_oracle and agent_path:
        print("Note: --oracle ignores the agent argument and scores reference diffs directly.")

    problem_ids = args.problems.split(",") if args.problems else None
    results = run_evaluation(
        agent_path=agent_path,
        problem_ids=problem_ids,
        use_sandbox=not args.no_sandbox,
        use_all=args.all,
        use_oracle=use_oracle,
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

    if args.no_sandbox:
        print(f"\n  Note: --no-sandbox scores use a local heuristic that typically")
        print(f"  runs 3–5× above Docker CI scores. Use these for relative comparison")
        print(f"  only — the authoritative score comes from CI (git push + open PR).")

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


def cmd_problems(args: argparse.Namespace) -> None:
    """List benchmark problems with filtering and sorting."""
    import json as _json

    pool_dir = REPO_ROOT / "benchmark" / "problems"
    baselines_path = REPO_ROOT / "results" / "baselines.json"
    baseline_lookup: dict[str, float] = {}
    if baselines_path.exists():
        raw = _json.loads(baselines_path.read_text())
        for entry in raw.get("problems", []):
            pid_key = entry.get("id", "")
            if pid_key:
                baseline_lookup[pid_key] = entry.get("base_score", 0.0)

    _LANG = {"npm": "js", "cargo": "rs", "./gradlew": "java"}

    rows = []
    for meta_path in sorted(pool_dir.glob("*/meta.json")):
        meta = _json.loads(meta_path.read_text())
        pid = meta.get("id", "")
        runner = meta.get("test_cmd", ["python"])[0]
        lang = _LANG.get(runner, "py")
        baseline = baseline_lookup.get(pid)

        difficulty = "?"
        if baseline is not None:
            if baseline >= 25:
                difficulty = "easy"
            elif baseline >= 18:
                difficulty = "medium"
            else:
                difficulty = "hard"

        rows.append({
            "id": pid,
            "repo": meta.get("repo_name", ""),
            "lang": lang,
            "difficulty": difficulty,
            "baseline": baseline,
            "title": meta.get("issue_title", "")[:60],
        })

    # Filter
    if args.lang:
        rows = [r for r in rows if r["lang"] == args.lang]
    if args.difficulty:
        rows = [r for r in rows if r["difficulty"] == args.difficulty]
    if args.repo:
        rows = [r for r in rows if args.repo.lower() in r["repo"].lower()]
    if args.search:
        q = args.search.lower()
        rows = [r for r in rows if q in r["title"].lower() or q in r["id"].lower()]

    # Sort
    reverse = args.sort in ("baseline",)
    if args.sort == "baseline":
        rows.sort(key=lambda r: (r["baseline"] or 0), reverse=True)
    elif args.sort == "difficulty":
        order = {"hard": 0, "medium": 1, "easy": 2, "?": 3}
        rows.sort(key=lambda r: order.get(r["difficulty"], 3))
    else:
        rows.sort(key=lambda r: r["id"])

    # Display
    limit = args.limit or len(rows)
    print(f"\n{'ID':<42} {'Repo':<30} {'Lang':<6} {'Diff':<8} {'Baseline':>9}")
    print("─" * 100)
    for r in rows[:limit]:
        b = f"{r['baseline']:.2f}" if r["baseline"] is not None else "n/a"
        print(f"{r['id']:<42} {r['repo']:<30} {r['lang']:<6} {r['difficulty']:<8} {b:>9}  {r['title']}")

    print(f"\n{len(rows[:limit])} of {len(rows)} problems shown.")


def cmd_leaderboard(args: argparse.Namespace) -> None:
    """Print the current leaderboard from results/leaderboard.json."""
    lb_path = REPO_ROOT / "results" / "leaderboard.json"
    if not lb_path.exists():
        print("Leaderboard not found. Check results/leaderboard.json.")
        return

    rows = json.loads(lb_path.read_text())
    # Separate oracle row from ranked entries
    oracle = next((r for r in rows if r.get("rank") is None), None)
    ranked = [r for r in rows if r.get("rank") is not None]

    if not ranked:
        print("\nNo submissions yet — be the first to submit an agent!")
        if oracle and oracle.get("score") is not None:
            print(f"\nOracle (reference diffs): {oracle['score']:.2f} / 30.00  ← score to beat")
        print(f"\nDashboard: https://punchthedev.github.io/gittensor-miner-dashboard/")
        return

    handle_w = max(len(r.get("agent", "")) for r in ranked)
    handle_w = max(handle_w, 8)
    model_w = max(len(r.get("model", "")) for r in ranked)
    model_w = max(model_w, 5)

    header = f"{'Rank':>4}  {'Agent':<{handle_w}}  {'Score':>8}  {'Model':<{model_w}}  {'Date'}"
    print()
    print(header)
    print("─" * len(header))

    for row in ranked:
        rank = row.get("rank", "?")
        handle = row.get("agent", "—")
        score = row.get("score")
        model = row.get("model", "—")
        date = (row.get("date") or "")[:10]

        rank_str = f"#{rank:>3}"
        score_str = f"{score:>7.2f}" if score is not None else "  pending"

        print(f"{rank_str}  {handle:<{handle_w}}  {score_str}  {model:<{model_w}}  {date}")

    print()
    if oracle and oracle.get("score") is not None:
        print(f"Oracle (reference diffs): {oracle['score']:.2f} / 30.00")
    print(f"Dashboard: https://punchthedev.github.io/gittensor-miner-dashboard/")
    print()


def cmd_validate(args: argparse.Namespace) -> None:
    """
    Check that a patch applies cleanly to a problem's base commit.

    Useful for quick local sanity checks before running a full eval.
    Uses the repo cache (run `gitminer cache` first for fastest results).
    """
    import subprocess
    import tempfile
    from benchmark.harness.score import _cached_repo, apply_patch, run_tests

    pool_dir = REPO_ROOT / "benchmark" / "problems"
    problem_dir = pool_dir / args.problem
    meta_path = problem_dir / "meta.json"

    if not meta_path.exists():
        print(f"Problem {args.problem!r} not found in {pool_dir}", file=sys.stderr)
        sys.exit(1)

    meta = json.loads(meta_path.read_text())

    # Read patch
    patch_path = Path(args.patch)
    if not patch_path.exists():
        print(f"Patch file not found: {args.patch}", file=sys.stderr)
        sys.exit(1)

    patch_text = patch_path.read_text().strip()
    if not patch_text:
        print("Patch file is empty.", file=sys.stderr)
        sys.exit(1)

    repo_url = meta["repo_url"]
    base_commit = meta["base_commit"]
    repo_name = meta["repo_name"]

    print(f"Problem : {args.problem}  —  {meta.get('issue_title', '')[:60]}")
    print(f"Repo    : {repo_name}")
    print(f"Commit  : {base_commit[:12]}")
    print()

    # Ensure cached clone exists
    print("Checking repo cache...", end=" ", flush=True)
    try:
        cached = _cached_repo(repo_url)
        print("ok")
    except Exception as e:
        print(f"FAILED\n{e}", file=sys.stderr)
        sys.exit(1)

    # Create an isolated worktree at base_commit
    with tempfile.TemporaryDirectory(prefix="gmval_") as tmpdir:
        worktree = Path(tmpdir) / "repo"
        try:
            subprocess.run(
                ["git", "-C", str(cached), "worktree", "add",
                 "--detach", "--force", str(worktree), base_commit],
                check=True, capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            print(f"Failed to create worktree: {e.stderr.decode()}", file=sys.stderr)
            sys.exit(1)

        try:
            # Copy patch into the worktree dir so git apply can resolve paths
            import shutil
            patch_copy = Path(tmpdir) / "candidate.patch"
            shutil.copy(patch_path, patch_copy)

            # Check apply
            check = subprocess.run(
                ["git", "apply", "--check", "--verbose", str(patch_copy)],
                cwd=worktree, capture_output=True, text=True,
            )
            if check.returncode != 0:
                print("FAIL  patch does not apply cleanly")
                print()
                stderr = check.stderr.strip()
                if stderr:
                    print(stderr)
                sys.exit(1)

            # Apply
            subprocess.run(
                ["git", "apply", str(patch_copy)],
                cwd=worktree, check=True, capture_output=True,
            )

            # Diff stat
            stat = subprocess.run(
                ["git", "diff", "--stat", "HEAD"],
                cwd=worktree, capture_output=True, text=True,
            )
            print("PASS  patch applies cleanly")
            print()
            if stat.stdout.strip():
                print(stat.stdout.rstrip())
            print()

            # Optional: run tests
            if args.run_tests:
                test_cmd = meta.get("test_cmd")
                if not test_cmd:
                    print("No test_cmd defined for this problem — skipping tests.")
                else:
                    print(f"Running: {' '.join(test_cmd)}")
                    passed, output, all_skipped = run_tests(worktree, test_cmd)
                    if passed or all_skipped:
                        status = "PASS" if passed else "SKIP (no tests collected)"
                        print(f"{status}  tests")
                    else:
                        print("FAIL  tests")
                    # Show last 40 lines of test output
                    lines = output.strip().splitlines()
                    if lines:
                        print()
                        print("\n".join(lines[-40:]))
                    if not passed and not all_skipped:
                        sys.exit(1)
        finally:
            subprocess.run(
                ["git", "-C", str(cached), "worktree", "remove", "--force", str(worktree)],
                capture_output=True,
            )


def _print_diff(diff: str) -> None:
    """Print a unified diff with ANSI colors when the terminal supports it."""
    use_color = sys.stdout.isatty()
    RED   = "\033[31m" if use_color else ""
    GREEN = "\033[32m" if use_color else ""
    CYAN  = "\033[36m" if use_color else ""
    RESET = "\033[0m"  if use_color else ""

    for line in diff.splitlines():
        if line.startswith(("---", "+++")):
            print(f"{CYAN}{line}{RESET}")
        elif line.startswith("+"):
            print(f"{GREEN}{line}{RESET}")
        elif line.startswith("-"):
            print(f"{RED}{line}{RESET}")
        elif line.startswith("@@"):
            print(f"{CYAN}{line}{RESET}")
        else:
            print(line)


def cmd_run(args: argparse.Namespace) -> None:
    """
    Run an agent on a single problem and print its output patch.

    The fastest development loop: iterate on your agent without running
    the full 30-problem eval.  Uses the same evaluate.load_problem path as
    eval so the problem is identical to CI.

    Examples:
        python gitminer.py run --problem 0463
        python gitminer.py run --problem 0463 --agent agent/submissions/alice/agent.py
        python gitminer.py run --problem 0463 --show-ref --score --no-sandbox
        python gitminer.py run --problem 0463 --output my_fix.diff --verbose
    """
    import tempfile
    import time

    from benchmark.evaluate import POOL_DIR, load_agent, load_problem

    problem_dir = REPO_ROOT / "benchmark" / "problems" / args.problem
    if not (problem_dir / "meta.json").exists():
        print(f"Problem {args.problem!r} not found in benchmark/problems/", file=sys.stderr)
        sys.exit(1)

    problem = load_problem(problem_dir)

    # Friendly lang label
    _lang_map = {"python": "py", "pytest": "py", "npm": "js",
                 "cargo": "rs", "./gradlew": "java"}
    lang = _lang_map.get(problem.test_cmd[0] if problem.test_cmd else "", "?")
    test_str = " ".join(problem.test_cmd) if problem.test_cmd else "(none)"

    print(f"Problem  : {args.problem}  [{lang}]  {problem.repo_name}")
    print(f"Issue    : {problem.issue_title[:72]}")
    print(f"Test cmd : {test_str}")
    print()

    agent_path = args.agent or str(REPO_ROOT / "agent" / "example" / "agent.py")
    if not Path(agent_path).exists():
        print(f"Agent not found: {agent_path}", file=sys.stderr)
        sys.exit(1)

    agent = load_agent(agent_path)
    print(f"Agent    : {Path(agent_path).name}", flush=True)
    print("Running  ...", flush=True)

    t0 = time.time()
    try:
        patch = agent.solve(problem)
    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    elapsed = time.time() - t0

    diff = patch.diff or ""
    print(f"Elapsed  : {elapsed:.1f}s")
    print()

    # Agent patch
    print("─" * 72)
    print("Agent patch")
    print("─" * 72)
    if diff:
        _print_diff(diff)
    else:
        print("(empty patch)")
    print()

    # Reference diff
    if args.show_ref:
        ref_path = problem_dir / "reference.diff"
        print("─" * 72)
        print("Reference diff")
        print("─" * 72)
        if ref_path.exists():
            _print_diff(ref_path.read_text())
        else:
            print("(no reference.diff)")
        print()

    # Reasoning log
    if args.verbose and patch.reasoning:
        print("─" * 72)
        print("Reasoning log")
        print("─" * 72)
        print(patch.reasoning)
        print()

    # Save to file
    if args.output:
        out = Path(args.output)
        out.write_text(diff)
        print(f"Saved    : {out}")
        print()

    # Score
    if args.score and diff:
        with tempfile.NamedTemporaryFile(suffix=".diff", mode="w", delete=False) as tmp:
            tmp.write(diff)
            tmp_path = Path(tmp.name)
        try:
            if args.no_sandbox:
                from benchmark.harness.score import score_patch
                result = score_patch(problem_dir, tmp_path)
            else:
                from benchmark.harness.runner import run_in_sandbox
                result = run_in_sandbox(problem_dir, tmp_path)

            tests_ok = result.get("tests_passed", False)
            score = result.get("final_score", 0.0)
            status = "PASS" if tests_ok else "FAIL"
            print("─" * 72)
            print(f"Score    : {score:.2f} / 30.00  ({status})")

            baselines_path = REPO_ROOT / "results" / "baselines.json"
            if baselines_path.exists():
                baselines = json.loads(baselines_path.read_text())
                ref_score = next(
                    (b["score"] for b in baselines if b["problem_id"] == args.problem),
                    None,
                )
                if ref_score is not None:
                    delta = score - ref_score
                    sign = "+" if delta >= 0 else ""
                    print(f"Baseline : {ref_score:.2f}  (delta {sign}{delta:.2f})")
            if args.no_sandbox:
                print("Note: --no-sandbox scores run ~3–5× above Docker CI.")
        finally:
            tmp_path.unlink(missing_ok=True)
    elif args.score:
        print("Nothing to score — agent produced an empty patch.")


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
    p_eval.add_argument("agent", nargs="?", help="Path to the agent Python file")
    p_eval.add_argument("--oracle", action="store_true",
                        help="Score reference diffs instead of an agent (pipeline calibration check)")
    p_eval.add_argument("--no-sandbox", action="store_true",
                        help="Skip Docker sandbox (faster, less accurate — for local dev)")
    p_eval.add_argument("--all", action="store_true",
                        help="Evaluate against all pool problems (default: current 30-problem shard)")
    p_eval.add_argument("--problems", metavar="IDS",
                        help="Comma-separated problem IDs to evaluate (e.g. 930,986)")
    p_eval.add_argument("--output", metavar="FILE",
                        help="Save full results JSON to FILE")
    p_eval.set_defaults(func=cmd_eval)

    # run
    p_run = sub.add_parser(
        "run",
        help="Run an agent on a single problem and print its patch (fast dev loop)",
    )
    p_run.add_argument("--problem", required=True, metavar="ID",
                       help="Problem ID to run (e.g. 0463)")
    p_run.add_argument("--agent", metavar="PATH",
                       help="Path to agent.py (default: example agent)")
    p_run.add_argument("--show-ref", action="store_true",
                       help="Also print the reference diff for comparison")
    p_run.add_argument("--score", action="store_true",
                       help="Score the generated patch inline")
    p_run.add_argument("--no-sandbox", action="store_true",
                       help="Score without Docker sandbox (faster, ~3-5x higher scores)")
    p_run.add_argument("--output", metavar="FILE",
                       help="Save the generated patch to FILE")
    p_run.add_argument("--verbose", action="store_true",
                       help="Print the agent's internal reasoning log")
    p_run.set_defaults(func=cmd_run)

    # validate
    p_validate = sub.add_parser(
        "validate",
        help="Check that a patch applies cleanly to a problem's base commit",
    )
    p_validate.add_argument("--problem", required=True, metavar="ID",
                            help="Problem ID (e.g. 0463)")
    p_validate.add_argument("--patch", required=True, metavar="FILE",
                            help="Path to the unified diff file")
    p_validate.add_argument("--run-tests", action="store_true",
                            help="Also run the problem's test command after applying the patch")
    p_validate.set_defaults(func=cmd_validate)

    # leaderboard
    p_lb = sub.add_parser("leaderboard", help="Show current leaderboard in the terminal")
    p_lb.set_defaults(func=cmd_leaderboard)

    # problems
    p_problems = sub.add_parser("problems", help="List benchmark problems with optional filters")
    p_problems.add_argument("--lang", choices=["py", "js", "rs", "java"], help="Filter by language")
    p_problems.add_argument("--difficulty", choices=["easy", "medium", "hard"], help="Filter by difficulty")
    p_problems.add_argument("--repo", metavar="PATTERN", help="Filter by repo name substring")
    p_problems.add_argument("--search", metavar="TEXT", help="Search title or problem ID")
    p_problems.add_argument("--sort", choices=["id", "baseline", "difficulty"], default="id",
                            help="Sort order (default: id)")
    p_problems.add_argument("--limit", type=int, metavar="N", help="Show at most N problems")
    p_problems.set_defaults(func=cmd_problems)

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
