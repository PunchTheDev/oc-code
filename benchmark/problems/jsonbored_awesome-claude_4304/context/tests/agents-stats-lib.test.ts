import { describe, expect, it } from "vitest";

import { buildAgentsReport } from "@/lib/agents-stats-lib";
import { buildAgentsReport as buildAgentsReportFromWrapper } from "@/lib/agents-stats";
import { buildReportDataset, REPORT_PATHS } from "@/lib/data-reports";
import { ENTRIES, REGISTRY_GENERATED_AT } from "@/data/entries";
import type { Entry } from "@/types/registry";

function agent(partial: Partial<Entry>): Entry {
  return {
    category: "agents",
    trust: "trusted",
    source: "source-backed",
    tags: [],
    ...partial,
  } as Entry;
}

describe("agents-stats-lib buildAgentsReport (deterministic)", () => {
  const sample = [
    agent({ tags: ["testing"], safetyNotes: "x", privacyNotes: "y" }),
    agent({ tags: ["review"], safetyNotes: "x", prerequisites: ["node"] }),
    agent({ tags: ["sre"], privacyNotes: "y", source: "external" }),
    agent({ tags: ["testing"] }),
  ];

  it("is stable and reports the right totals/stats", () => {
    const a = buildAgentsReport(sample, "2026-06-20");
    const b = buildAgentsReport(sample, "2026-06-20");
    expect(a).toEqual(b);
    expect(a.slug).toBe("/state-of-ai-agents");
    expect(a.exportSlug).toBe("ai-agents");
    expect(a.total).toBe(4);
    expect(a.stats.find((s) => s.key === "documented")?.value).toBe(25);
  });

  it("breaks down safety/privacy disclosure into both/only/neither", () => {
    const model = buildAgentsReport(sample, "2026-06-20");
    const disclosure = model.dimensions.find((d) => d.key === "disclosure");
    expect(disclosure).toBeDefined();
    const byLabel = new Map(disclosure!.rows.map((r) => [r.label, r.count]));
    expect(byLabel.get("Safety & privacy")).toBe(1);
    expect(byLabel.get("Safety only")).toBe(1);
    expect(byLabel.get("Privacy only")).toBe(1);
    expect(byLabel.get("Neither documented")).toBe(1);
  });

  it("drops degenerate single-bucket dimensions", () => {
    const uniform = [
      agent({ tags: ["testing"], safetyNotes: "x", privacyNotes: "y" }),
      agent({ tags: ["review"], safetyNotes: "x", privacyNotes: "y" }),
    ];
    const model = buildAgentsReport(uniform, "2026-06-20");
    for (const dimension of model.dimensions) {
      expect(dimension.rows.length).toBeGreaterThan(1);
    }
    expect(model.dimensions.some((d) => d.key === "disclosure")).toBe(false);
  });

  it("excludes mechanism tags from the use-case distribution", () => {
    const model = buildAgentsReport(
      [
        agent({ tags: ["agents", "claude-code", "testing"] }),
        agent({ tags: ["Agent", "CI", "testing"] }),
      ],
      "2026-06-20",
    );
    const useCases = model.dimensions.find((d) => d.key === "use-cases");
    expect(useCases?.rows.map((row) => row.label)).toEqual(["testing", "ci"]);
  });

  it("counts list-style safety and privacy notes", () => {
    const model = buildAgentsReport(
      [
        agent({
          safetyNotesList: ["  runs shell  "],
          privacyNotesList: ["stores logs"],
        }),
      ],
      "2026-06-20",
    );
    expect(model.stats.find((s) => s.key === "documented")?.value).toBe(100);
  });

  it("reports prerequisite and source-backed headline stats", () => {
    const model = buildAgentsReport(
      [
        agent({ hasPrerequisites: true, source: "first-party" }),
        agent({ source: "unverified" }),
      ],
      "2026-06-20",
    );
    expect(model.stats.find((s) => s.key === "ready")?.value).toBe(50);
    expect(model.stats.find((s) => s.key === "source-backed")?.value).toBe(50);
    const prerequisites = model.dimensions.find(
      (d) => d.key === "prerequisites",
    );
    expect(prerequisites?.rows).toEqual([
      { label: "Requires prerequisites", count: 1, pct: 50 },
      { label: "No prerequisites", count: 1, pct: 50 },
    ]);
  });

  it("returns an empty report when the registry has no agents", () => {
    const model = buildAgentsReport(
      [agent({ category: "skills", tags: ["testing"] }) as Entry],
      "2026-06-20",
    );
    expect(model.total).toBe(0);
    expect(model.dimensions).toEqual([]);
    expect(model.stats.find((s) => s.key === "total")?.value).toBe(0);
  });

  it("keeps the public wrapper re-export aligned with the lib module", () => {
    const fromLib = buildAgentsReport(sample, "2026-06-20");
    const fromWrapper = buildAgentsReportFromWrapper(sample, "2026-06-20");
    expect(fromWrapper).toEqual(fromLib);
  });
});

describe("agents-stats-lib report Dataset JSON-LD", () => {
  it("measures every stat and dimension", () => {
    const model = buildAgentsReport(
      [
        agent({ tags: ["testing"], safetyNotes: "x", privacyNotes: "y" }),
        agent({ tags: ["review"] }),
      ],
      "2026-06-20",
    );
    const ds = buildReportDataset(model) as Record<string, unknown>;
    expect(ds["@type"]).toBe("Dataset");
    expect(ds.dateModified).toBe("2026-06-20");
    const measured = ds.variableMeasured as string[];
    for (const stat of model.stats) expect(measured).toContain(stat.label);
    for (const dimension of model.dimensions)
      expect(measured).toContain(dimension.title);
    expect(new Set(measured).size).toBe(measured.length);
  });
});

describe("agents-stats-lib sitemap manifest", () => {
  it("lists the new report so it gets indexed", () => {
    expect(REPORT_PATHS).toContain("/state-of-ai-agents");
    expect(new Set(REPORT_PATHS).size).toBe(REPORT_PATHS.length);
  });
});

describe("agents-stats-lib real registry data", () => {
  const asOf = String(REGISTRY_GENERATED_AT).slice(0, 10);
  const model = buildAgentsReport(ENTRIES, asOf);

  it("covers a substantial agents corpus with informative dimensions", () => {
    expect(model.total).toBeGreaterThan(50);
    expect(model.dimensions.length).toBeGreaterThanOrEqual(2);
    for (const dimension of model.dimensions) {
      expect(dimension.rows.length).toBeGreaterThan(1);
    }
  });

  it("includes trust and source dimensions when the sample is diverse", () => {
    const model = buildAgentsReport(
      [
        agent({ trust: "trusted", source: "source-backed", tags: ["testing"] }),
        agent({ trust: "review", source: "external", tags: ["review"] }),
        agent({ trust: "limited", source: "unverified", tags: ["sre"] }),
      ],
      "2026-06-20",
    );
    const keys = model.dimensions.map((dimension) => dimension.key);
    expect(keys).toEqual(
      expect.arrayContaining(["source-provenance", "trust-level"]),
    );
  });
});