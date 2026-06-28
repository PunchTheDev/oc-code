"use strict";

// Show template library smoke suite for Podcast Design Canvas (#27).
// Guards saving, listing, selecting, and applying reusable show templates with
// current-episode speaker assignments.
// Run with: `node tests/show-templates.test.js`.

const assert = require("assert");
const setup = require("../app/episode-setup.js");
const style = require("../app/episode-style.js");
const editor = require("../app/canvas-editor.js");
const layers = require("../app/canvas-layers.js");
const templates = require("../app/show-templates.js");

let passed = 0;
function test(name, fn) {
  fn();
  passed += 1;
  console.log(`  ok ${name}`);
}

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

test("listTemplates returns saved templates sorted by name", () => {
  templates._resetTemplateCounter();
  let store = templates.createStore();
  store = templates.saveTemplate(store, templates.createTemplate("Zeta Show", { titleText: "Z" }, "tpl-z"));
  store = templates.saveTemplate(store, templates.createTemplate("Alpha Show", { titleText: "A" }, "tpl-a"));

  const list = templates.listTemplates(store);
  assert.strictEqual(list.length, 2);
  assert.strictEqual(list[0].name, "Alpha Show");
  assert.strictEqual(list[1].name, "Zeta Show");
});

test("styleSelectionFromCanvas restores preset, layout, and pacing", () => {
  const selection = templates.styleSelectionFromCanvas({
    presetId: "panel-grid",
    layoutId: "grid",
    pacingId: "dynamic",
  });
  assert.strictEqual(selection.presetId, "panel-grid");
  assert.strictEqual(selection.layout, "grid");
  assert.strictEqual(selection.pacing, "dynamic");
});

test("applyTemplateForEpisode keeps layout but uses the new episode speakers", () => {
  templates._resetTemplateCounter();
  const episodeA = setup.summarize(completeUploadDraft());
  const selection = style.createSelection();
  selection.presetId = "studio-spotlight";
  const applied = style.summarizeStyle(selection, episodeA.speakerCount);
  let doc = editor.createFromStyle(applied, episodeA, selection);
  doc = editor.updateElement(doc, "titleText", "Founders Unfiltered Layout");
  doc = editor.updateElement(doc, "background", "#223344");

  const template = templates.createTemplate("Founders Unfiltered", doc, "tpl-founders");
  const stored = templates.applyTemplate(template);
  assert.strictEqual(stored.speakerFrames.length, 3);
  assert.strictEqual(stored.speakerFrames[0].name, "Sam Rivera");

  const episodeB = setup.summarize(twoSpeakerDraft());
  const styleB = templates.styleSelectionFromCanvas(doc);
  const appliedB = templates.applyTemplateForEpisode(template, episodeB, styleB);

  assert.strictEqual(appliedB.titleText, "Founders Unfiltered Layout");
  assert.strictEqual(appliedB.background, "#223344");
  assert.strictEqual(appliedB.presetName, "Studio Spotlight");
  assert.strictEqual(appliedB.speakerFrames.length, 2);
  assert.deepStrictEqual(appliedB.speakerFrames.map((frame) => frame.name), ["Alex Chen", "Jordan Lee"]);
});

test("serializeStore and deserializeStore round-trip the template library", () => {
  templates._resetTemplateCounter();
  let store = templates.createStore();
  store = templates.saveTemplate(
    store,
    templates.createTemplate("Agency Weekly", { titleText: "Weekly", presetName: "Split Stage" }, "tpl-agency"),
  );
  const restored = templates.deserializeStore(templates.serializeStore(store));
  assert.strictEqual(templates.listTemplates(restored).length, 1);
  assert.strictEqual(templates.getTemplate(restored, "tpl-agency").name, "Agency Weekly");
});

test("ACCEPTANCE: save, list, select, and apply a reusable show template", () => {
  templates._resetTemplateCounter();
  const draftA = completeUploadDraft();
  assert.strictEqual(setup.validateDraft(draftA).ok, true);

  const episodeA = setup.summarize(draftA);
  const selection = style.createSelection();
  selection.presetId = "split-stage";
  selection.layout = "split";
  const applied = style.summarizeStyle(selection, episodeA.speakerCount);

  let doc = editor.createFromStyle(applied, episodeA, selection);
  doc = editor.updateElement(doc, "titleText", "Agency Split Layout");
  const captionsIdx = doc.layers.findIndex((layer) => layer.type === "captions");
  doc = editor.updateLayers(doc, layers.moveLayer(doc.layers, captionsIdx, -1));
  assert.strictEqual(editor.validateForSave(doc).ok, true);

  let store = templates.createStore();
  const nameCheck = templates.validateTemplateName(store, "Agency Split");
  assert.strictEqual(nameCheck.ok, true);
  const template = templates.createTemplate(nameCheck.name, doc, "tpl-agency-split");
  store = templates.saveTemplate(store, template);
  assert.strictEqual(templates.listTemplates(store).length, 1);

  const draftB = twoSpeakerDraft();
  const episodeB = setup.summarize(draftB);
  const picked = templates.getTemplate(store, "tpl-agency-split");
  const styleFromTemplate = templates.styleSelectionFromCanvas(picked.canvas);
  const canvasForB = templates.applyTemplateForEpisode(picked, episodeB, styleFromTemplate);
  const styleForB = style.summarizeStyle(styleFromTemplate, episodeB.speakerCount);

  assert.strictEqual(canvasForB.titleText, "Agency Split Layout");
  assert.strictEqual(styleForB.presetName, "Split Stage");
  assert.strictEqual(canvasForB.speakerFrames.length, 2);
  assert.strictEqual(canvasForB.speakerFrames[0].name, "Alex Chen");
  assert.ok(canvasForB.layers.length >= 5, "saved layout layers carry over");
});

console.log(`\nshow templates: ${passed} assertions passed`);