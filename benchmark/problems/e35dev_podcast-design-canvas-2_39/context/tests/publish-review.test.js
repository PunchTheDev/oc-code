"use strict";

// Publish review smoke suite for Podcast Design Canvas (#37).
// Guards blocked vs approved review states and export gating.
// Run with: `node tests/publish-review.test.js`.

const assert = require("assert");
const setup = require("../app/episode-setup.js");
const style = require("../app/episode-style.js");
const audio = require("../app/audio-polish.js");
const moments = require("../app/visual-moments.js");
const contextApi = require("../app/social-context.js");
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
    Object.assign(setup.createSpeaker("Host"), {
      name: "Sam Rivera",
      fileName: "sam.mp4",
      social: { website: "https://samrivera.show", twitter: "", instagram: "", linkedin: "" },
    }),
    Object.assign(setup.createSpeaker("Guest 1"), { name: "Dana Kim", fileName: "dana.mp4" }),
    Object.assign(setup.createSpeaker("Guest 2"), { name: "Marco Vidal", fileName: "marco.mp4" }),
  ];
  return draft;
}

function fullContext(episode, options) {
  const opts = options || {};
  const selection = style.createSelection();
  let board = moments.createBoard(episode);
  board = moments.addMoment(board, "caption", { time: "1:00", text: "Welcome back", speakerRole: "Host" });
  let contextReview = contextApi.createReview(episode);
  contextReview = contextApi.approveReview(contextReview);
  return {
    audioPolish: audio.summarizePolish(audio.createPolish(episode)),
    appliedStyle: style.summarizeStyle(selection, episode.speakerCount),
    templateName: opts.templateName || "Founders Unfiltered",
    hasCanvas: opts.hasCanvas !== false,
    contextApproved: opts.contextApproved !== false,
    contextSummary: contextApi.summarizeReview(contextReview),
    momentsSummary: moments.summarizeBoard(board),
    momentsBoard: board,
    captionCount: review.countVisibleCaptions(board),
  };
}

test("blocked review lists required fixes when audio and style are missing", () => {
  const episode = setup.summarize(completeDraft());
  const result = review.createReview(episode, { contextApproved: false });

  assert.strictEqual(review.canApprove(result), false);
  assert.ok(review.blockers(result).some((item) => item.id === "audio-missing"));
  assert.ok(review.blockers(result).some((item) => item.id === "style-missing"));
  assert.ok(review.warnings(result).some((item) => item.id === "captions-missing"));
  assert.strictEqual(result.timeline.length, 7);
});

test("social context is a blocker when links exist but context is not approved", () => {
  const episode = setup.summarize(completeDraft());
  const ctx = fullContext(episode, { contextApproved: false });
  const result = review.createReview(episode, ctx);

  assert.strictEqual(review.canApprove(result), false);
  assert.ok(review.blockers(result).some((item) => item.id === "context-missing"));
});

test("approveReview succeeds when required checks pass even with warnings", () => {
  const episode = setup.summarize(completeDraft());
  const ctx = fullContext(episode, { templateName: "", hasCanvas: false });
  let board = moments.createBoard(episode);
  ctx.momentsBoard = board;
  ctx.momentsSummary = moments.summarizeBoard(board);
  ctx.captionCount = 0;

  let publishReview = review.createReview(episode, ctx);
  assert.strictEqual(review.canApprove(publishReview), true);
  assert.ok(review.warnings(publishReview).some((item) => item.id === "captions-missing"));

  const approved = review.approveReview(publishReview);
  assert.strictEqual(approved.ok, true);
  assert.strictEqual(approved.review.approved, true);
  assert.strictEqual(review.validateExportGate(approved.review).ok, true);
});

test("approveReview is rejected while blockers remain", () => {
  const episode = setup.summarize(completeDraft());
  const publishReview = review.createReview(episode, {});
  const result = review.approveReview(publishReview);

  assert.strictEqual(result.ok, false);
  assert.ok(result.error);
  assert.strictEqual(review.validateExportGate(publishReview).ok, false);
});

test("validateExportGate blocks export until review is approved", () => {
  const episode = setup.summarize(completeDraft());
  const ctx = fullContext(episode);
  const publishReview = review.createReview(episode, ctx);

  assert.strictEqual(review.canApprove(publishReview), true);
  assert.strictEqual(review.validateExportGate(publishReview).ok, false);

  const approved = review.approveReview(publishReview);
  assert.strictEqual(review.validateExportGate(approved.review).ok, true);
  assert.strictEqual(exportApi.validateReadiness(ctx).ok, true);
});

test("ACCEPTANCE: blocked review, resolve requirements, approve, and reach export readiness", () => {
  const draft = completeDraft();
  assert.strictEqual(setup.validateDraft(draft).ok, true);
  const episode = setup.summarize(draft);

  let publishReview = review.createReview(episode, {});
  assert.strictEqual(review.approveReview(publishReview).ok, false);

  const ctx = fullContext(episode);
  publishReview = review.createReview(episode, ctx);
  assert.strictEqual(review.blockers(publishReview).length, 0);

  const approved = review.approveReview(publishReview);
  assert.strictEqual(approved.ok, true);
  const summary = review.summarizeReview(approved.review);
  assert.strictEqual(summary.approved, true);
  assert.ok(summary.reviewLine.includes("ready to export"));

  const exportCtx = {
    audioPolish: ctx.audioPolish,
    appliedStyle: ctx.appliedStyle,
    templateName: ctx.templateName,
    momentsSummary: ctx.momentsSummary,
    contextSummary: ctx.contextSummary,
  };
  assert.strictEqual(exportApi.validateReadiness(exportCtx).ok, true);
  assert.strictEqual(review.validateExportGate(approved.review).ok, true);
});

console.log(`\npublish review: ${passed} assertions passed`);