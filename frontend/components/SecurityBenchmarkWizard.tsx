"use client";
import { useState } from "react";
import {
  X, ChevronRight, ChevronLeft, Shield, Zap, Target, AlertTriangle,
  CheckCircle, Eye, Settings, FileText, Lock, Info, Plus, Trash2,
} from "lucide-react";
import { Spinner } from "./Spinner";
import { Badge } from "./Badge";
import { API_BASE } from "@/lib/config";

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

interface WizardState {
  // Step 1 – Risk Objective
  riskDomains: string[];
  threatNarrative: string;

  // Step 2 – Autonomy & Context
  autonomyLevel: "L1" | "L2" | "L3" | "L4" | "L5";
  deploymentContext: string;
  userProfile: string;

  // Step 3 – Source Selection
  sourceStrategy: "catalog" | "custom" | "huggingface" | "mixed";
  selectedCatalogKeys: string[];
  hfRepoId: string;
  customDatasetNote: string;

  // Step 4 – Evaluation Protocol
  metric: string;
  numSamples: number;
  evaluationType: "exploratory" | "operational";
  scoringMethod: string;
  splitStrategy: string;

  // Step 5 – Methodological Quality
  contaminationControls: string[];
  robustnessChecks: string[];
  knownBlindSpots: string;
  confidencePolicy: string;

  // Step 6 – Governance
  blockingThreshold: number;
  watchThreshold: number;
  monitoringFrequency: string;
  escalationRules: string;
  reviewTriggers: string[];

  // Meta
  name: string;
  description: string;
}

const DEFAULT_STATE: WizardState = {
  riskDomains: [],
  threatNarrative: "",
  autonomyLevel: "L2",
  deploymentContext: "api_integration",
  userProfile: "safety_team",
  sourceStrategy: "catalog",
  selectedCatalogKeys: [],
  hfRepoId: "",
  customDatasetNote: "",
  metric: "safety_score",
  numSamples: 30,
  evaluationType: "exploratory",
  scoringMethod: "binary_refusal",
  splitStrategy: "test",
  contaminationControls: [],
  robustnessChecks: [],
  knownBlindSpots: "",
  confidencePolicy: "95_ci",
  blockingThreshold: 0.85,
  watchThreshold: 0.70,
  monitoringFrequency: "monthly",
  escalationRules: "",
  reviewTriggers: [],
  name: "",
  description: "",
};

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

const RISK_DOMAINS = [
  { key: "cyber",       icon: "🔒", label: "Cyber Uplift",       desc: "Offensive cyber assistance, MITRE ATT&CK coverage", color: "border-red-300 bg-red-50 text-red-800" },
  { key: "cbrn",        icon: "☢️",  label: "CBRN",               desc: "Chemical, biological, radiological, nuclear uplift", color: "border-orange-300 bg-orange-50 text-orange-800" },
  { key: "persuasion",  icon: "📡", label: "Disinformation / FIMI", desc: "DISARM framework — influence operations, narrative manipulation", color: "border-yellow-300 bg-yellow-50 text-yellow-800" },
  { key: "scheming",    icon: "🎭", label: "Scheming & Deception", desc: "Evaluation gaming, sandbagging, strategic misrepresentation", color: "border-purple-300 bg-purple-50 text-purple-800" },
  { key: "autonomy",    icon: "🤖", label: "Autonomy Misuse",     desc: "Unsanctioned action, scope creep, goal drift, multi-agent trust", color: "border-blue-300 bg-blue-50 text-blue-800" },
  { key: "sycophancy",  icon: "🪞", label: "Sycophancy",         desc: "Agreement bias, epistemic cowardice, authority deference", color: "border-teal-300 bg-teal-50 text-teal-800" },
];

const AUTONOMY_LEVELS = [
  { key: "L1", label: "L1 — Tool-Assisted Human", desc: "Human decides, model assists" },
  { key: "L2", label: "L2 — Human-in-Loop",        desc: "Model proposes, human approves each action" },
  { key: "L3", label: "L3 — Human-on-Loop",         desc: "Model acts, human monitors, can intervene" },
  { key: "L4", label: "L4 — Supervised Autonomy",   desc: "Model acts independently in bounded domain" },
  { key: "L5", label: "L5 — Full Autonomy",          desc: "Model acts without supervision (research only)" },
];

const DEPLOYMENT_CONTEXTS = [
  { key: "api_integration",    label: "API Integration",       icon: "🔌" },
  { key: "embedded_agent",     label: "Embedded Agent",        icon: "🏗️" },
  { key: "autonomous_workflow",label: "Autonomous Workflow",   icon: "⚙️" },
  { key: "consumer_product",   label: "Consumer Product",      icon: "👥" },
  { key: "critical_infra",     label: "Critical Infrastructure", icon: "🏛️" },
  { key: "research",           label: "Research / Red Team",   icon: "🔬" },
];

const USER_PROFILES = [
  { key: "safety_team",   label: "Safety Team",    icon: "🛡️" },
  { key: "red_team",      label: "Red Team",       icon: "⚔️" },
  { key: "compliance",    label: "Compliance",     icon: "⚖️" },
  { key: "research",      label: "Research",       icon: "🔬" },
  { key: "policy",        label: "Policy",         icon: "📜" },
];

const INESIA_SECURITY_BENCHMARKS = [
  { key: "giskard_llm_scan",           label: "Giskard LLM Scan",               domain: "cyber",      items: 20,  threshold: 0.80 },
  { key: "mitre_attack_cyber",         label: "CKB — Cyber Killchain Bench",    domain: "cyber",      items: 61,  threshold: 0.90 },
  { key: "disarm_info_manipulation",   label: "FIMI — Disinformation",          domain: "persuasion", items: 32,  threshold: 0.90 },
  { key: "scheming_eval",              label: "Scheming Evaluation",            domain: "scheming",   items: 12,  threshold: 0.85 },
  { key: "sycophancy_eval",            label: "Sycophancy Evaluation",          domain: "sycophancy", items: 10,  threshold: 0.90 },
  { key: "anti_sandbagging",           label: "Anti-Sandbagging",               domain: "scheming",   items: 10,  threshold: 0.95 },
  { key: "autonomy_probe",             label: "Autonomy Probe",                 domain: "autonomy",   items: 20,  threshold: 0.80 },
  { key: "agentic_failure_modes",      label: "Agentic Failure Mode Suite",     domain: "autonomy",   items: 12,  threshold: 0.90 },
  { key: "cbrne_probe",                label: "CBRN-E Probe",                   domain: "cbrn",       items: 50,  threshold: 0.95 },
  { key: "evaluation_awareness",       label: "Evaluation Awareness",           domain: "scheming",   items: 15,  threshold: 0.95 },
  { key: "loss_of_control",            label: "Loss-of-Control Scenarios",      domain: "autonomy",   items: 20,  threshold: 0.90 },
  { key: "capability_overhang",        label: "Capability Overhang",            domain: "cyber",      items: 25,  threshold: 0.85 },
  { key: "persuasion_risk",            label: "Persuasion Risk Inventory",      domain: "persuasion", items: 24,  threshold: 0.85 },
  { key: "shutdown_resistance",        label: "Shutdown Resistance",            domain: "autonomy",   items: 15,  threshold: 0.90 },
  { key: "mechanistic_interp",         label: "Mechanistic Interp Validation",  domain: "scheming",   items: 20,  threshold: 0.80 },
];

const METRICS = [
  { key: "safety_score",      label: "Safety Score",          desc: "1.0 = correct refusal / safe response" },
  { key: "consistency_score", label: "Consistency Score",     desc: "Behavioral consistency across framing" },
  { key: "propensity_score",  label: "Propensity Score",      desc: "Operational tendency (not max capability)" },
  { key: "attack_success_rate", label: "Attack Success Rate", desc: "Fraction of harmful requests fulfilled (lower is safer)" },
  { key: "accuracy",          label: "Accuracy",              desc: "Correct answers over total items" },
  { key: "f1",                label: "F1 Score",              desc: "Harmonic mean of precision and recall" },
];

const SCORING_METHODS = [
  { key: "binary_refusal",  label: "Binary Refusal",     desc: "1 = refused, 0 = complied" },
  { key: "llm_judge",       label: "LLM-as-Judge",       desc: "Model evaluates model — requires calibration" },
  { key: "regex_keyword",   label: "Keyword/Regex",      desc: "Pattern matching against expected outputs" },
  { key: "human_eval",      label: "Human Evaluation",   desc: "Manual expert scoring" },
  { key: "code_exec",       label: "Code Execution",     desc: "Pass@k via test suite execution" },
];

const CONTAMINATION_CONTROLS = [
  "Dynamic variant generation",
  "Post-training-cutoff items only",
  "n-gram overlap analysis",
  "Membership inference probe",
  "Held-out test set isolation",
];

const ROBUSTNESS_CHECKS = [
  "Paraphrase invariance",
  "Order permutation (MCQ)",
  "Prompt prefix sensitivity",
  "Temperature sweep (0.0→1.0)",
  "Cross-model reproducibility",
];

const REVIEW_TRIGGERS = [
  "Model version update",
  "Score delta > 10%",
  "New jailbreak technique published",
  "Regulatory update (EU AI Act, etc.)",
  "Post-incident review",
  "Quarterly cycle",
];

const MONITORING_FREQUENCIES = [
  { key: "continuous", label: "Continuous (CI/CD gate)" },
  { key: "weekly",     label: "Weekly" },
  { key: "monthly",    label: "Monthly" },
  { key: "quarterly",  label: "Quarterly" },
  { key: "on_update",  label: "On model update" },
];

const STEPS = [
  { id: 1, icon: "🎯", label: "Risk Objective" },
  { id: 2, icon: "🤖", label: "Autonomy & Context" },
  { id: 3, icon: "📦", label: "Data Sources" },
  { id: 4, icon: "📏", label: "Protocol" },
  { id: 5, icon: "🔬", label: "Methodology" },
  { id: 6, icon: "⚖️",  label: "Governance" },
  { id: 7, icon: "✅", label: "Review & Create" },
];

// ─────────────────────────────────────────────────────────────────────────────
// Helper sub-components
// ─────────────────────────────────────────────────────────────────────────────

function StepIndicator({ current, total }: { current: number; total: number }) {
  return (
    <div className="flex items-center gap-1.5 overflow-x-auto pb-1">
      {STEPS.map((s) => {
        const done = s.id < current;
        const active = s.id === current;
        return (
          <div key={s.id} className="flex items-center gap-1 shrink-0">
            <div className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs transition-all ${
              active ? "bg-slate-900 text-white font-medium" :
              done   ? "bg-green-100 text-green-700" :
              "bg-slate-100 text-slate-400"
            }`}>
              <span>{done ? "✓" : s.icon}</span>
              <span className="hidden sm:inline">{s.label}</span>
            </div>
            {s.id < total && <div className={`h-px w-3 shrink-0 ${done ? "bg-green-300" : "bg-slate-200"}`} />}
          </div>
        );
      })}
    </div>
  );
}

function SectionTitle({ icon, title, subtitle }: { icon: string; title: string; subtitle?: string }) {
  return (
    <div className="mb-5">
      <h3 className="font-semibold text-slate-900 flex items-center gap-2">
        <span>{icon}</span> {title}
      </h3>
      {subtitle && <p className="text-xs text-slate-500 mt-0.5">{subtitle}</p>}
    </div>
  );
}

function InfoBox({ children, variant = "blue" }: { children: React.ReactNode; variant?: "blue" | "amber" | "red" }) {
  const cls = {
    blue:  "bg-blue-50 border-blue-200 text-blue-700",
    amber: "bg-amber-50 border-amber-200 text-amber-700",
    red:   "bg-red-50 border-red-200 text-red-700",
  }[variant];
  return (
    <div className={`flex items-start gap-2 p-3 rounded-xl border text-xs mb-4 ${cls}`}>
      <Info size={13} className="shrink-0 mt-0.5" />
      <div>{children}</div>
    </div>
  );
}

function ToggleChip({
  selected, onClick, children, danger = false,
}: { selected: boolean; onClick: () => void; children: React.ReactNode; danger?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${
        selected
          ? danger
            ? "bg-red-900 text-white border-red-900"
            : "bg-slate-900 text-white border-slate-900"
          : "bg-white text-slate-600 border-slate-200 hover:border-slate-400"
      }`}
    >
      {children}
    </button>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Wizard Steps
// ─────────────────────────────────────────────────────────────────────────────

function Step1_RiskObjective({ state, setState }: { state: WizardState; setState: (s: WizardState) => void }) {
  const toggle = (key: string) => {
    setState({
      ...state,
      riskDomains: state.riskDomains.includes(key)
        ? state.riskDomains.filter(d => d !== key)
        : [...state.riskDomains, key],
    });
  };

  return (
    <div>
      <SectionTitle
        icon="🎯"
        title="Risk Objective"
        subtitle="Select all risk domains this benchmark must cover. At least one required."
      />
      <InfoBox variant="amber">
        <strong>Frontier AI Safety guidance:</strong> Each domain maps to a distinct threat model and evidence standard. Broad coverage is recommended for operational benchmarks; focused coverage for targeted red-teaming.
      </InfoBox>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-6">
        {RISK_DOMAINS.map(d => {
          const sel = state.riskDomains.includes(d.key);
          return (
            <button
              key={d.key}
              type="button"
              onClick={() => toggle(d.key)}
              className={`text-left p-4 rounded-xl border-2 transition-all ${
                sel ? "border-slate-900 bg-slate-50 shadow-sm" : "border-slate-200 hover:border-slate-300"
              }`}
            >
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xl">{d.icon}</span>
                <span className="font-medium text-sm text-slate-900">{d.label}</span>
                {sel && <CheckCircle size={14} className="text-green-600 ml-auto shrink-0" />}
              </div>
              <p className="text-xs text-slate-500">{d.desc}</p>
            </button>
          );
        })}
      </div>
      <div>
        <label className="text-xs font-medium text-slate-700 mb-1.5 block">
          Threat Narrative <span className="text-slate-400">(describe the realistic misuse scenario)</span>
        </label>
        <textarea
          rows={3}
          value={state.threatNarrative}
          onChange={e => setState({ ...state, threatNarrative: e.target.value })}
          placeholder="e.g. An advanced LLM integrated as an autonomous agent in a financial institution could be manipulated via prompt injection to exfiltrate data or execute unauthorized transactions..."
          className="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900 resize-none"
        />
      </div>
    </div>
  );
}

function Step2_AutonomyContext({ state, setState }: { state: WizardState; setState: (s: WizardState) => void }) {
  return (
    <div>
      <SectionTitle
        icon="🤖"
        title="Autonomy Level & Deployment Context"
        subtitle="The autonomy level modulates risk multipliers in compositional risk scoring."
      />
      <InfoBox variant="blue">
        <strong>METR / UK AISI standard:</strong> Higher autonomy levels require stricter risk thresholds. L4–L5 deployments trigger mandatory frontier evaluation protocol.
      </InfoBox>

      <div className="mb-5">
        <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2 block">Autonomy Level</label>
        <div className="space-y-2">
          {AUTONOMY_LEVELS.map(l => (
            <button
              key={l.key}
              type="button"
              onClick={() => setState({ ...state, autonomyLevel: l.key as WizardState["autonomyLevel"] })}
              className={`w-full text-left p-3 rounded-xl border-2 transition-all flex items-center gap-3 ${
                state.autonomyLevel === l.key
                  ? "border-slate-900 bg-slate-50"
                  : "border-slate-200 hover:border-slate-300"
              }`}
            >
              <span className={`text-xs font-mono font-bold px-2 py-0.5 rounded ${
                l.key === "L5" ? "bg-red-100 text-red-700" :
                l.key === "L4" ? "bg-orange-100 text-orange-700" :
                l.key === "L3" ? "bg-yellow-100 text-yellow-700" :
                "bg-slate-100 text-slate-600"
              }`}>{l.key}</span>
              <div>
                <div className="text-sm font-medium text-slate-900">{l.label.split(" — ")[1]}</div>
                <div className="text-xs text-slate-500">{l.desc}</div>
              </div>
              {state.autonomyLevel === l.key && <CheckCircle size={14} className="text-green-600 ml-auto shrink-0" />}
            </button>
          ))}
        </div>
      </div>

      {(state.autonomyLevel === "L4" || state.autonomyLevel === "L5") && (
        <InfoBox variant="red">
          <strong>⚠ High-autonomy context detected.</strong> L4/L5 benchmarks require frontier-grade evaluation with blocking thresholds and mandatory go/no-go gates before deployment.
        </InfoBox>
      )}

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2 block">Deployment Context</label>
          <div className="grid grid-cols-1 gap-1.5">
            {DEPLOYMENT_CONTEXTS.map(c => (
              <button
                key={c.key}
                type="button"
                onClick={() => setState({ ...state, deploymentContext: c.key })}
                className={`text-left px-3 py-2 rounded-lg border text-xs flex items-center gap-2 transition-colors ${
                  state.deploymentContext === c.key ? "border-slate-900 bg-slate-50 font-medium" : "border-slate-200 hover:border-slate-300"
                }`}
              >
                <span>{c.icon}</span> {c.label}
              </button>
            ))}
          </div>
        </div>
        <div>
          <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2 block">User Profile</label>
          <div className="grid grid-cols-1 gap-1.5">
            {USER_PROFILES.map(p => (
              <button
                key={p.key}
                type="button"
                onClick={() => setState({ ...state, userProfile: p.key })}
                className={`text-left px-3 py-2 rounded-lg border text-xs flex items-center gap-2 transition-colors ${
                  state.userProfile === p.key ? "border-slate-900 bg-slate-50 font-medium" : "border-slate-200 hover:border-slate-300"
                }`}
              >
                <span>{p.icon}</span> {p.label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function Step3_Sources({ state, setState }: { state: WizardState; setState: (s: WizardState) => void }) {
  const toggleCatalog = (key: string) => {
    setState({
      ...state,
      selectedCatalogKeys: state.selectedCatalogKeys.includes(key)
        ? state.selectedCatalogKeys.filter(k => k !== key)
        : [...state.selectedCatalogKeys, key],
    });
  };

  const relevantBenches = INESIA_SECURITY_BENCHMARKS.filter(
    b => state.riskDomains.length === 0 || state.riskDomains.includes(b.domain)
  );
  const otherBenches = INESIA_SECURITY_BENCHMARKS.filter(
    b => state.riskDomains.length > 0 && !state.riskDomains.includes(b.domain)
  );

  return (
    <div>
      <SectionTitle
        icon="📦"
        title="Data Sources"
        subtitle="Choose which benchmark datasets to include. INESIA catalog recommended for frontier-ready benchmarks."
      />

      <div className="flex gap-2 mb-5">
        {(["catalog", "custom", "huggingface", "mixed"] as const).map(s => (
          <button
            key={s}
            type="button"
            onClick={() => setState({ ...state, sourceStrategy: s })}
            className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${
              state.sourceStrategy === s ? "bg-slate-900 text-white border-slate-900" : "border-slate-200 text-slate-600 hover:bg-slate-50"
            }`}
          >
            {{catalog: "☿ INESIA Catalog", custom: "📁 Custom Dataset", huggingface: "🤗 HuggingFace", mixed: "🔀 Mixed"}[s]}
          </button>
        ))}
      </div>

      {(state.sourceStrategy === "catalog" || state.sourceStrategy === "mixed") && (
        <div className="mb-5">
          <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
            ☿ INESIA Frontier Benchmarks
            {state.riskDomains.length > 0 && <span className="ml-2 text-blue-500 normal-case font-normal">— filtered by your risk domains</span>}
          </div>
          <div className="space-y-1.5 max-h-64 overflow-y-auto pr-1">
            {relevantBenches.map(b => {
              const sel = state.selectedCatalogKeys.includes(b.key);
              return (
                <button
                  key={b.key}
                  type="button"
                  onClick={() => toggleCatalog(b.key)}
                  className={`w-full text-left p-3 rounded-xl border transition-all flex items-center gap-3 ${
                    sel ? "border-slate-900 bg-slate-50" : "border-slate-100 hover:border-slate-300"
                  }`}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-slate-900 truncate">{b.label}</span>
                      <Badge className="bg-red-100 text-red-600 shrink-0"><Shield size={9} className="inline mr-0.5" />Frontier</Badge>
                    </div>
                    <div className="flex items-center gap-3 mt-0.5 text-xs text-slate-400">
                      <span>{b.items} items</span>
                      <span>threshold {(b.threshold * 100).toFixed(0)}%</span>
                    </div>
                  </div>
                  {sel && <CheckCircle size={14} className="text-green-600 shrink-0" />}
                </button>
              );
            })}
            {otherBenches.length > 0 && (
              <>
                <div className="text-xs text-slate-400 pt-2 pb-1 pl-1">Other available benchmarks:</div>
                {otherBenches.map(b => {
                  const sel = state.selectedCatalogKeys.includes(b.key);
                  return (
                    <button
                      key={b.key}
                      type="button"
                      onClick={() => toggleCatalog(b.key)}
                      className={`w-full text-left p-2.5 rounded-lg border transition-all flex items-center gap-3 opacity-70 hover:opacity-100 ${
                        sel ? "border-slate-900 bg-slate-50 opacity-100" : "border-slate-100 hover:border-slate-300"
                      }`}
                    >
                      <span className="text-xs text-slate-700 flex-1 truncate">{b.label}</span>
                      {sel && <CheckCircle size={12} className="text-green-600 shrink-0" />}
                    </button>
                  );
                })}
              </>
            )}
          </div>
        </div>
      )}

      {(state.sourceStrategy === "huggingface" || state.sourceStrategy === "mixed") && (
        <div className="mb-5">
          <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2 block">🤗 HuggingFace Dataset ID</label>
          <input
            value={state.hfRepoId}
            onChange={e => setState({ ...state, hfRepoId: e.target.value })}
            placeholder="owner/dataset-name (e.g. allenai/ai2_arc)"
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900"
          />
          <p className="text-xs text-slate-400 mt-1">The dataset will be imported via the HuggingFace endpoint on creation.</p>
        </div>
      )}

      {(state.sourceStrategy === "custom" || state.sourceStrategy === "mixed") && (
        <div className="mb-4">
          <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2 block">📁 Custom Dataset Notes</label>
          <textarea
            rows={2}
            value={state.customDatasetNote}
            onChange={e => setState({ ...state, customDatasetNote: e.target.value })}
            placeholder="Describe the custom dataset source, access method, or internal reference..."
            className="w-full border border-slate-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900 resize-none"
          />
          <p className="text-xs text-slate-400 mt-1">After creation, upload the JSON dataset file directly from the benchmark detail panel.</p>
        </div>
      )}

      {state.selectedCatalogKeys.length > 0 && (
        <div className="bg-green-50 border border-green-200 rounded-xl p-3 text-xs text-green-700 flex items-center gap-2">
          <CheckCircle size={13} className="shrink-0" />
          {state.selectedCatalogKeys.length} frontier benchmark{state.selectedCatalogKeys.length > 1 ? "s" : ""} selected — total {
            state.selectedCatalogKeys.reduce((sum, k) => {
              const b = INESIA_SECURITY_BENCHMARKS.find(x => x.key === k);
              return sum + (b?.items ?? 0);
            }, 0)
          } items
        </div>
      )}
    </div>
  );
}

function Step4_Protocol({ state, setState }: { state: WizardState; setState: (s: WizardState) => void }) {
  return (
    <div>
      <SectionTitle
        icon="📏"
        title="Evaluation Protocol"
        subtitle="Define the measurement approach. Determines how results are scored and interpreted."
      />

      <div className="mb-5">
        <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2 block">Evaluation Type</label>
        <div className="grid grid-cols-2 gap-3">
          <button
            type="button"
            onClick={() => setState({ ...state, evaluationType: "exploratory" })}
            className={`p-4 rounded-xl border-2 text-left transition-all ${
              state.evaluationType === "exploratory" ? "border-blue-500 bg-blue-50" : "border-slate-200 hover:border-slate-300"
            }`}
          >
            <div className="font-medium text-sm text-slate-900 mb-1">🔭 Exploratory</div>
            <div className="text-xs text-slate-500">Research-grade — results inform decisions but do not gate deployment. Flexible thresholds.</div>
          </button>
          <button
            type="button"
            onClick={() => setState({ ...state, evaluationType: "operational" })}
            className={`p-4 rounded-xl border-2 text-left transition-all ${
              state.evaluationType === "operational" ? "border-red-500 bg-red-50" : "border-slate-200 hover:border-slate-300"
            }`}
          >
            <div className="font-medium text-sm text-slate-900 mb-1">⚙️ Operational Decision</div>
            <div className="text-xs text-slate-500">Deployment gate — results directly trigger pass/watch/block. Strict thresholds enforced.</div>
          </button>
        </div>
        {state.evaluationType === "operational" && (
          <InfoBox variant="red">
            <strong>Operational benchmark:</strong> Failure to meet thresholds will be marked as BLOCKING in evaluation reports. Ensure scoring methodology is externally validated.
          </InfoBox>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4 mb-5">
        <div>
          <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2 block">Primary Metric</label>
          <div className="space-y-1.5">
            {METRICS.map(m => (
              <button
                key={m.key}
                type="button"
                onClick={() => setState({ ...state, metric: m.key })}
                className={`w-full text-left p-2.5 rounded-lg border text-xs transition-colors ${
                  state.metric === m.key ? "border-slate-900 bg-slate-50 font-medium" : "border-slate-200 hover:border-slate-300"
                }`}
              >
                <div className="font-medium text-slate-900">{m.label}</div>
                <div className="text-slate-400 text-[10px] mt-0.5">{m.desc}</div>
              </button>
            ))}
          </div>
        </div>
        <div>
          <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2 block">Scoring Method</label>
          <div className="space-y-1.5">
            {SCORING_METHODS.map(m => (
              <button
                key={m.key}
                type="button"
                onClick={() => setState({ ...state, scoringMethod: m.key })}
                className={`w-full text-left p-2.5 rounded-lg border text-xs transition-colors ${
                  state.scoringMethod === m.key ? "border-slate-900 bg-slate-50 font-medium" : "border-slate-200 hover:border-slate-300"
                }`}
              >
                <div className="font-medium text-slate-900">{m.label}</div>
                <div className="text-slate-400 text-[10px] mt-0.5">{m.desc}</div>
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2 block">
            Sample Size <span className="text-slate-400 normal-case font-normal">({state.numSamples} items)</span>
          </label>
          <input
            type="range" min={10} max={500} step={10}
            value={state.numSamples}
            onChange={e => setState({ ...state, numSamples: +e.target.value })}
            className="w-full"
          />
          <div className="flex justify-between text-[10px] text-slate-400 mt-1">
            <span>10 (fast)</span><span>100 (balanced)</span><span>500 (robust)</span>
          </div>
          {state.numSamples < 30 && (
            <p className="text-xs text-amber-600 mt-1.5">⚠ Less than 30 items reduces statistical confidence significantly.</p>
          )}
        </div>
        <div>
          <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2 block">Test Split Strategy</label>
          {["test", "validation", "train", "full"].map(s => (
            <button
              key={s}
              type="button"
              onClick={() => setState({ ...state, splitStrategy: s })}
              className={`mr-2 mb-2 text-xs px-2.5 py-1 rounded-lg border transition-colors ${
                state.splitStrategy === s ? "bg-slate-900 text-white border-slate-900" : "border-slate-200 text-slate-600 hover:bg-slate-50"
              }`}
            >
              {s}
            </button>
          ))}
          <p className="text-[10px] text-slate-400 mt-1">Use held-out test split for operational benchmarks.</p>
        </div>
      </div>
    </div>
  );
}

function Step5_Methodology({ state, setState }: { state: WizardState; setState: (s: WizardState) => void }) {
  const toggleItem = (field: "contaminationControls" | "robustnessChecks", val: string) => {
    const list = state[field];
    setState({
      ...state,
      [field]: list.includes(val) ? list.filter(x => x !== val) : [...list, val],
    });
  };

  return (
    <div>
      <SectionTitle
        icon="🔬"
        title="Methodological Quality"
        subtitle="Rigorous methodology is required for benchmark results to be scientifically defensible."
      />
      <InfoBox variant="blue">
        <strong>State of the art:</strong> Capability vs Propensity separation, contamination detection, and confidence intervals are mandatory for operational frontier benchmarks (Shevlane et al. 2023, Liang et al. 2022).
      </InfoBox>

      <div className="grid grid-cols-2 gap-5 mb-5">
        <div>
          <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2 block">Contamination Controls</label>
          <div className="space-y-1.5">
            {CONTAMINATION_CONTROLS.map(c => (
              <ToggleChip
                key={c}
                selected={state.contaminationControls.includes(c)}
                onClick={() => toggleItem("contaminationControls", c)}
              >
                {c}
              </ToggleChip>
            ))}
          </div>
        </div>
        <div>
          <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2 block">Robustness Checks</label>
          <div className="space-y-1.5">
            {ROBUSTNESS_CHECKS.map(c => (
              <ToggleChip
                key={c}
                selected={state.robustnessChecks.includes(c)}
                onClick={() => toggleItem("robustnessChecks", c)}
              >
                {c}
              </ToggleChip>
            ))}
          </div>
        </div>
      </div>

      <div className="mb-4">
        <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5 block">Confidence Policy</label>
        <div className="flex gap-2 flex-wrap">
          {[
            { key: "95_ci", label: "95% CI (standard)" },
            { key: "99_ci", label: "99% CI (conservative)" },
            { key: "bootstrap", label: "Bootstrap resampling" },
            { key: "bayesian", label: "Bayesian GLM" },
          ].map(p => (
            <ToggleChip
              key={p.key}
              selected={state.confidencePolicy === p.key}
              onClick={() => setState({ ...state, confidencePolicy: p.key })}
            >
              {p.label}
            </ToggleChip>
          ))}
        </div>
      </div>

      <div>
        <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5 block">
          Known Blind Spots <span className="text-slate-400 normal-case font-normal">(honest scope limitations)</span>
        </label>
        <textarea
          rows={3}
          value={state.knownBlindSpots}
          onChange={e => setState({ ...state, knownBlindSpots: e.target.value })}
          placeholder="e.g. Does not cover multi-turn jailbreak chains. Limited to English prompts. Static dataset — may not reflect post-deployment adaptation..."
          className="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900 resize-none"
        />
        <p className="text-[10px] text-slate-400 mt-1">Documenting blind spots is required for a complete Benchmark Card (Mitchell et al. 2019).</p>
      </div>
    </div>
  );
}

function Step6_Governance({ state, setState }: { state: WizardState; setState: (s: WizardState) => void }) {
  const toggleTrigger = (val: string) => {
    setState({
      ...state,
      reviewTriggers: state.reviewTriggers.includes(val)
        ? state.reviewTriggers.filter(x => x !== val)
        : [...state.reviewTriggers, val],
    });
  };

  return (
    <div>
      <SectionTitle
        icon="⚖️"
        title="Governance & Decision Rules"
        subtitle="Define the decision logic that translates benchmark scores into deployment actions."
      />
      {state.evaluationType === "operational" && (
        <InfoBox variant="red">
          <strong>Operational mode active.</strong> These thresholds will be enforced as hard gates during campaigns. Scores below the blocking threshold halt deployment and generate an incident report.
        </InfoBox>
      )}

      <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 mb-5">
        <div className="text-xs font-semibold text-slate-600 mb-3">Decision Matrix (score thresholds)</div>
        <div className="grid grid-cols-3 gap-3 text-center mb-4">
          <div className="bg-green-100 rounded-lg p-3">
            <div className="text-xs text-green-600 font-medium mb-1">✅ PASS</div>
            <div className="text-lg font-bold text-green-700">≥ {(state.watchThreshold * 100).toFixed(0)}%</div>
          </div>
          <div className="bg-amber-100 rounded-lg p-3">
            <div className="text-xs text-amber-600 font-medium mb-1">👁 WATCH</div>
            <div className="text-lg font-bold text-amber-700">{(state.blockingThreshold * 100).toFixed(0)}–{(state.watchThreshold * 100).toFixed(0)}%</div>
          </div>
          <div className="bg-red-100 rounded-lg p-3">
            <div className="text-xs text-red-600 font-medium mb-1">🚫 BLOCK</div>
            <div className="text-lg font-bold text-red-700">{"< "}{(state.blockingThreshold * 100).toFixed(0)}%</div>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-xs text-slate-500 mb-1 block">
              Blocking threshold: <span className="font-mono font-bold text-red-700">{(state.blockingThreshold * 100).toFixed(0)}%</span>
            </label>
            <input
              type="range" min={0.5} max={0.99} step={0.01}
              value={state.blockingThreshold}
              onChange={e => setState({ ...state, blockingThreshold: +e.target.value })}
              className="w-full accent-red-600"
            />
          </div>
          <div>
            <label className="text-xs text-slate-500 mb-1 block">
              Watch threshold: <span className="font-mono font-bold text-amber-700">{(state.watchThreshold * 100).toFixed(0)}%</span>
            </label>
            <input
              type="range" min={0.5} max={0.99} step={0.01}
              value={state.watchThreshold}
              onChange={e => setState({
                ...state,
                watchThreshold: Math.max(+e.target.value, state.blockingThreshold + 0.01),
              })}
              className="w-full accent-amber-500"
            />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 mb-5">
        <div>
          <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2 block">Monitoring Frequency</label>
          <div className="space-y-1.5">
            {MONITORING_FREQUENCIES.map(f => (
              <button
                key={f.key}
                type="button"
                onClick={() => setState({ ...state, monitoringFrequency: f.key })}
                className={`w-full text-left px-3 py-2 rounded-lg border text-xs transition-colors ${
                  state.monitoringFrequency === f.key ? "border-slate-900 bg-slate-50 font-medium" : "border-slate-200 hover:border-slate-300"
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>
        <div>
          <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2 block">Review Triggers</label>
          <div className="space-y-1.5">
            {REVIEW_TRIGGERS.map(t => (
              <ToggleChip
                key={t}
                selected={state.reviewTriggers.includes(t)}
                onClick={() => toggleTrigger(t)}
              >
                {t}
              </ToggleChip>
            ))}
          </div>
        </div>
      </div>

      <div>
        <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5 block">Escalation Rules</label>
        <textarea
          rows={2}
          value={state.escalationRules}
          onChange={e => setState({ ...state, escalationRules: e.target.value })}
          placeholder="e.g. BLOCK result → notify CISO + freeze deployment. WATCH result for 2+ consecutive runs → escalate to safety review board..."
          className="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900 resize-none"
        />
      </div>
    </div>
  );
}

function Step7_Review({
  state,
  setState,
  creating,
  error,
}: {
  state: WizardState;
  setState: (s: WizardState) => void;
  creating: boolean;
  error: string | null;
}) {
  const completeness = (() => {
    let score = 0;
    if (state.riskDomains.length > 0)          score += 15;
    if (state.threatNarrative.trim())           score += 10;
    if (state.selectedCatalogKeys.length > 0 || state.hfRepoId || state.customDatasetNote) score += 15;
    if (state.metric)                           score += 10;
    if (state.scoringMethod)                    score += 10;
    if (state.contaminationControls.length > 0) score += 10;
    if (state.robustnessChecks.length > 0)      score += 10;
    if (state.knownBlindSpots.trim())           score += 5;
    if (state.reviewTriggers.length > 0)        score += 10;
    if (state.escalationRules.trim())           score += 5;
    return score;
  })();

  const completenessColor =
    completeness >= 80 ? "text-green-700 bg-green-100" :
    completeness >= 50 ? "text-amber-700 bg-amber-100" :
    "text-red-700 bg-red-100";

  const tags = [
    "security-wizard",
    ...state.riskDomains,
    state.evaluationType,
    state.autonomyLevel.toLowerCase(),
    ...(state.selectedCatalogKeys.length > 0 ? ["INESIA"] : []),
  ];

  const configPreview = {
    security_profile: {
      risk_domains: state.riskDomains,
      threat_narrative: state.threatNarrative,
      autonomy_level: state.autonomyLevel,
      deployment_context: state.deploymentContext,
      user_profile: state.userProfile,
      source_strategy: state.sourceStrategy,
      selected_catalog_keys: state.selectedCatalogKeys,
      hf_repo_id: state.hfRepoId || null,
      evaluation_type: state.evaluationType,
      scoring_method: state.scoringMethod,
      split_strategy: state.splitStrategy,
      contamination_controls: state.contaminationControls,
      robustness_checks: state.robustnessChecks,
      known_blind_spots: state.knownBlindSpots,
      confidence_policy: state.confidencePolicy,
      blocking_threshold: state.blockingThreshold,
      watch_threshold: state.watchThreshold,
      monitoring_frequency: state.monitoringFrequency,
      review_triggers: state.reviewTriggers,
      escalation_rules: state.escalationRules,
      custom_dataset_note: state.customDatasetNote || null,
      wizard_version: "1.0",
    },
  };

  return (
    <div>
      <SectionTitle
        icon="✅"
        title="Review & Generate Benchmark Card"
        subtitle="Finalize the benchmark name, description, and review the generated security profile."
      />

      <div className="flex items-center gap-3 mb-5">
        <div className={`px-3 py-1.5 rounded-lg text-sm font-bold ${completenessColor}`}>
          {completeness}% complete
        </div>
        {completeness < 50 && (
          <span className="text-xs text-red-600">⚠ Below 50% — add more methodology details before creating an operational benchmark.</span>
        )}
        {completeness >= 80 && (
          <span className="text-xs text-green-600">✓ Well-documented benchmark — ready for operational use.</span>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 mb-5">
        <div>
          <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5 block">Benchmark Name <span className="text-red-500">*</span></label>
          <input
            required
            value={state.name}
            onChange={e => setState({ ...state, name: e.target.value })}
            placeholder="e.g. Cyber Uplift + Scheming — Production Agent v2"
            className="w-full border border-slate-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900"
          />
        </div>
        <div>
          <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5 block">Description <span className="text-red-500">*</span></label>
          <textarea
            rows={3}
            value={state.description}
            onChange={e => setState({ ...state, description: e.target.value })}
            placeholder="Summarize the benchmark purpose, target model type, and key threat scenarios..."
            className="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900 resize-none"
          />
        </div>
      </div>

      {/* Summary card */}
      <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 mb-4 space-y-3 text-xs">
        <div className="font-semibold text-slate-700 text-sm mb-3">📄 Generated Benchmark Card</div>

        <div className="grid grid-cols-2 gap-x-6 gap-y-2">
          <div><span className="text-slate-400">Risk domains:</span> <span className="text-slate-800 font-medium">{state.riskDomains.join(", ") || "—"}</span></div>
          <div><span className="text-slate-400">Autonomy:</span> <span className="text-slate-800 font-medium">{state.autonomyLevel}</span></div>
          <div><span className="text-slate-400">Type:</span> <span className={`font-medium ${state.evaluationType === "operational" ? "text-red-700" : "text-blue-700"}`}>{state.evaluationType}</span></div>
          <div><span className="text-slate-400">Metric:</span> <span className="text-slate-800 font-mono">{state.metric}</span></div>
          <div><span className="text-slate-400">Samples:</span> <span className="text-slate-800 font-medium">{state.numSamples}</span></div>
          <div><span className="text-slate-400">Scoring:</span> <span className="text-slate-800 font-medium">{state.scoringMethod}</span></div>
          <div><span className="text-slate-400">Blocking:</span> <span className="text-red-700 font-bold">{(state.blockingThreshold * 100).toFixed(0)}%</span></div>
          <div><span className="text-slate-400">Watch:</span> <span className="text-amber-700 font-bold">{(state.watchThreshold * 100).toFixed(0)}%</span></div>
          <div><span className="text-slate-400">Monitoring:</span> <span className="text-slate-800 font-medium">{state.monitoringFrequency}</span></div>
          <div><span className="text-slate-400">Confidence:</span> <span className="text-slate-800 font-medium">{state.confidencePolicy}</span></div>
        </div>

        {state.selectedCatalogKeys.length > 0 && (
          <div>
            <span className="text-slate-400">INESIA datasets ({state.selectedCatalogKeys.length}):</span>{" "}
            <span className="text-slate-800">{state.selectedCatalogKeys.join(", ")}</span>
          </div>
        )}

        {state.contaminationControls.length > 0 && (
          <div><span className="text-slate-400">Contamination:</span> {state.contaminationControls.join(", ")}</div>
        )}
        {state.robustnessChecks.length > 0 && (
          <div><span className="text-slate-400">Robustness:</span> {state.robustnessChecks.join(", ")}</div>
        )}
        {state.knownBlindSpots && (
          <div className="border-t border-slate-200 pt-2 mt-2">
            <span className="text-amber-600 font-medium">⚠ Blind spots:</span>{" "}
            <span className="text-slate-600 italic">{state.knownBlindSpots}</span>
          </div>
        )}

        <div className="border-t border-slate-200 pt-2 flex flex-wrap gap-1">
          {tags.map(t => <span key={t} className="bg-white border border-slate-200 text-slate-600 text-[10px] px-2 py-0.5 rounded-full">{t}</span>)}
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-3 text-xs text-red-700 mb-3">
          {error}
        </div>
      )}

      {creating && (
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <Spinner size={14} /> Creating benchmark…
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Validation helpers
// ─────────────────────────────────────────────────────────────────────────────

function validateStep(step: number, state: WizardState): string | null {
  if (step === 1 && state.riskDomains.length === 0) return "Select at least one risk domain.";
  if (step === 3) {
    const hasSrc = state.selectedCatalogKeys.length > 0 || state.hfRepoId.trim() || state.customDatasetNote.trim();
    if (!hasSrc) return "Select at least one data source.";
  }
  if (step === 7) {
    if (!state.name.trim()) return "Benchmark name is required.";
    if (!state.description.trim()) return "Description is required.";
  }
  return null;
}

// ─────────────────────────────────────────────────────────────────────────────
// Main Wizard Component
// ─────────────────────────────────────────────────────────────────────────────

export function SecurityBenchmarkWizard({ onClose, onCreated }: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const [step, setStep] = useState(1);
  const [state, setState] = useState<WizardState>(DEFAULT_STATE);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stepError, setStepError] = useState<string | null>(null);

  const TOTAL_STEPS = STEPS.length;

  const goNext = () => {
    const err = validateStep(step, state);
    if (err) { setStepError(err); return; }
    setStepError(null);
    setStep(s => Math.min(s + 1, TOTAL_STEPS));
  };

  const goPrev = () => {
    setStepError(null);
    setStep(s => Math.max(s - 1, 1));
  };

  const handleCreate = async () => {
    const err = validateStep(7, state);
    if (err) { setStepError(err); return; }

    setCreating(true);
    setError(null);

    const tags = [
      "security-wizard",
      ...state.riskDomains,
      state.evaluationType,
      state.autonomyLevel.toLowerCase(),
      ...(state.selectedCatalogKeys.length > 0 ? ["INESIA"] : []),
    ];

    const configPayload = {
      security_profile: {
        risk_domains: state.riskDomains,
        threat_narrative: state.threatNarrative,
        autonomy_level: state.autonomyLevel,
        deployment_context: state.deploymentContext,
        user_profile: state.userProfile,
        source_strategy: state.sourceStrategy,
        selected_catalog_keys: state.selectedCatalogKeys,
        hf_repo_id: state.hfRepoId || null,
        evaluation_type: state.evaluationType,
        scoring_method: state.scoringMethod,
        split_strategy: state.splitStrategy,
        contamination_controls: state.contaminationControls,
        robustness_checks: state.robustnessChecks,
        known_blind_spots: state.knownBlindSpots,
        confidence_policy: state.confidencePolicy,
        blocking_threshold: state.blockingThreshold,
        watch_threshold: state.watchThreshold,
        monitoring_frequency: state.monitoringFrequency,
        review_triggers: state.reviewTriggers,
        escalation_rules: state.escalationRules,
        custom_dataset_note: state.customDatasetNote || null,
        wizard_version: "1.0",
      },
    };

    try {
      const res = await fetch(`${API_BASE}/benchmarks/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: state.name,
          type: "safety",
          description: state.description,
          tags,
          metric: state.metric,
          num_samples: state.numSamples,
          config: configPayload,
          risk_threshold: state.blockingThreshold,
        }),
      });
      if (!res.ok) {
        const e = await res.json().catch(() => ({}));
        throw new Error(e.detail ?? `HTTP ${res.status}`);
      }
      onCreated();
      onClose();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl w-full max-w-3xl max-h-[92vh] flex flex-col shadow-2xl">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <div>
            <h2 className="font-semibold text-slate-900 flex items-center gap-2">
              <Shield size={16} className="text-red-600" />
              Security Benchmark Builder
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              State-of-the-art frontier AI safety evaluation — INESIA methodology
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 hover:bg-slate-100 rounded-lg text-slate-500"
          >
            <X size={16} />
          </button>
        </div>

        {/* Step Indicator */}
        <div className="px-6 py-3 border-b border-slate-100">
          <StepIndicator current={step} total={TOTAL_STEPS} />
        </div>

        {/* Step Content */}
        <div className="flex-1 overflow-y-auto px-6 py-5">
          {step === 1 && <Step1_RiskObjective state={state} setState={setState} />}
          {step === 2 && <Step2_AutonomyContext state={state} setState={setState} />}
          {step === 3 && <Step3_Sources state={state} setState={setState} />}
          {step === 4 && <Step4_Protocol state={state} setState={setState} />}
          {step === 5 && <Step5_Methodology state={state} setState={setState} />}
          {step === 6 && <Step6_Governance state={state} setState={setState} />}
          {step === 7 && (
            <Step7_Review
              state={state}
              setState={setState}
              creating={creating}
              error={error}
            />
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-slate-100">
          <div className="flex items-center gap-3">
            {step > 1 && (
              <button
                type="button"
                onClick={goPrev}
                className="flex items-center gap-1.5 text-sm text-slate-600 hover:text-slate-900 px-3 py-2 rounded-lg hover:bg-slate-100 transition-colors"
              >
                <ChevronLeft size={14} /> Back
              </button>
            )}
            {stepError && (
              <span className="text-xs text-red-600 flex items-center gap-1">
                <AlertTriangle size={12} /> {stepError}
              </span>
            )}
          </div>

          <div className="flex items-center gap-3">
            <span className="text-xs text-slate-400">Step {step} / {TOTAL_STEPS}</span>
            {step < TOTAL_STEPS ? (
              <button
                type="button"
                onClick={goNext}
                className="flex items-center gap-1.5 bg-slate-900 text-white px-4 py-2 rounded-lg text-sm hover:bg-slate-700 transition-colors"
              >
                Continue <ChevronRight size={14} />
              </button>
            ) : (
              <button
                type="button"
                onClick={handleCreate}
                disabled={creating || !state.name.trim() || !state.description.trim()}
                className="flex items-center gap-1.5 bg-red-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-red-700 disabled:opacity-40 transition-colors"
              >
                {creating ? <><Spinner size={14} /> Creating…</> : <><Shield size={14} /> Create Benchmark</>}
              </button>
            )}
          </div>
        </div>

      </div>
    </div>
  );
}
