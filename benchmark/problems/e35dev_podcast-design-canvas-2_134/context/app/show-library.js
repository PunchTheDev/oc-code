"use strict";

// Show library dashboard for Podcast Design Canvas (#47).
//
// Manages a collection of named shows, each with a saved template/style identity
// and a list of episodes. Creators can start a new episode from a show template,
// review episode status, and keep multiple podcast identities separated.
// DOM-free so the library screen and tests share one source of truth.
(function (global) {
  const EPISODE_STATUS = {
    DRAFT: "draft",
    IN_PROGRESS: "in-progress",
    REVIEW: "review",
    EXPORTED: "exported",
  };

  let showCounter = 0;
  let episodeCounter = 0;

  function trim(value) {
    return typeof value === "string" ? value.trim() : "";
  }

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function createLibrary() {
    return { shows: [] };
  }

  function createShow(name, options) {
    showCounter += 1;
    const opts = options || {};
    return {
      id: opts.id || `show-${showCounter}`,
      name: trim(name) || "Untitled Show",
      description: trim(opts.description),
      templateId: opts.templateId || "",
      templateName: opts.templateName || "",
      presetName: opts.presetName || "",
      brandKit: opts.brandKit || null,
      defaultSourceMode: opts.defaultSourceMode || "",
      defaultRiversideLink: opts.defaultRiversideLink || "",
      defaultSpeakers: Array.isArray(opts.defaultSpeakers) ? clone(opts.defaultSpeakers) : [],
      createdAt: opts.createdAt || Date.now(),
      episodes: [],
    };
  }

  function validateShowName(library, name, excludeId) {
    const trimmed = trim(name);
    if (!trimmed) {
      return { ok: false, error: "Give your show a name." };
    }
    const list = library && Array.isArray(library.shows) ? library.shows : [];
    const duplicate = list.find(
      (show) => show.name.toLowerCase() === trimmed.toLowerCase() && show.id !== excludeId,
    );
    if (duplicate) {
      return { ok: false, error: "A show with that name already exists." };
    }
    return { ok: true, name: trimmed };
  }

  function addShow(library, show) {
    const next = clone(library || createLibrary());
    next.shows = (next.shows || []).concat(clone(show));
    next.shows.sort(function (a, b) { return a.name.localeCompare(b.name); });
    return next;
  }

  function updateShow(library, showId, patch) {
    const next = clone(library || createLibrary());
    next.shows = (next.shows || []).map(function (show) {
      if (show.id !== showId) return show;
      return Object.assign({}, show, patch);
    });
    return next;
  }

  function getShow(library, showId) {
    const list = library && Array.isArray(library.shows) ? library.shows : [];
    const found = list.find(function (show) { return show.id === showId; });
    return found ? clone(found) : null;
  }

  function listShows(library) {
    const list = library && Array.isArray(library.shows) ? library.shows : [];
    return list.map(function (show) {
      return {
        id: show.id,
        name: show.name,
        description: show.description || "",
        templateId: show.templateId || "",
        templateName: show.templateName || "",
        presetName: show.presetName || "",
        brandKit: show.brandKit ? clone(show.brandKit) : null,
        episodeCount: Array.isArray(show.episodes) ? show.episodes.length : 0,
        latestEpisode: latestEpisodeSummary(show.episodes),
        createdAt: show.createdAt,
      };
    });
  }

  function latestEpisodeSummary(episodes) {
    const list = Array.isArray(episodes) ? episodes : [];
    if (!list.length) return null;
    const sorted = list.slice().sort(function (a, b) { return (b.createdAt || 0) - (a.createdAt || 0); });
    const ep = sorted[0];
    return { id: ep.id, name: ep.name, status: ep.status, createdAt: ep.createdAt };
  }

  function createEpisode(showId, name, options) {
    episodeCounter += 1;
    const opts = options || {};
    return {
      id: opts.id || `ep-${episodeCounter}`,
      showId: showId,
      name: trim(name) || "Untitled Episode",
      status: opts.status || EPISODE_STATUS.DRAFT,
      templateId: opts.templateId || "",
      templateName: opts.templateName || "",
      presetName: opts.presetName || "",
      speakerRoles: Array.isArray(opts.speakerRoles) ? opts.speakerRoles : [],
      createdAt: opts.createdAt || Date.now(),
      updatedAt: opts.updatedAt || opts.createdAt || Date.now(),
      exportedAt: opts.exportedAt || null,
      downloadName: opts.downloadName || "",
    };
  }

  function addEpisode(library, showId, episode) {
    const next = clone(library || createLibrary());
    next.shows = (next.shows || []).map(function (show) {
      if (show.id !== showId) return show;
      const updated = clone(show);
      updated.episodes = (Array.isArray(updated.episodes) ? updated.episodes : []).concat(clone(episode));
      return updated;
    });
    return next;
  }

  function updateEpisode(library, showId, episodeId, patch) {
    const next = clone(library || createLibrary());
    next.shows = (next.shows || []).map(function (show) {
      if (show.id !== showId) return show;
      const updated = clone(show);
      updated.episodes = (Array.isArray(updated.episodes) ? updated.episodes : []).map(function (ep) {
        if (ep.id !== episodeId) return ep;
        return Object.assign({}, ep, patch);
      });
      return updated;
    });
    return next;
  }

  function listEpisodes(library, showId) {
    const show = getShow(library, showId);
    if (!show || !Array.isArray(show.episodes)) return [];
    return show.episodes.slice().sort(function (a, b) { return (b.createdAt || 0) - (a.createdAt || 0); });
  }

  function episodeStatusLabel(status) {
    switch (status) {
      case EPISODE_STATUS.DRAFT: return "Draft";
      case EPISODE_STATUS.IN_PROGRESS: return "In progress";
      case EPISODE_STATUS.REVIEW: return "In review";
      case EPISODE_STATUS.EXPORTED: return "Exported";
      default: return "Draft";
    }
  }

  // Build a starter draft pre-filled with the show's template and style defaults.
  // The caller wires this into ES.createDraft() as initial state.
  function newEpisodeDraft(show) {
    const s = show || {};
    return {
      showId: s.id || "",
      showName: s.name || "",
      templateId: s.templateId || "",
      templateName: s.templateName || "",
      presetName: s.presetName || "",
      brandKit: s.brandKit ? clone(s.brandKit) : null,
      defaultSourceMode: s.defaultSourceMode || "",
      defaultSpeakers: Array.isArray(s.defaultSpeakers) ? clone(s.defaultSpeakers) : [],
      speakerRoles: Array.isArray(s.defaultSpeakers)
        ? s.defaultSpeakers.map(function (speaker) { return speaker.role; })
        : (Array.isArray(s.defaultSpeakerRoles) ? s.defaultSpeakerRoles.slice() : []),
    };
  }

  function summarizeLibrary(library) {
    const shows = listShows(library);
    const totalEpisodes = shows.reduce(function (n, s) { return n + s.episodeCount; }, 0);
    const exported = (library && Array.isArray(library.shows) ? library.shows : []).reduce(function (n, show) {
      return n + (Array.isArray(show.episodes) ? show.episodes.filter(function (ep) { return ep.status === EPISODE_STATUS.EXPORTED; }).length : 0);
    }, 0);
    return {
      showCount: shows.length,
      totalEpisodes: totalEpisodes,
      exportedCount: exported,
      libraryLine: shows.length === 0
        ? "No shows yet — create your first show to get started."
        : `${shows.length} show${shows.length === 1 ? "" : "s"} · ${totalEpisodes} episode${totalEpisodes === 1 ? "" : "s"}`,
    };
  }

  function serializeLibrary(library) {
    return JSON.stringify(library || createLibrary());
  }

  function deserializeLibrary(json) {
    if (!json) return createLibrary();
    try {
      const parsed = JSON.parse(json);
      if (!parsed || !Array.isArray(parsed.shows)) return createLibrary();
      return parsed;
    } catch (err) {
      return createLibrary();
    }
  }

  function _resetCounters() {
    showCounter = 0;
    episodeCounter = 0;
  }

  const api = {
    EPISODE_STATUS,
    createLibrary,
    createShow,
    validateShowName,
    addShow,
    updateShow,
    getShow,
    listShows,
    createEpisode,
    addEpisode,
    updateEpisode,
    listEpisodes,
    episodeStatusLabel,
    newEpisodeDraft,
    summarizeLibrary,
    serializeLibrary,
    deserializeLibrary,
    _resetCounters,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
    return;
  }

  global.PdcShowLibrary = api;
}(typeof window !== "undefined" ? window : globalThis));
