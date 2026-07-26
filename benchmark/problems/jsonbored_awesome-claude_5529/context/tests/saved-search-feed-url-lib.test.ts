import { describe, expect, it } from "vitest";

import type { SavedSearch } from "../apps/web/src/lib/recents";
import { savedFeedUrl } from "../apps/web/src/lib/saved-search-feed-url-lib";

const search = (over: Partial<SavedSearch> = {}) =>
  ({ q: "", ...over }) as SavedSearch;

describe("savedFeedUrl", () => {
  it("omits every empty filter, yielding a bare feed path", () => {
    expect(savedFeedUrl(search())).toBe("/feeds/saved.xml?");
  });

  it("appends each provided filter as a query param", () => {
    const url = savedFeedUrl(
      search({
        q: "mcp",
        category: "mcp",
        trust: "trusted",
        source: "official",
        platform: "claude-code",
        label: "my feed",
      }),
    );
    const params = new URL(`https://x.test${url}`).searchParams;
    expect(params.get("q")).toBe("mcp");
    expect(params.get("category")).toBe("mcp");
    expect(params.get("trust")).toBe("trusted");
    expect(params.get("source")).toBe("official");
    expect(params.get("platform")).toBe("claude-code");
    expect(params.get("label")).toBe("my feed");
  });

  it("includes only the non-empty filters", () => {
    expect(savedFeedUrl(search({ q: "agents", category: "" }))).toBe(
      "/feeds/saved.xml?q=agents",
    );
  });

  it("URL-encodes values with spaces and reserved characters", () => {
    const url = savedFeedUrl(search({ q: "a b & c" }));
    expect(url).toContain("q=a+b+%26+c");
  });
});
