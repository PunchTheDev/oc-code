"use strict";

// Home screen polish smoke suite for Podcast Design Canvas (#112).
// Run with: `node tests/home-screen.test.js`.

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const gallery = require("../app/creator-template-gallery.js");
const templates = require("../app/show-templates.js");
const setup = require("../app/episode-setup.js");
const style = require("../app/episode-style.js");
const editor = require("../app/canvas-editor.js");

let passed = 0;
function test(name, fn) {
  fn();
  passed += 1;
  console.log(`  ok ${name}`);
}

const ui = fs.readFileSync(path.join(__dirname, "../app/episode-setup.ui.js"), "utf8");
const styles = fs.readFileSync(path.join(__dirname, "../app/styles.css"), "utf8");
const indexHtml = fs.readFileSync(path.join(__dirname, "../index.html"), "utf8");

test("home screen exposes one primary start CTA and quieter secondary paths", () => {
  assert.ok(ui.includes("home-primary-cta"));
  assert.ok(ui.includes("Create show & import episode →"));
  assert.ok(ui.includes("home-secondary-links"));
  assert.ok(ui.includes("home-explore-panel"));
  assert.ok(ui.includes("Preview style presets"));
  assert.ok(!ui.includes("Gallery walkthrough"));
  assert.ok(!ui.includes('class: "workspace-actions"'));
  assert.ok(!ui.includes("Try style preset cards"));
  assert.ok(!ui.includes("Try publish flow"));
});

test("home gallery spotlight renders preview thumbnails and browse entry", () => {
  assert.ok(ui.includes("renderHomeGallerySpotlight"));
  assert.ok(ui.includes("home-gallery-thumb-grid"));
  assert.ok(ui.includes("renderGalleryPreviewThumb"));
  assert.ok(ui.includes("Browse creator gallery →"));
  assert.ok(styles.includes(".home-gallery-thumb-card"));
  assert.ok(styles.includes(".home-primary-cta"));
});

test("library intro copy focuses creators on the main start path", () => {
  assert.ok(indexHtml.includes("Start your next episode"));
  assert.ok(ui.includes('heading.textContent = "Start your next episode"'));
});

test("ACCEPTANCE: gallery spotlight uses meaningful preview content from listings", () => {
  gallery._resetListingCounter();
  templates._resetTemplateCounter();

  const draft = setup.createDraft();
  draft.episodeName = "Founders Unfiltered #7";
  draft.sourceMode = "upload";
  draft.speakers = [
    Object.assign(setup.createSpeaker("Host"), { name: "Sam Rivera", fileName: "sam.mp4" }),
    Object.assign(setup.createSpeaker("Guest 1"), { name: "Dana Kim", fileName: "dana.mp4" }),
  ];
  const episode = setup.summarize(draft);
  const selection = style.createSelection();
  selection.presetId = "split-stage";
  const applied = style.summarizeStyle(selection, episode.speakerCount);
  let doc = editor.createFromStyle(applied, episode, selection);
  doc = editor.updateElement(doc, "titleText", "Split Stage Layout");

  const template = templates.createTemplate("Agency Split", doc, "tpl-home-preview");
  let store = gallery.createGallery();
  store = gallery.publishListing(store, template, {
    name: "Founders Split Look",
    description: "Side-by-side interview layout with captions.",
    styleTags: ["interview", "split-stage"],
  });

  const listing = gallery.getListing(store, gallery.listListings(store)[0].id);
  assert.strictEqual(listing.previewImage.presetName, "Split Stage");
  assert.strictEqual(listing.previewImage.titleText, "Split Stage Layout");
  assert.ok(listing.styleTags.length >= 1);
});

console.log(`\nhome screen: ${passed} assertions passed`);
