"use strict";

// Visual moments editor model for Podcast Design Canvas (#19).
//
// The contextual editing layer that turns a long-form recording into a deliberately
// produced episode: a speaker-aware, transcript-style timeline where creators place
// captions, title moments, b-roll overlays, branded callouts, and overlay notes at key
// points, then preview how each moment changes the on-screen look. DOM-free on purpose so
// the same rules drive the screen and the tests. No build step, no dependencies.
(function (global) {
  // The moment treatments a creator can place across the episode. Each carries a creator
  // facing label and a description of how it reads on screen — no pipeline jargon.
  const MOMENT_TYPES = [
    {
      id: "caption",
      label: "Caption",
      defaultText: "Add a caption line",
      treatment: "Lower-third caption",
      onScreen: true,
    },
    {
      id: "title",
      label: "Title moment",
      defaultText: "Section title",
      treatment: "Full-width title card",
      onScreen: true,
    },
    {
      id: "broll",
      label: "B-roll overlay",
      defaultText: "Describe the b-roll footage",
      treatment: "B-roll fills the frame",
      onScreen: true,
    },
    {
      id: "callout",
      label: "Visual callout",
      defaultText: "Key point to highlight",
      treatment: "Highlighted callout badge",
      onScreen: true,
    },
    {
      id: "note",
      label: "Overlay note",
      defaultText: "Note for this moment",
      treatment: "Director note (off-screen)",
      onScreen: false,
    },
  ];

  function trim(value) {
    return typeof value === "string" ? value.trim() : "";
  }

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function getType(id) {
    return MOMENT_TYPES.find((type) => type.id === id) || MOMENT_TYPES[0];
  }

  function pad2(n) {
    return n < 10 ? `0${n}` : String(n);
  }

  function formatTime(totalSeconds) {
    const safe = Math.max(0, Math.floor(totalSeconds || 0));
    const minutes = Math.floor(safe / 60);
    const seconds = safe % 60;
    return `${minutes}:${pad2(seconds)}`;
  }

  // Accept creator input like "1:30", "90", or "  2:05 " and normalize to "M:SS". Invalid
  // input clamps to 0:00 rather than throwing, so the timeline can never break.
  function parseTime(value) {
    if (typeof value === "number" && isFinite(value)) {
      return Math.max(0, Math.floor(value));
    }
    const text = trim(value);
    if (!text) {
      return 0;
    }
    if (text.indexOf(":") >= 0) {
      const parts = text.split(":");
      const minutes = parseInt(parts[0], 10) || 0;
      const seconds = parseInt(parts[1], 10) || 0;
      return Math.max(0, minutes * 60 + Math.min(59, Math.max(0, seconds)));
    }
    const asSeconds = parseInt(text, 10);
    return isFinite(asSeconds) ? Math.max(0, asSeconds) : 0;
  }

  function normalizeTime(value) {
    return formatTime(parseTime(value));
  }

  // Build a speaker-aware, transcript-style scaffold for the full episode. Segments cycle
  // through the real assigned speakers and are spaced evenly, giving creators meaningful
  // anchor points to attach moments to without a real transcript yet.
  function buildTranscript(episodeSummary, segmentCount) {
    const speakers = episodeSummary && Array.isArray(episodeSummary.speakers)
      ? episodeSummary.speakers
      : [];
    const count = typeof segmentCount === "number" && segmentCount > 0 ? segmentCount : 6;
    const spacingSeconds = 90;
    const segments = [];
    for (let i = 0; i < count; i += 1) {
      const speaker = speakers.length ? speakers[i % speakers.length] : null;
      segments.push({
        index: i,
        seconds: i * spacingSeconds,
        time: formatTime(i * spacingSeconds),
        speakerRole: (speaker && speaker.role) || "All speakers",
        speakerName: (speaker && speaker.name) || "Conversation",
      });
    }
    return segments;
  }

  function speakerOptions(episodeSummary) {
    const speakers = episodeSummary && Array.isArray(episodeSummary.speakers)
      ? episodeSummary.speakers
      : [];
    const options = [{ role: "All speakers", name: "All speakers" }];
    speakers.forEach((speaker) => {
      options.push({
        role: (speaker && speaker.role) || "Speaker",
        name: (speaker && speaker.name) || "Unnamed speaker",
      });
    });
    return options;
  }

  // A fresh moments board for an episode. Holds the transcript scaffold and the ordered
  // list of placed moments. `seq` keeps moment ids stable and unique within the board.
  function createBoard(episodeSummary) {
    const episode = episodeSummary || {};
    return {
      seq: 0,
      episodeName: trim(episode.episodeName),
      transcript: buildTranscript(episode),
      moments: [],
    };
  }

  function sortMoments(moments) {
    return moments
      .slice()
      .sort((a, b) => (a.seconds - b.seconds) || (a.order - b.order));
  }

  // Place a new moment of the given type. `opts` may set time, text, speaker, and an order
  // hint. Returns a new board with the moment inserted in timeline order.
  function addMoment(board, typeId, opts) {
    const base = board && typeof board === "object" ? board : createBoard({});
    const type = getType(typeId);
    const options = opts || {};
    const seq = (typeof base.seq === "number" ? base.seq : 0) + 1;
    const seconds = parseTime(options.time != null ? options.time : 0);
    const moment = {
      id: `moment-${seq}`,
      order: seq,
      type: type.id,
      typeLabel: type.label,
      text: trim(options.text) || type.defaultText,
      seconds,
      time: formatTime(seconds),
      speakerRole: trim(options.speakerRole) || "All speakers",
      speakerName: trim(options.speakerName) || "All speakers",
      visible: options.visible === false ? false : true,
    };
    const moments = sortMoments((Array.isArray(base.moments) ? base.moments : []).concat(moment));
    return Object.assign({}, base, { seq, moments });
  }

  // Immutable edit of a single moment's timing, text, speaker, or visibility. Re-sorts when
  // timing changes so the timeline always reads top-to-bottom in episode order.
  function updateMoment(board, id, patch) {
    const base = board && typeof board === "object" ? board : createBoard({});
    const changes = patch || {};
    const moments = (Array.isArray(base.moments) ? base.moments : []).map((moment) => {
      if (moment.id !== id) {
        return moment;
      }
      const next = Object.assign({}, moment);
      if (changes.text != null) {
        next.text = trim(changes.text);
      }
      if (changes.time != null) {
        next.seconds = parseTime(changes.time);
        next.time = formatTime(next.seconds);
      }
      if (changes.speakerRole != null) {
        next.speakerRole = trim(changes.speakerRole) || "All speakers";
      }
      if (changes.speakerName != null) {
        next.speakerName = trim(changes.speakerName) || "All speakers";
      }
      if (changes.visible != null) {
        next.visible = Boolean(changes.visible);
      }
      return next;
    });
    return Object.assign({}, base, { moments: sortMoments(moments) });
  }

  function toggleMoment(board, id) {
    const moment = getMoment(board, id);
    return updateMoment(board, id, { visible: !(moment && moment.visible) });
  }

  function removeMoment(board, id) {
    const base = board && typeof board === "object" ? board : createBoard({});
    const moments = (Array.isArray(base.moments) ? base.moments : []).filter(
      (moment) => moment.id !== id,
    );
    return Object.assign({}, base, { moments });
  }

  function getMoment(board, id) {
    const moments = board && Array.isArray(board.moments) ? board.moments : [];
    return moments.find((moment) => moment.id === id) || null;
  }

  function listMoments(board) {
    return board && Array.isArray(board.moments) ? sortMoments(board.moments) : [];
  }

  // How a single moment reads on the episode look — used by the editor's live preview so
  // creators see the effect of a moment before committing to it.
  function previewMoment(board, id) {
    const moment = getMoment(board, id);
    if (!moment) {
      return null;
    }
    const type = getType(moment.type);
    const speakerLabel = moment.speakerRole === "All speakers"
      ? "the whole conversation"
      : `${moment.speakerRole}${moment.speakerName && moment.speakerName !== moment.speakerRole ? ` (${moment.speakerName})` : ""}`;
    return {
      id: moment.id,
      type: moment.type,
      typeLabel: type.label,
      treatment: type.treatment,
      onScreen: type.onScreen,
      time: moment.time,
      text: moment.text,
      speakerLabel,
      visible: moment.visible,
      effect: moment.visible
        ? `${type.treatment} over ${speakerLabel} at ${moment.time}.`
        : `${type.label} hidden — it will not appear in the episode.`,
    };
  }

  function countsByType(board) {
    const counts = {};
    MOMENT_TYPES.forEach((type) => {
      counts[type.id] = 0;
    });
    listMoments(board).forEach((moment) => {
      counts[moment.type] = (counts[moment.type] || 0) + 1;
    });
    return counts;
  }

  function summarizeBoard(board) {
    const moments = listMoments(board);
    const visible = moments.filter((moment) => moment.visible);
    const counts = countsByType(board);
    const lines = MOMENT_TYPES
      .filter((type) => counts[type.id] > 0)
      .map((type) => `${type.label}: ${counts[type.id]}`);
    return {
      total: moments.length,
      visibleCount: visible.length,
      counts,
      lines,
      reviewLine: moments.length
        ? `Visual moments: ${visible.length} of ${moments.length} live${lines.length ? ` (${lines.join(", ")})` : ""}`
        : "",
    };
  }

  // Persistence is handled by the UI (localStorage); these mirror the show-template store.
  function serializeBoard(board) {
    return JSON.stringify(board || createBoard({}));
  }

  function deserializeBoard(json, episodeSummary) {
    if (!json) {
      return createBoard(episodeSummary || {});
    }
    try {
      const parsed = JSON.parse(json);
      if (!parsed || !Array.isArray(parsed.moments)) {
        return createBoard(episodeSummary || {});
      }
      // Refresh the transcript scaffold from the current episode while keeping moments.
      const board = createBoard(episodeSummary || { episodeName: parsed.episodeName });
      board.seq = typeof parsed.seq === "number" ? parsed.seq : parsed.moments.length;
      board.moments = sortMoments(parsed.moments.map((moment) => clone(moment)));
      return board;
    } catch (err) {
      return createBoard(episodeSummary || {});
    }
  }

  const api = {
    MOMENT_TYPES,
    getType,
    formatTime,
    parseTime,
    normalizeTime,
    buildTranscript,
    speakerOptions,
    createBoard,
    addMoment,
    updateMoment,
    toggleMoment,
    removeMoment,
    getMoment,
    listMoments,
    previewMoment,
    countsByType,
    summarizeBoard,
    serializeBoard,
    deserializeBoard,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
    return;
  }

  global.PdcVisualMoments = api;
}(typeof window !== "undefined" ? window : globalThis));