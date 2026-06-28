// Static "build" check for the preview app. There is no bundler — the app is plain
// HTML/CSS/JS — so this verifies the runnable preview is shippable: required files
// exist, every script parses, and index.html wires the app together.
// Usage: `node scripts/preview-build.mjs`.
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";

const required = [
  "index.html",
  "app/styles.css",
  "app/episode-setup.js",
  "app/episode-style.js",
  "app/canvas-layers.js",
  "app/canvas-editor.js",
  "app/show-templates.js",
  "app/episode-setup.ui.js",
];

let failed = false;
function fail(message) {
  console.error(`  ✗ ${message}`);
  failed = true;
}

for (const file of required) {
  if (!existsSync(file)) {
    fail(`missing required file: ${file}`);
  }
}

// Parse-check every shipped script.
for (const file of [
  "app/episode-setup.js",
  "app/episode-style.js",
  "app/canvas-layers.js",
  "app/canvas-editor.js",
  "app/show-templates.js",
  "app/episode-setup.ui.js",
]) {
  if (!existsSync(file)) {
    continue;
  }
  const result = spawnSync("node", ["--check", file], { encoding: "utf8" });
  if (result.status !== 0) {
    fail(`syntax error in ${file}: ${(result.stderr || "").trim()}`);
  }
}

// Confirm the entry HTML actually loads the app.
if (existsSync("index.html")) {
  const html = readFileSync("index.html", "utf8");
  for (const ref of [
    "app/styles.css",
    "app/episode-setup.js",
    "app/episode-style.js",
    "app/canvas-layers.js",
    "app/canvas-editor.js",
    "app/show-templates.js",
    "app/episode-setup.ui.js",
    'id="app"',
  ]) {
    if (!html.includes(ref)) {
      fail(`index.html does not reference ${ref}`);
    }
  }
}

if (failed) {
  console.error("\npreview-build: FAILED");
  process.exit(1);
}

console.log("preview-build: OK — static preview is shippable.");
