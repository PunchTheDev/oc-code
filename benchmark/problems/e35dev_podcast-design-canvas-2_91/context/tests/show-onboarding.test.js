"use strict";

// Show onboarding order smoke suite for Podcast Design Canvas (#73).
// Run with: `node tests/show-onboarding.test.js`.

const assert = require("assert");
const library = require("../app/show-library.js");
const identity = require("../app/show-identity.js");
const onboarding = require("../app/show-onboarding.js");

let passed = 0;
function test(name, fn) {
  fn();
  passed += 1;
  console.log(`  ok ${name}`);
}

test("firstStepAfterCreateShow routes new shows to episode setup before brand work", () => {
  assert.strictEqual(onboarding.firstStepAfterCreateShow(), "episode-setup");
  assert.strictEqual(onboarding.FIRST_STEP, "episode-setup");
});

test("showDetailSections prioritizes episode import over brand kit on an empty show", () => {
  library._resetCounters();
  let lib = library.createLibrary();
  const show = library.createShow("Founders Unfiltered");
  lib = library.addShow(lib, show);
  const sections = onboarding.showDetailSections(library.getShow(lib, show.id));

  assert.strictEqual(sections.primary.id, "episode-setup");
  assert.strictEqual(sections.secondary.id, "brand-kit");
  assert.ok(/Import your recording/i.test(sections.primary.title));
  assert.ok(/optional/i.test(sections.secondary.title));
  assert.ok(/Set up later/i.test(sections.secondary.hint));
});

test("showDetailSections keeps episode setup primary when a show already has episodes", () => {
  library._resetCounters();
  let lib = library.createLibrary();
  const show = library.createShow("Agency Weekly");
  lib = library.addShow(lib, show);
  const ep = library.createEpisode(show.id, "Episode 1", { status: library.EPISODE_STATUS.DRAFT });
  lib = library.addEpisode(lib, show.id, ep);
  const stored = library.getShow(lib, show.id);
  const sections = onboarding.showDetailSections(stored);

  assert.strictEqual(sections.primary.id, "episode-setup");
  assert.strictEqual(sections.primary.actionLabel, "New episode →");
});

test("ACCEPTANCE: create-show path starts episode import with setup draft, not brand kit gate", () => {
  library._resetCounters();
  let lib = library.createLibrary();
  const show = library.createShow("Founders Unfiltered");
  lib = library.addShow(lib, show);
  const stored = library.getShow(lib, show.id);

  assert.strictEqual(onboarding.firstStepAfterCreateShow(), "episode-setup");
  const start = identity.buildEpisodeStart(stored, { templates: [] });
  assert.ok(start.setupDraft);
  assert.ok(Array.isArray(start.setupDraft.speakers));
  assert.strictEqual(stored.brandKit, null);
  assert.ok(/Episode 1/.test(start.setupDraft.episodeName));
});

console.log(`\nshow onboarding: ${passed} assertions passed`);
