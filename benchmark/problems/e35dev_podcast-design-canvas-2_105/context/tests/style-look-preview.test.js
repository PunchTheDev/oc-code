"use strict";

// Rich episode look preview smoke suite for Podcast Design Canvas (#102).
// Run with: `node tests/style-look-preview.test.js`.

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const style = require("../app/episode-style.js");
const preview = require("../app/style-preview.js");

let passed = 0;
function test(name, fn) {
  fn();
  passed += 1;
  console.log(`  ok ${name}`);
}

const ui = fs.readFileSync(path.join(__dirname, "../app/episode-setup.ui.js"), "utf8");
const styles = fs.readFileSync(path.join(__dirname, "../app/styles.css"), "utf8");

test("buildEpisodeLook returns realistic multi-speaker frames with overlay and caption cues", () => {
  const look = preview.buildEpisodeLook("split-stage", { showName: "Founders Unfiltered" });
  assert.strictEqual(look.frames.length, 3);
  assert.ok(look.frames.every((frame) => frame.name && frame.initials));
  assert.ok(look.overlayLabel);
  assert.ok(look.captionText);
  assert.ok(look.episodeTitle.includes("Founders Unfiltered"));
});

test("buildEpisodeLookFromEpisode uses episode speakers when provided", () => {
  const look = preview.buildEpisodeLookFromEpisode(
    "panel-grid",
    {
      episodeName: "Agency Weekly · Pilot",
      speakerCount: 2,
      speakers: [
        { role: "Host", name: "Jamie Lee" },
        { role: "Guest 1", name: "Riley Park" },
      ],
    },
    { layout: "grid", pacing: "punchy" },
  );
  assert.strictEqual(look.frames[0].name, "Jamie Lee");
  assert.strictEqual(look.frames[0].initials, "JL");
  assert.strictEqual(look.pacingLabel, "Punchy");
});

test("new-show setup uses rich episode look previews instead of abstract layout thumbs", () => {
  assert.ok(ui.includes("renderEpisodeLookPreview"));
  assert.ok(ui.includes("create-show-preset-grid"));
  assert.ok(ui.includes("create-show-preview-panel"));
  assert.ok(ui.includes("create-show-blank-option"));
  assert.ok(!ui.includes("create-show-template-picker"));
  assert.ok(styles.includes(".episode-look-video"));
  assert.ok(styles.includes(".episode-look-caption"));
});

test("ACCEPTANCE: every named preset produces a distinct publish-ready look model", () => {
  const layouts = new Set();
  style.STYLE_PRESETS.forEach((preset) => {
    const look = preview.buildEpisodeLook(preset.id, { showName: "Demo Show" });
    assert.ok(look.presetName);
    assert.ok(look.captionStyle);
    assert.ok(look.formatCue);
    layouts.add(look.layoutId);
  });
  assert.ok(layouts.size >= 3);
});

console.log(`\nstyle look preview: ${passed} assertions passed`);