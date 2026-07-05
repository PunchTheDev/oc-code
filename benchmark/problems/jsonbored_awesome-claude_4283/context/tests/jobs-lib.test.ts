import { describe, expect, it } from "vitest";

import {
  buildPublicJobsIndex,
  jobSourceLabel,
  mapJobListingRow,
  normalizeJobLocation,
  sortJobs,
  toPublicJobListing,
  type JobListing,
  type JobListingRow,
} from "@/lib/jobs-lib";

function job(overrides: Partial<JobListing> = {}): JobListing {
  return {
    slug: "role",
    title: "Role",
    company: "Example Co",
    location: "Remote",
    description: "Description",
    featured: false,
    applyUrl: "https://example.com/apply",
    ...overrides,
  };
}

function row(overrides: Partial<JobListingRow> = {}): JobListingRow {
  return {
    slug: "role",
    title: "Role",
    company_name: "Example Co",
    company_url: null,
    location_text: "Remote",
    summary: "Summary",
    description_md: null,
    employment_type: null,
    posted_at: null,
    compensation_summary: null,
    equity_summary: null,
    bonus_summary: null,
    benefits_json: null,
    responsibilities_json: null,
    requirements_json: null,
    apply_url: "https://example.com/apply",
    tier: "standard",
    status: "active",
    source: "manual",
    source_kind: "employer_submitted",
    source_url: null,
    first_seen_at: null,
    last_checked_at: null,
    source_checked_at: null,
    stale_check_count: 0,
    curation_note: null,
    paid_placement_expires_at: null,
    claimed_employer: 0,
    posted_by_email: null,
    expires_at: null,
    is_remote: 1,
    is_worldwide: 0,
    ...overrides,
  };
}

describe("jobs-lib normalizeJobLocation", () => {
  it("normalizes EU and US labels without double-wrapping abbreviations", () => {
    expect(normalizeJobLocation("European Union")).toBe("EU (European Union)");
    expect(normalizeJobLocation("EU (European Union)")).toBe(
      "EU (European Union)",
    );
    expect(normalizeJobLocation("EU (EU (European Union))")).toBe(
      "EU (European Union)",
    );
    expect(normalizeJobLocation("US (US (United States))")).toBe(
      "US (United States)",
    );
  });

  it("applies exact city and region replacements", () => {
    expect(
      normalizeJobLocation("San Francisco, California, United States"),
    ).toBe("San Francisco, CA, US");
    expect(
      normalizeJobLocation("San Francisco Bay Area, California, United States"),
    ).toBe("SF Bay Area, CA, US");
    expect(normalizeJobLocation("London, Moorgate, United Kingdom")).toBe(
      "London, UK",
    );
    expect(normalizeJobLocation("EMEA - Remote")).toBe("Remote (EMEA)");
    expect(normalizeJobLocation("London, Europe, France")).toBe("Remote (EU)");
  });

  it("falls back to regex replacements and defaults empty input to Remote", () => {
    expect(normalizeJobLocation("United Kingdom")).toBe("UK");
    expect(normalizeJobLocation("Remote (EU)")).toBe("Remote (EU)");
    expect(normalizeJobLocation(null)).toBe("Remote");
    expect(normalizeJobLocation("")).toBe("Remote");
  });
});

describe("jobs-lib mapJobListingRow", () => {
  it("maps sparse rows through public fallbacks and strips generic seeded bullets", () => {
    const mapped = mapJobListingRow(
      row({
        slug: "fallback-role",
        location_text: "United Kingdom",
        summary: null,
        description_md: "Fallback description.",
        benefits_json: "not-json",
        responsibilities_json: JSON.stringify([
          "Build and maintain production-quality systems aligned with the role and company product surface.",
          "Own useful role-specific automation.",
        ]),
        requirements_json: JSON.stringify({ invalid: true }),
        apply_url: null,
        tier: "unknown",
        status: "unknown",
        source: "unknown",
        source_kind: "unknown",
        posted_by_email: "private@example.com",
        paid_placement_expires_at: "2026-06-01T00:00:00Z",
        is_remote: null,
        is_worldwide: null,
      }),
    );

    expect(mapped).toMatchObject({
      slug: "fallback-role",
      location: "UK",
      description: "Fallback description.",
      applyUrl: "/jobs/post",
      tier: "standard",
      status: "active",
      source: "manual",
      sourceKind: "employer_submitted",
      responsibilities: ["Own useful role-specific automation."],
      benefits: undefined,
      requirements: undefined,
      isRemote: true,
      isWorldwide: false,
    });
  });

  it("derives featured and sponsored flags from tier", () => {
    expect(mapJobListingRow(row({ tier: "featured" }))).toMatchObject({
      tier: "featured",
      featured: true,
      sponsored: false,
    });
    expect(mapJobListingRow(row({ tier: "sponsored" }))).toMatchObject({
      tier: "sponsored",
      featured: true,
      sponsored: true,
    });
  });
});

describe("jobs-lib sortJobs", () => {
  it("ranks sponsored above featured above standard and breaks ties by postedAt", () => {
    const jobs = [
      job({ slug: "free-old", tier: "free", postedAt: "2026-01-01T00:00:00Z" }),
      job({
        slug: "featured-fresh",
        tier: "featured",
        featured: true,
        postedAt: "2026-01-08T00:00:00Z",
      }),
      job({
        slug: "sponsored-fresh",
        tier: "sponsored",
        featured: true,
        sponsored: true,
        postedAt: "2026-01-07T00:00:00Z",
      }),
    ];

    expect(sortJobs(jobs).map((item) => item.slug)).toEqual([
      "sponsored-fresh",
      "featured-fresh",
      "free-old",
    ]);
  });
});

describe("jobs-lib jobSourceLabel", () => {
  it("labels curated jobs first, then ATS and employer-careers source kinds", () => {
    expect(
      jobSourceLabel({ source: "curated", sourceKind: "official_ats" }),
    ).toBe("Editorially curated");
    expect(
      jobSourceLabel({ source: "manual", sourceKind: "official_ats" }),
    ).toBe("Official ATS page");
    expect(
      jobSourceLabel({ source: "manual", sourceKind: "employer_careers" }),
    ).toBe("Employer careers page");
    expect(
      jobSourceLabel({ source: "manual", sourceKind: "employer_submitted" }),
    ).toBe("Employer submitted");
  });
});

describe("jobs-lib toPublicJobListing", () => {
  it("strips private fields and builds labels, URLs, and verification metadata", () => {
    const mapped = mapJobListingRow(
      row({
        slug: "fallback-role",
        location_text: "United Kingdom",
        summary: null,
        description_md: "Fallback description.",
        apply_url: null,
      }),
    );

    const sponsored = toPublicJobListing(
      {
        ...mapped,
        sponsored: true,
        featured: true,
        source: "curated",
        sourceKind: "official_ats",
        compensation: "$180k-$220k",
        claimedEmployer: true,
        lastCheckedAt: "2026-05-01T00:00:00Z",
      },
      "https://heyclau.de",
    );

    expect(sponsored).toMatchObject({
      webUrl: "https://heyclau.de/jobs/fallback-role",
      sourceLabel: "Editorially curated",
      applySourceLabel: "External apply via ATS",
      lastVerifiedAt: "2026-05-01T00:00:00Z",
    });
    expect(sponsored.labels).toEqual(
      expect.arrayContaining([
        "Sponsored",
        "Editorially curated",
        "Claimed employer",
        "Remote",
        "Compensation listed",
      ]),
    );
    expect(sponsored).not.toHaveProperty("postedByEmail");
    expect(sponsored).not.toHaveProperty("paidPlacementExpiresAt");
    expect(sponsored).not.toHaveProperty("staleCheckCount");
  });

  it("prefers sourceCheckedAt over lastCheckedAt for lastVerifiedAt", () => {
    const publicJob = toPublicJobListing(
      job({
        sourceCheckedAt: "2026-06-01T00:00:00Z",
        lastCheckedAt: "2026-05-01T00:00:00Z",
      }),
    );
    expect(publicJob.lastVerifiedAt).toBe("2026-06-01T00:00:00Z");
  });

  it("uses employer-careers apply copy for careers source kinds", () => {
    const publicJob = toPublicJobListing(
      job({ sourceKind: "employer_careers" }),
    );
    expect(publicJob.applySourceLabel).toBe("External apply via employer site");
  });
});

describe("jobs-lib buildPublicJobsIndex", () => {
  it("returns an empty index when there are no jobs", () => {
    expect(buildPublicJobsIndex([])).toMatchObject({
      schemaVersion: 1,
      kind: "jobs-index",
      generatedAt: "",
      count: 0,
      entries: [],
    });
  });

  it("uses the latest verification timestamp as generatedAt", () => {
    const index = buildPublicJobsIndex([
      job({
        slug: "older",
        postedAt: "2026-01-01T00:00:00Z",
        lastCheckedAt: "2026-02-01T00:00:00Z",
      }),
      job({
        slug: "newer",
        postedAt: "2026-03-01T00:00:00Z",
        sourceCheckedAt: "2026-04-01T00:00:00Z",
      }),
    ]);

    expect(index.count).toBe(2);
    expect(index.generatedAt).toBe(
      new Date("2026-04-01T00:00:00Z").toISOString(),
    );
    expect(index.entries.map((entry) => entry.slug)).toEqual([
      "older",
      "newer",
    ]);
  });
});