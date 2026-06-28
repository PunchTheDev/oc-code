"use strict";

// Speaker bucket visual cues smoke suite for Podcast Design Canvas (#92).
// Run with: `node tests/speaker-bucket-cues.test.js`.

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const setup = require("../app/episode-setup.js");

let passed = 0;
function test(name, fn) {
  fn();
  passed += 1;
  console.log(`  ok ${name}`);
}

const styles = fs.readFileSync(path.join(__dirname, "../app/styles.css"), "utf8");
const ui = fs.readFileSync(path.join(__dirname, "../app/episode-setup.ui.js"), "utf8");

test("speakerBucketCueClass maps Host and Guest buckets to stable CSS classes", () => {
  assert.strictEqual(setup.speakerBucketCueClass("Host"), "speaker-bucket-host");
  assert.strictEqual(setup.speakerBucketCueClass("Guest 1"), "speaker-bucket-guest-1");
  assert.strictEqual(setup.speakerBucketCueClass("Guest 2"), "speaker-bucket-guest-2");
  assert.strictEqual(setup.speakerBucketCueClass(""), "speaker-bucket-unassigned");
});

test("styles define distinct bucket accents for Host and Guest roles", () => {
  assert.ok(styles.includes(".speaker-bucket-host"));
  assert.ok(styles.includes(".speaker-bucket-guest-1"));
  assert.ok(styles.includes(".speaker-bucket-guest-2"));
  assert.ok(styles.includes(".speaker-card[class*=\"speaker-bucket-\"]"));
});

test("import UI applies bucket classes to cards, badges, and overview chips", () => {
  assert.ok(ui.includes("speakerBucketCueClass"));
  assert.ok(ui.includes("syncSpeakerBucketCues"));
  assert.ok(ui.includes("applySpeakerBucketCue"));
  assert.ok(ui.includes("speaker speaker-card ${bucketClass}"));
});

test("ACCEPTANCE: default draft speakers expose Host, Guest 1, and Guest 2 bucket cues", () => {
  const draft = setup.createDraft();
  const classes = draft.speakers.map((speaker) => setup.speakerBucketCueClass(speaker.role));
  assert.deepStrictEqual(classes, [
    "speaker-bucket-host",
    "speaker-bucket-guest-1",
    "speaker-bucket-guest-2",
  ]);
});

console.log(`\nspeaker bucket cues: ${passed} assertions passed`);