"use strict";

// Free/Paid pricing label for creator gallery listings (#159).
// Run with: `node tests/gallery-pricing.test.js`.

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const gallery = require("../app/creator-template-gallery.js");

let passed = 0;
function test(name, fn) { fn(); passed += 1; console.log(`  ok ${name}`); }

const canvas = { background: "#10131f", accent: "#6c4cff", layoutId: "grid", presetName: "Studio" };

test("normalizePricing defaults to free and accepts paid", () => {
  assert.strictEqual(gallery.normalizePricing("paid"), "paid");
  assert.strictEqual(gallery.normalizePricing("PAID"), "paid");
  assert.strictEqual(gallery.normalizePricing(""), "free");
  assert.strictEqual(gallery.normalizePricing(undefined), "free");
  assert.strictEqual(gallery.normalizePricing("anything"), "free");
});

test("createListing records the pricing label", () => {
  const paid = gallery.createListing({ name: "Pro Layout", pricing: "paid" }, canvas);
  assert.strictEqual(paid.pricing, "paid");
  const free = gallery.createListing({ name: "Open Layout" }, canvas);
  assert.strictEqual(free.pricing, "free");
});

test("listListings exposes pricing for every listing", () => {
  let g = gallery.createGallery();
  g = gallery.publishListing(g, { canvas }, { name: "Paid One", pricing: "paid" });
  g = gallery.publishListing(g, { canvas }, { name: "Free One" });
  const listed = gallery.listListings(g);
  const paid = listed.find((l) => l.name === "Paid One");
  const free = listed.find((l) => l.name === "Free One");
  assert.strictEqual(paid.pricing, "paid");
  assert.strictEqual(free.pricing, "free");
});

const ui = fs.readFileSync(path.join(__dirname, "../app/episode-setup.ui.js"), "utf8");
const styles = fs.readFileSync(path.join(__dirname, "../app/styles.css"), "utf8");

test("publish form offers a free/paid pricing control", () => {
  assert.ok(/id: "gallery-listing-pricing"/.test(ui));
  assert.ok(/pricing: pricingSelect\.value/.test(ui), "publish passes pricing");
});

test("gallery listing cards render the pricing label with styles", () => {
  assert.ok(/creator-gallery-card-pricing|creator-gallery-pricing/.test(ui));
  assert.ok(/pricing-free/.test(styles) && /pricing-paid/.test(styles));
});

console.log(`\ngallery-pricing: ${passed} test(s) passed.`);