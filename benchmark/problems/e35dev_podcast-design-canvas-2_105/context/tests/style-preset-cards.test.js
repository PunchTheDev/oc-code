"use strict";

// Visual style preset cards smoke suite for Podcast Design Canvas (#94).
// Run with: `node tests/style-preset-cards.test.js`.

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const style = require("../app/episode-style.js");

let passed = 0;
function test(name, fn) {
  fn();
  passed += 1;
  console.log(`  ok ${name}`);
}

const ui = fs.readFileSync(path.join(__dirname, "../app/episode-setup.ui.js"), "utf8");
const styles = fs.readFileSync(path.join(__dirname, "../app/styles.css"), "utf8");

test("presetCardSummary exposes layout and caption cues for preset cards", () => {
  const preset = style.getPreset("split-stage");
  const summary = style.presetCardSummary(preset);
  assert.ok(summary.formatCue.includes("Side by side"));
  assert.ok(summary.formatCue.includes("Clean caption bar"));
});

test("layoutCardSummary exposes card-friendly layout notes", () => {
  const layout = style.layoutCardSummary({ id: "grid" });
  assert.strictEqual(layout.label, "Grid");
  assert.ok(layout.note.length > 0);
});

test("style step uses visual preset and choice cards instead of native selects", () => {
  assert.ok(ui.includes("renderStylePresetCard"));
  assert.ok(ui.includes("openStylePickerDemo"));
  assert.ok(ui.includes("style-choice-card"));
  assert.ok(ui.includes("create-show-template-card"));
  assert.ok(!ui.includes('id: "style-layout"'));
  assert.ok(!ui.includes('id: "style-pacing"'));
  assert.ok(!ui.includes('id: "f-show-template"'));
});

test("styles define visual preset cards with layout thumbnails", () => {
  assert.ok(styles.includes(".style-preset-card"));
  assert.ok(styles.includes(".style-layout-thumb"));
  assert.ok(styles.includes(".style-choice-card"));
  assert.ok(styles.includes(".create-show-template-card"));
});

test("ACCEPTANCE: preset cards carry name, layout cue, and caption format metadata", () => {
  style.STYLE_PRESETS.forEach((preset) => {
    const summary = style.presetCardSummary(preset);
    assert.ok(summary.layoutLabel);
    assert.ok(summary.captionStyle);
    assert.ok(summary.formatCue.includes(preset.captionStyle));
  });
});

console.log(`\nstyle preset cards: ${passed} assertions passed`);
