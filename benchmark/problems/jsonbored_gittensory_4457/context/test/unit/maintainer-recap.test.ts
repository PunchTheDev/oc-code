import { describe, expect, it } from "vitest";
import { buildMaintainerRecap, type MaintainerRecapRepoInput } from "../../src/services/maintainer-recap";
import type { OutcomeCalibration } from "../../src/services/outcome-calibration";

const GEN = "2026-07-08T00:00:00.000Z";

/** Build one repo's injected inputs from the handful of counts this builder actually reads. */
function repoInput(
  repoFullName: string,
  c: {
    blocked?: number;
    blockedThenMerged?: number;
    overridden?: number;
    totalResolved?: number;
    merged?: number;
    closed?: number;
    reversals?: number;
    emptyBands?: boolean;
  } = {},
): MaintainerRecapRepoInput {
  const blocked = c.blocked ?? 0;
  const blockedThenMerged = c.blockedThenMerged ?? 0;
  const bands: OutcomeCalibration["slop"]["bands"] = c.emptyBands
    ? []
    : [{ band: "clean", sampleSize: 0, merged: c.merged ?? 0, closed: c.closed ?? 0, mergeRate: 0 }];
  return {
    gatePrecision: {
      repoFullName,
      generatedAt: GEN,
      windowDays: 7,
      perGateType: [{ gateType: "missing_linked_issue", blocked, blockedThenMerged, overridden: c.overridden ?? 0, falsePositiveRate: null }],
      overall: { blocked, blockedThenMerged, falsePositiveRate: null },
      signals: [],
    },
    calibration: {
      repoFullName,
      generatedAt: GEN,
      windowDays: 7,
      slop: { totalResolved: c.totalResolved ?? 0, bands, overallMergeRate: null, discriminates: null },
      recommendations: { total: 0, positive: 0, negative: c.reversals ?? 0, pending: 0, positiveRate: null },
      signals: [],
    },
  };
}

describe("buildMaintainerRecap (#2239)", () => {
  it("zeroes everything for an empty window and reports the null false-positive rate", () => {
    // windowDays omitted ⇒ normalizeWindowDays' non-finite arm ⇒ the 7-day default.
    const report = buildMaintainerRecap({ generatedAt: GEN, repos: [] });
    expect(report.windowDays).toBe(7);
    expect(report.repos).toEqual([]);
    expect(report.totals).toMatchObject({ reviewed: 0, merged: 0, closed: 0, blocked: 0, gateFalsePositives: 0, gateOverrides: 0, reversals: 0, gateFalsePositiveRate: null });
    // blocked === 0 ⇒ rate is null ⇒ the "not enough blocked PRs" summary arm.
    expect(report.summary[1]).toContain("not enough blocked PRs");
    expect(report.summary[0]).toContain("0 repo(s)");
  });

  it("folds a single repo's counts and computes the gate false-positive rate", () => {
    const report = buildMaintainerRecap({
      generatedAt: GEN,
      windowDays: 14, // provided ⇒ normalizeWindowDays' finite/clamp arm
      repos: [repoInput("owner/repo-a", { blocked: 10, blockedThenMerged: 2, overridden: 3, totalResolved: 8, merged: 6, closed: 2, reversals: 1 })],
    });
    expect(report.windowDays).toBe(14);
    expect(report.repos).toHaveLength(1);
    expect(report.repos[0]).toMatchObject({ repoFullName: "owner/repo-a", reviewed: 8, merged: 6, closed: 2, gateFalsePositives: 2, gateOverrides: 3, reversals: 1 });
    expect(report.totals).toMatchObject({ reviewed: 8, merged: 6, closed: 2, blocked: 10, gateFalsePositives: 2, gateOverrides: 3, reversals: 1, gateFalsePositiveRate: 0.2 });
    // blocked > 0 ⇒ the populated summary arm with the percentage.
    expect(report.summary[1]).toContain("Gate false-positive rate: 20%");
    expect(report.summary[1]).toContain("(2/10 block(s) later merged)");
    expect(report.summary[2]).toContain("3 maintainer override(s), 1 recommendation reversal(s)");
  });

  it("aggregates across multiple repos (including one with no slop bands)", () => {
    const report = buildMaintainerRecap({
      generatedAt: GEN,
      windowDays: 30,
      repos: [
        repoInput("owner/repo-a", { blocked: 4, blockedThenMerged: 1, overridden: 1, totalResolved: 5, merged: 4, closed: 1, reversals: 2 }),
        repoInput("owner/repo-b", { blocked: 6, blockedThenMerged: 3, overridden: 2, totalResolved: 0, reversals: 1, emptyBands: true }),
      ],
    });
    expect(report.repos).toHaveLength(2);
    expect(report.repos[1]).toMatchObject({ repoFullName: "owner/repo-b", reviewed: 0, merged: 0, closed: 0, gateFalsePositives: 3, gateOverrides: 2, reversals: 1 });
    expect(report.totals).toMatchObject({ reviewed: 5, merged: 4, closed: 1, blocked: 10, gateFalsePositives: 4, gateOverrides: 3, reversals: 3, gateFalsePositiveRate: 0.4 });
  });

  it("clamps an out-of-range window to the max and a zero to the min", () => {
    expect(buildMaintainerRecap({ generatedAt: GEN, windowDays: 999, repos: [] }).windowDays).toBe(90);
    expect(buildMaintainerRecap({ generatedAt: GEN, windowDays: 0, repos: [] }).windowDays).toBe(1);
  });

  it("scrubs a local-path leak out of the repo name (public-safe by construction)", () => {
    const report = buildMaintainerRecap({ generatedAt: GEN, repos: [repoInput("/Users/secret/repo", { blocked: 1, blockedThenMerged: 0 })] });
    expect(report.repos[0]?.repoFullName).toContain("<redacted-path>");
    expect(report.repos[0]?.repoFullName).not.toContain("/Users/secret");
  });
});
