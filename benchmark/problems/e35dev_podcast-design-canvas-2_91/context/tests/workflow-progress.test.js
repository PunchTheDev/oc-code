"use strict";

// Workflow progress and draft resume smoke suite for Podcast Design Canvas (#89).
// Run with: `node tests/workflow-progress.test.js`.

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const library = require("../app/show-library.js");
const flow = require("../app/episode-flow.js");
const onboarding = require("../app/show-onboarding.js");

let passed = 0;
function test(name, fn) {
  fn();
  passed += 1;
  console.log(`  ok ${name}`);
}

const ui = fs.readFileSync(path.join(__dirname, "../app/episode-setup.ui.js"), "utf8");
const styles = fs.readFileSync(path.join(__dirname, "../app/styles.css"), "utf8");
const html = fs.readFileSync(path.join(__dirname, "../index.html"), "utf8");

test("parseStepLabel and stepIndicatorForLabel expose prominent workflow progress", () => {
  const parsed = flow.parseStepLabel("Step 3 of 8 · Audio polish");
  assert.strictEqual(parsed.step, 3);
  assert.strictEqual(parsed.total, 8);
  const indicator = flow.stepIndicatorForLabel("Step 3 of 8 · Audio polish");
  assert.strictEqual(indicator.countText, "Step 3 of 8");
  assert.strictEqual(indicator.labelText, "Audio polish");
  assert.ok(indicator.progress > 0.3 && indicator.progress < 0.4);
});

test("stepIndicatorForWorkspaceStage maps the active production stage to a step", () => {
  const indicator = flow.stepIndicatorForWorkspaceStage("style");
  assert.strictEqual(indicator.step, 4);
  assert.strictEqual(indicator.labelText, "Choose a style");
});

test("latestResumableDraft prefers the newest draft or in-progress episode", () => {
  const episodes = [
    { id: "ep-1", name: "Older draft", status: "draft", createdAt: 1 },
    { id: "ep-2", name: "Latest draft", status: "draft", createdAt: 3 },
    { id: "ep-3", name: "Exported", status: "exported", createdAt: 4 },
  ];
  const latest = flow.latestResumableDraft(episodes);
  assert.strictEqual(latest.id, "ep-2");
});

test("resumeDestination returns workspace when production progress was saved", () => {
  assert.strictEqual(flow.resumeDestination({ workspaceReached: true }), "workspace");
  assert.strictEqual(flow.resumeDestination({ setupComplete: true, lastView: "style" }), "style");
  assert.strictEqual(flow.resumeDestination({ setupComplete: false }), "setup");
});

test("showDetailSections promotes resume when a draft episode exists", () => {
  library._resetCounters();
  const show = library.createShow("Founders Unfiltered");
  show.episodes = [
    library.createEpisode(show.id, "Founders — Episode 1", { id: "ep-draft", status: library.EPISODE_STATUS.DRAFT }),
  ];
  const sections = onboarding.showDetailSections(show);
  assert.strictEqual(sections.primary.mode, "resume");
  assert.strictEqual(sections.primary.episodeId, "ep-draft");
  assert.ok(/Resume/i.test(sections.primary.actionLabel));
});

test("UI wires workflow indicator, draft resume, and workspace next action (#89)", () => {
  assert.ok(html.includes("workflow-step-indicator"));
  assert.ok(ui.includes("resumeEpisodeFromShow"));
  assert.ok(ui.includes("workspace-next-action"));
  assert.ok(ui.includes("setWorkspaceStep"));
  assert.ok(ui.includes("persistEpisodeSession"));
  assert.ok(styles.includes(".workflow-step-track"));
  assert.ok(styles.includes(".show-episode-card-resumable"));
});

test("ACCEPTANCE: draft episode resume lands in workspace when progress was saved", () => {
  const destination = flow.resumeDestination({
    setupComplete: true,
    workspaceReached: true,
    lastView: "workspace",
  });
  assert.strictEqual(destination, "workspace");
  const resume = flow.summarizeResumeAction({
    id: "ep-draft",
    name: "Founders — Episode 1",
    status: "draft",
  });
  assert.ok(/Founders — Episode 1/.test(resume.title));
  assert.ok(/Resume draft episode/.test(resume.actionLabel));
});

console.log(`\nworkflow progress: ${passed} assertions passed`);