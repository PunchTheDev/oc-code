// Read-only client + pure aggregation for the local portfolio-queue API (#4306). The view is summary CARDS,
// so the aggregation lives here (client-side over `listQueue()`'s rows, per the issue's guidance) as pure,
// unit-testable functions — the middleware serves raw rows and duplicates no aggregation.

export const PORTFOLIO_QUEUE_API_PATH = "/api/portfolio-queue";

export const QUEUE_STATUSES = ["queued", "in_progress", "done"] as const;

export type QueueStatus = (typeof QUEUE_STATUSES)[number];

/** One `miner_portfolio_queue` row as served by the local API — mirrors `portfolio-queue.js`'s `rowToEntry`. */
export type PortfolioQueueRow = {
  repoFullName: string;
  identifier: string;
  priority: number;
  status: QueueStatus;
  enqueuedAt: string;
};

export type QueueStatusCounts = Record<QueueStatus, number>;

export type RepoQueueSummary = { repoFullName: string; counts: QueueStatusCounts; total: number };

export type PortfolioQueueSummary = {
  total: number;
  counts: QueueStatusCounts;
  byRepo: RepoQueueSummary[];
};

export type PortfolioQueueResult = { ok: true; rows: PortfolioQueueRow[] } | { ok: false; error: string };

function isQueueStatus(value: unknown): value is QueueStatus {
  return value === "queued" || value === "in_progress" || value === "done";
}

function isPortfolioQueueRow(value: unknown): value is PortfolioQueueRow {
  if (typeof value !== "object" || value === null) return false;
  const row = value as Record<string, unknown>;
  return (
    typeof row.repoFullName === "string" &&
    typeof row.identifier === "string" &&
    typeof row.priority === "number" &&
    typeof row.enqueuedAt === "string" &&
    isQueueStatus(row.status)
  );
}

const emptyCounts = (): QueueStatusCounts => ({ queued: 0, in_progress: 0, done: 0 });

/** Pure aggregation: overall counts by status plus a per-repo breakdown (sorted by repo name for stable cards).
 *  The cross-repo section is the schema's own multi-repo shape surfaced as data — the view decides rendering. */
export function summarizePortfolioQueue(rows: PortfolioQueueRow[]): PortfolioQueueSummary {
  const counts = emptyCounts();
  const perRepo = new Map<string, QueueStatusCounts>();
  for (const row of rows) {
    counts[row.status] += 1;
    const repoCounts = perRepo.get(row.repoFullName) ?? emptyCounts();
    repoCounts[row.status] += 1;
    perRepo.set(row.repoFullName, repoCounts);
  }
  const byRepo = [...perRepo.entries()]
    .map(([repoFullName, repoCounts]) => ({
      repoFullName,
      counts: repoCounts,
      total: repoCounts.queued + repoCounts.in_progress + repoCounts.done,
    }))
    .sort((a, b) => a.repoFullName.localeCompare(b.repoFullName));
  return { total: rows.length, counts, byRepo };
}

/** Fetch the local queue rows; failures surface as a typed error result the view renders, never a crash. */
export async function fetchPortfolioQueue(fetchImpl: typeof fetch = fetch): Promise<PortfolioQueueResult> {
  try {
    const response = await fetchImpl(PORTFOLIO_QUEUE_API_PATH);
    if (!response.ok) return { ok: false, error: `local portfolio-queue API responded ${response.status}` };
    const payload: unknown = await response.json();
    const rows = (payload as { rows?: unknown }).rows;
    if (!Array.isArray(rows) || !rows.every(isPortfolioQueueRow)) {
      return { ok: false, error: "local portfolio-queue API returned an unexpected payload shape" };
    }
    return { ok: true, rows };
  } catch (error) {
    return {
      ok: false,
      error: error instanceof Error ? error.message : "failed to reach the local portfolio-queue API",
    };
  }
}