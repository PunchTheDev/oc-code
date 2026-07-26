import { describe, expect, it } from "vitest";

import { leadsToCsv, normalizeKind } from "@/lib/listing-leads-csv-lib";

describe("normalizeKind", () => {
  it("accepts allow-listed kinds, case/space-insensitively", () => {
    expect(normalizeKind("job")).toBe("job");
    expect(normalizeKind("  Tool ")).toBe("tool");
    expect(normalizeKind("CLAIM")).toBe("claim");
  });

  it("returns '' for unknown or missing kinds", () => {
    expect(normalizeKind("sponsor")).toBe("");
    expect(normalizeKind(null)).toBe("");
  });
});

describe("leadsToCsv", () => {
  it("emits the header row followed by column-ordered values", () => {
    const csv = leadsToCsv([
      { id: "1", kind: "job", contact_email: "a@b.com", message: "hi" },
    ]);
    const [header, row] = csv.split("\n");
    expect(header.split(",")[0]).toBe("id");
    expect(header).toContain("contact_email");
    const cols = row.split(",");
    expect(cols[0]).toBe("1");
    expect(cols[1]).toBe("job");
  });

  it("escapes values containing commas and quotes", () => {
    const csv = leadsToCsv([{ message: 'a,b "c"' }]);
    const row = csv.split("\n")[1];
    expect(row).toContain('"a,b ""c"""');
  });

  it("renders only the header for no rows", () => {
    const csv = leadsToCsv([]);
    expect(csv.split("\n")).toHaveLength(1);
    expect(csv.startsWith("id,kind,status")).toBe(true);
  });
});
