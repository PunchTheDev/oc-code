"use strict";

// Canvas layer stack + locking rules for Podcast Design Canvas.
//
// Locking fixes a layer's position in the stack — not just deletion. Reorder primitives
// respect locked layers: a locked layer cannot move itself, and neighbors cannot displace
// it. DOM-free so the screen and tests share one source of truth.
(function (global) {
  const LAYER_TYPES = {
    speaker: { label: "Speaker video frame", swatch: "#6c4cff", brand: false },
    captions: { label: "Captions", swatch: "#1b1c2e", brand: false },
    "lower-thirds": { label: "Lower-third", swatch: "#4a3aff", brand: false },
    title: { label: "Title moment", swatch: "#ff7a59", brand: false },
    broll: { label: "B-roll zone", swatch: "#9aa0c3", brand: false },
    background: { label: "Shape / background", swatch: "#2a2d4a", brand: false },
    brand: { label: "Logo / show branding", swatch: "#c8324a", brand: true },
    "safe-area": { label: "Safe-area guide", swatch: "#5b5d77", brand: false },
  };

  function getLayerType(type) {
    return LAYER_TYPES[type] || { label: "Layer", swatch: "#5b5d77", brand: false };
  }

  function createLayer(type, id, options) {
    const opts = options || {};
    const meta = getLayerType(type);
    return {
      id: id || `layer-${Date.now()}`,
      type: type,
      visible: opts.visible !== false,
      locked: Boolean(opts.locked),
      brand: meta.brand,
    };
  }

  function sampleLayers() {
    return [
      createLayer("captions", "l1"),
      createLayer("speaker", "l2"),
      createLayer("lower-thirds", "l3"),
      createLayer("title", "l4"),
      createLayer("brand", "l5", { locked: true }),
    ];
  }

  function layerIndex(layers, id) {
    if (!Array.isArray(layers)) {
      return -1;
    }
    return layers.findIndex((layer) => layer && layer.id === id);
  }

  function canMoveLayer(layers, index, delta) {
    if (!Array.isArray(layers) || index < 0 || index >= layers.length) {
      return false;
    }
    if (layers[index].locked) {
      return false;
    }
    const target = index + delta;
    if (target < 0 || target >= layers.length) {
      return false;
    }
    if (layers[target].locked) {
      return false;
    }
    return true;
  }

  function moveLayer(layers, index, delta) {
    if (!canMoveLayer(layers, index, delta)) {
      return layers.slice();
    }
    const copy = layers.slice();
    const target = index + delta;
    const moving = copy[index];
    copy[index] = copy[target];
    copy[target] = moving;
    return copy;
  }

  function toggleLock(layers, index) {
    if (!Array.isArray(layers) || index < 0 || index >= layers.length) {
      return layers.slice();
    }
    const copy = layers.slice();
    copy[index] = Object.assign({}, copy[index], { locked: !copy[index].locked });
    return copy;
  }

  function toggleVisibility(layers, index) {
    if (!Array.isArray(layers) || index < 0 || index >= layers.length) {
      return layers.slice();
    }
    const copy = layers.slice();
    copy[index] = Object.assign({}, copy[index], { visible: !copy[index].visible });
    return copy;
  }

  function removeLayer(layers, index) {
    if (!Array.isArray(layers) || index < 0 || index >= layers.length) {
      return layers.slice();
    }
    if (layers[index].locked) {
      return layers.slice();
    }
    const copy = layers.slice();
    copy.splice(index, 1);
    return copy;
  }

  function addLayer(layers, type, id) {
    const list = Array.isArray(layers) ? layers.slice() : [];
    list.unshift(createLayer(type, id));
    return list;
  }

  function visibleLayersForStage(layers) {
    if (!Array.isArray(layers)) {
      return [];
    }
    const visible = [];
    for (let i = layers.length - 1; i >= 0; i -= 1) {
      if (layers[i].visible) {
        visible.push(layers[i]);
      }
    }
    return visible;
  }

  function evaluateLayout(layers) {
    const list = Array.isArray(layers) ? layers : [];
    const checks = [];

    const captionsIdx = list.findIndex((layer) => layer.type === "captions" && layer.visible);
    const speakerIdx = list.findIndex((layer) => layer.type === "speaker" && layer.visible);
    if (captionsIdx >= 0 && speakerIdx >= 0 && speakerIdx < captionsIdx) {
      checks.push({
        title: "Captions may be covered",
        action: "A speaker frame sits above the captions. Move captions higher in the stack so they stay readable.",
        tone: "review",
      });
    }

    list.forEach((layer) => {
      const meta = getLayerType(layer.type);
      if (meta.brand && layer.visible && !layer.locked) {
        checks.push({
          title: "Brand element is unlocked",
          action: "Lock the logo or show branding so its stack position cannot move by accident while editing.",
          tone: "review",
        });
      }
    });

    const hiddenSpeakers = list.filter((layer) => layer.type === "speaker" && !layer.visible).length;
    if (hiddenSpeakers > 0) {
      checks.push({
        title: `${hiddenSpeakers} speaker frame${hiddenSpeakers === 1 ? "" : "s"} hidden`,
        action: "A hidden speaker will not appear in this layout. Show the frame or confirm they are audio-only.",
        tone: "info",
      });
    }

    const hasReview = checks.some((check) => check.tone === "review");
    return { checks, overall: hasReview ? "review" : "ready" };
  }

  const api = {
    LAYER_TYPES,
    getLayerType,
    createLayer,
    sampleLayers,
    layerIndex,
    canMoveLayer,
    moveLayer,
    toggleLock,
    toggleVisibility,
    removeLayer,
    addLayer,
    visibleLayersForStage,
    evaluateLayout,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
    return;
  }

  global.PdcCanvasLayers = api;
}(typeof window !== "undefined" ? window : globalThis));