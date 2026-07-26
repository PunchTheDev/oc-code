import { afterEach, describe, expect, it, vi } from "vitest";
import * as backfillModule from "../../src/github/backfill";
import { cachedLiveCiAggregate } from "../../src/queue/ci-resolution";
import type { LiveGithubFacts } from "../../src/queue/processors";
import { createTestEnv } from "../helpers/d1";

function emptyFacts(): LiveGithubFacts {
  return {
    requiredContexts: new Map(),
    ciAggregates: new Map(),
    mergeStates: new Map(),
    forcedCiAggregateKeys: new Set(),
    forcedMergeStateKeys: new Set(),
  };
}

describe("cachedLiveCiAggregate request-scoped memoization (#4498)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("reuses the SAME in-flight/settled promise for a second call sharing the same facts + cache key, never fetching live twice", async () => {
    const env = createTestEnv();
    const liveCiSpy = vi.spyOn(backfillModule, "fetchLiveCiAggregatePreferGraphQl").mockResolvedValue({
      ciState: "passed",
      hasPending: false,
      hasVisiblePending: false,
      hasMissingRequiredContext: false,
      failingDetails: [],
      nonRequiredFailingDetails: [],
      advisoryHoldDetails: [],
      ciCompletenessWarning: null,
    });
    const facts = emptyFacts();
    const args = {
      repoFullName: "owner/repo",
      facts,
      prNumber: 7,
      headSha: "abc123",
      // null baseRef short-circuits fetchRequiredStatusContexts before any network call (see its own
      // `if (!baseRef) return null;` guard) -- irrelevant to what this test is verifying.
      baseRef: null,
      token: "tok",
      expectedCiContexts: null,
      advisoryCheckRuns: null,
    };

    const first = await cachedLiveCiAggregate(env, args);
    const second = await cachedLiveCiAggregate(env, args);

    expect(second).toEqual(first);
    expect(liveCiSpy).toHaveBeenCalledTimes(1);
  });

  it("#4372: a DIFFERENT advisoryCheckRuns config produces a DIFFERENT cache key, so the aggregate is re-fetched (a config change never serves a stale entry)", async () => {
    const env = createTestEnv();
    const liveCiSpy = vi.spyOn(backfillModule, "fetchLiveCiAggregatePreferGraphQl").mockResolvedValue({
      ciState: "passed",
      hasPending: false,
      hasVisiblePending: false,
      hasMissingRequiredContext: false,
      failingDetails: [],
      nonRequiredFailingDetails: [],
      advisoryHoldDetails: [],
      ciCompletenessWarning: null,
    });
    const facts = emptyFacts();
    const base = { repoFullName: "owner/repo", facts, prNumber: 7, headSha: "abc123", baseRef: null, token: "tok", expectedCiContexts: null };

    await cachedLiveCiAggregate(env, { ...base, advisoryCheckRuns: null });
    await cachedLiveCiAggregate(env, { ...base, advisoryCheckRuns: [{ name: "Third-Party Scan", appSlug: "example-scanner" }] });
    // Distinct advisory config ⇒ distinct key ⇒ two live fetches (not one memoized).
    expect(liveCiSpy).toHaveBeenCalledTimes(2);

    // The SAME advisory config in a different order still collapses to one key (order-independent fingerprint).
    const twoEntry = [{ name: "A", appSlug: "app-a" }, { name: "B", appSlug: "app-b" }];
    await cachedLiveCiAggregate(env, { ...base, advisoryCheckRuns: twoEntry });
    await cachedLiveCiAggregate(env, { ...base, advisoryCheckRuns: [...twoEntry].reverse() });
    expect(liveCiSpy).toHaveBeenCalledTimes(3); // +1 only, the reversed list reused the key
  });
});
