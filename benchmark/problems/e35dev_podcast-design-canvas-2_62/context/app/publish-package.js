"use strict";

// Publish package builder for Podcast Design Canvas (#60).
//
// Turns an approved episode into creator-editable publishing assets: title,
// description, chapter markers, speaker credits, and branded thumbnail options.
// DOM-free so the publish package screen, export summary, and tests share one model.
(function (global) {
  function trim(value) {
    return typeof value === "string" ? value.trim() : "";
  }

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function momentsApi() {
    if (typeof module !== "undefined" && module.exports && typeof require === "function") {
      return require("./visual-moments.js");
    }
    const g = typeof window !== "undefined" ? window : globalThis;
    return g.PdcVisualMoments;
  }

  function brandKitApi() {
    if (typeof module !== "undefined" && module.exports && typeof require === "function") {
      return require("./show-brand-kit.js");
    }
    const g = typeof window !== "undefined" ? window : globalThis;
    return g.PdcShowBrandKit;
  }

  function defaultBrandColors() {
    return {
      primary: "#6c4cff",
      secondary: "#10131f",
      background: "#10131f",
      accent: "#ffb347",
      text: "#f6f7fb",
    };
  }

  function brandColorsFromContext(context) {
    const ctx = context || {};
    const kit = ctx.brandKit || (ctx.brandKitSummary && ctx.brandKitSummary.showId ? null : null);
    if (kit && kit.colors) {
      return Object.assign({}, defaultBrandColors(), kit.colors);
    }
    if (ctx.appliedStyle) {
      return {
        primary: ctx.appliedStyle.accent || defaultBrandColors().primary,
        secondary: ctx.appliedStyle.surface || defaultBrandColors().secondary,
        background: ctx.appliedStyle.background || defaultBrandColors().background,
        accent: ctx.appliedStyle.accent || defaultBrandColors().accent,
        text: ctx.appliedStyle.textColor || defaultBrandColors().text,
      };
    }
    return defaultBrandColors();
  }

  function buildSpeakerCredits(episodeSummary) {
    const episode = episodeSummary || {};
    const speakers = Array.isArray(episode.speakers) ? episode.speakers : [];
    return speakers.map((speaker, index) => ({
      id: `credit-${index + 1}`,
      role: speaker.role || "",
      name: speaker.name || "",
      creditLine: speaker.name && speaker.role
        ? `${speaker.name} · ${speaker.role}`
        : (speaker.name || speaker.role || "Speaker"),
    }));
  }

  function buildChapters(momentsBoard) {
    const VM = momentsApi();
    const chapters = [{ id: "chapter-intro", time: "0:00", label: "Intro" }];
    if (!VM || !momentsBoard) {
      return chapters;
    }
    VM.listMoments(momentsBoard)
      .filter((moment) => moment.visible !== false)
      .forEach((moment) => {
        if (moment.type === "title" || moment.type === "caption" || moment.type === "callout") {
          chapters.push({
            id: moment.id,
            time: moment.time,
            label: trim(moment.text) || moment.typeLabel,
          });
        }
      });
    return chapters;
  }

  function buildDescription(episodeSummary, context) {
    const episode = episodeSummary || {};
    const ctx = context || {};
    const names = (episode.speakers || []).map((speaker) => speaker.name).filter(Boolean);
    const showName = trim(ctx.showName) || trim(episode.episodeName) || "This episode";
    const speakerLine = names.length
      ? `Featuring ${names.join(", ")}.`
      : "";
    const styleLine = ctx.appliedStyle && ctx.appliedStyle.presetName
      ? `Visual style: ${ctx.appliedStyle.presetName}.`
      : "";
    return [showName, speakerLine, styleLine, "Edit this description before you publish."]
      .filter(Boolean)
      .join(" ");
  }

  function buildThumbnailOptions(episodeSummary, context) {
    const episode = episodeSummary || {};
    const ctx = context || {};
    const colors = brandColorsFromContext(ctx);
    const BK = brandKitApi();
    const logoLabel = ctx.brandKit && ctx.brandKit.logoLabel
      ? ctx.brandKit.logoLabel
      : (ctx.brandKitSummary && ctx.brandKitSummary.logoLabel) || "";
    const title = trim(episode.episodeName) || "Episode";
    const typeLabel = BK && ctx.brandKit
      ? ctx.brandKit.typeStyleLabel
      : (ctx.brandKitSummary && ctx.brandKitSummary.typeStyleLabel) || "";

    return [
      {
        id: "thumb-spotlight",
        label: "Speaker spotlight",
        layout: "spotlight",
        background: colors.background,
        accent: colors.accent,
        text: colors.text,
        logoLabel: logoLabel,
        headline: title,
        tagline: typeLabel || "Host front and center",
      },
      {
        id: "thumb-split",
        label: "Split conversation",
        layout: "split",
        background: colors.secondary,
        accent: colors.primary,
        text: colors.text,
        logoLabel: logoLabel,
        headline: title,
        tagline: "Side-by-side speakers",
      },
      {
        id: "thumb-title-card",
        label: "Title card",
        layout: "title-card",
        background: colors.primary,
        accent: colors.accent,
        text: colors.text,
        logoLabel: logoLabel,
        headline: title,
        tagline: "Bold episode title",
      },
    ];
  }

  function createPackage(episodeSummary, context) {
    const episode = episodeSummary || {};
    const ctx = context || {};
    const thumbnails = buildThumbnailOptions(episode, ctx);
    return {
      title: trim(episode.episodeName) || "Untitled episode",
      description: buildDescription(episode, ctx),
      chapters: buildChapters(ctx.momentsBoard),
      speakerCredits: buildSpeakerCredits(episode),
      thumbnailOptions: thumbnails,
      selectedThumbnailId: thumbnails[0] ? thumbnails[0].id : "",
      updatedAt: Date.now(),
    };
  }

  function updatePackage(pkg, patch) {
    const next = clone(pkg || createPackage({}, {}));
    const p = patch || {};
    if (p.title != null) next.title = trim(p.title);
    if (p.description != null) next.description = trim(p.description);
    if (p.selectedThumbnailId != null) next.selectedThumbnailId = trim(p.selectedThumbnailId);
    if (Array.isArray(p.chapters)) next.chapters = clone(p.chapters);
    if (Array.isArray(p.speakerCredits)) next.speakerCredits = clone(p.speakerCredits);
    next.updatedAt = Date.now();
    return next;
  }

  function updateChapter(pkg, chapterId, patch) {
    const next = clone(pkg || createPackage({}, {}));
    next.chapters = (next.chapters || []).map((chapter) => {
      if (chapter.id !== chapterId) return chapter;
      return Object.assign({}, chapter, patch || {});
    });
    next.updatedAt = Date.now();
    return next;
  }

  function updateSpeakerCredit(pkg, creditId, patch) {
    const next = clone(pkg || createPackage({}, {}));
    next.speakerCredits = (next.speakerCredits || []).map((credit) => {
      if (credit.id !== creditId) return credit;
      const updated = Object.assign({}, credit, patch || {});
      if (patch && (patch.name != null || patch.role != null)) {
        updated.creditLine = updated.name && updated.role
          ? `${updated.name} · ${updated.role}`
          : (updated.name || updated.role || updated.creditLine);
      }
      return updated;
    });
    next.updatedAt = Date.now();
    return next;
  }

  function selectThumbnail(pkg, thumbnailId) {
    return updatePackage(pkg, { selectedThumbnailId: thumbnailId });
  }

  function getSelectedThumbnail(pkg) {
    const list = pkg && Array.isArray(pkg.thumbnailOptions) ? pkg.thumbnailOptions : [];
    return list.find((item) => item.id === pkg.selectedThumbnailId) || list[0] || null;
  }

  function summarizePackage(pkg) {
    const p = pkg || createPackage({}, {});
    const thumb = getSelectedThumbnail(p);
    const chapterCount = Array.isArray(p.chapters) ? p.chapters.length : 0;
    const creditCount = Array.isArray(p.speakerCredits) ? p.speakerCredits.length : 0;
    const lines = [];
    lines.push(`Publish title: ${p.title || "Untitled episode"}`);
    if (p.description) {
      lines.push(`Description: ${p.description}`);
    }
    if (chapterCount) {
      lines.push(`Chapters: ${chapterCount} marker${chapterCount === 1 ? "" : "s"}`);
    }
    if (creditCount) {
      lines.push(`Credits: ${p.speakerCredits.map((item) => item.creditLine).join(" · ")}`);
    }
    if (thumb) {
      lines.push(`Thumbnail: ${thumb.label}${thumb.logoLabel ? ` · ${thumb.logoLabel}` : ""}`);
    }
    return {
      title: p.title || "",
      description: p.description || "",
      chapterCount: chapterCount,
      creditCount: creditCount,
      thumbnailLabel: thumb ? thumb.label : "",
      reviewLine: lines.join(" · "),
      lines: lines,
    };
  }

  function serializePackage(pkg) {
    return JSON.stringify(pkg || null);
  }

  function deserializePackage(json, episodeSummary, context) {
    if (!json) {
      return createPackage(episodeSummary, context);
    }
    try {
      const parsed = typeof json === "string" ? JSON.parse(json) : json;
      if (!parsed || typeof parsed !== "object") {
        return createPackage(episodeSummary, context);
      }
      const base = createPackage(episodeSummary, context);
      return Object.assign(base, parsed, {
        chapters: Array.isArray(parsed.chapters) ? parsed.chapters : base.chapters,
        speakerCredits: Array.isArray(parsed.speakerCredits) ? parsed.speakerCredits : base.speakerCredits,
        thumbnailOptions: Array.isArray(parsed.thumbnailOptions) && parsed.thumbnailOptions.length >= 3
          ? parsed.thumbnailOptions
          : base.thumbnailOptions,
      });
    } catch (err) {
      return createPackage(episodeSummary, context);
    }
  }

  const api = {
    createPackage,
    updatePackage,
    updateChapter,
    updateSpeakerCredit,
    selectThumbnail,
    getSelectedThumbnail,
    buildThumbnailOptions,
    buildChapters,
    buildSpeakerCredits,
    summarizePackage,
    serializePackage,
    deserializePackage,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
    return;
  }

  global.PdcPublishPackage = api;
}(typeof window !== "undefined" ? window : globalThis));