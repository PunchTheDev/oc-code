"use strict";

// End-to-end speaker name integrity acceptance for issue #172.
// Run with: `node tests/speaker-name-integrity.test.js`.

const assert = require("assert");
const setup = require("../app/episode-setup.js");
const style = require("../app/episode-style.js");
const audio = require("../app/audio-polish.js");
const canvasEditor = require("../app/canvas-editor.js");
const moments = require("../app/visual-moments.js");
const context = require("../app/social-context.js");
const correction = require("../app/transcript-correction.js");
const templates = require("../app/show-templates.js");
const publishPackage = require("../app/publish-package.js");
const exportApi = require("../app/episode-export.js");

let passed = 0;
function test(name, fn) {
  fn();
  passed += 1;
  console.log(`  ok ${name}`);
}

function draftWithSamRiveraSocial() {
  const draft = setup.createDraft();
  draft.episodeName = "Founders Unfiltered #7";
  draft.sourceMode = "upload";
  draft.speakers = [
    Object.assign(setup.createSpeaker("Host"), {
      name: "Sam Rivera",
      fileName: "sam.mp4",
      social: {
        website: "https://samrivera.show",
        twitter: "https://x.com/samrivera",
        instagram: "",
        linkedin: "",
      },
    }),
    Object.assign(setup.createSpeaker("Guest 1"), {
      name: "Dana Kim",
      fileName: "dana.mp4",
      social: {
        website: "",
        twitter: "",
        instagram: "",
        linkedin: "https://linkedin.com/in/danakim",
      },
    }),
  ];
  return draft;
}

function assertNoCorruption(label, value) {
  const text = typeof value === "string" ? value : JSON.stringify(value);
  assert.ok(!text.includes("Riveraa"), `${label} must not contain Riveraa`);
  assert.ok(!text.includes("Sam Riveraa"), `${label} must not contain Sam Riveraa`);
}

test("ACCEPTANCE: Sam Rivera stays exact from setup through templates and export", () => {
  templates._resetTemplateCounter();
  const draft = draftWithSamRiveraSocial();
  assert.strictEqual(setup.validateDraft(draft).ok, true);

  const episode = setup.summarize(draft);
  assert.strictEqual(episode.speakers[0].name, "Sam Rivera");
  assert.strictEqual(episode.socialLinkCount, 3);

  let contextReview = context.createReview(episode);
  assert.ok(contextReview.speakers[0].spellingHints.includes("Sam River"));
  contextReview = context.updateSpeaker(contextReview, 0, {
    spellingHints: contextReview.speakers[0].spellingHints.concat("Sam Rivira"),
  });
  contextReview = context.approveReview(contextReview);
  assert.strictEqual(
    context.applyHintsToText("Sam River starts the episode", contextReview, "Host", "Sam Rivera"),
    "Sam Rivera starts the episode",
  );
  assert.strictEqual(
    context.applyHintsToText("Sam Rivera starts the episode", contextReview, "Host", "Sam Rivera"),
    "Sam Rivera starts the episode",
  );

  let board = moments.createBoard(episode);
  board = moments.addMoment(board, "caption", {
    time: "0:20",
    text: "Welcome Sam Rivera",
    speakerRole: "Host",
    speakerName: "Sam Rivera",
  });
  board = moments.addMoment(board, "caption", {
    time: "0:40",
    text: "Sam Rivira explains the launch",
    speakerRole: "Host",
    speakerName: "Sam Rivera",
  });
  board = moments.addMoment(board, "title", {
    time: "1:00",
    text: "Sam Rivera on building in public",
    speakerRole: "Host",
    speakerName: "Sam Rivera",
  });
  board = context.applyReviewToMoments(board, contextReview);
  assert.strictEqual(board.moments[0].text, "Welcome Sam Rivera");
  assert.ok(board.moments[1].text.includes("Sam Rivera"));
  assert.ok(!board.moments[1].text.includes("Sam Rivira"));
  assertNoCorruption("visual moments", board);

  const selection = style.createSelection();
  selection.presetId = "studio-spotlight";
  const appliedStyle = style.summarizeStyle(selection, episode.speakerCount);
  let canvasDoc = canvasEditor.createFromStyle(appliedStyle, episode, selection);
  canvasDoc = canvasEditor.updateElement(canvasDoc, "titleText", "Sam Rivera on building in public");
  canvasDoc = canvasEditor.updateElement(canvasDoc, "captionText", "Welcome Sam Rivera");
  canvasDoc = context.applyReviewToCanvas(canvasDoc, contextReview);
  assert.strictEqual(canvasDoc.titleText, "Sam Rivera on building in public");
  assert.strictEqual(canvasDoc.captionText, "Welcome Sam Rivera");
  assert.strictEqual(canvasDoc.speakerFrames[0].name, "Sam Rivera");
  assertNoCorruption("canvas", canvasDoc);

  let correctionReview = correction.createCorrectionReview(episode, {
    contextReview: contextReview,
    momentsBoard: board,
  });
  assertNoCorruption("correction review before approval", correctionReview);
  correctionReview = correction.approveCorrection(correctionReview);

  let pkg = publishPackage.createPackage(episode, {
    appliedStyle: appliedStyle,
    momentsBoard: board,
  });
  const applied = correction.applyCorrectionReview(correctionReview, {
    momentsBoard: board,
    canvasDoc: canvasDoc,
    publishPackage: pkg,
    speakers: draft.speakers,
  });
  board = applied.momentsBoard;
  canvasDoc = applied.canvasDoc;
  pkg = applied.publishPackage;
  assert.strictEqual(applied.speakers[0].name, "Sam Rivera");
  assert.strictEqual(pkg.speakerCredits[0].name, "Sam Rivera");
  assert.ok(pkg.description.includes("Sam Rivera"));
  assertNoCorruption("applied correction outputs", applied);

  let store = templates.createStore();
  store = templates.saveTemplate(
    store,
    templates.createTemplate("Founders Sam Layout", canvasDoc, "tpl-sam"),
  );
  const savedTemplate = templates.getTemplate(store, "tpl-sam");
  const canvasFromTemplate = templates.applyTemplateForEpisode(
    savedTemplate,
    episode,
    templates.styleSelectionFromCanvas(savedTemplate.canvas),
  );
  assert.strictEqual(canvasFromTemplate.speakerFrames[0].name, "Sam Rivera");
  assertNoCorruption("saved template", savedTemplate);
  assertNoCorruption("applied template", canvasFromTemplate);

  const publishPackageSummary = publishPackage.summarizePackage(pkg);
  const correctionSummary = correction.summarizeCorrection(correctionReview);
  const contextSummary = context.summarizeReview(contextReview);
  const momentsSummary = moments.summarizeBoard(board);
  const exportJob = exportApi.createExport(episode, {
    templateId: savedTemplate.id,
    templateName: savedTemplate.name,
  });
  const exportSummary = exportApi.buildFinalSummary(episode, {
    audioPolish: audio.summarizePolish(audio.createPolish(episode)),
    appliedStyle: appliedStyle,
    templateName: savedTemplate.name,
    momentsSummary: momentsSummary,
    contextSummary: contextSummary,
    correctionSummary: correctionSummary,
    publishPackageSummary: publishPackageSummary,
  }, exportJob);
  const finalText = exportSummary.lines.join("\n");
  assert.ok(finalText.includes("Sam Rivera"));
  assert.ok(finalText.includes("Show template: Founders Sam Layout"));
  assertNoCorruption("export summary", finalText);
});

console.log(`\nspeaker name integrity: ${passed} assertions passed`);