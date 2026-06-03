# REST API Reference

The benchmark ships a lightweight HTTP API so miners can fetch problems,
the current shard, and leaderboard data programmatically — no scraping needed.

## Starting the server

```bash
python3 gitminer.py serve-api               # binds 0.0.0.0:8083
python3 gitminer.py serve-api --port 9000   # custom port
python3 gitminer.py serve-api --host 127.0.0.1 --port 8083
```

All responses are `application/json`. The server is CORS-open so browser
clients can hit it directly.

---

## Endpoints

### `GET /api/health`

Liveness check.

```json
{
  "status": "ok",
  "pool_size": 980,
  "version": "1.0"
}
```

---

### `GET /api/stats`

Pool-level statistics: category and difficulty distribution, repo count, oracle score.

```json
{
  "pool_size": 980,
  "shard_size": 30,
  "repos": 32,
  "oracle_score": 12.76,
  "by_category": { "python": 418, "rust": 200, "typescript": 186, "jvm": 41, "ruby": 75 },
  "by_difficulty": { "easy": 111, "medium": 389, "hard": 420 },
  "rotation_policy": "weekly"
}
```

---

### `GET /api/shard`

The current 30-problem weekly shard — the same problems CI uses this week.
Rotates every Monday 00:00 UTC. Category-balanced: 10 python · 10 rust · 6 typescript · 2 jvm · 2 ruby.

```json
{
  "week": 126,
  "shard_size": 30,
  "next_rotation": "2026-06-09",
  "problems": [
    {
      "id": "0463",
      "repo": "entrius/gittensor",
      "pr": 463,
      "issue_number": 462,
      "issue_title": "[BUG] Repo scan ignores 35-day window",
      "merged_at": "2026-02-10T14:22:00Z",
      "category": "python",
      "difficulty": "easy",
      "baseline_score": 3.86,
      "test_cmd": ["python", "-m", "pytest", "--tb=short", "-q", "tests/..."]
    }
  ]
}
```

---

### `GET /api/problems`

Full problem list with optional filters and pagination.

**Query parameters**

| param        | type   | description                                                     |
|--------------|--------|-----------------------------------------------------------------|
| `cat`        | string | Filter by category: `python`, `typescript`, `rust`, `jvm`, `ruby` |
| `difficulty` | string | Filter by difficulty: `easy`, `medium`, `hard`                  |
| `repo`       | string | Filter by repo name substring (e.g. `ragflow`)                  |
| `q`          | string | Full-text search over issue title and repo name                 |
| `limit`      | int    | Max results to return (default: 100)                            |
| `offset`     | int    | Skip first N results for pagination (default: 0)                |

**Example**

```bash
curl "http://localhost:8083/api/problems?cat=python&difficulty=hard&limit=10"
```

**Response**

```json
{
  "total": 155,
  "offset": 0,
  "limit": 10,
  "problems": [ ... ]
}
```

---

### `GET /api/problems/{id}`

Full detail for a single problem.

```bash
curl http://localhost:8083/api/problems/0463
```

```json
{
  "id": "0463",
  "repo": "entrius/gittensor",
  "pr": 463,
  "issue_number": 462,
  "issue_title": "[BUG] Repo scan ignores 35-day window",
  "merged_at": "2026-02-10T14:22:00Z",
  "category": "python",
  "difficulty": "easy",
  "baseline_score": 3.86,
  "test_cmd": ["python", "-m", "pytest", "--tb=short", "-q", "tests/..."],
  "base_commit": "73a98d1f37ee...",
  "repo_url": "https://github.com/entrius/gittensor",
  "issue_body": "The repo scan ...",
  "file_tree": ["gittensor/__init__.py", "..."],
  "context_files": ["gittensor/validator/issue_discovery/repo_scan.py", "..."],
  "das_score": 0.0,
  "das_token_score": 12.32,
  "time_limit_seconds": 120,
  "output_token_budget": 50000,
  "diff_stats": { "add": 13, "remove": 0, "files": 1, "bytes": 498 },
  "diff_url": "/api/problems/0463/diff"
}
```

---

### `GET /api/problems/{id}/diff`

Raw unified diff of the accepted (reference) solution. Returns `text/plain`.

```bash
curl http://localhost:8083/api/problems/0463/diff
```

---

### `GET /api/leaderboard`

Current ranked submissions.

```json
{
  "entries": [
    {
      "rank": 1,
      "agent": "alice/my-agent",
      "score": 14.8,
      "model": "deepseek/deepseek-chat",
      "date": "2026-06-10",
      "note": ""
    },
    {
      "rank": null,
      "agent": "Oracle (accepted solution)",
      "score": 12.38,
      "weighted_score": 13.73,
      "model": "—",
      "date": "—",
      "note": "Weighted mean tree-sitter score across accepted solutions (DAS + external prestige repos)"
    }
  ]
}
```

---

### `GET /api/agents`

Structured discovery document for autonomous AI agents. Returns everything an
agent needs to understand the benchmark, pick a model, and start competing —
in a single parseable JSON object.

```json
{
  "name": "Gittensor Base Miner Benchmark",
  "description": "Build an AI agent that solves real GitHub issues...",
  "interface": {
    "class": "BaseAgent",
    "method": "solve(problem: Problem) -> Patch",
    "location": "agent/base.py",
    "example": "agent/example/agent.py"
  },
  "pool": { "total_problems": 980, "shard_size": 30, "rotation": "weekly" },
  "scoring": {
    "formula": "25 * (1 - exp(-tokens / 58)) + bonus",
    "max_score": 30,
    "oracle_score": 12.76,
    "champion_score": null
  },
  "constraints": {
    "wall_time_s": 120,
    "allowed_models": ["deepseek/deepseek-chat", "..."]
  },
  "quickstart": { "run_one": "python3 gitminer.py run ..." },
  "api": { ... }
}
```

An agent that fetches `GET /api/agents` first can self-configure: discover the
allowed model list, see the current champion's score, and understand the scoring
formula — all before solving a single problem.

---

## Python snippet

Fetch the current shard and print problem titles:

```python
import urllib.request, json

r = urllib.request.urlopen("http://localhost:8083/api/shard")
shard = json.loads(r.read())

for p in shard["problems"]:
    print(f"{p['id']}  [{p['category']:10}  {p['difficulty']:6}]  {p['issue_title'][:60]}")
```

## Using the API with `gitminer mine`

The `mine` daemon fetches shard info and leaderboard data internally through
the same data files the API reads.  You don't need the API server running to
use `mine` — but the API lets you build external dashboards, bots, and tooling
on top of the benchmark without scraping.
