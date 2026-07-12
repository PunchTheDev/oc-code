import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  fetchPortfolioQueue,
  PORTFOLIO_QUEUE_API_PATH,
  summarizePortfolioQueue,
  type PortfolioQueueResult,
  type PortfolioQueueRow,
} from "./lib/portfolio-queue";
import { PortfolioPage, PortfolioQueueView } from "./routes/portfolio";
import { handlePortfolioQueueRequest, type PortfolioQueueApiDeps } from "../vite-portfolio-queue-api";

const fixtureRows: PortfolioQueueRow[] = [
  {
    repoFullName: "acme/widgets",
    identifier: "issue:12",
    priority: 5,
    status: "queued",
    enqueuedAt: "2026-07-10T06:00:00.000Z",
  },
  {
    repoFullName: "acme/widgets",
    identifier: "issue:13",
    priority: 3,
    status: "in_progress",
    enqueuedAt: "2026-07-10T06:05:00.000Z",
  },
  {
    repoFullName: "acme/gadgets",
    identifier: "issue:7",
    priority: 8,
    status: "done",
    enqueuedAt: "2026-07-10T05:00:00.000Z",
  },
  {
    repoFullName: "acme/gadgets",
    identifier: "issue:8",
    priority: 1,
    status: "queued",
    enqueuedAt: "2026-07-10T05:30:00.000Z",
  },
];

describe("summarizePortfolioQueue (#4306)", () => {
  it("counts rows by status and per repo, sorted by repo name", () => {
    const summary = summarizePortfolioQueue(fixtureRows);
    expect(summary.total).toBe(4);
    expect(summary.counts).toEqual({ queued: 2, in_progress: 1, done: 1 });
    expect(summary.byRepo).toEqual([
      { repoFullName: "acme/gadgets", counts: { queued: 1, in_progress: 0, done: 1 }, total: 2 },
      { repoFullName: "acme/widgets", counts: { queued: 1, in_progress: 1, done: 0 }, total: 2 },
    ]);
  });

  it("summarizes an empty queue to zeros with no repo rows", () => {
    expect(summarizePortfolioQueue([])).toEqual({
      total: 0,
      counts: { queued: 0, in_progress: 0, done: 0 },
      byRepo: [],
    });
  });
});

describe("PortfolioQueueView (#4306)", () => {
  it("renders one card per status with the aggregated counts", () => {
    render(<PortfolioQueueView result={{ ok: true, rows: fixtureRows }} />);
    // The status words also appear as per-repo column headers, so target the card <dt> elements (first match).
    expect(screen.getAllByText("Queued")[0]!.nextSibling?.textContent).toBe("2");
    expect(screen.getAllByText("In progress")[0]!.nextSibling?.textContent).toBe("1");
    expect(screen.getAllByText("Done")[0]!.nextSibling?.textContent).toBe("1");
  });

  it("renders the per-repo breakdown when the queue spans multiple repos", () => {
    render(<PortfolioQueueView result={{ ok: true, rows: fixtureRows }} />);
    expect(screen.getByRole("columnheader", { name: "Repository" })).toBeTruthy();
    expect(screen.getByText("acme/widgets")).toBeTruthy();
    expect(screen.getByText("acme/gadgets")).toBeTruthy();
  });

  it("omits the per-repo table for a single-repo queue (cards only)", () => {
    render(<PortfolioQueueView result={{ ok: true, rows: fixtureRows.slice(0, 2) }} />);
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.getByText("Queued").nextSibling?.textContent).toBe("1");
  });

  it("renders the fresh-install empty state without erroring", () => {
    render(<PortfolioQueueView result={{ ok: true, rows: [] }} />);
    expect(screen.getByText(/No queued work yet/i)).toBeTruthy();
  });

  it("renders an error message when the local API is unreachable", () => {
    render(<PortfolioQueueView result={{ ok: false, error: "connection refused" }} />);
    expect(screen.getByRole("alert").textContent).toContain("connection refused");
  });

  it("renders the loading state before the first result arrives", () => {
    render(<PortfolioQueueView result={null} />);
    expect(screen.getByText(/Loading local portfolio queue/i)).toBeTruthy();
  });
});

describe("PortfolioPage (#4306)", () => {
  it("loads rows through the injected loader and renders the cards", async () => {
    const loadPortfolioQueue = async (): Promise<PortfolioQueueResult> => ({ ok: true, rows: fixtureRows });
    render(<PortfolioPage loadPortfolioQueue={loadPortfolioQueue} />);
    expect(screen.getByRole("heading", { name: "Portfolio queue" })).toBeTruthy();
    await waitFor(() => expect(screen.getByText("acme/widgets")).toBeTruthy());
  });
});

describe("fetchPortfolioQueue (#4306)", () => {
  const jsonResponse = (status: number, payload: unknown) =>
    ({ ok: status >= 200 && status < 300, status, json: async () => payload }) as unknown as Response;

  it("returns typed rows from a well-formed payload, requesting the local API path", async () => {
    let requested: string | undefined;
    const result = await fetchPortfolioQueue(async (input) => {
      requested = String(input);
      return jsonResponse(200, { rows: fixtureRows });
    });
    expect(requested).toBe(PORTFOLIO_QUEUE_API_PATH);
    expect(result).toEqual({ ok: true, rows: fixtureRows });
  });

  it("surfaces non-2xx, malformed payloads, and thrown fetches as typed errors", async () => {
    expect(await fetchPortfolioQueue(async () => jsonResponse(500, {}))).toEqual({
      ok: false,
      error: "local portfolio-queue API responded 500",
    });
    expect(await fetchPortfolioQueue(async () => jsonResponse(200, { rows: "nope" }))).toMatchObject({ ok: false });
    expect(
      await fetchPortfolioQueue(async () => jsonResponse(200, { rows: [{ ...fixtureRows[0], status: "warp" }] })),
    ).toMatchObject({ ok: false });
    expect(
      await fetchPortfolioQueue(async () => {
        throw new Error("connection refused");
      }),
    ).toEqual({ ok: false, error: "connection refused" });
  });
});

describe("handlePortfolioQueueRequest (#4306)", () => {
  const rows = fixtureRows;
  function deps(overrides: Partial<PortfolioQueueApiDeps> = {}): PortfolioQueueApiDeps {
    return {
      loadPortfolioQueueModule: async () => ({
        resolvePortfolioQueueDbPath: () => "/home/miner/.config/gittensory-miner/portfolio-queue.sqlite3",
        listQueue: () => rows,
      }),
      fileExists: () => true,
      ...overrides,
    };
  }

  it("serves the queue rows via the existing portfolio-queue.js exports", async () => {
    const handled = await handlePortfolioQueueRequest("GET", "/api/portfolio-queue", deps());
    expect(handled).toEqual({ status: 200, body: JSON.stringify({ rows }) });
  });

  it("serves [] on a fresh install WITHOUT initializing the store", async () => {
    let listed = false;
    const handled = await handlePortfolioQueueRequest(
      "GET",
      "/api/portfolio-queue",
      deps({
        loadPortfolioQueueModule: async () => ({
          resolvePortfolioQueueDbPath: () => "/nowhere/portfolio-queue.sqlite3",
          listQueue: () => {
            listed = true;
            return rows;
          },
        }),
        fileExists: () => false,
      }),
    );
    expect(handled).toEqual({ status: 200, body: JSON.stringify({ rows: [] }) });
    expect(listed).toBe(false);
  });

  it("falls through (null) for other paths and non-GET methods", async () => {
    expect(await handlePortfolioQueueRequest("GET", "/api/run-state", deps())).toBeNull();
    expect(await handlePortfolioQueueRequest("POST", "/api/portfolio-queue", deps())).toBeNull();
  });

  it("surfaces a store read failure as a 500 with a safe message", async () => {
    const handled = await handlePortfolioQueueRequest(
      "GET",
      "/api/portfolio-queue",
      deps({
        loadPortfolioQueueModule: async () => {
          throw new Error("sqlite locked");
        },
      }),
    );
    expect(handled).toEqual({ status: 500, body: JSON.stringify({ error: "sqlite locked" }) });
  });
});