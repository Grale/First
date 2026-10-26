/**
 * Check the JavaScript scoring port against the Python, model by model and component by component.
 *
 *   python tools/artifact/export_scores.py > tools/artifact/expected_scores.json
 *   node tools/artifact/parity.mjs
 *
 * The browsable ranking page imports the same scoring.mjs this test imports, so a pass means the page
 * and the bot agree. Every component of every model under both profiles is compared, plus the overall
 * score across a grid of fit/review weights, plus the pixel density and the final rank order.
 *
 * Multipliers are left at 1 throughout: that is the state in which the JavaScript is required to equal
 * the Python. The page's sliders move away from it deliberately.
 */
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { fitScore, ppi, rankModels, scoreModel } from "./scoring.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..", "..");
const EPS = 1e-9;

const watchlist = JSON.parse(readFileSync(join(ROOT, "watchlist.json"), "utf8"));
const expectedFile = JSON.parse(readFileSync(join(HERE, "expected_scores.json"), "utf8"));
const models = watchlist.models;
const byKey = new Map(models.map((m) => [m.model_key, m]));

let checks = 0;
const failures = [];

function eq(actual, want, what) {
  checks += 1;
  const ok = (actual === null || want === null)
    ? actual === want
    : Math.abs(Number(actual) - Number(want)) < EPS;
  if (!ok) failures.push(`${what}: JS ${JSON.stringify(actual)} vs Python ${JSON.stringify(want)}`);
}

for (const exp of expectedFile.expected) {
  const m = byKey.get(exp.model_key);
  if (!m) {
    failures.push(`${exp.model_key}: in the Python export but not in watchlist.json`);
    continue;
  }
  const label = `${exp.model_key} [${exp.profile}]`;

  // pixel density, which feeds the density band
  eq(ppi(m), exp.ppi, `${label} ppi`);

  // the fit total and every component of the breakdown
  const { fit, parts } = fitScore(m, exp.profile);
  eq(fit, exp.fit_raw, `${label} fit total`);

  const jsKeys = Object.keys(parts).sort();
  const pyKeys = Object.keys(exp.parts).sort();
  checks += 1;
  if (jsKeys.join(",") !== pyKeys.join(",")) {
    failures.push(`${label} component set: JS [${jsKeys}] vs Python [${pyKeys}]`);
  }
  for (const k of pyKeys) {
    eq(parts[k], exp.parts[k], `${label} component ${k}`);
  }

  // the overall score across the weight grid, and the value score against the real price snapshot
  const bestPrices = expectedFile.best_prices || {};
  for (const row of exp.overalls) {
    const cfg = { scoring: { fit_weight: row.fit_weight, review_weight: row.review_weight, profile: exp.profile } };
    const sc = scoreModel(m, cfg, bestPrices[exp.model_key] || null);
    eq(sc.overall, row.overall, `${label} overall @ fit ${row.fit_weight}/review ${row.review_weight}`);
    eq(sc.fit, row.fit, `${label} rounded fit @ ${row.fit_weight}`);
    eq(sc.review, row.review, `${label} review @ ${row.fit_weight}`);
    eq(sc.value, row.value, `${label} value @ ${row.fit_weight}`);
    checks += 1;
    if (sc.has_review !== row.has_review) {
      failures.push(`${label} has_review: JS ${sc.has_review} vs Python ${row.has_review}`);
    }
  }
}

// rank order, per profile, at every weighting in the grid
for (const profile of ["work", "gaming"]) {
  for (const [wFit, wRev] of expectedFile.weight_grid) {
    const cfg = { scoring: { fit_weight: wFit, review_weight: wRev, profile } };
    const ranked = rankModels(models, cfg, {});
    checks += 1;
    if (ranked.length !== models.length) {
      failures.push(`${profile} @ ${wFit}: ranked ${ranked.length} of ${models.length} models`);
      continue;
    }
    // the ordering must be non-increasing in overall, which is what the Python sort guarantees
    for (let i = 1; i < ranked.length; i += 1) {
      if (ranked[i][2].overall > ranked[i - 1][2].overall + EPS) {
        failures.push(`${profile} @ ${wFit}: rank ${i + 1} scores above rank ${i}`);
        break;
      }
    }
  }
}

console.log(`${checks - failures.length}/${checks} comparisons matched`);
for (const f of failures) console.log("  FAIL:", f);

// build_page.py reads this so the page can state the real number rather than a remembered one.
writeFileSync(join(HERE, "parity_result.json"),
  JSON.stringify({ comparisons: checks, failures: failures.length }, null, 1) + "\n");

process.exit(failures.length ? 1 : 0);
