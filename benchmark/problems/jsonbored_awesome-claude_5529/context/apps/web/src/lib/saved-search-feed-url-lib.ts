// Pure `/feeds/saved.xml` URL builder for a saved search, split out of
// saved-search-manager.tsx so the query-string assembly can be unit-tested
// without React Router.

import type { SavedSearch } from "@/lib/recents";

/**
 * Build the RSS feed URL for a saved search. Each of `q`, `category`, `trust`,
 * `source`, `platform`, and `label` is appended as a query param only when it
 * is a non-empty value, so empty filters are omitted. The params are
 * URL-encoded via `URLSearchParams`.
 */
export function savedFeedUrl(s: SavedSearch): string {
  const p = new URLSearchParams();
  if (s.q) p.set("q", s.q);
  if (s.category) p.set("category", s.category);
  if (s.trust) p.set("trust", s.trust);
  if (s.source) p.set("source", s.source);
  if (s.platform) p.set("platform", s.platform);
  if (s.label) p.set("label", s.label);
  return `/feeds/saved.xml?${p.toString()}`;
}
