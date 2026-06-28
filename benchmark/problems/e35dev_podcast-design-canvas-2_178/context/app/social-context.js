"use strict";

// Social context review model for Podcast Design Canvas (#34).
//
// Turns optional speaker social links into creator-approved names, brands, topics, and
// spelling hints — then applies those hints to captions, title moments, callouts, and
// export summaries. Deterministic and DOM-free; no external research or pipeline jargon.
(function (global) {
  function trim(value) {
    return typeof value === "string" ? value.trim() : "";
  }

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function titleCase(value) {
    return trim(value)
      .split(/[\s-_]+/)
      .filter(Boolean)
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
      .join(" ");
  }

  function parseHostname(url) {
    const text = trim(url);
    if (!text) {
      return "";
    }
    try {
      return new URL(text).hostname.replace(/^www\./i, "");
    } catch (err) {
      const stripped = text.replace(/^https?:\/\//i, "").split(/[/?#]/)[0];
      return stripped.replace(/^www\./i, "");
    }
  }

  function brandFromWebsite(url) {
    const host = parseHostname(url);
    if (!host) {
      return "";
    }
    const parts = host.split(".").filter(Boolean);
    if (parts.length >= 2) {
      return titleCase(parts[parts.length - 2]);
    }
    return titleCase(parts[0] || "");
  }

  function handleFromSocialUrl(url) {
    const text = trim(url);
    const twitter = text.match(/(?:twitter\.com|x\.com)\/([^/?#]+)/i);
    if (twitter) {
      return titleCase(twitter[1].replace(/[_-]+/g, " "));
    }
    const linkedin = text.match(/linkedin\.com\/in\/([^/?#]+)/i);
    if (linkedin) {
      return titleCase(linkedin[1].replace(/[-_]+/g, " "));
    }
    const instagram = text.match(/instagram\.com\/([^/?#]+)/i);
    if (instagram) {
      return titleCase(instagram[1].replace(/[._-]+/g, " "));
    }
    return "";
  }

  function defaultTopics(speaker, brand) {
    const role = trim(speaker && speaker.role).toLowerCase();
    const topics = [];
    if (brand) {
      topics.push(brand);
    }
    if (role.indexOf("host") >= 0) {
      topics.push("podcasting", "conversation");
    } else if (role.indexOf("guest") >= 0) {
      topics.push("expertise", "insights");
    } else {
      topics.push("discussion");
    }
    return topics.slice(0, 3);
  }

  function spellingHints(name, socialHandle) {
    const display = trim(name);
    const hints = [];
    if (display) {
      hints.push(display);
      const parts = display.split(/\s+/).filter(Boolean);
      if (parts.length >= 2) {
        hints.push(parts.join(""));
        hints.push(`${parts[0]} ${parts[1].charAt(0)}.`);
        if (parts[1].length > 2) {
          hints.push(`${parts[0]} ${parts[1].slice(0, -1)}`);
        }
      }
    }
    if (socialHandle && socialHandle.toLowerCase() !== display.toLowerCase()) {
      hints.push(socialHandle);
    }
    const seen = {};
    return hints.filter((hint) => {
      const key = hint.toLowerCase();
      if (!hint || seen[key]) {
        return false;
      }
      seen[key] = true;
      return true;
    });
  }

  function deriveSpeakerContext(speaker) {
    const sp = speaker || {};
    const social = Array.isArray(sp.social) ? sp.social : [];
    let brand = "";
    let socialHandle = "";
    social.forEach((link) => {
      if (!link || !link.url) {
        return;
      }
      if (link.key === "website" && !brand) {
        brand = brandFromWebsite(link.url);
      }
      if (!socialHandle) {
        socialHandle = handleFromSocialUrl(link.url);
      }
    });
    const displayName = trim(sp.name) || socialHandle || "Unnamed speaker";
    return {
      role: trim(sp.role) || "Speaker",
      displayName: displayName,
      brand: brand,
      topics: defaultTopics(sp, brand),
      spellingHints: spellingHints(displayName, socialHandle),
      socialLinkCount: social.length,
      approved: false,
    };
  }

  function createReview(episodeSummary) {
    const episode = episodeSummary || {};
    const speakers = Array.isArray(episode.speakers) ? episode.speakers : [];
    return {
      episodeName: trim(episode.episodeName),
      approved: false,
      speakers: speakers.map((speaker) => deriveSpeakerContext(speaker)),
    };
  }

  function updateSpeaker(review, index, patch) {
    const next = clone(review || createReview({}));
    if (!Array.isArray(next.speakers) || index < 0 || index >= next.speakers.length) {
      return next;
    }
    const current = next.speakers[index];
    const changes = patch || {};
    const updated = Object.assign({}, current);
    if (changes.displayName != null) {
      updated.displayName = trim(changes.displayName);
    }
    if (changes.brand != null) {
      updated.brand = trim(changes.brand);
    }
    if (changes.topics != null) {
      if (Array.isArray(changes.topics)) {
        updated.topics = changes.topics.map(trim).filter(Boolean).slice(0, 5);
      } else if (typeof changes.topics === "string") {
        updated.topics = changes.topics.split(",").map(trim).filter(Boolean).slice(0, 5);
      }
    }
    if (changes.spellingHints != null) {
      if (Array.isArray(changes.spellingHints)) {
        updated.spellingHints = changes.spellingHints.map(trim).filter(Boolean);
      } else if (typeof changes.spellingHints === "string") {
        updated.spellingHints = changes.spellingHints.split(",").map(trim).filter(Boolean);
      }
    }
    if (changes.approved != null) {
      updated.approved = Boolean(changes.approved);
    }
    next.speakers[index] = updated;
    next.approved = next.speakers.every((speaker) => speaker.approved);
    return next;
  }

  function approveReview(review) {
    const next = clone(review || createReview({}));
    next.speakers = (next.speakers || []).map((speaker) => Object.assign({}, speaker, { approved: true }));
    next.approved = next.speakers.length > 0;
    return next;
  }

  function findSpeakerContext(review, speakerRole, speakerName) {
    const speakers = review && Array.isArray(review.speakers) ? review.speakers : [];
    const byRole = speakers.find((entry) => entry.role === speakerRole);
    if (byRole) {
      return byRole;
    }
    const byName = speakers.find((entry) => entry.displayName === speakerName);
    return byName || null;
  }

  function escapeRegExp(text) {
    return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function applyHintsToText(text, review, speakerRole, speakerName) {
    const original = trim(text);
    if (!original || !review || !review.approved) {
      return original;
    }
    const ctx = findSpeakerContext(review, speakerRole, speakerName);
    if (!ctx) {
      return original;
    }
    let next = original;
    ctx.spellingHints.forEach((hint) => {
      if (!hint || hint.toLowerCase() === ctx.displayName.toLowerCase()) {
        return;
      }
      next = next.replace(new RegExp(escapeRegExp(hint), "gi"), ctx.displayName);
    });
    return next;
  }

  function enrichMomentText(moment, review) {
    if (!moment || !review || !review.approved) {
      return moment;
    }
    const ctx = findSpeakerContext(review, moment.speakerRole, moment.speakerName);
    if (!ctx) {
      return moment;
    }
    let text = applyHintsToText(moment.text, review, moment.speakerRole, moment.speakerName);
    if (moment.type === "callout" && ctx.brand && text.indexOf(ctx.brand) < 0) {
      text = `${text} · ${ctx.brand}`;
    }
    if (moment.type === "caption" && text.indexOf(ctx.displayName) < 0 && moment.speakerRole !== "All speakers") {
      text = `${ctx.displayName}: ${text}`;
    }
    if (moment.type === "title" && ctx.topics.length && text.indexOf(ctx.topics[0]) < 0) {
      text = `${text} — ${ctx.topics[0]}`;
    }
    return Object.assign({}, moment, { text: text });
  }

  function applyReviewToMoments(board, review) {
    const base = board && typeof board === "object" ? clone(board) : { moments: [] };
    if (!review || !review.approved) {
      return base;
    }
    base.moments = (Array.isArray(base.moments) ? base.moments : []).map((moment) => enrichMomentText(moment, review));
    return base;
  }

  function applyReviewToCanvas(canvasDoc, review) {
    const doc = clone(canvasDoc || {});
    if (!review || !review.approved) {
      return doc;
    }
    if (typeof doc.titleText === "string") {
      doc.titleText = applyHintsToText(doc.titleText, review, "Host", doc.titleText);
    }
    if (typeof doc.captionText === "string") {
      const host = review.speakers && review.speakers.find((s) => s.role === "Host");
      doc.captionText = applyHintsToText(
        doc.captionText,
        review,
        host ? host.role : "Host",
        host ? host.displayName : "",
      );
    }
    if (Array.isArray(doc.speakerFrames)) {
      doc.speakerFrames = doc.speakerFrames.map((frame) => {
        const ctx = findSpeakerContext(review, frame.role, frame.name);
        if (!ctx) {
          return frame;
        }
        return Object.assign({}, frame, { name: ctx.displayName });
      });
    }
    return doc;
  }

  function summarizeReview(review) {
    const speakers = review && Array.isArray(review.speakers) ? review.speakers : [];
    const approvedCount = speakers.filter((speaker) => speaker.approved).length;
    const withSocial = speakers.filter((speaker) => speaker.socialLinkCount > 0).length;
    const topicPreview = speakers
      .filter((speaker) => speaker.topics && speaker.topics.length)
      .map((speaker) => `${speaker.displayName}: ${speaker.topics.slice(0, 2).join(", ")}`)
      .slice(0, 3);
    return {
      approved: Boolean(review && review.approved),
      speakerCount: speakers.length,
      approvedCount: approvedCount,
      socialLinkCount: withSocial,
      reviewLine: review && review.approved
        ? `Context: ${speakers.length} speaker${speakers.length === 1 ? "" : "s"} approved${topicPreview.length ? ` (${topicPreview.join(" · ")})` : ""}`
        : "",
      topicPreview: topicPreview,
    };
  }

  function serializeReview(review) {
    return JSON.stringify(review || createReview({}));
  }

  function deserializeReview(json, episodeSummary) {
    if (!json) {
      return createReview(episodeSummary);
    }
    try {
      const parsed = JSON.parse(json);
      if (!parsed || !Array.isArray(parsed.speakers)) {
        return createReview(episodeSummary);
      }
      return parsed;
    } catch (err) {
      return createReview(episodeSummary);
    }
  }

  const api = {
    brandFromWebsite,
    handleFromSocialUrl,
    deriveSpeakerContext,
    createReview,
    updateSpeaker,
    approveReview,
    findSpeakerContext,
    applyHintsToText,
    enrichMomentText,
    applyReviewToMoments,
    applyReviewToCanvas,
    summarizeReview,
    serializeReview,
    deserializeReview,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
    return;
  }

  global.PdcSocialContext = api;
}(typeof window !== "undefined" ? window : globalThis));
