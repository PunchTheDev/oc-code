# REST API Reference

The benchmark ships a lightweight HTTP API so miners can fetch problems,
the current shard, and leaderboard data programmatically — no scraping needed.

## Starting the server

```bash
python gitminer.py serve-api               # binds 0.0.0.0:8083
python gitminer.py serve-api --port 9000   # custom port
python gitminer.py serve-api --host 127.0.0.1 --port 8083
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
  "pool_size": 397,
  "version": "1.0"
}
```

---

### `GET /api/stats`

Pool-level statistics: language and difficulty distribution, repo count, mean baseline.

```json
{
  "pool_size": 397,
  "shard_size": 30,
  "repos": 13,
  "mean_baseline": 23.05,
  "by_language": { "py": 200, "js": 68, "rs": 40, "java": 34 },
  "by_difficulty": { "easy": 80, "medium": 140, "hard": 122 },
  "rotation_policy": "weekly"
}
```

---

### `GET /api/shard`

The current 30-problem weekly shard — the same problems CI uses this week.
Rotates every Monday 00:00 UTC.

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
      "issue_title": "Add repo-level open PR exclusions",
      "merged_at": "2026-02-10T14:22:00Z",
      "language": "py",
      "difficulty": "medium",
      "baseline_score": 21.5,
      "test_cmd": ["python", "-m", "pytest", "--tb=short", "-q", "tests/..."]
    }
  ]
}
```

---

### `GET /api/problems`

Full problem list with optional filters and pagination.

**Query parameters**

| param       | type   | description                                          |
|-------------|--------|------------------------------------------------------|
| `lang`      | string | Filter by language: `py`, `js`, `rs`, `java`         |
| `difficulty`| string | Filter by difficulty: `easy`, `medium`, `hard`       |
| `repo`      | string | Filter by repo name substring (e.g. `ragflow`)       |
| `q`         | string | Full-text search over issue title and repo name      |
| `limit`     | int    | Max results to return (default: 100)                 |
| `offset`    | int    | Skip first N results for pagination (default: 0)     |

**Example**

```bash
curl "http://localhost:8083/api/problems?lang=py&difficulty=hard&limit=10"
```

**Response**

```json
{
  "total": 122,
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
  "issue_title": "Add repo-level open PR exclusions",
  "merged_at": "2026-02-10T14:22:00Z",
  "language": "py",
  "difficulty": "medium",
  "baseline_score": 21.5,
  "test_cmd": ["python", "-m", "pytest", "--tb=short", "-q", "tests/..."],
  "base_commit": "abc123...",
  "repo_url": "https://github.com/entrius/gittensor",
  "issue_body": "Please add the ability to ...",
  "file_tree": ["gittensor/__init__.py", "..."],
  "context_files": ["gittensor/validator/evaluation/reward.py", "..."],
  "das_score": "12.34",
  "das_token_score": "15.67",
  "time_limit_seconds": 120,
  "output_token_budget": 50000
}
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
      "score": 19.4,
      "model": "deepseek/deepseek-chat",
      "date": "2026-06-01",
      "note": ""
    },
    {
      "rank": null,
      "agent": "Oracle (accepted solution)",
      "score": 23.05,
      "model": "—",
      "date": "—",
      "note": "Upper bound (accepted solutions mean)"
    }
  ]
}
```

---

## Python snippet

Fetch the current shard and print problem titles:

```python
import urllib.request, json

r = urllib.request.urlopen("http://localhost:8083/api/shard")
shard = json.loads(r.read())

for p in shard["problems"]:
    print(f"{p['id']}  [{p['difficulty']:6}]  {p['issue_title'][:60]}")
```

## Using the API with `gitminer mine`

The `mine` daemon fetches shard info and leaderboard data internally through
the same data files the API reads.  You don't need the API server running to
use `mine` — but the API lets you build external dashboards, bots, and tooling
on top of the benchmark without scraping.
