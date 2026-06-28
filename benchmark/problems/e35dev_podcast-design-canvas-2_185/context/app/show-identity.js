"use strict";

// Show identity episode start for Podcast Design Canvas (#57).
//
// Connects the show library, brand kits, and saved templates into a repeat-production
// workflow: starting a new episode prefills setup, style, canvas, and export context
// from the show's established identity while leaving every step editable.
(function (global) {
  function trim(value) {
    return typeof value === "string" ? value.trim() : "";
  }

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function setupApi() {
    if (typeof module !== "undefined" && module.exports && typeof require === "function") {
      return require("./episode-setup.js");
    }
    const g = typeof window !== "undefined" ? window : globalThis;
    return g.PdcEpisodeSetup;
  }

  function styleApi() {
    if (typeof module !== "undefined" && module.exports && typeof require === "function") {
      return require("./episode-style.js");
    }
    const g = typeof window !== "undefined" ? window : globalThis;
    return g.PdcEpisodeStyle;
  }

  function templatesApi() {
    if (typeof module !== "undefined" && module.exports && typeof require === "function") {
      return require("./show-templates.js");
    }
    const g = typeof window !== "undefined" ? window : globalThis;
    return g.PdcShowTemplates;
  }

  function brandKitApi() {
    if (typeof module !== "undefined" && module.exports && typeof require === "function") {
      return require("./show-brand-kit.js");
    }
    const g = typeof window !== "undefined" ? window : globalThis;
    return g.PdcShowBrandKit;
  }

  function suggestedEpisodeName(show) {
    const episodes = show && Array.isArray(show.episodes) ? show.episodes : [];
    const nextNumber = episodes.length + 1;
    const base = (show && show.name) || "Episode";
    return `${base} — Episode ${nextNumber}`;
  }

  function isShowContextLabel(text, show, draft) {
    const trimmed = trim(text);
    if (!trimmed) {
      return false;
    }
    const showName = show && trim(show.name);
    const episodeName = draft && trim(draft.episodeName);
    const lowered = trimmed.toLowerCase();
    if (showName && lowered === showName.toLowerCase()) {
      return true;
    }
    if (episodeName && lowered === episodeName.toLowerCase()) {
      return true;
    }
    if (show && lowered === trim(suggestedEpisodeName(show)).toLowerCase()) {
      return true;
    }
    if (episodeName) {
      const episodeStem = trim(episodeName.split("—")[0]);
      if (episodeStem && lowered === episodeStem.toLowerCase()) {
        return true;
      }
    }
    return false;
  }

  function speakerNameForImport(item, show, draft) {
    const name = trim(item && item.name);
    if (!name || isShowContextLabel(name, show, draft)) {
      return "";
    }
    return name;
  }

  function trackLabelForImport(item, show, draft) {
    const label = trim(item && item.trackLabel);
    if (!label || isShowContextLabel(label, show, draft)) {
      return "";
    }
    return label;
  }

  function sanitizeSpeaker(speaker, show, draft) {
    const next = clone(speaker || {});
    if (isShowContextLabel(next.name, show, draft)) {
      next.name = "";
    }
    if (isShowContextLabel(next.trackLabel, show, draft)) {
      next.trackLabel = "";
    }
    return next;
  }

  function sanitizeSetupDraft(draft, show) {
    const next = clone(draft || setupApi().createDraft());
    next.speakers = (next.speakers || []).map((speaker) => sanitizeSpeaker(speaker, show, next));
    return next;
  }

  function applyDefaultSpeakers(draft, show) {
    const ES = setupApi();
    const next = clone(draft || ES.createDraft());
    const defaults = show && Array.isArray(show.defaultSpeakers) ? show.defaultSpeakers : [];
    if (!defaults.length) {
      return sanitizeSetupDraft(next, show);
    }
    next.speakers = defaults.map((item) => {
      const speaker = ES.createSpeaker(item.role || "Host");
      speaker.name = speakerNameForImport(item, show, next);
      speaker.trackLabel = trackLabelForImport(item, show, next);
      if (item.social && typeof item.social === "object") {
        speaker.social = Object.assign({}, speaker.social, item.social);
      }
      return speaker;
    });
    return sanitizeSetupDraft(next, show);
  }

  function buildSetupDraft(show) {
    const ES = setupApi();
    const draft = ES.createDraft();
    draft.episodeName = suggestedEpisodeName(show);
    if (show && show.defaultSourceMode) {
      draft.sourceMode = show.defaultSourceMode;
    }
    if (show && trim(show.defaultRiversideLink)) {
      draft.riversideLink = trim(show.defaultRiversideLink);
    }
    return applyDefaultSpeakers(draft, show);
  }

  function resolveTemplateId(show, preferredTemplateId) {
    const preferred = typeof preferredTemplateId === "string" ? preferredTemplateId.trim() : "";
    if (preferred) {
      return preferred;
    }
    return show && show.templateId ? show.templateId : "";
  }

  function templateBelongsToShow(template, show) {
    if (!template || !show || !show.id) {
      return Boolean(template);
    }
    const scopedShowId = typeof template.showId === "string" ? template.showId.trim() : "";
    return !scopedShowId || scopedShowId === show.id;
  }

  function resolveStyleSelection(show, templateStore, preferredTemplateId) {
    const STY = styleApi();
    const TM = templatesApi();
    let selection = STY ? STY.createSelection() : { presetId: "studio-spotlight", layout: "auto", pacing: "balanced" };
    const templateId = resolveTemplateId(show, preferredTemplateId);

    if (show && templateId && TM && templateStore) {
      const template = TM.getTemplate(templateStore, templateId);
      if (template && templateBelongsToShow(template, show)) {
        const fromCanvas = TM.styleSelectionFromCanvas(template.canvas);
        if (fromCanvas) {
          return fromCanvas;
        }
      }
    }

    if (show && show.presetId && STY) {
      selection.presetId = show.presetId;
      const preset = STY.getPreset(show.presetId);
      if (preset) {
        selection.layout = preset.defaultLayout || selection.layout;
      }
    } else if (show && show.presetName && STY && STY.STYLE_PRESETS) {
      const match = STY.STYLE_PRESETS.find((preset) => preset.name === show.presetName);
      if (match) {
        selection.presetId = match.id;
        selection.layout = match.defaultLayout || selection.layout;
      }
    }

    return selection;
  }

  function resolveTemplate(show, templateStore, preferredTemplateId) {
    const TM = templatesApi();
    const templateId = resolveTemplateId(show, preferredTemplateId);
    if (!show || !templateId || !TM || !templateStore) {
      return null;
    }
    const template = TM.getTemplate(templateStore, templateId);
    if (!template || !templateBelongsToShow(template, show)) {
      return null;
    }
    return template;
  }

  function buildAppliedPresentation(show, templateStore, setupDraft, preferredTemplateId) {
    const ES = setupApi();
    const STY = styleApi();
    const TM = templatesApi();
    const BK = brandKitApi();
    const summary = ES.summarize(setupDraft || buildSetupDraft(show));
    const styleSelection = resolveStyleSelection(show, templateStore, preferredTemplateId);
    const template = resolveTemplate(show, templateStore, preferredTemplateId);
    let canvasDoc = null;

    if (template && TM) {
      canvasDoc = TM.applyTemplateForEpisode(template, summary, styleSelection);
    }

    let appliedStyle = STY
      ? STY.summarizeStyle(styleSelection, summary.speakerCount)
      : null;

    const brandKit = show && show.brandKit ? clone(show.brandKit) : null;
    if (brandKit && BK) {
      if (appliedStyle) {
        appliedStyle = BK.applyToStyleSummary(appliedStyle, brandKit);
      }
      if (canvasDoc) {
        canvasDoc = BK.applyToCanvas(canvasDoc, brandKit);
      }
    }

    return {
      summary: summary,
      styleSelection: styleSelection,
      appliedStyle: appliedStyle,
      canvasDoc: canvasDoc,
      templateId: template ? template.id : (show && show.templateId) || "",
      templateName: template ? template.name : (show && show.templateName) || "",
      brandKit: brandKit,
    };
  }

  function summarizeShowIdentity(show, presentation) {
    const s = show || {};
    const p = presentation || {};
    const lines = [];
    lines.push(`Show: ${s.name || "Untitled show"}`);
    if (p.templateName) {
      lines.push(`Template: ${p.templateName}`);
    }
    if (p.appliedStyle && p.appliedStyle.presetName) {
      lines.push(`Style: ${p.appliedStyle.presetName}${p.appliedStyle.layoutLabel ? ` · ${p.appliedStyle.layoutLabel}` : ""}`);
    }
    if (p.brandKit && brandKitApi()) {
      const brandSummary = brandKitApi().summarizeBrandKit(p.brandKit);
      if (brandSummary.reviewLine) {
        lines.push(brandSummary.reviewLine);
      }
    }
    if (p.summary && p.summary.socialLinkCount > 0) {
      lines.push(`${p.summary.socialLinkCount} saved social link${p.summary.socialLinkCount === 1 ? "" : "s"} for host context`);
    }
    return {
      headline: `Starting from ${s.name || "show"} identity`,
      identityLine: lines.join(" · "),
      lines: lines,
    };
  }

  function buildEpisodeStart(show, templateStore, options) {
    const opts = options || {};
    const setupDraft = buildSetupDraft(show);
    const presentation = buildAppliedPresentation(show, templateStore, setupDraft, opts.templateId);
    const identity = summarizeShowIdentity(show, presentation);

    return {
      fromShowIdentity: true,
      showId: show.id || "",
      showName: show.name || "",
      setupDraft: setupDraft,
      styleSelection: presentation.styleSelection,
      appliedStyle: presentation.appliedStyle,
      canvasDoc: presentation.canvasDoc,
      templateId: presentation.templateId,
      templateName: presentation.templateName,
      brandKit: presentation.brandKit,
      summary: presentation.summary,
      identity: identity,
    };
  }

  function buildBlankEpisodeStart() {
    const ES = setupApi();
    const STY = styleApi();
    return {
      fromShowIdentity: false,
      showId: "",
      showName: "",
      setupDraft: ES.createDraft(),
      styleSelection: STY ? STY.createSelection() : null,
      appliedStyle: null,
      canvasDoc: null,
      templateId: "",
      templateName: "",
      brandKit: null,
      summary: null,
      identity: {
        headline: "Start a blank episode",
        identityLine: "Generic defaults — no show identity applied.",
        lines: [],
      },
    };
  }

  const api = {
    suggestedEpisodeName,
    isShowContextLabel,
    speakerNameForImport,
    trackLabelForImport,
    sanitizeSpeaker,
    sanitizeSetupDraft,
    buildSetupDraft,
    resolveStyleSelection,
    resolveTemplate,
    buildAppliedPresentation,
    summarizeShowIdentity,
    buildEpisodeStart,
    buildBlankEpisodeStart,
    applyDefaultSpeakers,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
    return;
  }

  global.PdcShowIdentity = api;
}(typeof window !== "undefined" ? window : globalThis));
