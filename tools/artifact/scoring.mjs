/**
 * JavaScript port of monbot/scoring.py.
 *
 * The browsable ranking page and tools/artifact/parity.mjs both import this one file, so what the
 * parity test checks is exactly what the page runs. Keep it a line-for-line mirror of the Python:
 * every band table, every unknown value and every tie-break below is copied from fit_score() there,
 * and tools/artifact/parity.mjs fails if the two ever disagree on any model under either profile.
 *
 * The only addition is `mult`, a per-component multiplier the page's sliders drive. At the default of
 * 1 for every component the output must equal the Python exactly, which is the state parity runs in.
 */

export const DEFAULT_PROFILE = "work";
export const PROFILES = ["work", "gaming"];

/** Components in display order, per profile, with the maximum each can reach. */
export const COMPONENTS = {
  work: [
    ["panel", "Panel type", 13],
    ["usb_c", "USB-C power delivery", 12],
    ["density", "Pixel density", 11],
    ["eye_comfort", "TÜV Eye Comfort", 11],
    ["kvm", "KVM", 7],
    ["contrast", "Contrast", 7],
    ["gamut", "Colour gamut", 5],
    ["stand", "Height-adjustable stand", 5],
    ["hdr", "HDR tier", 5],
    ["refresh", "Refresh rate", 4],
    ["year", "Model year", 5],
    ["burn_in", "Burn-in cover", 3],
    ["curvature", "Curvature", 2],
    ["dp", "DisplayPort version", 1],
    ["response", "Measured response", 1],
    ["priority", "Starred by you", 8],
  ],
  gaming: [
    ["refresh", "Refresh rate", 18],
    ["response", "Response time", 14],
    ["panel", "Panel type", 14],
    ["contrast", "Contrast", 10],
    ["vrr", "VRR certification", 7],
    ["hdr", "HDR tier", 7],
    ["curvature", "Curvature", 5],
    ["density", "Pixel density", 4],
    ["year", "Model year", 4],
    ["dp", "DisplayPort version", 3],
    ["usb_c", "USB-C power delivery", 2],
    ["stand", "Height-adjustable stand", 2],
    ["kvm", "KVM", 1],
    ["eye_comfort", "TÜV Eye Comfort", 1],
    ["priority", "Starred by you", 8],
  ],
};

const isNil = (v) => v === null || v === undefined;

/** Python's `round(x, 1)`: half-to-even, unlike JS Math.round which always rounds a half up. */
export function round1(x) {
  const scaled = x * 10;
  const frac = scaled - Math.floor(scaled);
  if (Math.abs(frac - 0.5) < Number.EPSILON * Math.max(1, Math.abs(scaled))) {
    const fl = Math.floor(scaled);
    return (fl % 2 === 0 ? fl : fl + 1) / 10;
  }
  return Math.round(scaled) / 10;
}

function band(v, bands, unknown) {
  if (isNil(v)) return unknown;
  for (const [threshold, pts] of bands) if (v >= threshold) return pts;
  return 0;
}

function bandLowerIsBetter(v, bands, unknown, worst) {
  if (isNil(v)) return unknown;
  for (const [threshold, pts] of bands) if (v <= threshold) return pts;
  return worst;
}

export function isOled(m) {
  return `${m.panel || ""} ${m.family || ""} ${m.model_key || ""}`.toUpperCase().includes("OLED");
}

export function ppi(m) {
  const s = m.specs || {};
  if (!s.width || !s.height || !m.size_inch) return null;
  return round1(Math.sqrt(s.width ** 2 + s.height ** 2) / Number(m.size_inch));
}

export function panelPoints(text, { ips_black, nano_ips, miniled, ips, woled, qd_oled, va, other }) {
  const t = (text || "").toUpperCase().replaceAll("-", " ");
  if (t.includes("MINI LED") || t.includes("MINILED")) return miniled;
  if (t.includes("OLED")) {
    if (t.includes("QD") || t.includes("QUANTUM")) return qd_oled;
    return woled;
  }
  if (t.includes("IPS BLACK")) return ips_black;
  if (t.includes("NANO IPS") || t.includes("FAST IPS")) return nano_ips;
  if (t.includes("IPS")) return ips;
  if (t.includes("VA")) return va;
  return other;
}

function responsePoints(m, bands, unknown, worst, quotedCap) {
  const extra = (m.review && m.review.specs_extra) || {};
  const measured = extra.measured_response_ms;
  if (!isNil(measured)) return bandLowerIsBetter(Number(measured), bands, unknown, worst);
  const quoted = (m.specs || {}).response_ms;
  if (!isNil(quoted)) {
    return Math.min(quotedCap, bandLowerIsBetter(Number(quoted), bands, unknown, worst));
  }
  return unknown;
}

function contrastPoints(m, oledPts, bands, unknown) {
  if (isOled(m)) return oledPts;
  const extra = (m.review && m.review.specs_extra) || {};
  let value = extra.measured_contrast;
  if (isNil(value)) value = (m.specs || {}).contrast;
  return band(isNil(value) ? null : Number(value), bands, unknown);
}

function gamutPoints(m, p3_95, p3_90, srgb_99, unknown) {
  const s = m.specs || {};
  const extra = (m.review && m.review.specs_extra) || {};
  let p3 = extra.measured_dci_p3_pct;
  if (isNil(p3)) p3 = s.dci_p3_pct;
  if (!isNil(p3)) {
    if (p3 >= 95) return p3_95;
    if (p3 >= 90) return p3_90;
  }
  if (!isNil(s.srgb_pct) && s.srgb_pct >= 99) return srgb_99;
  return isNil(p3) && isNil(s.srgb_pct) ? unknown : 0;
}

export function hdrPoints(hdr, { true_black, dhdr_1000, dhdr_600, dhdr_500, dhdr_400, hdr10, unknown }) {
  const t = (hdr || "").toUpperCase().replaceAll("-", " ");
  if (!t) return unknown;
  if (t.includes("TRUE BLACK")) return true_black;
  for (const [marker, pts] of [["1400", dhdr_1000], ["1000", dhdr_1000], ["600", dhdr_600],
                               ["500", dhdr_500], ["400", dhdr_400]]) {
    if (t.includes(marker)) return pts;
  }
  return hdr10;
}

export function eyeComfortPoints(stars, { five, four, three, certified, none_documented, unknown }) {
  if (isNil(stars)) return unknown;
  if (stars >= 5) return five;
  if (stars === 4) return four;
  if (stars === 3) return three;
  if (stars >= 1) return certified;
  return none_documented;
}

export function curvaturePoints(curvature, { aggressive, medium, gentle, flat, unknown }) {
  const t = (curvature || "").toUpperCase().trim();
  if (!t) return unknown;
  if (t.includes("FLAT")) return flat;
  const digits = t.replace(/\D/g, "");
  if (!digits) return unknown;
  const r = parseInt(digits, 10);
  if (r <= 1000) return aggressive;
  if (r <= 1200) return medium;
  return gentle;
}

export function dpPoints(version, { v21, v14, older, unknown }) {
  const t = (version || "").trim();
  if (!t) return unknown;
  const v = parseFloat(t.split(/\s+/)[0]);
  if (Number.isNaN(v)) return unknown;
  if (v >= 2.0) return v21;
  if (v >= 1.4) return v14;
  return older;
}

export function vrrPoints(m, { both, one, plain, none, unknown }) {
  const s = m.specs || {};
  const brand = (s.vrr_brand || "").toUpperCase();
  const hasGsync = brand.replaceAll("-", " ").includes("G SYNC") || brand.includes("GSYNC");
  const hasFreesync = brand.includes("FREESYNC");
  if (hasGsync && hasFreesync) return both;
  if (hasGsync || hasFreesync) return one;
  if (s.vrr === true) return plain;
  if (s.vrr === false) return none;
  return unknown;
}

export function burnInPoints(m, { covered_long, covered_short, uncovered, not_oled }) {
  if (!isOled(m)) return not_oled;
  const years = (m.specs || {}).burn_in_warranty_years;
  if (isNil(years)) return uncovered;
  if (years >= 3) return covered_long;
  if (years >= 2) return covered_short;
  return uncovered;
}

/**
 * Fit score and its per-component breakdown.
 * `mult` multiplies individual components (the page's sliders); all-1 reproduces the Python exactly.
 */
export function fitScore(m, profile = DEFAULT_PROFILE, mult = {}) {
  const s = m.specs || {};
  let parts;

  if (profile === "gaming") {
    parts = {
      refresh: band(s.hz, [[240, 18], [165, 14], [144, 11], [120, 8], [100, 5]], 0),
      response: responsePoints(m, [[1, 14], [3, 12], [5, 8], [8, 4]], 5, 2, 8),
      panel: panelPoints(m.panel, { ips_black: 9, nano_ips: 10, miniled: 11, ips: 9, woled: 13, qd_oled: 14, va: 6, other: 7 }),
      contrast: contrastPoints(m, 10, [[3000, 7], [2000, 6], [1500, 4], [1000, 3]], 3),
      vrr: vrrPoints(m, { both: 7, one: 5, plain: 3, none: 0, unknown: 1 }),
      hdr: hdrPoints(s.hdr, { true_black: 7, dhdr_1000: 7, dhdr_600: 5, dhdr_500: 4, dhdr_400: 2, hdr10: 1, unknown: 1 }),
      curvature: curvaturePoints(s.curvature, { aggressive: 5, medium: 4, gentle: 3, flat: 2, unknown: 2 }),
      density: band(ppi(m), [[140, 4], [120, 3], [105, 3], [95, 2]], 2),
      year: m.year ? band(m.year, [[2026, 4], [2025, 3], [2024, 2]], 1) : 1,
      dp: dpPoints(s.dp_version, { v21: 3, v14: 2, older: 1, unknown: 1 }),
      usb_c: band(s.usb_c_pd_w, [[90, 2], [1, 1]], 0),
      stand: s.height_adjust ? 2 : (isNil(s.height_adjust) ? 1 : 0),
      kvm: s.kvm ? 1 : 0,
      eye_comfort: (s.tuv_eye_comfort_stars || 0) >= 1 ? 1 : 0,
      priority: m.priority ? 8 : 0,
    };
  } else {
    parts = {
      panel: panelPoints(m.panel, { ips_black: 13, nano_ips: 12, miniled: 12, ips: 11, woled: 9, qd_oled: 7, va: 6, other: 8 }),
      density: band(ppi(m), [[140, 11], [120, 9], [105, 8], [95, 5]], 5),
      usb_c: band(s.usb_c_pd_w, [[90, 12], [65, 9], [45, 6], [1, 3]], isNil(s.usb_c_pd_w) ? 2 : 0),
      kvm: s.kvm ? 7 : (isNil(s.kvm) ? 1 : 0),
      eye_comfort: eyeComfortPoints(s.tuv_eye_comfort_stars, { five: 11, four: 8, three: 6, certified: 4, none_documented: 0, unknown: 2 }),
      contrast: contrastPoints(m, 7, [[3000, 7], [2000, 6], [1500, 4], [1000, 3]], 3),
      gamut: gamutPoints(m, 5, 4, 3, 2),
      stand: s.height_adjust ? 5 : (isNil(s.height_adjust) ? 2 : 0),
      hdr: hdrPoints(s.hdr, { true_black: 5, dhdr_1000: 5, dhdr_600: 5, dhdr_500: 4, dhdr_400: 2, hdr10: 1, unknown: 1 }),
      refresh: band(s.hz, [[165, 4], [144, 3], [120, 2], [100, 1]], 0),
      year: m.year ? band(m.year, [[2026, 5], [2025, 4], [2024, 3]], 2) : 2,
      curvature: curvaturePoints(s.curvature, { aggressive: 1, medium: 2, gentle: 2, flat: 2, unknown: 1 }),
      dp: dpPoints(s.dp_version, { v21: 1, v14: 1, older: 0, unknown: 1 }),
      response: responsePoints(m, [[5, 1]], 1, 0, 1),
      burn_in: burnInPoints(m, { covered_long: 3, covered_short: 2, uncovered: 0, not_oled: 3 }),
      priority: m.priority ? 8 : 0,
    };
  }

  // Deductions. A penalty may name the profiles it applies to; one with no "profiles" key applies
  // everywhere. Penalties are never scaled by the sliders: a flaw is a flaw at any weighting.
  const penalties = (((m.review || {}).fit_penalties) || [])
    .filter((p) => !p.profiles || p.profiles.includes(profile));

  const scaled = {};
  for (const [k, v] of Object.entries(parts)) {
    const f = isNil(mult[k]) ? 1 : Number(mult[k]);
    scaled[k] = f === 1 ? v : v * f;
  }
  if (penalties.length) {
    scaled.penalties = penalties.reduce((a, p) => a + parseInt(p.points, 10), 0);
  }
  const total = Object.values(scaled).reduce((a, b) => a + b, 0);
  return { fit: Math.max(0, total), parts: scaled };
}

/** Mirror of score_model(): fit, review, overall, value. */
export function scoreModel(m, cfg = {}, bestPrice = null, mult = {}) {
  const weights = cfg.scoring || {};
  const wFit = Number(isNil(weights.fit_weight) ? 0.5 : weights.fit_weight);
  const wRev = Number(isNil(weights.review_weight) ? 0.5 : weights.review_weight);
  const { fit, parts } = fitScore(m, String(weights.profile || DEFAULT_PROFILE).toLowerCase(), mult);

  const review = m.review || {};
  const rev = !isNil(review.critic) ? review.review_score : null;
  const reviewScore = isNil(rev) ? null : Number(rev) * 10;

  let overall;
  if (isNil(reviewScore) || wFit + wRev === 0) overall = fit;
  else overall = (fit * wFit + reviewScore * wRev) / (wFit + wRev);

  const value = bestPrice ? overall / (bestPrice / 1000.0) : null;
  return {
    fit: round1(fit),
    review: isNil(reviewScore) ? null : round1(reviewScore),
    overall: round1(overall),
    parts,
    confidence: review.confidence || "",
    has_review: !isNil(reviewScore),
    value: isNil(value) ? null : round1(value),
    raw: { fit, review: reviewScore, overall },
  };
}

/** Mirror of rank_models(): sort by overall desc, then review desc, then model_key asc. */
export function rankModels(models, cfg = {}, bestPrices = {}, mult = {}) {
  const scored = models.map((m) => [m, scoreModel(m, cfg, bestPrices[m.model_key] || null, mult)]);
  scored.sort((a, b) => {
    if (b[1].overall !== a[1].overall) return b[1].overall - a[1].overall;
    const ar = a[1].review || 0, br = b[1].review || 0;
    if (br !== ar) return br - ar;
    return a[0].model_key < b[0].model_key ? -1 : a[0].model_key > b[0].model_key ? 1 : 0;
  });
  return scored.map(([m, s], i) => [i + 1, m, s]);
}
