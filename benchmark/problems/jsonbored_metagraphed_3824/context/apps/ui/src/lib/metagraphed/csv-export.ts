/** Merge `format=csv` into `url`, preserving any existing query params and hash. */
export function buildCsvExportUrl(url: string): string {
  const trimmed = url.trim();
  const parsed = new URL(trimmed, "https://export.local");
  parsed.searchParams.set("format", "csv");
  if (/^https?:\/\//i.test(trimmed)) {
    return parsed.toString();
  }
  const path = `${parsed.pathname}${parsed.search}${parsed.hash}`;
  return path.startsWith("/") ? path : `/${path}`;
}

/** Navigate to `exportUrl` via a transient anchor so the SPA view is preserved. */
export function triggerCsvDownload(exportUrl: string): void {
  if (typeof document === "undefined") return;
  const anchor = document.createElement("a");
  anchor.href = exportUrl;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

/** Compose URL merge + native download navigation for a caller-supplied API URL. */
export function downloadCsvFromUrl(url: string): void {
  triggerCsvDownload(buildCsvExportUrl(url));
}