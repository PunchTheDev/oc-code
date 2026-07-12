import { describe, expect, it, vi } from "vitest";

import * as csvExport from "./csv-export";
import { DownloadCsvButton, onDownloadCsvButtonClick } from "./download-csv-button";

describe("onDownloadCsvButtonClick", () => {
  it("delegates to downloadCsvFromUrl", () => {
    const spy = vi.spyOn(csvExport, "downloadCsvFromUrl").mockImplementation(() => {});
    onDownloadCsvButtonClick("/api/v1/subnets?sort=emission");
    expect(spy).toHaveBeenCalledWith("/api/v1/subnets?sort=emission");
    spy.mockRestore();
  });
});

describe("DownloadCsvButton", () => {
  it("exports a component function", () => {
    expect(typeof DownloadCsvButton).toBe("function");
  });
});