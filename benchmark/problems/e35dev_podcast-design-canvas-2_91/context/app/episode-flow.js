"use strict";

// Episode workflow progress and resume routing for Podcast Design Canvas (#89).
//
// Maps the guided production journey to step indicators, show-home resume actions,
// and the view a creator should land on when returning to a draft episode.
// DOM-free so the UI and tests share one source of truth.
(function (global) {
  const WORKFLOW_TOTAL = 8;

  const WORKFLOW_STEPS = [
    { num: 1, id: "setup", label: "Set up episode" },
    { num: 2, id: "context", label: "Review context" },
    { num: 3, id: "audio", label: "Audio polish" },
    { num: 4, id: "style", label: "Choose a style" },
    { num: 5, id: "canvas", label: "Canvas editor" },
    { num: 6, id: "moments", label: "Visual moments" },
    { num: 7, id: "review", label: "Publish review" },
    { num: 8, id: "export", label: "Export & publish" },
  ];

  const WORKSPACE_STAGE_STEP = {
    setup: 1,
    audio: 3,
    style: 4,
    template: 5,
    moments: 6,
    review: 7,
    export: 8,
  };

  const RESUMABLE_STATUSES = new Set(["draft", "in-progress", "review"]);

  function trim(value) {
    return typeof value === "string" ? value.trim() : "";
  }

  function parseStepLabel(label) {
    const text = trim(label);
    const match = text.match(/^Step\s+(\d+)\s+of\s+(\d+)\s+·\s+(.+)$/i);
    if (match) {
      return {
        step: Number(match[1]),
        total: Number(match[2]),
        subtitle: match[3],
        headline: text,
      };
    }
    if (/production workspace|import to publish/i.test(text)) {
      return {
        step: null,
        total: WORKFLOW_TOTAL,
        subtitle: "Production workspace",
        headline: text,
      };
    }
    return {
      step: null,
      total: WORKFLOW_TOTAL,
      subtitle: text,
      headline: text,
    };
  }

  function stepIndicatorForLabel(label) {
    const parsed = parseStepLabel(label);
    const step = parsed.step || WORKFLOW_TOTAL;
    const progress = Math.max(0, Math.min(1, step / parsed.total));
    return {
      countText: parsed.step ? `Step ${parsed.step} of ${parsed.total}` : "Production flow",
      labelText: parsed.subtitle || parsed.headline,
      progress: progress,
      step: parsed.step,
      total: parsed.total,
    };
  }

  function stepIndicatorForWorkspaceStage(stageId) {
    const step = WORKSPACE_STAGE_STEP[stageId] || 1;
    const match = WORKFLOW_STEPS.find((entry) => entry.num === step);
    return {
      countText: `Step ${step} of ${WORKFLOW_TOTAL}`,
      labelText: match ? match.label : "Production workspace",
      progress: step / WORKFLOW_TOTAL,
      step: step,
      total: WORKFLOW_TOTAL,
    };
  }

  function latestResumableDraft(episodes) {
    const list = Array.isArray(episodes) ? episodes : [];
    const resumable = list.filter((episode) => RESUMABLE_STATUSES.has(episode && episode.status));
    if (!resumable.length) {
      return null;
    }
    return resumable.slice().sort(function (a, b) {
      return (b.updatedAt || b.createdAt || 0) - (a.updatedAt || a.createdAt || 0);
    })[0];
  }

  function resumeDestination(session) {
    const data = session && typeof session === "object" ? session : {};
    if (data.workspaceReached || data.lastView === "workspace") {
      return "workspace";
    }
    if (data.setupComplete && data.lastView && data.lastView !== "setup") {
      return data.lastView;
    }
    return "setup";
  }

  function summarizeResumeAction(episode) {
    const ep = episode || {};
    return {
      episodeId: ep.id || "",
      episodeName: ep.name || "Draft episode",
      status: ep.status || "draft",
      actionLabel: "Resume draft episode →",
      title: `Resume "${trim(ep.name) || "Draft episode"}"`,
      hint: "Pick up where you left off — your speaker setup and production progress stay with this draft.",
    };
  }

  const api = {
    WORKFLOW_TOTAL,
    WORKFLOW_STEPS,
    WORKSPACE_STAGE_STEP,
    RESUMABLE_STATUSES,
    parseStepLabel,
    stepIndicatorForLabel,
    stepIndicatorForWorkspaceStage,
    latestResumableDraft,
    resumeDestination,
    summarizeResumeAction,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
    return;
  }

  global.PdcEpisodeFlow = api;
}(typeof window !== "undefined" ? window : globalThis));