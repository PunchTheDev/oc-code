// Subnet concentration / decentralization metrics (#2106): pure statistics over a
// subnet's per-UID value distribution (stake_tao, emission_tao from the live
// `neurons` D1 tier). Every function is pure + exported for unit tests; the Worker
// does the D1 read + envelope. Null-safe by design: an empty / all-zero
// distribution yields a schema-stable `null` block (never throws), matching the
// live metagraph tiers the entity handlers already own.

// Top-K%-of-holders cutoffs reported as cumulative shares of the total.
const TOP_PERCENTILES = [1, 5, 10, 20];

// Round a ratio/amount to a stable decimal precision; null/non-finite → null so the
// schema stays `number|null` and JSON never carries a long floating-point tail.
function round(value, dp = 6) {
  if (value == null || !Number.isFinite(value)) return null;
  const factor = 10 ** dp;
  return Math.round(value * factor) / factor;
}

// Coerce a raw column array to the finite, strictly-positive values that actually
// make up a distribution. Zero / negative / NaN / null entries carry no share and
// are dropped, so `holders` counts real participants and the shares sum to 1.
function positiveValues(values) {
  const out = [];
  for (const raw of values) {
    const n = typeof raw === "number" ? raw : Number(raw);
    if (Number.isFinite(n) && n > 0) out.push(n);
  }
  return out;
}

// Gini coefficient via the sorted-rank formula
//   G = (2·Σ i·x₍ᵢ₎) / (n·Σx) − (n+1)/n,  x ascending, i = 1..n.
// 0 = perfectly equal, →1 = one holder owns everything. A lone holder is 0 by this
// definition (no inequality between a single point); HHI/Nakamoto capture that the
// single holder is nonetheless maximally concentrated. Tiny negative FP drift on a
// uniform distribution is clamped to 0.
function gini(ascending, total) {
  const n = ascending.length;
  let weighted = 0;
  for (let i = 0; i < n; i += 1) weighted += (i + 1) * ascending[i];
  const g = (2 * weighted) / (n * total) - (n + 1) / n;
  return g < 0 ? 0 : g;
}

// Herfindahl–Hirschman Index: Σ shareᵢ². Ranges [1/n, 1]; 1 = monopoly.
function hhi(values, total) {
  let sum = 0;
  for (const v of values) {
    const share = v / total;
    sum += share * share;
  }
  return sum;
}

// Normalize HHI to [0,1] independent of holder count: (H − 1/n)/(1 − 1/n). A single
// holder (n = 1) is defined as 1 (maximally concentrated).
function hhiNormalized(h, n) {
  if (n <= 1) return 1;
  return (h - 1 / n) / (1 - 1 / n);
}

// Nakamoto coefficient: the fewest top holders whose cumulative share strictly
// exceeds 50% — the smallest set that could collude to control the subnet.
function nakamoto(descending, total) {
  const half = total / 2;
  let acc = 0;
  let count = 0;
  for (const value of descending) {
    acc += value;
    count += 1;
    if (acc > half) break;
  }
  return count;
}

// Cumulative share held by the top ⌈n·p/100⌉ holders for each p in TOP_PERCENTILES
// (at least one holder). One prefix-sum pass, then each cutoff is an O(1) read.
function topShares(descending, total) {
  const n = descending.length;
  const prefix = new Array(n);
  let acc = 0;
  for (let i = 0; i < n; i += 1) {
    acc += descending[i];
    prefix[i] = acc;
  }
  const out = {};
  for (const p of TOP_PERCENTILES) {
    const k = Math.max(1, Math.ceil((n * p) / 100));
    out[`top_${p}pct_share`] = round(prefix[k - 1] / total);
  }
  return out;
}

// Shannon entropy of the share distribution (bits) + its normalization against the
// log2(n) maximum: 1 = perfectly uniform, →0 = fully concentrated.
function entropy(values, total) {
  let bits = 0;
  for (const v of values) {
    const share = v / total;
    if (share > 0) bits -= share * Math.log2(share);
  }
  const normalized = values.length > 1 ? bits / Math.log2(values.length) : 0;
  return { bits, normalized };
}

// Full concentration scorecard for one value column, or `null` when there is no
// positive distribution to measure (cold store / empty subnet / all-zero column).
export function computeConcentration(values) {
  const positives = positiveValues(Array.isArray(values) ? values : []);
  const holders = positives.length;
  if (holders === 0) return null;
  const total = positives.reduce((sum, v) => sum + v, 0);
  if (total <= 0) return null;
  const ascending = [...positives].sort((a, b) => a - b);
  const descending = [...positives].sort((a, b) => b - a);
  const h = hhi(descending, total);
  const { bits, normalized } = entropy(descending, total);
  return {
    holders,
    total: round(total, 4),
    gini: round(gini(ascending, total)),
    hhi: round(h),
    hhi_normalized: round(hhiNormalized(h, holders)),
    nakamoto_coefficient: nakamoto(descending, total),
    ...topShares(descending, total),
    entropy: round(bits),
    entropy_normalized: round(normalized),
  };
}

// Shape the neurons-tier rows for one subnet into the concentration artifact:
// stake + emission scorecards plus the snapshot stamp. Null-safe on junk/sparse
// rows — an empty array yields a schema-stable zero (stake/emission: null).
export function buildConcentration(rows, netuid) {
  const list = Array.isArray(rows) ? rows : [];
  // The rows share one cron capture, but don't assume an order — take the newest.
  let capturedAt = null;
  for (const row of list) {
    const captured = row?.captured_at ?? null;
    if (captured != null && (capturedAt == null || captured > capturedAt)) {
      capturedAt = captured;
    }
  }
  return {
    schema_version: 1,
    netuid,
    neuron_count: list.length,
    captured_at: capturedAt,
    stake: computeConcentration(list.map((row) => row?.stake_tao)),
    emission: computeConcentration(list.map((row) => row?.emission_tao)),
  };
}
