// Zero-dependency smoke-test runner. Discovers *.test.js files and runs each in its
// own node process, mirroring the acceptance manifest in .builderloops/verify.json.
// Usage: `node scripts/run-tests.mjs [dir ...]` (defaults to the tests/ directory).
import { spawnSync } from "node:child_process";
import { readdirSync } from "node:fs";
import { join } from "node:path";

const dirs = process.argv.slice(2);
if (dirs.length === 0) {
  dirs.push("tests");
}

const testFiles = dirs.flatMap((dir) =>
  readdirSync(dir)
    .filter((file) => file.endsWith(".test.js"))
    .sort()
    .map((file) => join(dir, file)),
);

if (testFiles.length === 0) {
  console.error("No test files found.");
  process.exit(1);
}

for (const file of testFiles) {
  console.log(`\n> node ${file}`);
  const result = spawnSync("node", [file], { stdio: "inherit" });
  if (result.error) {
    console.error(result.error.message);
    process.exit(1);
  }
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

console.log(`\n${testFiles.length} test file(s) passed.`);