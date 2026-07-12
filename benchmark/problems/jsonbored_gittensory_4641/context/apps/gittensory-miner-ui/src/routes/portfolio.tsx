import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import {
  fetchPortfolioQueue,
  summarizePortfolioQueue,
  type PortfolioQueueResult,
  type QueueStatus,
} from "../lib/portfolio-queue";

export const Route = createFileRoute("/portfolio")({
  component: PortfolioPage,
});

// Portfolio/queue summary cards (#4306): read-only counts by status over the local `miner_portfolio_queue`
// store, with a per-repo breakdown when the local queue spans repos. Same 4-state pattern as the run-history
// view (loading / error / fresh-install empty / populated).

const STATUS_LABELS: Record<QueueStatus, string> = {
  queued: "Queued",
  in_progress: "In progress",
  done: "Done",
};

const STATUS_CARD_CLASSES: Record<QueueStatus, string> = {
  queued: "border-sky-400/30 bg-sky-500/10 text-sky-100",
  in_progress: "border-amber-400/30 bg-amber-500/10 text-amber-100",
  done: "border-emerald-400/30 bg-emerald-500/10 text-emerald-100",
};

export function PortfolioQueueView({ result }: { result: PortfolioQueueResult | null }) {
  if (result === null) {
    return <p className="text-sm text-white/60">Loading local portfolio queue…</p>;
  }
  if (!result.ok) {
    return (
      <p role="alert" className="text-sm text-rose-300">
        Could not read the local portfolio queue: {result.error}
      </p>
    );
  }
  const summary = summarizePortfolioQueue(result.rows);
  if (summary.total === 0) {
    return (
      <p className="text-sm text-white/60">
        No queued work yet — the cards fill in once the miner enqueues its first portfolio item.
      </p>
    );
  }
  return (
    <div>
      <dl className="grid gap-4 sm:grid-cols-3">
        {(Object.keys(STATUS_LABELS) as QueueStatus[]).map((status) => (
          <div key={status} className={`rounded-xl border p-4 ${STATUS_CARD_CLASSES[status]}`}>
            <dt className="text-xs uppercase tracking-wider opacity-80">{STATUS_LABELS[status]}</dt>
            <dd className="mt-1 text-3xl font-semibold">{summary.counts[status]}</dd>
          </div>
        ))}
      </dl>
      {summary.byRepo.length > 1 && (
        <table className="mt-6 w-full text-left text-sm">
          <thead>
            <tr className="border-b border-white/10 text-xs uppercase tracking-wider text-white/50">
              <th scope="col" className="py-2 pr-4">
                Repository
              </th>
              <th scope="col" className="py-2 pr-4">
                Queued
              </th>
              <th scope="col" className="py-2 pr-4">
                In progress
              </th>
              <th scope="col" className="py-2">
                Done
              </th>
            </tr>
          </thead>
          <tbody>
            {summary.byRepo.map((repo) => (
              <tr key={repo.repoFullName} className="border-b border-white/5">
                <td className="py-2 pr-4 font-mono text-white/90">{repo.repoFullName}</td>
                <td className="py-2 pr-4 text-white/70">{repo.counts.queued}</td>
                <td className="py-2 pr-4 text-white/70">{repo.counts.in_progress}</td>
                <td className="py-2 text-white/70">{repo.counts.done}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export function PortfolioPage({
  loadPortfolioQueue = fetchPortfolioQueue,
}: {
  loadPortfolioQueue?: () => Promise<PortfolioQueueResult>;
}) {
  const [result, setResult] = useState<PortfolioQueueResult | null>(null);

  useEffect(() => {
    let cancelled = false;
    void loadPortfolioQueue().then((loaded) => {
      if (!cancelled) setResult(loaded);
    });
    return () => {
      cancelled = true;
    };
  }, [loadPortfolioQueue]);

  return (
    <section className="rounded-xl border border-white/10 bg-white/5 p-6">
      <h2 className="text-xl font-semibold">Portfolio queue</h2>
      <p className="mt-1 text-sm text-white/60">
        Local, read-only summary of the miner&apos;s portfolio queue (`miner_portfolio_queue`).
      </p>
      <div className="mt-4">
        <PortfolioQueueView result={result} />
      </div>
    </section>
  );
}