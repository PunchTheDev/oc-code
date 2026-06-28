"use strict";

// Show library dashboard smoke suite for Podcast Design Canvas (#47).
// Run with: `node tests/show-library.test.js`.

const assert = require("assert");
const setup = require("../app/episode-setup.js");
const templates = require("../app/show-templates.js");
const style = require("../app/episode-style.js");
const editor = require("../app/canvas-editor.js");
const library = require("../app/show-library.js");

let passed = 0;
function test(name, fn) {
  fn();
  passed += 1;
  console.log(`  ok ${name}`);
}

function makeShow(lib, name, opts) {
  const nameCheck = library.validateShowName(lib, name);
  assert.strictEqual(nameCheck.ok, true, nameCheck.error);
  const show = library.createShow(nameCheck.name, opts);
  return { lib: library.addShow(lib, show), show };
}

function makeEpisode(lib, showId, name, opts) {
  const ep = library.createEpisode(showId, name, opts);
  return { lib: library.addEpisode(lib, showId, ep), ep };
}

// ---- shows ------------------------------------------------------------------

test("createLibrary starts with an empty shows list", () => {
  library._resetCounters();
  const lib = library.createLibrary();
  assert.deepStrictEqual(lib.shows, []);
  const summary = library.summarizeLibrary(lib);
  assert.strictEqual(summary.showCount, 0);
  assert.ok(/No shows/.test(summary.libraryLine));
});

test("addShow saves a named show and listShows returns it sorted", () => {
  library._resetCounters();
  let lib = library.createLibrary();
  lib = makeShow(lib, "Zebra Cast").lib;
  lib = makeShow(lib, "Alpha Podcast").lib;
  const shows = library.listShows(lib);
  assert.strictEqual(shows.length, 2);
  assert.strictEqual(shows[0].name, "Alpha Podcast");
  assert.strictEqual(shows[1].name, "Zebra Cast");
});

test("validateShowName rejects empty name and duplicate names", () => {
  library._resetCounters();
  let lib = library.createLibrary();
  lib = makeShow(lib, "Founders Unfiltered").lib;
  assert.strictEqual(library.validateShowName(lib, "").ok, false);
  assert.strictEqual(library.validateShowName(lib, "Founders Unfiltered").ok, false);
  assert.strictEqual(library.validateShowName(lib, "New Show").ok, true);
});

test("show carries template identity when created with templateId and presetName", () => {
  library._resetCounters();
  let lib = library.createLibrary();
  const result = makeShow(lib, "Agency Weekly", {
    templateId: "tpl-agency",
    templateName: "Agency Layout",
    presetName: "Split Stage",
  });
  const shows = library.listShows(result.lib);
  assert.strictEqual(shows[0].templateName, "Agency Layout");
  assert.strictEqual(shows[0].presetName, "Split Stage");
});

// ---- episodes ---------------------------------------------------------------

test("addEpisode attaches an episode to its show and listEpisodes returns it", () => {
  library._resetCounters();
  let lib = library.createLibrary();
  const { lib: lib1, show } = makeShow(lib, "Founders Unfiltered");
  lib = lib1;
  const { lib: lib2 } = makeEpisode(lib, show.id, "Episode #1");
  const eps = library.listEpisodes(lib2, show.id);
  assert.strictEqual(eps.length, 1);
  assert.strictEqual(eps[0].name, "Episode #1");
  assert.strictEqual(eps[0].status, library.EPISODE_STATUS.DRAFT);
});

test("updateEpisode changes status to exported and records downloadName", () => {
  library._resetCounters();
  let lib = library.createLibrary();
  const { lib: lib1, show } = makeShow(lib, "Founders Unfiltered");
  lib = lib1;
  const { lib: lib2, ep } = makeEpisode(lib, show.id, "Episode #2");
  const lib3 = library.updateEpisode(lib2, show.id, ep.id, {
    status: library.EPISODE_STATUS.EXPORTED,
    downloadName: "founders-episode-2-1080p.mp4",
    exportedAt: Date.now(),
  });
  const eps = library.listEpisodes(lib3, show.id);
  assert.strictEqual(eps[0].status, library.EPISODE_STATUS.EXPORTED);
  assert.strictEqual(eps[0].downloadName, "founders-episode-2-1080p.mp4");
  assert.strictEqual(library.episodeStatusLabel(eps[0].status), "Exported");
});

test("listShows includes latestEpisode summary", () => {
  library._resetCounters();
  let lib = library.createLibrary();
  const { lib: lib1, show } = makeShow(lib, "Founders Unfiltered");
  lib = lib1;
  lib = makeEpisode(lib, show.id, "Episode #1", { createdAt: 1000 }).lib;
  lib = makeEpisode(lib, show.id, "Episode #2", { createdAt: 2000 }).lib;
  const shows = library.listShows(lib);
  assert.strictEqual(shows[0].latestEpisode.name, "Episode #2");
});

// ---- new episode prefill ---------------------------------------------------

test("newEpisodeDraft pre-fills templateId, templateName, and presetName from the show", () => {
  library._resetCounters();
  const show = library.createShow("Agency Weekly", {
    templateId: "tpl-agency",
    templateName: "Agency Layout",
    presetName: "Studio Spotlight",
  });
  const draft = library.newEpisodeDraft(show);
  assert.strictEqual(draft.showId, show.id);
  assert.strictEqual(draft.templateId, "tpl-agency");
  assert.strictEqual(draft.templateName, "Agency Layout");
  assert.strictEqual(draft.presetName, "Studio Spotlight");
});

// ---- persistence -----------------------------------------------------------

test("serializeLibrary and deserializeLibrary round-trip shows and episodes", () => {
  library._resetCounters();
  let lib = library.createLibrary();
  lib = makeShow(lib, "Founders Unfiltered", { templateId: "tpl-1" }).lib;
  lib = makeEpisode(lib, library.listShows(lib)[0].id, "Episode #1", {
    status: library.EPISODE_STATUS.IN_PROGRESS,
  }).lib;
  const restored = library.deserializeLibrary(library.serializeLibrary(lib));
  const shows = library.listShows(restored);
  assert.strictEqual(shows.length, 1);
  assert.strictEqual(shows[0].episodeCount, 1);
  assert.strictEqual(shows[0].templateId, "tpl-1");
});

// ---- integration with show templates ---------------------------------------

test("a saved canvas template flows into show identity and new episode prefill", () => {
  library._resetCounters();
  templates._resetTemplateCounter();

  // Create a canvas template from a styled episode.
  const draft = setup.createDraft();
  draft.episodeName = "Founders Unfiltered #7";
  draft.sourceMode = "upload";
  draft.speakers = [
    Object.assign(setup.createSpeaker("Host"), { name: "Sam Rivera", fileName: "sam.mp4" }),
    Object.assign(setup.createSpeaker("Guest 1"), { name: "Dana Kim", fileName: "dana.mp4" }),
  ];
  const episode = setup.summarize(draft);
  const selection = style.createSelection();
  selection.presetId = "studio-spotlight";
  const applied = style.summarizeStyle(selection, episode.speakerCount);
  const doc = editor.createFromStyle(applied, episode, selection);
  const tpl = templates.createTemplate("Founders Format", doc, "tpl-founders");
  let store = templates.createStore();
  store = templates.saveTemplate(store, tpl);

  // Create a show using that template.
  let lib = library.createLibrary();
  lib = makeShow(lib, "Founders Unfiltered", {
    templateId: tpl.id,
    templateName: tpl.name,
    presetName: applied.presetName,
  }).lib;

  const show = library.getShow(lib, library.listShows(lib)[0].id);
  assert.strictEqual(show.templateId, "tpl-founders");
  assert.strictEqual(show.templateName, "Founders Format");

  // New episode prefill carries the show's template forward.
  const prefill = library.newEpisodeDraft(show);
  assert.strictEqual(prefill.templateId, "tpl-founders");
  assert.strictEqual(prefill.templateName, "Founders Format");
  assert.ok(prefill.presetName.length > 0);
});

// ---- ACCEPTANCE ------------------------------------------------------------

test("ACCEPTANCE: create show, add episodes with statuses, list, and start new episode from template", () => {
  library._resetCounters();

  // Create a show.
  let lib = library.createLibrary();
  const nameCheck = library.validateShowName(lib, "Weeknight Live");
  assert.strictEqual(nameCheck.ok, true);
  const show = library.createShow(nameCheck.name, {
    templateId: "tpl-wl",
    templateName: "Weeknight Layout",
    presetName: "Panel Grid",
  });
  lib = library.addShow(lib, show);

  // Add two episodes.
  const ep1 = library.createEpisode(show.id, "Episode #1 — Pilot");
  lib = library.addEpisode(lib, show.id, ep1);
  lib = library.updateEpisode(lib, show.id, ep1.id, { status: library.EPISODE_STATUS.EXPORTED, downloadName: "weeknight-ep1-1080p.mp4" });

  const ep2 = library.createEpisode(show.id, "Episode #2 — Follow-up");
  lib = library.addEpisode(lib, show.id, ep2);
  lib = library.updateEpisode(lib, show.id, ep2.id, { status: library.EPISODE_STATUS.IN_PROGRESS });

  // Verify list.
  const episodes = library.listEpisodes(lib, show.id);
  assert.strictEqual(episodes.length, 2);
  assert.ok(episodes.some(ep => ep.status === library.EPISODE_STATUS.EXPORTED));
  assert.ok(episodes.some(ep => ep.status === library.EPISODE_STATUS.IN_PROGRESS));

  // Library summary.
  const summary = library.summarizeLibrary(lib);
  assert.strictEqual(summary.showCount, 1);
  assert.strictEqual(summary.totalEpisodes, 2);
  assert.strictEqual(summary.exportedCount, 1);
  assert.ok(summary.libraryLine.includes("2 episodes"));

  // New episode prefill.
  const storedShow = library.getShow(lib, show.id);
  const prefill = library.newEpisodeDraft(storedShow);
  assert.strictEqual(prefill.showId, show.id);
  assert.strictEqual(prefill.templateId, "tpl-wl");
  assert.strictEqual(prefill.templateName, "Weeknight Layout");

  // Round-trip.
  const restored = library.deserializeLibrary(library.serializeLibrary(lib));
  assert.strictEqual(library.listShows(restored).length, 1);
  assert.strictEqual(library.listEpisodes(restored, show.id).length, 2);
});

console.log(`\nshow library: ${passed} assertions passed`);