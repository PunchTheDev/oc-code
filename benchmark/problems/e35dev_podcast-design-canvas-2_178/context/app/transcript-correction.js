"use strict";

// Transcript and caption correction for Podcast Design Canvas (#63).
//
// Lets creators fix speaker names, brand spellings, topic terms, and caption text once,
// then applies those corrections to moments, canvas captions, export metadata, and the
// publish package. DOM-free so the review screen and tests share one source of truth.
(function (global) {
  function trim(value) {
    return typeof value === "string" ? value.trim() : "";
  }

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function escapeRegExp(text) {
    return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function socialContextApi() {
    if (typeof module !== "undefined" && module.exports && typeof require === "function") {
      return require("./social-context.js");
    }
    const g = typeof window !== "undefined" ? window : globalThis;
    return g.PdcSocialContext;
  }

  function momentsApi() {
    if (typeof module !== "undefined" && module.exports && typeof require === "function") {
      return require("./visual-moments.js");
    }
    const g = typeof window !== "undefined" ? window : globalThis;
    return g.PdcVisualMoments;
  }

  function buildSpeakers(episodeSummary, contextReview) {
    const episode = episodeSummary || {};
    const speakers = Array.isArray(episode.speakers) ? episode.speakers : [];
    const SC = socialContextApi();
    if (contextReview && Array.isArray(contextReview.speakers) && contextReview.speakers.length) {
      return contextReview.speakers.map((entry) => ({
        role: entry.role,
        label: entry.displayName,
        brand: entry.brand || "",
        topicTerms: Array.isArray(entry.topics) ? entry.topics.slice() : [],
        spellingHints: Array.isArray(entry.spellingHints) ? entry.spellingHints.slice() : [],
      }));
    }
    return speakers.map((speaker) => {
      const derived = SC ? SC.deriveSpeakerContext(speaker) : {};
      return {
        role: speaker.role || "Speaker",
        label: speaker.name || derived.displayName || "Unnamed speaker",
        brand: derived.brand || "",
        topicTerms: derived.topics || [],
        spellingHints: derived.spellingHints || [],
      };
    });
  }

  function speakerByRole(review, role) {
    const speakers = review && Array.isArray(review.speakers) ? review.speakers : [];
    return speakers.find((speaker) => speaker.role === role) || null;
  }

  function buildReplacements(speakers) {
    const replacements = [];
    (speakers || []).forEach((speaker) => {
      (speaker.spellingHints || []).forEach((hint) => {
        if (hint && speaker.label && hint.toLowerCase() !== speaker.label.toLowerCase()) {
          replacements.push({ from: hint, to: speaker.label, kind: "speaker" });
        }
      });
      if (speaker.brand) {
        replacements.push({ from: speaker.brand.toLowerCase(), to: speaker.brand, kind: "brand" });
      }
      (speaker.topicTerms || []).forEach((term) => {
        if (term) {
          replacements.push({ from: term.toLowerCase(), to: term, kind: "topic" });
        }
      });
    });
    return dedupeReplacements(replacements);
  }

  function dedupeReplacements(replacements) {
    const seen = {};
    return (replacements || []).filter((item) => {
      const key = `${(item.from || "").toLowerCase()}→${item.to || ""}`;
      if (!item.from || !item.to || seen[key]) {
        return false;
      }
      seen[key] = true;
      return true;
    });
  }

  function applyReplacements(text, replacements) {
    let next = trim(text);
    if (!next) {
      return next;
    }
    (replacements || []).forEach((item) => {
      if (!item.from || !item.to) {
        return;
      }
      next = next.replace(new RegExp(escapeRegExp(item.from), "gi"), item.to);
    });
    return next;
  }

  function initialLineText(text, review, speakerRole, speakerName) {
    const SC = socialContextApi();
    let next = trim(text);
    if (SC && review.contextApproved && review.contextReview) {
      next = SC.applyHintsToText(next, review.contextReview, speakerRole, speakerName);
    }
    return applyReplacements(next, review.replacements);
  }

  function buildLines(episodeSummary, review, momentsBoard) {
    const lines = [];
    const speakers = review.speakers || [];
    const board = momentsBoard || {};
    const transcript = Array.isArray(board.transcript) ? board.transcript : [];
    const VM = momentsApi();
    const moments = VM ? VM.listMoments(board) : (Array.isArray(board.moments) ? board.moments : []);

    moments
      .filter((moment) => moment.visible !== false)
      .filter((moment) => moment.type === "caption" || moment.type === "title" || moment.type === "callout")
      .forEach((moment) => {
        const speaker = speakerByRole(review, moment.speakerRole);
        const originalText = trim(moment.text);
        lines.push({
          id: `line-moment-${moment.id}`,
          time: moment.time,
          speakerRole: moment.speakerRole,
          speakerLabel: speaker ? speaker.label : moment.speakerName,
          originalText: originalText,
          text: initialLineText(originalText, review, moment.speakerRole, moment.speakerName),
          source: "moment",
          momentId: moment.id,
          kind: moment.type,
        });
      });

    transcript.forEach((segment) => {
      const speaker = speakerByRole(review, segment.speakerRole);
      const label = speaker ? speaker.label : segment.speakerName;
      const originalText = `${segment.speakerName} speaks at ${segment.time}`;
      lines.push({
        id: `line-transcript-${segment.index}`,
        time: segment.time,
        speakerRole: segment.speakerRole,
        speakerLabel: label,
        originalText: originalText,
        text: initialLineText(`${label} speaks at ${segment.time}`, review, segment.speakerRole, segment.speakerName),
        source: "transcript",
        transcriptIndex: segment.index,
        kind: "transcript",
      });
    });

    if (!lines.length && episodeSummary && episodeSummary.episodeName) {
      lines.push({
        id: "line-episode-title",
        time: "0:00",
        speakerRole: "Host",
        speakerLabel: speakers[0] ? speakers[0].label : "Host",
        originalText: episodeSummary.episodeName,
        text: initialLineText(episodeSummary.episodeName, review, "Host", speakers[0] ? speakers[0].label : ""),
        source: "episode",
        kind: "title",
      });
    }

    return lines.sort((a, b) => {
      const parse = (value) => {
        const parts = String(value || "0:0").split(":");
        return (Number(parts[0]) || 0) * 60 + (Number(parts[1]) || 0);
      };
      return parse(a.time) - parse(b.time);
    });
  }

  function createCorrectionReview(episodeSummary, options) {
    const opts = options || {};
    const speakers = buildSpeakers(episodeSummary, opts.contextReview);
    const review = {
      episodeName: trim(episodeSummary && episodeSummary.episodeName),
      approved: false,
      contextApproved: Boolean(opts.contextReview && opts.contextReview.approved),
      contextReview: opts.contextReview ? clone(opts.contextReview) : null,
      speakers: speakers,
      replacements: buildReplacements(speakers),
      lines: [],
    };
    review.lines = buildLines(episodeSummary, review, opts.momentsBoard);
    return review;
  }

  function updateSpeaker(review, role, patch) {
    const next = clone(review || createCorrectionReview({}, {}));
    next.speakers = (next.speakers || []).map((speaker) => {
      if (speaker.role !== role) {
        return speaker;
      }
      const updated = Object.assign({}, speaker, patch || {});
      if (patch && patch.label != null) {
        updated.label = trim(patch.label);
      }
      if (patch && patch.brand != null) {
        updated.brand = trim(patch.brand);
      }
      if (patch && patch.topicTerms != null) {
        updated.topicTerms = Array.isArray(patch.topicTerms)
          ? patch.topicTerms.map(trim).filter(Boolean)
          : String(patch.topicTerms).split(",").map(trim).filter(Boolean);
      }
      return updated;
    });
    next.replacements = dedupeReplacements(
      buildReplacements(next.speakers).concat(next.replacements || []),
    );
    next.lines = (next.lines || []).map((line) => {
      if (line.speakerRole !== role) {
        return line;
      }
      const speaker = speakerByRole(next, role);
      return Object.assign({}, line, {
        speakerLabel: speaker ? speaker.label : line.speakerLabel,
      });
    });
    next.approved = false;
    return next;
  }

  function updateLine(review, lineId, patch) {
    const next = clone(review || createCorrectionReview({}, {}));
    let extraReplacement = null;
    next.lines = (next.lines || []).map((line) => {
      if (line.id !== lineId) {
        return line;
      }
      const updated = Object.assign({}, line, patch || {});
      if (patch && patch.text != null) {
        updated.text = trim(patch.text);
        if (updated.originalText && updated.text && updated.originalText !== updated.text) {
          extraReplacement = {
            from: updated.originalText,
            to: updated.text,
            kind: "line",
          };
        }
      }
      if (patch && patch.speakerLabel != null) {
        updated.speakerLabel = trim(patch.speakerLabel);
      }
      return updated;
    });
    if (extraReplacement) {
      next.replacements = dedupeReplacements((next.replacements || []).concat(extraReplacement));
    }
    next.approved = false;
    return next;
  }

  function approveCorrection(review) {
    const next = clone(review || createCorrectionReview({}, {}));
    next.approved = true;
    return next;
  }

  function applyToMoments(board, review) {
    const base = clone(board || { moments: [], transcript: [] });
    if (!review || !review.approved) {
      return base;
    }
    const lineByMoment = {};
    (review.lines || []).forEach((line) => {
      if (line.momentId) {
        lineByMoment[line.momentId] = line;
      }
    });
    base.moments = (Array.isArray(base.moments) ? base.moments : []).map((moment) => {
      const line = lineByMoment[moment.id];
      if (!line) {
        return Object.assign({}, moment, {
          text: applyReplacements(moment.text, review.replacements),
          speakerName: (speakerByRole(review, moment.speakerRole) || {}).label || moment.speakerName,
        });
      }
      return Object.assign({}, moment, {
        text: line.text,
        speakerName: line.speakerLabel,
      });
    });
    base.transcript = (Array.isArray(base.transcript) ? base.transcript : []).map((segment) => {
      const speaker = speakerByRole(review, segment.speakerRole);
      return Object.assign({}, segment, {
        speakerName: speaker ? speaker.label : segment.speakerName,
      });
    });
    return base;
  }

  function applyToCanvas(canvasDoc, review) {
    const doc = clone(canvasDoc || {});
    if (!review || !review.approved) {
      return doc;
    }
    if (typeof doc.captionText === "string") {
      doc.captionText = applyReplacements(doc.captionText, review.replacements);
      const captionLine = (review.lines || []).find((line) => line.kind === "caption");
      if (captionLine) {
        doc.captionText = captionLine.text;
      }
    }
    if (typeof doc.titleText === "string") {
      doc.titleText = applyReplacements(doc.titleText, review.replacements);
      const titleLine = (review.lines || []).find((line) => line.kind === "title");
      if (titleLine) {
        doc.titleText = titleLine.text;
      }
    }
    if (Array.isArray(doc.speakerFrames)) {
      doc.speakerFrames = doc.speakerFrames.map((frame) => {
        const speaker = speakerByRole(review, frame.role);
        return speaker ? Object.assign({}, frame, { name: speaker.label }) : frame;
      });
    }
    return doc;
  }

  function applyToPublishPackage(publishPackage, review) {
    const pkg = clone(publishPackage || {});
    if (!review || !review.approved) {
      return pkg;
    }
    const titleLine = (review.lines || []).find((line) => line.kind === "title");
    if (titleLine && titleLine.text) {
      pkg.title = titleLine.text;
    } else if (pkg.title) {
      pkg.title = applyReplacements(pkg.title, review.replacements);
    }
    if (pkg.description) {
      pkg.description = applyReplacements(pkg.description, review.replacements);
    }
    if (Array.isArray(pkg.speakerCredits)) {
      pkg.speakerCredits = pkg.speakerCredits.map((credit) => {
        const speaker = speakerByRole(review, credit.role);
        if (!speaker) {
          return credit;
        }
        return Object.assign({}, credit, {
          name: speaker.label,
          creditLine: `${speaker.label} · ${credit.role}`,
        });
      });
    }
    if (Array.isArray(pkg.chapters)) {
      pkg.chapters = pkg.chapters.map((chapter) => Object.assign({}, chapter, {
        label: applyReplacements(chapter.label, review.replacements),
      }));
    }
    return pkg;
  }

  function applyToDraftSpeakers(speakers, review) {
    const list = Array.isArray(speakers) ? clone(speakers) : [];
    if (!review || !review.approved) {
      return list;
    }
    return list.map((speaker) => {
      const corrected = speakerByRole(review, speaker.role);
      return corrected ? Object.assign({}, speaker, { name: corrected.label }) : speaker;
    });
  }

  function applyCorrectionReview(review, targets) {
    const t = targets || {};
    return {
      momentsBoard: applyToMoments(t.momentsBoard, review),
      canvasDoc: applyToCanvas(t.canvasDoc, review),
      publishPackage: applyToPublishPackage(t.publishPackage, review),
      speakers: applyToDraftSpeakers(t.speakers, review),
    };
  }

  function summarizeCorrection(review) {
    const lines = review && Array.isArray(review.lines) ? review.lines : [];
    const changed = lines.filter((line) => line.text && line.originalText && line.text !== line.originalText);
    const speakers = review && Array.isArray(review.speakers) ? review.speakers : [];
    const summaryLines = [];
    if (review && review.approved) {
      summaryLines.push(`Transcript corrections: ${changed.length} line${changed.length === 1 ? "" : "s"} updated`);
      if (speakers.length) {
        summaryLines.push(`Speaker labels: ${speakers.map((speaker) => speaker.label).join(" · ")}`);
      }
    }
    return {
      approved: Boolean(review && review.approved),
      changedLineCount: changed.length,
      reviewLine: summaryLines.join(" · "),
      lines: summaryLines,
    };
  }

  function serializeCorrection(review) {
    return JSON.stringify(review || null);
  }

  function deserializeCorrection(json, episodeSummary, options) {
    if (!json) {
      return createCorrectionReview(episodeSummary, options);
    }
    try {
      const parsed = typeof json === "string" ? JSON.parse(json) : json;
      if (!parsed || typeof parsed !== "object") {
        return createCorrectionReview(episodeSummary, options);
      }
      const base = createCorrectionReview(episodeSummary, options);
      return Object.assign(base, parsed, {
        speakers: Array.isArray(parsed.speakers) ? parsed.speakers : base.speakers,
        lines: Array.isArray(parsed.lines) ? parsed.lines : base.lines,
        replacements: Array.isArray(parsed.replacements) ? parsed.replacements : base.replacements,
      });
    } catch (err) {
      return createCorrectionReview(episodeSummary, options);
    }
  }

  const api = {
    createCorrectionReview,
    updateSpeaker,
    updateLine,
    approveCorrection,
    applyReplacements,
    applyToMoments,
    applyToCanvas,
    applyToPublishPackage,
    applyToDraftSpeakers,
    applyCorrectionReview,
    summarizeCorrection,
    serializeCorrection,
    deserializeCorrection,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
    return;
  }

  global.PdcTranscriptCorrection = api;
}(typeof window !== "undefined" ? window : globalThis));
