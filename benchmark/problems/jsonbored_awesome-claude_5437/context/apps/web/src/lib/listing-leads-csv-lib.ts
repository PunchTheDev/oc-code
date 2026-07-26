// Pure helpers for the admin listing-leads route: normalize the kind filter to
// an allowlist and render lead rows to CSV. Split out of the route so both can
// be unit-tested without the handler.

import { csvEscape } from "@/lib/csv";

const ALLOWED_KINDS = new Set(["job", "tool", "claim"]);

const CSV_COLUMNS = [
  "id",
  "kind",
  "status",
  "tier_interest",
  "contact_name",
  "contact_email",
  "company_name",
  "listing_title",
  "website_url",
  "apply_url",
  "message",
  "created_at",
  "updated_at",
] as const;

/** Normalize a lead-kind filter to an allow-listed value, or "" when unknown. */
export function normalizeKind(value: string | null): string {
  const normalized = String(value ?? "")
    .trim()
    .toLowerCase();
  return ALLOWED_KINDS.has(normalized) ? normalized : "";
}

/** Render listing-lead rows to CSV using the fixed column order. */
export function leadsToCsv(rows: Record<string, unknown>[]): string {
  return [
    CSV_COLUMNS.join(","),
    ...rows.map((row) => CSV_COLUMNS.map((column) => csvEscape(row[column])).join(",")),
  ].join("\n");
}
