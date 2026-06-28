"use strict";

// Creator template gallery smoke suite for Podcast Design Canvas (#106).
// Guards publishing saved layouts, browsing listings, preview metadata, and applying
// gallery templates to new episodes with current speaker assignments.
// Run with: `node tests/creator-template-gallery.test.js`.

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const setup = require("../app/episode-setup.js");
const style = require("../app/episode-style.js");
const editor = require("../app/canvas-editor.js");
const layers = require("../app/canvas-layers.js");
const templates = require("../app/show-templates.js");
const gallery = require("../app/creator-template-gallery.js");

let passed = 0;
function test(name, fn) {
  fn();
  passed += 1;
  console.log(`  ok ${name}`);
}

const ui = fs.readFileSync(path.join(__dirname, "../app/episode-setup.ui.js"), "utf8");
const styles = fs.readFileSync(path.join(__dirname, "../app/styles.css"), "utf8");
const indexHtml = fs.readFileSync(path.join(__dirname, "../index.html"), "utf8");

function completeUploadDraft() {
  const draft = setup.createDraft();
  draft.episodeName = "Founders Unfiltered #7";
  draft.sourceMode = "upload";
  draft.speakers = [
    Object.assign(setup.createSpeaker("Host"), { name: "Sam Rivera", fileName: "sam.mp4" }),
    Object.assign(setup.createSpeaker("Guest 1"), { name: "Dana Kim", fileName: "dana.mp4" }),
    Object.assign(setup.createSpeaker("Guest 2"), { name: "Marco Vidal", fileName: "marco.mp4" }),
  ];
  return draft;
}

function twoSpeakerDraft() {
  const draft = setup.createDraft();
  draft.episodeName = "New Episode";
  draft.sourceMode = "upload";
  draft.speakers = [
    Object.assign(setup.createSpeaker("Host"), { name: "Alex Chen", fileName: "alex.mp4" }),
    Object.assign(setup.createSpeaker("Guest 1"), { name: "Jordan Lee", fileName: "jordan.mp4" }),
  ];
  return draft;
}

function agencySplitTemplate() {
  templates._resetTemplateCounter();
  const episodeA = setup.summarize(completeUploadDraft());
  const selection = style.createSelection();
  selection.presetId = "split-stage";
  selection.layout = "split";
  const applied = style.summarizeStyle(selection, episodeA.speakerCount);

  let doc = editor.createFromStyle(applied, episodeA, selection);
  doc = editor.updateElement(doc, "titleText", "Agency Split Layout");
  const captionsIdx = doc.layers.findIndex((layer) => layer.type === "captions");
  doc = editor.updateLayers(doc, layers.moveLayer(doc.layers, captionsIdx, -1));
  assert.strictEqual(editor.validateForSave(doc).ok, true);

  return templates.createTemplate("Agency Split", doc, "tpl-agency-split");
}

test("buildPreviewImage and deriveStyleTags capture layout metadata", () => {
  const template = agencySplitTemplate();
  const preview = gallery.buildPreviewImage(template.canvas);
  assert.strictEqual(preview.presetName, "Split Stage");
  assert.strictEqual(preview.layoutId, "split");
  assert.strictEqual(preview.titleText, "Agency Split Layout");

  const tags = gallery.deriveStyleTags(template.canvas);
  assert.ok(tags.includes("split-stage"));
  assert.ok(tags.includes("split"));
});

test("publishListing stores name, description, style tags, and preview image", () => {
  gallery._resetListingCounter();
  const template = agencySplitTemplate();
  let store = gallery.createGallery();
  store = gallery.publishListing(store, template, {
    name: "Founders Split Look",
    description: "Side-by-side interview with bold captions and lower-thirds.",
    styleTags: ["interview", "split-stage", "bold-captions"],
    creatorName: "Sam Rivera",
  });

  const list = gallery.listListings(store);
  assert.strictEqual(list.length, 1);
  assert.strictEqual(list[0].name, "Founders Split Look");
  assert.strictEqual(list[0].description, "Side-by-side interview with bold captions and lower-thirds.");
  assert.deepStrictEqual(list[0].styleTags, ["interview", "split-stage", "bold-captions"]);
  assert.strictEqual(list[0].previewImage.titleText, "Agency Split Layout");
  assert.strictEqual(list[0].sourceTemplateId, "tpl-agency-split");
});

test("applyListingForEpisode keeps layout but uses the new episode speakers", () => {
  gallery._resetListingCounter();
  const template = agencySplitTemplate();
  let store = gallery.createGallery();
  store = gallery.publishListing(store, template, {
    name: "Agency Split Look",
    description: "Reusable split layout",
  });

  const listing = gallery.getListing(store, gallery.listListings(store)[0].id);
  const episodeB = setup.summarize(twoSpeakerDraft());
  const styleFromListing = gallery.styleSelectionFromListing(listing);
  const applied = gallery.applyListingForEpisode(listing, episodeB, styleFromListing);
  const styleForB = style.summarizeStyle(styleFromListing, episodeB.speakerCount);

  assert.strictEqual(applied.titleText, "Agency Split Layout");
  assert.strictEqual(styleForB.presetName, "Split Stage");
  assert.strictEqual(applied.speakerFrames.length, 2);
  assert.deepStrictEqual(applied.speakerFrames.map((frame) => frame.name), ["Alex Chen", "Jordan Lee"]);
  assert.ok(applied.layers.length >= 5, "gallery layout layers carry over");
});

test("serializeGallery and deserializeGallery round-trip the gallery store", () => {
  gallery._resetListingCounter();
  const template = agencySplitTemplate();
  let store = gallery.createGallery();
  store = gallery.publishListing(store, template, {
    name: "Round Trip Layout",
    description: "Persisted gallery listing",
    styleTags: ["panel", "broadcast"],
  });

  const restored = gallery.deserializeGallery(gallery.serializeGallery(store));
  assert.strictEqual(gallery.listListings(restored).length, 1);
  const listing = gallery.getListing(restored, gallery.listListings(restored)[0].id);
  assert.strictEqual(listing.name, "Round Trip Layout");
  assert.strictEqual(listing.canvas.titleText, "Agency Split Layout");
});

test("UI exposes creator gallery browse, publish, and demo entry points", () => {
  assert.ok(ui.includes("renderCreatorGalleryBrowse"));
  assert.ok(ui.includes("renderPublishToGallery"));
  assert.ok(ui.includes("openGalleryDemo"));
  assert.ok(ui.includes("Browse creator gallery"));
  assert.ok(ui.includes("Publish to gallery"));
  assert.ok(ui.includes("Creator template gallery"));
  assert.ok(ui.includes("Apply gallery template"));
  assert.ok(indexHtml.includes("creator-template-gallery.js"));
  assert.ok(styles.includes(".creator-gallery-grid"));
  assert.ok(styles.includes(".creator-gallery-layout"));
});

test("ACCEPTANCE: publish, browse, preview, and apply a creator gallery template", () => {
  gallery._resetListingCounter();
  templates._resetTemplateCounter();

  const draftA = completeUploadDraft();
  assert.strictEqual(setup.validateDraft(draftA).ok, true);
  const template = agencySplitTemplate();

  let templateStore = templates.createStore();
  templateStore = templates.saveTemplate(templateStore, template);
  assert.strictEqual(templates.listTemplates(templateStore).length, 1);

  let galleryStore = gallery.createGallery();
  const nameCheck = gallery.validateListingName(galleryStore, "Creator Split Stage");
  assert.strictEqual(nameCheck.ok, true);
  galleryStore = gallery.publishListing(galleryStore, template, {
    name: nameCheck.name,
    description: "Shareable split-stage layout with captions and brand styling.",
    styleTags: gallery.deriveStyleTags(template.canvas).concat(["creator-share"]),
    creatorName: "Founders Unfiltered",
  });

  const browse = gallery.listListings(galleryStore);
  assert.strictEqual(browse.length, 1);
  assert.ok(browse[0].previewImage.background, "preview image descriptor is available for UI rendering");
  assert.ok(browse[0].styleTags.includes("creator-share"));

  const picked = gallery.getListing(galleryStore, browse[0].id);
  const draftB = twoSpeakerDraft();
  const episodeB = setup.summarize(draftB);
  const previewStyle = gallery.styleSelectionFromListing(picked);
  const previewCanvas = gallery.applyListingForEpisode(picked, episodeB, previewStyle);
  assert.strictEqual(previewCanvas.speakerFrames[0].name, "Alex Chen");
  assert.strictEqual(previewCanvas.presetName, "Split Stage");

  const appliedCanvas = gallery.applyListingForEpisode(picked, episodeB, previewStyle);
  assert.strictEqual(appliedCanvas.titleText, "Agency Split Layout");
  assert.strictEqual(appliedCanvas.background, template.canvas.background);
  assert.ok(
    appliedCanvas.layers.some((layer) => layer.type === "captions"),
    "captions layer carries over from gallery template",
  );
});

console.log(`\ncreator template gallery: ${passed} assertions passed`);