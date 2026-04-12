"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { campaignsApi, modelsApi, benchmarksApi } from "@/lib/api";
import { API_BASE } from "@/lib/config";
import { Spinner } from "@/components/Spinner";
import { AppErrorBoundary } from "@/components/AppErrorBoundary";
import { Check, ChevronRight, ChevronLeft, Cpu, Wrench, Brain, Globe, Settings, Rocket } from "lucide-react";
import type { LLMModel, LLMModelSlim, Benchmark } from "@/lib/api";

/**
 * System-in-context evaluation wizard.
 *
 * Aligned with INESIA doctrine: evaluation starts with the SYSTEM, not the model.
 * Primitive: system → scenario → trajectory → risk signals → confidence
 */

type AutonomyLevel = "L1" | "L2" | "L3" | "L4" | "L5";

const AUTONOMY_LEVELS: Record<AutonomyLevel, { label: string; desc: string; color: string }> = {
  L1: { label: "L1 — No autonomy",    desc: "Human approves every action",           color: "bg-green-100 text-green-700 border-green-200" },
  L2: { label: "L2 — Supervised",     desc: "Human reviews outputs before acting",   color: "bg-blue-100 text-blue-700 border-blue-200" },
  L3: { label: "L3 — Conditional",    desc: "Human intervenes on exceptions only",   color: "bg-yellow-100 text-yellow-700 border-yellow-200" },
  L4: { label: "L4 — High autonomy",  desc: "Model acts independently on most tasks", color: "bg-orange-100 text-orange-700 border-orange-200" },
  L5: { label: "L5 — Full autonomy",  desc: "No human-in-the-loop",                 color: "bg-red-100 text-red-700 border-red-200" },
};

const RISK_DOMAINS = [
  { key: "cbrn",      label: "CBRN Uplift",        icon: "☢️", desc: "Chemical, biological, radiological, nuclear" },
  { key: "cyber",     label: "Cyber Uplift",        icon: "💻", desc: "Offensive cyber, attack planning" },
  { key: "fimi",      label: "Info Warfare",        icon: "📡", desc: "Disinformation, influence operations" },
  { key: "agentic",   label: "Agentic Failures",    icon: "🤖", desc: "Prompt injection, goal drift, inter-agent trust" },
  { key: "alignment", label: "Alignment",           icon: "🧭", desc: "Scheming, sandbagging, sycophancy, shutdown resistance" },
  { key: "safety",    label: "General Safety",      icon: "🛡", desc: "Refusal calibration, harmful content" },
];

const TOOL_OPTIONS = [
  "Web search", "Code execution", "File system", "Email/calendar", "Database",
  "External APIs", "Browser automation", "Memory (long-term)", "Sub-agent spawning",
];

const STEPS = ["System", "Risk Domains", "Parameters", "Review & Launch"];

function StepDot({ i, current }: { i: number; current: number }) {
  return (
    <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-medium transition-colors ${
      i < current ? "bg-green-500 text-white" : i === current ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-400"
    }`}>
      {i < current ? <Check size={12} /> : i + 1}
    </div>
  );
}

function EvaluateWizard() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [models, setModels] = useState<LLMModelSlim[]>([]);
  const [benchmarks, setBenchmarks] = useState<Benchmark[]>([]);
  const [saving, setSaving] = useState(false);

  const [system, setSystem] = useState({
    name: "",
    modelId: null as number | null,
    autonomyLevel: "L2" as AutonomyLevel,
    tools: [] as string[],
    hasMemory: false,
    hasOrchestration: false,
    deploymentContext: "",
  });

  const [selectedDomains, setSelectedDomains] = useState<string[]>([]);
  const [selectedBenchmarkIds, setSelectedBenchmarkIds] = useState<number[]>([]);
  const [maxSamples, setMaxSamples] = useState(20);
  const [temperature, setTemperature] = useState(0.0);
  const [riskProfile, setRiskProfile] = useState<any | null>(null);
  const [riskLoading, setRiskLoading] = useState(false);
  const selectedModel = models.find(m => m.id === system.modelId);

  useEffect(() => {
    modelsApi.list().then(setModels).catch(() => {});
    benchmarksApi.list().then(setBenchmarks).catch(() => {});
  }, []);

  useEffect(() => {
    const domainMap: Record<string, string[]> = {
      cbrn:      ["cbrn", "chemical", "biological", "radiological", "nuclear", "explosives"],
      cyber:     ["ckb", "cyber", "mitre", "attack"],
      fimi:      ["fimi", "disarm", "information"],
      agentic:   ["agentic", "autonomy", "failure mode"],
      alignment: ["scheming", "sycophancy", "shutdown", "sandbagging", "persuasion"],
      safety:    ["refusals", "harmbench", "wildguard", "salad"],
    };
    const autoIds: number[] = [];
    for (const domain of selectedDomains) {
      const kws = domainMap[domain] ?? [];
      benchmarks.forEach(b => {
        const haystack = (b.name + " " + (b.tags ?? []).join(" ")).toLowerCase();
        if (kws.some(k => haystack.includes(k)) && !autoIds.includes(b.id)) {
          autoIds.push(b.id);
        }
      });
    }
    setSelectedBenchmarkIds(autoIds);
  }, [selectedDomains, benchmarks]);

  useEffect(() => {
    if (step !== 3 || !system.modelId || selectedDomains.length === 0) {
      setRiskProfile(null);
      return;
    }

    const domainScores: Record<string, number> = {};
    if (selectedDomains.includes("cbrn")) domainScores.cbrn = 0.55;
    if (selectedDomains.includes("cyber")) domainScores.cyber = 0.55;
    if (selectedDomains.includes("fimi")) domainScores.persuasion = 0.5;
    if (selectedDomains.includes("agentic")) {
      domainScores.goal_drift = 0.5;
      domainScores.scope_creep = 0.45;
      domainScores.error_compounding = 0.45;
    }
    if (selectedDomains.includes("alignment")) {
      domainScores.scheming = 0.5;
      domainScores.shutdown_resistance = 0.45;
      domainScores.sycophancy = 0.4;
    }
    if (selectedDomains.includes("safety")) domainScores.safety_refusal = 0.45;
    if (system.hasOrchestration) domainScores.inter_agent_trust = Math.max(domainScores.inter_agent_trust ?? 0, 0.5);

    const propensityScores: Record<string, number> = {};
    if (selectedDomains.includes("alignment")) propensityScores.scheming = 0.4;
    if (selectedDomains.includes("fimi")) propensityScores.persuasion = 0.4;

    const toolMap: Record<string, string> = {
      "Web search": "web_search",
      "Code execution": "code_execution",
      "File system": "file_system",
      "Email/calendar": "email",
      "Database": "database",
      "External APIs": "external_apis",
      "Browser automation": "browser",
    };
    const tools = system.tools.map(t => toolMap[t]).filter(Boolean);

    setRiskLoading(true);
    fetch(`${API_BASE}/science/compositional-risk`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model_name: selectedModel?.name ?? "system",
        domain_scores: domainScores,
        propensity_scores: propensityScores,
        autonomy_level: system.autonomyLevel,
        tools,
        memory_type: system.hasMemory ? "persistent" : "session",
      }),
    })
      .then(async (res) => (res.ok ? res.json() : null))
      .then((json) => setRiskProfile(json))
      .catch(() => setRiskProfile(null))
      .finally(() => setRiskLoading(false));
  }, [
    step,
    system.modelId,
    system.autonomyLevel,
    system.tools,
    system.hasMemory,
    system.hasOrchestration,
    selectedDomains,
    selectedModel?.name,
  ]);

  const launch = async () => {
    if (!system.modelId || selectedBenchmarkIds.length === 0) return;
    setSaving(true);
    try {
      const campaign = await campaignsApi.create({
        name: system.name || `${selectedModel?.name ?? "Model"} · L${system.autonomyLevel} · ${selectedDomains.join("+")}`,
        description: [
          "System-in-context evaluation (INESIA doctrine).",
          `Autonomy: ${system.autonomyLevel}`,
          system.tools.length ? `Tools: ${system.tools.join(", ")}` : "",
          system.deploymentContext ? `Context: ${system.deploymentContext}` : "",
          system.hasMemory ? "Memory: enabled" : "",
          system.hasOrchestration ? "Orchestration: multi-agent" : "",
          `Risk domains: ${selectedDomains.join(", ")}`,
        ].filter(Boolean).join(" | "),
        model_ids: [system.modelId],
        benchmark_ids: selectedBenchmarkIds,
        max_samples: maxSamples,
        temperature,
      });
      router.push(`/campaigns`);
    } catch (e: any) {
      alert(e.message ?? String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto p-4 sm:p-8">
      <div className="mb-8">
        <h1 className="text-xl font-bold text-slate-900">New System Evaluation</h1>
        <p className="text-sm text-slate-500 mt-1">
          System-in-context evaluation — define the system context before choosing benchmarks.
        </p>
      </div>

      {/* Steps */}
      <div className="flex items-center gap-3 mb-8 flex-wrap">
        {STEPS.map((label, i) => (
          <div key={label} className="flex items-center gap-2">
            <StepDot i={i} current={step} />
            <span className={`text-sm ${i === step ? "font-medium text-slate-900" : "text-slate-400"}`}>{label}</span>
            {i < STEPS.length - 1 && <ChevronRight size={14} className="text-slate-200 mx-1" />}
          </div>
        ))}
      </div>

      {/* Step 0 — System */}
      {step === 0 && (
        <div className="space-y-6">
          <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-xs text-blue-700">
            <span className="font-semibold">INESIA doctrine:</span> Evaluate the <em>system-in-context</em>, not the model in isolation.
            The risk profile changes as a function of tools, autonomy level, and deployment context.
          </div>

          <div>
            <label className="text-xs font-medium text-slate-600 mb-1 block">Evaluation name (optional)</label>
            <input value={system.name} onChange={e => setSystem(s => ({ ...s, name: e.target.value }))}
              placeholder="e.g. Claude Sonnet — Customer support agent — Q2 2026"
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900" />
          </div>

          <div>
            <label className="text-xs font-medium text-slate-600 mb-2 block">
              <Cpu size={11} className="inline mr-1" />Model under evaluation
            </label>
            <div className="grid grid-cols-2 gap-2 max-h-52 overflow-y-auto pr-1">
              {models.map(m => (
                <button key={m.id} onClick={() => setSystem(s => ({ ...s, modelId: m.id }))}
                  className={`text-left p-3 rounded-lg border text-xs transition-colors ${
                    system.modelId === m.id ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 hover:border-slate-300 hover:bg-slate-50"
                  }`}>
                  <div className="font-medium truncate">{m.name}</div>
                  <div className={`text-[10px] mt-0.5 ${system.modelId === m.id ? "text-slate-300" : "text-slate-400"}`}>{m.provider}</div>
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="text-xs font-medium text-slate-600 mb-2 block">
              <Settings size={11} className="inline mr-1" />Autonomy level
            </label>
            <div className="space-y-2">
              {(Object.entries(AUTONOMY_LEVELS) as [AutonomyLevel, any][]).map(([level, cfg]) => (
                <button key={level} onClick={() => setSystem(s => ({ ...s, autonomyLevel: level }))}
                  className={`w-full text-left flex items-center gap-3 px-4 py-3 rounded-xl border transition-colors ${
                    system.autonomyLevel === level ? `${cfg.color} border-current` : "border-slate-200 hover:bg-slate-50"
                  }`}>
                  <span className="font-mono text-xs font-bold w-6">{level}</span>
                  <div>
                    <div className="text-xs font-semibold">{cfg.label.split(" — ")[1]}</div>
                    <div className="text-[10px] text-slate-500">{cfg.desc}</div>
                  </div>
                  {system.autonomyLevel === level && <Check size={13} className="ml-auto shrink-0" />}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="text-xs font-medium text-slate-600 mb-2 block">
              <Wrench size={11} className="inline mr-1" />Tools granted to the system
            </label>
            <div className="flex flex-wrap gap-2">
              {TOOL_OPTIONS.map(t => (
                <button key={t} onClick={() => setSystem(s => ({
                  ...s, tools: s.tools.includes(t) ? s.tools.filter(x => x !== t) : [...s.tools, t]
                }))}
                  className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
                    system.tools.includes(t) ? "bg-slate-900 text-white border-slate-900" : "border-slate-200 text-slate-600 hover:bg-slate-50"
                  }`}>
                  {t}
                </button>
              ))}
            </div>
          </div>

          <div className="flex gap-3">
            {[
              { key: "hasMemory", label: "Long-term memory", icon: Brain },
              { key: "hasOrchestration", label: "Multi-agent orchestration", icon: Globe },
            ].map(({ key, label, icon: Icon }) => (
              <button key={key} onClick={() => setSystem(s => ({ ...s, [key]: !(s as any)[key] }))}
                className={`flex-1 flex items-center gap-2 px-4 py-3 rounded-xl border text-xs transition-colors ${
                  (system as any)[key] ? "bg-slate-900 text-white border-slate-900" : "border-slate-200 text-slate-600 hover:bg-slate-50"
                }`}>
                <Icon size={13} /> {label}
                {(system as any)[key] && <Check size={12} className="ml-auto" />}
              </button>
            ))}
          </div>

          <div>
            <label className="text-xs font-medium text-slate-600 mb-1 block">
              <Globe size={11} className="inline mr-1" />Deployment context
            </label>
            <input value={system.deploymentContext}
              onChange={e => setSystem(s => ({ ...s, deploymentContext: e.target.value }))}
              placeholder="e.g. Customer support chatbot, medical triage assistant, autonomous coding agent…"
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900" />
          </div>
        </div>
      )}

      {/* Step 1 — Risk domains */}
      {step === 1 && (
        <div className="space-y-4">
          <p className="text-sm text-slate-600">Select risk domains to evaluate. Benchmarks auto-select based on your choices.</p>
          {(system.autonomyLevel === "L4" || system.autonomyLevel === "L5") && (
            <div className="bg-red-50 border border-red-200 rounded-xl p-3 text-xs text-red-700">
              ⚠️ Autonomy level {system.autonomyLevel} — agentic failure modes are <strong>strongly recommended</strong> per INESIA doctrine.
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            {RISK_DOMAINS.map(({ key, label, icon, desc }) => (
              <button key={key} onClick={() => setSelectedDomains(d =>
                d.includes(key) ? d.filter(x => x !== key) : [...d, key]
              )}
                className={`text-left p-4 rounded-xl border transition-colors ${
                  selectedDomains.includes(key) ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 hover:border-slate-300 hover:bg-slate-50"
                }`}>
                <div className="text-2xl mb-1">{icon}</div>
                <div className="text-sm font-medium">{label}</div>
                <div className={`text-xs mt-0.5 ${selectedDomains.includes(key) ? "text-slate-300" : "text-slate-400"}`}>{desc}</div>
              </button>
            ))}
          </div>
          {selectedBenchmarkIds.length > 0 && (
            <div className="bg-green-50 border border-green-200 rounded-xl p-3 text-xs text-green-700">
              ✓ {selectedBenchmarkIds.length} benchmark{selectedBenchmarkIds.length !== 1 ? "s" : ""} auto-selected.
            </div>
          )}
        </div>
      )}

      {/* Step 2 — Parameters */}
      {step === 2 && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-medium text-slate-600 mb-1 block">Max samples per benchmark</label>
              <input type="number" value={maxSamples} onChange={e => setMaxSamples(+e.target.value)}
                min={5} max={500} step={5}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" />
              <p className="text-[10px] text-slate-400 mt-1">≥50 samples recommended for grade A reliability.</p>
            </div>
            <div>
              <label className="text-xs font-medium text-slate-600 mb-1 block">Temperature</label>
              <input type="number" value={temperature} onChange={e => setTemperature(+e.target.value)}
                min={0} max={2} step={0.1}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" />
              <p className="text-[10px] text-slate-400 mt-1">0.0 = deterministic (recommended for safety evals)</p>
            </div>
          </div>
        </div>
      )}

      {/* Step 3 — Review */}
      {step === 3 && (
        <div className="space-y-4">
          <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-4 text-xs">
            <h3 className="font-semibold text-slate-900 text-sm">System</h3>
            <div className="grid grid-cols-2 gap-2">
              <div className="bg-slate-50 rounded-lg p-2"><div className="text-slate-400 mb-0.5">Model</div><div className="font-medium">{selectedModel?.name ?? "—"}</div></div>
              <div className="bg-slate-50 rounded-lg p-2"><div className="text-slate-400 mb-0.5">Autonomy</div><div className="font-medium">{system.autonomyLevel}</div></div>
              <div className="bg-slate-50 rounded-lg p-2 col-span-2"><div className="text-slate-400 mb-0.5">Tools ({system.tools.length})</div><div className="font-medium">{system.tools.join(", ") || "None"}</div></div>
              {system.deploymentContext && <div className="bg-slate-50 rounded-lg p-2 col-span-2"><div className="text-slate-400 mb-0.5">Context</div><div className="font-medium">{system.deploymentContext}</div></div>}
            </div>
            <h3 className="font-semibold text-slate-900 text-sm pt-1">Evaluation</h3>
            <div className="grid grid-cols-3 gap-2">
              <div className="bg-slate-50 rounded-lg p-2"><div className="text-slate-400 mb-0.5">Risk domains</div><div className="font-medium">{selectedDomains.length}</div></div>
              <div className="bg-slate-50 rounded-lg p-2"><div className="text-slate-400 mb-0.5">Benchmarks</div><div className="font-medium">{selectedBenchmarkIds.length}</div></div>
              <div className="bg-slate-50 rounded-lg p-2"><div className="text-slate-400 mb-0.5">Max samples</div><div className="font-medium">{maxSamples}</div></div>
            </div>
          </div>
          {(!system.modelId || selectedBenchmarkIds.length === 0) && (
            <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 text-xs text-amber-700">
              ⚠️ {!system.modelId ? "Select a model in Step 1." : "Select at least one risk domain in Step 2."}
            </div>
          )}

          {(riskLoading || riskProfile?.system_threat_profile) && (
            <div className="bg-white border border-slate-200 rounded-xl p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-slate-900 text-sm">Compositional Threat Profile</h3>
                {riskLoading ? (
                  <span className="text-xs text-slate-400">Computing…</span>
                ) : (
                  <span className={`text-[11px] px-2 py-0.5 rounded border font-bold ${
                    riskProfile?.system_threat_profile?.overall_risk_level === "critical" ? "bg-red-100 text-red-700 border-red-200" :
                    riskProfile?.system_threat_profile?.overall_risk_level === "high" ? "bg-orange-100 text-orange-700 border-orange-200" :
                    "bg-green-100 text-green-700 border-green-200"
                  }`}>
                    {(riskProfile?.system_threat_profile?.overall_risk_level ?? "low").toUpperCase()}
                  </span>
                )}
              </div>
              {!riskLoading && riskProfile?.system_threat_profile && (
                <div className="grid grid-cols-3 gap-2 text-xs">
                  <div className="bg-slate-50 rounded-lg p-2">
                    <div className="text-slate-400">Dominant vector</div>
                    <div className="font-medium text-slate-800">{riskProfile.system_threat_profile.dominant_threat_vector}</div>
                  </div>
                  <div className="bg-slate-50 rounded-lg p-2">
                    <div className="text-slate-400">Composition ×</div>
                    <div className="font-medium text-slate-800">{riskProfile.system_threat_profile.composition_multiplier}x</div>
                  </div>
                  <div className="bg-slate-50 rounded-lg p-2">
                    <div className="text-slate-400">Autonomy certification</div>
                    <div className="font-medium text-slate-800">{riskProfile.system_threat_profile.autonomy_certification}</div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Navigation */}
      <div className="flex items-center justify-between mt-8 pt-6 border-t border-slate-100">
        <button onClick={() => setStep(s => Math.max(0, s - 1))} disabled={step === 0}
          className="flex items-center gap-2 px-4 py-2 text-sm text-slate-600 disabled:opacity-30 hover:text-slate-900">
          <ChevronLeft size={14} /> Back
        </button>
        {step < 3 ? (
          <button onClick={() => setStep(s => s + 1)}
            disabled={step === 0 && !system.modelId}
            className="flex items-center gap-2 bg-slate-900 text-white px-6 py-2.5 rounded-lg text-sm hover:bg-slate-700 disabled:opacity-40">
            Next <ChevronRight size={14} />
          </button>
        ) : (
          <button onClick={launch}
            disabled={saving || !system.modelId || selectedBenchmarkIds.length === 0}
            className="flex items-center gap-2 bg-green-700 text-white px-6 py-2.5 rounded-lg text-sm hover:bg-green-600 disabled:opacity-40">
            {saving ? <Spinner size={13} /> : <Rocket size={14} />}
            {saving ? "Creating…" : "Launch evaluation"}
          </button>
        )}
      </div>
    </div>
  );
}

export default function EvaluatePage() {
  return <AppErrorBoundary><EvaluateWizard /></AppErrorBoundary>;
}
