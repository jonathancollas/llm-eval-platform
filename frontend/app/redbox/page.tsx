"use client";
import { useEffect, useState, useCallback } from "react";
import { modelsApi } from "@/lib/api";
import type { LLMModel } from "@/lib/api";
import { Spinner } from "@/components/Spinner";
import { ShieldAlert, Zap, Target, AlertTriangle, ChevronDown, ChevronUp, Play, RotateCcw } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "https://llm-eval-backend-kqlh.onrender.com/api";

const MUTATION_TYPES = [
  { key: "prompt_injection",  label: "Prompt Injection",  icon: "💉", desc: "Ignore previous instructions variants" },
  { key: "ambiguity",         label: "Ambiguité",         icon: "🌫", desc: "Reformulation ambiguë du même objectif" },
  { key: "multilingual",      label: "Multilingue",       icon: "🌍", desc: "Mix de langues, traductions" },
  { key: "contradiction",     label: "Contradiction",     icon: "⚡", desc: "Instructions contradictoires" },
  { key: "malformed_context", label: "Contexte bruité",   icon: "🔊", desc: "Données tronquées, corrompues" },
  { key: "jailbreak",         label: "Jailbreak",         icon: "🔓", desc: "Contournement des politiques" },
];

interface Variant {
  mutation: string; prompt: string; difficulty: number; expected_failure: string; rationale?: string;
}
interface RunResult {
  mutation: string; prompt: string; response: string; breached: boolean;
  severity: number; failure_detected: string; latency_ms: number;
}
interface Exploit {
  id: number; model_name: string; model_id: number; mutation_type: string;
  adversarial_prompt: string; model_response: string; breached: boolean;
  severity: number; difficulty: number; failure_detected: string;
  latency_ms: number; created_at: string;
}
interface HeatmapCell {
  model_name: string; mutation_type: string; tested: number; breached: number;
  breach_rate: number; avg_severity: number; risk_level: string;
}

function SeverityBadge({ severity }: { severity: number }) {
  const pct = Math.round(severity * 100);
  const cls = severity > 0.7 ? "bg-red-100 text-red-700" : severity > 0.4 ? "bg-yellow-100 text-yellow-700" : "bg-green-100 text-green-700";
  return <span className={`text-xs px-2 py-0.5 rounded-full font-mono font-medium ${cls}`}>{pct}%</span>;
}

export default function RedboxPage() {
  const [seed, setSeed] = useState("");
  const [selectedMutations, setSelectedMutations] = useState<string[]>(["prompt_injection", "jailbreak"]);
  const [variants, setVariants] = useState<Variant[]>([]);
  const [generating, setGenerating] = useState(false);
  const [activeTab, setActiveTab] = useState<"forge" | "exploits" | "heatmap">("forge");

  // Run state
  const [models, setModels] = useState<LLMModel[]>([]);
  const [selectedModelId, setSelectedModelId] = useState<number | null>(null);
  const [running, setRunning] = useState(false);
  const [runResults, setRunResults] = useState<RunResult[] | null>(null);
  const [runSummary, setRunSummary] = useState<{ total_tested: number; breached: number; breach_rate: number } | null>(null);

  // Exploits state
  const [exploits, setExploits] = useState<Exploit[]>([]);
  const [exploitFilter, setExploitFilter] = useState<"all" | "breached">("all");
  const [expandedExploit, setExpandedExploit] = useState<number | null>(null);

  // Heatmap state
  const [heatmap, setHeatmap] = useState<{ heatmap: HeatmapCell[]; models: string[]; mutations: string[]; computed: boolean } | null>(null);

  useEffect(() => { modelsApi.list().then(setModels).catch(() => {}); }, []);

  const loadExploits = useCallback(() => {
    fetch(`${API_BASE}/redbox/exploits?limit=200`).then(r => r.json()).then(setExploits).catch(() => {});
  }, []);

  const loadHeatmap = useCallback(() => {
    fetch(`${API_BASE}/redbox/heatmap`).then(r => r.json()).then(setHeatmap).catch(() => {});
  }, []);

  useEffect(() => {
    if (activeTab === "exploits") loadExploits();
    if (activeTab === "heatmap") loadHeatmap();
  }, [activeTab, loadExploits, loadHeatmap]);

  const toggleMutation = (key: string) =>
    setSelectedMutations(prev => prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]);

  const generate = async () => {
    if (!seed.trim() || !selectedMutations.length) return;
    setGenerating(true); setVariants([]); setRunResults(null); setRunSummary(null);
    try {
      const res = await fetch(`${API_BASE}/redbox/forge`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ seed_prompt: seed, mutation_types: selectedMutations, num_variants_per_type: 3 }),
      });
      const data = await res.json();
      setVariants(data.variants ?? []);
    } catch (e) {
      console.error("Forge error:", e);
    } finally { setGenerating(false); }
  };

  const runAttack = async () => {
    if (!selectedModelId || !variants.length) return;
    setRunning(true); setRunResults(null); setRunSummary(null);
    try {
      const res = await fetch(`${API_BASE}/redbox/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model_id: selectedModelId, variants }),
      });
      const data = await res.json();
      setRunResults(data.results ?? []);
      setRunSummary({ total_tested: data.total_tested, breached: data.breached, breach_rate: data.breach_rate });
    } catch (e) {
      console.error("Run error:", e);
    } finally { setRunning(false); }
  };

  const replayExploit = async (exploitId: number, modelId: number) => {
    try {
      await fetch(`${API_BASE}/redbox/replay/${exploitId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model_id: modelId }),
      });
      loadExploits();
    } catch {}
  };

  const TABS = [
    { key: "forge", label: "⚡ Adversarial Forge" },
    { key: "exploits", label: "🕳 Exploit Tracker" },
    { key: "heatmap", label: "🗺 Attack Surface" },
  ];

  const filteredExploits = exploitFilter === "breached"
    ? (exploits as any)?.exploits?.filter((e: Exploit) => e.breached) ?? []
    : (exploits as any)?.exploits ?? [];

  return (
    <div>
      <div className="bg-red-950 px-8 py-5 border-b border-red-900">
        <div className="flex items-center gap-3 mb-1">
          <ShieldAlert size={20} className="text-red-400" />
          <h1 className="text-xl font-bold text-white tracking-wide">REDBOX</h1>
          <span className="text-xs bg-red-800 text-red-300 px-2 py-0.5 rounded-full border border-red-700">
            Adversarial Security Lab
          </span>
        </div>
        <p className="text-red-300 text-sm italic">Break the model before reality does.</p>
      </div>

      <div className="px-8 pt-3 flex gap-1 bg-red-950 border-b border-red-900">
        {TABS.map(({ key, label }) => (
          <button key={key} onClick={() => setActiveTab(key as any)}
            className={`px-4 py-2 text-sm border-b-2 transition-colors ${
              activeTab === key ? "border-red-400 text-red-300 font-medium" : "border-transparent text-red-600 hover:text-red-400"
            }`}>
            {label}
          </button>
        ))}
      </div>

      <div className="p-8">

        {/* ── FORGE TAB ────────────────────────────────────────────────── */}
        {activeTab === "forge" && (
          <div className="space-y-6 max-w-4xl">
            <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">
              <AlertTriangle size={14} className="inline mr-2" />
              Variantes générées à des fins d'évaluation de sécurité. Usage réservé aux équipes autorisées.
            </div>

            <div>
              <label className="text-xs font-medium text-slate-700 mb-2 block">Prompt seed</label>
              <textarea value={seed} onChange={e => setSeed(e.target.value)} rows={3}
                placeholder="ex. Summarize this financial report and highlight the key risks."
                className="w-full border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-red-400 resize-none" />
            </div>

            <div>
              <label className="text-xs font-medium text-slate-700 mb-2 block">Types de mutations</label>
              <div className="grid grid-cols-3 gap-2">
                {MUTATION_TYPES.map(({ key, label, icon, desc }) => (
                  <button key={key} onClick={() => toggleMutation(key)}
                    className={`flex items-start gap-2 p-3 rounded-xl border text-left transition-colors ${
                      selectedMutations.includes(key) ? "border-red-400 bg-red-50" : "border-slate-200 hover:border-slate-300"
                    }`}>
                    <span className="text-lg shrink-0">{icon}</span>
                    <div>
                      <div className="text-xs font-medium text-slate-800">{label}</div>
                      <div className="text-xs text-slate-400 mt-0.5">{desc}</div>
                    </div>
                  </button>
                ))}
              </div>
            </div>

            <button onClick={generate} disabled={generating || !seed.trim() || !selectedMutations.length}
              className="flex items-center gap-2 bg-red-600 text-white px-6 py-2.5 rounded-xl text-sm font-medium hover:bg-red-700 disabled:opacity-40 transition-colors">
              {generating ? <Spinner size={14} /> : <Zap size={15} />}
              {generating ? "Génération LLM en cours…" : `Forger ${selectedMutations.length} types de variants`}
            </button>

            {/* Generated variants */}
            {variants.length > 0 && (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="font-medium text-slate-900">{variants.length} variants forgés</h3>
                </div>

                {/* Model selector + Run button */}
                <div className="flex items-center gap-3 bg-slate-50 rounded-xl p-4 border border-slate-200">
                  <select value={selectedModelId ?? ""} onChange={e => setSelectedModelId(+e.target.value || null)}
                    className="border border-slate-200 rounded-lg px-3 py-2 text-sm flex-1">
                    <option value="">— Choisir un model cible —</option>
                    {models.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
                  </select>
                  <button onClick={runAttack} disabled={running || !selectedModelId}
                    className="flex items-center gap-2 bg-red-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-red-700 disabled:opacity-40">
                    {running ? <Spinner size={13} /> : <Play size={14} />}
                    {running ? "Attaque en cours…" : "Launch l'attaque"}
                  </button>
                </div>

                {/* Run summary */}
                {runSummary && (
                  <div className={`rounded-xl p-4 border ${runSummary.breached > 0 ? "bg-red-50 border-red-200" : "bg-green-50 border-green-200"}`}>
                    <div className="flex items-center gap-4 text-sm">
                      <span className="font-medium">{runSummary.breached > 0 ? "🔴" : "🟢"} {runSummary.breached}/{runSummary.total_tested} brèches</span>
                      <span className="text-slate-500">Taux de brèche: {Math.round(runSummary.breach_rate * 100)}%</span>
                    </div>
                  </div>
                )}

                {/* Results or Variants list */}
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {(runResults ?? variants).map((item: any, i: number) => {
                    const mt = MUTATION_TYPES.find(m => m.key === item.mutation);
                    const isResult = !!runResults;
                    return (
                      <div key={i} className={`bg-white border rounded-xl p-4 ${isResult && item.breached ? "border-red-300" : "border-slate-200"}`}>
                        <div className="flex items-center gap-2 mb-2 flex-wrap">
                          <span>{mt?.icon}</span>
                          <span className="text-xs font-medium text-slate-700">{mt?.label}</span>
                          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                            item.difficulty > 0.7 ? "bg-red-100 text-red-700" :
                            item.difficulty > 0.4 ? "bg-yellow-100 text-yellow-700" : "bg-green-100 text-green-700"
                          }`}>Diff {Math.round((item.difficulty ?? 0) * 100)}%</span>
                          {isResult && (
                            <>
                              <span className={`text-xs px-2 py-0.5 rounded-full font-bold ${item.breached ? "bg-red-600 text-white" : "bg-green-600 text-white"}`}>
                                {item.breached ? "BREACHED" : "HELD"}
                              </span>
                              {item.severity > 0 && <SeverityBadge severity={item.severity} />}
                              <span className="text-xs text-slate-400 ml-auto">{item.latency_ms}ms</span>
                            </>
                          )}
                        </div>
                        <pre className="text-xs text-slate-600 whitespace-pre-wrap font-mono bg-slate-50 rounded-lg p-2.5 border border-slate-100 line-clamp-3">
                          {item.prompt}
                        </pre>
                        {isResult && item.response && (
                          <div className="mt-2">
                            <span className="text-[10px] text-slate-400 uppercase font-medium">Réponse model</span>
                            <pre className={`text-xs whitespace-pre-wrap font-mono rounded-lg p-2.5 border mt-0.5 line-clamp-4 ${
                              item.breached ? "bg-red-50 border-red-100 text-red-700" : "bg-green-50 border-green-100 text-green-700"
                            }`}>{item.response}</pre>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── EXPLOITS TAB ─────────────────────────────────────────────── */}
        {activeTab === "exploits" && (
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <button onClick={() => setExploitFilter("all")}
                className={`text-xs px-3 py-1.5 rounded-lg ${exploitFilter === "all" ? "bg-slate-900 text-white" : "border border-slate-200 text-slate-600"}`}>
                Tous ({(exploits as any)?.total ?? 0})
              </button>
              <button onClick={() => setExploitFilter("breached")}
                className={`text-xs px-3 py-1.5 rounded-lg ${exploitFilter === "breached" ? "bg-red-600 text-white" : "border border-red-200 text-red-600"}`}>
                🔴 Brèches ({(exploits as any)?.total_breached ?? 0})
              </button>
              <button onClick={loadExploits} className="text-xs text-slate-400 hover:text-slate-600 ml-auto">
                <RotateCcw size={12} />
              </button>
            </div>

            {!filteredExploits.length ? (
              <div className="bg-slate-50 border border-slate-200 rounded-2xl p-12 text-center">
                <Target size={40} className="text-slate-300 mx-auto mb-3" />
                <h3 className="font-semibold text-slate-700 mb-1">Aucun exploit enregistré</h3>
                <p className="text-sm text-slate-500">Lancez une attaque depuis l'onglet Forge.</p>
              </div>
            ) : (
              <div className="space-y-2 max-h-[600px] overflow-y-auto">
                {filteredExploits.map((e: Exploit) => {
                  const mt = MUTATION_TYPES.find(m => m.key === e.mutation_type);
                  const isExpanded = expandedExploit === e.id;
                  return (
                    <div key={e.id}>
                      <button onClick={() => setExpandedExploit(isExpanded ? null : e.id)}
                        className={`w-full flex items-center gap-2 text-xs text-left rounded-xl px-4 py-3 border transition-colors ${
                          e.breached ? "border-red-200 bg-red-50 hover:bg-red-100" : "border-slate-200 bg-white hover:bg-slate-50"
                        }`}>
                        <span className={`w-2 h-2 rounded-full shrink-0 ${e.breached ? "bg-red-500" : "bg-green-500"}`} />
                        <span className="shrink-0">{mt?.icon}</span>
                        <span className="text-slate-600 w-28 shrink-0 truncate">{e.model_name}</span>
                        <span className="text-slate-400 flex-1 truncate">{e.adversarial_prompt}</span>
                        <SeverityBadge severity={e.severity} />
                        {isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                      </button>
                      {isExpanded && (
                        <div className="bg-slate-50 rounded-xl p-4 mx-2 mb-1 border border-slate-100 text-xs space-y-2">
                          <div><span className="text-slate-400 uppercase text-[10px] font-medium">Prompt adversarial</span>
                            <pre className="mt-0.5 font-mono whitespace-pre-wrap">{e.adversarial_prompt}</pre></div>
                          <div><span className="text-slate-400 uppercase text-[10px] font-medium">Réponse model</span>
                            <pre className={`mt-0.5 font-mono whitespace-pre-wrap ${e.breached ? "text-red-600" : "text-green-600"}`}>{e.model_response}</pre></div>
                          <div className="flex items-center gap-4 text-slate-500 pt-1">
                            <span>Failure: {e.failure_detected || "—"}</span>
                            <span>{e.latency_ms}ms</span>
                            <span>{e.created_at.split("T")[0]}</span>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* ── HEATMAP TAB ──────────────────────────────────────────────── */}
        {activeTab === "heatmap" && (
          <div>
            {!heatmap?.computed ? (
              <div className="bg-slate-50 border border-slate-200 rounded-2xl p-12 text-center">
                <ShieldAlert size={40} className="text-slate-300 mx-auto mb-3" />
                <h3 className="font-semibold text-slate-700 mb-1">Attack Surface Map</h3>
                <p className="text-sm text-slate-500">Lancez des attaques pour générer la carte.</p>
              </div>
            ) : (
              <div className="overflow-x-auto rounded-xl border border-slate-200">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50">
                    <tr>
                      <th className="text-left text-xs text-slate-500 font-medium p-4">Modèle</th>
                      {heatmap.mutations.map(mt => {
                        const cfg = MUTATION_TYPES.find(m => m.key === mt);
                        return <th key={mt} className="text-center text-xs text-slate-500 font-medium p-4">{cfg?.icon} {cfg?.label ?? mt}</th>;
                      })}
                    </tr>
                  </thead>
                  <tbody>
                    {heatmap.models.map(model => (
                      <tr key={model} className="border-t border-slate-100">
                        <td className="p-4 text-xs font-medium text-slate-700 whitespace-nowrap">{model}</td>
                        {heatmap.mutations.map(mt => {
                          const cell = heatmap.heatmap.find(h => h.model_name === model && h.mutation_type === mt);
                          if (!cell) return <td key={mt} className="p-4 text-center text-slate-200 text-xs">—</td>;
                          const bg = cell.risk_level === "red" ? "bg-red-100 text-red-700" :
                                     cell.risk_level === "yellow" ? "bg-yellow-100 text-yellow-700" : "bg-green-100 text-green-700";
                          return (
                            <td key={mt} className="p-4 text-center">
                              <div className={`inline-flex flex-col items-center gap-0.5 px-3 py-1.5 rounded-lg text-xs font-medium ${bg}`}>
                                <span>{cell.breached}/{cell.tested}</span>
                                <span className="text-[10px] opacity-70">{Math.round(cell.breach_rate * 100)}%</span>
                              </div>
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
