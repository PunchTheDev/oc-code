"use strict";

// Preset style + preview smoke suite for Podcast Design Canvas (#3).
// Guards the documented acceptance: at least three clearly different presets, adjustable
// layout and pacing, and a preview built from the assigned Host/Guest speaker buckets.
// Run with: `node tests/episode-style.test.js`.

const assert = require("assert");
const style = require("../app/episode-style.js");
const setup = require("../app/episode-setup.js");

let passed = 0;
function test(name, fn) {
  fn();
  passed += 1;
  console.log(`  ok ${name}`);
}

test("offers at least three clearly different presets", () => {
  assert.ok(style.STYLE_PRESETS.length >= 3, "need 3+ presets");
  const ids = style.STYLE_PRESETS.map((p) => p.id);
  const names = style.STYLE_PRESETS.map((p) => p.name);
  const backgrounds = style.STYLE_PRESETS.map((p) => p.background);
  assert.strictEqual(new Set(ids).size, ids.length, "preset ids are unique");
  assert.strictEqual(new Set(names).size, names.length, "preset names are unique");
  assert.ok(new Set(backgrounds).size >= 3, "presets are visually distinct");
  style.STYLE_PRESETS.forEach((p) => {
    assert.ok(p.name && p.tagline && p.accent && p.captionStyle, `${p.id} is fully described`);
  });
});

test("a fresh selection defaults to the first preset, auto layout, balanced pacing", () => {
  const selection = style.createSelection();
  assert.strictEqual(selection.presetId, style.STYLE_PRESETS[0].id);
  assert.strictEqual(selection.layout, "auto");
  assert.strictEqual(selection.pacing, "balanced");
});

test("getPreset falls back to the default for an unknown id", () => {
  assert.strictEqual(style.getPreset("nope").id, style.defaultPreset().id);
  assert.strictEqual(style.getPreset("panel-grid").id, "panel-grid");
});

test("auto layout resolves from the speaker count", () => {
  assert.strictEqual(style.resolveLayout({ layout: "auto" }, 1), "spotlight");
  assert.strictEqual(style.resolveLayout({ layout: "auto" }, 2), "split");
  assert.strictEqual(style.resolveLayout({ layout: "auto" }, 3), "grid");
});

test("an explicit layout choice overrides auto", () => {
  assert.strictEqual(style.resolveLayout({ layout: "spotlight" }, 3), "spotlight");
  assert.strictEqual(style.resolveLayout({ layout: "grid" }, 1), "grid");
});

test("the preview is built from the assigned Host/Guest speaker buckets", () => {
  const speakers = [
    { role: "Guest 1", name: "Dana Kim" },
    { role: "Host", name: "Sam Rivera" },
    { role: "Guest 2", name: "Marco Vidal" },
  ];
  const frames = style.buildPreviewFrames(speakers, { layout: "spotlight" }, 3);
  assert.strictEqual(frames.length, 3);
  assert.deepStrictEqual(frames.map((f) => f.name), ["Dana Kim", "Sam Rivera", "Marco Vidal"]);
  // The Host is featured in spotlight layout even when not listed first.
  assert.strictEqual(frames[1].active, true, "host frame is active");
  assert.strictEqual(frames[0].active, false);
});

test("with no Host, the first speaker is featured in spotlight", () => {
  const speakers = [
    { role: "Guest 1", name: "Dana Kim" },
    { role: "Guest 2", name: "Marco Vidal" },
  ];
  const frames = style.buildPreviewFrames(speakers, { layout: "spotlight" }, 2);
  assert.strictEqual(frames[0].active, true);
});

test("non-spotlight layouts feature no single frame", () => {
  const speakers = [{ role: "Host", name: "Sam" }, { role: "Guest 1", name: "Dana" }];
  const frames = style.buildPreviewFrames(speakers, { layout: "grid" }, 2);
  assert.ok(frames.every((f) => f.active === false));
});

test("summarizeStyle reflects the chosen preset, layout, and pacing", () => {
  const summary = style.summarizeStyle({ presetId: "panel-grid", layout: "split", pacing: "punchy" }, 3);
  assert.strictEqual(summary.presetName, "Panel Grid");
  assert.strictEqual(summary.layoutLabel, "Side by side");
  assert.strictEqual(summary.resolvedFromAuto, false);
  assert.strictEqual(summary.pacingLabel, "Punchy");
  assert.strictEqual(summary.captionStyle, "Minimal name tag");
});

test("summarizeStyle resolves an auto layout from the speaker count", () => {
  const summary = style.summarizeStyle(style.createSelection(), 3);
  assert.strictEqual(summary.resolvedFromAuto, true);
  assert.strictEqual(summary.layoutId, "grid");
});

// End-to-end: a completed setup feeds the style step, and the preview + summary reflect
// the real assigned speakers — the documented runnable check for issue #3.
test("ACCEPTANCE: pick a preset and preview the real episode speakers", () => {
  const draft = setup.createDraft();
  draft.episodeName = "Founders Unfiltered #7";
  draft.sourceMode = "upload";
  draft.speakers = [
    Object.assign(setup.createSpeaker("Host"), { name: "Sam Rivera", fileName: "sam.mp4" }),
    Object.assign(setup.createSpeaker("Guest 1"), { name: "Dana Kim", fileName: "dana.mp4" }),
    Object.assign(setup.createSpeaker("Guest 2"), { name: "Marco Vidal", fileName: "marco.mp4" }),
  ];
  assert.strictEqual(setup.validateDraft(draft).ok, true);

  const episode = setup.summarize(draft);
  const selection = style.createSelection();
  selection.presetId = "split-stage"; // change away from the default preset

  const frames = style.buildPreviewFrames(episode.speakers, selection, episode.speakerCount);
  assert.deepStrictEqual(frames.map((f) => f.role), ["Host", "Guest 1", "Guest 2"]);
  assert.deepStrictEqual(frames.map((f) => f.name), ["Sam Rivera", "Dana Kim", "Marco Vidal"]);

  const applied = style.summarizeStyle(selection, episode.speakerCount);
  assert.strictEqual(applied.presetName, "Split Stage");
  assert.strictEqual(applied.layoutId, "grid"); // auto, 3 speakers
});

console.log(`\nepisode style: ${passed} assertions passed`);
