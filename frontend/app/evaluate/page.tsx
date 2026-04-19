"use client";
import { Suspense, useState, useEffect, useMemo, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useModels, useBenchmarks, useCampaigns } from "@/lib/useApi";
import { campaignsApi, capabilityApi } from "@/lib/api";
import type { LLMModelSlim, Benchmark, Campaign } from "@/lib/api";
import { Spinner } from "@/components/Spinner";
import { ModelSelector } from "@/components/ModelSelector";
import { timeAgo } from "@/lib/utils";
import { API_BASE } from "@/lib/config";
import {
  Check, Rocket, Wrench, Brain, Globe, Settings,
  Clock, DollarSign, RefreshCw, Save, ChevronDown, ChevronUp,
} from "lucide-react";

type EvalType = "capability" | "safety" | "behavioral" | "comparative" | "compliance";
type AutonomyLevel = "L1" | "L2" | "L3" | "L4" | "L5";

const EVAL_TYPES: {
  key: EvalType; icon: string; label: string; desc: string;
  activeBar: string; activeBg: string; activeText: string;
}[] = [
  { key: "capability",  icon: "🎯", label: "Capability",  desc: "Academic · reasoning · coding",    activeBar: "bg-blue-500",   activeBg: "bg-blue-50",   activeText: "text-blue-700"  },
  { key: "safety",      icon: "🛡",  label: "Safety",      desc: "INESIA · CBRN · alignment",        activeBar: "bg-red-500",    activeBg: "bg-red-50",    activeText: "text-red-700"   },
  { key: "behavioral",  icon: "🧬", label: "Behavioral",  desc: "Genomia · propensity scores",      activeBar: "bg-cyan-500",   activeBg: "bg-cyan-50",   activeText: "text-cyan-700"  },
  { key: "comparative", icon: "⚖️", label: "Comparative", desc: "Head-to-head multi-model",         activeBar: "bg-violet-500", activeBg: "bg-violet-50", activeText: "text-violet-700"},
  { key: "compliance",  icon: "📋", label: "Compliance",  desc: "EU AI Act · NIST · ISO 42001",     activeBar: "bg-amber-500",  activeBg: "bg-amber-50",  activeText: "text-amber-700" },
];

const AUTONOMY_LEVELS: Record<AutonomyLevel, { label: string; desc: string; color: string }> = {
  L1: { label: "No autonomy",    desc: "Human approves every action",            color: "bg-green-100  text-green-700  border-green-200"  },
  L2: { label: "Supervised",     desc: "Human reviews outputs before acting",    color: "bg-blue-100   text-blue-700   border-blue-200"   },
  L3: { label: "Conditional",    desc: "Human intervenes on exceptions only",    color: "bg-yellow-100 text-yellow-700 border-yellow-200" },
  L4: { label: "High autonomy",  desc: "Model acts independently on most tasks", color: "bg-orange-100 text-orange-700 border-orange-200" },
  L5: { label: "Full autonomy",  desc: "No human-in-the-loop",                  color: "bg-red-100    text-red-700    border-red-200"    },
};

const RISK_DOMAINS = [
  { key: "cbrn",         label: "CBRN Uplift",     icon: "☢️", desc: "Chemical, biological, radiological, nuclear"     },
  { key: "cyber",        label: "Cyber Uplift",     icon: "💻", desc: "Offensive cyber, attack planning"               },
  { key: "fimi",         label: "Info Warfare",     icon: "📡", desc: "Disinformation, influence operations"           },
  { key: "agentic",      label: "Agentic Failures", icon: "🤖", desc: "Prompt injection, goal drift, inter-agent trust" },
  { key: "alignment",    label: "Alignment",        icon: "🧭", desc: "Scheming, sandbagging, sycophancy"              },
  { key: "safety",       label: "General Safety",   icon: "🛡",  desc: "Refusal calibration, harmful content"           },
  { key: "purple_llama", label: "Purple Llama",     icon: "🦙", desc: "Meta AI safety — CyberSecEval & LlamaGuard"     },
];

const TOOL_OPTIONS = [
  "Web search", "Code execution", "File system", "Email/calendar",
  "Database", "External APIs", "Browser automation", "Memory (long-term)", "Sub-agent spawning",
];

const COMPLIANCE_FRAMEWORKS = [
  { key: "eu_ai_act", label: "EU AI Act",     icon: "🇪🇺", desc: "High-risk system · Title III"        },
  { key: "nist_rmf",  label: "NIST AI RMF",   icon: "🇺🇸", desc: "Govern · Map · Measure · Manage"     },
  { key: "iso_42001", label: "ISO 42001",      icon: "🌐", desc: "AI management system requirements"   },
  { key: "mlcommons", label: "MLCommons v0.5", icon: "🔬", desc: "AI Safety benchmarks from MLCommons" },
];

const DOMAIN_KW_MAP: Record<string, string[]> = {
  cbrn:         ["cbrn","chemical","biological","radiological","nuclear","explosives"],
  cyber:        ["ckb","cyber","mitre","attack"],
  fimi:         ["fimi","disarm","information"],
  agentic:      ["agentic","autonomy","failure mode"],
  alignment:    ["scheming","sycophancy","shutdown","sandbagging","persuasion"],
  safety:       ["refusals","harmbench","wildguard","salad"],
  purple_llama: ["purple llama","llamaguard","cyberseceval","mlcommons","meta"],
};

const FRAMEWORK_KW_MAP: Record<string, string[]> = {
  eu_ai_act:  ["safety","accuracy","transparency","refusals","harmbench"],
  nist_rmf:   ["safety","alignment","cyber","cbrn"],
  iso_42001:  ["safety","accuracy"],
  mlcommons:  ["mlcommons","llamaguard","cyberseceval","purple llama"],
};

type BenchFilterKey = "all" | "academic" | "safety" | "coding" | "custom" | "inesia";
const BENCH_FILTERS: { key: BenchFilterKey; label: string }[] = [
  { key: "all",      label: "All"      },
  { key: "inesia",   label: "☿ INESIA" },
  { key: "academic", label: "Academic" },
  { key: "safety",   label: "Safety"   },
  { key: "coding",   label: "Code"     },
  { key: "custom",   label: "Custom"   },
];
function benchInFilter(b: Benchmark, f: BenchFilterKey): boolean {
  if (f === "all") return true;
  if (f === "inesia") return (b.tags ?? []).some(t => ["INESIA","frontier","cyber","disinformation","MITRE","DISARM","ATLAS"].includes(t)) || b.type === "safety";
  return b.type === f;
}

function estimateCost(
  models: LLMModelSlim[], selectedModelIds: number[],
  numBenchmarks: number, maxSamples: number,
): { costUsd: number; timeMin: number } {
  if (!selectedModelIds.length || !numBenchmarks) return { costUsd: 0, timeMin: 0 };
  let costUsd = 0;
  for (const id of selectedModelIds) {
    const m = models.find(x => x.id === id);
    if (!m) continue;
    costUsd += (m.cost_input_per_1k * 700 / 1000) * numBenchmarks * maxSamples;
  }
  const timeMin = Math.max(1, Math.ceil(selectedModelIds.length * numBenchmarks * maxSamples * 1.5 * 0.6 / 60));
  return { costUsd, timeMin };
}

function TypePicker({ value, onChange }: { value: EvalType; onChange: (t: EvalType) => void }) {
  return (
    <div className="flex flex-row md:flex-col gap-1.5 overflow-x-auto md:overflow-visible py-1 md:py-0">
      {EVAL_TYPES.map(t => {
        const active = t.key === value;
        return (
          <button key={t.key} onClick={() => onChange(t.key)}
            className={`flex md:flex-row items-center gap-2.5 px-3 py-2.5 rounded-xl border text-left transition-all shrink-0 md:shrink ${
              active ? `${t.activeBg} border-current ${t.activeText} font-medium shadow-sm`
                     : "border-slate-200 text-slate-600 hover:bg-slate-50 hover:border-slate-300"
            }`}>
            <span className="text-lg leading-none shrink-0">{t.icon}</span>
            <div className="min-w-0">
              <div className={`text-sm font-medium truncate ${active ? "" : "text-slate-800"}`}>{t.label}</div>
              <div className={`text-[10px] hidden md:block truncate ${active ? "opacity-75" : "text-slate-400"}`}>{t.desc}</div>
            </div>
            {active && <div className={`hidden md:block w-1 h-6 rounded-full ml-auto shrink-0 ${t.activeBar}`} />}
          </button>
        );
      })}
    </div>
  );
}

function CommonFields({ name, description, maxSamples, temperature, onChange }: {
  name: string; description: string; maxSamples: number; temperature: number;
  onChange: (p: Partial<{ name: string; description: string; maxSamples: number; temperature: number }>) => void;
}) {
  return (
    <div className="space-y-4">
      <div>
        <label className="text-xs font-medium text-slate-600 mb-1 block">Evaluation name</label>
        <input value={name} onChange={e => onChange({ name: e.target.value })}
          placeholder="e.g. Claude Sonnet — Safety audit Q2 2026"
          className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900" />
      </div>
      <div>
        <label className="text-xs font-medium text-slate-600 mb-1 block">Description <span className="text-slate-400">(optional)</span></label>
        <input value={description} onChange={e => onChange({ description: e.target.value })}
          placeholder="Context, goals, notes…"
          className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900" />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="text-xs font-medium text-slate-600 mb-1 block">Max samples / benchmark</label>
          <input type="number" value={maxSamples} onChange={e => onChange({ maxSamples: +e.target.value })}
            min={5} max={500} step={5} className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" />
          <p className="text-[10px] text-slate-400 mt-0.5">≥50 recommended for grade A</p>
        </div>
        <div>
          <label className="text-xs font-medium text-slate-600 mb-1 block">Temperature</label>
          <input type="number" value={temperature} onChange={e => onChange({ temperature: +e.target.value })}
            min={0} max={2} step={0.1} className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" />
          <p className="text-[10px] text-slate-400 mt-0.5">0.0 = deterministic</p>
        </div>
      </div>
    </div>
  );
}

function BenchmarkPicker({
  benchmarks, selected, onChange, defaultFilter = "all", locked = false,
}: {
  benchmarks: Benchmark[]; selected: number[]; onChange: (ids: number[]) => void;
  defaultFilter?: BenchFilterKey; locked?: boolean;
}) {
  const [filter, setFilter] = useState<BenchFilterKey>(defaultFilter);
  const [expanded, setExpanded] = useState(false);
  const filtered = useMemo(() => benchmarks.filter(b => benchInFilter(b, filter)), [benchmarks, filter]);

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <label className="text-xs font-medium text-slate-600">Benchmarks</label>
        <div className="flex items-center gap-2">
          <span className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full">{selected.length} selected</span>
          {locked && selected.length > 0 && (
            <button onClick={() => setExpanded(x => !x)}
              className="text-xs text-blue-500 hover:underline flex items-center gap-1">
              {expanded ? <><ChevronUp size={11} />hide</> : <><ChevronDown size={11} />edit</>}
            </button>
          )}
        </div>
      </div>

      {locked && !expanded ? (
        <div className="bg-green-50 border border-green-200 rounded-xl p-3 text-xs text-green-700">
          ✓ {selected.length} benchmark{selected.length !== 1 ? "s" : ""} auto-selected.{" "}
          <button className="underline" onClick={() => setExpanded(true)}>Edit</button>
        </div>
      ) : (
        <>
          <div className="flex gap-1.5 flex-wrap mb-2">
            {BENCH_FILTERS.map(({ key, label }) => (
              <button key={key} onClick={() => setFilter(key)}
                className={`text-xs px-2.5 py-1 rounded-lg transition-colors ${
                  filter === key ? "bg-slate-900 text-white" : "border border-slate-200 text-slate-600 hover:bg-slate-50"
                }`}>
                {label} <span className="opacity-50">{benchmarks.filter(b => benchInFilter(b, key)).length}</span>
              </button>
            ))}
          </div>
          <div className="space-y-1.5 max-h-56 overflow-y-auto">
            {filtered.map(b => {
              const sel = selected.includes(b.id);
              return (
                <button key={b.id} type="button"
                  onClick={() => onChange(sel ? selected.filter(x => x !== b.id) : [...selected, b.id])}
                  className={`w-full flex items-center gap-3 p-3 rounded-xl border text-left transition-colors ${
                    sel ? "border-slate-900 bg-slate-50" : "border-slate-100 bg-white hover:border-slate-200"
                  }`}>
                  <div className={`w-5 h-5 rounded-md border-2 flex items-center justify-center shrink-0 ${
                    sel ? "border-slate-900 bg-slate-900" : "border-slate-300"
                  }`}>{sel && <Check size={11} className="text-white" />}</div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-slate-900 truncate">{b.name}</div>
                    <div className="text-xs text-slate-400">{b.metric} · {b.num_samples ?? "all"} items</div>
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded-full shrink-0 ${
                    b.type === "safety" ? "bg-red-50 text-red-600"
                    : b.type === "academic" ? "bg-blue-50 text-blue-600" : "bg-slate-100 text-slate-500"
                  }`}>{b.type}</span>
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

function SafetyForm({ form, benchmarks, onChange }: {
  form: StudioForm; benchmarks: Benchmark[];
  onChange: (p: Partial<StudioForm>) => void;
}) {
  const needsWarning = form.autonomy_level === "L4" || form.autonomy_level === "L5";
  return (
    <div className="space-y-6">
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-xs text-blue-700">
        <span className="font-semibold">INESIA doctrine:</span>{" "}
        Evaluate the <em>system-in-context</em>, not the model in isolation.
        Risk profile = f(tools, autonomy, deployment context).
      </div>
      <ModelSelector mode="single" selected={form.model_ids} onChange={ids => onChange({ model_ids: ids })}
        idType="db_id" label="Model under evaluation" maxHeight="max-h-48" />
      <div>
        <label className="text-xs font-medium text-slate-600 mb-2 block">
          <Settings size={11} className="inline mr-1" />Autonomy level
        </label>
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-2">
          {(Object.entries(AUTONOMY_LEVELS) as [AutonomyLevel, typeof AUTONOMY_LEVELS[AutonomyLevel]][]).map(([level, cfg]) => (
            <button key={level} onClick={() => onChange({ autonomy_level: level })}
              className={`text-left flex items-center gap-2 px-3 py-2.5 rounded-xl border text-xs transition-colors ${
                form.autonomy_level === level ? `${cfg.color} border-current` : "border-slate-200 hover:bg-slate-50"
              }`}>
              <span className="font-mono font-bold w-5 shrink-0">{level}</span>
              <div><div className="font-semibold">{cfg.label}</div><div className="text-[10px] text-slate-500">{cfg.desc}</div></div>
              {form.autonomy_level === level && <Check size={12} className="ml-auto shrink-0" />}
            </button>
          ))}
        </div>
        {needsWarning && (
          <div className="mt-2 bg-red-50 border border-red-200 rounded-lg p-2.5 text-xs text-red-700">
            ⚠️ Autonomy {form.autonomy_level} — agentic failure modes are <strong>strongly recommended</strong> per INESIA doctrine.
          </div>
        )}
      </div>
      <div>
        <label className="text-xs font-medium text-slate-600 mb-2 block"><Wrench size={11} className="inline mr-1" />Tools granted to the system</label>
        <div className="flex flex-wrap gap-2">
          {TOOL_OPTIONS.map(t => (
            <button key={t} onClick={() => onChange({ tools: form.tools.includes(t) ? form.tools.filter(x => x !== t) : [...form.tools, t] })}
              className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
                form.tools.includes(t) ? "bg-slate-900 text-white border-slate-900" : "border-slate-200 text-slate-600 hover:bg-slate-50"
              }`}>{t}</button>
          ))}
        </div>
      </div>
      <div className="flex gap-3">
        {[
          { key: "has_memory" as const,        label: "Long-term memory",          icon: Brain  },
          { key: "has_orchestration" as const, label: "Multi-agent orchestration",  icon: Globe  },
        ].map(({ key, label, icon: Icon }) => (
          <button key={key} onClick={() => onChange({ [key]: !form[key] })}
            className={`flex-1 flex items-center gap-2 px-3 py-2.5 rounded-xl border text-xs transition-colors ${
              form[key] ? "bg-slate-900 text-white border-slate-900" : "border-slate-200 text-slate-600 hover:bg-slate-50"
            }`}>
            <Icon size={13} />{label}{form[key] && <Check size={12} className="ml-auto shrink-0" />}
          </button>
        ))}
      </div>
      <div>
        <label className="text-xs font-medium text-slate-600 mb-1 block"><Globe size={11} className="inline mr-1" />Deployment context</label>
        <input value={form.deployment_context} onChange={e => onChange({ deployment_context: e.target.value })}
          placeholder="e.g. Customer support chatbot, medical triage assistant, autonomous coding agent…"
          className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900" />
      </div>
      <div>
        <label className="text-xs font-medium text-slate-600 mb-2 block">Risk domains</label>
        <div className="grid grid-cols-2 gap-2">
          {RISK_DOMAINS.map(({ key, label, icon, desc }) => (
            <button key={key}
              onClick={() => onChange({ risk_domains: form.risk_domains.includes(key) ? form.risk_domains.filter(x => x !== key) : [...form.risk_domains, key] })}
              className={`text-left p-3 rounded-xl border transition-colors ${
                form.risk_domains.includes(key) ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 hover:border-slate-300 hover:bg-slate-50"
              }`}>
              <div className="text-xl mb-0.5">{icon}</div>
              <div className="text-xs font-medium">{label}</div>
              <div className={`text-[10px] mt-0.5 ${form.risk_domains.includes(key) ? "text-slate-300" : "text-slate-400"}`}>{desc}</div>
            </button>
          ))}
        </div>
      </div>
      <BenchmarkPicker benchmarks={benchmarks} selected={form.benchmark_ids}
        onChange={ids => onChange({ benchmark_ids: ids })}
        defaultFilter="safety" locked={form.risk_domains.length > 0} />
    </div>
  );
}

function ComplianceForm({ form, benchmarks, onChange }: {
  form: StudioForm; benchmarks: Benchmark[];
  onChange: (p: Partial<StudioForm>) => void;
}) {
  return (
    <div className="space-y-6">
      <ModelSelector mode="single" selected={form.model_ids} onChange={ids => onChange({ model_ids: ids })}
        idType="db_id" label="Model under evaluation" maxHeight="max-h-48" />
      <div>
        <label className="text-xs font-medium text-slate-600 mb-2 block">Compliance framework</label>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {COMPLIANCE_FRAMEWORKS.map(f => (
            <button key={f.key} onClick={() => onChange({ compliance_framework: f.key })}
              className={`text-left p-4 rounded-xl border transition-colors ${
                form.compliance_framework === f.key ? "border-amber-500 bg-amber-50 text-amber-900" : "border-slate-200 hover:border-slate-300 hover:bg-slate-50"
              }`}>
              <div className="text-xl mb-1">{f.icon}</div>
              <div className="text-sm font-medium">{f.label}</div>
              <div className="text-xs text-slate-500 mt-0.5">{f.desc}</div>
              {form.compliance_framework === f.key && <Check size={12} className="mt-1 text-amber-600" />}
            </button>
          ))}
        </div>
      </div>
      <BenchmarkPicker benchmarks={benchmarks} selected={form.benchmark_ids}
        onChange={ids => onChange({ benchmark_ids: ids })} locked={!!form.compliance_framework} />
    </div>
  );
}

function GenericForm({ form, benchmarks, onChange, multiModel, defaultBenchFilter }: {
  form: StudioForm; benchmarks: Benchmark[];
  onChange: (p: Partial<StudioForm>) => void;
  multiModel?: boolean; defaultBenchFilter?: BenchFilterKey;
}) {
  return (
    <div className="space-y-6">
      <ModelSelector
        mode={multiModel ? "multi" : "single"} selected={form.model_ids}
        onChange={ids => onChange({ model_ids: ids })} idType="db_id"
        label={multiModel ? "Models to compare (select ≥ 2)" : "Model under evaluation"}
        maxHeight="max-h-48" />
      <BenchmarkPicker benchmarks={benchmarks} selected={form.benchmark_ids}
        onChange={ids => onChange({ benchmark_ids: ids })} defaultFilter={defaultBenchFilter ?? "all"} />
    </div>
  );
}

function PreviewPanel({
  models, selectedModelIds, numBenchmarks, maxSamples, evalType, campaigns, onClone,
}: {
  models: LLMModelSlim[]; selectedModelIds: number[];
  numBenchmarks: number; maxSamples: number;
  evalType: EvalType; campaigns: Campaign[];
  onClone: (c: Campaign) => void;
}) {
  const { costUsd, timeMin } = estimateCost(models, selectedModelIds, numBenchmarks, maxSamples);
  const [capProfile, setCapProfile] = useState<any>(null);
  const [capLoading, setCapLoading] = useState(false);
  const primaryModelId = selectedModelIds[0];

  useEffect(() => {
    if (!primaryModelId) { setCapProfile(null); return; }
    setCapLoading(true);
    capabilityApi.profile(primaryModelId)
      .then(p => setCapProfile(p))
      .catch(() => setCapProfile(null))
      .finally(() => setCapLoading(false));
  }, [primaryModelId]);

  const recentRuns = campaigns.slice(0, 3);

  const TIPS: Record<EvalType, React.ReactNode> = {
    safety: (
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-[11px] text-blue-700 space-y-1">
        <div className="font-semibold mb-1">INESIA doctrine</div>
        <div>• System-in-context, not model in isolation</div>
        <div>• Risk profile = f(tools, autonomy, context)</div>
        <div>• ≥50 samples for grade A reliability</div>
      </div>
    ),
    capability: (
      <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 text-[11px] text-slate-600 space-y-1">
        <div className="font-semibold mb-1">Capability tips</div>
        <div>• Temperature 0 = reproducible results</div>
        <div>• ≥100 samples for MMLU-class benchmarks</div>
        <div>• Multi-model enables auto-comparison</div>
      </div>
    ),
    behavioral: (
      <div className="bg-cyan-50 border border-cyan-200 rounded-xl p-4 text-[11px] text-cyan-700 space-y-1">
        <div className="font-semibold mb-1">Behavioral eval</div>
        <div>• Results feed into Genomia fingerprint</div>
        <div>• View profile in Analyser → Genomia</div>
      </div>
    ),
    comparative: (
      <div className="bg-violet-50 border border-violet-200 rounded-xl p-4 text-[11px] text-violet-700 space-y-1">
        <div className="font-semibold mb-1">Head-to-head</div>
        <div>• Select ≥2 models to compare</div>
        <div>• McNemar / permutation test available in Analyser</div>
      </div>
    ),
    compliance: (
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-[11px] text-amber-700 space-y-1">
        <div className="font-semibold mb-1">Compliance eval</div>
        <div>• Benchmarks auto-mapped to framework</div>
        <div>• Gaps report generated automatically</div>
      </div>
    ),
  };

  return (
    <div className="space-y-4">
      <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-3">
        <h3 className="text-[10px] font-bold tracking-widest uppercase text-slate-400">Estimate</h3>
        <div className="grid grid-cols-2 gap-2">
          <div className="bg-slate-50 rounded-lg p-3">
            <div className="text-[10px] text-slate-400 mb-0.5 flex items-center gap-1"><DollarSign size={9} />Cost</div>
            <div className="font-semibold text-slate-900 text-sm">
              {!selectedModelIds.length || !numBenchmarks ? "—" : costUsd === 0 ? "Free" : costUsd < 0.01 ? "< $0.01" : `~$${costUsd.toFixed(2)}`}
            </div>
          </div>
          <div className="bg-slate-50 rounded-lg p-3">
            <div className="text-[10px] text-slate-400 mb-0.5 flex items-center gap-1"><Clock size={9} />Duration</div>
            <div className="font-semibold text-slate-900 text-sm">
              {!selectedModelIds.length || !numBenchmarks ? "—" : timeMin <= 1 ? "< 1 min" : `~${timeMin} min`}
            </div>
          </div>
        </div>
        {selectedModelIds.length > 0 && numBenchmarks > 0 && (
          <div className="text-[10px] text-slate-400">
            {selectedModelIds.length} model{selectedModelIds.length !== 1 ? "s" : ""} × {numBenchmarks} benchmark{numBenchmarks !== 1 ? "s" : ""} × {maxSamples} samples
          </div>
        )}
      </div>

      {(capLoading || capProfile) && (
        <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-2">
          <h3 className="text-[10px] font-bold tracking-widest uppercase text-slate-400">Capability profile</h3>
          {capLoading ? (
            <div className="flex items-center gap-2 text-xs text-slate-400"><Spinner size={12} />Loading…</div>
          ) : capProfile && (
            <div className="space-y-1.5">
              {(capProfile.strengths ?? []).slice(0, 3).map((s: string, i: number) => (
                <div key={i} className="flex items-center gap-2 text-xs">
                  <span className="w-1.5 h-1.5 rounded-full bg-green-400 shrink-0" />
                  <span className="text-slate-700 truncate">{s}</span>
                </div>
              ))}
              {(capProfile.gaps ?? []).slice(0, 2).map((g: any, i: number) => (
                <div key={i} className="flex items-center gap-2 text-xs">
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0" />
                  <span className="text-slate-500 truncate">{g.sub_capability ?? String(g)}</span>
                </div>
              ))}
              {capProfile.overall_score != null && (
                <div className="text-[10px] text-slate-400 pt-1">
                  Overall: <span className="font-semibold text-slate-700">{(capProfile.overall_score * 100).toFixed(0)}%</span>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {recentRuns.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <h3 className="text-[10px] font-bold tracking-widest uppercase text-slate-400 mb-2">Recent runs</h3>
          {recentRuns.map(c => (
            <div key={c.id} className="flex items-center gap-2 py-1.5 group">
              <div className="flex-1 min-w-0">
                <div className="text-xs font-medium text-slate-800 truncate">{c.name}</div>
                <div className="text-[10px] text-slate-400">{timeAgo(c.created_at)} · {c.status}</div>
              </div>
              <button onClick={() => onClone(c)}
                className="shrink-0 text-[10px] text-blue-500 hover:text-blue-700 opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1"
                title="Clone & re-run"><RefreshCw size={10} />Clone</button>
            </div>
          ))}
        </div>
      )}

      {TIPS[evalType]}
    </div>
  );
}

interface StudioForm {
  name: string; description: string;
  model_ids: number[]; benchmark_ids: number[];
  max_samples: number; temperature: number;
  autonomy_level: AutonomyLevel; tools: string[];
  has_memory: boolean; has_orchestration: boolean;
  deployment_context: string; risk_domains: string[];
  compliance_framework: string;
}

const DEFAULT_FORM: StudioForm = {
  name: "", description: "", model_ids: [], benchmark_ids: [],
  max_samples: 50, temperature: 0.0, autonomy_level: "L2", tools: [],
  has_memory: false, has_orchestration: false, deployment_context: "",
  risk_domains: [], compliance_framework: "",
};

function EvalStudioInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { models } = useModels();
  const { benchmarks, isLoading: benchLoading } = useBenchmarks();
  const { campaigns } = useCampaigns();

  const [evalType, setEvalType] = useState<EvalType>("capability");
  const [form, setForm] = useState<StudioForm>(DEFAULT_FORM);
  const [saving, setSaving] = useState(false);
  const [saveTemplate, setSaveTemplate] = useState(false);
  const [riskProfile, setRiskProfile] = useState<any>(null);
  const [riskLoading, setRiskLoading] = useState(false);

  const patch = useCallback((p: Partial<StudioForm>) => setForm(f => ({ ...f, ...p })), []);

  useEffect(() => {
    const t = searchParams.get("type") as EvalType | null;
    if (t && EVAL_TYPES.some(x => x.key === t)) setEvalType(t);
  }, [searchParams]);

  useEffect(() => {
    const cloneId = searchParams.get("clone");
    if (!cloneId) return;
    const id = parseInt(cloneId, 10);
    const existing = campaigns.find(c => c.id === id);
    if (existing) {
      setForm(f => ({
        ...f,
        name: `${existing.name} (clone)`,
        model_ids: existing.model_ids ?? [],
        benchmark_ids: existing.benchmark_ids ?? [],
        max_samples: existing.max_samples ?? 50,
        temperature: existing.temperature ?? 0,
      }));
    }
  }, [searchParams, campaigns]);

  useEffect(() => {
    if (evalType !== "safety") return;
    const autoIds: number[] = [];
    for (const domain of form.risk_domains) {
      const kws = DOMAIN_KW_MAP[domain] ?? [];
      benchmarks.forEach(b => {
        const hay = (b.name + " " + (b.tags ?? []).join(" ")).toLowerCase();
        if (kws.some(k => hay.includes(k)) && !autoIds.includes(b.id)) autoIds.push(b.id);
      });
    }
    setForm(f => ({ ...f, benchmark_ids: autoIds }));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.risk_domains, benchmarks, evalType]);

  useEffect(() => {
    if (evalType !== "compliance" || !form.compliance_framework) return;
    const kws = FRAMEWORK_KW_MAP[form.compliance_framework] ?? [];
    const autoIds: number[] = [];
    benchmarks.forEach(b => {
      const hay = (b.name + " " + (b.tags ?? []).join(" ")).toLowerCase();
      if (kws.some(k => hay.includes(k))) autoIds.push(b.id);
    });
    setForm(f => ({ ...f, benchmark_ids: autoIds }));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.compliance_framework, benchmarks, evalType]);

  const handleTypeChange = useCallback((t: EvalType) => {
    setEvalType(t);
    setForm(f => ({ ...f, benchmark_ids: [], risk_domains: [], compliance_framework: "" }));
    setRiskProfile(null);
  }, []);

  const primaryModelId = form.model_ids[0];
  useEffect(() => {
    if (evalType !== "safety" || !primaryModelId || !form.risk_domains.length) {
      setRiskProfile(null); return;
    }
    const domainScores: Record<string, number> = {};
    if (form.risk_domains.includes("cbrn"))      domainScores.cbrn = 0.55;
    if (form.risk_domains.includes("cyber"))     domainScores.cyber = 0.55;
    if (form.risk_domains.includes("fimi"))      domainScores.persuasion = 0.5;
    if (form.risk_domains.includes("agentic"))   { domainScores.goal_drift = 0.5; domainScores.scope_creep = 0.45; }
    if (form.risk_domains.includes("alignment")) { domainScores.scheming = 0.5; domainScores.sycophancy = 0.4; }
    if (form.risk_domains.includes("safety"))    domainScores.safety_refusal = 0.45;
    if (form.has_orchestration) domainScores.inter_agent_trust = 0.5;
    const propensityScores: Record<string, number> = {};
    if (form.risk_domains.includes("alignment")) propensityScores.scheming = 0.4;
    if (form.risk_domains.includes("fimi"))      propensityScores.persuasion = 0.4;
    const toolMap: Record<string, string> = {
      "Web search": "web_search", "Code execution": "code_execution", "File system": "file_system",
      "Email/calendar": "email", "Database": "database", "External APIs": "external_apis", "Browser automation": "browser",
    };
    const tools = form.tools.map(t => toolMap[t]).filter(Boolean);
    const modelName = models.find(m => m.id === primaryModelId)?.name ?? "system";
    const controller = new AbortController();
    setRiskLoading(true);
    fetch(`${API_BASE}/science/compositional-risk`, {
      signal: controller.signal,
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model_name: modelName, domain_scores: domainScores, propensity_scores: propensityScores,
        autonomy_level: form.autonomy_level, tools,
        memory_type: form.has_memory ? "persistent" : "session",
      }),
    })
      .then(r => r.ok ? r.json() : null)
      .then(setRiskProfile)
      .catch((err) => { if (err.name !== "AbortError") setRiskProfile(null); })
      .finally(() => setRiskLoading(false));
    return () => controller.abort();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [evalType, primaryModelId, form.autonomy_level, form.tools, form.has_memory, form.has_orchestration, form.risk_domains, models]);

  const canLaunch = form.model_ids.length > 0 && form.benchmark_ids.length > 0;
  const needsMoreModels = evalType === "comparative" && form.model_ids.length < 2;

  const launch = async () => {
    if (!canLaunch || needsMoreModels) return;
    setSaving(true);
    const typeLabel = EVAL_TYPES.find(t => t.key === evalType)?.label ?? evalType;
    const descParts: string[] = [`${typeLabel} evaluation`];
    if (evalType === "safety") {
      descParts.push(`Autonomy: ${form.autonomy_level}`);
      if (form.risk_domains.length) descParts.push(`Domains: ${form.risk_domains.join(", ")}`);
      if (form.tools.length)        descParts.push(`Tools: ${form.tools.join(", ")}`);
      if (form.deployment_context)  descParts.push(`Context: ${form.deployment_context}`);
    }
    if (evalType === "compliance")  descParts.push(`Framework: ${form.compliance_framework}`);
    if (evalType === "comparative") descParts.push(`${form.model_ids.length} models`);
    if (form.description)           descParts.push(form.description);
    if (saveTemplate) {
      try {
        const saved = JSON.parse(localStorage.getItem("eval_templates") ?? "[]");
        saved.unshift({ evalType, form, saved_at: new Date().toISOString() });
        localStorage.setItem("eval_templates", JSON.stringify(saved.slice(0, 10)));
      } catch (err) { console.warn("[error]", err); }
    }
    try {
      // Build SystemContext payload — audit requirement: model-in-system not model-in-isolation
      const systemContext = {
        autonomy_level: form.autonomy_level,
        tools: form.tools,
        has_memory: form.has_memory,
        has_orchestration: form.has_orchestration,
        deployment_context: form.deployment_context,
        eval_type: evalType,
        risk_domains: form.risk_domains ?? [],
      };
      const campaign = await campaignsApi.create({
        name: form.name || `${typeLabel} eval · ${new Date().toLocaleDateString()}`,
        description: descParts.join(" | "),
        model_ids: form.model_ids, benchmark_ids: form.benchmark_ids,
        max_samples: form.max_samples, temperature: form.temperature,
        // SystemContext serialised into run_context_json for engine consumption
        run_context_json: JSON.stringify(systemContext),
        judge_model: evalType === "safety" ? "claude-3-5-sonnet-20241022" : undefined,
      });

      // Wire to engines post-creation (non-blocking background calls)
      // #257 — generate reproducibility fingerprint for this eval configuration
      if (campaign?.id) {
        fetch(`${API_BASE}/research/manifests/generate/${campaign.id}`, { method: "POST" })
          .catch(err => console.warn("[evaluate] manifest generation failed (non-fatal):", err));
      }

      router.push("/campaigns");
    } catch (e: any) {
      console.error(e.message ?? String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="border-b border-slate-200 bg-white px-4 sm:px-6 py-4 flex items-center justify-between shrink-0">
        <div>
          <h1 className="text-lg font-semibold text-slate-900">Evaluation Studio</h1>
          <p className="text-xs text-slate-500 mt-0.5 hidden sm:block">Choose a template · configure · launch — all in one view · <kbd className="bg-slate-100 px-1 rounded text-[10px] border border-slate-200">⌘K</kbd> to search</p>
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        <aside className="md:w-52 border-b md:border-b-0 md:border-r border-slate-200 bg-white shrink-0 overflow-x-auto md:overflow-y-auto">
          <div className="p-3"><TypePicker value={evalType} onChange={handleTypeChange} /></div>
        </aside>

        <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-6 bg-slate-50">
          <CommonFields
            name={form.name} description={form.description}
            maxSamples={form.max_samples} temperature={form.temperature}
            onChange={p => patch({
              name: p.name ?? form.name, description: p.description ?? form.description,
              max_samples: p.maxSamples ?? form.max_samples, temperature: p.temperature ?? form.temperature,
            })} />

          {benchLoading ? (
            <div className="flex items-center gap-2 text-sm text-slate-400"><Spinner size={14} />Loading benchmarks…</div>
          ) : (
            <>
              {evalType === "safety"      && <SafetyForm     form={form} benchmarks={benchmarks} onChange={patch} />}
              {evalType === "compliance"  && <ComplianceForm form={form} benchmarks={benchmarks} onChange={patch} />}
              {evalType === "capability"  && <GenericForm    form={form} benchmarks={benchmarks} onChange={patch} defaultBenchFilter="academic" />}
              {evalType === "behavioral"  && <GenericForm    form={form} benchmarks={benchmarks} onChange={patch} defaultBenchFilter="safety" />}
              {evalType === "comparative" && <GenericForm    form={form} benchmarks={benchmarks} onChange={patch} multiModel />}
            </>
          )}

          {evalType === "safety" && (riskLoading || riskProfile?.system_threat_profile) && (
            <div className="bg-white border border-slate-200 rounded-xl p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-slate-900 text-sm">Compositional Threat Profile</h3>
                {riskLoading ? (
                  <span className="text-xs text-slate-400 flex items-center gap-1"><Spinner size={12} />Computing…</span>
                ) : (
                  <span className={`text-[11px] px-2 py-0.5 rounded border font-bold ${
                    riskProfile?.system_threat_profile?.overall_risk_level === "critical" ? "bg-red-100 text-red-700 border-red-200" :
                    riskProfile?.system_threat_profile?.overall_risk_level === "high" ? "bg-orange-100 text-orange-700 border-orange-200" :
                    "bg-green-100 text-green-700 border-green-200"
                  }`}>{(riskProfile?.system_threat_profile?.overall_risk_level ?? "low").toUpperCase()}</span>
                )}
              </div>
              {!riskLoading && riskProfile?.system_threat_profile && (
                <div className="grid grid-cols-3 gap-2 text-xs">
                  <div className="bg-slate-50 rounded-lg p-2"><div className="text-slate-400">Dominant vector</div><div className="font-medium">{riskProfile.system_threat_profile.dominant_threat_vector}</div></div>
                  <div className="bg-slate-50 rounded-lg p-2"><div className="text-slate-400">Composition ×</div><div className="font-medium">{riskProfile.system_threat_profile.composition_multiplier}x</div></div>
                  <div className="bg-slate-50 rounded-lg p-2"><div className="text-slate-400">Autonomy cert.</div><div className="font-medium">{riskProfile.system_threat_profile.autonomy_certification}</div></div>
                </div>
              )}
            </div>
          )}

          {!canLaunch && (form.model_ids.length > 0 || form.benchmark_ids.length > 0) && (
            <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 text-xs text-amber-700">
              ⚠️ {form.model_ids.length === 0 ? "Select at least one model." : "Select at least one benchmark."}
            </div>
          )}
          {needsMoreModels && (
            <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 text-xs text-amber-700">
              ⚠️ Comparative evaluation requires ≥ 2 models.
            </div>
          )}

          <div className="flex items-center gap-3 pt-2 pb-8">
            <button onClick={launch} disabled={saving || !canLaunch || needsMoreModels}
              className="flex items-center gap-2 bg-slate-900 text-white px-6 py-2.5 rounded-xl text-sm font-medium hover:bg-slate-700 disabled:opacity-40 transition-colors">
              {saving ? <Spinner size={14} /> : <Rocket size={14} />}
              {saving ? "Creating…" : "Launch evaluation"}
            </button>
            <label className="flex items-center gap-2 text-xs text-slate-500 cursor-pointer select-none">
              <input type="checkbox" checked={saveTemplate} onChange={e => setSaveTemplate(e.target.checked)} className="rounded border-slate-300" />
              <Save size={11} />Save as template
            </label>
          </div>
        </div>

        <aside className="hidden lg:block w-72 border-l border-slate-200 bg-white overflow-y-auto shrink-0 p-4">
          <PreviewPanel
            models={models} selectedModelIds={form.model_ids}
            numBenchmarks={form.benchmark_ids.length} maxSamples={form.max_samples}
            evalType={evalType} campaigns={campaigns}
            onClone={c => patch({
              name: `${c.name} (clone)`,
              model_ids: c.model_ids ?? [],
              benchmark_ids: c.benchmark_ids ?? [],
              max_samples: c.max_samples ?? 50,
              temperature: c.temperature ?? 0,
            })} />
        </aside>
      </div>
    </div>
  );
}

export default function EvaluationStudioPage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center h-full"><Spinner size={24} /></div>}>
      <EvalStudioInner />
    </Suspense>
  );
}
