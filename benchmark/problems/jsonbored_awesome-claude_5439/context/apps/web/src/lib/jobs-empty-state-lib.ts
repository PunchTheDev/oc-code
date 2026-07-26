// Pure helper for the jobs board's zero-result empty state: given the active
// filters and a counter, produce per-filter "relax this to see N roles"
// suggestions. Split out of the route so the ranking logic is unit-testable
// without the React component. Mirrors browse.tsx's empty-state guidance.

export type JobsFilterSlice = {
  q: string;
  tier: string; // JobTier | "all"
  remote: string; // "all" | "remote" | "onsite"
  type: string; // "all" | specific type
  freshOnly: boolean;
  featuredOnly: boolean;
};

export type JobsFilterAxis = keyof JobsFilterSlice;

export type JobsEmptyStateSuggestion = {
  axis: JobsFilterAxis;
  /** Human label for the relax action, e.g. `Any tier` or `Clear "rust"`. */
  label: string;
  /** How many roles match once this one filter is reset to its default. */
  count: number;
  /** The single-axis reset to apply. */
  patch: Partial<JobsFilterSlice>;
};

/** Which axes are currently narrowing the result set (i.e. not at their default). */
export function activeJobsFilters(f: JobsFilterSlice): JobsFilterAxis[] {
  const axes: JobsFilterAxis[] = [];
  if (f.q) axes.push("q");
  if (f.tier !== "all") axes.push("tier");
  if (f.remote !== "all") axes.push("remote");
  if (f.type !== "all") axes.push("type");
  if (f.freshOnly) axes.push("freshOnly");
  if (f.featuredOnly) axes.push("featuredOnly");
  return axes;
}

function labelFor(axis: JobsFilterAxis, f: JobsFilterSlice): string {
  switch (axis) {
    case "q":
      return `Clear "${f.q}"`;
    case "tier":
      return "Any tier";
    case "remote":
      return "Any location";
    case "type":
      return "Any type";
    case "freshOnly":
      return "Include older roles";
    case "featuredOnly":
      return "Include all tiers";
  }
}

const RESET: Record<JobsFilterAxis, Partial<JobsFilterSlice>> = {
  q: { q: "" },
  tier: { tier: "all" },
  remote: { remote: "all" },
  type: { type: "all" },
  freshOnly: { freshOnly: false },
  featuredOnly: { featuredOnly: false },
};

/**
 * For each active filter, compute how many roles would match if that one filter
 * were relaxed, keeping the rest. Only suggestions that actually recover roles
 * (`count > 0`) are returned, most-recovered first, so the empty state points at
 * the filter most likely causing the dead end. Returns `[]` when no filter is
 * active (the caller should not render the enhanced state then).
 */
export function jobsEmptyStateSuggestions(
  filters: JobsFilterSlice,
  countForFilters: (slice: Partial<JobsFilterSlice>) => number,
): JobsEmptyStateSuggestion[] {
  return activeJobsFilters(filters)
    .map((axis) => ({
      axis,
      label: labelFor(axis, filters),
      count: countForFilters(RESET[axis]),
      patch: RESET[axis],
    }))
    .filter((s) => s.count > 0)
    .sort((a, b) => b.count - a.count);
}