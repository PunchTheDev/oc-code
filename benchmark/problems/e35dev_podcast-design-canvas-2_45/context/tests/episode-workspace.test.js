"use strict";

// Guided episode workspace smoke suite for Podcast Design Canvas (#40).
// Run with: `node tests/episode-workspace.test.js`.

const assert = require("assert");
const setup = require("../app/episode-setup.js");
const style = require("../app/episode-style.js");
const audio = require("../app/audio-polish.js");
const moments = require("../app/visual-moments.js");
const workspace = require("../app/episode-workspace.js");
const review = require("../app/publish-review.js");
const exportApi = require("../app/episode-export.js");

let passed = 0;
function test(name, fn) {
  fn();
  passed += 1;
  console.log(`  ok ${name}`);
}

function completeDraft() {
  const draft = setup.createDraft();
  draft.episodeName = "Founders Unfiltered #7";
  draft.sourceMode = "upload";
  draft.speakers = [
    Object.assign(setup.createSpeaker("Host"), { name: "Sam Rivera", fileName: "sam.mp4" }),
    Object.assign(setup.createSpeaker("Guest 1"), { name: "Dana Kim", fileName: "dana.mp4" }),
  ];
  return draft;
}

function baseCtx(episode, overrides) {
  const selection = style.createSelection();
  let board = moments.createBoard(episode);
  board = moments.addMoment(board, "caption", { time: 30, text: "Welcome", speakerRole: "Host" });
  return Object.assign({
    appliedStyle: style.summarizeStyle(selection, episode.speakerCount),
    audioPolish: audio.summarizePolish(audio.createPolish(episode)),
    templateName: "Founders Format",
    momentsSummary: moments.summarizeBoard(board),
    contextApproved: true,
    exportReady: true,
    publishReviewApproved: false,
    exportStatus: "draft",
    exportDownloadName: "",
  }, overrides || {});
}

test("buildWorkspace lists ordered stages for setup through export", () => {
  const episode = setup.summarize(completeDraft());
  const ws = workspace.buildWorkspace(episode, {});
  assert.deepStrictEqual(ws.stages.map((s) => s.id), workspace.STAGE_ORDER);
  assert.strictEqual(ws.totalStages, 7);
  const setupStage = workspace.getStage(ws, "setup");
  assert.strictEqual(setupStage.status, workspace.STATUS.COMPLETE);
});

test("workspace reflects style progress when a preset is applied", () => {
  const episode = setup.summarize(completeDraft());
  const ctx = baseCtx(episode, { audioPolish: null, appliedStyle: null, templateName: "", momentsSummary: { total: 0 } });
  let ws = workspace.buildWorkspace(episode, ctx);
  assert.strictEqual(workspace.getStage(ws, "style").status, workspace.STATUS.ACTIVE);

  const withStyle = baseCtx(episode, {
    audioPolish: null,
    templateName: "",
    momentsSummary: { total: 0 },
  });
  ws = workspace.buildWorkspace(episode, withStyle);
  const styleStage = workspace.getStage(ws, "style");
  assert.strictEqual(styleStage.status, workspace.STATUS.COMPLETE);
  assert.ok(styleStage.summary.indexOf("Studio") >= 0 || styleStage.summary.length > 0);
});

test("workspace reflects publish review and export readiness", () => {
  const episode = setup.summarize(completeDraft());
  const ctx = baseCtx(episode);
  let ws = workspace.buildWorkspace(episode, ctx);
  assert.strictEqual(workspace.getStage(ws, "review").status, workspace.STATUS.ACTIVE);
  assert.strictEqual(workspace.getStage(ws, "export").status, workspace.STATUS.PENDING);

  ws = workspace.buildWorkspace(episode, Object.assign({}, ctx, {
    publishReviewApproved: true,
    exportStatus: "ready",
    exportDownloadName: "Founders-Unfiltered-7-1080p.mp4",
  }));
  assert.strictEqual(workspace.getStage(ws, "review").status, workspace.STATUS.COMPLETE);
  assert.strictEqual(workspace.getStage(ws, "export").status, workspace.STATUS.COMPLETE);
  assert.ok(workspace.getStage(ws, "export").summary.indexOf(".mp4") >= 0);
});

test("summarizeWorkspace reports progress across stages", () => {
  const episode = setup.summarize(completeDraft());
  const ws = workspace.buildWorkspace(episode, baseCtx(episode, { publishReviewApproved: true, exportStatus: "ready", exportDownloadName: "episode.mp4" }));
  const summary = workspace.summarizeWorkspace(ws);
  assert.ok(summary.completeCount >= 5);
  assert.ok(summary.progressLine.indexOf("stages complete") >= 0);
  assert.ok(summary.workspaceLine.indexOf("Next:") === 0 || summary.currentStageLabel.length > 0);
});

test("ACCEPTANCE: workspace tracks setup, style, review, and export progress", () => {
  const draft = completeDraft();
  assert.strictEqual(setup.validateDraft(draft).ok, true);
  const episode = setup.summarize(draft);

  // After setup only
  let ws = workspace.buildWorkspace(episode, {});
  assert.strictEqual(workspace.getStage(ws, "setup").status, workspace.STATUS.COMPLETE);
  assert.strictEqual(workspace.getStage(ws, "style").status, workspace.STATUS.ACTIVE);
  assert.strictEqual(workspace.getStage(ws, "export").status, workspace.STATUS.PENDING);

  // After style + audio
  const ctx = baseCtx(episode, { publishReviewApproved: false, exportReady: false, templateName: "", momentsSummary: { total: 0, visibleCount: 0 } });
  ctx.exportReady = exportApi.validateReadiness({
    audioPolish: ctx.audioPolish,
    appliedStyle: ctx.appliedStyle,
  }).ok;
  ws = workspace.buildWorkspace(episode, ctx);
  assert.strictEqual(workspace.getStage(ws, "style").status, workspace.STATUS.COMPLETE);
  assert.strictEqual(workspace.getStage(ws, "audio").status, workspace.STATUS.COMPLETE);

  const publishReview = review.createReview(episode, {
    audioPolish: ctx.audioPolish,
    appliedStyle: ctx.appliedStyle,
    contextApproved: true,
    hasCanvas: false,
    momentsSummary: { total: 0 },
    captionCount: 0,
  });
  assert.strictEqual(review.canApprove(publishReview), true);
  const approved = review.approveReview(publishReview);
  assert.strictEqual(approved.ok, true);

  ws = workspace.buildWorkspace(episode, Object.assign({}, ctx, {
    publishReviewApproved: true,
    exportReady: true,
    exportStatus: "ready",
    exportDownloadName: "Founders-Unfiltered-7-1080p.mp4",
  }));
  assert.strictEqual(workspace.getStage(ws, "review").status, workspace.STATUS.COMPLETE);
  assert.strictEqual(workspace.getStage(ws, "export").status, workspace.STATUS.COMPLETE);
  assert.ok(workspace.summarizeWorkspace(ws).completeCount >= 4);
});

console.log(`\nepisode workspace: ${passed} assertions passed`);