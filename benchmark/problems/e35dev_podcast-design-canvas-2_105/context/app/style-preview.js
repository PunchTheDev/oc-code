"use strict";

// Rich episode look previews for Podcast Design Canvas (#102).
//
// Builds demo-quality preset previews with realistic multi-speaker framing, captions,
// title treatment, overlays, and pacing cues. DOM-free so UI and tests share one model.
(function (global) {
  function styleApi() {
    if (typeof module !== "undefined" && module.exports && typeof require === "function") {
      return require("./episode-style.js");
    }
    const g = typeof window !== "undefined" ? window : globalThis;
    return g.PdcEpisodeStyle;
  }

  const SAMPLE_SPEAKERS = [
    { role: "Host", name: "Sam Rivera", initials: "SR", tile: "#5b4bff" },
    { role: "Guest 1", name: "Dana Kim", initials: "DK", tile: "#2bb9a9" },
    { role: "Guest 2", name: "Alex Chen", initials: "AC", tile: "#f0a030" },
  ];

  const PRESET_OVERLAY = {
    "studio-spotlight": "LIVE",
    "split-stage": "Founders",
    "panel-grid": "Panel",
    "bold-broadcast": "ON AIR",
  };

  function trim(value) {
    return typeof value === "string" ? value.trim() : "";
  }

  function sampleEpisodeSummary(showName) {
    const title = trim(showName) || "Founders Unfiltered";
    return {
      episodeName: `${title} · Episode 12`,
      showName: title,
      speakers: SAMPLE_SPEAKERS.map((speaker) => Object.assign({}, speaker)),
      speakerCount: SAMPLE_SPEAKERS.length,
    };
  }

  function initialsForName(name) {
    const parts = trim(name).split(/\s+/).filter(Boolean);
    if (!parts.length) {
      return "?";
    }
    if (parts.length === 1) {
      return parts[0].slice(0, 2).toUpperCase();
    }
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }

  function buildEpisodeLook(presetId, options) {
    const STY = styleApi();
    const opts = options || {};
    const preset = STY ? STY.getPreset(presetId) : null;
    if (!preset) {
      return null;
    }
    const summary = sampleEpisodeSummary(opts.showName);
    const selection = {
      presetId: preset.id,
      layout: preset.defaultLayout,
      pacing: opts.pacing || "balanced",
    };
    const layoutId = STY.resolveLayout(selection, summary.speakerCount);
    let activeIndex = summary.speakers.findIndex((speaker) => /host/i.test(speaker.role));
    if (activeIndex < 0) {
      activeIndex = 0;
    }
    const frames = summary.speakers.map((speaker, index) => ({
      role: speaker.role,
      name: speaker.name,
      initials: speaker.initials,
      tile: speaker.tile,
      active: layoutId === "spotlight" ? index === activeIndex : true,
    }));
    const pacing = STY.getPacing(selection.pacing);
    return {
      presetId: preset.id,
      presetName: preset.name,
      tagline: preset.tagline,
      layoutId: layoutId,
      layoutLabel: STY.getLayout(layoutId).label,
      pacingLabel: pacing.label,
      captionStyle: preset.captionStyle,
      formatCue: STY.presetCardSummary(preset).formatCue,
      episodeTitle: summary.episodeName,
      showName: summary.showName,
      captionText: "Building in public means shipping the story before the polish is perfect.",
      overlayLabel: PRESET_OVERLAY[preset.id] || preset.name.split(" ")[0].toUpperCase(),
      theme: {
        background: preset.background,
        surface: preset.surface,
        accent: preset.accent,
        textColor: preset.textColor,
      },
      frames: frames,
    };
  }

  function buildEpisodeLookFromEpisode(presetId, summary, selection) {
    const STY = styleApi();
    const episode = summary || {};
    const sel = selection || {};
    const preset = STY ? STY.getPreset(presetId || sel.presetId) : null;
    if (!preset) {
      return null;
    }
    const mergedSelection = {
      presetId: preset.id,
      layout: sel.layout || preset.defaultLayout,
      pacing: sel.pacing || "balanced",
    };
    const speakers = Array.isArray(episode.speakers) && episode.speakers.length
      ? episode.speakers
      : SAMPLE_SPEAKERS;
    const speakerCount = episode.speakerCount || speakers.length;
    const layoutId = STY.resolveLayout(mergedSelection, speakerCount);
    let activeIndex = speakers.findIndex((speaker) => /host/i.test((speaker && speaker.role) || ""));
    if (activeIndex < 0 && speakers.length) {
      activeIndex = 0;
    }
    const frames = speakers.map((speaker, index) => {
      const sample = SAMPLE_SPEAKERS[index] || SAMPLE_SPEAKERS[0];
      const name = trim(speaker && speaker.name) || sample.name;
      return {
        role: (speaker && speaker.role) || sample.role,
        name: name,
        initials: initialsForName(name),
        tile: sample.tile,
        active: layoutId === "spotlight" ? index === activeIndex : true,
      };
    });
    const pacing = STY.getPacing(mergedSelection.pacing);
    const showName = trim(episode.episodeName).split("·")[0].trim() || "Your show";
    return {
      presetId: preset.id,
      presetName: preset.name,
      tagline: preset.tagline,
      layoutId: layoutId,
      layoutLabel: STY.getLayout(layoutId).label,
      pacingLabel: pacing.label,
      captionStyle: preset.captionStyle,
      formatCue: STY.presetCardSummary(preset).formatCue,
      episodeTitle: trim(episode.episodeName) || `${showName} · Episode 1`,
      showName: showName,
      captionText: "Building in public means shipping the story before the polish is perfect.",
      overlayLabel: PRESET_OVERLAY[preset.id] || preset.name.split(" ")[0].toUpperCase(),
      theme: {
        background: preset.background,
        surface: preset.surface,
        accent: preset.accent,
        textColor: preset.textColor,
      },
      frames: frames,
    };
  }

  const api = {
    SAMPLE_SPEAKERS,
    PRESET_OVERLAY,
    sampleEpisodeSummary,
    buildEpisodeLook,
    buildEpisodeLookFromEpisode,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
    return;
  }

  global.PdcStylePreview = api;
}(typeof window !== "undefined" ? window : globalThis));