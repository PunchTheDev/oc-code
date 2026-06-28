"use strict";

// Browser wiring for episode setup (#1), social context (#34), audio polish (#15),
// preset style (#4), canvas editor (#11), visual moments (#19), social context (#34),
// publish review (#37), guided workspace (#40), export (#30), show library (#47),
// show brand kits (#52), show identity episode start (#57), publish package (#60),
// transcript correction (#63), episode import before brand setup (#73),
// and episode import polish (#77, #86, #89), visual style preset cards (#94, #102),
// and creator template gallery (#106), home screen focus (#112),
// and gallery copy polish (#117).
(function () {
  const ES = window.PdcEpisodeSetup;
  const STY = window.PdcEpisodeStyle;
  const AP = window.PdcAudioPolish;
  const CL = window.PdcCanvasLayers;
  const CE = window.PdcCanvasEditor;
  const TM = window.PdcShowTemplates;
  const GAL = window.PdcCreatorGallery;
  const VM = window.PdcVisualMoments;
  const SC = window.PdcSocialContext;
  const EXP = window.PdcEpisodeExport;
  const PR = window.PdcPublishReview;
  const WS = window.PdcEpisodeWorkspace;
  const LIB = window.PdcShowLibrary;
  const BK = window.PdcShowBrandKit;
  const SI = window.PdcShowIdentity;
  const ONB = window.PdcShowOnboarding;
  const FLOW = window.PdcEpisodeFlow;
  const SP = window.PdcStylePreview;
  const PP = window.PdcPublishPackage;
  const TC = window.PdcTranscriptCorrection;
  const root = document.getElementById("app");
  const stepIndicator = document.querySelector(".workflow-step-indicator");
  const stepCountEl = document.querySelector(".workflow-step-count");
  const stepLabelEl = document.querySelector(".workflow-step-label");
  const stepFillEl = document.querySelector(".workflow-step-fill");
  const stepPill = stepLabelEl || document.querySelector(".step-pill");
  if (!ES || !root) {
    return;
  }

  let state = ES.createDraft();
  let errors = {};
  let showErrors = false;
  // Style step state, kept across navigation so choices survive Edit setup / Back.
  let styleSelection = STY ? STY.createSelection() : null;
  let appliedStyle = null;
  let layoutCustomized = false;
  let audioPolish = null;
  let appliedAudioPolish = null;
  const TPL_STORAGE_KEY = "pdc-show-templates";
  const GALLERY_STORAGE_KEY = "pdc-creator-gallery";
  let templateStore = TM ? TM.deserializeStore(safeLoadTemplates()) : { templates: [] };
  let galleryStore = GAL ? GAL.deserializeGallery(safeLoadGallery()) : { listings: [] };
  let activeTemplateId = null;
  let activeGalleryListingId = null;
  let canvasDoc = null;
  let canvasLayerCounter = 20;
  let workspaceSummaryCache = null;
  // Visual moments (#19): the per-episode moments board + the moment selected for preview.
  // Kept in module state so edits survive navigating away and back; mirrored to localStorage.
  let momentsBoard = null;
  let selectedMomentId = null;
  let exportJob = null;
  let publishPackage = null;
  let correctionReview = null;
  let correctionApproved = false;
  const MOMENTS_STORAGE_KEY = "pdc-visual-moments";
  let contextReview = null;
  let contextApproved = false;
  let publishReview = null;
  let publishReviewApproved = false;
  const LIB_STORAGE_KEY = "pdc-show-library";
  const EPISODE_SESSIONS_KEY = "pdc-episode-sessions";
  let showLibrary = { shows: [] };
  let activeShowId = null;
  let activeEpisodeId = null;
  let activeBrandKit = null;
  let startingFromShowIdentity = false;
  let showIdentitySummary = null;
  let lastView = "setup";

  function getActiveBrandKit() {
    if (activeBrandKit) {
      return activeBrandKit;
    }
    if (activeShowId && LIB) {
      const show = LIB.getShow(showLibrary, activeShowId);
      return show && show.brandKit ? show.brandKit : null;
    }
    return null;
  }

  function brandKitSummary() {
    const kit = getActiveBrandKit();
    return BK && kit ? BK.summarizeBrandKit(kit) : null;
  }

  function brandedAppliedStyle(summary) {
    if (!appliedStyle || !STY) {
      return appliedStyle;
    }
    const kit = getActiveBrandKit();
    if (!kit || !BK) {
      return appliedStyle;
    }
    return BK.applyToStyleSummary(appliedStyle, kit);
  }

  function safeLoadMoments() {
    try {
      return typeof localStorage !== "undefined" ? localStorage.getItem(MOMENTS_STORAGE_KEY) : null;
    } catch (err) {
      return null;
    }
  }

  function persistMoments() {
    if (!VM || typeof localStorage === "undefined" || !momentsBoard) {
      return;
    }
    applyContextEffects();
    applyCorrectionEffects();
    try {
      localStorage.setItem(MOMENTS_STORAGE_KEY, VM.serializeBoard(momentsBoard));
    } catch (err) {
      /* ignore quota errors */
    }
  }

  function ensureMomentsBoard(summary) {
    if (!VM) {
      return;
    }
    if (!momentsBoard) {
      momentsBoard = VM.deserializeBoard(safeLoadMoments(), summary);
    }
  }

  function safeLoadTemplates() {
    try {
      return typeof localStorage !== "undefined" ? localStorage.getItem(TPL_STORAGE_KEY) : null;
    } catch (err) {
      return null;
    }
  }

  function persistTemplates() {
    if (!TM || typeof localStorage === "undefined") {
      return;
    }
    try {
      localStorage.setItem(TPL_STORAGE_KEY, TM.serializeStore(templateStore));
    } catch (err) {
      /* ignore quota errors */
    }
  }

  function safeLoadGallery() {
    try {
      return typeof localStorage !== "undefined" ? localStorage.getItem(GALLERY_STORAGE_KEY) : null;
    } catch (err) {
      return null;
    }
  }

  function persistGallery() {
    if (!GAL || typeof localStorage === "undefined") {
      return;
    }
    try {
      localStorage.setItem(GALLERY_STORAGE_KEY, GAL.serializeGallery(galleryStore));
    } catch (err) {
      /* ignore quota errors */
    }
  }

  function safeLoadShowLibrary() {
    try {
      return typeof localStorage !== "undefined" ? localStorage.getItem(LIB_STORAGE_KEY) : null;
    } catch (err) {
      return null;
    }
  }

  function persistShowLibrary() {
    if (!LIB || typeof localStorage === "undefined") {
      return;
    }
    try {
      localStorage.setItem(LIB_STORAGE_KEY, LIB.serializeLibrary(showLibrary));
    } catch (err) {
      /* ignore quota errors */
    }
  }

  function summaryFromWorkspace() {
    return workspaceSummaryCache;
  }

  function setStep(label) {
    if (stepPill) {
      stepPill.textContent = label;
    }
    if (/^Show Library/i.test(label)) {
      if (stepCountEl) {
        stepCountEl.textContent = "Show home";
      }
      if (stepLabelEl) {
        stepLabelEl.textContent = label.replace(/^Show Library ·\s*/, "") || "Show Library";
      }
      if (stepFillEl) {
        stepFillEl.style.width = "0%";
      }
      if (stepIndicator) {
        stepIndicator.classList.remove("workflow-step-indicator-active");
      }
      return;
    }
    if (!FLOW) {
      return;
    }
    const indicator = FLOW.stepIndicatorForLabel(label);
    if (stepCountEl) {
      stepCountEl.textContent = indicator.countText;
    }
    if (stepLabelEl) {
      stepLabelEl.textContent = indicator.labelText;
    }
    if (stepFillEl) {
      stepFillEl.style.width = `${Math.round(indicator.progress * 100)}%`;
    }
    if (stepIndicator) {
      stepIndicator.classList.toggle("workflow-step-indicator-active", Boolean(indicator.step));
    }
  }

  function setWorkspaceStep(stageId) {
    if (!FLOW) {
      setStep("Episode workspace · Import to publish");
      return;
    }
    const indicator = FLOW.stepIndicatorForWorkspaceStage(stageId);
    if (stepCountEl) {
      stepCountEl.textContent = indicator.countText;
    }
    if (stepLabelEl) {
      stepLabelEl.textContent = indicator.labelText;
    }
    if (stepFillEl) {
      stepFillEl.style.width = `${Math.round(indicator.progress * 100)}%`;
    }
    if (stepIndicator) {
      stepIndicator.classList.add("workflow-step-indicator-active");
    }
  }

  function loadEpisodeSessions() {
    try {
      const raw = typeof localStorage !== "undefined" ? localStorage.getItem(EPISODE_SESSIONS_KEY) : null;
      if (!raw) {
        return {};
      }
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch (err) {
      return {};
    }
  }

  function saveEpisodeSessions(sessions) {
    if (typeof localStorage === "undefined") {
      return;
    }
    try {
      localStorage.setItem(EPISODE_SESSIONS_KEY, JSON.stringify(sessions || {}));
    } catch (err) {
      /* ignore quota errors */
    }
  }

  function episodeSessionKey(showId, episodeId) {
    return `${showId || "show"}:${episodeId || "episode"}`;
  }

  function buildEpisodeSessionSnapshot() {
    return {
      showId: activeShowId,
      episodeId: activeEpisodeId,
      setupDraft: state,
      styleSelection: styleSelection,
      appliedStyle: appliedStyle,
      appliedAudioPolish: appliedAudioPolish,
      contextApproved: contextApproved,
      publishReviewApproved: publishReviewApproved,
      activeTemplateId: activeTemplateId,
      lastView: lastView,
      setupComplete: ES.validateDraft(state).ok,
      workspaceReached: lastView === "workspace" || Boolean(appliedStyle || appliedAudioPolish),
      updatedAt: Date.now(),
    };
  }

  function persistEpisodeSession() {
    if (!activeShowId || !activeEpisodeId) {
      return;
    }
    const sessions = loadEpisodeSessions();
    sessions[episodeSessionKey(activeShowId, activeEpisodeId)] = buildEpisodeSessionSnapshot();
    saveEpisodeSessions(sessions);
    if (LIB) {
      const status = buildEpisodeSessionSnapshot().workspaceReached
        ? LIB.EPISODE_STATUS.IN_PROGRESS
        : LIB.EPISODE_STATUS.DRAFT;
      showLibrary = LIB.updateEpisode(showLibrary, activeShowId, activeEpisodeId, {
        status: status,
        updatedAt: Date.now(),
      });
      persistShowLibrary();
    }
  }

  function applyEpisodeSessionSnapshot(snapshot) {
    const data = snapshot || {};
    state = data.setupDraft || ES.createDraft();
    styleSelection = data.styleSelection || (STY ? STY.createSelection() : null);
    appliedStyle = data.appliedStyle || null;
    appliedAudioPolish = data.appliedAudioPolish || null;
    contextApproved = Boolean(data.contextApproved);
    publishReviewApproved = Boolean(data.publishReviewApproved);
    activeTemplateId = data.activeTemplateId || null;
    lastView = data.lastView || "setup";
    if (SI && activeShowId && LIB) {
      state = SI.sanitizeSetupDraft(state, LIB.getShow(showLibrary, activeShowId));
    }
  }

  // Tiny DOM helper: el("div", {class:"x", onclick:fn}, child, child...).
  function el(tag, attrs) {
    const node = document.createElement(tag);
    const props = attrs || {};
    Object.keys(props).forEach((key) => {
      const value = props[key];
      if (value == null || value === false) {
        return;
      }
      if (key === "class") {
        node.className = value;
      } else if (key === "for") {
        node.htmlFor = value;
      } else if (key.indexOf("on") === 0 && typeof value === "function") {
        node.addEventListener(key.slice(2).toLowerCase(), value);
      } else if (value === true) {
        node.setAttribute(key, "");
      } else {
        node.setAttribute(key, value);
      }
    });
    for (let i = 2; i < arguments.length; i += 1) {
      appendChild(node, arguments[i]);
    }
    return node;
  }

  function appendChild(node, child) {
    if (child == null || child === false) {
      return;
    }
    if (Array.isArray(child)) {
      child.forEach((c) => appendChild(node, c));
    } else if (typeof child === "string") {
      node.appendChild(document.createTextNode(child));
    } else {
      node.appendChild(child);
    }
  }

  function fieldId(key) {
    if (key.indexOf("speaker:") === 0) {
      const parts = key.split(":");
      return parts.length === 4
        ? `f-sp-${parts[1]}-social-${parts[3]}`
        : `f-sp-${parts[1]}-${parts[2]}`;
    }
    return `f-${key}`;
  }

  // Inline error paragraph for a field, shown only after a failed Continue.
  function errorFor(key) {
    if (!showErrors || !errors[key]) {
      return null;
    }
    return el("p", { class: "field-error", role: "alert" }, errors[key]);
  }

  function isInvalid(key) {
    return showErrors && Boolean(errors[key]);
  }

  function field(labelText, control, key, hint) {
    return el(
      "div",
      { class: "field" },
      el("label", { for: control.id }, labelText),
      hint ? el("p", { class: "hint" }, hint) : null,
      control,
      key ? errorFor(key) : null,
    );
  }

  function setupSectionHeader(stepNum, title, lead) {
    return el(
      "div",
      { class: "setup-section-head" },
      el("span", { class: "setup-section-number", "aria-hidden": "true" }, String(stepNum)),
      el(
        "div",
        { class: "setup-section-title-block" },
        el("h2", {}, title),
        lead ? el("p", { class: "hint setup-section-lead" }, lead) : null,
      ),
    );
  }

  function renderImportFlowOutline() {
    return el(
      "nav",
      { class: "setup-import-flow", "aria-label": "Import setup sections" },
      el("span", { class: "setup-flow-step is-current" }, "1 · Episode details"),
      el("span", { class: "setup-flow-step" }, "2 · Recording source"),
      el("span", { class: "setup-flow-step" }, "3 · Speaker sources"),
    );
  }

  function renderSpeakerRoleOverview() {
    const overview = el("div", { class: "setup-role-overview", "aria-label": "Current speaker role assignments" });
    state.speakers.forEach((speaker, index) => {
      overview.appendChild(
        el(
          "span",
          {
            class: `setup-role-chip ${ES.speakerBucketCueClass(speaker.role)}`,
            "data-role-chip": String(index),
          },
          speaker.role || `Source ${index + 1}`,
        ),
      );
    });
    return overview;
  }

  function applySpeakerBucketCue(node, role) {
    if (!node) {
      return;
    }
    const nextClass = ES.speakerBucketCueClass(role);
    node.classList.forEach((className) => {
      if (className.indexOf("speaker-bucket-") === 0) {
        node.classList.remove(className);
      }
    });
    node.classList.add(nextClass);
  }

  function syncSpeakerBucketCues(role, card, roleBadge, chip) {
    applySpeakerBucketCue(card, role);
    applySpeakerBucketCue(roleBadge, role);
    applySpeakerBucketCue(chip, role);
  }

  function nextRole() {
    const used = {};
    state.speakers.forEach((s) => {
      used[s.role] = true;
    });
    const free = ES.SPEAKER_BUCKETS.find((bucket) => !used[bucket]);
    return free || `Guest ${state.speakers.length}`;
  }

  function setPageIntro(mode) {
    const intro = document.querySelector(".intro");
    if (!intro) {
      return;
    }
    const heading = intro.querySelector("h1");
    const copy = intro.querySelector("p");
    if (mode === "library") {
      intro.hidden = false;
      if (heading) {
        heading.textContent = "Start your next episode";
      }
      if (copy) {
        copy.textContent = "Create a show and import your recording — Riverside link or synced speaker files — then assign speakers before style or brand work.";
      }
      return;
    }
    if (mode === "new-show") {
      intro.hidden = false;
      if (heading) {
        heading.textContent = "Create a show";
      }
      if (copy) {
        copy.textContent = "Name your show and optionally pick a saved template. Next you will import your first episode recording and assign speakers.";
      }
      return;
    }
    if (mode === "show-detail") {
      intro.hidden = false;
      if (heading) {
        heading.textContent = "Show home";
      }
      if (copy) {
        copy.textContent = "Start or continue episode import here. Brand kit is optional and can wait until after your recording and speakers are set up.";
      }
      return;
    }
    if (mode === "episode-setup") {
      intro.hidden = false;
      if (heading) {
        heading.textContent = "Import your episode";
      }
      if (copy) {
        copy.textContent = "Bring in a Riverside link or separate synced speaker files, assign each source to Host, Guest 1, or Guest 2, and add social links so the edit gets names and context right.";
      }
      return;
    }
    intro.hidden = true;
  }

  function getShowDetailSections(show) {
    if (ONB) {
      return ONB.showDetailSections(show);
    }
    return {
      primary: {
        id: "episode-setup",
        title: "Import your recording first",
        hint: "Add a Riverside link or synced speaker files and assign speakers before style or brand work.",
        actionLabel: "Set up episode →",
      },
      secondary: {
        id: "brand-kit",
        title: "Brand kit (optional)",
        hint: "Set up later — episode import comes first.",
        actionLabel: "Set up brand kit later",
      },
    };
  }

  // ---- Show library view -----------------------------------------------------

  function renderHomeGallerySpotlight() {
    if (!GAL) {
      return null;
    }
    if (!GAL.listListings(galleryStore).length) {
      seedGalleryDemoData();
    }
    const listings = GAL.listListings(galleryStore);
    const previewSummary = galleryPreviewSummary("Founders Unfiltered");
    const section = el(
      "section",
      { class: "card show-library-gallery-card home-gallery-spotlight" },
      el("div", { class: "home-gallery-spotlight-head" },
        el("h2", { class: "show-library-gallery-title" }, "Creator template gallery"),
        el(
          "p",
          { class: "hint" },
          "Start from a publish-ready layout — preview speaker frames, captions, and overlays, then apply to your show.",
        ),
      ),
    );

    if (listings.length) {
      const thumbGrid = el("div", { class: "home-gallery-thumb-grid" });
      listings.slice(0, 3).forEach((item) => {
        const listing = GAL.getListing(galleryStore, item.id);
        const card = el(
          "button",
          {
            type: "button",
            class: "home-gallery-thumb-card",
            "aria-label": `Preview ${item.name}`,
          },
          renderGalleryPreviewThumb(listing, previewSummary),
          el("span", { class: "home-gallery-thumb-name" }, item.name),
          el(
            "span",
            { class: "home-gallery-thumb-meta" },
            galleryListingStatusLine(item),
          ),
        );
        card.addEventListener("click", () => {
          activeGalleryListingId = item.id;
          renderCreatorGalleryBrowse(null, { returnTo: "library" });
        });
        thumbGrid.appendChild(card);
      });
      section.appendChild(thumbGrid);
    }

    const actions = el("div", { class: "home-gallery-spotlight-actions" });
    const browseBtn = el("button", { type: "button", class: "btn-primary" }, "Browse creator gallery →");
    browseBtn.addEventListener("click", () => {
      if (!GAL.listListings(galleryStore).length) {
        seedGalleryDemoData();
      }
      renderCreatorGalleryBrowse(null, { returnTo: "library" });
    });
    actions.appendChild(browseBtn);

    const publishLink = el("button", { type: "button", class: "link-button home-gallery-secondary-link" }, "Publish a template");
    publishLink.addEventListener("click", () => openPublishGalleryDemo());
    actions.appendChild(publishLink);
    section.appendChild(actions);
    return section;
  }

  function renderShowLibrary() {
    if (!LIB) {
      setPageIntro("episode-setup");
      renderSetup();
      return;
    }
    setPageIntro("library");
    root.innerHTML = "";
    setStep("Show Library");

    const shows = LIB.listShows(showLibrary);
    const summary = LIB.summarizeLibrary(showLibrary);

    const header = el(
      "div",
      { class: "workspace-header home-screen-header" },
      el("h1", {}, "Show Library"),
      el("p", { class: "hint" }, summary.libraryLine),
    );

    const startHero = el(
      "section",
      { class: "card home-start-hero" },
      el("p", { class: "eyebrow" }, "Recommended start"),
      el("h2", { class: "home-start-title" }, "Create a show and import your first episode"),
      el(
        "p",
        { class: "hint home-start-lead" },
        "The main path: name your show, bring in a Riverside link or synced speaker files, assign Host and guests, then choose a look.",
      ),
    );
    const primaryStartBtn = el(
      "button",
      { class: "btn-primary home-primary-cta", type: "button" },
      "Create show & import episode →",
    );
    primaryStartBtn.addEventListener("click", () => renderNewShowForm());
    startHero.appendChild(primaryStartBtn);

    const secondaryLinks = el("div", { class: "home-secondary-links" });
    const blankEpisodeLink = el("button", { class: "link-button", type: "button" }, "Start blank episode");
    blankEpisodeLink.addEventListener("click", () => startBlankEpisode());
    secondaryLinks.appendChild(blankEpisodeLink);
    startHero.appendChild(secondaryLinks);

    const exploreSection = el(
      "section",
      { class: "card home-explore-panel" },
      el("h3", { class: "home-explore-title" }, "Explore"),
      el("p", { class: "hint" }, "Preview style presets before you create a show — the recommended start above is still the fastest path to a polished episode."),
    );
    const exploreLinks = el("div", { class: "home-explore-links" });
    const styleDemoLink = el("button", { class: "link-button", type: "button" }, "Preview style presets");
    styleDemoLink.addEventListener("click", () => openStylePickerDemo());
    exploreLinks.appendChild(styleDemoLink);
    exploreSection.appendChild(exploreLinks);

    const galleryCard = renderHomeGallerySpotlight();

    const listEl = el("div", { class: "show-library-list" });

    if (!shows.length) {
      listEl.appendChild(
        el(
          "div",
          { class: "show-library-empty" },
          el("p", {}, "No shows yet. Create a show — you will import your first recording and assign speakers right away."),
        ),
      );
    } else {
      shows.forEach((show) => {
        const meta = [];
        if (show.templateName) meta.push(show.templateName);
        if (show.presetName) meta.push(show.presetName);
        if (show.brandKit && BK) {
          const brandLine = BK.summarizeBrandKit(show.brandKit).identityLine;
          if (brandLine && brandLine !== "No brand kit configured") {
            meta.push(brandLine);
          }
        }
        const metaText = meta.length ? meta.join(" · ") : "No template saved";

        const epCount = el("span", { class: "show-ep-count" }, `${show.episodeCount} episode${show.episodeCount === 1 ? "" : "s"}`);
        const latest = show.latestEpisode
          ? el("span", { class: "show-latest" }, `Latest: ${show.latestEpisode.name} — ${LIB.episodeStatusLabel(show.latestEpisode.status)}`)
          : null;

        const openBtn = el("button", { class: "btn-secondary btn-sm", type: "button" }, "Open");
        openBtn.addEventListener("click", () => {
          activeShowId = show.id;
          renderShowDetail(show.id);
        });

        const newEpBtn = el("button", { class: "btn-primary btn-sm", type: "button" }, "New episode →");
        newEpBtn.addEventListener("click", () => {
          activeShowId = show.id;
          startEpisodeFromShow(show.id);
        });

        const card = el(
          "div",
          { class: "show-library-card" },
          el(
            "div",
            { class: "show-library-card-main" },
            el("h2", { class: "show-library-card-name" }, show.name),
            el("p", { class: "show-library-card-meta" }, metaText),
            el("div", { class: "show-library-card-stats" }, epCount, latest),
          ),
          el("div", { class: "show-library-card-actions" }, openBtn, newEpBtn),
        );
        listEl.appendChild(card);
      });
    }

    const view = el(
      "div",
      { class: "workspace-root home-screen" },
      header,
      startHero,
      galleryCard,
      exploreSection,
      listEl,
    );
    root.appendChild(view);
  }

  function renderNewShowForm(prefillName, errorMsg, initialPresetId) {
    setPageIntro("new-show");
    root.innerHTML = "";
    setStep("Show Library · New Show");

    const saved = TM ? TM.listTemplates(templateStore) : [];
    const defaultPreset = STY ? STY.defaultPreset() : null;
    let selectedTemplateId = initialPresetId || (defaultPreset ? `preset:${defaultPreset.id}` : "");
    let selectedPresetName = defaultPreset ? defaultPreset.name : "";

    const nameInput = el("input", { id: "f-show-name", type: "text", value: prefillName || "", placeholder: "e.g. Founders Unfiltered" });

    const previewHost = el("div", { class: "create-show-preview-host", id: "create-show-preview-host" });

    function selectedPresetIdFromChoice() {
      if (selectedTemplateId.indexOf("preset:") === 0) {
        return selectedTemplateId.slice("preset:".length);
      }
      return null;
    }

    function refreshLargePreview() {
      previewHost.innerHTML = "";
      const presetId = selectedPresetIdFromChoice();
      if (presetId && SP) {
        previewHost.appendChild(
          renderEpisodeLookPreview(SP.buildEpisodeLook(presetId, { showName: nameInput.value }), "hero"),
        );
        return;
      }
      previewHost.appendChild(
        el(
          "p",
          { class: "hint create-show-preview-placeholder" },
          "Select a named preset to preview your publish-ready episode look.",
        ),
      );
    }

    const presetGrid = el("div", { class: "create-show-preset-grid" });
    if (STY && SP) {
      STY.STYLE_PRESETS.forEach((preset) => {
        const choiceId = `preset:${preset.id}`;
        const selected = selectedTemplateId === choiceId;
        const card = el(
          "button",
          {
            type: "button",
            class: `create-show-preset-card${selected ? " selected" : ""}`,
            "aria-pressed": selected ? "true" : "false",
          },
          renderEpisodeLookPreview(SP.buildEpisodeLook(preset.id, { showName: nameInput.value }), "card"),
          el("span", { class: "create-show-preset-name" }, preset.name),
          el("span", { class: "create-show-preset-tagline" }, preset.tagline),
          el("span", { class: "preset-format-cue create-show-preset-format" }, STY.presetCardSummary(preset).formatCue),
        );
        card.addEventListener("click", () => {
          selectedTemplateId = choiceId;
          selectedPresetName = preset.name;
          presetGrid.querySelectorAll(".create-show-preset-card").forEach((node) => {
            const isActive = node === card;
            node.classList.toggle("selected", isActive);
            node.setAttribute("aria-pressed", isActive ? "true" : "false");
          });
          blankOption.classList.remove("selected");
          blankOption.setAttribute("aria-pressed", "false");
          refreshLargePreview();
        });
        presetGrid.appendChild(card);
      });
    }

    const blankOption = el(
      "button",
      {
        type: "button",
        class: `create-show-blank-option${selectedTemplateId === "" ? " selected" : ""}`,
        "aria-pressed": selectedTemplateId === "" ? "true" : "false",
      },
      "Blank show — choose a style later during import",
    );
    blankOption.addEventListener("click", () => {
      selectedTemplateId = "";
      selectedPresetName = "";
      presetGrid.querySelectorAll(".create-show-preset-card").forEach((node) => {
        node.classList.remove("selected");
        node.setAttribute("aria-pressed", "false");
      });
      blankOption.classList.add("selected");
      blankOption.setAttribute("aria-pressed", "true");
      refreshLargePreview();
    });

    nameInput.addEventListener("input", () => refreshLargePreview());

    const savedTemplatesBlock = el("div", { class: "create-show-saved-templates" });
    if (saved.length) {
      savedTemplatesBlock.appendChild(el("span", { class: "create-show-saved-label" }, "Saved templates"));
      saved.forEach((template) => {
        const row = el("button", {
          type: "button",
          class: `create-show-saved-template${selectedTemplateId === template.id ? " selected" : ""}`,
        }, template.name);
        row.addEventListener("click", () => {
          selectedTemplateId = template.id;
          selectedPresetName = template.presetName || "";
          blankOption.classList.remove("selected");
          blankOption.setAttribute("aria-pressed", "false");
          presetGrid.querySelectorAll(".create-show-preset-card").forEach((node) => {
            node.classList.remove("selected");
            node.setAttribute("aria-pressed", "false");
          });
          savedTemplatesBlock.querySelectorAll(".create-show-saved-template").forEach((node) => {
            node.classList.toggle("selected", node === row);
          });
          refreshLargePreview();
        });
        savedTemplatesBlock.appendChild(row);
      });
    }

    if (errorMsg) {
      root.appendChild(el("div", { class: "banner", role: "alert" }, errorMsg));
    }

    const presetLayout = el(
      "div",
      { class: "create-show-preset-layout" },
      el(
        "section",
        { class: "create-show-preset-panel" },
        el("span", { class: "field-label" }, "Choose your show look"),
        el(
          "p",
          { class: "hint create-show-preset-lead" },
          "Start from a publish-ready preset — each card shows realistic speaker framing, captions, and overlay treatment.",
        ),
        presetGrid,
        blankOption,
        saved.length ? savedTemplatesBlock : null,
      ),
      el(
        "section",
        { class: "card create-show-preview-panel" },
        el("h3", {}, "Episode look preview"),
        el("p", { class: "hint" }, "Sample multi-speaker episode with title bar, captions, and pacing cues."),
        previewHost,
      ),
    );

    const form = el(
      "div",
      { class: "card create-show-form" },
      el("h2", {}, "Create new show"),
      el(
        "div",
        { class: "field" },
        el("label", { for: "f-show-name" }, "Show name"),
        nameInput,
      ),
      presetLayout,
      el(
        "p",
        { class: "hint" },
        "After you create the show, you will go straight to episode import — Riverside link or synced speaker files, speaker roles, and social links.",
      ),
    );

    const cancelBtn = el("button", { class: "btn-secondary", type: "button" }, "Cancel");
    cancelBtn.addEventListener("click", () => renderShowLibrary());

    const saveBtn = el("button", { class: "btn-primary create-show-continue-btn", type: "button" }, "Create show & import episode →");
    saveBtn.addEventListener("click", () => {
      const name = nameInput.value;
      const check = LIB.validateShowName(showLibrary, name);
      if (!check.ok) {
        renderNewShowForm(name, check.error, selectedTemplateId);
        return;
      }
      const tpl = saved.find((t) => t.id === selectedTemplateId);
      const isPresetChoice = selectedTemplateId.indexOf("preset:") === 0;
      const show = LIB.createShow(check.name, {
        templateId: isPresetChoice ? "" : selectedTemplateId,
        templateName: tpl ? tpl.name : "",
        presetName: selectedPresetName,
      });
      showLibrary = LIB.addShow(showLibrary, show);
      persistShowLibrary();
      activeShowId = show.id;
      startEpisodeFromShow(show.id);
    });

    const footer = el("div", { class: "workspace-actions setup-cta-bar" }, cancelBtn, saveBtn);
    root.appendChild(el("div", { class: "workspace-root" }, form, footer));
    refreshLargePreview();
  }

  function renderShowDetail(showId) {
    const show = LIB.getShow(showLibrary, showId);
    if (!show) {
      renderShowLibrary();
      return;
    }
    setPageIntro("show-detail");
    root.innerHTML = "";
    setStep(`Show Library · ${show.name}`);

    const episodes = LIB.listEpisodes(showLibrary, showId);
    const sections = getShowDetailSections(show);
    const metaParts = [];
    if (show.templateName) metaParts.push(`Template: ${show.templateName}`);
    if (show.presetName) metaParts.push(`Style: ${show.presetName}`);

    const backBtn = el("button", { class: "btn-secondary btn-sm", type: "button" }, "← Library");
    backBtn.addEventListener("click", () => renderShowLibrary());

    const header = el(
      "div",
      { class: "workspace-header" },
      el("div", { class: "workspace-header-row" }, backBtn),
      el("h1", {}, show.name),
      metaParts.length ? el("p", { class: "hint" }, metaParts.join(" · ")) : null,
    );

    const primaryCard = el("section", { class: "card show-primary-step-card" }, el("h2", {}, sections.primary.title));
    primaryCard.appendChild(el("p", { class: "hint" }, sections.primary.hint));
    const primaryActions = el("div", { class: "show-primary-step-actions" });
    const primaryBtn = el("button", { class: "btn-primary", type: "button" }, sections.primary.actionLabel);
    primaryBtn.addEventListener("click", () => {
      if (sections.primary.mode === "resume" && sections.primary.episodeId) {
        resumeEpisodeFromShow(showId, sections.primary.episodeId);
        return;
      }
      startEpisodeFromShow(showId);
    });
    primaryActions.appendChild(primaryBtn);
    if (sections.primary.mode === "resume" && sections.canStartNewEpisode) {
      const newEpisodeBtn = el("button", { class: "btn-secondary", type: "button" }, "Start new episode →");
      newEpisodeBtn.addEventListener("click", () => startEpisodeFromShow(showId));
      primaryActions.appendChild(newEpisodeBtn);
    }
    primaryCard.appendChild(primaryActions);

    const epListEl = el("div", { class: "show-episode-list" });
    if (!episodes.length) {
      epListEl.appendChild(
        el("p", { class: "hint" }, "No episodes yet — use the button above to import your first recording and assign speakers."),
      );
    } else {
      episodes.forEach((ep) => {
        const statusLabel = LIB.episodeStatusLabel(ep.status);
        const statusClass = `ep-status ep-status--${ep.status}`;
        const resumable = FLOW && FLOW.RESUMABLE_STATUSES.has(ep.status);
        const epCard = el(
          "div",
          { class: `show-episode-card${resumable ? " show-episode-card-resumable" : ""}` },
          el("span", { class: "show-episode-name" }, ep.name),
          el("span", { class: statusClass }, statusLabel),
          ep.downloadName ? el("span", { class: "show-episode-download" }, ep.downloadName) : null,
        );
        if (resumable) {
          const resumeBtn = el("button", { type: "button", class: "btn-primary btn-sm show-episode-resume-btn" }, "Resume →");
          resumeBtn.addEventListener("click", () => resumeEpisodeFromShow(showId, ep.id));
          epCard.appendChild(resumeBtn);
        }
        epListEl.appendChild(epCard);
      });
    }

    const episodesCard = el("section", { class: "card show-episodes-card" }, el("h2", {}, "Episodes"), epListEl);

    const kit = show.brandKit;
    const kitSummary = BK && kit ? BK.summarizeBrandKit(kit) : null;
    const brandCard = el("section", { class: "card brand-kit-card show-secondary-step-card" }, el("h2", {}, sections.secondary.title));
    brandCard.appendChild(el("p", { class: "hint" }, sections.secondary.hint));
    if (kitSummary && kitSummary.identityLine !== "No brand kit configured") {
      brandCard.appendChild(el("p", { class: "brand-kit-line" }, kitSummary.identityLine));
      if (kitSummary.colorSummary) {
        brandCard.appendChild(el("p", { class: "hint" }, `Colors: ${kitSummary.colorSummary}`));
      }
      if (kitSummary.overlayCount) {
        brandCard.appendChild(el("p", { class: "hint" }, `${kitSummary.overlayCount} overlay asset${kitSummary.overlayCount === 1 ? "" : "s"}`));
      }
    }
    const editBrandBtn = el("button", { class: "btn-secondary btn-sm", type: "button" }, sections.secondary.actionLabel);
    editBrandBtn.addEventListener("click", () => renderBrandKitEditor(showId));
    brandCard.appendChild(el("div", { class: "brand-kit-actions" }, editBrandBtn));

    const view = el("div", { class: "workspace-root" }, header, primaryCard, episodesCard, brandCard);
    root.appendChild(view);
  }

  function renderBrandKitEditor(showId) {
    if (!BK || !LIB) {
      renderShowDetail(showId);
      return;
    }
    const show = LIB.getShow(showLibrary, showId);
    if (!show) {
      renderShowLibrary();
      return;
    }
    activeShowId = showId;
    setPageIntro("show-detail");
    let kit = show.brandKit || BK.createBrandKit(showId);
    root.innerHTML = "";
    setStep(`Show Library · ${show.name} · Brand kit`);

    const backBtn = el("button", { class: "btn-secondary btn-sm", type: "button" }, "← Back to show");
    backBtn.addEventListener("click", () => renderShowDetail(showId));

    const view = el("div", { class: "workspace-root brand-kit-editor" });
    view.appendChild(
      el(
        "div",
        { class: "workspace-header" },
        el("div", { class: "workspace-header-row" }, backBtn),
        el("h1", {}, "Brand kit"),
        el("p", { class: "hint" }, `Reusable identity for ${show.name} — logo, colors, type, captions, and overlay assets.`),
      ),
    );

    const form = el("form", { class: "card", novalidate: true });
    const logoInput = el("input", { id: "brand-logo", type: "text", value: kit.logoLabel || "", placeholder: "e.g. Founders wordmark" });
    form.appendChild(field("Logo label", logoInput, null, "Name the logo asset creators should expect on episodes."));

    const colorGrid = el("div", { class: "brand-color-grid" });
    ["primary", "secondary", "background", "accent", "text"].forEach((key) => {
      const input = el("input", {
        id: `brand-color-${key}`,
        type: "text",
        value: kit.colors[key] || "",
        placeholder: "#000000",
      });
      colorGrid.appendChild(field(key.charAt(0).toUpperCase() + key.slice(1), input));
    });
    form.appendChild(el("div", { class: "field" }, el("label", {}, "Brand colors"), colorGrid));

    const typeSelect = el("select", { id: "brand-type-style" });
    BK.TYPE_STYLES.forEach((item) => {
      typeSelect.appendChild(el("option", { value: item.id, selected: kit.typeStyle === item.id ? true : null }, item.label));
    });
    form.appendChild(field("Type style", typeSelect));

    const captionSelect = el("select", { id: "brand-caption-style" });
    BK.CAPTION_STYLES.forEach((item) => {
      captionSelect.appendChild(el("option", { value: item.id, selected: kit.captionStyle === item.id ? true : null }, item.label));
    });
    form.appendChild(field("Caption style", captionSelect));

    const overlayList = el("div", { class: "brand-overlay-list" });
    function renderOverlayList() {
      overlayList.innerHTML = "";
      (kit.overlayAssets || []).forEach((asset) => {
        const row = el(
          "div",
          { class: "brand-overlay-row" },
          el("span", {}, `${asset.name} · ${asset.kindLabel || asset.kind}`),
        );
        const removeBtn = el("button", { type: "button", class: "link-button" }, "Remove");
        removeBtn.addEventListener("click", () => {
          kit = BK.removeOverlayAsset(kit, asset.id);
          renderOverlayList();
        });
        row.appendChild(removeBtn);
        overlayList.appendChild(row);
      });
    }
    renderOverlayList();

    const overlayName = el("input", { id: "brand-overlay-name", type: "text", placeholder: "Asset name" });
    const overlayKind = el("select", { id: "brand-overlay-kind" });
    BK.OVERLAY_KINDS.forEach((item) => {
      overlayKind.appendChild(el("option", { value: item.id }, item.label));
    });
    const addOverlayBtn = el("button", { type: "button", class: "ghost" }, "+ Add overlay asset");
    addOverlayBtn.addEventListener("click", () => {
      kit = BK.addOverlayAsset(kit, overlayName.value, overlayKind.value);
      overlayName.value = "";
      renderOverlayList();
    });
    form.appendChild(field("Overlay assets", overlayList));
    form.appendChild(el("div", { class: "brand-overlay-add" }, overlayName, overlayKind, addOverlayBtn));

    const previewCard = el("section", { class: "card brand-kit-preview-card" }, el("h3", {}, "Preview"));
    const preset = STY ? STY.getPreset("studio-spotlight") : {};
    const previewTheme = BK.getPreviewTheme(preset, kit);
    const swatch = el("div", { class: "brand-kit-swatch" });
    swatch.style.background = previewTheme.background;
    swatch.style.color = previewTheme.textColor;
    swatch.style.borderColor = previewTheme.accent;
    swatch.appendChild(el("span", { class: "brand-kit-swatch-logo" }, previewTheme.logoLabel || "Logo"));
    swatch.appendChild(el("span", { class: "brand-kit-swatch-caption", style: `background:${previewTheme.accent}` }, previewTheme.captionStyle));
    swatch.appendChild(el("span", { class: "brand-kit-swatch-type" }, previewTheme.typeStyleLabel));
    previewCard.appendChild(swatch);
    form.appendChild(previewCard);

    const error = el("p", { class: "field-error", role: "alert", hidden: true });
    form.appendChild(error);

    form.addEventListener("submit", (event) => {
      event.preventDefault();
      kit = BK.updateBrandKit(kit, {
        logoLabel: logoInput.value,
        typeStyle: typeSelect.value,
        captionStyle: captionSelect.value,
        colors: {
          primary: document.getElementById("brand-color-primary").value,
          secondary: document.getElementById("brand-color-secondary").value,
          background: document.getElementById("brand-color-background").value,
          accent: document.getElementById("brand-color-accent").value,
          text: document.getElementById("brand-color-text").value,
        },
      });
      const check = BK.validateBrandKit(kit);
      if (!check.ok) {
        error.hidden = false;
        error.textContent = check.error;
        return;
      }
      showLibrary = LIB.updateShow(showLibrary, showId, { brandKit: kit });
      persistShowLibrary();
      activeBrandKit = kit;
      renderShowDetail(showId);
    });

    form.appendChild(
      el("div", { class: "actions" }, el("button", { type: "submit", class: "primary" }, "Save brand kit")),
    );
    view.appendChild(form);
    root.appendChild(view);
  }

  function renderShowIdentityBanner() {
    if (!startingFromShowIdentity || !showIdentitySummary) {
      return null;
    }
    return el(
      "section",
      { class: "card show-identity-banner" },
      el("h3", {}, showIdentitySummary.headline),
      el("p", { class: "hint" }, showIdentitySummary.identityLine),
      el("p", { class: "hint show-identity-note" }, "Show context is above — enter each speaker's name and recording source below."),
    );
  }

  function resetEpisodeSession() {
    state = ES.createDraft();
    errors = {};
    showErrors = false;
    styleSelection = STY ? STY.createSelection() : null;
    appliedStyle = null;
    layoutCustomized = false;
    audioPolish = null;
    appliedAudioPolish = null;
    activeTemplateId = null;
    canvasDoc = null;
    canvasLayerCounter = 20;
    workspaceSummaryCache = null;
    momentsBoard = null;
    selectedMomentId = null;
    exportJob = null;
    publishPackage = null;
    correctionReview = null;
    correctionApproved = false;
    contextReview = null;
    contextApproved = false;
    publishReview = null;
    publishReviewApproved = false;
    startingFromShowIdentity = false;
    showIdentitySummary = null;
    activeEpisodeId = null;
    lastView = "setup";
  }

  function applyEpisodeStart(start) {
    resetEpisodeSession();
    if (!start) {
      return;
    }
    activeShowId = start.showId || null;
    activeBrandKit = start.brandKit || null;
    startingFromShowIdentity = Boolean(start.fromShowIdentity);
    showIdentitySummary = start.identity || null;
    state = start.setupDraft || ES.createDraft();
    if (SI) {
      const showForSanitize = activeShowId && LIB
        ? LIB.getShow(showLibrary, activeShowId)
        : (start.showName ? { name: start.showName, episodes: [] } : null);
      state = SI.sanitizeSetupDraft(state, showForSanitize);
    }
    styleSelection = start.styleSelection || (STY ? STY.createSelection() : null);
    appliedStyle = start.appliedStyle || null;
    activeTemplateId = start.templateId || null;
    canvasDoc = start.canvasDoc || null;
    layoutCustomized = Boolean(styleSelection && styleSelection.layout && styleSelection.layout !== "auto");
  }

  function startBlankEpisode() {
    activeShowId = null;
    applyEpisodeStart(SI ? SI.buildBlankEpisodeStart() : null);
    setPageIntro("episode-setup");
    renderSetup();
  }

  function openStylePickerDemo() {
    activeShowId = null;
    activeEpisodeId = null;
    startingFromShowIdentity = false;
    showIdentitySummary = null;
    state = ES.createDraft();
    state.episodeName = "Founders Unfiltered #7";
    state.sourceMode = "riverside";
    state.riversideLink = "https://riverside.fm/studio/founders-demo";
    state.speakers = [
      Object.assign(ES.createSpeaker("Host"), { name: "Sam Rivera" }),
      Object.assign(ES.createSpeaker("Guest 1"), { name: "Dana Kim" }),
      Object.assign(ES.createSpeaker("Guest 2"), { name: "Alex Chen" }),
    ];
    contextApproved = true;
    contextReview = null;
    appliedStyle = null;
    styleSelection = STY ? STY.createSelection() : null;
    layoutCustomized = false;
    audioPolish = AP ? AP.createPolish(ES.summarize(state)) : null;
    appliedAudioPolish = AP && audioPolish ? AP.summarizePolish(audioPolish) : null;
    activeTemplateId = null;
    canvasDoc = null;
    exportJob = null;
    publishReview = null;
    publishReviewApproved = false;
    lastView = "style";
    const summary = ES.summarize(state);
    setPageIntro("episode-setup");
    renderStyle(summary);
  }

  function buildAgencySplitDemoTemplate() {
    if (!TM || !CE || !STY || !CL) {
      return null;
    }
    const demoDraft = ES.createDraft();
    demoDraft.episodeName = "Founders Unfiltered #7";
    demoDraft.sourceMode = "upload";
    demoDraft.speakers = [
      Object.assign(ES.createSpeaker("Host"), { name: "Sam Rivera" }),
      Object.assign(ES.createSpeaker("Guest 1"), { name: "Dana Kim" }),
      Object.assign(ES.createSpeaker("Guest 2"), { name: "Alex Chen" }),
    ];
    const episodeA = ES.summarize(demoDraft);
    const selection = STY.createSelection();
    selection.presetId = "split-stage";
    selection.layout = "split";
    const applied = STY.summarizeStyle(selection, episodeA.speakerCount);
    let doc = CE.createFromStyle(applied, episodeA, selection);
    doc = CE.updateElement(doc, "titleText", "Founders Unfiltered · Episode 12");
    doc = CE.updateElement(doc, "captionText", "Dana: Side-by-side framing keeps the conversation balanced.");
    const captionsIdx = doc.layers.findIndex((layer) => layer.type === "captions");
    doc = CE.updateLayers(doc, CL.moveLayer(doc.layers, captionsIdx, -1));
    if (!CE.validateForSave(doc).ok) {
      return null;
    }
    return TM.createTemplate("Agency Split", doc, "tpl-agency-split-demo");
  }

  function seedGalleryDemoData() {
    if (!GAL || !TM) {
      return false;
    }
    let template = TM.getTemplate(templateStore, "tpl-agency-split-demo");
    if (!template) {
      const built = buildAgencySplitDemoTemplate();
      if (!built) {
        return false;
      }
      templateStore = TM.saveTemplate(templateStore, built);
      persistTemplates();
      template = built;
    }
    const existing = GAL.listListings(galleryStore).find((item) => item.sourceTemplateId === template.id);
    if (existing) {
      return true;
    }
    galleryStore = GAL.publishListing(galleryStore, template, {
      name: "Founders Split Look",
      description: "Side-by-side interview layout with bold captions, lower-thirds, and brand styling.",
      styleTags: ["Interview", "Split stage", "Multi-speaker"],
      previewImage: GAL.buildPreviewImage(template.canvas),
      creatorName: "Founders Unfiltered",
    });
    persistGallery();
    return true;
  }

  function openPublishGalleryDemo() {
    if (!GAL || !TM) {
      return;
    }
    seedGalleryDemoData();
    const summary = galleryPreviewSummary("Founders Unfiltered");
    renderPublishToGallery("tpl-agency-split-demo", summary, "library");
  }

  function startEpisodeFromShow(showId) {
    if (!LIB || !SI) {
      startBlankEpisode();
      return;
    }
    const show = LIB.getShow(showLibrary, showId);
    if (!show) {
      renderShowLibrary();
      return;
    }
    const start = SI.buildEpisodeStart(show, templateStore);
    applyEpisodeStart(start);

    const episode = LIB.createEpisode(showId, state.episodeName, {
      templateId: start.templateId,
      templateName: start.templateName,
      presetName: start.appliedStyle ? start.appliedStyle.presetName : show.presetName,
      speakerRoles: state.speakers.map((speaker) => speaker.role),
      status: LIB.EPISODE_STATUS.DRAFT,
    });
    showLibrary = LIB.addEpisode(showLibrary, showId, episode);
    persistShowLibrary();
    activeEpisodeId = episode.id;
    lastView = "setup";
    persistEpisodeSession();

    setPageIntro("episode-setup");
    renderSetup();
  }

  function resumeEpisodeFromShow(showId, episodeId) {
    if (!LIB || !SI) {
      startBlankEpisode();
      return;
    }
    const show = LIB.getShow(showLibrary, showId);
    const episodes = LIB.listEpisodes(showLibrary, showId);
    const episode = episodes.find((entry) => entry.id === episodeId);
    if (!show || !episode) {
      renderShowDetail(showId);
      return;
    }

    activeShowId = showId;
    activeEpisodeId = episodeId;
    const sessions = loadEpisodeSessions();
    const snapshot = sessions[episodeSessionKey(showId, episodeId)];
    const start = SI.buildEpisodeStart(show, templateStore);

    resetEpisodeSession();
    activeShowId = showId;
    activeEpisodeId = episodeId;
    startingFromShowIdentity = true;
    showIdentitySummary = start.identity;
    activeBrandKit = start.brandKit;
    activeTemplateId = start.templateId;
    canvasDoc = start.canvasDoc;
    styleSelection = start.styleSelection;

    if (snapshot) {
      applyEpisodeSessionSnapshot(snapshot);
    } else {
      state = start.setupDraft || ES.createDraft();
      state = SI.sanitizeSetupDraft(state, show);
    }
    state.episodeName = episode.name;

    const destination = FLOW ? FLOW.resumeDestination(snapshot || buildEpisodeSessionSnapshot()) : "setup";
    setPageIntro("episode-setup");
    if (destination === "workspace") {
      lastView = "workspace";
      renderWorkspace(ES.summarize(state));
    } else {
      lastView = "setup";
      renderSetup();
    }
    persistEpisodeSession();
  }

  // ---- Setup view -------------------------------------------------------------

  function showContextForSanitize() {
    if (activeShowId && LIB) {
      return LIB.getShow(showLibrary, activeShowId);
    }
    if (startingFromShowIdentity && showIdentitySummary && showIdentitySummary.headline) {
      const match = showIdentitySummary.headline.match(/^Starting from (.+) identity$/);
      if (match) {
        return { name: match[1], episodes: [] };
      }
    }
    return null;
  }

  function sanitizeSetupState() {
    if (!SI) {
      return;
    }
    state = SI.sanitizeSetupDraft(state, showContextForSanitize());
  }

  function readSetupFormState() {
    const episodeInput = document.getElementById("f-episodeName");
    if (episodeInput) {
      state.episodeName = episodeInput.value;
    }
    const linkInput = document.getElementById("f-riversideLink");
    if (linkInput) {
      state.riversideLink = linkInput.value;
    }
    state.speakers.forEach((speaker, index) => {
      const nameInput = document.getElementById(`f-sp-${index}-name`);
      if (nameInput) {
        speaker.name = nameInput.value;
      }
      const trackInput = document.getElementById(`f-sp-${index}-source`);
      if (trackInput && trackInput.type === "text") {
        speaker.trackLabel = trackInput.value;
      }
      ES.SOCIAL_NETWORKS.forEach((net) => {
        const socialInput = document.getElementById(`f-sp-${index}-social-${net.key}`);
        if (socialInput) {
          speaker.social[net.key] = socialInput.value;
        }
      });
    });
    sanitizeSetupState();
  }

  function clearSpeakerAutofillLeak() {
    if (!SI) {
      return;
    }
    const show = showContextForSanitize();
    state.speakers.forEach((speaker, index) => {
      const nameInput = document.getElementById(`f-sp-${index}-name`);
      if (nameInput && !trim(speaker.name) && SI.isShowContextLabel(nameInput.value, show, state)) {
        nameInput.value = "";
      }
      const trackInput = document.getElementById(`f-sp-${index}-source`);
      if (trackInput && trackInput.type === "text" && !trim(speaker.trackLabel)
        && SI.isShowContextLabel(trackInput.value, show, state)) {
        trackInput.value = "";
      }
    });
  }

  function trim(value) {
    return typeof value === "string" ? value.trim() : "";
  }

  function renderSetup() {
    lastView = "setup";
    sanitizeSetupState();
    setPageIntro("episode-setup");
    root.innerHTML = "";
    setStep("Step 1 of 8 · Set up episode");
    state.sourceMode = ES.normalizeMode(state.sourceMode);

    const form = el("form", { class: "setup setup-import", novalidate: true });
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      onContinue();
    });

    form.appendChild(
      el(
        "div",
        { class: "setup-import-head" },
        el("p", { class: "eyebrow" }, "Episode import"),
        el("h2", {}, "Set up your recording and speakers"),
        el(
          "p",
          { class: "hint" },
          "Import your synced sources, assign each speaker, and add social links — then continue to audio polish and style.",
        ),
      ),
    );

    form.appendChild(renderImportFlowOutline());

    const identityBanner = renderShowIdentityBanner();
    if (identityBanner) {
      form.appendChild(identityBanner);
    }

    if (showErrors && errors && Object.keys(errors).length) {
      form.appendChild(
        el(
          "div",
          { class: "banner", role: "alert", tabindex: "-1", id: "error-banner" },
          el("strong", {}, "A few things need a quick fix:"),
          el(
            "ul",
            {},
            // Show up to the first handful of messages so the banner stays scannable.
            (function () {
              const seen = {};
              const items = [];
              Object.keys(errors).forEach((k) => {
                const msg = errors[k];
                if (!seen[msg]) {
                  seen[msg] = true;
                  items.push(el("li", {}, msg));
                }
              });
              return items;
            })(),
          ),
        ),
      );
    }

    // Episode details
    const nameInput = el("input", {
      id: "f-episodeName",
      type: "text",
      value: state.episodeName,
      placeholder: "e.g. Episode 12 — Building in Public",
      "aria-invalid": isInvalid("episodeName") ? "true" : null,
    });
    nameInput.addEventListener("input", (e) => {
      state.episodeName = e.target.value;
      sanitizeSetupState();
    });

    const detailsCard = el(
      "section",
      { class: "card setup-section setup-section-episode" },
      setupSectionHeader(1, "Episode details", "Name this episode so it is easy to find in your show library."),
      field("Episode name", nameInput, "episodeName"),
    );
    form.appendChild(detailsCard);

    // Recording source
    const modeButtons = ES.SOURCE_MODES.map((mode) => {
      const id = `mode-${mode.key}`;
      const input = el("input", {
        id,
        type: "radio",
        name: "sourceMode",
        value: mode.key,
        checked: state.sourceMode === mode.key,
      });
      input.addEventListener("change", () => {
        state.sourceMode = mode.key;
        renderSetup();
      });
      return el("label", { class: "mode-option", for: id }, input, el("span", {}, mode.label));
    });

    const sourceCard = el(
      "section",
      { class: "card setup-section setup-section-source" },
      setupSectionHeader(2, "Recording source", "Choose how you recorded — Riverside link or separate synced speaker files."),
      el("div", { class: "mode-row" }, modeButtons),
    );

    if (state.sourceMode === "riverside") {
      const linkInput = el("input", {
        id: "f-riversideLink",
        type: "url",
        value: state.riversideLink,
        placeholder: "https://riverside.fm/studio/your-episode",
        "aria-invalid": isInvalid("riversideLink") ? "true" : null,
      });
      linkInput.addEventListener("input", (e) => {
        state.riversideLink = e.target.value;
      });
      sourceCard.appendChild(
        field("Riverside recording link", linkInput, "riversideLink", "Paste the link to your Riverside recording session."),
      );
    } else {
      sourceCard.appendChild(
        el("p", { class: "hint" }, "Add a separate synced video file for each speaker in the cards below."),
      );
    }
    form.appendChild(sourceCard);

    // Speakers & sources
    const speakerStack = el("div", { class: "speaker-stack" });
    state.speakers.forEach((speaker, index) => {
      speakerStack.appendChild(renderSpeaker(speaker, index));
    });

    const speakersCard = el(
      "section",
      { class: "card setup-section setup-speakers-card" },
      setupSectionHeader(
        3,
        "Speakers & sources",
        "One card per speaker — assign Host, Guest 1, or Guest 2 and attach each synced source.",
      ),
      renderSpeakerRoleOverview(),
      speakerStack,
    );

    const addButton = el("button", { type: "button", class: "btn-secondary setup-add-speaker-btn" }, "+ Add speaker source");
    addButton.addEventListener("click", () => {
      readSetupFormState();
      state.speakers.push(ES.createSpeaker(nextRole()));
      sanitizeSetupState();
      renderSetup();
    });
    speakersCard.appendChild(addButton);
    form.appendChild(speakersCard);

    if (TM) {
      const saved = TM.listTemplates(templateStore);
      if (saved.length || GAL) {
        form.appendChild(renderSavedTemplatesCard(saved, null));
      }
    }

    if (activeShowId) {
      form.appendChild(
        el(
          "aside",
          { class: "setup-draft-review" },
          el("p", { class: "setup-draft-review-text" },
            el("strong", {}, "Draft saved to your show"),
            " — Continue when speakers and sources are ready, or use ",
            el("strong", {}, "Back to show"),
            " anytime to review this draft in your episode list.",
          ),
        ),
      );
    }

    form.appendChild(
      el(
        "div",
        { class: "actions setup-actions setup-cta-bar" },
        activeShowId
          ? el("button", { type: "button", class: "btn-secondary", id: "setup-back-show" }, "← Back to show")
          : null,
        el("button", { type: "submit", class: "btn-primary setup-continue-btn" }, "Continue to audio polish →"),
      ),
    );

    root.appendChild(form);
    clearSpeakerAutofillLeak();
    const backShow = document.getElementById("setup-back-show");
    if (backShow) {
      backShow.addEventListener("click", () => {
        persistEpisodeSession();
        renderShowDetail(activeShowId);
      });
    }

    if (showErrors) {
      focusFirstError();
    }
    persistEpisodeSession();
  }

  function renderSpeaker(speaker, index) {
    const bucketClass = ES.speakerBucketCueClass(speaker.role);
    const card = el("article", { class: `speaker speaker-card ${bucketClass}` });
    const roleBadge = el("span", { class: `speaker-role-badge ${bucketClass}` }, speaker.role || "Unassigned");
    const header = el(
      "div",
      { class: "speaker-head" },
      el(
        "div",
        { class: "speaker-head-main" },
        el("span", { class: "speaker-tag" }, `Source ${index + 1}`),
        roleBadge,
      ),
    );
    const removeButton = el("button", {
      type: "button",
      class: "link-button",
      "aria-label": `Remove source ${index + 1}`,
      disabled: state.speakers.length <= 1 ? true : null,
    }, "Remove");
    removeButton.addEventListener("click", () => {
      if (state.speakers.length > 1) {
        readSetupFormState();
        state.speakers.splice(index, 1);
        sanitizeSetupState();
        renderSetup();
      }
    });
    header.appendChild(removeButton);
    card.appendChild(header);

    const body = el("div", { class: "speaker-body" });
    const core = el("div", { class: "speaker-core" });

    // Name
    const nameInput = el("input", {
      id: `f-sp-${index}-name`,
      type: "text",
      value: speaker.name,
      placeholder: "Enter speaker name",
      autocomplete: "off",
      "data-lpignore": "true",
      "aria-invalid": isInvalid(`speaker:${index}:name`) ? "true" : null,
    });
    nameInput.addEventListener("input", (e) => {
      speaker.name = e.target.value;
    });
    core.appendChild(field("Speaker name", nameInput, `speaker:${index}:name`));

    // Role bucket
    const roleSelect = el("select", {
      id: `f-sp-${index}-role`,
      "aria-invalid": isInvalid(`speaker:${index}:role`) ? "true" : null,
    });
    ES.SPEAKER_BUCKETS.forEach((bucket) => {
      const option = el("option", { value: bucket, selected: speaker.role === bucket ? true : null }, bucket);
      roleSelect.appendChild(option);
    });
    roleSelect.addEventListener("change", (e) => {
      speaker.role = e.target.value;
      roleBadge.textContent = speaker.role;
      const chip = document.querySelector(`[data-role-chip="${index}"]`);
      if (chip) {
        chip.textContent = speaker.role;
      }
      syncSpeakerBucketCues(speaker.role, card, roleBadge, chip);
    });
    core.appendChild(field("Role", roleSelect, `speaker:${index}:role`));

    const identityGroup = el(
      "div",
      { class: "speaker-group speaker-identity-group" },
      el("h4", { class: "speaker-group-title" }, "Who is speaking"),
      core,
    );
    body.appendChild(identityGroup);

    // Source: file (upload) or optional channel label (riverside)
    const sourceBlock = el("div", { class: "speaker-source-block" });
    if (state.sourceMode === "upload") {
      const fileInput = el("input", {
        id: `f-sp-${index}-source`,
        type: "file",
        accept: "video/*",
        "aria-invalid": isInvalid(`speaker:${index}:source`) ? "true" : null,
      });
      const chosen = el(
        "p",
        { class: "chosen-file" },
        speaker.fileName ? `Selected: ${speaker.fileName}` : "No file chosen yet",
      );
      fileInput.addEventListener("change", (e) => {
        const file = e.target.files && e.target.files[0];
        speaker.fileName = file ? file.name : "";
        speaker.fileSize = file ? file.size : 0;
        chosen.textContent = speaker.fileName ? `Selected: ${speaker.fileName}` : "No file chosen yet";
      });
      sourceBlock.appendChild(field("Speaker video file", fileInput, `speaker:${index}:source`));
      sourceBlock.appendChild(chosen);
    } else {
      const trackInput = el("input", {
        id: `f-sp-${index}-source`,
        type: "text",
        value: speaker.trackLabel,
        placeholder: "e.g. Track 1 (optional)",
        autocomplete: "off",
        "data-lpignore": "true",
      });
      trackInput.addEventListener("input", (e) => {
        speaker.trackLabel = e.target.value;
      });
      sourceBlock.appendChild(field("Channel label", trackInput, null, "Optional — name this speaker's channel in the recording."));
    }

    const recordingGroup = el(
      "div",
      { class: "speaker-group speaker-recording-group" },
      el("h4", { class: "speaker-group-title" }, "Synced recording"),
      sourceBlock,
    );
    body.appendChild(recordingGroup);

    // Optional social links
    const social = el("details", { class: "social speaker-group speaker-social-group" });
    social.appendChild(el("summary", {}, "Social links (optional)"));
    const socialHint = el(
      "p",
      { class: "hint" },
      "Used only to spell names right and add relevant context — never to surface personal details.",
    );
    social.appendChild(socialHint);
    ES.SOCIAL_NETWORKS.forEach((net) => {
      const input = el("input", {
        id: `f-sp-${index}-social-${net.key}`,
        type: "url",
        value: speaker.social[net.key] || "",
        placeholder: `${net.label} URL`,
        "aria-invalid": isInvalid(`speaker:${index}:social:${net.key}`) ? "true" : null,
      });
      input.addEventListener("input", (e) => {
        speaker.social[net.key] = e.target.value;
      });
      social.appendChild(field(net.label, input, `speaker:${index}:social:${net.key}`));
    });
    body.appendChild(social);
    card.appendChild(body);

    return card;
  }

  function onContinue() {
    const result = ES.validateDraft(state);
    errors = result.errors;
    showErrors = true;
    if (result.ok) {
      const summary = ES.summarize(state);
      if (SC && !contextApproved) {
        contextReview = SC.createReview(summary);
        renderContextReview(summary);
      } else if (AP && !appliedAudioPolish) {
        audioPolish = AP.createPolish(summary);
        renderAudioPolish(summary);
      } else if (STY && !appliedStyle) {
        renderStyle(summary);
      } else {
        renderWorkspace(summary);
      }
    } else {
      renderSetup();
    }
  }

  function focusFirstError() {
    const keys = Object.keys(errors);
    if (!keys.length) {
      return;
    }
    const banner = document.getElementById("error-banner");
    if (banner) {
      banner.focus();
    }
    const target = document.getElementById(fieldId(keys[0]));
    if (target && typeof target.scrollIntoView === "function") {
      target.scrollIntoView({ block: "center" });
    }
  }

  // ---- Workspace summary view -------------------------------------------------

  function buildReviewContext(summary) {
    const exportCtx = buildExportContext(summary);
    return Object.assign({}, exportCtx, {
      contextApproved: contextApproved,
      hasCanvas: Boolean(canvasDoc),
      momentsBoard: momentsBoard,
      captionCount: PR ? PR.countVisibleCaptions(momentsBoard) : 0,
    });
  }

  function refreshPublishReview(summary) {
    if (!PR) {
      return null;
    }
    const next = PR.createReview(summary, buildReviewContext(summary));
    if (publishReview && publishReview.approved) {
      if (PR.canApprove(next)) {
        next.approved = true;
        next.approvedAt = publishReview.approvedAt;
      } else {
        publishReviewApproved = false;
      }
    }
    publishReview = next;
    publishReviewApproved = Boolean(publishReview.approved);
    return publishReview;
  }

  function buildWorkspaceContext(summary) {
    const exportCtx = buildExportContext(summary);
    refreshPublishReview(summary);
    const exportReady = EXP ? EXP.validateReadiness(exportCtx).ok : false;
    return {
      appliedStyle: exportCtx.appliedStyle,
      audioPolish: exportCtx.audioPolish,
      templateName: exportCtx.templateName,
      momentsSummary: exportCtx.momentsSummary,
      contextApproved: contextApproved,
      exportReady: exportReady,
      publishReviewApproved: publishReviewApproved,
      correctionApproved: correctionApproved,
      exportStatus: exportJob ? exportJob.status : "draft",
      exportDownloadName: exportJob && exportJob.downloadName ? exportJob.downloadName : "",
    };
  }

  function navigateWorkspaceStage(target, summary) {
    if (target === "setup") {
      renderSetup();
      return;
    }
    if (target === "context") {
      if (!contextReview) {
        contextReview = SC.createReview(summary);
      }
      renderContextReview(summary);
      return;
    }
    if (target === "audio") {
      if (!audioPolish) {
        audioPolish = AP.createPolish(summary);
      }
      renderAudioPolish(summary);
      return;
    }
    if (target === "style") {
      renderStyle(summary);
      return;
    }
    if (target === "canvas") {
      openCanvasEditor(summary);
      return;
    }
    if (target === "moments") {
      renderVisualMoments(summary);
      return;
    }
    if (target === "review") {
      renderPublishReview(summary);
      return;
    }
    if (target === "correction") {
      renderTranscriptCorrection(summary);
      return;
    }
    if (target === "export") {
      renderExport(summary);
      return;
    }
    renderWorkspace(summary);
  }

  function navigateReviewFix(target, summary) {
    if (target === "setup") {
      renderSetup();
      return;
    }
    if (target === "context") {
      if (!contextReview) {
        contextReview = SC.createReview(summary);
      }
      renderContextReview(summary);
      return;
    }
    if (target === "audio") {
      if (!audioPolish) {
        audioPolish = AP.createPolish(summary);
      }
      renderAudioPolish(summary);
      return;
    }
    if (target === "style") {
      renderStyle(summary);
      return;
    }
    if (target === "canvas") {
      openCanvasEditor(summary);
      return;
    }
    if (target === "moments") {
      renderVisualMoments(summary);
      return;
    }
    renderWorkspace(summary);
  }

  function applyContextEffects() {
    if (!SC || !contextReview || !contextReview.approved) {
      return;
    }
    if (momentsBoard) {
      momentsBoard = SC.applyReviewToMoments(momentsBoard, contextReview);
    }
    if (canvasDoc) {
      canvasDoc = SC.applyReviewToCanvas(canvasDoc, contextReview);
    }
  }

  function ensureCorrectionReview(summary) {
    if (!TC) {
      return null;
    }
    ensureMomentsBoard(summary);
    if (!correctionReview) {
      correctionReview = TC.createCorrectionReview(summary, {
        contextReview: contextReview,
        momentsBoard: momentsBoard,
      });
    }
    return correctionReview;
  }

  function applyCorrectionEffects() {
    if (!TC || !correctionReview || !correctionReview.approved) {
      return;
    }
    const applied = TC.applyCorrectionReview(correctionReview, {
      momentsBoard: momentsBoard,
      canvasDoc: canvasDoc,
      publishPackage: publishPackage,
      speakers: state.speakers,
    });
    if (applied.momentsBoard) {
      momentsBoard = applied.momentsBoard;
    }
    if (applied.canvasDoc) {
      canvasDoc = applied.canvasDoc;
    }
    if (applied.publishPackage) {
      publishPackage = applied.publishPackage;
    }
    if (applied.speakers) {
      state.speakers = applied.speakers;
    }
  }

  function buildPublishPackageContext(summary) {
    const show = activeShowId && LIB ? LIB.getShow(showLibrary, activeShowId) : null;
    return {
      showName: show ? show.name : summary.episodeName,
      momentsBoard: momentsBoard,
      brandKit: getActiveBrandKit(),
      brandKitSummary: brandKitSummary(),
      appliedStyle: brandedAppliedStyle(summary),
    };
  }

  function ensurePublishPackage(summary) {
    if (!PP) {
      return null;
    }
    applyCorrectionEffects();
    if (!publishPackage) {
      publishPackage = PP.createPackage(summary, buildPublishPackageContext(summary));
    }
    return publishPackage;
  }

  function buildExportContext(summary) {
    applyCorrectionEffects();
    const templateName = activeTemplateId && TM
      ? (TM.getTemplate(templateStore, activeTemplateId) || {}).name
      : "";
    let momentsSummary = null;
    if (VM && momentsBoard) {
      momentsSummary = VM.summarizeBoard(momentsBoard);
    }
    const contextSummary = SC && contextReview && contextReview.approved
      ? SC.summarizeReview(contextReview)
      : null;
    return {
      audioPolish: appliedAudioPolish,
      appliedStyle: brandedAppliedStyle(summary),
      templateName: templateName || "",
      momentsSummary: momentsSummary,
      contextSummary: contextSummary,
      brandKitSummary: brandKitSummary(),
      publishPackageSummary: publishPackage && PP ? PP.summarizePackage(publishPackage) : null,
      correctionSummary: correctionReview && correctionReview.approved && TC
        ? TC.summarizeCorrection(correctionReview)
        : null,
    };
  }

  function renderWorkspace(summary) {
    workspaceSummaryCache = summary;
    lastView = "workspace";
    root.innerHTML = "";

    const view = el("div", { class: "workspace guided-workspace" });
    const identityBanner = renderShowIdentityBanner();
    if (identityBanner) {
      view.appendChild(identityBanner);
    }
    view.appendChild(
      el(
        "div",
        { class: "workspace-head" },
        el("p", { class: "eyebrow" }, "Production workspace"),
        el("h2", {}, summary.episodeName),
        el("p", { class: "hint" }, "One self-serve flow from import to publish. Each stage shows what is ready and what still needs attention."),
      ),
    );

    if (WS) {
      ensureMomentsBoard(summary);
      const ws = WS.buildWorkspace(summary, buildWorkspaceContext(summary));
      const wsSummary = WS.summarizeWorkspace(ws);
      const currentStage = WS.getStage(ws, ws.currentStageId);
      setWorkspaceStep(ws.currentStageId);

      if (currentStage) {
        const nextActionBtn = el(
          "button",
          { type: "button", class: "btn-primary workspace-next-action-btn" },
          `${currentStage.actionLabel} →`,
        );
        nextActionBtn.addEventListener("click", function () {
          navigateWorkspaceStage(currentStage.actionTarget, summary);
        });
        view.appendChild(
          el(
            "section",
            { class: "card workspace-next-action" },
            el("p", { class: "eyebrow workspace-next-action-eyebrow" }, "Your next step"),
            el("h3", {}, currentStage.label),
            el("p", { class: "hint workspace-next-action-summary" }, currentStage.summary),
            el("div", { class: "workspace-next-action-cta" }, nextActionBtn),
          ),
        );
      }

      view.appendChild(
        el(
          "section",
          { class: "card workspace-progress workspace-progress-hero" },
          el("h3", {}, "Episode progress"),
          el("p", { class: "workspace-progress-line" }, wsSummary.progressLine),
          el("p", { class: "hint workspace-next-hint" }, wsSummary.workspaceLine),
        ),
      );

      const pipeline = el("section", { class: "card workspace-pipeline" }, el("h3", {}, "Production stages"));
      const stageList = el("div", { class: "workspace-stages" });
      ws.stages.forEach(function (item) {
        const statusLabel = item.status === "complete"
          ? "Complete"
          : item.status === "active"
            ? "Ready now"
            : item.status === "attention"
              ? "Recommended"
              : "Not started";
        const row = el(
          "div",
          { class: `workspace-stage workspace-stage-${item.status}${item.id === ws.currentStageId ? " workspace-stage-current" : ""}` },
          el(
            "div",
            { class: "workspace-stage-main" },
            el("span", { class: "workspace-stage-status" }, statusLabel),
            el("span", { class: "workspace-stage-label" }, item.label),
            el("p", { class: "workspace-stage-summary" }, item.summary),
          ),
        );
        const openButton = el("button", { type: "button", class: item.status === "active" ? "primary" : "ghost" }, `${item.actionLabel} →`);
        openButton.addEventListener("click", function () {
          navigateWorkspaceStage(item.actionTarget, summary);
        });
        row.appendChild(el("div", { class: "workspace-stage-actions" }, openButton));
        stageList.appendChild(row);
      });
      pipeline.appendChild(stageList);
      view.appendChild(pipeline);
    }

    const kitSummary = brandKitSummary();
    if (kitSummary && kitSummary.reviewLine) {
      view.appendChild(
        el(
          "section",
          { class: "card brand-kit-workspace-card" },
          el("h3", {}, "Show brand kit"),
          el("p", { class: "brand-kit-line" }, kitSummary.reviewLine),
          kitSummary.colorSummary ? el("p", { class: "hint" }, `Colors: ${kitSummary.colorSummary}`) : null,
          activeTemplateId && TM
            ? el("p", { class: "hint" }, `Saved template: ${(TM.getTemplate(templateStore, activeTemplateId) || {}).name || activeTemplateId}`)
            : null,
        ),
      );
    } else if (startingFromShowIdentity && activeTemplateId && TM) {
      const template = TM.getTemplate(templateStore, activeTemplateId);
      if (template) {
        view.appendChild(
          el(
            "section",
            { class: "card brand-kit-workspace-card" },
            el("h3", {}, "Saved show template"),
            el("p", { class: "brand-kit-line" }, template.name),
          ),
        );
      }
    }

    const editSetup = el("button", { type: "button", class: "ghost" }, "← Edit setup");
    editSetup.addEventListener("click", function () {
      showErrors = false;
      contextApproved = false;
      contextReview = null;
      correctionApproved = false;
      correctionReview = null;
      publishReviewApproved = false;
      publishReview = null;
      renderSetup();
    });
    view.appendChild(el("div", { class: "actions workspace-actions" }, editSetup));

    if (TM) {
      const saved = TM.listTemplates(templateStore);
      if (saved.length || GAL) {
        view.appendChild(renderSavedTemplatesCard(saved, summary));
      }
    }

    root.appendChild(view);
    view.scrollIntoView({ block: "start" });
    persistEpisodeSession();
  }

  function renderPublishReview(summary) {
    if (!PR) {
      renderWorkspace(summary);
      return;
    }
    refreshPublishReview(summary);
    root.innerHTML = "";
    setStep("Step 7 of 8 · Publish review");

    const view = el("div", { class: "publish-review-step" });
    view.appendChild(
      el("div", { class: "workspace-head" },
        el("p", { class: "eyebrow" }, "Publish review"),
        el("h2", {}, `Review ${summary.episodeName} before export`),
        el(
          "p",
          { class: "hint" },
          "Walk the full episode from setup through visual moments. Fix required items, then approve when you are confident the long-form result is publish-ready.",
        ),
      ),
    );

    const grid = el("div", { class: "publish-review-layout" });

    const timelineCard = el("section", { class: "card" }, el("h3", {}, "Episode timeline"));
    const timeline = el("div", { class: "publish-review-timeline" });
    publishReview.timeline.forEach((section) => {
      timeline.appendChild(
        el(
          "div",
          { class: `publish-review-section publish-review-${section.status}` },
          el("span", { class: "publish-review-time" }, section.time),
          el("span", { class: "publish-review-label" }, section.label),
          el("span", { class: "publish-review-summary" }, section.summary),
        ),
      );
    });
    timelineCard.appendChild(timeline);
    grid.appendChild(timelineCard);

    const checksCard = el("section", { class: "card" }, el("h3", {}, "Quality checks"));
    const reviewMeta = PR.summarizeReview(publishReview);
    checksCard.appendChild(el("p", { class: "publish-review-meta" }, reviewMeta.reviewLine));

    const checksList = el("div", { class: "publish-review-checks" });
    publishReview.checks.forEach((item) => {
      if (item.tone === "ok") {
        return;
      }
      const row = el(
        "div",
        { class: `publish-review-check publish-review-check-${item.tone}` },
        el("strong", {}, item.title),
        el("p", {}, item.message),
      );
      if (item.action && item.action.label) {
        const fixButton = el("button", { type: "button", class: "ghost" }, item.action.label);
        fixButton.addEventListener("click", () => navigateReviewFix(item.action.target, summary));
        row.appendChild(fixButton);
      }
      checksList.appendChild(row);
    });
    if (!checksList.childNodes.length) {
      checksList.appendChild(el("p", { class: "hint" }, "Everything looks good — approve when you are ready to export."));
    }
    checksCard.appendChild(checksList);

    const passed = el("div", { class: "publish-review-passed" });
    publishReview.checks.filter((item) => item.tone === "ok").forEach((item) => {
      passed.appendChild(el("p", { class: "publish-review-ok" }, `✓ ${item.title}`));
    });
    checksCard.appendChild(passed);
    grid.appendChild(checksCard);
    view.appendChild(grid);

    if (TC) {
      ensureMomentsBoard(summary);
      const correctionSummary = correctionReview && correctionReview.approved
        ? TC.summarizeCorrection(correctionReview)
        : null;
      const correctionCard = el("section", { class: "card transcript-correction-banner" }, el("h3", {}, "Transcript & captions"));
      correctionCard.appendChild(
        el(
          "p",
          { class: "hint" },
          "Fix speaker names, brand spellings, and caption text once — corrections carry through captions, visual moments, export metadata, and your publish package.",
        ),
      );
      if (correctionSummary && correctionSummary.reviewLine) {
        correctionCard.appendChild(el("p", { class: "transcript-correction-line" }, correctionSummary.reviewLine));
      }
      const correctionButton = el(
        "button",
        { type: "button", class: correctionApproved ? "ghost" : "primary" },
        correctionApproved ? "Edit transcript corrections" : "Review transcript & captions →",
      );
      correctionButton.addEventListener("click", () => renderTranscriptCorrection(summary, { returnTo: "review" }));
      correctionCard.appendChild(el("div", { class: "actions transcript-correction-actions" }, correctionButton));
      view.appendChild(correctionCard);
    }

    const approveError = el("p", { class: "field-error", role: "alert", hidden: true });
    const approveButton = el(
      "button",
      {
        type: "button",
        class: "primary",
        disabled: publishReviewApproved || !PR.canApprove(publishReview) ? true : null,
      },
      publishReviewApproved ? "Approved for export" : "Approve for export →",
    );
    approveButton.addEventListener("click", () => {
      const result = PR.approveReview(publishReview);
      if (!result.ok) {
        approveError.hidden = false;
        approveError.textContent = result.error;
        return;
      }
      publishReview = result.review;
      publishReviewApproved = true;
      approveError.hidden = true;
      renderPublishReview(summary);
    });

    const exportButton = el(
      "button",
      { type: "button", class: "ghost", disabled: publishReviewApproved ? null : true },
      "Continue to publish package →",
    );
    exportButton.addEventListener("click", () => renderPublishPackage(summary));

    const back = el("button", { type: "button", class: "ghost" }, "← Back to workspace");
    back.addEventListener("click", () => renderWorkspace(summary));
    view.appendChild(approveError);
    view.appendChild(el("div", { class: "actions" }, approveButton, exportButton, back));

    root.appendChild(view);
    view.scrollIntoView({ block: "start" });
  }

  // ---- Transcript & caption correction (#63) ---------------------------------

  function renderTranscriptCorrection(summary, options) {
    if (!TC) {
      renderPublishReview(summary);
      return;
    }
    ensureCorrectionReview(summary);
    const returnTo = options && options.returnTo;
    root.innerHTML = "";
    setStep("Transcript review · Fix names & captions");

    const view = el("div", { class: "transcript-correction-step" });
    view.appendChild(
      el(
        "div",
        { class: "workspace-head" },
        el("p", { class: "eyebrow" }, "Transcript & caption review"),
        el("h2", {}, `Correct wording for ${summary.episodeName}`),
        el(
          "p",
          { class: "hint" },
          "Edit speaker labels and key caption lines pulled from your episode and social context. Approved corrections update on-screen captions, title moments, export metadata, and publish package copy.",
        ),
      ),
    );

    const layout = el("div", { class: "transcript-correction-layout" });

    const speakersCard = el("section", { class: "card" }, el("h3", {}, "Speaker labels"));
    correctionReview.speakers.forEach((speaker) => {
      const card = el("section", { class: "transcript-speaker-card" });
      card.appendChild(el("h4", {}, speaker.role));

      function bindSpeakerInput(label, key, value, hint) {
        const input = el("input", {
          id: `tc-speaker-${speaker.role}-${key}`,
          type: "text",
          value: value || "",
        });
        input.addEventListener("input", (e) => {
          correctionReview = TC.updateSpeaker(correctionReview, speaker.role, { [key]: e.target.value });
        });
        card.appendChild(field(label, input, null, hint));
      }

      bindSpeakerInput("On-screen name", "label", speaker.label, "How this speaker's name appears in captions and credits.");
      bindSpeakerInput("Brand or show", "brand", speaker.brand, "Company, show, or personal brand spelling.");
      bindSpeakerInput(
        "Topic terms",
        "topicTerms",
        (speaker.topicTerms || []).join(", "),
        "Comma-separated terms to keep consistent in titles and callouts.",
      );
      speakersCard.appendChild(card);
    });
    layout.appendChild(speakersCard);

    const linesCard = el("section", { class: "card" }, el("h3", {}, "Key lines"));
    linesCard.appendChild(
      el("p", { class: "hint" }, "Captions, titles, and transcript segments that appear in the finished episode."),
    );
    const lineList = el("div", { class: "transcript-line-list" });
    correctionReview.lines.forEach((line) => {
      const row = el("div", { class: "transcript-line-row" });
      row.appendChild(
        el(
          "div",
          { class: "transcript-line-meta" },
          el("span", { class: "transcript-line-time" }, line.time),
          el("span", { class: "transcript-line-kind" }, line.kind),
          el("span", { class: "transcript-line-speaker" }, line.speakerLabel || line.speakerRole),
        ),
      );
      const textInput = el("textarea", {
        id: `tc-line-${line.id}`,
        rows: "2",
        class: "transcript-line-text",
      }, line.text || "");
      textInput.addEventListener("input", (e) => {
        correctionReview = TC.updateLine(correctionReview, line.id, { text: e.target.value });
      });
      row.appendChild(field("Caption / line text", textInput));
      lineList.appendChild(row);
    });
    linesCard.appendChild(lineList);
    layout.appendChild(linesCard);
    view.appendChild(layout);

    const approveError = el("p", { class: "field-error", role: "alert", hidden: true });
    const approveButton = el(
      "button",
      { type: "button", class: "primary" },
      correctionApproved ? "Re-apply corrections →" : "Apply corrections →",
    );
    approveButton.addEventListener("click", () => {
      if (!correctionReview.lines.length && !correctionReview.speakers.length) {
        approveError.hidden = false;
        approveError.textContent = "Add visual moments or speakers before applying corrections.";
        return;
      }
      correctionReview = TC.approveCorrection(correctionReview);
      correctionApproved = true;
      applyCorrectionEffects();
      persistMoments();
      approveError.hidden = true;
      if (returnTo === "package") {
        renderPublishPackage(summary);
      } else if (returnTo === "export") {
        renderExport(summary);
      } else {
        renderPublishReview(summary);
      }
    });

    const backTarget = returnTo === "package"
      ? () => renderPublishPackage(summary)
      : returnTo === "export"
        ? () => renderExport(summary)
        : () => renderPublishReview(summary);
    const back = el("button", { type: "button", class: "ghost" }, "← Back");
    back.addEventListener("click", backTarget);
    view.appendChild(approveError);
    view.appendChild(el("div", { class: "actions" }, approveButton, back));

    root.appendChild(view);
    view.scrollIntoView({ block: "start" });
  }

  // ---- Publish package (#60) --------------------------------------------------

  function renderPublishPackageThumbnail(thumb, selected) {
    const card = el(
      "button",
      {
        type: "button",
        class: `publish-thumb-card${selected ? " selected" : ""}`,
        "aria-pressed": selected ? "true" : "false",
      },
      el("span", { class: "publish-thumb-preview" }, (function () {
        const preview = el("span", { class: "publish-thumb-frame" });
        preview.style.background = thumb.background;
        preview.style.color = thumb.text;
        preview.style.borderColor = thumb.accent;
        if (thumb.logoLabel) {
          preview.appendChild(el("span", { class: "publish-thumb-logo" }, thumb.logoLabel));
        }
        preview.appendChild(el("span", { class: "publish-thumb-headline" }, thumb.headline));
        preview.appendChild(el("span", { class: "publish-thumb-tagline" }, thumb.tagline));
        return preview;
      })()),
      el("span", { class: "publish-thumb-label" }, thumb.label),
    );
    return card;
  }

  function renderPublishPackage(summary) {
    if (!PP) {
      renderExport(summary);
      return;
    }
    refreshPublishReview(summary);
    const reviewGate = PR ? PR.validateExportGate(publishReview) : { ok: true };
    if (!reviewGate.ok) {
      renderExport(summary);
      return;
    }

    ensurePublishPackage(summary);
    root.innerHTML = "";
    setStep("Publish package · Ready to upload");

    const view = el("div", { class: "publish-package-step" });
    view.appendChild(
      el(
        "div",
        { class: "workspace-head" },
        el("p", { class: "eyebrow" }, "Publish package"),
        el("h2", {}, "Publishing assets for upload"),
        el("p", { class: "hint" }, "Edit the title, description, chapters, credits, and thumbnail before you publish."),
      ),
    );

    const form = el("div", { class: "publish-package-layout" });

    const detailsCard = el("section", { class: "card" }, el("h3", {}, "Episode details"));
    const titleInput = el("input", { id: "publish-title", type: "text", value: publishPackage.title });
    titleInput.addEventListener("input", (e) => {
      publishPackage = PP.updatePackage(publishPackage, { title: e.target.value });
    });
    detailsCard.appendChild(field("Episode title", titleInput));

    const descriptionInput = el("textarea", { id: "publish-description", rows: "4" }, publishPackage.description);
    descriptionInput.addEventListener("input", (e) => {
      publishPackage = PP.updatePackage(publishPackage, { description: e.target.value });
    });
    detailsCard.appendChild(field("Short description", descriptionInput, null, "Used on YouTube, Spotify, and show notes."));
    form.appendChild(detailsCard);

    const chaptersCard = el("section", { class: "card" }, el("h3", {}, "Chapter markers"));
    const chapterList = el("div", { class: "publish-chapter-list" });
    publishPackage.chapters.forEach((chapter) => {
      const timeInput = el("input", {
        type: "text",
        value: chapter.time,
        class: "publish-chapter-time",
      });
      const labelInput = el("input", {
        type: "text",
        value: chapter.label,
        class: "publish-chapter-label",
      });
      timeInput.addEventListener("change", (e) => {
        publishPackage = PP.updateChapter(publishPackage, chapter.id, { time: e.target.value });
      });
      labelInput.addEventListener("input", (e) => {
        publishPackage = PP.updateChapter(publishPackage, chapter.id, { label: e.target.value });
      });
      chapterList.appendChild(
        el("div", { class: "publish-chapter-row" }, timeInput, labelInput),
      );
    });
    chaptersCard.appendChild(chapterList);
    form.appendChild(chaptersCard);

    const creditsCard = el("section", { class: "card" }, el("h3", {}, "Speaker credits"));
    const creditList = el("div", { class: "publish-credit-list" });
    publishPackage.speakerCredits.forEach((credit) => {
      const nameInput = el("input", { type: "text", value: credit.name, class: "publish-credit-name" });
      const roleInput = el("input", { type: "text", value: credit.role, class: "publish-credit-role" });
      nameInput.addEventListener("input", (e) => {
        publishPackage = PP.updateSpeakerCredit(publishPackage, credit.id, { name: e.target.value });
      });
      roleInput.addEventListener("input", (e) => {
        publishPackage = PP.updateSpeakerCredit(publishPackage, credit.id, { role: e.target.value });
      });
      creditList.appendChild(
        el("div", { class: "publish-credit-row" }, nameInput, roleInput),
      );
    });
    creditsCard.appendChild(creditList);
    form.appendChild(creditsCard);

    const thumbCard = el("section", { class: "card" }, el("h3", {}, "Thumbnail options"));
    thumbCard.appendChild(el("p", { class: "hint" }, "Branded with your show identity — pick the option that fits this episode."));
    const thumbGrid = el("div", { class: "publish-thumb-grid" });
    publishPackage.thumbnailOptions.forEach((thumb) => {
      const card = renderPublishPackageThumbnail(thumb, publishPackage.selectedThumbnailId === thumb.id);
      card.addEventListener("click", () => {
        publishPackage = PP.selectThumbnail(publishPackage, thumb.id);
        renderPublishPackage(summary);
      });
      thumbGrid.appendChild(card);
    });
    thumbCard.appendChild(thumbGrid);
    form.appendChild(thumbCard);

    view.appendChild(form);

    const packageSummary = PP.summarizePackage(publishPackage);
    const previewCard = el("section", { class: "card publish-package-preview" }, el("h3", {}, "Package preview"));
    packageSummary.lines.forEach((line) => {
      previewCard.appendChild(el("p", { class: "export-summary-line" }, line));
    });
    if (TC && correctionReview && correctionReview.approved) {
      const correctionSummary = TC.summarizeCorrection(correctionReview);
      if (correctionSummary.reviewLine) {
        previewCard.appendChild(el("p", { class: "export-summary-line" }, correctionSummary.reviewLine));
      }
    }
    view.appendChild(previewCard);

    const toExport = el("button", { type: "button", class: "primary" }, "Continue to export →");
    toExport.addEventListener("click", () => renderExport(summary));
    const correctionButton = TC
      ? el(
        "button",
        { type: "button", class: "ghost" },
        correctionApproved ? "Edit transcript corrections" : "Review transcript & captions",
      )
      : null;
    if (correctionButton) {
      correctionButton.addEventListener("click", () => renderTranscriptCorrection(summary, { returnTo: "package" }));
    }
    const back = el("button", { type: "button", class: "ghost" }, "← Back to publish review");
    back.addEventListener("click", () => renderPublishReview(summary));
    const actionButtons = correctionButton ? [toExport, correctionButton, back] : [toExport, back];
    view.appendChild(el("div", { class: "actions" }, actionButtons));

    root.appendChild(view);
    view.scrollIntoView({ block: "start" });
  }

  // ---- Export & publish (#30) -------------------------------------------------

  function renderExport(summary) {
    root.innerHTML = "";
    setStep("Step 8 of 8 · Export & publish");
    if (!EXP) {
      return;
    }

    refreshPublishReview(summary);
    const reviewGate = PR ? PR.validateExportGate(publishReview) : { ok: true };
    ensurePublishPackage(summary);
    const ctx = buildExportContext(summary);
    const readiness = EXP.validateReadiness(ctx);
    if (!exportJob) {
      exportJob = EXP.createExport(summary, {
        templateId: activeTemplateId || "",
        templateName: ctx.templateName || "",
      });
    }

    const view = el("div", { class: "export-step" });
    view.appendChild(
      el(
        "div",
        { class: "workspace-head" },
        el("p", { class: "eyebrow" }, "Export & publish"),
        el("h2", {}, `Publish ${summary.episodeName}`),
        el("p", { class: "hint" }, "Choose publishing options and export a long-form video ready to upload."),
      ),
    );

    if (!reviewGate.ok) {
      view.appendChild(
        el(
          "section",
          { class: "card export-blocked" },
          el("h3", {}, "Publish review required"),
          el("p", { class: "field-error" }, reviewGate.error),
        ),
      );
      const toReview = el("button", { type: "button", class: "primary" }, "Open publish review →");
      toReview.addEventListener("click", () => renderPublishReview(summary));
      const backBlocked = el("button", { type: "button", class: "ghost" }, "← Back to workspace");
      backBlocked.addEventListener("click", () => renderWorkspace(summary));
      view.appendChild(el("div", { class: "actions" }, toReview, backBlocked));
      root.appendChild(view);
      view.scrollIntoView({ block: "start" });
      return;
    }

    if (!readiness.ok) {
      view.appendChild(
        el(
          "section",
          { class: "card export-blocked" },
          el("h3", {}, "Not ready to export yet"),
          el("p", { class: "field-error" }, readiness.error),
        ),
      );
      const backBlocked = el("button", { type: "button", class: "ghost" }, "← Back to workspace");
      backBlocked.addEventListener("click", () => renderWorkspace(summary));
      view.appendChild(el("div", { class: "actions" }, backBlocked));
      root.appendChild(view);
      view.scrollIntoView({ block: "start" });
      return;
    }

    const finalSummary = EXP.buildFinalSummary(summary, ctx, exportJob);
    const summaryCard = el("section", { class: "card export-summary" }, el("h3", {}, "Final episode summary"));
    finalSummary.lines.forEach((line) => {
      summaryCard.appendChild(el("p", { class: "export-summary-line" }, line));
    });
    view.appendChild(summaryCard);

    const grid = el("div", { class: "export-layout" });

    const optionsCard = el("section", { class: "card" }, el("h3", {}, "Publishing options"));
    const platformGrid = el("div", { class: "export-option-grid" });
    EXP.PLATFORMS.forEach((platform) => {
      const selected = exportJob.platform === platform.id;
      const card = el(
        "button",
        {
          type: "button",
          class: `export-option-card${selected ? " selected" : ""}`,
          "aria-pressed": selected ? "true" : "false",
        },
        el("span", { class: "export-option-name" }, platform.name),
        el("span", { class: "export-option-tagline" }, platform.tagline),
      );
      card.addEventListener("click", () => {
        exportJob = EXP.updateOption(exportJob, "platform", platform.id);
        renderExport(summary);
      });
      platformGrid.appendChild(card);
    });
    optionsCard.appendChild(field("Platform", platformGrid, null, "Where you plan to publish this episode."));

    const resolutionSelect = el("select", { id: "export-resolution" });
    EXP.RESOLUTIONS.forEach((item) => {
      resolutionSelect.appendChild(
        el("option", { value: item.id, selected: exportJob.resolution === item.id ? true : null }, item.label),
      );
    });
    resolutionSelect.addEventListener("change", (e) => {
      exportJob = EXP.updateOption(exportJob, "resolution", e.target.value);
      renderExport(summary);
    });
    optionsCard.appendChild(field("Resolution", resolutionSelect, null, EXP.getResolution(exportJob.resolution).tagline));

    const captionSelect = el("select", { id: "export-captions" });
    EXP.CAPTION_MODES.forEach((item) => {
      captionSelect.appendChild(
        el("option", { value: item.id, selected: exportJob.captionMode === item.id ? true : null }, item.label),
      );
    });
    captionSelect.addEventListener("change", (e) => {
      exportJob = EXP.updateOption(exportJob, "captionMode", e.target.value);
      renderExport(summary);
    });
    optionsCard.appendChild(field("Captions", captionSelect, null, EXP.getCaptionMode(exportJob.captionMode).tagline));

    if (TM) {
      const saved = TM.listTemplates(templateStore);
      if (saved.length) {
        const templateSelect = el("select", { id: "export-template" });
        templateSelect.appendChild(el("option", { value: "" }, "No saved template"));
        saved.forEach((item) => {
          templateSelect.appendChild(
            el(
              "option",
              {
                value: item.id,
                selected: exportJob.templateId === item.id || (!exportJob.templateId && activeTemplateId === item.id) ? true : null,
              },
              item.name,
            ),
          );
        });
        templateSelect.addEventListener("change", (e) => {
          const picked = saved.find((item) => item.id === e.target.value);
          exportJob = EXP.updateOption(exportJob, "templateId", e.target.value);
          exportJob = EXP.updateOption(exportJob, "templateName", picked ? picked.name : "");
          renderExport(summary);
        });
        optionsCard.appendChild(field("Show template", templateSelect, null, "Reuse a saved layout identity in this export."));
      }
    }

    grid.appendChild(optionsCard);

    const statusCard = el("section", { class: "card export-status-card" }, el("h3", {}, "Export status"));
    const exportSummary = EXP.summarizeExport(exportJob);
    if (exportJob.status === "ready") {
      statusCard.appendChild(
        el("p", { class: "export-ready" }, `Ready to download: ${exportJob.downloadName}`),
      );
      statusCard.appendChild(
        el("p", { class: "hint" }, `${exportSummary.platformName} · ${exportSummary.resolutionLabel} · ${exportSummary.captionLabel}`),
      );
    } else {
      statusCard.appendChild(
        el("p", { class: "hint" }, "Start export when your publishing options look right."),
      );
    }
    grid.appendChild(statusCard);
    view.appendChild(grid);

    const actions = el("div", { class: "actions" });
    if (TC) {
      const correctionButton = el(
        "button",
        { type: "button", class: "ghost" },
        correctionApproved ? "Edit transcript corrections" : "Review transcript & captions",
      );
      correctionButton.addEventListener("click", () => renderTranscriptCorrection(summary, { returnTo: "export" }));
      actions.appendChild(correctionButton);
    }
    const packageButton = el("button", { type: "button", class: "ghost" }, publishPackage ? "Edit publish package" : "Open publish package →");
    packageButton.addEventListener("click", () => renderPublishPackage(summary));
    actions.appendChild(packageButton);
    if (exportJob.status !== "ready") {
      const startButton = el("button", { type: "button", class: "primary" }, "Start export →");
      startButton.addEventListener("click", () => {
        const result = EXP.runExport(exportJob, summary, ctx);
        if (!result.ok) {
          return;
        }
        exportJob = result.state;
        renderExport(summary);
      });
      actions.appendChild(startButton);
    } else {
      const doneButton = el("button", { type: "button", class: "primary" }, "Done — back to workspace");
      doneButton.addEventListener("click", () => renderWorkspace(summary));
      actions.appendChild(doneButton);
    }
    const back = el("button", { type: "button", class: "ghost" }, "← Back to workspace");
    back.addEventListener("click", () => renderWorkspace(summary));
    actions.appendChild(back);
    view.appendChild(actions);

    root.appendChild(view);
    view.scrollIntoView({ block: "start" });
  }

  function galleryListingStatusLine(item) {
    const preset = item.presetName || (item.previewImage && item.previewImage.presetName);
    const tags = GAL ? GAL.displayStyleTags(item.styleTags).slice(0, 2) : [];
    if (preset && tags.length) {
      return `${preset} · ${tags.join(" · ")}`;
    }
    if (preset) {
      return preset;
    }
    if (tags.length) {
      return tags.join(" · ");
    }
    return "Custom episode layout";
  }

  function galleryPreviewSummary(showName) {
    const base = workspaceSummaryCache || ES.summarize(state);
    if (base && base.speakerCount > 0) {
      return base;
    }
    const title = typeof showName === "string" && showName.trim() ? showName.trim() : "Founders Unfiltered";
    return {
      episodeName: `${title} · Episode 12`,
      showName: title,
      speakers: [
        { role: "Host", name: "Sam Rivera" },
        { role: "Guest 1", name: "Dana Kim" },
        { role: "Guest 2", name: "Alex Chen" },
      ],
      speakerCount: 3,
    };
  }

  function renderGalleryPreviewThumb(listing, summary) {
    if (!GAL || !listing) {
      return el("div", { class: "creator-gallery-preview-thumb" });
    }
    const previewSummary = summary || galleryPreviewSummary();
    const styleFromListing = GAL.styleSelectionFromListing(listing);
    const previewCanvas = GAL.applyListingForEpisode(listing, previewSummary, styleFromListing);
    const wrap = el("div", { class: "creator-gallery-preview-thumb" });
    if (previewCanvas) {
      wrap.appendChild(renderCanvasStage(previewCanvas));
    }
    return wrap;
  }

  function renderCreatorGalleryBrowse(summary, options) {
    if (!GAL) {
      return;
    }
    const returnTo = options && options.returnTo;
    const previewSummary = summary || galleryPreviewSummary();
    const listings = GAL.listListings(galleryStore);
    let selectedId = activeGalleryListingId || (listings[0] && listings[0].id) || null;

    root.innerHTML = "";
    setStep("Creator template gallery");

    const view = el("div", { class: "creator-gallery-step" });
    view.appendChild(
      el(
        "div",
        { class: "workspace-head" },
        el("p", { class: "eyebrow" }, "Creator gallery"),
        el("h2", {}, "Browse reusable podcast layouts"),
        el(
          "p",
          { class: "hint" },
          "Preview publish-ready layouts from other creators, then apply frames, captions, overlays, and brand styling to your episode.",
        ),
      ),
    );

    if (!listings.length) {
      const emptyCard = el(
        "section",
        { class: "card creator-gallery-empty" },
        el("h3", {}, "No gallery templates yet"),
        el(
          "p",
          { class: "hint" },
          "Featured templates from other creators appear here. Save a layout from the canvas editor and publish it, or return to the home gallery to start from a featured template.",
        ),
      );
      const featuredBtn = el("button", { type: "button", class: "primary" }, "Browse featured templates →");
      featuredBtn.addEventListener("click", () => {
        seedGalleryDemoData();
        renderCreatorGalleryBrowse(summary, { returnTo: returnTo });
      });
      emptyCard.appendChild(featuredBtn);
      view.appendChild(emptyCard);
      const back = el("button", { type: "button", class: "ghost" }, "← Back");
      back.addEventListener("click", () => {
        if (returnTo === "style" && summary) {
          renderStyle(summary);
        } else if (returnTo === "library") {
          renderShowLibrary();
        } else if (summary) {
          renderWorkspace(summary);
        } else {
          renderSetup();
        }
      });
      view.appendChild(el("div", { class: "actions" }, back));
      root.appendChild(view);
      return;
    }

    const layout = el("div", { class: "creator-gallery-layout" });
    const browsePanel = el("section", { class: "card creator-gallery-browse" }, el("h3", {}, "Gallery listings"));
    const grid = el("div", { class: "creator-gallery-grid" });

    const previewHost = el("section", { class: "card creator-gallery-preview-panel" }, el("h3", {}, "Episode preview"));
    const previewBody = el("div", { class: "creator-gallery-preview-body" });
    const previewMeta = el("div", { class: "creator-gallery-preview-meta" });
    previewHost.appendChild(previewBody);
    previewHost.appendChild(previewMeta);

    function renderSelectedPreview() {
      const listing = selectedId ? GAL.getListing(galleryStore, selectedId) : null;
      previewBody.innerHTML = "";
      previewMeta.innerHTML = "";
      if (!listing) {
        previewBody.appendChild(el("p", { class: "hint" }, "Select a gallery template to preview its layout."));
        return;
      }
      const styleFromListing = GAL.styleSelectionFromListing(listing);
      const previewCanvas = GAL.applyListingForEpisode(listing, previewSummary, styleFromListing);
      previewBody.appendChild(renderCanvasStage(previewCanvas));
      previewMeta.appendChild(el("h4", { class: "creator-gallery-preview-name" }, listing.name));
      if (listing.description) {
        previewMeta.appendChild(el("p", { class: "hint" }, listing.description));
      }
      const visibleTags = GAL ? GAL.displayStyleTags(listing.styleTags) : [];
      if (visibleTags.length) {
        const tags = el("div", { class: "creator-gallery-tags" });
        visibleTags.forEach((tag) => {
          tags.appendChild(el("span", { class: "creator-gallery-tag" }, tag));
        });
        previewMeta.appendChild(tags);
      }
      previewMeta.appendChild(
        el(
          "p",
          { class: "hint creator-gallery-preview-note" },
          `Preview uses ${previewSummary.speakerCount} speaker${previewSummary.speakerCount === 1 ? "" : "s"} from your current episode.`,
        ),
      );
    }

    function renderBrowseGrid() {
      grid.innerHTML = "";
      listings.forEach((item) => {
        const listing = GAL.getListing(galleryStore, item.id);
        const selected = item.id === selectedId;
        const card = el(
          "button",
          {
            type: "button",
            class: `creator-gallery-card${selected ? " selected" : ""}`,
            "aria-pressed": selected ? "true" : "false",
          },
          renderGalleryPreviewThumb(listing, previewSummary),
          el("span", { class: "creator-gallery-card-name" }, item.name),
          el("span", { class: "creator-gallery-card-meta" }, galleryListingStatusLine(item)),
        );
        if (item.description) {
          card.appendChild(el("span", { class: "creator-gallery-card-desc" }, item.description));
        }
        const cardTags = GAL ? GAL.displayStyleTags(item.styleTags).slice(0, 3) : [];
        if (cardTags.length) {
          card.appendChild(el("span", { class: "creator-gallery-card-tags" }, cardTags.join(" · ")));
        }
        card.addEventListener("click", () => {
          selectedId = item.id;
          activeGalleryListingId = item.id;
          renderBrowseGrid();
          renderSelectedPreview();
        });
        grid.appendChild(card);
      });
    }

    renderBrowseGrid();
    renderSelectedPreview();
    browsePanel.appendChild(grid);
    layout.appendChild(browsePanel);
    layout.appendChild(previewHost);
    view.appendChild(layout);

    const applyButton = el("button", { type: "button", class: "primary" }, "Apply gallery template →");
    applyButton.addEventListener("click", () => {
      if (!selectedId) {
        return;
      }
      applyGalleryListing(selectedId, previewSummary, { returnTo: returnTo });
    });
    const back = el("button", { type: "button", class: "ghost" }, "← Back");
    back.addEventListener("click", () => {
      if (returnTo === "style" && summary) {
        renderStyle(summary);
      } else if (returnTo === "library") {
        renderShowLibrary();
      } else if (summary) {
        renderWorkspace(summary);
      } else {
        renderSetup();
      }
    });
    view.appendChild(el("div", { class: "actions" }, applyButton, back));
    root.appendChild(view);
    view.scrollIntoView({ block: "start" });
  }

  function renderPublishToGallery(templateId, summary, returnTo) {
    if (!GAL || !TM) {
      return;
    }
    const template = TM.getTemplate(templateStore, templateId);
    if (!template) {
      if (returnTo === "style" && summary) {
        renderStyle(summary);
      } else if (summary) {
        renderWorkspace(summary);
      } else {
        renderSetup();
      }
      return;
    }

    root.innerHTML = "";
    setStep("Publish to creator gallery");

    const view = el("div", { class: "creator-gallery-publish-step" });
    view.appendChild(
      el(
        "div",
        { class: "workspace-head" },
        el("p", { class: "eyebrow" }, "Creator gallery"),
        el("h2", {}, "Publish saved layout"),
        el(
          "p",
          { class: "hint" },
          "Share this show template with name, description, style tags, and a preview image other shows can browse and apply.",
        ),
      ),
    );

    const layout = el("div", { class: "creator-gallery-publish-layout" });
    const formCard = el("section", { class: "card creator-gallery-publish-form" }, el("h3", {}, "Listing details"));

    const nameInput = el("input", {
      id: "gallery-listing-name",
      type: "text",
      value: template.name,
      placeholder: "e.g. Founders Split Stage",
    });
    formCard.appendChild(field("Gallery name", nameInput, null, "Public name shown in the creator gallery."));

    const descriptionInput = el("textarea", {
      id: "gallery-listing-description",
      rows: "3",
      placeholder: "Describe the layout, captions, overlays, and when to use it.",
    }, "");
    formCard.appendChild(field("Description", descriptionInput, null, "Help other creators understand this layout."));

    const tagsInput = el("input", {
      id: "gallery-listing-tags",
      type: "text",
      value: GAL.deriveStyleTags(template.canvas).join(", "),
      placeholder: "interview, split-stage, bold-captions",
    });
    formCard.appendChild(field("Style tags", tagsInput, null, "Comma-separated tags for browsing and filtering."));

    const publishError = el("p", { class: "field-error", role: "alert", hidden: true });
    formCard.appendChild(publishError);

    layout.appendChild(formCard);

    const previewCard = el("section", { class: "card creator-gallery-publish-preview" }, el("h3", {}, "Preview image"));
    previewCard.appendChild(
      el("p", { class: "hint" }, "Live layout preview saved with the listing — speakers update when others apply it to their episode."),
    );
    previewCard.appendChild(renderCanvasStage(template.canvas));
    layout.appendChild(previewCard);
    view.appendChild(layout);

    const publishButton = el("button", { type: "button", class: "primary" }, "Publish to gallery →");
    publishButton.addEventListener("click", () => {
      const nameResult = GAL.validateListingName(galleryStore, nameInput.value);
      if (!nameResult.ok) {
        publishError.hidden = false;
        publishError.textContent = nameResult.error;
        return;
      }
      publishError.hidden = true;
      galleryStore = GAL.publishListing(galleryStore, template, {
        name: nameResult.name,
        description: descriptionInput.value,
        styleTags: tagsInput.value,
        previewImage: GAL.buildPreviewImage(template.canvas),
        creatorName: previewSummaryShowName(summary),
      });
      persistGallery();
      const published = GAL.listListings(galleryStore).find((item) => item.name === nameResult.name);
      activeGalleryListingId = published ? published.id : null;
      renderCreatorGalleryBrowse(summary, { returnTo: returnTo });
    });

    const back = el("button", { type: "button", class: "ghost" }, "← Back");
    back.addEventListener("click", () => {
      if (returnTo === "style" && summary) {
        renderStyle(summary);
      } else if (returnTo === "library") {
        renderShowLibrary();
      } else if (summary) {
        renderWorkspace(summary);
      } else {
        renderSetup();
      }
    });
    view.appendChild(el("div", { class: "actions" }, publishButton, back));
    root.appendChild(view);
    view.scrollIntoView({ block: "start" });
  }

  function previewSummaryShowName(summary) {
    if (summary && summary.showName) {
      return summary.showName;
    }
    if (activeShowId && LIB) {
      const show = LIB.getShow(showLibrary, activeShowId);
      if (show && show.name) {
        return show.name;
      }
    }
    return "Creator";
  }

  function applyGalleryListing(listingId, summary, options) {
    if (!GAL || !TM) {
      return;
    }
    const listing = GAL.getListing(galleryStore, listingId);
    if (!listing) {
      return;
    }
    const episodeSummary = summary || ES.summarize(state);
    const fromCanvas = GAL.styleSelectionFromListing(listing);
    styleSelection = fromCanvas || styleSelection || (STY ? STY.createSelection() : null);
    canvasDoc = GAL.applyListingForEpisode(listing, episodeSummary, styleSelection);
    activeGalleryListingId = listing.id;
    activeTemplateId = listing.sourceTemplateId || null;
    if (STY && styleSelection) {
      appliedStyle = STY.summarizeStyle(styleSelection, episodeSummary.speakerCount);
      if (getActiveBrandKit() && BK) {
        appliedStyle = BK.applyToStyleSummary(appliedStyle, getActiveBrandKit());
      }
    }
    if (canvasDoc && getActiveBrandKit() && BK) {
      canvasDoc = BK.applyToCanvas(canvasDoc, getActiveBrandKit());
    }
    const returnTo = options && options.returnTo;
    if (returnTo === "style") {
      renderStyle(episodeSummary);
    } else if (summary) {
      renderWorkspace(episodeSummary);
    } else {
      renderSetup();
    }
  }

  function renderSavedTemplatesCard(saved, summary, returnTo) {
    const card = el("section", { class: "card template-picker template-library creator-template-area" });
    card.appendChild(el("h3", {}, "Show template library"));
    card.appendChild(
      el(
        "p",
        { class: "hint" },
        "Pick a saved layout and style — your current episode speakers stay assigned. Publish layouts to the creator gallery for other shows to browse.",
      ),
    );

    const headerActions = el("div", { class: "template-library-actions" });
    if (GAL) {
      const browseButton = el("button", { type: "button", class: "ghost" }, "Browse creator gallery →");
      browseButton.addEventListener("click", () => {
        if (!GAL.listListings(galleryStore).length) {
          seedGalleryDemoData();
        }
        renderCreatorGalleryBrowse(summary, { returnTo: returnTo });
      });
      headerActions.appendChild(browseButton);
    }
    if (headerActions.childNodes.length) {
      card.appendChild(headerActions);
    }

    if (!saved.length) {
      card.appendChild(
        el(
          "p",
          { class: "hint template-library-empty" },
          "No saved templates yet — customize a layout in the canvas editor, then save it here to publish.",
        ),
      );
      return card;
    }

    const list = el("div", { class: "template-list" });
    saved.forEach((item) => {
      const row = el(
        "div",
        { class: `template-row${activeTemplateId === item.id ? " active" : ""}` },
        el("span", { class: "template-row-name" }, item.name),
        el(
          "span",
          { class: "template-row-meta" },
          `${item.presetName || "Custom"} · ${item.titleText || "Untitled"}`,
        ),
      );
      const actions = el("div", { class: "template-row-actions" });
      const useButton = el("button", { type: "button", class: "ghost" }, "Use template");
      useButton.addEventListener("click", () => {
        applySavedTemplate(item.id, summary, { returnTo: returnTo });
      });
      actions.appendChild(useButton);
      if (GAL) {
        const publishButton = el("button", { type: "button", class: "ghost" }, "Publish to gallery");
        publishButton.addEventListener("click", () => {
          renderPublishToGallery(item.id, summary, returnTo);
        });
        actions.appendChild(publishButton);
      }
      row.appendChild(actions);
      list.appendChild(row);
    });
    card.appendChild(list);
    return card;
  }

  function applySavedTemplate(templateId, summary, options) {
    if (!TM) {
      return;
    }
    const template = TM.getTemplate(templateStore, templateId);
    if (!template) {
      return;
    }
    const episodeSummary = summary || ES.summarize(state);
    const fromCanvas = TM.styleSelectionFromCanvas(template.canvas);
    styleSelection = fromCanvas || styleSelection || (STY ? STY.createSelection() : null);
    canvasDoc = TM.applyTemplateForEpisode(template, episodeSummary, styleSelection);
    activeTemplateId = template.id;
    activeGalleryListingId = null;
    if (STY && styleSelection) {
      appliedStyle = STY.summarizeStyle(styleSelection, episodeSummary.speakerCount);
    }
    const returnTo = options && options.returnTo;
    if (returnTo === "style") {
      renderStyle(episodeSummary);
    } else if (summary) {
      renderWorkspace(episodeSummary);
    } else {
      renderSetup();
    }
  }

  function openCanvasEditor(summary) {
    workspaceSummaryCache = summary;
    if (!canvasDoc && CE && appliedStyle) {
      canvasDoc = CE.createFromStyle(appliedStyle, summary, styleSelection);
    } else if (canvasDoc && CE) {
      canvasDoc = CE.refreshSpeakerFrames(canvasDoc, summary, styleSelection);
    }
    renderCanvasEditor(summary);
  }

  // ---- Canvas editor (#11) ----------------------------------------------------

  function shortLayerLabel(type) {
    if (type === "speaker") return "Speaker";
    if (type === "captions") return "Captions";
    if (type === "lower-thirds") return "Lower-third";
    if (type === "title") return "Title";
    if (type === "broll") return "B-roll";
    if (type === "brand") return "Brand";
    if (type === "safe-area") return "Safe area";
    if (type === "background") return "Background";
    return CL.getLayerType(type).label;
  }

  function renderCanvasStage(doc) {
    const stage = el("div", { class: "canvas-stage", "aria-hidden": "true" });
    stage.style.background = doc.background || "#10131f";

    CL.visibleLayersForStage(doc.layers).forEach((layer) => {
      if (layer.type === "speaker") {
        const frameWrap = el("div", { class: `canvas-speaker-frames stage-${doc.layoutId || "grid"}` });
        (doc.speakerFrames || []).forEach((frame) => {
          const frameEl = el(
            "div",
            { class: `preview-frame${frame.active ? " active" : ""}` },
            el("span", { class: "preview-role" }, frame.role),
            el("span", { class: "preview-name" }, frame.name),
          );
          frameEl.style.borderColor = doc.accent;
          frameWrap.appendChild(frameEl);
        });
        stage.appendChild(frameWrap);
        return;
      }
      if (layer.type === "title") {
        stage.appendChild(el("div", { class: "canvas-obj canvas-obj-title canvas-title-live" }, doc.titleText));
        return;
      }
      if (layer.type === "captions") {
        stage.appendChild(
          el("div", { class: "canvas-obj canvas-obj-captions canvas-caption-live" }, doc.captionText),
        );
        return;
      }
      const obj = el("div", { class: `canvas-obj canvas-obj-${layer.type}` }, shortLayerLabel(layer.type));
      stage.appendChild(obj);
    });
    return stage;
  }

  function renderCanvasLayerRow(layer, index, summary) {
    const meta = CL.getLayerType(layer.type);
    const swatch = el("span", { class: "canvas-swatch" });
    swatch.style.background = meta.swatch;

    const metaBits = [index === 0 ? "Top of stack" : `Layer ${index + 1}`];
    if (layer.locked) metaBits.push("position locked");
    if (!layer.visible) metaBits.push("hidden");

    function refresh(layers) {
      canvasDoc = CE.updateLayers(canvasDoc, layers);
      renderCanvasEditor(summary);
    }

    const up = el("button", {
      type: "button",
      class: "ghost canvas-tiny",
      "aria-label": `Move ${meta.label} up`,
      disabled: CL.canMoveLayer(canvasDoc.layers, index, -1) ? null : true,
    }, "▲");
    up.addEventListener("click", (e) => {
      e.stopPropagation();
      refresh(CL.moveLayer(canvasDoc.layers, index, -1));
    });

    const down = el("button", {
      type: "button",
      class: "ghost canvas-tiny",
      "aria-label": `Move ${meta.label} down`,
      disabled: CL.canMoveLayer(canvasDoc.layers, index, 1) ? null : true,
    }, "▼");
    down.addEventListener("click", (e) => {
      e.stopPropagation();
      refresh(CL.moveLayer(canvasDoc.layers, index, 1));
    });

    const vis = el("button", { type: "button", class: "ghost canvas-tiny" }, layer.visible ? "Hide" : "Show");
    vis.addEventListener("click", (e) => {
      e.stopPropagation();
      refresh(CL.toggleVisibility(canvasDoc.layers, index));
    });

    const lock = el("button", {
      type: "button",
      class: "ghost canvas-tiny",
      title: layer.locked ? "Unlock position" : "Lock position",
    }, layer.locked ? "Unlock" : "Lock");
    lock.addEventListener("click", (e) => {
      e.stopPropagation();
      refresh(CL.toggleLock(canvasDoc.layers, index));
    });

    const remove = el("button", {
      type: "button",
      class: "ghost canvas-tiny",
      "aria-label": `Remove ${meta.label}`,
      disabled: layer.locked ? true : null,
    }, "Remove");
    remove.addEventListener("click", (e) => {
      e.stopPropagation();
      refresh(CL.removeLayer(canvasDoc.layers, index));
    });

    return el(
      "article",
      { class: `canvas-layer${layer.visible ? "" : " is-hidden"}${layer.locked ? " is-locked" : ""}` },
      swatch,
      el("div", { class: "canvas-layer-main" },
        el("span", { class: "canvas-layer-name" }, meta.label),
        el("span", { class: "canvas-layer-meta" }, metaBits.join(" · ")),
      ),
      el("div", { class: "canvas-layer-actions" }, up, down, vis, lock, remove),
    );
  }

  function renderCanvasEditor(summary) {
    workspaceSummaryCache = summary;
    if (!canvasDoc && CE) {
      canvasDoc = CE.createFromStyle(appliedStyle, summary, styleSelection);
    }
    root.innerHTML = "";
    setStep("Step 5 of 8 · Canvas editor");

    const evaluation = CL.evaluateLayout(canvasDoc.layers);
    const view = el("div", { class: "canvas-step" });
    view.appendChild(
      el("div", { class: "workspace-head" },
        el("p", { class: "eyebrow" }, "Canvas editor"),
        el("h2", {}, `Customize ${appliedStyle.presetName}`),
        el("p", { class: "hint" }, "Adjust layout elements, then save a named show template you can reuse on future episodes."),
      ),
    );

    const grid = el("div", { class: "canvas-layout" });

    const controls = el("section", { class: "card" }, el("h3", {}, "Layout elements"));

    const titleInput = el("input", {
      id: "canvas-title",
      type: "text",
      value: canvasDoc.titleText,
    });
    titleInput.addEventListener("input", (e) => {
      canvasDoc = CE.updateElement(canvasDoc, "titleText", e.target.value);
      renderCanvasEditor(summary);
    });
    controls.appendChild(field("Title text", titleInput, null, "Shown when the title layer is visible."));

    const bgInput = el("input", {
      id: "canvas-background",
      type: "color",
      value: canvasDoc.background,
    });
    bgInput.addEventListener("input", (e) => {
      canvasDoc = CE.updateElement(canvasDoc, "background", e.target.value);
      renderCanvasEditor(summary);
    });
    controls.appendChild(field("Background", bgInput, null, "Stage background color from your preset."));

    const captionInput = el("input", {
      id: "canvas-caption",
      type: "text",
      value: canvasDoc.captionText,
    });
    captionInput.addEventListener("input", (e) => {
      canvasDoc = CE.updateElement(canvasDoc, "captionText", e.target.value);
      renderCanvasEditor(summary);
    });
    controls.appendChild(field("Caption sample", captionInput, null, "Preview text for the captions layer."));

    const stackHeading = el("h4", { class: "canvas-subhead" }, "Layer stack");
    controls.appendChild(stackHeading);
    const list = el("div", { class: "canvas-layers" });
    canvasDoc.layers.forEach((layer, index) => {
      list.appendChild(renderCanvasLayerRow(layer, index, summary));
    });
    controls.appendChild(list);

    const addType = el("select", { id: "canvas-add-type", "aria-label": "Layer type to add" });
    Object.keys(CL.LAYER_TYPES).forEach((type) => {
      addType.appendChild(el("option", { value: type }, CL.getLayerType(type).label));
    });
    const addButton = el("button", { type: "button", class: "ghost" }, "Add layer");
    addButton.addEventListener("click", () => {
      const id = `l${canvasLayerCounter}`;
      canvasLayerCounter += 1;
      canvasDoc = CE.updateLayers(canvasDoc, CL.addLayer(canvasDoc.layers, addType.value, id));
      renderCanvasEditor(summary);
    });
    controls.appendChild(el("div", { class: "canvas-add-row" }, addType, addButton));
    grid.appendChild(controls);

    const previewCard = el("section", { class: "card" }, el("h3", {}, "Live preview"));
    previewCard.appendChild(renderCanvasStage(canvasDoc));
    previewCard.appendChild(
      el("p", { class: `canvas-status canvas-status-${evaluation.overall}` },
        evaluation.overall === "ready" ? "Layout ready to save" : "Review layout warnings before saving",
      ),
    );
    if (evaluation.checks.length) {
      const checks = el("div", { class: "canvas-checks" });
      evaluation.checks.forEach((check) => {
        checks.appendChild(
          el("div", { class: `canvas-check canvas-check-${check.tone}` },
            el("strong", {}, check.title),
            el("p", {}, check.action),
          ),
        );
      });
      previewCard.appendChild(checks);
    }
    grid.appendChild(previewCard);
    view.appendChild(grid);

    const saveCard = el("section", { class: "card template-save" }, el("h3", {}, "Save show template"));
    const nameInput = el("input", {
      id: "template-name",
      type: "text",
      placeholder: "e.g. Founders Unfiltered",
      value: activeTemplateId && TM.getTemplate(templateStore, activeTemplateId)
        ? TM.getTemplate(templateStore, activeTemplateId).name
        : "",
    });
    saveCard.appendChild(field("Template name", nameInput, null, "Name this layout so you can reuse it on future episodes."));
    const saveError = el("p", { class: "field-error", role: "alert", hidden: true });
    saveCard.appendChild(saveError);

    const saveButton = el("button", {
      type: "button",
      class: "primary",
      disabled: evaluation.overall !== "ready" ? true : null,
    }, "Save show template →");
    saveButton.addEventListener("click", () => {
      const nameResult = TM.validateTemplateName(templateStore, nameInput.value, activeTemplateId);
      const canvasResult = CE.validateForSave(canvasDoc);
      if (!nameResult.ok) {
        saveError.hidden = false;
        saveError.textContent = nameResult.error;
        return;
      }
      if (!canvasResult.ok) {
        saveError.hidden = false;
        saveError.textContent = canvasResult.error;
        return;
      }
      saveError.hidden = true;
      const template = TM.createTemplate(
        nameResult.name,
        canvasDoc,
        activeTemplateId || undefined,
      );
      templateStore = TM.saveTemplate(templateStore, template);
      activeTemplateId = template.id;
      persistTemplates();
      renderWorkspace(summary);
    });
    saveCard.appendChild(el("div", { class: "actions" }, saveButton));
    view.appendChild(saveCard);

    const back = el("button", { type: "button", class: "ghost" }, "← Back to workspace");
    back.addEventListener("click", () => renderWorkspace(summary));
    view.appendChild(el("div", { class: "actions" }, back));

    root.appendChild(view);
    view.scrollIntoView({ block: "start" });
  }

  // ---- Social context review (#34) --------------------------------------------

  function renderContextReview(summary) {
    if (!contextReview) {
      contextReview = SC.createReview(summary);
    }
    root.innerHTML = "";
    setStep("Step 2 of 8 · Review context");

    const view = el("div", { class: "context-step" });
    view.appendChild(
      el("div", { class: "workspace-head" },
        el("p", { class: "eyebrow" }, "Review context"),
        el("h2", {}, `Confirm names and spellings for ${summary.episodeName}`),
        el(
          "p",
          { class: "hint" },
          "We pulled concise hints from the social links you added — approve or edit them so captions, titles, and callouts spell names and brands correctly.",
        ),
      ),
    );

    const grid = el("div", { class: "context-layout" });
    contextReview.speakers.forEach((speaker, index) => {
      const card = el("section", { class: "card context-speaker-card" });
      card.appendChild(
        el("h3", {}, `${speaker.role}${speaker.socialLinkCount ? " · social links" : ""}`),
      );

      function bindInput(label, key, value, hint) {
        const input = el("input", { id: `ctx-${index}-${key}`, type: "text", value: value || "" });
        input.addEventListener("input", (e) => {
          contextReview = SC.updateSpeaker(contextReview, index, { [key]: e.target.value });
        });
        card.appendChild(field(label, input, null, hint));
      }

      bindInput("Approved name", "displayName", speaker.displayName, "How this speaker's name should appear on screen.");
      bindInput("Brand or show", "brand", speaker.brand, "Company, show, or personal brand tied to this speaker.");
      bindInput("Topics", "topics", (speaker.topics || []).join(", "), "Comma-separated topics for smarter titles and callouts.");
      bindInput(
        "Spelling hints",
        "spellingHints",
        (speaker.spellingHints || []).join(", "),
        "Common misspellings to auto-fix in captions and overlays.",
      );
      grid.appendChild(card);
    });
    view.appendChild(grid);

    const approveButton = el("button", { type: "button", class: "primary" }, "Approve context & continue →");
    approveButton.addEventListener("click", () => {
      contextReview = SC.approveReview(contextReview);
      contextApproved = true;
      applyContextEffects();
      if (AP && !appliedAudioPolish) {
        audioPolish = AP.createPolish(summary);
        renderAudioPolish(summary);
      } else {
        renderWorkspace(summary);
      }
    });
    const back = el("button", { type: "button", class: "ghost" }, "← Back to setup");
    back.addEventListener("click", () => {
      contextReview = null;
      renderSetup();
    });
    view.appendChild(el("div", { class: "actions" }, approveButton, back));

    root.appendChild(view);
    view.scrollIntoView({ block: "start" });
  }

  // ---- Audio polish (#15) -----------------------------------------------------

  function renderAudioPolish(summary) {
    if (!audioPolish) {
      audioPolish = AP.createPolish(summary);
    }
    root.innerHTML = "";
    setStep("Step 3 of 8 · Audio polish");

    const view = el("div", { class: "audio-step" });
    view.appendChild(
      el("div", { class: "workspace-head" },
        el("p", { class: "eyebrow" }, "Audio polish"),
        el("h2", {}, `Shape the sound for ${summary.episodeName}`),
        el("p", { class: "hint" }, "Choose the quality you want — not technical settings. Each speaker track below will get this treatment."),
      ),
    );

    const grid = el("div", { class: "audio-layout" });

    const controls = el("section", { class: "card" }, el("h3", {}, "Sound quality"));
    const presetGrid = el("div", { class: "audio-preset-grid" });
    AP.QUALITY_PRESETS.forEach((preset) => {
      const selected = audioPolish.presetId === preset.id;
      const card = el(
        "button",
        {
          type: "button",
          class: `audio-preset-card${selected ? " selected" : ""}`,
          "aria-pressed": selected ? "true" : "false",
        },
        el("span", { class: "audio-preset-name" }, preset.name),
        el("span", { class: "audio-preset-tagline" }, preset.tagline),
      );
      card.addEventListener("click", () => {
        audioPolish = AP.applyPreset(audioPolish, preset.id);
        renderAudioPolish(summary);
      });
      presetGrid.appendChild(card);
    });
    controls.appendChild(presetGrid);

    AP.CONTROLS.forEach((control) => {
      const select = el("select", { id: `audio-${control.id}` });
      AP.LEVELS.forEach((level) => {
        select.appendChild(
          el("option", {
            value: level.id,
            selected: audioPolish[control.id] === level.id ? true : null,
          }, level.label),
        );
      });
      select.addEventListener("change", (e) => {
        audioPolish = AP.updateControl(audioPolish, control.id, e.target.value);
        renderAudioPolish(summary);
      });
      controls.appendChild(field(control.label, select, null, control.hint));
    });
    grid.appendChild(controls);

    const tracksCard = el("section", { class: "card" }, el("h3", {}, "Speaker tracks"));
    tracksCard.appendChild(
      el("p", { class: "hint" }, "Each imported source receives the treatment you choose above."),
    );
    const trackList = el("div", { class: "audio-track-list" });
    audioPolish.speakers.forEach((track) => {
      trackList.appendChild(
        el("div", { class: "audio-track" },
          el("div", { class: "audio-track-main" },
            el("span", { class: "role-pill" }, track.role),
            el("span", { class: "summary-name" }, track.name),
          ),
          el("p", { class: "summary-source" }, track.sourceLabel),
          el("span", { class: "audio-track-badge" }, AP.speakerIndicator(audioPolish, track)),
        ),
      );
    });
    tracksCard.appendChild(trackList);
    grid.appendChild(tracksCard);
    view.appendChild(grid);

    const applyButton = el("button", { type: "button", class: "primary" }, "Apply audio & continue →");
    applyButton.addEventListener("click", () => {
      appliedAudioPolish = AP.summarizePolish(audioPolish);
      if (STY && !appliedStyle) {
        renderStyle(summary);
      } else {
        renderWorkspace(summary);
      }
    });
    const back = el("button", { type: "button", class: "ghost" }, "← Back to setup");
    back.addEventListener("click", () => {
      showErrors = false;
      renderSetup();
    });
    view.appendChild(el("div", { class: "actions" }, applyButton, back));

    root.appendChild(view);
    view.scrollIntoView({ block: "start" });
  }

  // ---- Visual moments editor (#19) --------------------------------------------

  function renderMomentPreview(preview) {
    const accent = appliedStyle ? appliedStyle.accent : "#6c4cff";
    const background = appliedStyle ? appliedStyle.background : "#10131f";
    const stage = el("div", { class: `moment-stage moment-stage-${preview.type}` });
    stage.style.background = background;
    stage.style.borderColor = accent;

    stage.appendChild(
      el(
        "span",
        { class: "moment-stage-speaker" },
        preview.speakerLabel === "the whole conversation" ? "Full episode" : preview.speakerLabel,
      ),
    );

    if (!preview.visible) {
      stage.appendChild(el("div", { class: "moment-hidden-note" }, "Hidden — will not appear on screen"));
      return stage;
    }
    if (preview.type === "caption") {
      const caption = el("div", { class: "moment-caption" }, preview.text);
      caption.style.background = accent;
      stage.appendChild(caption);
    } else if (preview.type === "title") {
      const title = el("div", { class: "moment-title-card" }, preview.text);
      title.style.color = accent;
      stage.appendChild(title);
    } else if (preview.type === "broll") {
      const broll = el("div", { class: "moment-broll" }, `B-roll · ${preview.text}`);
      broll.style.borderColor = accent;
      stage.appendChild(broll);
    } else if (preview.type === "callout") {
      const callout = el("div", { class: "moment-callout" }, preview.text);
      callout.style.background = accent;
      stage.appendChild(callout);
    } else {
      stage.appendChild(el("div", { class: "moment-note" }, `Note · ${preview.text}`));
    }
    return stage;
  }

  function renderMomentRow(moment, summary) {
    const isSelected = selectedMomentId === moment.id;
    const card = el("div", {
      class: `moment-row${isSelected ? " selected" : ""}${moment.visible ? "" : " hidden-moment"}`,
    });

    const head = el(
      "div",
      { class: "moment-row-head" },
      el("span", { class: "moment-type-badge" }, moment.typeLabel),
      el("span", { class: "moment-row-time" }, moment.time),
    );
    const visId = `mv-${moment.id}`;
    const visInput = el("input", { id: visId, type: "checkbox", checked: moment.visible ? true : null });
    visInput.addEventListener("change", () => {
      momentsBoard = VM.toggleMoment(momentsBoard, moment.id);
      selectedMomentId = moment.id;
      persistMoments();
      renderVisualMoments(summary);
    });
    head.appendChild(el("label", { class: "cv-toggle", for: visId }, visInput, el("span", {}, moment.visible ? "Visible" : "Hidden")));
    card.appendChild(head);

    const textInput = el("input", { id: `mt-${moment.id}`, type: "text", value: moment.text, placeholder: "Moment text" });
    textInput.addEventListener("change", (e) => {
      momentsBoard = VM.updateMoment(momentsBoard, moment.id, { text: e.target.value });
      selectedMomentId = moment.id;
      persistMoments();
      renderVisualMoments(summary);
    });
    card.appendChild(field("Text", textInput, null));

    const timeInput = el("input", { id: `mtime-${moment.id}`, type: "text", value: moment.time, placeholder: "0:00" });
    timeInput.addEventListener("change", (e) => {
      momentsBoard = VM.updateMoment(momentsBoard, moment.id, { time: e.target.value });
      selectedMomentId = moment.id;
      persistMoments();
      renderVisualMoments(summary);
    });

    const speakerSelect = el("select", { id: `msp-${moment.id}` });
    VM.speakerOptions(summary).forEach((opt) => {
      const selected = moment.speakerRole === opt.role;
      speakerSelect.appendChild(
        el("option", { value: opt.role, selected: selected ? true : null }, opt.name === opt.role ? opt.role : `${opt.role} · ${opt.name}`),
      );
    });
    speakerSelect.addEventListener("change", (e) => {
      const opt = VM.speakerOptions(summary).find((o) => o.role === e.target.value) || { role: e.target.value, name: e.target.value };
      momentsBoard = VM.updateMoment(momentsBoard, moment.id, { speakerRole: opt.role, speakerName: opt.name });
      selectedMomentId = moment.id;
      persistMoments();
      renderVisualMoments(summary);
    });

    card.appendChild(
      el("div", { class: "moment-row-grid" }, field("Time", timeInput, null), field("Speaker", speakerSelect, null)),
    );

    const previewButton = el("button", { type: "button", class: isSelected ? "primary" : "ghost" }, isSelected ? "Previewing" : "Preview");
    previewButton.addEventListener("click", () => {
      selectedMomentId = moment.id;
      renderVisualMoments(summary);
    });
    const removeButton = el("button", { type: "button", class: "link-button" }, "Remove");
    removeButton.addEventListener("click", () => {
      momentsBoard = VM.removeMoment(momentsBoard, moment.id);
      if (selectedMomentId === moment.id) {
        selectedMomentId = null;
      }
      persistMoments();
      renderVisualMoments(summary);
    });
    card.appendChild(el("div", { class: "actions" }, previewButton, removeButton));
    return card;
  }

  function renderVisualMoments(summary) {
    ensureMomentsBoard(summary);
    root.innerHTML = "";
    setStep("Step 6 of 8 · Visual moments");

    const list = VM.listMoments(momentsBoard);
    // Keep the selected moment valid; default to the first moment so a preview is shown.
    if (selectedMomentId && !VM.getMoment(momentsBoard, selectedMomentId)) {
      selectedMomentId = null;
    }
    if (!selectedMomentId && list.length) {
      selectedMomentId = list[0].id;
    }

    const view = el("div", { class: "moments-step" });
    view.appendChild(
      el(
        "div",
        { class: "workspace-head" },
        el("p", { class: "eyebrow" }, "Visual moments"),
        el("h2", {}, `Add visual moments to ${summary.episodeName}`),
        el(
          "p",
          { class: "hint" },
          "Place captions, titles, b-roll, and callouts at key points across the episode, then preview how each one changes the look.",
        ),
      ),
    );

    // Add-moment palette
    const palette = el(
      "section",
      { class: "card" },
      el("h3", {}, "Add a moment"),
      el("p", { class: "hint" }, "Add a treatment, then set its time, text, and speaker below."),
    );
    const paletteRow = el("div", { class: "moments-palette" });
    VM.MOMENT_TYPES.forEach((type) => {
      const button = el(
        "button",
        { type: "button", class: "ghost moment-add" },
        el("span", { class: "moment-add-label" }, `+ ${type.label}`),
        el("span", { class: "moment-add-hint" }, type.treatment),
      );
      button.addEventListener("click", () => {
        const defaultSeconds = VM.listMoments(momentsBoard).length * 30;
        momentsBoard = VM.addMoment(momentsBoard, type.id, { time: defaultSeconds });
        const updated = VM.listMoments(momentsBoard);
        selectedMomentId = updated[updated.length - 1].id;
        persistMoments();
        renderVisualMoments(summary);
      });
      paletteRow.appendChild(button);
    });
    palette.appendChild(paletteRow);
    view.appendChild(palette);

    const grid = el("div", { class: "moments-layout" });

    // Left column: episode timeline + editable moments
    const leftCol = el("div", { class: "moments-left" });
    const timelineCard = el(
      "section",
      { class: "card" },
      el("h3", {}, "Episode timeline"),
      el("p", { class: "hint" }, "A speaker-aware view of the full conversation. Your moments are listed in episode order below."),
    );
    const timeline = el("div", { class: "timeline-list" });
    momentsBoard.transcript.forEach((seg) => {
      timeline.appendChild(
        el(
          "div",
          { class: "timeline-seg" },
          el("span", { class: "timeline-time" }, seg.time),
          el("span", { class: "role-pill" }, seg.speakerRole),
          el("span", { class: "timeline-speaker" }, seg.speakerName),
        ),
      );
    });
    timelineCard.appendChild(timeline);
    leftCol.appendChild(timelineCard);

    const momentsCard = el("section", { class: "card" }, el("h3", {}, "Your moments"));
    if (!list.length) {
      momentsCard.appendChild(
        el("p", { class: "hint" }, "No moments yet. Use “Add a moment” above to place captions, titles, b-roll, or callouts."),
      );
    } else {
      list.forEach((moment) => {
        momentsCard.appendChild(renderMomentRow(moment, summary));
      });
    }
    leftCol.appendChild(momentsCard);
    grid.appendChild(leftCol);

    // Right column: live preview of the selected moment
    const previewCard = el("section", { class: "card preview-card" }, el("h3", {}, "Moment preview"));
    const preview = selectedMomentId ? VM.previewMoment(momentsBoard, selectedMomentId) : null;
    if (!preview) {
      previewCard.appendChild(
        el("p", { class: "hint" }, "Add a moment and select Preview to see how it changes the episode look."),
      );
    } else {
      previewCard.appendChild(el("p", { class: "moment-preview-meta" }, `${preview.typeLabel} · ${preview.time}`));
      previewCard.appendChild(renderMomentPreview(preview));
      previewCard.appendChild(el("p", { class: "moment-effect" }, preview.effect));
    }
    grid.appendChild(previewCard);
    view.appendChild(grid);

    const doneButton = el("button", { type: "button", class: "primary" }, "Save moments & continue →");
    doneButton.addEventListener("click", () => {
      persistMoments();
      renderWorkspace(summary);
    });
    const back = el("button", { type: "button", class: "ghost" }, "← Back to workspace");
    back.addEventListener("click", () => {
      persistMoments();
      renderWorkspace(summary);
    });
    view.appendChild(el("div", { class: "actions" }, doneButton, back));

    root.appendChild(view);
    view.scrollIntoView({ block: "start" });
  }

  // ---- Preset style selection + preview (#4, #94, #102) -------------------------

  function renderEpisodeLookPreview(look, size) {
    if (!look) {
      return el("div", { class: "episode-look-preview episode-look-empty" }, "Choose a preset to preview the episode look.");
    }
    const previewSize = size || "hero";
    const preview = el("div", {
      class: [
        "episode-look-preview",
        `episode-look-${previewSize}`,
        `stage-${look.layoutId}`,
        `preset-${look.presetId}`,
        look.captionTreatment ? `caption-${look.captionTreatment}` : "",
        look.titleStyle ? `title-${look.titleStyle}` : "",
        look.overlayTone ? `overlay-${look.overlayTone}` : "",
        look.pacingId ? `pacing-${look.pacingId}` : "",
      ].filter(Boolean).join(" "),
    });

    const chromeTitle = previewSize === "card" && SP
      ? SP.galleryCardChromeTitle(look)
      : look.episodeTitle;
    preview.appendChild(
      el(
        "div",
        { class: "episode-look-chrome" },
        el("span", { class: "episode-look-title" }, chromeTitle),
        el("span", { class: "episode-look-overlay" }, look.overlayLabel),
      ),
    );

    const stage = el("div", {
      class: "episode-look-stage",
      style: `background:${look.theme.background};color:${look.theme.textColor};`,
    });
    const framesWrap = el("div", { class: "episode-look-frames" });
    look.frames.forEach((frame) => {
      const frameEl = el("div", { class: `episode-look-frame${frame.active ? " active" : ""}${frame.active ? "" : " inactive"}` });
      const video = el("div", {
        class: "episode-look-video",
        style: `background:linear-gradient(160deg, ${frame.tile}, ${look.theme.surface});`,
      });
      video.appendChild(el("span", { class: "episode-look-initials" }, frame.initials));
      frameEl.appendChild(video);
      frameEl.appendChild(el("div", { class: "episode-look-nameplate" }, frame.name));
      framesWrap.appendChild(frameEl);
    });
    stage.appendChild(framesWrap);
    if (look.topicLabel) {
      stage.appendChild(el("div", { class: "episode-look-topic" }, look.topicLabel));
    }
    stage.appendChild(
      el(
        "div",
        {
          class: `episode-look-caption episode-look-caption-${look.captionTreatment || "default"}`,
          style: `background:${look.theme.accent};`,
        },
        look.captionText,
      ),
    );
    if (look.lowerThird) {
      stage.appendChild(el("div", { class: "episode-look-lower-third" }, look.lowerThird));
    }
    stage.appendChild(
      el(
        "div",
        { class: "episode-look-meta" },
        el("span", { class: "episode-look-pacing" }, look.pacingLabel),
        el("span", { class: "episode-look-format" }, look.captionStyle),
        look.pacingId === "punchy"
          ? el("span", { class: "episode-look-pacing-cues", "aria-hidden": "true" }, "|||")
          : look.pacingId === "relaxed"
            ? el("span", { class: "episode-look-pacing-cues", "aria-hidden": "true" }, "—")
            : el("span", { class: "episode-look-pacing-cues", "aria-hidden": "true" }, "••"),
      ),
    );
    preview.appendChild(stage);

    if (previewSize === "hero") {
      preview.appendChild(
        el("p", { class: "episode-look-foot" }, `${look.presetName} · ${look.formatCue}`),
      );
    }

    return preview;
  }

  function renderLayoutThumb(layoutId, colors) {
    const palette = colors || {};
    const thumb = el("div", {
      class: `style-layout-thumb style-layout-thumb-${layoutId || "spotlight"}`,
      style: palette.background ? `background:${palette.background};` : null,
    });
    if (layoutId === "split") {
      thumb.appendChild(el("span", { class: "style-layout-thumb-frame", style: `border-color:${palette.accent || "currentColor"};` }));
      thumb.appendChild(el("span", { class: "style-layout-thumb-frame", style: `border-color:${palette.accent || "currentColor"};` }));
    } else if (layoutId === "grid") {
      for (let i = 0; i < 4; i += 1) {
        thumb.appendChild(el("span", { class: "style-layout-thumb-cell", style: `border-color:${palette.accent || "currentColor"};` }));
      }
    } else if (layoutId === "auto") {
      thumb.appendChild(el("span", { class: "style-layout-thumb-auto-badge", style: `background:${palette.accent || "currentColor"};` }, "Auto"));
    } else {
      thumb.appendChild(el("span", { class: "style-layout-thumb-main", style: `border-color:${palette.accent || "currentColor"};` }));
      thumb.appendChild(el("span", { class: "style-layout-thumb-rail", style: `border-color:${palette.accent || "currentColor"};` }));
    }
    return thumb;
  }

  function renderStylePresetCard(preset, selected, summary) {
    const cues = STY.presetCardSummary(preset);
    const look = SP
      ? SP.buildEpisodeLook(preset.id, { showName: summary && summary.showName })
      : null;
    const card = el(
      "button",
      {
        type: "button",
        class: `preset-card style-preset-card${selected ? " selected" : ""}`,
        "aria-pressed": selected ? "true" : "false",
      },
      look ? renderEpisodeLookPreview(look, "card") : null,
      el("span", { class: "preset-name" }, preset.name),
      el("span", { class: "preset-tagline" }, preset.tagline),
      el("span", { class: "preset-format-cue" }, cues.formatCue),
    );
    card.addEventListener("click", () => {
      styleSelection = STY.applyPresetToSelection(styleSelection, preset.id, layoutCustomized);
      activeTemplateId = null;
      canvasDoc = null;
      renderStyle(summary);
    });
    return card;
  }

  function renderStyleChoiceCards(items, selectedId, gridClass, renderCard, onSelect) {
    const grid = el("div", { class: gridClass });
    items.forEach((item) => {
      const selected = item.id === selectedId;
      const card = renderCard(item, selected);
      card.addEventListener("click", () => onSelect(item.id));
      grid.appendChild(card);
    });
    return grid;
  }

  function renderPreview(summary, selection, compact) {
    const look = SP && STY
      ? SP.buildEpisodeLookFromEpisode(
        STY.getPreset(selection && selection.presetId).id,
        summary,
        selection,
      )
      : null;
    return renderEpisodeLookPreview(look, compact ? "card" : "hero");
  }

  function renderStyle(summary) {
    root.innerHTML = "";
    setStep("Step 4 of 8 · Choose a style");
    if (!styleSelection) {
      styleSelection = STY.createSelection();
    }

    const view = el("div", { class: "style-step" });
    const identityBanner = renderShowIdentityBanner();
    if (identityBanner) {
      view.appendChild(identityBanner);
    }
    view.appendChild(
      el(
        "div",
        { class: "workspace-head" },
        el("p", { class: "eyebrow" }, "Choose a style"),
        el("h2", {}, `Pick a look for ${summary.episodeName}`),
        el("p", { class: "hint" }, "Pick a preset card with a full episode preview — layout, captions, and overlay update live on the right."),
      ),
    );

    const layoutGrid = el("div", { class: "style-layout" });

    const controls = el("section", { class: "card style-preset-panel" }, el("h3", {}, "Style presets"));
    const presetGrid = el("div", { class: "preset-grid style-preset-grid" });
    STY.STYLE_PRESETS.forEach((preset) => {
      presetGrid.appendChild(renderStylePresetCard(preset, styleSelection.presetId === preset.id, summary));
    });
    controls.appendChild(presetGrid);

    controls.appendChild(el("h4", { class: "style-subsection-title" }, "Layout"));
    controls.appendChild(
      renderStyleChoiceCards(
        STY.LAYOUTS.map((layout) => STY.layoutCardSummary(layout)),
        styleSelection.layout,
        "style-choice-grid style-layout-grid",
        function (layout, selected) {
          return el(
            "button",
            {
              type: "button",
              class: `style-choice-card style-layout-card${selected ? " selected" : ""}`,
              "aria-pressed": selected ? "true" : "false",
            },
            renderLayoutThumb(layout.id, {
              background: STY.getPreset(styleSelection.presetId).background,
              accent: STY.getPreset(styleSelection.presetId).accent,
            }),
            el("span", { class: "style-choice-name" }, layout.label),
            el("span", { class: "style-choice-note" }, layout.note),
          );
        },
        function (layoutId) {
          styleSelection.layout = layoutId;
          layoutCustomized = styleSelection.layout !== "auto";
          activeTemplateId = null;
          canvasDoc = null;
          renderStyle(summary);
        },
      ),
    );

    controls.appendChild(el("h4", { class: "style-subsection-title" }, "Pacing"));
    controls.appendChild(
      renderStyleChoiceCards(
        STY.PACING,
        styleSelection.pacing,
        "style-choice-grid style-pacing-grid",
        function (pacing, selected) {
          return el(
            "button",
            {
              type: "button",
              class: `style-choice-card style-pacing-card${selected ? " selected" : ""}`,
              "aria-pressed": selected ? "true" : "false",
            },
            el("span", { class: "style-choice-name" }, pacing.label),
            el("span", { class: "style-choice-note" }, pacing.note),
          );
        },
        function (pacingId) {
          styleSelection.pacing = pacingId;
          activeTemplateId = null;
          canvasDoc = null;
          renderStyle(summary);
        },
      ),
    );

    layoutGrid.appendChild(controls);

    // Preview column
    const previewCard = el(
      "section",
      { class: "card preview-card" },
      el("h3", {}, "Preview"),
      renderPreview(summary, styleSelection, false),
    );
    layoutGrid.appendChild(previewCard);

    view.appendChild(layoutGrid);

    if (TM) {
      const saved = TM.listTemplates(templateStore);
      if (saved.length || GAL) {
        view.appendChild(renderSavedTemplatesCard(saved, summary, "style"));
      }
    }

    // Actions
    const applyButton = el("button", { type: "button", class: "primary" }, "Apply style & continue →");
    applyButton.addEventListener("click", () => {
      appliedStyle = STY.summarizeStyle(styleSelection, summary.speakerCount);
      if (getActiveBrandKit() && BK) {
        appliedStyle = BK.applyToStyleSummary(appliedStyle, getActiveBrandKit());
      }
      if (!activeTemplateId) {
        canvasDoc = null;
      } else if (canvasDoc && BK && getActiveBrandKit()) {
        canvasDoc = BK.applyToCanvas(canvasDoc, getActiveBrandKit());
      }
      renderWorkspace(summary);
    });
    const back = el("button", { type: "button", class: "ghost" }, "← Back to workspace");
    back.addEventListener("click", () => renderWorkspace(summary));
    view.appendChild(el("div", { class: "actions" }, applyButton, back));

    root.appendChild(view);
    view.scrollIntoView({ block: "start" });
  }

  function stat(value, label) {
    return el("div", { class: "stat" }, el("span", { class: "stat-value" }, value), el("span", { class: "stat-label" }, label));
  }

  // Initialize show library from localStorage, then show the library dashboard first.
  if (LIB) {
    showLibrary = LIB.deserializeLibrary(safeLoadShowLibrary());
  }
  renderShowLibrary();
}());
