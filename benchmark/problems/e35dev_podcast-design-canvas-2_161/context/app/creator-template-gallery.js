"use strict";

// Creator template gallery for Podcast Design Canvas (#106).
//
// Lets power users publish saved show layouts as reusable gallery listings other
// shows can browse, preview, and apply. DOM-free — persistence is handled by the UI.
(function (global) {
  let listingCounter = 0;

  function templatesApi() {
    if (typeof module !== "undefined" && module.exports && typeof require === "function") {
      return require("./show-templates.js");
    }
    const g = typeof window !== "undefined" ? window : globalThis;
    return g.PdcShowTemplates;
  }

  function trim(value) {
    return typeof value === "string" ? value.trim() : "";
  }

  function createGallery() {
    return { listings: [] };
  }

  function cloneCanvas(canvas) {
    return JSON.parse(JSON.stringify(canvas));
  }

  function cloneListing(listing) {
    return Object.assign({}, listing, {
      styleTags: Array.isArray(listing.styleTags) ? listing.styleTags.slice() : [],
      previewImage: Object.assign({}, listing.previewImage || {}),
      canvas: cloneCanvas(listing.canvas),
    });
  }

  function normalizeName(name) {
    return trim(name);
  }

  function normalizeTags(tags) {
    if (Array.isArray(tags)) {
      return tags.map((tag) => trim(tag)).filter(Boolean);
    }
    if (typeof tags === "string") {
      return tags.split(/[,;]+/).map((tag) => trim(tag)).filter(Boolean);
    }
    return [];
  }

  function buildPreviewImage(canvas) {
    if (!canvas) {
      return {
        background: "#10131f",
        accent: "#6c4cff",
        layoutId: "grid",
        presetName: "Custom",
        titleText: "",
        captionText: "",
      };
    }
    return {
      background: canvas.background || "#10131f",
      accent: canvas.accent || "#6c4cff",
      layoutId: canvas.layoutId || "grid",
      presetName: canvas.presetName || "Custom",
      titleText: canvas.titleText || "",
      captionText: canvas.captionText || "",
      presetId: canvas.presetId || "",
    };
  }

  const INTERNAL_STYLE_TAGS = new Set(["creator-share"]);

  function deriveStyleTags(canvas) {
    const tags = [];
    if (!canvas) {
      return tags;
    }
    if (canvas.presetName) {
      tags.push(canvas.presetName.toLowerCase().replace(/\s+/g, "-"));
    }
    if (canvas.layoutId) {
      tags.push(canvas.layoutId);
    }
    if (canvas.pacingId) {
      tags.push(canvas.pacingId);
    }
    if (canvas.presetId) {
      tags.push(canvas.presetId);
    }
    return [...new Set(tags)];
  }

  function formatStyleTag(tag) {
    const trimmed = trim(tag);
    if (!trimmed || INTERNAL_STYLE_TAGS.has(trimmed)) {
      return null;
    }
    if (/^[a-z0-9]+[-_][a-z0-9_-]+$/i.test(trimmed)) {
      return trimmed
        .split(/[-_]+/)
        .filter(Boolean)
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join(" ");
    }
    return trimmed.charAt(0).toUpperCase() + trimmed.slice(1);
  }

  function displayStyleTags(tags) {
    const list = Array.isArray(tags) ? tags : [];
    const seen = new Set();
    const formatted = [];
    list.forEach((tag) => {
      const label = formatStyleTag(tag);
      if (!label) {
        return;
      }
      const key = label.toLowerCase();
      if (seen.has(key)) {
        return;
      }
      seen.add(key);
      formatted.push(label);
    });
    return formatted;
  }

  function validateListingName(gallery, name, excludeId) {
    const trimmed = normalizeName(name);
    if (!trimmed) {
      return { ok: false, error: "Give your gallery template a name." };
    }
    const list = gallery && Array.isArray(gallery.listings) ? gallery.listings : [];
    const duplicate = list.find(
      (listing) => listing.name.toLowerCase() === trimmed.toLowerCase() && listing.id !== excludeId,
    );
    if (duplicate) {
      return { ok: false, error: "A gallery template with that name already exists." };
    }
    return { ok: true, name: trimmed };
  }

  function createListing(meta, canvas, id) {
    listingCounter += 1;
    const previewImage = meta.previewImage || buildPreviewImage(canvas);
    return {
      id: id || `gal-${listingCounter}`,
      name: normalizeName(meta.name),
      description: trim(meta.description),
      styleTags: normalizeTags(meta.styleTags !== undefined ? meta.styleTags : deriveStyleTags(canvas)),
      previewImage,
      canvas: cloneCanvas(canvas),
      sourceTemplateId: meta.sourceTemplateId || null,
      creatorName: trim(meta.creatorName) || "Creator",
      publishedAt: Date.now(),
    };
  }

  function saveListing(gallery, listing) {
    const next = createGallery();
    const existing = gallery && Array.isArray(gallery.listings) ? gallery.listings : [];
    next.listings = existing.slice();
    const index = next.listings.findIndex((item) => item.id === listing.id);
    if (index >= 0) {
      next.listings[index] = cloneListing(listing);
    } else {
      next.listings.push(cloneListing(listing));
    }
    next.listings.sort((a, b) => a.name.localeCompare(b.name));
    return next;
  }

  function publishListing(gallery, template, meta) {
    if (!template || !template.canvas) {
      return gallery || createGallery();
    }
    const listingMeta = Object.assign({}, meta || {}, {
      sourceTemplateId: (meta && meta.sourceTemplateId) || template.id || null,
    });
    const listing = createListing(listingMeta, template.canvas);
    return saveListing(gallery, listing);
  }

  function listListings(gallery) {
    const list = gallery && Array.isArray(gallery.listings) ? gallery.listings : [];
    return list.map((listing) => ({
      id: listing.id,
      name: listing.name,
      description: listing.description,
      styleTags: Array.isArray(listing.styleTags) ? listing.styleTags.slice() : [],
      previewImage: Object.assign({}, listing.previewImage || {}),
      creatorName: listing.creatorName,
      publishedAt: listing.publishedAt,
      presetName: listing.previewImage && listing.previewImage.presetName,
      sourceTemplateId: listing.sourceTemplateId,
    }));
  }

  function getListing(gallery, id) {
    const list = gallery && Array.isArray(gallery.listings) ? gallery.listings : [];
    const found = list.find((listing) => listing.id === id);
    if (!found) {
      return null;
    }
    return cloneListing(found);
  }

  function applyListingForEpisode(listing, episodeSummary, styleSelection) {
    const TM = templatesApi();
    if (!TM || !listing || !listing.canvas) {
      return null;
    }
    return TM.applyTemplateForEpisode({ canvas: listing.canvas }, episodeSummary, styleSelection);
  }

  function styleSelectionFromListing(listing) {
    const TM = templatesApi();
    if (!TM || !listing) {
      return null;
    }
    return TM.styleSelectionFromCanvas(listing.canvas);
  }

  function serializeGallery(gallery) {
    return JSON.stringify(gallery || createGallery());
  }

  function deserializeGallery(json) {
    if (!json) {
      return createGallery();
    }
    try {
      const parsed = JSON.parse(json);
      if (!parsed || !Array.isArray(parsed.listings)) {
        return createGallery();
      }
      return { listings: parsed.listings };
    } catch (err) {
      return createGallery();
    }
  }

  function _resetListingCounter() {
    listingCounter = 0;
  }

  const api = {
    createGallery,
    buildPreviewImage,
    deriveStyleTags,
    formatStyleTag,
    displayStyleTags,
    validateListingName,
    createListing,
    saveListing,
    publishListing,
    listListings,
    getListing,
    applyListingForEpisode,
    styleSelectionFromListing,
    serializeGallery,
    deserializeGallery,
    _resetListingCounter,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
    return;
  }

  global.PdcCreatorGallery = api;
}(typeof window !== "undefined" ? window : globalThis));
