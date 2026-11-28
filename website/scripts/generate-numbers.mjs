#!/usr/bin/env node
/**
 * Build-time numbers block for the marketing site.
 *
 * Reads bench/results.json and bench/external/results.json from the
 * Aethens repository root (the parent of this website/ folder), plus
 * data/bench/meta.json for date and provenance labels.
 *
 * Never invents metrics: every figure is copied from the JSON.
 * Update data/bench/meta.json when you refresh the results so the
 * labels stay accurate.
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const websiteRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = resolve(websiteRoot, "..");
const internalSrc = resolve(repoRoot, "bench/results.json");
const externalSrc = resolve(repoRoot, "bench/external/results.json");
const metaPath = resolve(websiteRoot, "data/bench/meta.json");
const unconfirmedPath = resolve(repoRoot, "bench/external/c004_unconfirmed.json");

if (!existsSync(internalSrc) || !existsSync(externalSrc)) {
  throw new Error(
    `Bench results not found at ${internalSrc} and ${externalSrc}. ` +
      "Build the site from a full Aethens checkout so website/ sits next to bench/.",
  );
}
if (!existsSync(metaPath)) {
  throw new Error(`Missing ${metaPath}`);
}

const internal = JSON.parse(readFileSync(internalSrc, "utf8"));
const external = JSON.parse(readFileSync(externalSrc, "utf8"));
const meta = JSON.parse(readFileSync(metaPath, "utf8"));
const unconfirmed = existsSync(unconfirmedPath)
  ? JSON.parse(readFileSync(unconfirmedPath, "utf8"))
  : null;

const taskCount = Array.isArray(internal.tasks) ? internal.tasks.length : internal.tasks;
const c004 = external.metrics.per_check.C004;
const extPerCheck = external.metrics.per_check;

const out = {
  generated_by: "scripts/generate-numbers.mjs",
  source: {
    internal: "bench/results.json",
    external: "bench/external/results.json",
    meta: "website/data/bench/meta.json",
  },
  internal: {
    label: meta.internal.label,
    note: meta.internal.note,
    schema: internal.schema,
    tool_version: internal.tool_version,
    seed: internal.seed,
    budget: internal.budget,
    tasks: taskCount,
    controls: internal.controls,
    defective: internal.defective,
    precision: internal.metrics.precision,
    recall: internal.metrics.recall,
    planted: internal.metrics.planted,
    found: internal.metrics.found,
    false_positives: internal.metrics.false_positives,
    unexpected_findings: internal.metrics.unexpected_findings,
    info_on_controls: internal.metrics.info_on_controls,
    known_misses: internal.metrics.known_misses,
    per_check: internal.metrics.per_check,
    per_class: internal.metrics.per_class,
    reward_hack: {
      labelled: internal.reward_hack.labelled,
      found: internal.reward_hack.found,
      false_positives: internal.reward_hack.false_positives,
      recall: internal.reward_hack.recall,
      precision: internal.reward_hack.precision,
      per_category: internal.reward_hack.per_category,
    },
  },
  external: {
    label: meta.external.label,
    note: meta.external.note,
    schema: external.schema,
    tool_version: external.tool_version,
    subset: external.subset,
    seed: external.seed,
    budget: external.budget,
    exhaustive: external.exhaustive,
    checks: external.checks,
    datasets: external.datasets,
    tasks: Array.isArray(external.tasks) ? external.tasks.length : external.tasks,
    tasks_without_oracle: external.metrics.tasks_without_oracle.length,
    c004: {
      precision: c004.precision,
      recall: c004.recall,
      survivors_judged_by_oracle: c004.survivors_judged_by_oracle,
      confirmed: c004.confirmed,
      unconfirmed: c004.unconfirmed,
      weak_tasks: c004.recall_detail.weak_tasks,
      weak_tasks_found_at_budget: c004.recall_detail.weak_tasks_found_at_budget,
      precision_without_filter: c004.precision_without_filter ?? null,
      recall_without_filter: c004.recall_without_filter ?? null,
      filtered_as_equivalent: c004.filtered_as_equivalent ?? null,
      filtered_rejected_by_oracle: c004.filtered_rejected_by_oracle ?? null,
      unconfirmed_breakdown: unconfirmed
        ? {
            equivalent: unconfirmed.unconfirmed.filter((r) => r.bucket === "a").length,
            out_of_precondition: unconfirmed.unconfirmed.filter((r) => r.bucket === "b").length,
            real_gap: unconfirmed.unconfirmed.filter((r) => r.bucket === "c").length,
            rows: unconfirmed.unconfirmed.map((r) => ({
              task: r.task,
              change: r.change,
              bucket: r.bucket,
              reason: r.reason,
            })),
            filter_hidden: unconfirmed.filter_hidden.length,
          }
        : null,
    },
    presumed_clean: {
      C001: {
        loud_findings: extPerCheck.C001.loud_findings,
        tasks_with_loud_findings: extPerCheck.C001.tasks_with_loud_findings,
      },
      C002: {
        loud_findings: extPerCheck.C002.loud_findings,
        tasks_with_loud_findings: extPerCheck.C002.tasks_with_loud_findings,
        loud_finding_list: extPerCheck.C002.loud_finding_list,
      },
      C005: {
        loud_findings: extPerCheck.C005.loud_findings,
        tasks_with_loud_findings: extPerCheck.C005.tasks_with_loud_findings,
      },
    },
  },
  competitive_survey: meta.competitive_survey,
  report_snippet: meta.report_snippet,
};

const dest = resolve(websiteRoot, "src/data/numbers.json");
mkdirSync(dirname(dest), { recursive: true });
writeFileSync(dest, JSON.stringify(out, null, 2) + "\n");
console.log(`Wrote ${dest} from ${internalSrc} and ${externalSrc}`);
