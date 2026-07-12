import { describe, expect, it } from "vitest";
import { matchesProviderAuthority } from "./providers-url-state";
import type { Provider } from "./types";

describe("matchesProviderAuthority", () => {
  const base = { slug: "acme" } satisfies Provider;

  it("passes through when no filter is set", () => {
    expect(matchesProviderAuthority({ ...base, authority: "community" }, "")).toBe(true);
  });

  it("matches exact authority values", () => {
    expect(matchesProviderAuthority({ ...base, authority: "official" }, "official")).toBe(true);
    expect(matchesProviderAuthority({ ...base, authority: "community" }, "official")).toBe(false);
  });

  it("treats high as official + provider-claimed", () => {
    expect(matchesProviderAuthority({ ...base, authority: "official" }, "high")).toBe(true);
    expect(matchesProviderAuthority({ ...base, authority: "provider-claimed" }, "high")).toBe(true);
    expect(matchesProviderAuthority({ ...base, authority: "community" }, "high")).toBe(false);
  });
});