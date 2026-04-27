/**
 * Mercury Retrograde — navigation graph.
 *
 * Single source of truth for semantically related views across the app.
 * Replaces the flat 14-tile sidebar pattern: instead of "always show 14
 * links", each entity declares its own related views relative to itself.
 *
 * The OmniBar handles top-level navigation. This module handles the
 * "what else can I do with THIS thing I'm looking at" navigation,
 * surfaced via <RelatedViews> in the right rail of entity pages.
 *
 * Conventions:
 *   - `key` is stable, used by /api/navigation/counts to attach badge counts
 *   - `href` always starts with "/"
 *   - `requiredRole` filters at the UI layer; the backend must still enforce
 *
 * To extend: add a new entity type to EntityType, add its block here, and
 * optionally surface counts in backend/api/routers/navigation.py.
 */

export type EntityType =
  | "model"
  | "benchmark"
  | "campaign"
  | "tenant"
  | "report"
  | "incident"
  | "exploit"
  | "trajectory"
  | "scenario"
  | "leaderboard_domain"
  | "judge"
  | "plugin";

export type Role = "viewer" | "evaluator" | "admin";

export interface NavLink {
  /** Stable key used by counts endpoint. Do not rename after deployment. */
  key: string;
  label: string;
  href: string;
  /** Role required to see this link. Default: visible to everyone. */
  requiredRole?: Role;
  /** When true, the link uses the `elevated` visual treatment (vermillion). */
  elevated?: boolean;
}

type EntityId = string | number;
const enc = (v: EntityId): string => encodeURIComponent(String(v));

// ═══════════════════════════════════════════════════════════════════════════
//  NAVIGATION_GRAPH
//  One factory per entity type. Each takes the entity id and returns the
//  list of related views.
// ═══════════════════════════════════════════════════════════════════════════

export const NAVIGATION_GRAPH: Record<EntityType, (id: EntityId) => NavLink[]> = {
  // ─── Model ──────────────────────────────────────────────────────────────
  model: (id) => [
    { key: "runs",          label: "Run history",            href: `/models/${enc(id)}/runs` },
    { key: "capability",    label: "Capability profile",      href: `/models/${enc(id)}/capability` },
    { key: "genome",        label: "Genomia fingerprint",     href: `/genome?model=${enc(id)}` },
    { key: "leaderboard",   label: "Leaderboard placement",   href: `/leaderboard?model=${enc(id)}` },
    { key: "compare",       label: "Comparable models",       href: `/models/${enc(id)}/compare` },
    { key: "incidents",     label: "Known incidents",         href: `/incidents?model=${enc(id)}` },
    { key: "redbox",        label: "Red Room against this",   href: `/redbox?target=${enc(id)}`, requiredRole: "evaluator", elevated: true },
    { key: "trajectories",  label: "Agent trajectories",      href: `/agents?model=${enc(id)}` },
  ],

  // ─── Benchmark ──────────────────────────────────────────────────────────
  benchmark: (id) => [
    { key: "leaderboard",   label: "Leaderboard for this bench", href: `/leaderboard?benchmark=${enc(id)}` },
    { key: "contamination", label: "Contamination check",         href: `/benchmarks/${enc(id)}/contamination` },
    { key: "capability",    label: "Capability mapping",          href: `/benchmarks/${enc(id)}/capability` },
    { key: "forks",         label: "Variants & forks",            href: `/benchmarks/${enc(id)}/forks` },
    { key: "citations",     label: "Scientific citations",        href: `/benchmarks/${enc(id)}/citations` },
    { key: "failures",      label: "Common failure modes",        href: `/benchmarks/${enc(id)}/failures` },
    { key: "coverage",      label: "Models that ran it",          href: `/benchmarks/${enc(id)}/coverage` },
    { key: "new_campaign",  label: "Launch campaign with this",   href: `/evaluate?benchmark=${enc(id)}` },
  ],

  // ─── Campaign ───────────────────────────────────────────────────────────
  campaign: (id) => [
    { key: "dashboard",     label: "Dashboard",                href: `/campaigns/${enc(id)}` },
    { key: "failures",      label: "Failed items",             href: `/campaigns/${enc(id)}/failures` },
    { key: "genome",        label: "Genome for this run",      href: `/genome/campaigns/${enc(id)}` },
    { key: "judge",         label: "Judge scores",             href: `/judge?campaign=${enc(id)}` },
    { key: "contamination", label: "Contamination analysis",   href: `/campaigns/${enc(id)}/contamination` },
    { key: "confidence",    label: "Confidence grading",       href: `/campaigns/${enc(id)}/confidence` },
    { key: "manifest",      label: "Experiment manifest",      href: `/campaigns/${enc(id)}/manifest` },
    { key: "export",        label: "Export bundle (replay)",   href: `/campaigns/${enc(id)}/bundle/export` },
    { key: "comments",      label: "Comments & review",        href: `/campaigns/${enc(id)}/reviews` },
    { key: "clone",         label: "Clone into Studio",        href: `/evaluate?clone=${enc(id)}` },
    { key: "rerun",         label: "Re-run identically",       href: `/campaigns/${enc(id)}/rerun`, requiredRole: "evaluator" },
  ],

  // ─── Tenant ─────────────────────────────────────────────────────────────
  tenant: (id) => [
    { key: "members",   label: "Members & roles", href: `/tenants/${enc(id)}/members`,  requiredRole: "admin" },
    { key: "campaigns", label: "Campaigns owned", href: `/tenants/${enc(id)}/campaigns` },
    { key: "shared",    label: "Shared with tenant", href: `/tenants/${enc(id)}/shared` },
    { key: "api_key",   label: "API key management", href: `/tenants/${enc(id)}/api-key`, requiredRole: "admin", elevated: true },
    { key: "usage",     label: "Usage & billing",  href: `/tenants/${enc(id)}/usage`,  requiredRole: "admin" },
    { key: "audit_log", label: "Audit log",         href: `/tenants/${enc(id)}/audit`,  requiredRole: "admin" },
  ],

  // ─── Report ─────────────────────────────────────────────────────────────
  report: (id) => [
    { key: "campaign",   label: "Source campaign",    href: `/reports/${enc(id)}/campaign` },
    { key: "export_pdf", label: "Export as PDF",      href: `/reports/${enc(id)}/pdf` },
    { key: "export_tex", label: "Export as LaTeX",    href: `/reports/${enc(id)}/tex` },
    { key: "citations",  label: "Cite this report",   href: `/reports/${enc(id)}/bibtex` },
    { key: "regenerate", label: "Regenerate",         href: `/reports/${enc(id)}/regenerate`, requiredRole: "evaluator" },
  ],

  // ─── Incident (AIID-style) ──────────────────────────────────────────────
  incident: (id) => [
    { key: "replays",   label: "Replays on current models",  href: `/incidents/${enc(id)}/replays` },
    { key: "similar",   label: "Similar incidents",          href: `/incidents/${enc(id)}/similar` },
    { key: "patterns",  label: "Failure pattern family",     href: `/failure-patterns?incident=${enc(id)}` },
    { key: "scenarios", label: "Scenarios derived",          href: `/scenarios?incident=${enc(id)}` },
    { key: "redbox",    label: "Attack this incident",       href: `/redbox?aiid=${enc(id)}`, requiredRole: "evaluator", elevated: true },
  ],

  // ─── Exploit (Red Room finding) ─────────────────────────────────────────
  exploit: (id) => [
    { key: "trace",       label: "Full attack trace",         href: `/redbox/exploits/${enc(id)}` },
    { key: "replay",      label: "Replay exploit",            href: `/redbox/exploits/${enc(id)}/replay`,  requiredRole: "evaluator", elevated: true },
    { key: "variants",    label: "Generate variants",         href: `/redbox/exploits/${enc(id)}/variants`, requiredRole: "evaluator" },
    { key: "similar",     label: "Similar exploits",          href: `/redbox/exploits/${enc(id)}/similar` },
    { key: "submit_aiid", label: "Submit as AIID candidate",  href: `/incidents/new?from=${enc(id)}`,  requiredRole: "evaluator" },
  ],

  // ─── Trajectory (agent run) ─────────────────────────────────────────────
  trajectory: (id) => [
    { key: "replay",   label: "Replay step by step",      href: `/agents/${enc(id)}/replay` },
    { key: "judge",    label: "Judge scores by axis",     href: `/agents/${enc(id)}/judge` },
    { key: "scenario", label: "Originating scenario",     href: `/agents/${enc(id)}/scenario` },
    { key: "compare",  label: "Compare with another run", href: `/agents/${enc(id)}/compare` },
    { key: "export",   label: "Export signed trace",      href: `/agents/${enc(id)}/export` },
  ],

  // ─── Scenario (agentic task template) ───────────────────────────────────
  scenario: (id) => [
    { key: "runs",     label: "Runs on this scenario",  href: `/scenarios/${enc(id)}/runs` },
    { key: "launch",   label: "Launch run",             href: `/scenarios/${enc(id)}/launch`, requiredRole: "evaluator" },
    { key: "variants", label: "Scenario variants",      href: `/scenarios/${enc(id)}/variants` },
    { key: "domain",   label: "Capability domain",      href: `/capabilities?scenario=${enc(id)}` },
    { key: "edit",     label: "Edit scenario",          href: `/scenarios/${enc(id)}/edit`, requiredRole: "evaluator" },
  ],

  // ─── Leaderboard domain ─────────────────────────────────────────────────
  leaderboard_domain: (id) => [
    { key: "rankings",   label: "Full rankings",             href: `/leaderboard/${enc(id)}` },
    { key: "report",     label: "Generated report",          href: `/leaderboard/${enc(id)}/report` },
    { key: "benchmarks", label: "Benchmarks in this domain", href: `/benchmarks?domain=${enc(id)}` },
    { key: "gaps",       label: "Coverage gaps",             href: `/capabilities?domain=${enc(id)}` },
    { key: "new_eval",   label: "Evaluate on this domain",   href: `/evaluate?domain=${enc(id)}` },
  ],

  // ─── Judge (LLM-as-judge configuration) ─────────────────────────────────
  judge: (id) => [
    { key: "calibration",     label: "Calibration metrics",     href: `/judge/${enc(id)}/calibration` },
    { key: "bias",            label: "Bias detection report",   href: `/judge/${enc(id)}/bias` },
    { key: "scores",          label: "Scores by campaign",      href: `/judge/${enc(id)}/scores` },
    { key: "human_agreement", label: "Human-agreement trace",   href: `/judge/${enc(id)}/human` },
    { key: "recalibrate",     label: "Recalibrate",             href: `/judge/${enc(id)}/recalibrate`, requiredRole: "admin" },
  ],

  // ─── Plugin (SDK plugin) ────────────────────────────────────────────────
  plugin: (id) => [
    { key: "manifest",   label: "Plugin manifest",          href: `/plugins/${enc(id)}/manifest` },
    { key: "validation", label: "Validation report",        href: `/plugins/${enc(id)}/validation` },
    { key: "runs",       label: "Runs using this plugin",   href: `/plugins/${enc(id)}/runs` },
    { key: "source",     label: "Source repository",        href: `/plugins/${enc(id)}/source` },
    { key: "disable",    label: "Disable plugin",           href: `/plugins/${enc(id)}/disable`, requiredRole: "admin", elevated: true },
  ],
};

// ═══════════════════════════════════════════════════════════════════════════
//  Helpers
// ═══════════════════════════════════════════════════════════════════════════

const ROLE_ORDER: Record<Role, number> = { viewer: 0, evaluator: 1, admin: 2 };

/**
 * Filter NavLinks by user role. A user can see links whose requiredRole
 * is at or below their effective role.
 */
export function filterByRole(links: NavLink[], userRole: Role): NavLink[] {
  return links.filter(
    (link) =>
      !link.requiredRole || ROLE_ORDER[userRole] >= ROLE_ORDER[link.requiredRole]
  );
}

/**
 * Convenience: get the related view list for an entity, role-filtered.
 * Returns an empty list if the entity type is unknown.
 */
export function getRelatedViews(
  entityType: EntityType,
  entityId: EntityId,
  userRole: Role = "viewer"
): NavLink[] {
  const factory = NAVIGATION_GRAPH[entityType];
  if (!factory) return [];
  return filterByRole(factory(entityId), userRole);
}
