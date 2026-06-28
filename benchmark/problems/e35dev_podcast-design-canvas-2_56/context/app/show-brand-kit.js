"use strict";

// Show brand kit model for Podcast Design Canvas (#52).
//
// Reusable visual identity per show: logo, colors, type style, caption style, and
// common overlay assets. DOM-free so the show library, style preview, workspace,
// and export summary share one source of truth.
(function (global) {
  const TYPE_STYLES = [
    { id: "modern-sans", label: "Modern sans", sample: "Aa" },
    { id: "classic-serif", label: "Classic serif", sample: "Aa" },
    { id: "bold-display", label: "Bold display", sample: "Aa" },
  ];

  const CAPTION_STYLES = [
    { id: "bold-lower-third", label: "Bold lower-third" },
    { id: "clean-bar", label: "Clean caption bar" },
    { id: "minimal-tag", label: "Minimal name tag" },
    { id: "big-animated", label: "Big animated captions" },
  ];

  const OVERLAY_KINDS = [
    { id: "lower-third", label: "Lower-third bug" },
    { id: "intro", label: "Intro card" },
    { id: "outro", label: "Outro card" },
    { id: "watermark", label: "Watermark" },
  ];

  let overlayCounter = 0;

  function trim(value) {
    return typeof value === "string" ? value.trim() : "";
  }

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function isHexColor(value) {
    return typeof value === "string" && /^#[0-9a-fA-F]{6}$/.test(value);
  }

  function getTypeStyle(id) {
    return TYPE_STYLES.find((item) => item.id === id) || TYPE_STYLES[0];
  }

  function getCaptionStyle(id) {
    return CAPTION_STYLES.find((item) => item.id === id) || CAPTION_STYLES[0];
  }

  function getOverlayKind(id) {
    return OVERLAY_KINDS.find((item) => item.id === id) || OVERLAY_KINDS[0];
  }

  function defaultColors(options) {
    const opts = options || {};
    return {
      primary: opts.primary || "#6c4cff",
      secondary: opts.secondary || "#10131f",
      background: opts.background || "#10131f",
      accent: opts.accent || "#ffb347",
      text: opts.text || "#f6f7fb",
    };
  }

  function createBrandKit(showId, options) {
    const opts = options || {};
    const typeStyle = getTypeStyle(opts.typeStyle);
    const captionStyle = getCaptionStyle(opts.captionStyle);
    return {
      showId: showId || "",
      logoLabel: trim(opts.logoLabel),
      logoUrl: trim(opts.logoUrl),
      colors: defaultColors(opts.colors),
      typeStyle: typeStyle.id,
      typeStyleLabel: typeStyle.label,
      captionStyle: captionStyle.id,
      captionStyleLabel: captionStyle.label,
      overlayAssets: Array.isArray(opts.overlayAssets) ? clone(opts.overlayAssets) : [],
      updatedAt: opts.updatedAt || Date.now(),
    };
  }

  function validateBrandKit(kit) {
    const k = kit || {};
    if (!trim(k.showId)) {
      return { ok: false, error: "Brand kit must belong to a show." };
    }
    const colors = k.colors || {};
    const colorKeys = ["primary", "secondary", "background", "accent", "text"];
    for (let i = 0; i < colorKeys.length; i += 1) {
      if (!isHexColor(colors[colorKeys[i]])) {
        return { ok: false, error: `Use a valid hex color for ${colorKeys[i]}.` };
      }
    }
    if (!getTypeStyle(k.typeStyle)) {
      return { ok: false, error: "Choose a type style." };
    }
    if (!getCaptionStyle(k.captionStyle)) {
      return { ok: false, error: "Choose a caption style." };
    }
    return { ok: true };
  }

  function updateBrandKit(kit, patch) {
    const next = clone(kit || createBrandKit(""));
    const p = patch || {};
    if (p.logoLabel != null) next.logoLabel = trim(p.logoLabel);
    if (p.logoUrl != null) next.logoUrl = trim(p.logoUrl);
    if (p.typeStyle) {
      const typeStyle = getTypeStyle(p.typeStyle);
      next.typeStyle = typeStyle.id;
      next.typeStyleLabel = typeStyle.label;
    }
    if (p.captionStyle) {
      const captionStyle = getCaptionStyle(p.captionStyle);
      next.captionStyle = captionStyle.id;
      next.captionStyleLabel = captionStyle.label;
    }
    if (p.colors) {
      next.colors = Object.assign({}, next.colors, p.colors);
    }
    if (Array.isArray(p.overlayAssets)) {
      next.overlayAssets = clone(p.overlayAssets);
    }
    next.updatedAt = Date.now();
    return next;
  }

  function addOverlayAsset(kit, name, kind) {
    overlayCounter += 1;
    const overlayKind = getOverlayKind(kind);
    const next = clone(kit || createBrandKit(""));
    next.overlayAssets = (next.overlayAssets || []).concat({
      id: `overlay-${overlayCounter}`,
      name: trim(name) || overlayKind.label,
      kind: overlayKind.id,
      kindLabel: overlayKind.label,
    });
    next.updatedAt = Date.now();
    return next;
  }

  function removeOverlayAsset(kit, overlayId) {
    const next = clone(kit || createBrandKit(""));
    next.overlayAssets = (next.overlayAssets || []).filter((item) => item.id !== overlayId);
    next.updatedAt = Date.now();
    return next;
  }

  function styleApi() {
    if (typeof module !== "undefined" && module.exports && typeof require === "function") {
      return require("./episode-style.js");
    }
    const g = typeof window !== "undefined" ? window : globalThis;
    return g.PdcEpisodeStyle;
  }

  function getPreviewTheme(preset, brandKit) {
    const STY = styleApi();
    const base = preset || (STY ? STY.getPreset("studio-spotlight") : {});
    const kit = brandKit || {};
    const colors = kit.colors || {};
    return {
      background: colors.background || base.background,
      surface: colors.secondary || base.surface,
      accent: colors.accent || base.accent,
      textColor: colors.text || base.textColor,
      primary: colors.primary || colors.accent || base.accent,
      captionStyle: kit.captionStyleLabel || base.captionStyle,
      typeStyleLabel: kit.typeStyleLabel || getTypeStyle(kit.typeStyle).label,
      logoLabel: kit.logoLabel || "",
    };
  }

  function applyToStyleSummary(appliedStyle, brandKit) {
    const style = clone(appliedStyle || {});
    const theme = getPreviewTheme(
      { background: style.background, surface: style.surface, accent: style.accent, textColor: style.textColor, captionStyle: style.captionStyle },
      brandKit,
    );
    style.background = theme.background;
    style.surface = theme.surface;
    style.accent = theme.accent;
    style.textColor = theme.textColor;
    style.captionStyle = theme.captionStyle;
    style.typeStyleLabel = theme.typeStyleLabel;
    style.brandApplied = Boolean(brandKit && brandKit.showId);
    return style;
  }

  function applyToCanvas(canvasDoc, brandKit) {
    const doc = clone(canvasDoc || {});
    const theme = getPreviewTheme(
      { background: doc.background, accent: doc.accent, textColor: doc.textColor, captionStyle: doc.captionStyle },
      brandKit,
    );
    doc.background = theme.background;
    doc.accent = theme.accent;
    doc.textColor = theme.textColor;
    doc.captionStyle = theme.captionStyle;
    if (brandKit && brandKit.logoLabel) {
      doc.brandLogoLabel = brandKit.logoLabel;
    }
    return doc;
  }

  function summarizeBrandKit(kit) {
    const k = kit || {};
    const overlays = Array.isArray(k.overlayAssets) ? k.overlayAssets : [];
    const parts = [];
    if (k.logoLabel) {
      parts.push(`Logo: ${k.logoLabel}`);
    }
    if (k.typeStyleLabel) {
      parts.push(k.typeStyleLabel);
    }
    if (k.captionStyleLabel) {
      parts.push(k.captionStyleLabel);
    }
    return {
      showId: k.showId || "",
      logoLabel: k.logoLabel || "",
      typeStyleLabel: k.typeStyleLabel || "",
      captionStyleLabel: k.captionStyleLabel || "",
      colorSummary: `${k.colors && k.colors.primary ? k.colors.primary : ""} · ${k.colors && k.colors.accent ? k.colors.accent : ""}`.replace(/^ · | · $/g, ""),
      overlayCount: overlays.length,
      identityLine: parts.length ? parts.join(" · ") : "No brand kit configured",
      reviewLine: parts.length
        ? `Brand kit: ${parts.join(" · ")}${overlays.length ? ` · ${overlays.length} overlay${overlays.length === 1 ? "" : "s"}` : ""}`
        : "",
    };
  }

  function exportSummaryLine(kit) {
    const summary = summarizeBrandKit(kit);
    return summary.reviewLine;
  }

  function serializeBrandKit(kit) {
    return JSON.stringify(kit || null);
  }

  function deserializeBrandKit(json, showId) {
    if (!json) {
      return showId ? createBrandKit(showId) : null;
    }
    try {
      const parsed = typeof json === "string" ? JSON.parse(json) : json;
      if (!parsed || typeof parsed !== "object") {
        return showId ? createBrandKit(showId) : null;
      }
      (parsed.overlayAssets || []).forEach((item) => {
        const match = /^overlay-(\d+)$/.exec(item.id || "");
        if (match) {
          overlayCounter = Math.max(overlayCounter, Number(match[1]));
        }
      });
      return createBrandKit(showId || parsed.showId, parsed);
    } catch (err) {
      return showId ? createBrandKit(showId) : null;
    }
  }

  function _resetOverlayCounter() {
    overlayCounter = 0;
  }

  const api = {
    TYPE_STYLES,
    CAPTION_STYLES,
    OVERLAY_KINDS,
    createBrandKit,
    validateBrandKit,
    updateBrandKit,
    addOverlayAsset,
    removeOverlayAsset,
    getPreviewTheme,
    applyToStyleSummary,
    applyToCanvas,
    summarizeBrandKit,
    exportSummaryLine,
    serializeBrandKit,
    deserializeBrandKit,
    getTypeStyle,
    getCaptionStyle,
    _resetOverlayCounter,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
    return;
  }

  global.PdcShowBrandKit = api;
}(typeof window !== "undefined" ? window : globalThis));