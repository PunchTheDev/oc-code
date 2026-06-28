"use strict";

// Setup-flow smoke suite for Podcast Design Canvas (#1).
// Runs the real episode-setup rules the screen uses, so the documented acceptance flow
// (title → source mode → 3 sources → role buckets → social links → accurate summary)
// is guarded automatically. Run with: `node tests/episode-setup.test.js`.

const assert = require("assert");
const setup = require("../app/episode-setup.js");

let passed = 0;
function test(name, fn) {
  fn();
  passed += 1;
  console.log(`  ok ${name}`);
}

// Build a fully valid draft the way a creator would complete the screen.
function completeRiversideDraft() {
  const draft = setup.createDraft();
  draft.episodeName = "Episode 12 — Building in Public";
  draft.sourceMode = "riverside";
  draft.riversideLink = "https://riverside.fm/studio/episode-12";
  draft.speakers[0].name = "Avery Stone";
  draft.speakers[0].social.website = "https://averystone.com";
  draft.speakers[0].social.twitter = "https://x.com/averystone";
  draft.speakers[1].name = "Jordan Lee";
  draft.speakers[1].social.linkedin = "https://linkedin.com/in/jordanlee";
  draft.speakers[2].name = "Priya Raman";
  return draft;
}

function completeUploadDraft() {
  const draft = setup.createDraft();
  draft.episodeName = "Episode 12 — Building in Public";
  draft.sourceMode = "upload";
  draft.speakers[0].name = "Avery Stone";
  draft.speakers[0].fileName = "avery-host.mp4";
  draft.speakers[1].name = "Jordan Lee";
  draft.speakers[1].fileName = "jordan-guest1.mp4";
  draft.speakers[2].name = "Priya Raman";
  draft.speakers[2].fileName = "priya-guest2.mp4";
  return draft;
}

test("a fresh draft seeds Host / Guest 1 / Guest 2 defaults", () => {
  const draft = setup.createDraft();
  assert.strictEqual(draft.speakers.length, 3);
  assert.deepStrictEqual(draft.speakers.map((s) => s.role), ["Host", "Guest 1", "Guest 2"]);
  assert.strictEqual(draft.sourceMode, "riverside");
});

test("an empty draft is invalid and asks for an episode name", () => {
  const result = setup.validateDraft(setup.createDraft());
  assert.strictEqual(result.ok, false);
  assert.ok(result.errors.episodeName, "expected an episode name error");
  assert.ok(/episode name/i.test(result.errors.episodeName));
});

test("riverside mode requires a recording link", () => {
  const draft = setup.createDraft();
  draft.episodeName = "Test";
  draft.speakers.forEach((s, i) => (s.name = `Speaker ${i + 1}`));
  const result = setup.validateDraft(draft);
  assert.ok(result.errors.riversideLink, "expected a missing-link error");
});

test("riverside mode rejects a link that is not a URL", () => {
  const draft = setup.createDraft();
  draft.episodeName = "Test";
  draft.riversideLink = "my recording";
  draft.speakers.forEach((s, i) => (s.name = `Speaker ${i + 1}`));
  const result = setup.validateDraft(draft);
  assert.ok(/doesn't look right/i.test(result.errors.riversideLink || ""));
});

test("upload mode requires a video file for each speaker", () => {
  const draft = completeUploadDraft();
  draft.speakers[1].fileName = "";
  const result = setup.validateDraft(draft);
  assert.ok(result.errors["speaker:1:source"], "expected a missing-file error on speaker 1");
  assert.ok(/video file/i.test(result.errors["speaker:1:source"]));
});

test("every speaker needs a name", () => {
  const draft = completeRiversideDraft();
  draft.speakers[2].name = "";
  const result = setup.validateDraft(draft);
  assert.ok(result.errors["speaker:2:name"], "expected a missing-name error on speaker 2");
});

test("two speakers cannot share a role bucket", () => {
  const draft = completeRiversideDraft();
  draft.speakers[1].role = "Host"; // collides with speaker 0
  const result = setup.validateDraft(draft);
  assert.ok(/different role/i.test(result.errors["speaker:1:role"] || ""));
});

test("a malformed social link is caught with a creator-facing message", () => {
  const draft = completeRiversideDraft();
  draft.speakers[0].social.website = "not-a-link";
  const result = setup.validateDraft(draft);
  assert.ok(result.errors["speaker:0:social:website"], "expected a social link error");
  assert.ok(/full URL/i.test(result.errors["speaker:0:social:website"]));
});

test("a fully completed riverside setup is valid", () => {
  const result = setup.validateDraft(completeRiversideDraft());
  assert.strictEqual(result.ok, true, JSON.stringify(result.errors));
  assert.strictEqual(result.messages.length, 0);
});

test("a fully completed upload setup is valid", () => {
  const result = setup.validateDraft(completeUploadDraft());
  assert.strictEqual(result.ok, true, JSON.stringify(result.errors));
});

test("the workspace summary reflects exactly what was entered", () => {
  const draft = completeRiversideDraft();
  const summary = setup.summarize(draft);
  assert.strictEqual(summary.episodeName, "Episode 12 — Building in Public");
  assert.strictEqual(summary.sourceModeLabel, "Riverside link");
  assert.strictEqual(summary.riversideLink, "https://riverside.fm/studio/episode-12");
  assert.strictEqual(summary.speakerCount, 3);
  assert.deepStrictEqual(summary.roles, ["Host", "Guest 1", "Guest 2"]);
  assert.strictEqual(summary.socialLinkCount, 3); // 2 on Avery + 1 on Jordan
  assert.strictEqual(summary.speakers[0].name, "Avery Stone");
  assert.strictEqual(summary.speakers[0].sourceLabel, "Riverside recording");
  assert.deepStrictEqual(
    summary.speakers[0].social.map((s) => s.label),
    ["Website", "X"],
  );
});

test("upload summary shows the chosen file name per speaker", () => {
  const summary = setup.summarize(completeUploadDraft());
  assert.strictEqual(summary.sourceModeLabel, "Uploaded speaker files");
  assert.strictEqual(summary.speakers[1].sourceLabel, "jordan-guest1.mp4");
  assert.strictEqual(summary.riversideLink, ""); // link not surfaced in upload mode
});

// End-to-end acceptance walkthrough: the documented runnable check for issue #1.
test("ACCEPTANCE: complete a new episode setup with 3 sources end to end", () => {
  const draft = setup.createDraft();
  // 1. Name the episode.
  draft.episodeName = "Founders Unfiltered #7";
  // 2. Choose a source mode.
  draft.sourceMode = "upload";
  // 3. Add at least three speaker sources, assigned to Host / Guest 1 / Guest 2.
  const people = [
    { name: "Sam Rivera", role: "Host", fileName: "sam.mp4" },
    { name: "Dana Kim", role: "Guest 1", fileName: "dana.mp4" },
    { name: "Marco Vidal", role: "Guest 2", fileName: "marco.mp4" },
  ];
  draft.speakers = people.map((p) => {
    const speaker = setup.createSpeaker(p.role);
    speaker.name = p.name;
    speaker.fileName = p.fileName;
    return speaker;
  });
  // 4. Add a social link for one speaker.
  draft.speakers[0].social.website = "https://samrivera.show";

  // Validation passes — the creator can continue.
  const result = setup.validateDraft(draft);
  assert.strictEqual(result.ok, true, JSON.stringify(result.errors));

  // The workspace screen shows everything accurately.
  const summary = setup.summarize(draft);
  assert.strictEqual(summary.speakerCount, 3);
  assert.deepStrictEqual(summary.roles, ["Host", "Guest 1", "Guest 2"]);
  assert.deepStrictEqual(
    summary.speakers.map((s) => s.sourceLabel),
    ["sam.mp4", "dana.mp4", "marco.mp4"],
  );
  assert.strictEqual(summary.socialLinkCount, 1);
});

console.log(`\nepisode setup: ${passed} assertions passed`);