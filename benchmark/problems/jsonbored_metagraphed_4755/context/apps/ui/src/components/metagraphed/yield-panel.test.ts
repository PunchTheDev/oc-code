import { describe, expect, it } from "vitest";
import { fmtYield } from "./yield-panel";

describe("fmtYield", () => {
  it("returns the em-dash fallback for nullish / non-finite input", () => {
    expect(fmtYield(null)).toBe("—");
    expect(fmtYield(undefined)).toBe("—");
    expect(fmtYield(Number.NaN)).toBe("—");
    expect(fmtYield(Infinity)).toBe("—");
  });

  it("renders exactly zero as a plain 0%", () => {
    expect(fmtYield(0)).toBe("0%");
  });

  it("uses 2 decimal places once the percentage reaches 1%", () => {
    expect(fmtYield(0.5)).toBe("50.00%");
    expect(fmtYield(0.01)).toBe("1.00%");
  });

  it("does not collapse distinct validator-scale yields to the same string (#3946)", () => {
    // Real values observed on-chain for SN64 validators — under the previous
    // toFixed(4) formatting these all rounded to "0.0041%" or "0.0042%"
    // despite differing, making a ranked leaderboard look identical/broken.
    const raw = [
      4.1721e-5, 4.1529e-5, 4.1496e-5, 4.1425e-5, 4.1359e-5, 4.1306e-5, 4.1225e-5, 4.1128e-5,
      4.0711e-5, 4.056e-5,
    ];
    const formatted = raw.map((v) => fmtYield(v));
    expect(new Set(formatted).size).toBe(formatted.length);
  });

  it("falls back to exponential notation below the 0.001% precision floor", () => {
    expect(fmtYield(0.0000001)).toBe("1.00e-5%");
  });
});
