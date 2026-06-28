"use strict";

// First-episode import smoke suite for Podcast Design Canvas (#130).
// Run with: `node tests/first-episode-import.test.js`.

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const library = require("../app/show-library.js");
const identity = require("../app/show-identity.js");
const setup = require("../app/episode-setup.js");

let passed = 0;
function test(name, fn) {
  fn();
  passed += 1;
  console.log(`  ok ${name}`);
}

const ui = fs.readFileSync(path.join(__dirname, "../app/episode-setup.ui.js"), "utf8");
const styles = fs.readFileSync(path.join(__dirname, "../app/styles.css"), "utf8");

test("createShow stores presetId alongside presetName for style carry-over", () => {
  library._resetCounters();
  const show = library.createShow("Founders Unfiltered", {
    presetId: "split-stage",
    presetName: "Split Stage",
  });
  assert.strictEqual(show.presetId, "split-stage");
  assert.strictEqual(show.presetName, "Split Stage");
});

test("resolveStyleSelection prefers show.presetId over presetName lookup", () => {
  library._resetCounters();
  const show = library.createShow("Agency Weekly", {
    presetId: "studio-spotlight",
    presetName: "Split Stage",
  });
  const selection = identity.resolveStyleSelection(show, null);
  assert.strictEqual(selection.presetId, "studio-spotlight");
});

test("attachPlaceholderFile seeds a synced filename per speaker bucket", () => {
  const host = setup.attachPlaceholderFile(setup.createSpeaker("Host"));
  assert.strictEqual(host.fileName, "host-synced.mp4");
  assert.ok(host.fileSize > 0);

  const guest = setup.attachPlaceholderFile(setup.createSpeaker("Guest 2"));
  assert.strictEqual(guest.fileName, "guest-2-synced.mp4");
});

test("upload draft with placeholder files validates for sandbox import", () => {
  const draft = setup.createDraft();
  draft.episodeName = "Founders Unfiltered — Episode 1";
  draft.sourceMode = "upload";
  draft.speakers.forEach((speaker) => setup.attachPlaceholderFile(speaker));
  draft.speakers.forEach((speaker, index) => {
    speaker.name = `Speaker ${index + 1}`;
  });

  const result = setup.validateDraft(draft);
  assert.strictEqual(result.ok, true, JSON.stringify(result.errors));
  const summary = setup.summarize(draft);
  assert.strictEqual(summary.sourceModeLabel, "Uploaded speaker files");
  assert.deepStrictEqual(
    summary.speakers.map((speaker) => speaker.sourceLabel),
    ["host-synced.mp4", "guest-1-synced.mp4", "guest-2-synced.mp4"],
  );
});

test("buildEpisodeStart carries preset style into first-episode import context", () => {
  library._resetCounters();
  let lib = library.createLibrary();
  const show = library.createShow("Founders Unfiltered", {
    presetId: "split-stage",
    presetName: "Split Stage",
  });
  lib = library.addShow(lib, show);
  const start = identity.buildEpisodeStart(library.getShow(lib, show.id), null);

  assert.ok(start.setupDraft);
  assert.strictEqual(start.styleSelection.presetId, "split-stage");
  assert.ok(start.appliedStyle);
  assert.strictEqual(start.appliedStyle.presetName, "Split Stage");
});

test("ACCEPTANCE: primary CTA lands on first-episode import with Riverside, files, and workspace recap", () => {
  assert.ok(ui.includes("startNewShowImportFlow"));
  assert.ok(ui.includes('() => startNewShowImportFlow()'));
  assert.ok(ui.includes("renderFirstEpisodeImport"));
  assert.ok(ui.includes("First episode import"));
  assert.ok(ui.includes("setup-first-episode-import"));
  assert.ok(ui.includes("import-ready-summary"));
  assert.ok(ui.includes("file-placeholder-btn"));
  assert.ok(ui.includes("Attach placeholder file"));
  assert.ok(ui.includes("f-riversideLink"));
  assert.ok(ui.includes("renderEpisodeImportRecap"));
  assert.ok(ui.includes("episode-import-recap"));
  assert.ok(styles.includes(".import-ready-summary"));
  assert.ok(styles.includes(".episode-import-recap"));
});

console.log(`\nfirst episode import: ${passed} assertions passed`);