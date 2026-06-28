"use strict";

// Visual moments editor smoke suite for Podcast Design Canvas (#19).
// Guards the documented acceptance: a speaker-aware transcript-style timeline; adding at
// least four moment types (caption, title, b-roll, callout); editing timing/text/visibility;
// previewing a moment's effect; and persisting moments across navigation (serialize round
// trip). Run with: `node tests/visual-moments.test.js`.

const assert = require("assert");
const setup = require("../app/episode-setup.js");
const moments = require("../app/visual-moments.js");

let passed = 0;
function test(name, fn) {
  fn();
  passed += 1;
  console.log(`  ok ${name}`);
}

function completeEpisode() {
  const draft = setup.createDraft();
  draft.episodeName = "Founders Unfiltered #7";
  draft.sourceMode = "upload";
  draft.speakers = [
    Object.assign(setup.createSpeaker("Host"), { name: "Sam Rivera", fileName: "sam.mp4" }),
    Object.assign(setup.createSpeaker("Guest 1"), { name: "Dana Kim", fileName: "dana.mp4" }),
  ];
  return setup.summarize(draft);
}

test("offers at least four moment types incl. caption, title, b-roll, callout", () => {
  const ids = moments.MOMENT_TYPES.map((type) => type.id);
  ["caption", "title", "broll", "callout"].forEach((id) => {
    assert.ok(ids.indexOf(id) >= 0, `${id} moment type exists`);
  });
  assert.ok(moments.MOMENT_TYPES.length >= 4, "at least four moment types");
  moments.MOMENT_TYPES.forEach((type) => {
    assert.ok(type.label && type.treatment, `${type.id} is described for creators`);
  });
});

test("the timeline is a speaker-aware transcript scaffold built from real speakers", () => {
  const board = moments.createBoard(completeEpisode());
  assert.ok(board.transcript.length >= 4, "has a full-episode scaffold");
  // Segments cycle the assigned speakers and carry timeline timestamps.
  assert.strictEqual(board.transcript[0].speakerRole, "Host");
  assert.strictEqual(board.transcript[1].speakerRole, "Guest 1");
  assert.strictEqual(board.transcript[2].speakerRole, "Host");
  assert.strictEqual(board.transcript[0].time, "0:00");
  assert.strictEqual(board.transcript[1].time, "1:30");
});

test("time parsing accepts M:SS, raw seconds, and clamps junk to 0:00", () => {
  assert.strictEqual(moments.normalizeTime("1:30"), "1:30");
  assert.strictEqual(moments.normalizeTime("90"), "1:30");
  assert.strictEqual(moments.normalizeTime("  2:05 "), "2:05");
  assert.strictEqual(moments.normalizeTime("nonsense"), "0:00");
  assert.strictEqual(moments.normalizeTime(""), "0:00");
});

test("adding moments places them in timeline order with stable ids", () => {
  let board = moments.createBoard(completeEpisode());
  board = moments.addMoment(board, "callout", { time: "3:00", text: "Big insight" });
  board = moments.addMoment(board, "caption", { time: "0:30", text: "Welcome back" });
  board = moments.addMoment(board, "title", { time: "1:30" });

  const list = moments.listMoments(board);
  assert.deepStrictEqual(list.map((m) => m.time), ["0:30", "1:30", "3:00"], "sorted by time");
  assert.deepStrictEqual(list.map((m) => m.type), ["caption", "title", "callout"]);
  assert.strictEqual(new Set(list.map((m) => m.id)).size, 3, "ids are unique");
  // A type's default text fills in when the creator does not type their own.
  assert.strictEqual(moments.getMoment(board, list[1].id).text, "Section title");
});

test("editing a moment changes its timing, text, speaker, and visibility", () => {
  let board = moments.createBoard(completeEpisode());
  board = moments.addMoment(board, "broll", { time: "1:00", text: "City skyline" });
  const id = moments.listMoments(board)[0].id;

  board = moments.updateMoment(board, id, { text: "Studio b-roll", time: "2:15", speakerRole: "Host", speakerName: "Sam Rivera" });
  const edited = moments.getMoment(board, id);
  assert.strictEqual(edited.text, "Studio b-roll");
  assert.strictEqual(edited.time, "2:15");
  assert.strictEqual(edited.speakerRole, "Host");

  board = moments.toggleMoment(board, id);
  assert.strictEqual(moments.getMoment(board, id).visible, false);
});

test("removing a moment drops it from the board", () => {
  let board = moments.createBoard(completeEpisode());
  board = moments.addMoment(board, "caption", {});
  board = moments.addMoment(board, "title", {});
  const first = moments.listMoments(board)[0].id;
  board = moments.removeMoment(board, first);
  assert.strictEqual(moments.listMoments(board).length, 1);
  assert.strictEqual(moments.getMoment(board, first), null);
});

test("previewMoment describes how the moment changes the episode look", () => {
  let board = moments.createBoard(completeEpisode());
  board = moments.addMoment(board, "caption", { time: "1:30", text: "Welcome", speakerRole: "Host", speakerName: "Sam Rivera" });
  const id = moments.listMoments(board)[0].id;

  const preview = moments.previewMoment(board, id);
  assert.strictEqual(preview.treatment, "Lower-third caption");
  assert.strictEqual(preview.onScreen, true);
  assert.ok(preview.effect.indexOf("Lower-third caption") === 0);
  assert.ok(preview.effect.indexOf("1:30") >= 0);

  board = moments.toggleMoment(board, id);
  assert.ok(moments.previewMoment(board, id).effect.indexOf("hidden") >= 0);
});

test("summarizeBoard rolls moments up for the review/export path", () => {
  let board = moments.createBoard(completeEpisode());
  board = moments.addMoment(board, "caption", {});
  board = moments.addMoment(board, "caption", {});
  board = moments.addMoment(board, "callout", {});
  board = moments.toggleMoment(board, moments.listMoments(board)[0].id);

  const summary = moments.summarizeBoard(board);
  assert.strictEqual(summary.total, 3);
  assert.strictEqual(summary.visibleCount, 2);
  assert.strictEqual(summary.counts.caption, 2);
  assert.ok(summary.reviewLine.indexOf("Caption: 2") >= 0);
});

test("moments persist across a serialize/deserialize round trip (navigate away and back)", () => {
  const episode = completeEpisode();
  let board = moments.createBoard(episode);
  board = moments.addMoment(board, "title", { time: "0:45", text: "Chapter one" });
  board = moments.addMoment(board, "broll", { time: "2:00", text: "Office tour" });

  const restored = moments.deserializeBoard(moments.serializeBoard(board), episode);
  assert.strictEqual(moments.listMoments(restored).length, 2);
  assert.deepStrictEqual(moments.listMoments(restored).map((m) => m.text), ["Chapter one", "Office tour"]);
  // Adding after a reload keeps ids unique.
  const after = moments.addMoment(restored, "caption", {});
  const ids = moments.listMoments(after).map((m) => m.id);
  assert.strictEqual(new Set(ids).size, ids.length, "no id collisions after reload");
});

// End-to-end: a completed episode flows into the moments editor; the creator builds the
// four headline moment types, edits and previews one, and the board survives a round trip —
// the runnable check for issue #19.
test("ACCEPTANCE: episode → build caption/title/b-roll/callout → edit + preview → persist", () => {
  const episode = completeEpisode();
  let board = moments.createBoard(episode);

  board = moments.addMoment(board, "caption", { time: "0:20", text: "Welcome to the show" });
  board = moments.addMoment(board, "title", { time: "1:00", text: "Building in public" });
  board = moments.addMoment(board, "broll", { time: "2:30", text: "Skyline timelapse" });
  board = moments.addMoment(board, "callout", { time: "4:00", text: "Key takeaway" });
  assert.strictEqual(moments.listMoments(board).length, 4);

  const titleId = moments.listMoments(board).find((m) => m.type === "title").id;
  board = moments.updateMoment(board, titleId, { text: "Building in Public — Part 2", time: "1:15" });
  const preview = moments.previewMoment(board, titleId);
  assert.strictEqual(preview.treatment, "Full-width title card");
  assert.ok(preview.effect.indexOf("1:15") >= 0);

  const restored = moments.deserializeBoard(moments.serializeBoard(board), episode);
  assert.strictEqual(moments.listMoments(restored).length, 4);
  assert.strictEqual(moments.getMoment(restored, titleId).text, "Building in Public — Part 2");
  assert.strictEqual(moments.summarizeBoard(restored).counts.callout, 1);
});

console.log(`\nvisual moments: ${passed} assertions passed`);