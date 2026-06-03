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
    hash        Compute the commit-reveal SHA-256 hash for an agent file
    shard       Print the current week's 30-problem shard IDs
    info        Show full details for a single problem (issue, test cmd, context files, scores)
    submit      Validate an agent, generate its commit-reveal hash, and print (or open) a PR
    serve-api   Start the REST API server (default port 8083)
    mine        Run your agent continuously; auto-submit when it beats the champion

Usage:
    python3 gitminer.py eval agent/submissions/myhandle/agent.py
    python3 gitminer.py eval agent/submissions/myhandle/agent.py --no-sandbox
    python3 gitminer.py eval agent/submissions/myhandle/agent.py --all
    python3 gitminer.py eval agent/submissions/myhandle/agent.py --problems 930,986
    python3 gitminer.py eval --oracle --no-sandbox   # calibration: score reference diffs, expected weighted mean ~13.03
    python3 gitminer.py run --problem 0463
    python3 gitminer.py run --problem 0463 --agent agent/submissions/myhandle/agent.py
    python3 gitminer.py run --problem 0463 --show-ref --score --no-sandbox
    python3 gitminer.py validate --problem 0463 --patch my_fix.diff
    python3 gitminer.py validate --problem 0463 --patch my_fix.diff --run-tests
    python3 gitminer.py problems
    python3 gitminer.py problems --cat python --difficulty hard --limit 10
    python3 gitminer.py cache
    python3 gitminer.py hash agent/submissions/myhandle/agent.py
    python3 gitminer.py shard
    python3 gitminer.py info 0463
    python3 gitminer.py submit agent/submissions/myhandle/agent.py
    python3 gitminer.py submit agent/submissions/myhandle/agent.py --model deepseek/deepseek-chat --open-pr
    python3 gitminer.py serve-api
    python3 gitminer.py serve-api --port 9000 --host 127.0.0.1
    python3 gitminer.py mine --agent agent/submissions/myhandle/agent.py --no-sandbox
    python3 gitminer.py mine --agent agent/submissions/myhandle/agent.py --loop
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).parent
sys.path.insert(0, str(REPO_ROOT))


def _oracle_weighted() -> float:
    """Read the oracle weighted mean from leaderboard.json (primary ranking metric)."""
    try:
        lb = json.loads((REPO_ROOT / "results" / "leaderboard.json").read_text())
        oracle = next((r for r in lb if "Oracle" in r.get("agent", "")), None)
        if oracle:
            return float(oracle.get("weighted_score") or oracle.get("score", 13.03))
    except Exception:
        pass
    return 13.03  # fallback


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
    oracle_weighted = _oracle_weighted()

    from benchmark.evaluate import REPO_CATEGORY

    # Read category info from meta.json for each problem
    pool_dir = REPO_ROOT / "benchmark" / "problems"
    cat_map: dict[str, str] = {}
    for r in problems:
        pid = r.get("problem_id", "")
        cat = r.get("category", "")
        if not cat:
            meta_path = pool_dir / str(pid) / "meta.json"
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text())
                    cat = REPO_CATEGORY.get(meta.get("repo_name", ""), "?")
                except Exception:
                    cat = "?"
        cat_map[pid] = cat or "?"

    # Per-category pass rates
    cat_stats: dict[str, list] = {}
    for r in problems:
        pid = r.get("problem_id", "")
        cat = cat_map.get(pid, "?")
        if cat not in cat_stats:
            cat_stats[cat] = []
        cat_stats[cat].append(r.get("tests_passed", False))

    weighted_mean = results.get("weighted_mean_score", mean)
    print(f"\n{'─'*54}")
    print(f"  Problems evaluated : {len(problems)} ({len(passed)} passed, {len(failed)} failed, {len(errored)} errors)")
    print(f"  Mean score         : {mean:.2f} / 30.00")
    print(f"  Weighted mean      : {weighted_mean:.2f} / 30.00  (easy×1 / medium×1.5 / hard×2)")
    print(f"  Oracle weighted    : {oracle_weighted:.2f} / 30.00  (reference diffs, weighted)")
    delta = weighted_mean - oracle_weighted
    arrow = "▲" if delta >= 0 else "▼"
    print(f"  vs oracle          : {arrow} {abs(delta):.2f}")

    if len(cat_stats) > 1:
        print(f"\n  Pass rate by category:")
        for cat in sorted(cat_stats):
            bits = cat_stats[cat]
            n_pass = sum(bits)
            print(f"    {cat:12s}: {n_pass}/{len(bits)}")

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
        print(f"  runs ~2× above Docker CI scores. Use these for relative comparison")
        print(f"  only — the authoritative score comes from CI (git push + open PR).")

    import os as _os
    if not _os.environ.get("SHARD_SECRET") and not getattr(args, "all", False) and not args.problems:
        print(f"\n  Note: local shard may differ from CI shard (server-side anti-gaming).")
        print(f"  Use --all for a stable benchmark independent of shard selection.")

    print(f"{'─'*54}")

    if args.output:
        out = Path(args.output)
        out.write_text(json.dumps(results, indent=2))
        print(f"  Results saved to   : {out}")


def cmd_hash(args: argparse.Namespace) -> None:
    agent_path = Path(args.agent)
    if not agent_path.exists():
        print(f"Error: agent file not found: {agent_path}", file=sys.stderr)
        sys.exit(1)

    content = agent_path.read_bytes()
    sha = hashlib.sha256(content).hexdigest()
    print(sha)
    print(f"\nCopy this hash into your PR description before pushing your agent.")
    print(f"It proves you held this version at submission time — used for first-to-commit credit.")


def cmd_shard(args: argparse.Namespace) -> None:
    from benchmark.evaluate import select_shard, load_pool_config, POOL_DIR, _problem_category, problem_difficulty

    config = load_pool_config()
    all_problem_dirs = sorted(p.parent for p in POOL_DIR.glob("*/meta.json"))
    if not all_problem_dirs:
        print("No problems found. Run scripts/build_pool.py to populate benchmark/problems/")
        sys.exit(1)

    shard = select_shard(all_problem_dirs, config)
    by_cat: dict[str, int] = {}
    by_diff: dict[str, int] = {}
    for d in shard:
        cat = _problem_category(d)
        tier, _ = problem_difficulty(d)
        by_cat[cat] = by_cat.get(cat, 0) + 1
        by_diff[tier] = by_diff.get(tier, 0) + 1
    cat_summary = "  ".join(f"{c}:{n}" for c, n in sorted(by_cat.items()))
    diff_summary = "  ".join(f"{t}:{by_diff.get(t, 0)}" for t in ("hard", "medium", "easy") if t in by_diff)
    print(f"Current weekly shard ({len(shard)} problems)  [{cat_summary}]  difficulty[{diff_summary}]:")
    import json as _json
    for d in shard:
        meta = _json.loads((d / "meta.json").read_text())
        cat = _problem_category(d)
        tier, _ = problem_difficulty(d)
        print(f"  {meta['id']:<32}  [{cat:<10}]  [{tier:<6}]  {meta['repo_name']}  —  {meta['issue_title'][:40]}")


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
- [ ] SHA-256 above matches: `python3 gitminer.py hash agent/submissions/{handle}/agent.py`
- [ ] Ran `gitminer eval` locally with no errors
"""


def cmd_parity(args: argparse.Namespace) -> None:
    """Compare local tree-sitter scores against embedded DAS reference scores."""
    import json as _json
    from benchmark.evaluate import POOL_DIR

    # Load pre-computed tree-sitter baselines (matches DAS scoring engine).
    # Fallback to heuristic only for problems not yet in baselines.json.
    baselines_path = REPO_ROOT / "results" / "baselines.json"
    ts_by_id: dict[str, float] = {}
    scoring_method = "heuristic"
    if baselines_path.exists():
        bl = _json.loads(baselines_path.read_text())
        ts_by_id = {p["id"]: float(p["base_score"]) for p in bl.get("problems", [])}
        if ts_by_id:
            scoring_method = "tree-sitter"

    from benchmark.harness.score import approximate_src_token_score, compute_base_score

    problems = sorted(POOL_DIR.glob("*/meta.json"))
    rows = []
    skipped = 0

    for meta_path in problems:
        meta = _json.loads(meta_path.read_text())
        if meta.get("das_base_score") is None:
            skipped += 1
            continue

        pid = meta["id"]
        das_base = float(meta["das_base_score"])

        if pid in ts_by_id:
            local_base = ts_by_id[pid]
            method = "ts"
        else:
            ref_diff = meta_path.parent / "reference.diff"
            if not ref_diff.exists():
                skipped += 1
                continue
            src_tok, total_tok = approximate_src_token_score(ref_diff.read_text())
            local_base = compute_base_score(src_tok, total_tok)
            method = "heuristic"

        ratio = local_base / max(das_base, 0.001)
        rows.append((pid, das_base, local_base, ratio, method))

    if not rows:
        print("No problems with DAS reference scores found.")
        return

    rows.sort(key=lambda r: abs(r[3] - 1), reverse=True)
    limit = args.top if hasattr(args, "top") else 20

    ts_count = sum(1 for r in rows if r[4] == "ts")
    print(f"Local vs DAS score calibration ({len(rows)} problems, {skipped} skipped)")
    print(f"Scoring method: {scoring_method} ({ts_count}/{len(rows)} via tree-sitter)\n")
    print(f"{'Problem ID':<42} {'DAS Base':>9} {'Local':>8} {'Ratio':>7}")
    print("─" * 72)
    for pid, das, local, ratio, _ in rows[:limit]:
        flag = " ← outlier" if ratio > 10 or ratio < 0.5 else ""
        print(f"{pid:<42} {das:>9.2f} {local:>8.2f} {ratio:>6.1f}×{flag}")

    ratios = [r[3] for r in rows]
    median_ratio = sorted(ratios)[len(ratios) // 2]
    outlier_count = sum(1 for r in rows if r[3] > 10 or r[3] < 0.5)
    aligned_count = len(rows) - outlier_count
    print("─" * 72)
    if scoring_method == "tree-sitter":
        print(f"Median local/DAS ratio: {median_ratio:.2f}×  "
              f"(tree-sitter scorer — ratio near 1.0 means tight DAS alignment)")
    else:
        print(f"Median local/DAS ratio: {median_ratio:.1f}×  "
              f"(heuristic — run baseline_scores.py to get tree-sitter parity)")
    high_outliers = sum(1 for r in rows if r[3] > 10)
    low_outliers = sum(1 for r in rows if r[3] < 0.5)
    print(f"{aligned_count}/{len(rows)} problems within 10× of DAS  |  "
          f"{outlier_count} outliers ({high_outliers} local>DAS, {low_outliers} local<DAS)")
    if outlier_count:
        print("Note: local>DAS = DAS had test failures; local<DAS = local scorer gap (zero-score problems).")


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
    model = args.model or "deepseek/deepseek-chat"
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
    from benchmark.evaluate import REPO_CATEGORY

    pool_dir = REPO_ROOT / "benchmark" / "problems"
    baselines_path = REPO_ROOT / "results" / "baselines.json"
    baseline_lookup: dict[str, float] = {}
    difficulty_lookup: dict[str, str] = {}
    if baselines_path.exists():
        raw = _json.loads(baselines_path.read_text())
        for entry in raw.get("problems", []):
            pid_key = entry.get("id", "")
            if pid_key:
                baseline_lookup[pid_key] = entry.get("base_score", 0.0)
                difficulty_lookup[pid_key] = entry.get("difficulty", "medium")

    rows = []
    for meta_path in sorted(pool_dir.glob("*/meta.json")):
        meta = _json.loads(meta_path.read_text())
        pid = meta.get("id", "")
        repo = meta.get("repo_name", "")
        cat = REPO_CATEGORY.get(repo.lower(), "python")
        baseline = baseline_lookup.get(pid)

        rows.append({
            "id": pid,
            "repo": repo,
            "cat": cat,
            "difficulty": difficulty_lookup.get(pid, "?"),
            "baseline": baseline,
            "title": meta.get("issue_title", "")[:60],
        })

    # Filter
    if args.cat:
        rows = [r for r in rows if r["cat"] == args.cat]
    if args.difficulty:
        rows = [r for r in rows if r["difficulty"] == args.difficulty]
    if args.repo:
        rows = [r for r in rows if args.repo.lower() in r["repo"].lower()]
    if args.search:
        q = args.search.lower()
        rows = [r for r in rows if q in r["title"].lower() or q in r["id"].lower()]

    # Sort
    if args.sort == "baseline":
        rows.sort(key=lambda r: (r["baseline"] or 0), reverse=True)
    elif args.sort == "difficulty":
        order = {"hard": 0, "medium": 1, "easy": 2, "?": 3}
        rows.sort(key=lambda r: order.get(r["difficulty"], 3))
    else:
        rows.sort(key=lambda r: r["id"])

    # Display
    limit = args.limit or len(rows)
    print(f"\n{'ID':<42} {'Repo':<32} {'Cat':<12} {'Diff':<8} {'Baseline':>9}")
    print("─" * 107)
    for r in rows[:limit]:
        b = f"{r['baseline']:.2f}" if r["baseline"] is not None else "n/a"
        print(f"{r['id']:<42} {r['repo']:<32} {r['cat']:<12} {r['difficulty']:<8} {b:>9}  {r['title']}")

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
        if oracle and oracle.get("weighted_score") is not None:
            print(f"\nOracle (reference diffs): {oracle['weighted_score']:.2f} / 30.00  ← weighted score to beat")
        elif oracle and oracle.get("score") is not None:
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
    if oracle:
        w = oracle.get("weighted_score") or oracle.get("score")
        if w is not None:
            print(f"Oracle (reference diffs): {w:.2f} / 30.00  (weighted)")
    print(f"Dashboard: https://punchthedev.github.io/gittensor-miner-dashboard/")
    print()


def cmd_info(args: argparse.Namespace) -> None:
    """Show full details for a single problem: issue, test cmd, context files, scores."""
    problem_dir = REPO_ROOT / "benchmark" / "problems" / args.id
    meta_path = problem_dir / "meta.json"
    if not meta_path.exists():
        print(f"Problem {args.id!r} not found in benchmark/problems/")
        sys.exit(1)

    meta = json.loads(meta_path.read_text())

    # Baselines
    baseline_score: float | None = None
    baseline_difficulty: str | None = None
    baseline_weight: float | None = None
    bl_path = REPO_ROOT / "results" / "baselines.json"
    if bl_path.exists():
        bl = json.loads(bl_path.read_text())
        for entry in bl.get("problems", []):
            if entry.get("id") == args.id:
                baseline_score = entry.get("base_score")
                baseline_difficulty = entry.get("difficulty")
                baseline_weight = entry.get("weight")
                break

    # Context files
    ctx_dir = problem_dir / "context"
    ctx_files: list[str] = []
    test_files: set[str] = set()
    if ctx_dir.exists():
        _TEST_PATS = ("test_", "_test.", ".test.", ".spec.", "/tests/", "/test/", "/spec/")
        for f in sorted(ctx_dir.rglob("*")):
            if f.is_file():
                rel = str(f.relative_to(ctx_dir))
                ctx_files.append(rel)
                if any(p in rel.replace("\\", "/") for p in _TEST_PATS):
                    test_files.add(rel)

    # Reference diff size
    ref_diff = problem_dir / "reference.diff"
    diff_lines = ref_diff.read_text().splitlines() if ref_diff.exists() else []
    add_lines = sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++"))
    rem_lines = sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---"))

    RESET, BOLD, DIM, GREEN, YELLOW, CYAN, RED = (
        "\033[0m", "\033[1m", "\033[2m", "\033[32m", "\033[33m", "\033[36m", "\033[31m",
    )
    sep = DIM + "─" * 70 + RESET

    print(f"\n{BOLD}{meta.get('issue_title', 'Untitled')}{RESET}")
    print(f"{DIM}{meta.get('repo_name','')}  ·  Issue #{meta.get('issue_number','?')}  ·  PR #{meta.get('pr_number','?')}{RESET}")
    merged = (meta.get("merged_at") or "")[:10]
    if merged:
        print(f"{DIM}Merged {merged}{RESET}")

    print(f"\n{sep}")

    # Issue body
    body = (meta.get("issue_body") or "").strip()
    if body:
        print(f"\n{BOLD}Issue{RESET}")
        # Wrap to ~72 chars
        for line in body[:1200].splitlines():
            print(f"  {line}")
        if len(body) > 1200:
            print(f"  {DIM}… (truncated){RESET}")

    # Test command
    test_cmd = meta.get("test_cmd") or []
    print(f"\n{BOLD}Test command{RESET}")
    print(f"  {GREEN}{' '.join(test_cmd)}{RESET}")

    # Scores
    print(f"\n{BOLD}Scores{RESET}")
    if baseline_score is not None:
        if baseline_difficulty == "easy":
            diff_str = f"  {GREEN}easy ×1{RESET}"
        elif baseline_difficulty == "medium":
            diff_str = f"  {YELLOW}medium ×1.5{RESET}"
        elif baseline_difficulty == "hard":
            diff_str = f"  {RED}hard ×2{RESET}"
        else:
            diff_str = ""
        print(f"  Baseline: {CYAN}{baseline_score:.2f}{RESET}/30{diff_str}")
    das = meta.get("das_score")
    if das is not None:
        try:
            print(f"  DAS match: {float(das):.4f}")
        except (TypeError, ValueError):
            pass
    print(f"  Reference diff: {GREEN}+{add_lines}{RESET}/{RED}-{rem_lines}{RESET} lines")

    # Context files
    print(f"\n{BOLD}Context files ({len(ctx_files)}){RESET}")
    for f in ctx_files:
        marker = f"  {GREEN}🧪{RESET}" if f in test_files else "  📄"
        print(f"{marker}  {CYAN}{f}{RESET}")
    src_count = len(ctx_files) - len(test_files)
    print(f"  {DIM}{src_count} source · {len(test_files)} test{RESET}")

    # Quick commands
    print(f"\n{sep}")
    print(f"\n{BOLD}Quick commands{RESET}")
    print(f"  {DIM}Run oracle (no agent):  {RESET}python3 gitminer.py run --problem {args.id} --show-ref")
    print(f"  {DIM}Run your agent:         {RESET}python3 gitminer.py run --problem {args.id} --agent <path/agent.py> --score --no-sandbox")
    print(f"  {DIM}View on GitHub:         {RESET}https://github.com/{meta.get('repo_name','')}/pull/{meta.get('pr_number','?')}")
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
        python3 gitminer.py run --problem 0463
        python3 gitminer.py run --problem 0463 --agent agent/submissions/alice/agent.py
        python3 gitminer.py run --problem 0463 --show-ref --score --no-sandbox
        python3 gitminer.py run --problem 0463 --output my_fix.diff --verbose
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

    # --show-ref alone: print the reference diff without running an agent.
    if args.show_ref and not args.agent:
        ref_path = problem_dir / "reference.diff"
        print("─" * 72)
        print("Reference diff")
        print("─" * 72)
        if ref_path.exists():
            _print_diff(ref_path.read_text())
        else:
            print("(no reference.diff)")
        return

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
        use_color = sys.stdout.isatty()
        GREEN = "\033[32m" if use_color else ""
        RED   = "\033[31m" if use_color else ""
        CYAN  = "\033[36m" if use_color else ""
        RESET = "\033[0m"  if use_color else ""

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
            status = f"{GREEN}PASS{RESET}" if tests_ok else f"{RED}FAIL{RESET}"
            src_tok = result.get("source_token_score", 0.0)
            base_score = result.get("base_score", score)
            skipped = result.get("tests_skipped_locally", False)

            print("─" * 72)
            if not tests_ok:
                print(f"Tests    : {status}")
                test_out = result.get("test_output", "")
                if test_out:
                    # Show last 20 lines of test output
                    lines = test_out.strip().splitlines()
                    shown = lines[-20:]
                    if len(lines) > 20:
                        print(f"  [{len(lines) - 20} lines omitted]")
                    for line in shown:
                        print(f"  {line}")
                print(f"Score    : {RED}0.00{RESET} / 30.00  (tests must pass)")
            else:
                print(f"Tests    : {status}{'  (skipped locally — CI runs full suite)' if skipped else ''}")
                # Score breakdown
                src_bar_filled = int(round(src_tok / 25 * 20))
                src_bar = "█" * src_bar_filled + "░" * (20 - src_bar_filled)
                print(f"Src tok  : {GREEN}{src_tok:5.2f}{RESET} / 25.00  [{src_bar}]")
                bonus = score - base_score if score > base_score else 0.0
                print(f"Score    : {GREEN}{score:.2f}{RESET} / 30.00")

            baselines_path = REPO_ROOT / "results" / "baselines.json"
            if baselines_path.exists():
                baselines_data = json.loads(baselines_path.read_text())
                baselines = baselines_data.get("problems", baselines_data) if isinstance(baselines_data, dict) else baselines_data
                ref_score = next(
                    (b.get("base_score") for b in baselines if isinstance(b, dict) and b.get("id") == args.problem),
                    None,
                )
                if ref_score is not None:
                    delta = score - ref_score
                    sign = "+" if delta >= 0 else ""
                    color = GREEN if delta >= 0 else RED
                    print(f"Oracle   : {ref_score:.2f}  (local, delta {color}{sign}{delta:.2f}{RESET})")

            # Show DAS validator score for the reference PR if available
            meta_path = problem_dir / "meta.json"
            if meta_path.exists():
                prob_meta = json.loads(meta_path.read_text())
                das_base = prob_meta.get("das_base_score")
                if das_base is not None:
                    try:
                        das_base_f = float(das_base)
                        if das_base_f > 0:
                            print(f"DAS ref  : {CYAN}{das_base_f:.2f}{RESET}  "
                                  f"(Gittensor validator score for the reference PR)")
                    except (ValueError, TypeError):
                        pass

            oracle_mean = _oracle_weighted()
            delta_vs_oracle = score - oracle_mean
            sign = "+" if delta_vs_oracle >= 0 else ""
            color = GREEN if delta_vs_oracle >= 0 else CYAN
            print(f"Oracle weighted: {oracle_mean:.2f}  (vs oracle: {color}{sign}{delta_vs_oracle:.2f}{RESET})")

            if args.no_sandbox:
                print(f"\n{CYAN}Note:{RESET} --no-sandbox scores ~3-5× above Docker CI.  "
                      "DAS ref above shows what the reference PR actually earned on the validator.")

            # --- Repair loop (--repair N, local only) ---
            if args.repair and args.no_sandbox and not tests_ok:
                test_out_for_repair = result.get("test_output", "")
                for repair_attempt in range(1, args.repair + 1):
                    print()
                    print(f"─" * 72)
                    print(f"Repair attempt {repair_attempt}/{args.repair}  (feeding test failure to agent)")
                    current_patch = patch
                    try:
                        repaired_patch = agent.repair(problem, current_patch, test_out_for_repair)
                    except Exception as exc:
                        print(f"  Repair error: {exc}", file=sys.stderr)
                        break

                    repaired_diff = repaired_patch.diff or ""
                    if not repaired_diff:
                        print("  Agent produced empty patch — stopping.")
                        break

                    print()
                    print("Repaired patch:")
                    _print_diff(repaired_diff)
                    print()

                    with tempfile.NamedTemporaryFile(suffix=".diff", mode="w", delete=False) as tmp2:
                        tmp2.write(repaired_diff)
                        repair_path = Path(tmp2.name)
                    try:
                        from benchmark.harness.score import score_patch as _score_patch
                        repair_result = _score_patch(problem_dir, repair_path)
                    finally:
                        repair_path.unlink(missing_ok=True)

                    tests_ok = repair_result.get("tests_passed", False)
                    repair_score = repair_result.get("final_score", 0.0)
                    test_out_for_repair = repair_result.get("test_output", "")
                    status2 = f"{GREEN}PASS{RESET}" if tests_ok else f"{RED}FAIL{RESET}"
                    print(f"Tests    : {status2}")
                    if tests_ok:
                        src_tok2 = repair_result.get("source_token_score", 0.0)
                        src_bar2 = "█" * int(round(src_tok2 / 25 * 20)) + "░" * (20 - int(round(src_tok2 / 25 * 20)))
                        print(f"Src tok  : {GREEN}{src_tok2:5.2f}{RESET} / 25.00  [{src_bar2}]")
                        print(f"Score    : {GREEN}{repair_score:.2f}{RESET} / 30.00")
                        patch = repaired_patch
                        diff = repaired_diff
                        if args.output:
                            Path(args.output).write_text(diff)
                            print(f"Saved    : {args.output}  (repaired)")
                        break
                    else:
                        lines2 = test_out_for_repair.strip().splitlines()
                        shown2 = lines2[-15:]
                        if len(lines2) > 15:
                            print(f"  [{len(lines2) - 15} lines omitted]")
                        for line in shown2:
                            print(f"  {line}")
                        print(f"Score    : {RED}0.00{RESET} / 30.00  (still failing)")
                        if repair_attempt == args.repair:
                            print(f"\nRepair limit reached — consider adjusting your agent or context.")
            elif args.repair and not args.no_sandbox:
                print(f"\n{CYAN}Note:{RESET} --repair requires --no-sandbox (Docker sandbox doesn't support in-loop repair)")
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


def cmd_serve_api(args: argparse.Namespace) -> None:
    """Start the REST API server for programmatic access to benchmark data."""
    from api.server import serve
    serve(host=args.host, port=args.port)


def cmd_mine(args: argparse.Namespace) -> None:
    """
    Autonomous mining daemon — run your agent against the current shard and
    auto-submit if you beat the champion.

    In --loop mode the daemon waits for the next shard rotation (Monday 00:00
    UTC) and repeats.  This is the "idle compute" mode: point it at your agent
    and walk away.

    Examples:
        python3 gitminer.py mine --agent agent/submissions/myhandle/agent.py --no-sandbox
        python3 gitminer.py mine --agent agent/submissions/myhandle/agent.py --loop
    """
    import time
    from datetime import datetime, timezone

    from benchmark.evaluate import run_evaluation

    agent_path = args.agent
    if not agent_path or not Path(agent_path).exists():
        print(f"Agent not found: {agent_path}", file=sys.stderr)
        sys.exit(1)

    handle = Path(agent_path).parent.name

    def _champion_score() -> float:
        lb_path = REPO_ROOT / "results" / "leaderboard.json"
        if not lb_path.exists():
            return 0.0
        entries = json.loads(lb_path.read_text())
        human = [e for e in entries if "Oracle" not in e.get("agent", "")]
        if not human:
            return 0.0
        row = human[0]
        return float(row.get("weighted_score") or row.get("score", 0.0))

    def _run_cycle() -> None:
        champ = _champion_score()
        oracle = _oracle_weighted()
        label = f"{champ:.2f}" if champ else "none yet"
        print(f"\n{'═'*60}")
        print(f"  gitminer mine — {handle}")
        print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
        print(f"  Champion: {label}    Oracle weighted: {oracle:.2f}")
        print(f"{'═'*60}\n")

        results = run_evaluation(
            agent_path=agent_path,
            use_sandbox=not args.no_sandbox,
        )
        problems = results.get("problems", [])
        if not problems:
            print("No problems evaluated.")
            return

        weighted_mean = results.get("weighted_mean_score") or (
            sum(p.get("final_score", 0.0) for p in problems) / len(problems)
        )
        passed = sum(1 for p in problems if p.get("tests_passed", False))
        print(f"\nResult: {weighted_mean:.2f} / 30.00 (weighted)   ({passed}/{len(problems)} tests passing)")

        if weighted_mean <= 0:
            print("Score is 0 — no tests passed. Keep improving before submitting.")
            return

        if champ and weighted_mean <= champ:
            gap = champ - weighted_mean
            print(f"Gap to champion: {gap:.2f} — keep improving!")
            return

        status = "BEAT CHAMPION" if champ else "FIRST SUBMISSION"
        oracle_gap = oracle - weighted_mean
        oracle_note = f"  (oracle: {oracle:.2f}, gap: {oracle_gap:+.2f})"
        print(f"\n{status}! Your weighted score: {weighted_mean:.2f}{oracle_note}")

        # Generate commit-reveal hash from agent file content
        agent_bytes = Path(agent_path).read_bytes()
        reveal_hash = hashlib.sha256(agent_bytes).hexdigest()
        print(f"\nCommit-reveal hash: {reveal_hash}")
        print(f"\nNext steps:")
        print(f"  1. Run: python3 gitminer.py submit {agent_path}")
        print(f"  2. Open a PR — the CI will score your agent and publish results.")
        print(f"  3. Post the hash {reveal_hash[:16]}... in your PR body to claim credit.\n")

        if args.loop:
            print("Submission ready. Waiting for next shard rotation to mine again...\n")

    def _seconds_to_next_monday() -> int:
        """Seconds until next Monday 00:00 UTC."""
        now = datetime.now(timezone.utc)
        days_ahead = (7 - now.weekday()) % 7 or 7
        return days_ahead * 86400 - (now.hour * 3600 + now.minute * 60 + now.second)

    _run_cycle()
    if args.loop:
        while True:
            wait = _seconds_to_next_monday()
            h, m = divmod(wait // 60, 60)
            print(f"Sleeping {h}h {m}m until next shard rotation...")
            time.sleep(wait)
            _run_cycle()


def cmd_doctor(args: argparse.Namespace) -> None:
    """
    Pre-flight environment check — verify everything is wired up before mining.

    Checks OPENROUTER_KEY, problem pool, leaderboard, allowed models, and
    optionally validates your agent file and handle.

    Example:
        python3 gitminer.py doctor
        python3 gitminer.py doctor --agent agent/submissions/myhandle/agent.py
    """
    import os

    passed: list[str] = []
    failed: list[str] = []

    def ok(label: str, detail: str) -> None:
        passed.append(label)
        print(f"  \033[32m✓\033[0m  {label:<28} {detail}")

    def fail(label: str, detail: str) -> None:
        failed.append(label)
        print(f"  \033[31m✗\033[0m  {label:<28} {detail}")

    def warn(label: str, detail: str) -> None:
        print(f"  \033[33m!\033[0m  {label:<28} {detail}")

    print("\ngitminer doctor — pre-flight check\n")

    # OPENROUTER_KEY
    key = os.environ.get("OPENROUTER_KEY", "")
    if key:
        masked = key[:4] + "..." + key[-4:] if len(key) > 8 else "set"
        ok("OPENROUTER_KEY", f"set  ({masked})")
    else:
        fail("OPENROUTER_KEY", "not set — export OPENROUTER_KEY=<your key>")

    # Problem pool
    pool_dir = REPO_ROOT / "benchmark" / "problems"
    n_problems = sum(1 for _ in pool_dir.glob("*/meta.json"))
    if n_problems > 0:
        ok("Problem pool", f"{n_problems} problems ready")
    else:
        fail("Problem pool", "empty — check your clone or re-run build_pool.py")

    # Leaderboard
    lb_path = REPO_ROOT / "results" / "leaderboard.json"
    if lb_path.exists():
        ok("Leaderboard", "results/leaderboard.json found")
    else:
        fail("Leaderboard", "results/leaderboard.json missing")

    # Allowed models list
    models_path = REPO_ROOT / "benchmark" / "harness" / "allowed_models.txt"
    if models_path.exists():
        models = [
            line.strip()
            for line in models_path.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]
        ok("Allowed models", f"{len(models)} models whitelisted")
    else:
        fail("Allowed models", f"not found at {models_path}")

    # Agent file (optional)
    agent_path = getattr(args, "agent", None)
    if agent_path:
        p = Path(agent_path)
        if p.exists():
            ok("Agent file", str(p))
            handle = p.parent.name
            if handle and handle not in ("submissions", "example", "agent"):
                ok("Handle", handle)
            else:
                warn("Handle", f"looks generic ({handle!r}) — use agent/submissions/<your-handle>/agent.py")
            # Check model against allowlist
            if models_path.exists():
                try:
                    src = p.read_text(errors="replace")
                    import re
                    model_hits = re.findall(r'"([\w\-./]+)"', src)
                    used = [m for m in model_hits if "/" in m and not m.startswith("http")]
                    for model in set(used):
                        if any(model.startswith(a) or a.startswith(model.split(":")[0]) for a in models):
                            pass  # plausibly whitelisted — don't spam per-model output
                except Exception:
                    pass
        else:
            fail("Agent file", f"not found: {agent_path}")

    # Shard connectivity
    try:
        from benchmark.evaluate import load_pool_config, select_shard
        config = load_pool_config()
        shard_dirs = sorted(pool_dir.glob("*/meta.json"))
        shard_size = config.get("shard_size", 30)
        ok("Shard config", f"size={shard_size}, rotation={config.get('rotation_policy', 'weekly')}")
    except Exception as e:
        fail("Shard config", str(e))

    print()
    if failed:
        print(f"\033[31mFailed {len(failed)} check(s)\033[0m: {', '.join(failed)}")
        print("Fix the above before running gitminer mine.\n")
        sys.exit(1)
    else:
        print(f"\033[32mAll {len(passed)} checks passed.\033[0m You're ready to mine!\n")


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
    p_run.add_argument("--repair", type=int, default=0, metavar="N",
                       help="After test failure, call agent.repair() up to N times "
                            "(requires --score --no-sandbox; not used in CI scoring)")
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
    p_problems.add_argument("--cat", choices=["python", "typescript", "rust", "jvm", "ruby"],
                            help="Filter by language category")
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
    p_hash = sub.add_parser("hash", help="Compute commit-reveal SHA-256 for your agent file")
    p_hash.add_argument("agent", help="Path to your agent.py file")
    p_hash.set_defaults(func=cmd_hash)

    # shard
    p_shard = sub.add_parser("shard", help="Print current week's 30-problem shard")
    p_shard.set_defaults(func=cmd_shard)

    # info
    p_info = sub.add_parser("info", help="Show full details for a single problem")
    p_info.add_argument("id", metavar="ID", help="Problem ID (e.g. 0463)")
    p_info.set_defaults(func=cmd_info)

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
        help="Model ID to embed in the PR body (default: deepseek/deepseek-chat)",
    )
    p_submit.add_argument(
        "--open-pr",
        action="store_true",
        help="Create branch, commit, push, and open the PR via gh (requires gh CLI)",
    )
    p_submit.set_defaults(func=cmd_submit)

    # serve-api
    p_api = sub.add_parser(
        "serve-api",
        help="Start the REST API server (default port 8083)",
    )
    p_api.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    p_api.add_argument("--port", type=int, default=8083, help="Port to listen on (default: 8083)")
    p_api.set_defaults(func=cmd_serve_api)

    # mine
    p_mine = sub.add_parser(
        "mine",
        help="Run your agent continuously; auto-submit when it beats the champion",
    )
    p_mine.add_argument("--agent", required=True, metavar="PATH",
                        help="Path to your agent.py")
    p_mine.add_argument("--no-sandbox", action="store_true",
                        help="Skip Docker sandbox (faster, ~2× higher scores — local dev only)")
    p_mine.add_argument("--loop", action="store_true",
                        help="Run continuously, sleeping between shard rotations (daemon mode)")
    p_mine.set_defaults(func=cmd_mine)

    # doctor
    p_doctor = sub.add_parser(
        "doctor",
        help="Pre-flight check: verify environment is ready to mine",
    )
    p_doctor.add_argument("--agent", metavar="PATH",
                          help="Path to your agent.py (optional — also validates handle and file)")
    p_doctor.set_defaults(func=cmd_doctor)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
