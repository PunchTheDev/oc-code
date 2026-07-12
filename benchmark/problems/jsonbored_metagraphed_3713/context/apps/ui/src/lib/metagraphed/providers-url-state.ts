import type { Provider } from "./types";

/** Match a provider against the URL authority filter (including the `high` shortcut). */
export function matchesProviderAuthority(p: Provider, filter: string): boolean {
  if (!filter) return true;
  if (filter === "high") {
    return p.authority === "official" || p.authority === "provider-claimed";
  }
  return p.authority === filter;
}