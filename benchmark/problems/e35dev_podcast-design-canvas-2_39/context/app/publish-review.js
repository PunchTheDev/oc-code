"use strict";

// Full-episode publish review model for Podcast Design Canvas (#37).
//
// Gives creators a confidence check before export: a timeline of assembled choices,
// creator-facing warnings for gaps, and approval only when publish-ready checks pass.
// DOM-free so the review screen and tests share one source of truth.
(function (global) {
  const FIX_TARGETS = {
    setup: "setup",
    context: "context",
    audio: "audio",
    style: "style",
    canvas: "canvas",
    moments: "moments",
    workspace: "workspace",
    export: "export",
  };

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function check(id, sectionId, tone, title, message, action) {
    return {
      id: id,
      sectionId: sectionId,
      tone: tone,
      title: title,
      message: message,
      action: action || null,
      passed: tone === "ok",
    };
  }

  function countVisibleCaptions(momentsBoard) {
    const moments = momentsBoard && Array.isArray(momentsBoard.moments) ? momentsBoard.moments : [];
    return moments.filter((moment) => moment.type === "caption" && moment.visible !== false).length;
  }

  function runChecks(episodeSummary, ctx) {
    const episode = episodeSummary || {};
    const context = ctx || {};
    const checks = [];
    const speakers = Array.isArray(episode.speakers) ? episode.speakers : [];

    const unnamed = speakers.filter((speaker) => !speaker.name || !speaker.name.trim());
    if (unnamed.length) {
      checks.push(check(
        "speakers-unnamed",
        "setup",
        "blocker",
        "Speaker names missing",
        "Every speaker needs a name before this episode can publish.",
        { label: "Fix setup", target: FIX_TARGETS.setup },
      ));
    } else {
      checks.push(check(
        "speakers-ready",
        "setup",
        "ok",
        "Speakers assigned",
        `${speakers.length} speaker${speakers.length === 1 ? "" : "s"} with names and sources.`,
        null,
      ));
    }

    if (episode.socialLinkCount > 0) {
      if (context.contextApproved) {
        checks.push(check(
          "context-ready",
          "context",
          "ok",
          "Social context approved",
          context.contextSummary && context.contextSummary.reviewLine
            ? context.contextSummary.reviewLine.replace(/^Context: /, "")
            : "Names, brands, and spelling hints are set.",
          null,
        ));
      } else {
        checks.push(check(
          "context-missing",
          "context",
          "blocker",
          "Social context not approved",
          "You added social links — review and approve the spelling hints before publishing.",
          { label: "Review context", target: FIX_TARGETS.context },
        ));
      }
    } else {
      checks.push(check(
        "context-optional",
        "context",
        "ok",
        "Social context optional",
        "No social links added — you can still publish with the names you entered.",
        null,
      ));
    }

    if (context.audioPolish && context.audioPolish.presetName) {
      checks.push(check(
        "audio-ready",
        "audio",
        "ok",
        "Audio polished",
        `${context.audioPolish.presetName} · ${context.audioPolish.treatmentLine || "treatment applied"}`,
        null,
      ));
    } else {
      checks.push(check(
        "audio-missing",
        "audio",
        "blocker",
        "Audio polish missing",
        "Choose a sound quality preset so the episode audio is publish-ready.",
        { label: "Polish audio", target: FIX_TARGETS.audio },
      ));
    }

    if (context.appliedStyle && context.appliedStyle.presetName) {
      checks.push(check(
        "style-ready",
        "style",
        "ok",
        "Visual style chosen",
        `${context.appliedStyle.presetName} · ${context.appliedStyle.layoutLabel || "layout"}`,
        null,
      ));
    } else {
      checks.push(check(
        "style-missing",
        "style",
        "blocker",
        "Visual style missing",
        "Pick a preset look so the episode has a coherent on-screen identity.",
        { label: "Choose style", target: FIX_TARGETS.style },
      ));
    }

    const hasTemplate = Boolean(context.templateName);
    const hasCanvas = Boolean(context.hasCanvas);
    if (hasTemplate) {
      checks.push(check(
        "template-ready",
        "canvas",
        "ok",
        "Show template saved",
        context.templateName,
        null,
      ));
    } else if (hasCanvas) {
      checks.push(check(
        "canvas-ready",
        "canvas",
        "ok",
        "Layout customized",
        "Canvas layout is personalized for this episode.",
        null,
      ));
    } else {
      checks.push(check(
        "template-empty",
        "canvas",
        "warning",
        "No saved show template",
        "Consider saving a show template so future episodes keep the same visual identity.",
        { label: "Open canvas", target: FIX_TARGETS.canvas },
      ));
    }

    const captionCount = typeof context.captionCount === "number"
      ? context.captionCount
      : countVisibleCaptions(context.momentsBoard);
    const momentTotal = context.momentsSummary && context.momentsSummary.total
      ? context.momentsSummary.total
      : 0;

    if (captionCount > 0) {
      checks.push(check(
        "captions-ready",
        "moments",
        "ok",
        "Captions placed",
        `${captionCount} caption moment${captionCount === 1 ? "" : "s"} across the episode.`,
        null,
      ));
    } else {
      checks.push(check(
        "captions-missing",
        "moments",
        "warning",
        "No caption moments yet",
        "Add caption sections at key points so viewers can follow the conversation.",
        { label: "Add moments", target: FIX_TARGETS.moments },
      ));
    }

    if (momentTotal === 0) {
      checks.push(check(
        "moments-empty",
        "moments",
        "warning",
        "No visual moments placed",
        "Title cards, b-roll, and callouts help a long episode feel deliberately produced.",
        { label: "Add moments", target: FIX_TARGETS.moments },
      ));
    } else {
      checks.push(check(
        "moments-ready",
        "moments",
        "ok",
        "Visual moments placed",
        context.momentsSummary && context.momentsSummary.reviewLine
          ? context.momentsSummary.reviewLine.replace(/^Visual moments: /, "")
          : `${momentTotal} moments across the timeline.`,
        null,
      ));
    }

    const exportReady = Boolean(context.audioPolish && context.audioPolish.presetName
      && context.appliedStyle && context.appliedStyle.presetName);
    if (exportReady) {
      checks.push(check(
        "export-ready",
        "export",
        "ok",
        "Core export requirements met",
        "Audio and visual style are set — approve this review to unlock export.",
        null,
      ));
    } else {
      checks.push(check(
        "export-blocked",
        "export",
        "blocker",
        "Not ready to export",
        "Complete audio polish and visual style before exporting this episode.",
        { label: "Back to workspace", target: FIX_TARGETS.workspace },
      ));
    }

    return checks;
  }

  function buildTimeline(episodeSummary, ctx, checks) {
    const episode = episodeSummary || {};
    const context = ctx || {};
    const bySection = {};
    checks.forEach((item) => {
      if (!bySection[item.sectionId]) {
        bySection[item.sectionId] = [];
      }
      bySection[item.sectionId].push(item);
    });

    function sectionStatus(sectionId) {
      const items = bySection[sectionId] || [];
      if (items.some((item) => item.tone === "blocker" && !item.passed)) {
        return "blocked";
      }
      if (items.some((item) => item.tone === "warning" && !item.passed)) {
        return "warning";
      }
      return "ready";
    }

    return [
      {
        id: "setup",
        label: "Episode setup",
        time: "0:00",
        summary: `${episode.speakerCount || 0} speakers · ${episode.sourceModeLabel || "sources"}`,
        status: sectionStatus("setup"),
      },
      {
        id: "context",
        label: "Social context",
        time: "5:00",
        summary: episode.socialLinkCount
          ? `${episode.socialLinkCount} social link${episode.socialLinkCount === 1 ? "" : "s"}`
          : "Names from setup",
        status: sectionStatus("context"),
      },
      {
        id: "audio",
        label: "Audio polish",
        time: "15:00",
        summary: context.audioPolish ? context.audioPolish.presetName : "Not set",
        status: sectionStatus("audio"),
      },
      {
        id: "style",
        label: "Visual style",
        time: "25:00",
        summary: context.appliedStyle ? context.appliedStyle.presetName : "Not set",
        status: sectionStatus("style"),
      },
      {
        id: "canvas",
        label: "Layout & template",
        time: "35:00",
        summary: context.templateName || (context.hasCanvas ? "Custom layout" : "Preset layout"),
        status: sectionStatus("canvas"),
      },
      {
        id: "moments",
        label: "Visual moments",
        time: "45:00",
        summary: context.momentsSummary && context.momentsSummary.total
          ? `${context.momentsSummary.total} moments`
          : "None placed",
        status: sectionStatus("moments"),
      },
      {
        id: "export",
        label: "Export readiness",
        time: "End",
        summary: "Final publish check",
        status: sectionStatus("export"),
      },
    ];
  }

  function createReview(episodeSummary, ctx) {
    const checks = runChecks(episodeSummary, ctx);
    return {
      episodeName: (episodeSummary && episodeSummary.episodeName) || "",
      approved: false,
      approvedAt: null,
      checks: checks,
      timeline: buildTimeline(episodeSummary, ctx, checks),
    };
  }

  function blockers(review) {
    const checks = review && Array.isArray(review.checks) ? review.checks : [];
    return checks.filter((item) => item.tone === "blocker" && !item.passed);
  }

  function warnings(review) {
    const checks = review && Array.isArray(review.checks) ? review.checks : [];
    return checks.filter((item) => item.tone === "warning" && !item.passed);
  }

  function canApprove(review) {
    return blockers(review).length === 0;
  }

  function approveReview(review) {
    const current = review || createReview({}, {});
    if (!canApprove(current)) {
      return {
        ok: false,
        error: "Fix the required items before approving this episode for export.",
        review: current,
      };
    }
    return {
      ok: true,
      review: Object.assign({}, current, { approved: true, approvedAt: Date.now() }),
    };
  }

  function summarizeReview(review) {
    const blockersList = blockers(review);
    const warningsList = warnings(review);
    return {
      approved: Boolean(review && review.approved),
      blockerCount: blockersList.length,
      warningCount: warningsList.length,
      canApprove: canApprove(review),
      reviewLine: review && review.approved
        ? "Publish review approved — ready to export."
        : blockersList.length
          ? `${blockersList.length} required fix${blockersList.length === 1 ? "" : "es"} before approval`
          : warningsList.length
            ? `${warningsList.length} suggestion${warningsList.length === 1 ? "" : "s"} — you can approve when ready`
            : "Ready to approve",
    };
  }

  function validateExportGate(review) {
    if (!review || !review.approved) {
      return {
        ok: false,
        error: review && canApprove(review)
          ? "Approve the publish review before exporting."
          : "Complete the publish review before exporting.",
      };
    }
    return { ok: true };
  }

  const api = {
    FIX_TARGETS,
    createReview,
    runChecks,
    buildTimeline,
    blockers,
    warnings,
    canApprove,
    approveReview,
    summarizeReview,
    validateExportGate,
    countVisibleCaptions,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
    return;
  }

  global.PdcPublishReview = api;
}(typeof window !== "undefined" ? window : globalThis));