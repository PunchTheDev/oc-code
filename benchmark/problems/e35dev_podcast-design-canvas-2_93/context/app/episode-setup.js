"use strict";

// Episode setup model + rules for Podcast Design Canvas (#1 — first episode setup flow).
//
// This is the single source of truth for the creator's first job: turning raw synced
// recordings and a few social links into a set-up episode. It is deliberately DOM-free
// so the exact same rules run in the browser (the setup screen imports it as a global)
// and in node (the setup-flow tests `require` it). No build step, no dependencies.
(function (global) {
  // Role buckets a creator assigns each source to. "Host" leads; the rest match the
  // Riverside-style guest naming the product workflow describes (Host, Guest 1, Guest 2…).
  const SPEAKER_BUCKETS = ["Host", "Co-host", "Guest 1", "Guest 2", "Guest 3", "Guest 4"];

  // How the raw recording comes in. Either one Riverside recording link, or a separate
  // synced video file per speaker. Labels are creator-facing — no pipeline jargon.
  const SOURCE_MODES = [
    { key: "riverside", label: "Riverside link" },
    { key: "upload", label: "Uploaded speaker files" },
  ];

  // Optional social context captured per speaker. Used only to learn names, topics, and
  // spellings for a smarter edit — never to surface unrelated personal details.
  const SOCIAL_NETWORKS = [
    { key: "website", label: "Website" },
    { key: "twitter", label: "X" },
    { key: "instagram", label: "Instagram" },
    { key: "linkedin", label: "LinkedIn" },
  ];

  function trim(value) {
    return typeof value === "string" ? value.trim() : "";
  }

  function normalizeMode(value) {
    return value === "upload" ? "upload" : "riverside";
  }

  function modeLabel(mode) {
    const found = SOURCE_MODES.find((entry) => entry.key === normalizeMode(mode));
    return found ? found.label : SOURCE_MODES[0].label;
  }

  // Creator-friendly URL check: must be a full link (starts with http/https) and have a
  // host with a dot. Kept lenient on purpose — this guards typos, not link providers.
  function isLikelyUrl(value) {
    const text = trim(value);
    if (!/^https?:\/\//i.test(text)) {
      return false;
    }
    const host = text.replace(/^https?:\/\//i, "").split(/[/?#]/)[0];
    return /[^.\s]+\.[^.\s]+/.test(host);
  }

  function emptySocial() {
    return { website: "", twitter: "", instagram: "", linkedin: "" };
  }

  // A single speaker source: who is talking, which role bucket they fill, the recording
  // that carries them (a file in upload mode, an optional channel label in link mode),
  // and any optional social links.
  function createSpeaker(role) {
    return {
      name: "",
      role: role || "",
      fileName: "",
      fileSize: 0,
      trackLabel: "",
      social: emptySocial(),
    };
  }

  // A fresh episode draft. Seeded with Host / Guest 1 / Guest 2 so the creator starts
  // from sensible defaults instead of a blank list, matching the preset-first taste rule.
  function createDraft() {
    return {
      episodeName: "",
      sourceMode: "riverside",
      riversideLink: "",
      speakers: [createSpeaker("Host"), createSpeaker("Guest 1"), createSpeaker("Guest 2")],
    };
  }

  function socialEntries(speaker) {
    const social = (speaker && speaker.social) || {};
    return SOCIAL_NETWORKS
      .map((net) => ({ key: net.key, label: net.label, url: trim(social[net.key]) }))
      .filter((entry) => entry.url);
  }

  // Validate a draft against the rules a reviewer must be able to feel in the UI. Returns
  // a flat map of field-key → creator-facing message (so the screen can place each error
  // inline) plus an ordered `messages` list for a summary banner. `ok` is true only when
  // nothing is wrong.
  function validateDraft(draft) {
    const data = draft && typeof draft === "object" ? draft : {};
    const mode = normalizeMode(data.sourceMode);
    const errors = {};
    const messages = [];

    function fail(key, message) {
      if (!errors[key]) {
        errors[key] = message;
        messages.push(message);
      }
    }

    if (!trim(data.episodeName)) {
      fail("episodeName", "Add an episode name so you can find this episode later.");
    }

    if (mode === "riverside") {
      const link = trim(data.riversideLink);
      if (!link) {
        fail("riversideLink", "Add your Riverside recording link to import this episode.");
      } else if (!isLikelyUrl(link)) {
        fail("riversideLink", "That Riverside link doesn't look right — paste the full link starting with http.");
      }
    }

    const speakers = Array.isArray(data.speakers) ? data.speakers : [];
    if (speakers.length === 0) {
      fail("speakers", "Add at least one speaker source to set up the episode.");
    }

    const seenRoles = new Set();
    speakers.forEach((raw, index) => {
      const speaker = raw && typeof raw === "object" ? raw : {};
      const name = trim(speaker.name);
      const who = name || `Speaker ${index + 1}`;

      if (!name) {
        fail(`speaker:${index}:name`, `Give speaker ${index + 1} a name so it's clear who's talking.`);
      }

      const role = trim(speaker.role);
      if (!role) {
        fail(`speaker:${index}:role`, `Choose a role for ${who}.`);
      } else if (seenRoles.has(role)) {
        fail(`speaker:${index}:role`, `Two speakers are set to ${role}. Give ${who} a different role so the layout knows who's who.`);
      } else {
        seenRoles.add(role);
      }

      if (mode === "upload" && !trim(speaker.fileName)) {
        fail(`speaker:${index}:source`, `Choose a video file for ${who}.`);
      }

      const social = (speaker && speaker.social) || {};
      SOCIAL_NETWORKS.forEach((net) => {
        const value = trim(social[net.key]);
        if (value && !isLikelyUrl(value)) {
          fail(`speaker:${index}:social:${net.key}`, `The ${net.label} link for ${who} should be a full URL starting with http.`);
        }
      });
    });

    return { ok: messages.length === 0, errors, messages };
  }

  // The label shown for a speaker's source on the workspace summary. Honest about what
  // was actually captured: the chosen file, the named channel, or just the shared link.
  function sourceLabel(mode, speaker) {
    if (normalizeMode(mode) === "upload") {
      return trim(speaker && speaker.fileName) || "No file chosen";
    }
    return trim(speaker && speaker.trackLabel) || "Riverside recording";
  }

  // Derive exactly what the workspace screen displays. Everything here is computed from
  // the draft — no fabricated state — so the summary always reflects what was entered.
  function summarize(draft) {
    const data = draft && typeof draft === "object" ? draft : {};
    const mode = normalizeMode(data.sourceMode);
    const speakers = Array.isArray(data.speakers) ? data.speakers : [];

    const summarizedSpeakers = speakers.map((raw) => {
      const speaker = raw && typeof raw === "object" ? raw : {};
      const social = socialEntries(speaker);
      return {
        role: trim(speaker.role),
        name: trim(speaker.name),
        sourceLabel: sourceLabel(mode, speaker),
        social,
      };
    });

    const socialLinkCount = summarizedSpeakers.reduce((total, sp) => total + sp.social.length, 0);

    return {
      episodeName: trim(data.episodeName),
      sourceMode: mode,
      sourceModeLabel: modeLabel(mode),
      riversideLink: mode === "riverside" ? trim(data.riversideLink) : "",
      speakerCount: summarizedSpeakers.length,
      socialLinkCount,
      roles: summarizedSpeakers.map((sp) => sp.role).filter(Boolean),
      speakers: summarizedSpeakers,
    };
  }

  const api = {
    SPEAKER_BUCKETS,
    SOURCE_MODES,
    SOCIAL_NETWORKS,
    createDraft,
    createSpeaker,
    emptySocial,
    isLikelyUrl,
    modeLabel,
    normalizeMode,
    socialEntries,
    sourceLabel,
    summarize,
    validateDraft,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
    return;
  }

  global.PdcEpisodeSetup = api;
}(typeof window !== "undefined" ? window : globalThis));
