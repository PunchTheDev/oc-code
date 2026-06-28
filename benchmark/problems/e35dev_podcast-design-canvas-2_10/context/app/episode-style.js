"use strict";

// Preset visual styles + preview model for Podcast Design Canvas (#3).
//
// This is the single source of truth for the preset-first look step that follows episode
// setup: a small set of clearly different show styles, adjustable layout and pacing, and
// a preview built from the creator's actual assigned Host/Guest speaker buckets. DOM-free
// on purpose, so the same rules drive the screen and the tests. No build, no dependencies.
(function (global) {
  // Distinct show identities. Each preset deliberately differs in arrangement, palette,
  // and caption treatment so shows feel different rather than sharing one house look.
  const STYLE_PRESETS = [
    {
      id: "studio-spotlight",
      name: "Studio Spotlight",
      tagline: "Active speaker front and center, the rest in a filmstrip.",
      defaultLayout: "spotlight",
      background: "#10131f",
      surface: "#1b2133",
      accent: "#ffb347",
      textColor: "#f6f7fb",
      captionStyle: "Bold lower-third",
    },
    {
      id: "split-stage",
      name: "Split Stage",
      tagline: "Equal side-by-side frames for an even conversation.",
      defaultLayout: "split",
      background: "#f4f1ea",
      surface: "#ffffff",
      accent: "#e0563b",
      textColor: "#23201c",
      captionStyle: "Clean caption bar",
    },
    {
      id: "panel-grid",
      name: "Panel Grid",
      tagline: "A balanced grid that keeps every guest on screen.",
      defaultLayout: "grid",
      background: "#0f1a2b",
      surface: "#16263d",
      accent: "#4dd0e1",
      textColor: "#eaf6fb",
      captionStyle: "Minimal name tag",
    },
    {
      id: "bold-broadcast",
      name: "Bold Broadcast",
      tagline: "High-contrast frames with big animated captions.",
      defaultLayout: "spotlight",
      background: "#1a0f2b",
      surface: "#2a1745",
      accent: "#ff5d8f",
      textColor: "#f7eefc",
      captionStyle: "Big animated captions",
    },
  ];

  const LAYOUTS = [
    { id: "auto", label: "Auto (match speakers)" },
    { id: "spotlight", label: "Spotlight" },
    { id: "split", label: "Side by side" },
    { id: "grid", label: "Grid" },
  ];

  const PACING = [
    { id: "relaxed", label: "Relaxed", note: "Longer holds and fewer cuts — calm and conversational." },
    { id: "balanced", label: "Balanced", note: "A natural rhythm that cuts on speaker changes." },
    { id: "punchy", label: "Punchy", note: "Tighter cuts and quicker reframes for more energy." },
  ];

  function defaultPreset() {
    return STYLE_PRESETS[0];
  }

  function getPreset(id) {
    return STYLE_PRESETS.find((preset) => preset.id === id) || defaultPreset();
  }

  function getLayout(id) {
    return LAYOUTS.find((layout) => layout.id === id) || LAYOUTS[0];
  }

  function getPacing(id) {
    return PACING.find((pacing) => pacing.id === id) || PACING[1];
  }

  function createSelection() {
    return { presetId: STYLE_PRESETS[0].id, layout: "auto", pacing: "balanced" };
  }

  // Resolve "auto" into a concrete arrangement from the speaker count: one → spotlight,
  // two → side by side, three or more → grid. This is the preset-first promise — a good
  // default appears without the creator touching a blank canvas.
  function resolveLayout(selection, speakerCount) {
    const chosen = selection && selection.layout;
    if (chosen && chosen !== "auto") {
      return chosen;
    }
    const count = typeof speakerCount === "number" ? speakerCount : 0;
    if (count <= 1) {
      return "spotlight";
    }
    if (count === 2) {
      return "split";
    }
    return "grid";
  }

  // Build preview frames from the real assigned speaker buckets. In spotlight layouts the
  // Host (or the first speaker, if none is a Host) is flagged active so it can be featured.
  // Frames are derived from the setup — never invented — so the preview is honest.
  function buildPreviewFrames(speakers, selection, speakerCount) {
    const list = Array.isArray(speakers) ? speakers : [];
    const count = typeof speakerCount === "number" ? speakerCount : list.length;
    const layout = resolveLayout(selection, count);
    let activeIndex = list.findIndex((speaker) => /host/i.test((speaker && speaker.role) || ""));
    if (activeIndex < 0 && list.length) {
      activeIndex = 0;
    }
    return list.map((speaker, index) => ({
      role: (speaker && speaker.role) || "Speaker",
      name: (speaker && speaker.name) || "Unnamed speaker",
      active: layout === "spotlight" && index === activeIndex,
      layout,
    }));
  }

  // Everything the workspace shows once a style is applied. Computed from the selection
  // and speaker count, so the applied-style summary always reflects the real choices.
  function summarizeStyle(selection, speakerCount) {
    const preset = getPreset(selection && selection.presetId);
    const layoutId = resolveLayout(selection, speakerCount);
    const usedAuto = !selection || !selection.layout || selection.layout === "auto";
    return {
      presetId: preset.id,
      presetName: preset.name,
      tagline: preset.tagline,
      layoutId,
      layoutLabel: getLayout(layoutId).label,
      resolvedFromAuto: usedAuto,
      pacingId: getPacing(selection && selection.pacing).id,
      pacingLabel: getPacing(selection && selection.pacing).label,
      captionStyle: preset.captionStyle,
      accent: preset.accent,
      background: preset.background,
    };
  }

  const api = {
    STYLE_PRESETS,
    LAYOUTS,
    PACING,
    defaultPreset,
    getPreset,
    getLayout,
    getPacing,
    createSelection,
    resolveLayout,
    buildPreviewFrames,
    summarizeStyle,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
    return;
  }

  global.PdcEpisodeStyle = api;
}(typeof window !== "undefined" ? window : globalThis));
