"use strict";

// Canvas editor + show template smoke suite for Podcast Design Canvas (#11).
// Guards opening the editor from a preset, customizing layout elements, saving a named
// template, and reselecting it for a future episode.
// Run with: `node tests/canvas-editor.test.js`.

const assert = require("assert");
const setup = require("../app/episode-setup.js");
const style = require("../app/episode-style.js");
const layers = require("../app/canvas-layers.js");
const editor = require("../app/canvas-editor.js");
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

test("createFromStyle seeds a canvas document from the applied preset", () => {
  const draft = completeUploadDraft();
  const episode = setup.summarize(draft);
  const selection = style.createSelection();
  selection.presetId = "panel-grid";
  const applied = style.summarizeStyle(selection, episode.speakerCount);
  const doc = editor.createFromStyle(applied, episode, selection);

  assert.strictEqual(doc.presetId, "panel-grid");
  assert.strictEqual(doc.presetName, "Panel Grid");
  assert.strictEqual(doc.background, applied.background);
  assert.ok(doc.layers.length >= 5, "canvas has layout layers");
  assert.strictEqual(doc.speakerFrames.length, 3);
  assert.deepStrictEqual(doc.speakerFrames.map((f) => f.role), ["Host", "Guest 1", "Guest 2"]);
});

test("updateElement changes title and background on the canvas document", () => {
  const draft = completeUploadDraft();
  const episode = setup.summarize(draft);
  const selection = style.createSelection();
  const applied = style.summarizeStyle(selection, episode.speakerCount);
  let doc = editor.createFromStyle(applied, episode, selection);

  doc = editor.updateElement(doc, "titleText", "My Show — Episode 12");
  assert.strictEqual(doc.titleText, "My Show — Episode 12");

  doc = editor.updateElement(doc, "background", "#112233");
  assert.strictEqual(doc.background, "#112233");
});

test("updateLayers reorders the stack through the layer primitives", () => {
  const draft = completeUploadDraft();
  const episode = setup.summarize(draft);
  const selection = style.createSelection();
  const applied = style.summarizeStyle(selection, episode.speakerCount);
  let doc = editor.createFromStyle(applied, episode, selection);
  const speakerIdx = doc.layers.findIndex((layer) => layer.type === "speaker");
  const topBefore = doc.layers[0].id;
  doc = editor.updateLayers(doc, layers.moveLayer(doc.layers, speakerIdx, -1));
  assert.notStrictEqual(doc.layers[0].id, topBefore, "layer stack changed");
});

test("validateTemplateName requires a unique non-empty name", () => {
  const store = templates.createStore();
  assert.strictEqual(templates.validateTemplateName(store, "").ok, false);
  templates._resetTemplateCounter();
  store.templates = [templates.createTemplate("My Show", { titleText: "x" })];
  assert.strictEqual(templates.validateTemplateName(store, "My Show").ok, false);
  assert.strictEqual(templates.validateTemplateName(store, "Another Show").ok, true);
});

test("saveTemplate lists and returns a saved show template", () => {
  templates._resetTemplateCounter();
  let store = templates.createStore();
  const canvas = { titleText: "Demo", presetName: "Studio Spotlight", layers: [] };
  const template = templates.createTemplate("Weeknight Live", canvas, "tpl-1");
  store = templates.saveTemplate(store, template);

  assert.strictEqual(templates.listTemplates(store).length, 1);
  assert.strictEqual(templates.listTemplates(store)[0].name, "Weeknight Live");
  const loaded = templates.getTemplate(store, "tpl-1");
  assert.strictEqual(loaded.canvas.titleText, "Demo");
});

// End-to-end: setup → preset → open canvas → customize → save → reselect.
test("ACCEPTANCE: customize canvas, save named template, and reselect it", () => {
  templates._resetTemplateCounter();
  const draft = completeUploadDraft();
  assert.strictEqual(setup.validateDraft(draft).ok, true);

  const episode = setup.summarize(draft);
  const selection = style.createSelection();
  selection.presetId = "studio-spotlight";
  const applied = style.summarizeStyle(selection, episode.speakerCount);

  let doc = editor.createFromStyle(applied, episode, selection);
  assert.ok(doc.layers.some((layer) => layer.type === "speaker"), "canvas opens with speaker frames");

  doc = editor.updateElement(doc, "titleText", "Founders Unfiltered Show Layout");
  const captionsIdx = doc.layers.findIndex((layer) => layer.type === "captions");
  doc = editor.updateLayers(doc, layers.moveLayer(doc.layers, captionsIdx, -1));
  assert.strictEqual(editor.validateForSave(doc).ok, true);

  let store = templates.createStore();
  const nameCheck = templates.validateTemplateName(store, "Founders Unfiltered");
  assert.strictEqual(nameCheck.ok, true);
  const template = templates.createTemplate(nameCheck.name, doc, "tpl-founders");
  store = templates.saveTemplate(store, template);
  assert.strictEqual(templates.listTemplates(store).length, 1);

  const reselected = templates.getTemplate(store, "tpl-founders");
  assert.ok(reselected, "saved template is available for future episodes");
  const appliedCanvas = templates.applyTemplate(reselected);
  assert.strictEqual(appliedCanvas.titleText, "Founders Unfiltered Show Layout");
  assert.strictEqual(appliedCanvas.presetName, "Studio Spotlight");
  assert.ok(appliedCanvas.layers.length >= 5);
});

console.log(`\ncanvas editor: ${passed} assertions passed`);
