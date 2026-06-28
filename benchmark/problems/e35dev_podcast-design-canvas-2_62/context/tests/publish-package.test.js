"use strict";

// Publish package builder smoke suite for Podcast Design Canvas (#60).
// Run with: `node tests/publish-package.test.js`.

const assert = require("assert");
const setup = require("../app/episode-setup.js");
const style = require("../app/episode-style.js");
const audio = require("../app/audio-polish.js");
const moments = require("../app/visual-moments.js");
const brandKit = require("../app/show-brand-kit.js");
const exportApi = require("../app/episode-export.js");
const publishPackage = require("../app/publish-package.js");

let passed = 0;
function test(name, fn) {
  fn();
  passed += 1;
  console.log(`  ok ${name}`);
}

function completeDraft() {
  const draft = setup.createDraft();
  draft.episodeName = "Founders Unfiltered #7";
  draft.sourceMode = "upload";
  draft.speakers = [
    Object.assign(setup.createSpeaker("Host"), { name: "Sam Rivera", fileName: "sam.mp4" }),
    Object.assign(setup.createSpeaker("Guest 1"), { name: "Dana Kim", fileName: "dana.mp4" }),
  ];
  return draft;
}

function buildContext(episode) {
  let board = moments.createBoard(episode);
  board = moments.addMoment(board, "title", { time: "1:30", text: "Building in public" });
  board = moments.addMoment(board, "caption", { time: "3:00", text: "Key insight", speakerRole: "Host" });
  const selection = style.createSelection();
  return {
    showName: "Founders Unfiltered",
    appliedStyle: style.summarizeStyle(selection, episode.speakerCount),
    audioPolish: audio.summarizePolish(audio.createPolish(episode)),
    momentsBoard: board,
    brandKit: brandKit.createBrandKit("show-1", {
      logoLabel: "Founders mark",
      colors: {
        primary: "#6c4cff",
        secondary: "#10131f",
        background: "#0d1117",
        accent: "#ffb347",
        text: "#f6f7fb",
      },
    }),
    brandKitSummary: brandKit.summarizeBrandKit(brandKit.createBrandKit("show-1", { logoLabel: "Founders mark" })),
  };
}

test("createPackage seeds title, description, chapters, credits, and thumbnail options", () => {
  const episode = setup.summarize(completeDraft());
  const ctx = buildContext(episode);
  const pkg = publishPackage.createPackage(episode, ctx);

  assert.strictEqual(pkg.title, "Founders Unfiltered #7");
  assert.ok(pkg.description.includes("Sam Rivera"));
  assert.ok(pkg.chapters.length >= 2);
  assert.strictEqual(pkg.speakerCredits.length, 2);
  assert.ok(pkg.thumbnailOptions.length >= 3);
  assert.strictEqual(pkg.thumbnailOptions[0].logoLabel, "Founders mark");
});

test("updatePackage and selectThumbnail reflect creator edits", () => {
  const episode = setup.summarize(completeDraft());
  const ctx = buildContext(episode);
  let pkg = publishPackage.createPackage(episode, ctx);
  pkg = publishPackage.updatePackage(pkg, {
    title: "Episode 12 — Building in Public",
    description: "A conversation about shipping in public.",
  });
  pkg = publishPackage.selectThumbnail(pkg, "thumb-title-card");

  const summary = publishPackage.summarizePackage(pkg);
  assert.ok(summary.lines.some((line) => /Episode 12/.test(line)));
  assert.ok(summary.lines.some((line) => /shipping in public/.test(line)));
  assert.ok(summary.lines.some((line) => /Title card/.test(line)));
});

test("updateChapter and updateSpeakerCredit change package content", () => {
  const episode = setup.summarize(completeDraft());
  const ctx = buildContext(episode);
  let pkg = publishPackage.createPackage(episode, ctx);
  const chapterId = pkg.chapters[1].id;
  pkg = publishPackage.updateChapter(pkg, chapterId, { label: "Chapter one" });
  pkg = publishPackage.updateSpeakerCredit(pkg, pkg.speakerCredits[0].id, {
    name: "Sam Rivera",
    role: "Host & Producer",
  });

  assert.ok(pkg.chapters.some((item) => item.label === "Chapter one"));
  assert.ok(pkg.speakerCredits[0].creditLine.includes("Host & Producer"));
});

test("serializePackage and deserializePackage round-trip creator edits", () => {
  const episode = setup.summarize(completeDraft());
  const ctx = buildContext(episode);
  let pkg = publishPackage.updatePackage(publishPackage.createPackage(episode, ctx), {
    title: "Saved title",
  });
  const restored = publishPackage.deserializePackage(publishPackage.serializePackage(pkg), episode, ctx);
  assert.strictEqual(restored.title, "Saved title");
  assert.ok(restored.thumbnailOptions.length >= 3);
});

test("ACCEPTANCE: publish package updates appear in the final export summary", () => {
  const episode = setup.summarize(completeDraft());
  const ctx = buildContext(episode);
  let pkg = publishPackage.createPackage(episode, ctx);
  pkg = publishPackage.updatePackage(pkg, {
    title: "Episode 12 — Building in Public",
    description: "Sam and Dana talk about founder-led storytelling.",
  });
  pkg = publishPackage.selectThumbnail(pkg, "thumb-split");
  const publishPackageSummary = publishPackage.summarizePackage(pkg);

  const exportSummary = exportApi.buildFinalSummary(episode, Object.assign({}, ctx, {
    publishPackageSummary: publishPackageSummary,
  }), exportApi.createExport(episode));

  assert.ok(exportSummary.lines.some((line) => /Publish title: Episode 12/.test(line)));
  assert.ok(exportSummary.lines.some((line) => /Description:/.test(line)));
  assert.ok(exportSummary.lines.some((line) => /Split conversation/.test(line)));
  assert.ok(exportSummary.lines.some((line) => /Credits:/.test(line)));
});

console.log(`\npublish package: ${passed} assertions passed`);