"use strict";

// Show brand kit smoke suite for Podcast Design Canvas (#52).
// Guards saving, loading, applying brand identity to preview and export summary.
// Run with: `node tests/show-brand-kit.test.js`.

const assert = require("assert");
const style = require("../app/episode-style.js");
const exportApi = require("../app/episode-export.js");
const setup = require("../app/episode-setup.js");
const library = require("../app/show-library.js");
const brandKit = require("../app/show-brand-kit.js");

let passed = 0;
function test(name, fn) {
  fn();
  passed += 1;
  console.log(`  ok ${name}`);
}

function sampleKit(showId) {
  return brandKit.createBrandKit(showId || "show-1", {
    logoLabel: "Founders mark",
    colors: {
      primary: "#6c4cff",
      secondary: "#10131f",
      background: "#0d1117",
      accent: "#ffb347",
      text: "#f6f7fb",
    },
    typeStyle: "bold-display",
    captionStyle: "big-animated",
  });
}

test("createBrandKit seeds logo, colors, type style, and caption style", () => {
  brandKit._resetOverlayCounter();
  const kit = sampleKit("show-founders");
  assert.strictEqual(kit.showId, "show-founders");
  assert.strictEqual(kit.logoLabel, "Founders mark");
  assert.strictEqual(kit.typeStyleLabel, "Bold display");
  assert.strictEqual(kit.captionStyleLabel, "Big animated captions");
  assert.strictEqual(kit.colors.primary, "#6c4cff");
});

test("validateBrandKit rejects invalid colors and accepts a complete kit", () => {
  const bad = brandKit.updateBrandKit(sampleKit("show-1"), {
    colors: { primary: "purple" },
  });
  assert.strictEqual(brandKit.validateBrandKit(bad).ok, false);
  assert.strictEqual(brandKit.validateBrandKit(sampleKit("show-1")).ok, true);
});

test("addOverlayAsset and removeOverlayAsset manage reusable overlay assets", () => {
  brandKit._resetOverlayCounter();
  let kit = sampleKit("show-1");
  kit = brandKit.addOverlayAsset(kit, "Episode bug", "lower-third");
  kit = brandKit.addOverlayAsset(kit, "Outro card", "outro");
  assert.strictEqual(kit.overlayAssets.length, 2);
  kit = brandKit.removeOverlayAsset(kit, kit.overlayAssets[0].id);
  assert.strictEqual(kit.overlayAssets.length, 1);
  assert.strictEqual(kit.overlayAssets[0].name, "Outro card");
});

test("getPreviewTheme applies brand colors and caption style to a preset preview", () => {
  const preset = style.getPreset("studio-spotlight");
  const theme = brandKit.getPreviewTheme(preset, sampleKit("show-1"));
  assert.strictEqual(theme.background, "#0d1117");
  assert.strictEqual(theme.accent, "#ffb347");
  assert.strictEqual(theme.captionStyle, "Big animated captions");
  assert.strictEqual(theme.typeStyleLabel, "Bold display");
  assert.strictEqual(theme.logoLabel, "Founders mark");
});

test("applyToStyleSummary merges brand kit into the applied style summary", () => {
  const episode = setup.summarize(setup.createDraft());
  const applied = style.summarizeStyle(style.createSelection(), episode.speakerCount);
  const branded = brandKit.applyToStyleSummary(applied, sampleKit("show-1"));
  assert.strictEqual(branded.background, "#0d1117");
  assert.strictEqual(branded.captionStyle, "Big animated captions");
  assert.strictEqual(branded.brandApplied, true);
});

test("serializeBrandKit and deserializeBrandKit round-trip through show library storage", () => {
  library._resetCounters();
  brandKit._resetOverlayCounter();
  let kit = brandKit.addOverlayAsset(sampleKit("show-1"), "Intro card", "intro");
  let lib = library.createLibrary();
  const show = library.createShow("Founders Unfiltered", { id: "show-1", brandKit: kit });
  lib = library.addShow(lib, show);
  const restored = library.deserializeLibrary(library.serializeLibrary(lib));
  const restoredShow = library.getShow(restored, "show-1");
  assert.ok(restoredShow.brandKit);
  assert.strictEqual(restoredShow.brandKit.logoLabel, "Founders mark");
  assert.strictEqual(restoredShow.brandKit.overlayAssets.length, 1);
});

test("export summary includes the selected brand kit line", () => {
  const episode = setup.summarize(setup.createDraft());
  episode.episodeName = "Episode 12";
  const ctx = {
    audioPolish: { presetName: "Studio", treatmentLine: "balanced" },
    appliedStyle: style.summarizeStyle(style.createSelection(), episode.speakerCount),
    brandKitSummary: brandKit.summarizeBrandKit(sampleKit("show-1")),
  };
  const summary = exportApi.buildFinalSummary(episode, ctx, exportApi.createExport(episode));
  assert.ok(summary.lines.some((line) => /Brand kit:/.test(line)));
  assert.ok(summary.lines.some((line) => /Founders mark/.test(line)));
});

test("ACCEPTANCE: save, load, apply brand kit, and reflect it in export summary", () => {
  library._resetCounters();
  brandKit._resetOverlayCounter();
  let lib = library.createLibrary();
  let kit = brandKit.addOverlayAsset(sampleKit("show-founders"), "Episode lower-third", "lower-third");
  assert.strictEqual(brandKit.validateBrandKit(kit).ok, true);
  lib = library.addShow(lib, library.createShow("Founders Unfiltered", {
    id: "show-founders",
    templateName: "Founders Layout",
    presetName: "Split Stage",
    brandKit: kit,
  }));

  const draft = library.newEpisodeDraft(library.getShow(lib, "show-founders"));
  assert.ok(draft.brandKit);
  assert.strictEqual(draft.brandKit.captionStyleLabel, "Big animated captions");

  const preset = style.getPreset("split-stage");
  const theme = brandKit.getPreviewTheme(preset, draft.brandKit);
  assert.strictEqual(theme.background, "#0d1117");
  assert.strictEqual(theme.logoLabel, "Founders mark");

  const episode = setup.summarize(setup.createDraft());
  episode.episodeName = "Episode 12 — Building in Public";
  const brandedStyle = brandKit.applyToStyleSummary(
    style.summarizeStyle(style.createSelection(), episode.speakerCount),
    draft.brandKit,
  );
  const exportSummary = exportApi.buildFinalSummary(episode, {
    audioPolish: { presetName: "Studio", treatmentLine: "broadcast polish" },
    appliedStyle: brandedStyle,
    brandKitSummary: brandKit.summarizeBrandKit(draft.brandKit),
    templateName: draft.templateName,
  }, exportApi.createExport(episode));
  assert.ok(exportSummary.lines.some((line) => /Brand kit:/.test(line)));
  assert.ok(exportSummary.lines.some((line) => /Big animated captions/.test(line)));
});

console.log(`\nshow brand kit: ${passed} assertions passed`);