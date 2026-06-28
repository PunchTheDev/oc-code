"use strict";

// Speaker identity defaults smoke suite for Podcast Design Canvas (#78).
// Run with: `node tests/speaker-identity-defaults.test.js`.

const assert = require("assert");
const setup = require("../app/episode-setup.js");
const library = require("../app/show-library.js");
const identity = require("../app/show-identity.js");

let passed = 0;
function test(name, fn) {
  fn();
  passed += 1;
  console.log(`  ok ${name}`);
}

function showWithSpeakerDefaults(defaultSpeakers) {
  return library.createShow("Founders Unfiltered", {
    defaultSourceMode: "upload",
    defaultSpeakers: defaultSpeakers,
  });
}

test("isShowContextLabel detects show and episode titles used as speaker names", () => {
  const show = showWithSpeakerDefaults([]);
  const draft = { episodeName: "Founders Unfiltered — Episode 1" };
  assert.strictEqual(identity.isShowContextLabel("Founders Unfiltered", show, draft), true);
  assert.strictEqual(identity.isShowContextLabel("Founders Unfiltered — Episode 1", show, draft), true);
  assert.strictEqual(identity.isShowContextLabel("Sam Rivera", show, draft), false);
});

test("isShowContextLabel detects episode title leakage like Test Episode", () => {
  library._resetCounters();
  const show = library.createShow("Test Episode", { defaultSpeakers: [] });
  const draft = { episodeName: "Test Episode — Episode 1" };
  assert.strictEqual(identity.isShowContextLabel("Test Episode", show, draft), true);
  assert.strictEqual(identity.isShowContextLabel("Test Episode — Episode 1", show, draft), true);
});

test("buildSetupDraft keeps role buckets and social links without copying speaker names", () => {
  library._resetCounters();
  const show = showWithSpeakerDefaults([
    { role: "Host", name: "Founders Unfiltered", social: { twitter: "https://x.com/host" } },
    { role: "Guest 1", name: "Founders Unfiltered — Episode 1", social: { linkedin: "https://linkedin.com/in/guest" } },
  ]);
  const draft = identity.buildSetupDraft(show);
  assert.strictEqual(draft.speakers[0].name, "");
  assert.strictEqual(draft.speakers[1].name, "");
  assert.strictEqual(draft.speakers[0].role, "Host");
  assert.strictEqual(draft.speakers[1].role, "Guest 1");
  assert.strictEqual(draft.speakers[0].social.twitter, "https://x.com/host");
  assert.strictEqual(draft.speakers[1].social.linkedin, "https://linkedin.com/in/guest");
});

test("buildSetupDraft strips show or episode titles from saved track labels", () => {
  library._resetCounters();
  const show = showWithSpeakerDefaults([
    { role: "Host", name: "Sam Rivera", trackLabel: "Founders Unfiltered — Episode 1" },
    { role: "Guest 1", name: "Dana Kim", trackLabel: "Track 2" },
  ]);
  const draft = identity.buildSetupDraft(show);
  assert.strictEqual(draft.speakers[0].name, "Sam Rivera");
  assert.strictEqual(draft.speakers[0].trackLabel, "");
  assert.strictEqual(draft.speakers[1].trackLabel, "Track 2");
});

test("buildSetupDraft without saved speakers keeps blank Host and Guest defaults", () => {
  library._resetCounters();
  const show = showWithSpeakerDefaults([]);
  const draft = identity.buildSetupDraft(show);
  assert.strictEqual(draft.episodeName, "Founders Unfiltered — Episode 1");
  assert.strictEqual(draft.speakers.length, 3);
  assert.ok(draft.speakers.every((speaker) => speaker.name === ""));
  assert.deepStrictEqual(
    draft.speakers.map((speaker) => speaker.role),
    ["Host", "Guest 1", "Guest 2"],
  );
});

test("sanitizeSetupDraft clears episode title leakage after removing a speaker source", () => {
  library._resetCounters();
  const show = library.createShow("Test Episode", { defaultSpeakers: [] });
  let draft = identity.buildSetupDraft(show);
  draft.speakers[0].name = "Test Episode";
  draft.speakers[0].trackLabel = "Test Episode";
  draft.speakers.splice(1, 1);
  draft = identity.sanitizeSetupDraft(draft, show);
  assert.strictEqual(draft.speakers[0].name, "");
  assert.strictEqual(draft.speakers[0].trackLabel, "");
  assert.strictEqual(draft.speakers[0].role, "Host");
});

test("ACCEPTANCE: episode import from show saves draft with blank speaker names and working roles", () => {
  library._resetCounters();
  let lib = library.createLibrary();
  const show = showWithSpeakerDefaults([
    { role: "Host", name: "Founders Unfiltered", social: { website: "https://founders.fm" } },
    { role: "Guest 1", name: "Founders Unfiltered — Episode 1" },
  ]);
  lib = library.addShow(lib, show);
  const stored = library.getShow(lib, show.id);
  const start = identity.buildEpisodeStart(stored, { templates: [] });
  const episode = library.createEpisode(stored.id, start.setupDraft.episodeName, {
    status: library.EPISODE_STATUS.DRAFT,
    speakerRoles: start.setupDraft.speakers.map((speaker) => speaker.role),
  });
  lib = library.addEpisode(lib, stored.id, episode);

  assert.ok(start.setupDraft.speakers.every((speaker) => !speaker.name));
  assert.strictEqual(start.setupDraft.speakers[0].role, "Host");
  assert.strictEqual(start.setupDraft.speakers[0].social.website, "https://founders.fm");
  assert.strictEqual(library.listEpisodes(lib, stored.id).length, 1);
  const draft = start.setupDraft;
  draft.sourceMode = "riverside";
  draft.riversideLink = "https://riverside.fm/studio/founders";
  assert.strictEqual(setup.validateDraft(draft).ok, false);
  draft.speakers.forEach((speaker, index) => {
    speaker.name = `Speaker ${index + 1}`;
  });
  assert.strictEqual(setup.validateDraft(draft).ok, true);
});

console.log(`\nspeaker identity defaults: ${passed} assertions passed`);