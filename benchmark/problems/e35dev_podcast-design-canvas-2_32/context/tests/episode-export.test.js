"use strict";

// Episode export smoke suite for Podcast Design Canvas (#30).
// Guards readiness checks, export options, final summary, and completed export state.
// Run with: `node tests/episode-export.test.js`.

const assert = require("assert");
const setup = require("../app/episode-setup.js");
const style = require("../app/episode-style.js");
const audio = require("../app/audio-polish.js");
const moments = require("../app/visual-moments.js");
const exportApi = require("../app/episode-export.js");

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

function completeContext(episode) {
  const selection = style.createSelection();
  const appliedStyle = style.summarizeStyle(selection, episode.speakerCount);
  const polish = audio.summarizePolish(audio.createPolish(episode));
  const board = moments.createBoard(episode);
  const withMoment = moments.addMoment(board, "caption", { time: "1:00", text: "Welcome back", speakerRole: "Host" });
  const momentsSummary = moments.summarizeBoard(withMoment);
  return {
    audioPolish: polish,
    appliedStyle,
    templateName: "Founders Unfiltered",
    momentsSummary,
  };
}

test("offers practical platform, resolution, and caption export options", () => {
  assert.ok(exportApi.PLATFORMS.length >= 3);
  assert.ok(exportApi.RESOLUTIONS.length >= 2);
  assert.ok(exportApi.CAPTION_MODES.length >= 2);
});

test("validateReadiness requires audio polish and visual style", () => {
  const episode = setup.summarize(completeUploadDraft());
  const missingBoth = exportApi.validateReadiness({});
  assert.strictEqual(missingBoth.ok, false);
  assert.ok(missingBoth.error.includes("polish your audio"));
  assert.ok(missingBoth.error.includes("choose a visual style"));

  const ctx = completeContext(episode);
  assert.strictEqual(exportApi.validateReadiness(ctx).ok, true);
});

test("updateOption changes platform, resolution, caption mode, and template", () => {
  let job = exportApi.createExport({ episodeName: "Demo" });
  job = exportApi.updateOption(job, "platform", "download");
  job = exportApi.updateOption(job, "resolution", "720p");
  job = exportApi.updateOption(job, "captionMode", "sidecar");
  job = exportApi.updateOption(job, "templateName", "Weeknight Live");

  assert.strictEqual(job.platform, "download");
  assert.strictEqual(job.resolution, "720p");
  assert.strictEqual(job.captionMode, "sidecar");
  assert.strictEqual(job.templateName, "Weeknight Live");
});

test("buildFinalSummary rolls speakers, audio, style, moments, and export choices", () => {
  const episode = setup.summarize(completeUploadDraft());
  const ctx = completeContext(episode);
  const job = exportApi.createExport(episode, { templateName: "Founders Unfiltered" });
  const summary = exportApi.buildFinalSummary(episode, ctx, job);

  assert.strictEqual(summary.episodeName, "Founders Unfiltered #7");
  assert.ok(summary.lines.some((line) => line.indexOf("Audio:") === 0));
  assert.ok(summary.lines.some((line) => line.indexOf("Visual style:") === 0));
  assert.ok(summary.lines.some((line) => line.indexOf("Show template:") === 0));
  assert.ok(summary.lines.some((line) => line.indexOf("Visual moments:") === 0));
  assert.ok(summary.lines.some((line) => line.indexOf("Export:") === 0));
});

test("startExport blocks when required choices are missing", () => {
  const episode = setup.summarize(completeUploadDraft());
  const job = exportApi.createExport(episode);
  const blocked = exportApi.startExport(job, episode, {});
  assert.strictEqual(blocked.ok, false);
  assert.ok(blocked.error);
  assert.strictEqual(blocked.state.status, "draft");
});

test("runExport completes with a ready-to-download filename", () => {
  const episode = setup.summarize(completeUploadDraft());
  const ctx = completeContext(episode);
  const job = exportApi.createExport(episode, { templateName: "Founders Unfiltered" });
  const result = exportApi.runExport(job, episode, ctx);

  assert.strictEqual(result.ok, true);
  assert.strictEqual(result.state.status, "ready");
  assert.strictEqual(result.state.progress, 100);
  assert.strictEqual(result.state.downloadName, "Founders-Unfiltered-7-1080p.mp4");

  const summary = exportApi.summarizeExport(result.state);
  assert.strictEqual(summary.ready, true);
  assert.strictEqual(summary.downloadName, "Founders-Unfiltered-7-1080p.mp4");
});

test("ACCEPTANCE: review episode choices, pick export options, start export, reach ready state", () => {
  const draft = completeUploadDraft();
  assert.strictEqual(setup.validateDraft(draft).ok, true);

  const episode = setup.summarize(draft);
  const ctx = completeContext(episode);
  assert.strictEqual(exportApi.validateReadiness(ctx).ok, true);

  let job = exportApi.createExport(episode, { templateName: "Founders Unfiltered" });
  job = exportApi.updateOption(job, "platform", "youtube");
  job = exportApi.updateOption(job, "resolution", "1080p");
  job = exportApi.updateOption(job, "captionMode", "burn-in");

  const preview = exportApi.buildFinalSummary(episode, ctx, job);
  assert.ok(preview.lines.length >= 5);

  const result = exportApi.runExport(job, episode, ctx);
  assert.strictEqual(result.ok, true);
  assert.strictEqual(result.state.status, "ready");
  assert.ok(result.state.downloadName.endsWith(".mp4"));
});

console.log(`\nepisode export: ${passed} assertions passed`);