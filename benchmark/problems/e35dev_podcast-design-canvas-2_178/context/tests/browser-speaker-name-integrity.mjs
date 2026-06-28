// Browser-runtime acceptance for issue #172.
// Loads the real browser bundle in headless Chrome and checks that social context never
// corrupts a confirmed setup speaker name.
// Run: node tests/browser-speaker-name-integrity.mjs
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { spawnSync } from "node:child_process";

const root = fileURLToPath(new URL("..", import.meta.url));
const chromeCandidates = [
  process.env.CHROME_BIN,
  "/usr/bin/google-chrome",
  "/usr/bin/chromium",
  "/usr/bin/chromium-browser",
].filter(Boolean);

function scriptTagsFromIndex() {
  const html = readFileSync(join(root, "index.html"), "utf8");
  const scripts = [];
  const pattern = /<script src="([^"]+)"><\/script>/g;
  let match = pattern.exec(html);
  while (match) {
    scripts.push(`<script src="${pathToFileURL(join(root, match[1])).href}"></script>`);
    match = pattern.exec(html);
  }
  return scripts.join("\n");
}

function findChrome() {
  for (const candidate of chromeCandidates) {
    const result = spawnSync(candidate, ["--version"], { encoding: "utf8" });
    if (result.status === 0) {
      return candidate;
    }
  }
  return "";
}

function probeScript() {
  return `
    (function () {
      const checks = [];
      function log(ok, message) {
        checks.push({ ok: Boolean(ok), message });
      }
      function noCorruption(value) {
        return !/Riveraa/.test(typeof value === "string" ? value : JSON.stringify(value));
      }
      try {
        localStorage.clear();
        const ES = window.PdcEpisodeSetup;
        const SC = window.PdcSocialContext;
        const STY = window.PdcEpisodeStyle;
        const AP = window.PdcAudioPolish;
        const CE = window.PdcCanvasEditor;
        const VM = window.PdcVisualMoments;
        const TC = window.PdcTranscriptCorrection;
        const TM = window.PdcShowTemplates;
        const PP = window.PdcPublishPackage;
        const EX = window.PdcEpisodeExport;

        const draft = ES.createDraft();
        draft.episodeName = "Founders Unfiltered #7";
        draft.sourceMode = "upload";
        draft.speakers = [
          Object.assign(ES.createSpeaker("Host"), {
            name: "Sam Rivera",
            fileName: "sam.mp4",
            social: {
              website: "https://samrivera.show",
              twitter: "https://x.com/samrivera",
              instagram: "",
              linkedin: "",
            },
          }),
          Object.assign(ES.createSpeaker("Guest 1"), {
            name: "Dana Kim",
            fileName: "dana.mp4",
            social: {
              website: "",
              twitter: "",
              instagram: "",
              linkedin: "https://linkedin.com/in/danakim",
            },
          }),
        ];

        const episode = ES.summarize(draft);
        let contextReview = SC.createReview(episode);
        const riskyHintPresent = contextReview.speakers[0].spellingHints.indexOf("Sam River") >= 0;
        contextReview = SC.updateSpeaker(contextReview, 0, {
          spellingHints: contextReview.speakers[0].spellingHints.concat("Sam Rivira"),
        });
        contextReview = SC.approveReview(contextReview);

        let board = VM.createBoard(episode);
        board = VM.addMoment(board, "caption", {
          time: "0:20",
          text: "Welcome Sam Rivera",
          speakerRole: "Host",
          speakerName: "Sam Rivera",
        });
        board = VM.addMoment(board, "caption", {
          time: "0:40",
          text: "Sam Rivira opens the show",
          speakerRole: "Host",
          speakerName: "Sam Rivera",
        });
        board = SC.applyReviewToMoments(board, contextReview);

        const selection = STY.createSelection();
        const appliedStyle = STY.summarizeStyle(selection, episode.speakerCount);
        let canvasDoc = CE.createFromStyle(appliedStyle, episode, selection);
        canvasDoc = CE.updateElement(canvasDoc, "titleText", "Sam Rivera on building in public");
        canvasDoc = CE.updateElement(canvasDoc, "captionText", "Welcome Sam Rivera");
        canvasDoc = SC.applyReviewToCanvas(canvasDoc, contextReview);

        let correctionReview = TC.createCorrectionReview(episode, {
          contextReview,
          momentsBoard: board,
        });
        correctionReview = TC.approveCorrection(correctionReview);
        let publishPackage = PP.createPackage(episode, {
          appliedStyle,
          momentsBoard: board,
        });
        const applied = TC.applyCorrectionReview(correctionReview, {
          momentsBoard: board,
          canvasDoc,
          publishPackage,
          speakers: draft.speakers,
        });
        board = applied.momentsBoard;
        canvasDoc = applied.canvasDoc;
        publishPackage = applied.publishPackage;

        let templateStore = TM.createStore();
        templateStore = TM.saveTemplate(
          templateStore,
          TM.createTemplate("Founders Sam Layout", canvasDoc, "tpl-browser-sam"),
        );
        localStorage.setItem("pdc-show-templates", TM.serializeStore(templateStore));
        const savedTemplate = TM.getTemplate(templateStore, "tpl-browser-sam");
        const canvasFromTemplate = TM.applyTemplateForEpisode(
          savedTemplate,
          episode,
          TM.styleSelectionFromCanvas(savedTemplate.canvas),
        );

        const exportSummary = EX.buildFinalSummary(episode, {
          audioPolish: AP.summarizePolish(AP.createPolish(episode)),
          appliedStyle,
          templateName: savedTemplate.name,
          momentsSummary: VM.summarizeBoard(board),
          contextSummary: SC.summarizeReview(contextReview),
          correctionSummary: TC.summarizeCorrection(correctionReview),
          publishPackageSummary: PP.summarizePackage(publishPackage),
        }, EX.createExport(episode, {
          templateId: savedTemplate.id,
          templateName: savedTemplate.name,
        }));

        const allOutputs = {
          episode,
          contextReview,
          board,
          correctionReview,
          canvasDoc,
          savedTemplate,
          canvasFromTemplate,
          publishPackage,
          exportSummary,
        };

        log(episode.speakers[0].name === "Sam Rivera", "Setup summary keeps Sam Rivera exact");
        log(riskyHintPresent, "Social context generated the risky Sam River hint");
        log(SC.applyHintsToText("Thanks Sam Rivera", contextReview, "Host", "Sam Rivera") === "Thanks Sam Rivera", "Already-correct text stays exact");
        log(SC.applyHintsToText("Thanks Sam River", contextReview, "Host", "Sam Rivera") === "Thanks Sam Rivera", "Standalone shortened hint still normalizes");
        log(/Sam Rivera/.test(board.moments.map((moment) => moment.text).join("\\n")) && !/Sam Rivira/.test(JSON.stringify(board)), "Captions correct genuine misspellings");
        log(canvasDoc.titleText === "Sam Rivera on building in public", "Canvas title keeps Sam Rivera exact");
        log(canvasDoc.captionText === "Welcome Sam Rivera", "Canvas caption keeps Sam Rivera exact");
        log(canvasDoc.speakerFrames[0].name === "Sam Rivera", "Canvas speaker frame keeps Sam Rivera exact");
        log(canvasFromTemplate.speakerFrames[0].name === "Sam Rivera", "Saved template reapplies Sam Rivera exact");
        log(/Sam Rivera/.test(publishPackage.description), "Publish description includes Sam Rivera");
        log(/Sam Rivera/.test(publishPackage.speakerCredits.map((credit) => credit.creditLine).join("\\n")), "Publish credits include Sam Rivera");
        log(/Show template: Founders Sam Layout/.test(exportSummary.lines.join("\\n")), "Export summary includes the saved template");
        log(/Sam Rivera/.test(exportSummary.lines.join("\\n")), "Export metadata includes Sam Rivera");
        log(noCorruption(allOutputs), "No browser product output contains Riveraa");
      } catch (err) {
        checks.push({ ok: false, message: err && err.stack ? err.stack : String(err) });
      }
      const result = {
        ok: checks.every((check) => check.ok),
        checks,
      };
      const pre = document.createElement("pre");
      pre.id = "probe-result";
      pre.textContent = "PDC_PROBE_RESULT:" + JSON.stringify(result) + ":PDC_PROBE_RESULT_END";
      document.body.appendChild(pre);
    }());
  `;
}

const chrome = findChrome();
if (!chrome) {
  console.error("browser speaker name integrity: no Chrome binary found.");
  process.exit(1);
}

const tempDir = mkdtempSync(join(tmpdir(), "pdc-speaker-name-"));
const probePath = join(tempDir, "probe.html");
writeFileSync(
  probePath,
  `<!doctype html>
  <html lang="en">
    <head><meta charset="utf-8"><title>Speaker name integrity probe</title></head>
    <body>
      <div id="page-intro"></div>
      <div id="app"></div>
      ${scriptTagsFromIndex()}
      <script>${probeScript()}</script>
    </body>
  </html>`,
);

const result = spawnSync(chrome, [
  "--headless=new",
  "--disable-gpu",
  "--no-sandbox",
  "--allow-file-access-from-files",
  "--dump-dom",
  pathToFileURL(probePath).href,
], {
  encoding: "utf8",
  maxBuffer: 1024 * 1024 * 8,
});
rmSync(tempDir, { recursive: true, force: true });

if (result.status !== 0) {
  console.error(result.stderr || result.stdout);
  process.exit(result.status || 1);
}

const matches = Array.from(result.stdout.matchAll(/PDC_PROBE_RESULT:(.*?):PDC_PROBE_RESULT_END/gs));
const match = matches[matches.length - 1];
if (!match) {
  console.error("browser speaker name integrity: probe result missing.");
  console.error(result.stdout.slice(-2000));
  process.exit(1);
}

const parsed = JSON.parse(match[1]);
parsed.checks.forEach((check) => {
  console.log(`${check.ok ? "  ok" : " FAIL"} ${check.message}`);
});
if (!parsed.ok) {
  process.exit(1);
}
console.log("\nbrowser speaker name integrity: browser-runtime acceptance passed.");