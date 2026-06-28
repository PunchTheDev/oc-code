"use strict";

// Social context smoke suite for Podcast Design Canvas (#34).
// Guards deriving hints from social links, approving edits, and applying hints to
// moments and export summaries.
// Run with: `node tests/social-context.test.js`.

const assert = require("assert");
const setup = require("../app/episode-setup.js");
const style = require("../app/episode-style.js");
const audio = require("../app/audio-polish.js");
const moments = require("../app/visual-moments.js");
const context = require("../app/social-context.js");
const exportApi = require("../app/episode-export.js");

let passed = 0;
function test(name, fn) {
  fn();
  passed += 1;
  console.log(`  ok ${name}`);
}

function draftWithSocial() {
  const draft = setup.createDraft();
  draft.episodeName = "Founders Unfiltered #7";
  draft.sourceMode = "upload";
  draft.speakers = [
    Object.assign(setup.createSpeaker("Host"), {
      name: "Sam Rivera",
      fileName: "sam.mp4",
      social: { website: "https://samrivera.show", twitter: "https://x.com/samrivera", instagram: "", linkedin: "" },
    }),
    Object.assign(setup.createSpeaker("Guest 1"), {
      name: "Dana Kim",
      fileName: "dana.mp4",
      social: { website: "", twitter: "", instagram: "", linkedin: "https://linkedin.com/in/danakim" },
    }),
    Object.assign(setup.createSpeaker("Guest 2"), { name: "Marco Vidal", fileName: "marco.mp4" }),
  ];
  return draft;
}

test("createReview derives brand and spelling hints from social links", () => {
  const episode = setup.summarize(draftWithSocial());
  const review = context.createReview(episode);

  assert.strictEqual(review.speakers.length, 3);
  assert.strictEqual(review.speakers[0].displayName, "Sam Rivera");
  assert.strictEqual(review.speakers[0].brand, "Samrivera");
  assert.ok(review.speakers[0].spellingHints.includes("Sam Rivera"));
  assert.ok(review.speakers[0].topics.includes("Samrivera"));
  assert.strictEqual(review.speakers[1].displayName, "Dana Kim");
  assert.ok(review.speakers[1].spellingHints.length >= 1);
});

test("updateSpeaker lets creators edit names, brands, topics, and spelling hints", () => {
  let review = context.createReview(setup.summarize(draftWithSocial()));
  review = context.updateSpeaker(review, 0, {
    displayName: "Sam R. Rivera",
    brand: "Rivera Media",
    topics: "founders, SaaS, community",
    spellingHints: "Sam River, Sam Rivira, Sam R. Rivera",
  });

  assert.strictEqual(review.speakers[0].displayName, "Sam R. Rivera");
  assert.strictEqual(review.speakers[0].brand, "Rivera Media");
  assert.deepStrictEqual(review.speakers[0].topics, ["founders", "SaaS", "community"]);
  assert.ok(review.speakers[0].spellingHints.includes("Sam Rivira"));
});

test("applyReviewToMoments fixes spellings and enriches captions, titles, and callouts", () => {
  const episode = setup.summarize(draftWithSocial());
  let review = context.createReview(episode);
  review = context.updateSpeaker(review, 0, {
    displayName: "Sam R. Rivera",
    brand: "Rivera Media",
    topics: "founders, SaaS",
    spellingHints: "Sam River, Sam Rivira",
  });
  review = context.approveReview(review);

  let board = moments.createBoard(episode);
  board = moments.addMoment(board, "caption", {
    time: "0:30",
    text: "Sam Rivira on building in public",
    speakerRole: "Host",
    speakerName: "Sam Rivera",
  });
  board = moments.addMoment(board, "title", {
    time: "1:00",
    text: "Opening segment",
    speakerRole: "Host",
    speakerName: "Sam Rivera",
  });
  board = moments.addMoment(board, "callout", {
    time: "2:00",
    text: "Key takeaway",
    speakerRole: "Host",
    speakerName: "Sam Rivera",
  });

  board = context.applyReviewToMoments(board, review);
  const caption = board.moments.find((moment) => moment.type === "caption");
  const title = board.moments.find((moment) => moment.type === "title");
  const callout = board.moments.find((moment) => moment.type === "callout");

  assert.ok(caption.text.includes("Sam R. Rivera"));
  assert.ok(!caption.text.includes("Sam Rivira"));
  assert.ok(title.text.includes("founders"));
  assert.ok(callout.text.includes("Rivera Media"));
});

test("summarizeReview rolls approved context into an export-friendly line", () => {
  let review = context.approveReview(context.createReview(setup.summarize(draftWithSocial())));
  review = context.updateSpeaker(review, 0, { topics: "founders, SaaS" });
  review = context.approveReview(review);
  const summary = context.summarizeReview(review);

  assert.strictEqual(summary.approved, true);
  assert.ok(summary.reviewLine.indexOf("Context:") === 0);
  assert.ok(summary.reviewLine.includes("Sam Rivera"));
});

test("serializeReview and deserializeReview preserve approved edits", () => {
  let review = context.createReview(setup.summarize(draftWithSocial()));
  review = context.updateSpeaker(review, 1, { brand: "Kim Consulting", approved: true });
  review = context.approveReview(review);

  const restored = context.deserializeReview(context.serializeReview(review), setup.summarize(draftWithSocial()));
  assert.strictEqual(restored.speakers[1].brand, "Kim Consulting");
  assert.strictEqual(restored.approved, true);
});

test("ACCEPTANCE: social links → approve context → moments and export reflect hints", () => {
  const draft = draftWithSocial();
  assert.strictEqual(setup.validateDraft(draft).ok, true);

  const episode = setup.summarize(draft);
  let review = context.createReview(episode);
  review = context.updateSpeaker(review, 0, {
    displayName: "Sam R. Rivera",
    brand: "Rivera Media",
    topics: "founders, startups",
    spellingHints: "Sam River, Sam Rivira",
  });
  review = context.approveReview(review);
  const contextSummary = context.summarizeReview(review);

  let board = moments.createBoard(episode);
  board = moments.addMoment(board, "caption", {
    time: "0:45",
    text: "Sam Rivira welcomes Dana Kim",
    speakerRole: "Host",
    speakerName: "Sam Rivera",
  });
  board = context.applyReviewToMoments(board, review);
  assert.ok(board.moments[0].text.includes("Sam R. Rivera"));

  const selection = style.createSelection();
  const exportCtx = {
    audioPolish: audio.summarizePolish(audio.createPolish(episode)),
    appliedStyle: style.summarizeStyle(selection, episode.speakerCount),
    templateName: "Founders Unfiltered",
    momentsSummary: moments.summarizeBoard(board),
    contextSummary: contextSummary,
  };
  const job = exportApi.createExport(episode);
  const finalSummary = exportApi.buildFinalSummary(episode, exportCtx, job);

  assert.ok(finalSummary.lines.some((line) => line.indexOf("Context:") === 0));
  assert.ok(finalSummary.lines.some((line) => line.indexOf("Visual moments:") === 0));
});

console.log(`\nsocial context: ${passed} assertions passed`);
