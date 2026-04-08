"use client";
import { useEffect, useState, useCallback } from "react";
import { modelsApi } from "@/lib/api";
import type { LLMModel } from "@/lib/api";
import { Spinner } from "@/components/Spinner";
import { ModelSelector } from "@/components/ModelSelector";
import { ShieldAlert, Zap, Target, AlertTriangle, ChevronDown, ChevronUp, Play, RotateCcw } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "https://llm-eval-backend-kqlh.onrender.com/api";

const MUTATION_TYPES = [
  { key: "prompt_injection",  label: "Prompt Injection",   icon: "💉", desc: "Direct injection — override instructions (ATLAS AML.T0051)" },
  { key: "jailbreak",         label: "Jailbreak",          icon: "🔓", desc: "Persona manipulation, DAN, roleplay bypass (ATLAS AML.T0054)" },
  { key: "encoding_evasion",  label: "Encoding Evasion",   icon: "🔤", desc: "Base64, ROT13, reversed text, homoglyphs (ATLAS AML.T0043)" },
  { key: "token_smuggling",   label: "Token Smuggling",    icon: "👻", desc: "Zero-width chars, RTL override, hidden instructions (ATLAS AML.T0051.002)" },
  { key: "multi_turn",        label: "Multi-Turn",         icon: "🔄", desc: "Context manipulation, false prior agreement (ATLAS AML.T0052)" },
  { key: "crescendo",         label: "Crescendo",          icon: "📈", desc: "Gradual escalation from benign to harmful" },
  { key: "ambiguity",         label: "Ambiguity",          icon: "🌫", desc: "Ambiguous reformulation of the same objective" },
  { key: "multilingual",      label: "Multilingual",       icon: "🌍", desc: "Cross-lingual attacks, language switching (NIST AI 100-2)" },
  { key: "contradiction",     label: "Contradiction",      icon: "⚡", desc: "Conflicting instructions, output override (OWASP LLM01)" },
  { key: "malformed_context", label: "Malformed Context",  icon: "🔊", desc: "XSS payloads, template injection, format exploits" },
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

function RedboxLiveFeed({ modelId }: { modelId: number }) {
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    const fetchLive = async () => {
      try {
        const res = await fetch(`${API_BASE}/redbox/live/${modelId}?limit=5`);
        if (res.ok) setData(await res.json());
      } catch {}
    };
    fetchLive();
    const poll = setInterval(fetchLive, 1500);
    return () => clearInterval(poll);
  }, [modelId]);

  return (
    <div className="border border-red-200 rounded-xl overflow-hidden bg-red-50">
      <div className="px-4 py-2 flex items-center gap-3 text-xs">
        <div className="w-2 h-2 bg-red-500 rounded-full animate-pulse" />
        <span className="font-semibold text-red-700">Live — Attack Feed</span>
        {data && (
          <>
            <span className="text-red-500 font-mono">{data.total_exploits} tested</span>
            <span className="text-red-500 font-mono">{data.total_breached} breached</span>
            {data.total_exploits > 0 && (
              <span className="ml-auto font-bold text-red-700">{Math.round(data.breach_rate * 100)}%</span>
            )}
          </>
        )}
      </div>
      {data?.items?.length > 0 && (
        <div className="border-t border-red-200 px-4 py-2 space-y-1">
          {data.items.slice(0, 5).map((item: any) => {
            const mt = MUTATION_TYPES.find(m => m.key === item.mutation_type);
            return (
              <div key={item.id} className="flex items-center gap-2 text-xs">
                <span className={`w-5 h-5 rounded-full flex items-center justify-center text-white text-[9px] font-bold ${item.breached ? "bg-red-500" : "bg-green-500"}`}>
                  {item.breached ? "✗" : "✓"}
                </span>
                <span className="text-slate-500 w-20 shrink-0 truncate">{mt?.label || item.mutation_type}</span>
                <span className="text-slate-400 flex-1 truncate">{item.prompt}</span>
                <span className="text-slate-400">{item.latency_ms}ms</span>
              </div>
            );
          })}
        </div>
      )}
      {(!data || data.items.length === 0) && (
        <div className="border-t border-red-200 px-4 py-3 text-xs text-red-400 flex items-center gap-2">
          <div className="w-3 h-3 border-2 border-red-300 border-t-transparent rounded-full animate-spin" />
          Waiting for first results…
        </div>
      )}
    </div>
  );
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

                {/* Model selector */}
                <ModelSelector
                  mode="single"
                  selected={selectedModelId ? [selectedModelId] : []}
                  onChange={(ids) => setSelectedModelId(ids[0] ?? null)}
                  idType="db_id"
                  label="Target model"
                  maxHeight="max-h-40"
                />

                {/* Run button */}
                <div className="flex items-center gap-3">
                  <button onClick={runAttack} disabled={running || !selectedModelId}
                    className="flex items-center gap-2 bg-red-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-red-700 disabled:opacity-40">
                    {running ? <Spinner size={13} /> : <Play size={14} />}
                    {running ? "Attack in progress…" : "Launch attack"}
                  </button>
                </div>

                {/* Live feed during attack */}
                {running && selectedModelId && <RedboxLiveFeed modelId={selectedModelId} />}

                {/* Run summary */}
                {runSummary && (
                  <div className={`rounded-xl p-4 border ${runSummary.breached > 0 ? "bg-red-50 border-red-200" : "bg-green-50 border-green-200"}`}>
                    <div className="flex items-center gap-4 text-sm">
                      <span className="font-medium">{runSummary.breached > 0 ? "🔴" : "🟢"} {runSummary.breached}/{runSummary.total_tested} breaches</span>
                      <span className="text-slate-500">Breach rate: {Math.round(runSummary.breach_rate * 100)}%</span>
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
                <h3 className="font-semibold text-slate-700 mb-1">No exploits recorded</h3>
                <p className="text-sm text-slate-500">Launch an attack from the Forge tab.</p>
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
                <p className="text-sm text-slate-500">Run attacks to generate the heatmap.</p>
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
