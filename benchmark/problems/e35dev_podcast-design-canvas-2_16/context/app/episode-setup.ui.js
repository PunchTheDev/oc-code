"use strict";

// Browser wiring for episode setup (#1), preset style (#4), and canvas editor (#11).
// Renders the setup wizard, workspace, style selection, and canvas editor from the
// shared PdcEpisodeSetup / PdcEpisodeStyle / PdcCanvasEditor / PdcShowTemplates rules.
(function () {
  const ES = window.PdcEpisodeSetup;
  const STY = window.PdcEpisodeStyle;
  const CL = window.PdcCanvasLayers;
  const CE = window.PdcCanvasEditor;
  const TM = window.PdcShowTemplates;
  const root = document.getElementById("app");
  const stepPill = document.querySelector(".step-pill");
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
  const TPL_STORAGE_KEY = "pdc-show-templates";
  let templateStore = TM ? TM.deserializeStore(safeLoadTemplates()) : { templates: [] };
  let activeTemplateId = null;
  let canvasDoc = null;
  let canvasLayerCounter = 20;
  let workspaceSummaryCache = null;

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

  function summaryFromWorkspace() {
    return workspaceSummaryCache;
  }

  function setStep(label) {
    if (stepPill) {
      stepPill.textContent = label;
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

  function nextRole() {
    const used = {};
    state.speakers.forEach((s) => {
      used[s.role] = true;
    });
    const free = ES.SPEAKER_BUCKETS.find((bucket) => !used[bucket]);
    return free || `Guest ${state.speakers.length}`;
  }

  // ---- Setup view -------------------------------------------------------------

  function renderSetup() {
    root.innerHTML = "";
    setStep("Step 1 of 6 · Set up episode");
    state.sourceMode = ES.normalizeMode(state.sourceMode);

    const form = el("form", { class: "setup", novalidate: true });
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      onContinue();
    });

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
    });

    const detailsCard = el(
      "section",
      { class: "card" },
      el("h2", {}, "Episode details"),
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
      { class: "card" },
      el("h2", {}, "Recording source"),
      el("p", { class: "hint" }, "Bring in your recording, then assign each track to a speaker below."),
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
    const speakersCard = el("section", { class: "card" }, el("h2", {}, "Speakers & sources"));
    state.speakers.forEach((speaker, index) => {
      speakersCard.appendChild(renderSpeaker(speaker, index));
    });

    const addButton = el("button", { type: "button", class: "ghost" }, "+ Add speaker source");
    addButton.addEventListener("click", () => {
      state.speakers.push(ES.createSpeaker(nextRole()));
      renderSetup();
    });
    speakersCard.appendChild(addButton);
    form.appendChild(speakersCard);

    if (TM) {
      const saved = TM.listTemplates(templateStore);
      if (saved.length) {
        form.appendChild(renderSavedTemplatesCard(saved, null));
      }
    }

    form.appendChild(
      el(
        "div",
        { class: "actions" },
        el("button", { type: "submit", class: "primary" }, "Continue to style →"),
      ),
    );

    root.appendChild(form);

    if (showErrors) {
      focusFirstError();
    }
  }

  function renderSpeaker(speaker, index) {
    const card = el("div", { class: "speaker" });
    const header = el(
      "div",
      { class: "speaker-head" },
      el("span", { class: "speaker-tag" }, `Source ${index + 1}`),
    );
    const removeButton = el("button", {
      type: "button",
      class: "link-button",
      "aria-label": `Remove source ${index + 1}`,
      disabled: state.speakers.length <= 1 ? true : null,
    }, "Remove");
    removeButton.addEventListener("click", () => {
      if (state.speakers.length > 1) {
        state.speakers.splice(index, 1);
        renderSetup();
      }
    });
    header.appendChild(removeButton);
    card.appendChild(header);

    // Name
    const nameInput = el("input", {
      id: `f-sp-${index}-name`,
      type: "text",
      value: speaker.name,
      placeholder: "Speaker name",
      "aria-invalid": isInvalid(`speaker:${index}:name`) ? "true" : null,
    });
    nameInput.addEventListener("input", (e) => {
      speaker.name = e.target.value;
    });
    card.appendChild(field("Speaker name", nameInput, `speaker:${index}:name`));

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
    });
    card.appendChild(field("Role", roleSelect, `speaker:${index}:role`));

    // Source: file (upload) or optional channel label (riverside)
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
      card.appendChild(field("Speaker video file", fileInput, `speaker:${index}:source`));
      card.appendChild(chosen);
    } else {
      const trackInput = el("input", {
        id: `f-sp-${index}-source`,
        type: "text",
        value: speaker.trackLabel,
        placeholder: "e.g. Track 1 (optional)",
      });
      trackInput.addEventListener("input", (e) => {
        speaker.trackLabel = e.target.value;
      });
      card.appendChild(field("Channel label", trackInput, null, "Optional — name this speaker's channel in the recording."));
    }

    // Optional social links
    const social = el("details", { class: "social" });
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
    card.appendChild(social);

    return card;
  }

  function onContinue() {
    const result = ES.validateDraft(state);
    errors = result.errors;
    showErrors = true;
    if (result.ok) {
      const summary = ES.summarize(state);
      if (STY && !appliedStyle) {
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

  function renderWorkspace(summary) {
    root.innerHTML = "";
    setStep("Step 1 of 6 · Episode workspace");

    const view = el("div", { class: "workspace" });
    view.appendChild(
      el(
        "div",
        { class: "workspace-head" },
        el("p", { class: "eyebrow" }, "Episode workspace"),
        el("h2", {}, summary.episodeName),
      ),
    );

    // Captured context
    const context = el(
      "section",
      { class: "card" },
      el("h3", {}, "Captured context"),
      el(
        "div",
        { class: "stats" },
        stat(summary.sourceModeLabel, "Source"),
        stat(String(summary.speakerCount), `Speaker${summary.speakerCount === 1 ? "" : "s"}`),
        stat(String(summary.socialLinkCount), `Social link${summary.socialLinkCount === 1 ? "" : "s"}`),
      ),
    );
    if (summary.riversideLink) {
      context.appendChild(
        el(
          "p",
          { class: "context-link" },
          "Recording: ",
          el("a", { href: summary.riversideLink, target: "_blank", rel: "noopener noreferrer" }, summary.riversideLink),
        ),
      );
    }
    view.appendChild(context);

    // Sources & speakers
    const sources = el("section", { class: "card" }, el("h3", {}, "Sources & speakers"));
    summary.speakers.forEach((speaker) => {
      const row = el(
        "div",
        { class: "summary-speaker" },
        el(
          "div",
          { class: "summary-speaker-main" },
          el("span", { class: "role-pill" }, speaker.role || "Unassigned"),
          el("span", { class: "summary-name" }, speaker.name || "Unnamed speaker"),
        ),
        el("p", { class: "summary-source" }, speaker.sourceLabel),
      );
      if (speaker.social.length) {
        const chips = el("div", { class: "chips" });
        speaker.social.forEach((link) => {
          chips.appendChild(
            el("a", { class: "chip", href: link.url, target: "_blank", rel: "noopener noreferrer" }, link.label),
          );
        });
        row.appendChild(chips);
      }
      sources.appendChild(row);
    });
    view.appendChild(sources);

    // Selected style (shown once a preset has been applied to the episode)
    if (STY && appliedStyle) {
      const styleCard = el(
        "section",
        { class: "card selected-style" },
        el("h3", {}, "Selected style"),
        el(
          "div",
          { class: "selected-style-body" },
          renderPreview(summary, styleSelection, true),
          el(
            "div",
            { class: "selected-style-meta" },
            el("p", { class: "selected-style-name" }, appliedStyle.presetName),
            el("p", { class: "hint" }, appliedStyle.tagline),
            el(
              "p",
              { class: "selected-style-facts" },
              `Layout: ${appliedStyle.layoutLabel} · Pacing: ${appliedStyle.pacingLabel} · Captions: ${appliedStyle.captionStyle}`,
            ),
          ),
        ),
      );
      view.appendChild(styleCard);
    }

    // Saved show template (after canvas save)
    if (activeTemplateId && TM) {
      const active = TM.getTemplate(templateStore, activeTemplateId);
      if (active) {
        view.appendChild(
          el(
            "section",
            { class: "card saved-template" },
            el("h3", {}, "Show template"),
            el("p", { class: "saved-template-name" }, active.name),
            el(
              "p",
              { class: "hint" },
              `Reusable layout based on ${active.canvas.presetName || "your preset"}. Available for future episodes.`,
            ),
          ),
        );
      }
    }

    // Next step — style, canvas, or template
    const styleAvailable = Boolean(STY);
    const canvasAvailable = Boolean(CL && CE && appliedStyle);
    const styleButton = el(
      "button",
      { type: "button", class: canvasAvailable ? "ghost" : "primary", disabled: styleAvailable ? null : true },
      appliedStyle ? "Change style →" : "Choose a style →",
    );
    if (styleAvailable) {
      styleButton.addEventListener("click", () => renderStyle(summary));
    }
    const canvasButton = el(
      "button",
      { type: "button", class: "primary", disabled: canvasAvailable ? null : true },
      activeTemplateId ? "Edit canvas →" : "Open canvas editor →",
    );
    if (canvasAvailable) {
      canvasButton.addEventListener("click", () => openCanvasEditor(summary));
    }
    const nextTitle = activeTemplateId
      ? "Template saved"
      : appliedStyle
        ? "Style applied"
        : "Ready for the next step";
    const nextCopy = activeTemplateId
      ? "Your show template is saved and ready for the next episode."
      : appliedStyle
        ? "Your style is set. Open the canvas editor to personalize the layout and save a reusable show template."
        : "Your sources, speaker roles, and context are saved. Pick a visual style next.";
    const actions = el("div", { class: "actions" });
    if (appliedStyle && canvasAvailable) {
      actions.appendChild(canvasButton);
      actions.appendChild(styleButton);
    } else {
      actions.appendChild(styleButton);
    }
    actions.appendChild(
      (function () {
        const back = el("button", { type: "button", class: "ghost" }, "← Edit setup");
        back.addEventListener("click", () => {
          showErrors = false;
          renderSetup();
        });
        return back;
      })(),
    );
    view.appendChild(
      el(
        "section",
        { class: "card next-step" },
        el("h3", {}, nextTitle),
        el("p", {}, nextCopy),
        actions,
      ),
    );

    if (TM) {
      const saved = TM.listTemplates(templateStore);
      if (saved.length) {
        view.appendChild(renderSavedTemplatesCard(saved, summary));
      }
    }

    root.appendChild(view);
    view.scrollIntoView({ block: "start" });
  }

  function renderSavedTemplatesCard(saved, summary) {
    const card = el("section", { class: "card template-picker" }, el("h3", {}, "Saved show templates"));
    card.appendChild(
      el("p", { class: "hint" }, "Reuse a layout you designed for a previous episode."),
    );
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
      const useButton = el("button", { type: "button", class: "ghost" }, "Use template");
      useButton.addEventListener("click", () => {
        applySavedTemplate(item.id, summary);
      });
      row.appendChild(useButton);
      list.appendChild(row);
    });
    card.appendChild(list);
    return card;
  }

  function applySavedTemplate(templateId, summary) {
    if (!TM) {
      return;
    }
    const template = TM.getTemplate(templateStore, templateId);
    if (!template) {
      return;
    }
    canvasDoc = TM.applyTemplate(template);
    activeTemplateId = template.id;
    if (canvasDoc && STY) {
      styleSelection = styleSelection || STY.createSelection();
      styleSelection.presetId = canvasDoc.presetId || styleSelection.presetId;
      styleSelection.layout = canvasDoc.layoutId || styleSelection.layout;
      styleSelection.pacing = canvasDoc.pacingId || styleSelection.pacing;
      appliedStyle = STY.summarizeStyle(styleSelection, summary ? summary.speakerCount : 3);
    }
    if (summary) {
      renderWorkspace(summary);
    } else {
      renderSetup();
    }
  }

  function openCanvasEditor(summary) {
    workspaceSummaryCache = summary;
    if (!canvasDoc && CE && appliedStyle) {
      canvasDoc = CE.createFromStyle(appliedStyle, summary, styleSelection);
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
    setStep("Step 3 of 6 · Canvas editor");

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

  // ---- Preset style selection + preview (#4) ----------------------------------

  // A live preview built from the real assigned speakers. `compact` renders the smaller
  // version shown on the workspace once a style is applied.
  function renderPreview(summary, selection, compact) {
    const preset = STY.getPreset(selection && selection.presetId);
    const pacing = STY.getPacing(selection && selection.pacing);
    const frames = STY.buildPreviewFrames(summary.speakers, selection, summary.speakerCount);
    const layoutId = STY.resolveLayout(selection, summary.speakerCount);

    const stage = el("div", {
      class: `preview-stage stage-${layoutId} pacing-${pacing.id}${compact ? " compact" : ""}`,
    });
    stage.style.background = preset.background;
    stage.style.color = preset.textColor;

    const frameWrap = el("div", { class: "preview-frames" });
    frames.forEach((frame) => {
      const frameEl = el(
        "div",
        { class: `preview-frame${frame.active ? " active" : ""}` },
        el("span", { class: "preview-role" }, frame.role),
        el("span", { class: "preview-name" }, frame.name),
      );
      frameEl.style.borderColor = preset.accent;
      if (frame.active) {
        frameEl.style.boxShadow = `0 0 0 2px ${preset.accent}`;
      }
      frameWrap.appendChild(frameEl);
    });
    stage.appendChild(frameWrap);

    // Sample caption strip so the caption treatment is visible in the preview.
    const caption = el(
      "div",
      { class: "preview-caption" },
      el("span", { class: "preview-caption-text" }, "Sample caption — this is how on-screen text will look."),
    );
    caption.style.background = preset.accent;
    stage.appendChild(caption);

    if (!compact) {
      const foot = el(
        "p",
        { class: "preview-foot" },
        `${pacing.label} pacing · ${preset.captionStyle} · ${STY.getLayout(layoutId).label}`,
      );
      const container = el("div", {}, stage, foot);
      return container;
    }
    return stage;
  }

  function renderStyle(summary) {
    root.innerHTML = "";
    setStep("Step 2 of 6 · Choose a style");
    if (!styleSelection) {
      styleSelection = STY.createSelection();
    }

    const view = el("div", { class: "style-step" });
    view.appendChild(
      el(
        "div",
        { class: "workspace-head" },
        el("p", { class: "eyebrow" }, "Choose a style"),
        el("h2", {}, `Pick a look for ${summary.episodeName}`),
        el("p", { class: "hint" }, "Start from a preset, then fine-tune layout and pacing. The preview uses your real speakers."),
      ),
    );

    const layoutGrid = el("div", { class: "style-layout" });

    // Controls column
    const controls = el("section", { class: "card" }, el("h3", {}, "Style presets"));
    const presetGrid = el("div", { class: "preset-grid" });
    STY.STYLE_PRESETS.forEach((preset) => {
      const selected = styleSelection.presetId === preset.id;
      const card = el(
        "button",
        {
          type: "button",
          class: `preset-card${selected ? " selected" : ""}`,
          "aria-pressed": selected ? "true" : "false",
        },
        (function () {
          const swatch = el("span", { class: "preset-swatch" });
          swatch.style.background = preset.background;
          swatch.style.borderColor = preset.accent;
          const dot = el("span", { class: "preset-swatch-dot" });
          dot.style.background = preset.accent;
          swatch.appendChild(dot);
          return swatch;
        })(),
        el("span", { class: "preset-name" }, preset.name),
        el("span", { class: "preset-tagline" }, preset.tagline),
      );
      card.addEventListener("click", () => {
        styleSelection = STY.applyPresetToSelection(styleSelection, preset.id, layoutCustomized);
        renderStyle(summary);
      });
      presetGrid.appendChild(card);
    });
    controls.appendChild(presetGrid);

    // Layout control
    const layoutSelect = el("select", { id: "style-layout" });
    STY.LAYOUTS.forEach((layout) => {
      layoutSelect.appendChild(
        el("option", { value: layout.id, selected: styleSelection.layout === layout.id ? true : null }, layout.label),
      );
    });
    layoutSelect.addEventListener("change", (e) => {
      styleSelection.layout = e.target.value;
      layoutCustomized = styleSelection.layout !== "auto";
      renderStyle(summary);
    });
    controls.appendChild(field("Layout", layoutSelect, null, "Auto matches the number of speakers you set up."));

    // Pacing control
    const pacingSelect = el("select", { id: "style-pacing" });
    STY.PACING.forEach((pacing) => {
      pacingSelect.appendChild(
        el("option", { value: pacing.id, selected: styleSelection.pacing === pacing.id ? true : null }, pacing.label),
      );
    });
    pacingSelect.addEventListener("change", (e) => {
      styleSelection.pacing = e.target.value;
      renderStyle(summary);
    });
    controls.appendChild(field("Pacing", pacingSelect, null, STY.getPacing(styleSelection.pacing).note));

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

    // Actions
    const applyButton = el("button", { type: "button", class: "primary" }, "Apply style & continue →");
    applyButton.addEventListener("click", () => {
      appliedStyle = STY.summarizeStyle(styleSelection, summary.speakerCount);
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

  renderSetup();
}());
