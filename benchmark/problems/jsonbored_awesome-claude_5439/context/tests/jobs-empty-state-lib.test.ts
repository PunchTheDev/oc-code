import { describe, expect, it } from "vitest";

import {
  activeJobsFilters,
  jobsEmptyStateSuggestions,
  type JobsFilterSlice,
} from "@/lib/jobs-empty-state-lib";

const NONE: JobsFilterSlice = {
  q: "",
  tier: "all",
  remote: "all",
  type: "all",
  freshOnly: false,
  featuredOnly: false,
};

describe("activeJobsFilters", () => {
  it("returns [] when nothing is narrowing the set", () => {
    expect(activeJobsFilters(NONE)).toEqual([]);
  });

  it("lists exactly the axes that differ from their default", () => {
    expect(
      activeJobsFilters({
        ...NONE,
        q: "rust",
        tier: "featured",
        freshOnly: true,
      }),
    ).toEqual(["q", "tier", "freshOnly"]);
  });
});

describe("jobsEmptyStateSuggestions", () => {
  it("returns [] when no filter is active (caller should skip the enhanced state)", () => {
    expect(jobsEmptyStateSuggestions(NONE, () => 5)).toEqual([]);
  });

  it("suggests relaxing each active filter, ranked by roles recovered", () => {
    const filters: JobsFilterSlice = {
      ...NONE,
      q: "rust",
      tier: "featured",
      freshOnly: true,
    };
    // Relaxing tier recovers the most, then q, then freshOnly.
    const counts: Record<string, number> = { tier: 9, q: 4, freshOnly: 1 };
    const out = jobsEmptyStateSuggestions(filters, (slice) => {
      if ("tier" in slice) return counts.tier;
      if ("q" in slice) return counts.q;
      if ("freshOnly" in slice) return counts.freshOnly;
      return 0;
    });
    expect(out.map((s) => s.axis)).toEqual(["tier", "q", "freshOnly"]);
    expect(out.map((s) => s.count)).toEqual([9, 4, 1]);
    expect(out[1].label).toBe('Clear "rust"');
    expect(out[0].patch).toEqual({ tier: "all" });
  });

  it("drops suggestions that recover zero roles", () => {
    const filters: JobsFilterSlice = {
      ...NONE,
      tier: "featured",
      remote: "remote",
    };
    // Relaxing tier still yields 0 (some other filter is the real cause) → dropped.
    const out = jobsEmptyStateSuggestions(filters, (slice) =>
      "remote" in slice ? 3 : 0,
    );
    expect(out.map((s) => s.axis)).toEqual(["remote"]);
    expect(out[0].count).toBe(3);
  });
});