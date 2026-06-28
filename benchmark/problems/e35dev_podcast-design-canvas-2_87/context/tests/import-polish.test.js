"use strict";

// Episode import UI polish smoke suite for Podcast Design Canvas (#77).
// Run with: `node tests/import-polish.test.js`.

const assert = require("assert");
const fs = require("fs");
const path = require("path");

let passed = 0;
function test(name, fn) {
  fn();
  passed += 1;
  console.log(`  ok ${name}`);
}

const styles = fs.readFileSync(path.join(__dirname, "../app/styles.css"), "utf8");
const ui = fs.readFileSync(path.join(__dirname, "../app/episode-setup.ui.js"), "utf8");

test("styles define shared btn-primary and primary CTA hierarchy", () => {
  assert.ok(/\.btn-primary,\s*\nbutton\.primary,\s*\n\.primary/.test(styles));
  assert.ok(/\.btn-secondary,\s*\nbutton\.ghost,\s*\n\.ghost/.test(styles));
});

test("styles include spaced speaker cards and responsive import layout", () => {
  assert.ok(styles.includes(".speaker-stack"));
  assert.ok(styles.includes(".speaker-core"));
  assert.ok(styles.includes(".setup-import"));
  assert.ok(styles.includes("@media (max-width: 720px)"));
});

test("import setup screen uses consistent forward CTA classes with create-show", () => {
  assert.ok(ui.includes('class: "btn-primary setup-continue-btn"'));
  assert.ok(ui.includes('class: "btn-primary create-show-continue-btn"'));
  assert.ok(ui.includes("setup-cta-bar"));
});

test("ACCEPTANCE: library → create show → import path keeps polished setup structure", () => {
  assert.ok(ui.includes('class: "setup setup-import"'));
  assert.ok(ui.includes("setup-speakers-card"));
  assert.ok(ui.includes("speaker-card"));
  assert.ok(styles.includes(".setup-cta-bar"));
});

console.log(`\nimport polish: ${passed} assertions passed`);
