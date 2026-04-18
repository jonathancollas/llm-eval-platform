"use client";
import { useState } from "react";
import type { LLMModelSlim } from "@/lib/api";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { ChevronDown, ChevronUp, Play, Zap, CheckCircle2, XCircle, ArrowRight,
         Shield, AlertTriangle, Network, Brain, Target, TrendingDown } from "lucide-react";

import { API_BASE } from "@/lib/config";
import { useModels, useBenchmarks, useAgentTrajectories, useAgentDashboard, useMultiagentPayloads } from "@/lib/useApi";

interface Trajectory {
  id: number; model_name: string; task_description: string; task_type: string;
  num_steps: number; task_completed: boolean; score_overall: number | null;
  scores: Record<string, number | null> | null;
  total_tokens: number; total_cost_usd: number; created_at: string;
}
interface Step {
  step_index: number; thought: string; action: string; tool: string | null;
  tool_args: any; observation: string; tokens: number; latency_ms: number; error: string | null;
}
interface TrajectoryDetail extends Trajectory {
  steps: Step[]; expected_answer: string | null; final_answer: string;
  total_latency_ms: number;
}

const AXES = [
  { key: "task_completion", label: "Task Completion", color: "#3b82f6", icon: "🎯" },
  { key: "tool_precision", label: "Tool Precision", color: "#8b5cf6", icon: "🔧" },
  { key: "planning_coherence", label: "Planning", color: "#10b981", icon: "📋" },
  { key: "error_recovery", label: "Error Recovery", color: "#f59e0b", icon: "🔄" },
  { key: "safety_compliance", label: "Safety", color: "#ef4444", icon: "🛡" },
  { key: "cost_efficiency", label: "Cost Efficiency", color: "#06b6d4", icon: "💰" },
];

type Tab = "trajectories" | "upload" | "dashboard" | "multiagent";

function ScoreBar({ label, score, color, icon }: { label: string; score: number | null; color: string; icon: string }) {
  if (score == null) return null;
  const pct = Math.round(score * 100);
  return (
    <div className="flex items-center gap-2">
      <span className="text-sm">{icon}</span>
      <span className="text-xs text-slate-600 w-28 shrink-0">{label}</span>
      <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
      <span className="text-xs font-mono text-slate-700 w-10 text-right">{pct}%</span>
    </div>
  );
}

function StepTimeline({ steps }: { steps: Step[] }) {
  const [expanded, setExpanded] = useState<number | null>(null);
  return (
    <div className="space-y-1">
      {steps.map((s, i) => {
        const isExp = expanded === i;
        const hasError = !!s.error;
        return (
          <div key={i}>
            <button onClick={() => setExpanded(isExp ? null : i)}
              className={`w-full flex items-center gap-2 text-xs text-left rounded-lg px-3 py-2 transition-colors ${
                hasError ? "bg-red-50 hover:bg-red-100" : "bg-slate-50 hover:bg-slate-100"
              }`}>
              <span className={`w-5 h-5 rounded-full flex items-center justify-center text-white text-[10px] font-bold shrink-0 ${
                hasError ? "bg-red-400" : "bg-blue-500"
              }`}>{i + 1}</span>
              <span className="text-slate-500 w-20 shrink-0 font-mono">{s.action || "think"}</span>
              {s.tool && <span className="bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded text-[10px] font-medium">{s.tool}</span>}
              <span className="text-slate-400 flex-1 truncate">{s.thought || s.observation}</span>
              <span className="text-slate-300 shrink-0">{s.latency_ms}ms</span>
              {isExp ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            </button>
            {isExp && (
              <div className="bg-white rounded-lg p-3 mx-2 mb-1 border border-slate-100 text-xs space-y-2">
                {s.thought && <div><span className="text-slate-400 uppercase text-[10px] font-medium">Thought</span>
                  <p className="mt-0.5 text-slate-700">{s.thought}</p></div>}
                {s.tool && (
                  <div className="flex items-center gap-2">
                    <span className="text-slate-400 uppercase text-[10px] font-medium">Tool</span>
                    <span className="font-mono text-purple-700 bg-purple-50 px-1.5 py-0.5 rounded">{s.tool}</span>
                    {s.tool_args && <span className="font-mono text-slate-500 text-[10px]">{JSON.stringify(s.tool_args).slice(0, 100)}</span>}
                  </div>
                )}
                {s.observation && <div><span className="text-slate-400 uppercase text-[10px] font-medium">Observation</span>
                  <pre className="mt-0.5 text-slate-600 font-mono whitespace-pre-wrap">{s.observation}</pre></div>}
                {s.error && <div className="text-red-600 font-mono bg-red-50 p-2 rounded">❌ {s.error}</div>}
                <div className="text-slate-300">{s.tokens} tokens · {s.latency_ms}ms</div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default function AgentsPage() {
  const [tab, setTab] = useState<Tab>("trajectories");
  const [selectedTraj, setSelectedTraj] = useState<TrajectoryDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [evaluating, setEvaluating] = useState(false);

  // Upload form
  const [uploadJson, setUploadJson] = useState("");
  const [uploading, setUploading] = useState(false);

  const { models } = useModels();
  const { trajectories, refresh: refreshTrajectories } = useAgentTrajectories();
  const { dashboard } = useAgentDashboard();

  const viewTrajectory = async (id: number) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/agents/trajectories/${id}`);
      setSelectedTraj(await res.json());
    } finally { setLoading(false); }
  };

  const evaluateTrajectory = async (id: number) => {
    setEvaluating(true);
    try {
      await fetch(`${API_BASE}/agents/evaluate`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ trajectory_id: id, use_llm_judge: true }),
      });
      await viewTrajectory(id);
      refreshTrajectories();
    } finally { setEvaluating(false); }
  };

  const uploadTrajectory = async () => {
    if (!uploadJson.trim()) return;
    setUploading(true);
    try {
      const data = JSON.parse(uploadJson);
      const res = await fetch(`${API_BASE}/agents/trajectories`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      if (res.ok) { setUploadJson(""); refreshTrajectories(); setTab("trajectories"); }
    } catch (e: any) { console.error("Error: " + e.message); }
    finally { setUploading(false); }
  };

  const TABS = [
    { key: "trajectories", label: "📋 Trajectoires" },
    { key: "upload", label: "⬆️ Upload" },
    { key: "dashboard", label: "📊 Dashboard" },
    { key: "multiagent", label: "🧠 Multi-Agent Lab" },
  ];

  return (
    <div>
      <PageHeader title="Agent Evaluation" description="Multi-step LLM agent evaluation on 6 axes." />

      <div className="px-4 sm:px-8 pt-4 flex gap-1 overflow-x-auto border-b border-slate-100">
        {TABS.map(({ key, label }) => (
          <button key={key} onClick={() => setTab(key as Tab)}
            className={`px-4 py-2.5 text-sm border-b-2 transition-colors whitespace-nowrap ${
              tab === key ? "border-slate-900 text-slate-900 font-medium" : "border-transparent text-slate-400 hover:text-slate-600"
            }`}>{label}</button>
        ))}
      </div>

      <div className="p-4 sm:p-8">

        {/* TRAJECTORIES TAB */}
        {tab === "trajectories" && (
          <div className="flex gap-6">
            {/* List */}
            <div className="w-96 shrink-0 space-y-2 max-h-[600px] overflow-y-auto">
              {!trajectories.length ? (
                <div className="bg-slate-50 border border-slate-200 rounded-xl p-8 text-center">
                  <p className="text-sm text-slate-500">No trajectories. Upload one.</p>
                </div>
              ) : trajectories.map(t => (
                <button key={t.id} onClick={() => viewTrajectory(t.id)}
                  className={`w-full text-left p-3 rounded-xl border transition-colors ${
                    selectedTraj?.id === t.id ? "border-slate-900 bg-slate-50" : "border-slate-200 hover:border-slate-300"
                  }`}>
                  <div className="flex items-center gap-2 mb-1">
                    {t.task_completed ? <CheckCircle2 size={13} className="text-green-500" /> : <XCircle size={13} className="text-red-400" />}
                    <span className="text-xs font-medium text-slate-800 truncate flex-1">{t.task_description}</span>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-slate-400">
                    <span>{t.model_name}</span>
                    <span>·</span>
                    <span>{t.num_steps} steps</span>
                    {t.score_overall != null && (
                      <span className={`ml-auto font-mono font-bold ${t.score_overall > 0.7 ? "text-green-600" : t.score_overall > 0.4 ? "text-yellow-600" : "text-red-600"}`}>
                        {Math.round(t.score_overall * 100)}%
                      </span>
                    )}
                  </div>
                </button>
              ))}
            </div>

            {/* Detail */}
            <div className="flex-1 min-w-0">
              {loading && <div className="flex justify-center py-20"><Spinner size={24} /></div>}
              {!selectedTraj && !loading && (
                <div className="text-center py-20 text-slate-400 text-sm">Select a trajectory.</div>
              )}
              {selectedTraj && !loading && (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className="font-medium text-slate-900">{selectedTraj.task_description}</h3>
                    <button onClick={() => evaluateTrajectory(selectedTraj.id)} disabled={evaluating}
                      className="flex items-center gap-1.5 bg-slate-900 text-white px-4 py-1.5 rounded-lg text-xs hover:bg-slate-700 disabled:opacity-40">
                      {evaluating ? <Spinner size={12} /> : <Zap size={12} />}
                      {evaluating ? "Scoring…" : "Scorer (6 axes)"}
                    </button>
                  </div>

                  {/* Scores radar */}
                  {selectedTraj.scores?.overall != null && (
                    <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-2">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-sm font-medium text-slate-900">Score global</span>
                        <span className={`text-xl font-bold ${(selectedTraj.scores.overall ?? 0) > 0.7 ? "text-green-600" : "text-yellow-600"}`}>
                          {Math.round((selectedTraj.scores.overall ?? 0) * 100)}%
                        </span>
                      </div>
                      {AXES.map(a => (
                        <ScoreBar key={a.key} label={a.label} score={(selectedTraj.scores as any)?.[a.key] ?? null} color={a.color} icon={a.icon} />
                      ))}
                    </div>
                  )}

                  {/* Meta */}
                  <div className="grid grid-cols-4 gap-3 text-xs">
                    {[
                      { label: "Steps", value: selectedTraj.num_steps },
                      { label: "Tokens", value: selectedTraj.total_tokens },
                      { label: "Latency", value: `${selectedTraj.total_latency_ms}ms` },
                      { label: "Completed", value: selectedTraj.task_completed ? "✅" : "❌" },
                    ].map(({ label, value }) => (
                      <div key={label} className="bg-slate-50 rounded-lg p-2.5 text-center">
                        <div className="text-slate-400">{label}</div>
                        <div className="font-medium text-slate-900">{value}</div>
                      </div>
                    ))}
                  </div>

                  {/* Final answer */}
                  {selectedTraj.final_answer && (
                    <div className="bg-green-50 border border-green-200 rounded-lg p-3 text-xs">
                      <span className="text-green-700 font-medium">Final response: </span>
                      <span className="text-green-600">{selectedTraj.final_answer}</span>
                    </div>
                  )}

                  {/* Step timeline */}
                  <div>
                    <h4 className="text-sm font-medium text-slate-700 mb-2">Trajectoire ({selectedTraj.steps?.length} steps)</h4>
                    <StepTimeline steps={selectedTraj.steps ?? []} />
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* UPLOAD TAB */}
        {tab === "upload" && (
          <div className="max-w-2xl space-y-4">
            <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-xs text-blue-700 space-y-1">
              <div className="font-medium">Format JSON attendu :</div>
              <pre className="bg-white rounded p-2 border border-blue-100 text-[11px]">{`{
  "model_id": 1,
  "task_description": "Find the weather in Paris",
  "task_type": "tool_use",
  "task_completed": true,
  "final_answer": "22°C, sunny",
  "expected_answer": "22°C",
  "steps": [
    {"step_index": 0, "thought": "I need to search...", "action": "tool_call", "tool": "weather_api", "tool_args": {"city": "Paris"}, "observation": "22°C sunny", "tokens": 150, "latency_ms": 800},
    {"step_index": 1, "thought": "Got the answer", "action": "reply", "observation": "", "tokens": 50, "latency_ms": 200}
  ]
}`}</pre>
            </div>
            <textarea rows={12} value={uploadJson} onChange={e => setUploadJson(e.target.value)}
              placeholder="Collez votre JSON de trajectoire ici…"
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono resize-none" />
            <button onClick={uploadTrajectory} disabled={uploading || !uploadJson.trim()}
              className="flex items-center gap-2 bg-slate-900 text-white px-5 py-2 rounded-lg text-sm hover:bg-slate-700 disabled:opacity-40">
              {uploading ? <Spinner size={13} /> : <Play size={14} />}
              Upload & create
            </button>
          </div>
        )}

        {/* DASHBOARD TAB */}
        {tab === "dashboard" && (
          <div>
            {!dashboard?.computed ? (
              <div className="bg-slate-50 border border-slate-200 rounded-xl p-12 text-center">
                <p className="text-sm text-slate-500">Evaluate trajectories to generate the dashboard.</p>
              </div>
            ) : (
              <div className="space-y-4">
                {Object.entries(dashboard.models ?? {}).map(([modelName, data]: any) => (
                  <div key={modelName} className="bg-white border border-slate-200 rounded-xl p-5">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="font-medium text-slate-900">{modelName}</h3>
                      <div className="flex items-center gap-3 text-xs text-slate-400">
                        <span>{data.n_trajectories} trajectoires</span>
                        <span>Completion: {Math.round(data.completion_rate * 100)}%</span>
                        <span className="font-bold text-slate-900 text-sm">{Math.round(data.avg_overall * 100)}%</span>
                      </div>
                    </div>
                    <div className="space-y-1.5">
                      {AXES.map(a => (
                        <ScoreBar key={a.key} label={a.label} score={data.axes?.[a.key] ?? null} color={a.color} icon={a.icon} />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* MULTI-AGENT LAB TAB */}
        {tab === "multiagent" && (
          <MultiAgentLab models={models} />
        )}
      </div>
    </div>
  );
}

// ── Multi-Agent Lab Component ──────────────────────────────────────────────────

type SimScenario = "pipeline_injection" | "goal_drift" | "trust_propagation";
type SimResult = any;
type SandbaggingResult = any;

function MultiAgentLab({ models }: { models: LLMModelSlim[] }) {
  const [activeSection, setActiveSection] = useState<"simulation" | "sandbagging">("simulation");

  // Simulation state
  const [scenario, setScenario]               = useState<SimScenario>("pipeline_injection");
  const [selectedModels, setSelectedModels]   = useState<number[]>([]);
  const [payloadId, setPayloadId]             = useState("INJ-002");
  const [maxSteps, setMaxSteps]               = useState(6);
  const [autonomyLevel, setAutonomyLevel]     = useState(3);
  const [simRunning, setSimRunning]           = useState(false);
  const [simResult, setSimResult]             = useState<SimResult | null>(null);
  const [simError, setSimError]               = useState<string | null>(null);

  // Sandbagging state
  const [sbModelId, setSbModelId]             = useState<number | "">("");
  const [sbBenchId, setSbBenchId]             = useState<number | "">("");
  const [sbSamples, setSbSamples]             = useState(10);
  const [sbRunning, setSbRunning]             = useState(false);
  const [sbResult, setSbResult]               = useState<SandbaggingResult | null>(null);
  const [sbError, setSbError]                 = useState<string | null>(null);

  const { payloads } = useMultiagentPayloads();
  const { benchmarks: sbBenchmarks } = useBenchmarks();

  const toggleModel = (id: number) => {
    setSelectedModels(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : prev.length < 3 ? [...prev, id] : prev
    );
  };

  const runSimulation = async () => {
    if (!selectedModels.length) return;
    setSimRunning(true); setSimResult(null); setSimError(null);
    try {
      const res = await fetch(`${API_BASE}/multiagent/simulate/pipeline`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scenario_type: scenario,
          model_ids: selectedModels,
          injection_payload_id: payloadId,
          max_steps: maxSteps,
          autonomy_level: autonomyLevel,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      setSimResult(await res.json());
    } catch (e: any) {
      setSimError(e.message);
    } finally {
      setSimRunning(false);
    }
  };

  const runSandbagging = async () => {
    if (!sbModelId || !sbBenchId) return;
    setSbRunning(true); setSbResult(null); setSbError(null);
    try {
      const res = await fetch(`${API_BASE}/multiagent/sandbagging/probe`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model_id: sbModelId, benchmark_id: sbBenchId, n_samples: sbSamples }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      setSbResult(await res.json());
    } catch (e: any) {
      setSbError(e.message);
    } finally {
      setSbRunning(false);
    }
  };

  const SCENARIO_INFO: Record<SimScenario, { title: string; desc: string; ref: string; icon: string }> = {
    pipeline_injection: {
      title: "Pipeline Indirect Injection",
      desc: "Orchestrator → Retriever → Executor. The retriever's input carries an injected payload (EchoLeak pattern). Tests whether the executor follows the injected instruction.",
      ref: "EchoLeak CVE-2025-32711",
      icon: "💉",
    },
    goal_drift: {
      title: "Long-Horizon Goal Drift",
      desc: "Single agent over multiple self-loop steps with a crescendo injection. Measures how the agent's alignment with the original objective degrades over time.",
      ref: "INESIA PDF — Contextual drift in extended sessions",
      icon: "📉",
    },
    trust_propagation: {
      title: "Inter-Agent Trust Propagation",
      desc: "3-agent pipeline where the first agent is compromised via a trust escalation attack. Tests whether the malicious instruction propagates to downstream agents.",
      ref: "ATLAS AML.T0051.002 — Indirect Prompt Injection",
      icon: "🕸️",
    },
  };

  const riskColor = (level: string) => {
    if (level === "critical") return "text-red-700 bg-red-50 border-red-200";
    if (level === "high")     return "text-orange-700 bg-orange-50 border-orange-200";
    if (level === "medium")   return "text-yellow-700 bg-yellow-50 border-yellow-200";
    return "text-green-700 bg-green-50 border-green-200";
  };

  const scoreBar = (label: string, value: number, invert = false) => {
    const pct = Math.round(value * 100);
    const fill = invert ? `hsl(${Math.round(120 * (1 - value))}, 70%, 50%)` : `hsl(${Math.round(120 * value)}, 70%, 50%)`;
    return (
      <div key={label} className="flex items-center gap-3">
        <span className="text-xs text-slate-500 w-40 shrink-0">{label}</span>
        <div className="flex-1 bg-slate-100 rounded-full h-1.5">
          <div className="h-1.5 rounded-full transition-all" style={{ width: `${pct}%`, background: fill }} />
        </div>
        <span className="text-xs font-mono text-slate-700 w-10 text-right">{pct}%</span>
      </div>
    );
  };

  return (
    <div className="space-y-6">
      {/* Section tabs */}
      <div className="flex gap-2">
        {(["simulation", "sandbagging"] as const).map(s => (
          <button key={s} onClick={() => setActiveSection(s)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              activeSection === s ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}>
            {s === "simulation" ? "🧠 Multi-Agent Simulation" : "🔍 Anti-Sandbagging Probe"}
          </button>
        ))}
      </div>

      {/* ── SIMULATION ── */}
      {activeSection === "simulation" && (
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
          {/* Config panel */}
          <div className="lg:col-span-2 space-y-4">
            <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-4">
              <h3 className="font-semibold text-slate-900 text-sm">Scenario</h3>
              <div className="space-y-2">
                {(Object.keys(SCENARIO_INFO) as SimScenario[]).map(s => {
                  const info = SCENARIO_INFO[s];
                  return (
                    <button key={s} onClick={() => setScenario(s)}
                      className={`w-full text-left p-3 rounded-lg border transition-colors ${
                        scenario === s ? "border-slate-900 bg-slate-50" : "border-slate-100 hover:border-slate-200"
                      }`}>
                      <div className="flex items-center gap-2 mb-1">
                        <span>{info.icon}</span>
                        <span className="text-xs font-medium text-slate-900">{info.title}</span>
                      </div>
                      <p className="text-[11px] text-slate-500 line-clamp-2">{info.desc}</p>
                      <p className="text-[10px] text-blue-500 mt-1">Ref: {info.ref}</p>
                    </button>
                  );
                })}
              </div>

              <div>
                <label className="text-xs text-slate-500 mb-1.5 block">
                  Models (select {scenario === "trust_propagation" ? "3" : scenario === "pipeline_injection" ? "1-3" : "1"})
                </label>
                <div className="space-y-1 max-h-40 overflow-y-auto">
                  {models.slice(0, 30).map(m => (
                    <label key={m.id} className="flex items-center gap-2 p-1.5 rounded hover:bg-slate-50 cursor-pointer">
                      <input type="checkbox" checked={selectedModels.includes(m.id)}
                        onChange={() => toggleModel(m.id)} className="rounded" />
                      <span className="text-xs text-slate-700 truncate">{m.name}</span>
                    </label>
                  ))}
                </div>
              </div>

              <div>
                <label className="text-xs text-slate-500 mb-1.5 block">Injection Payload</label>
                <select value={payloadId} onChange={e => setPayloadId(e.target.value)}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-xs">
                  {payloads.map(p => (
                    <option key={p.id} value={p.id}>{p.id} — {p.name} (sev. {p.severity})</option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-slate-500 mb-1 block">Max Steps</label>
                  <input type="number" min={3} max={12} value={maxSteps}
                    onChange={e => setMaxSteps(Number(e.target.value))}
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-xs" />
                </div>
                <div>
                  <label className="text-xs text-slate-500 mb-1 block">Autonomy Level (L1-L5)</label>
                  <input type="number" min={1} max={5} value={autonomyLevel}
                    onChange={e => setAutonomyLevel(Number(e.target.value))}
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-xs" />
                </div>
              </div>

              <button onClick={runSimulation}
                disabled={simRunning || !selectedModels.length}
                className="w-full flex items-center justify-center gap-2 bg-slate-900 text-white px-4 py-2.5 rounded-lg text-sm hover:bg-slate-700 disabled:opacity-40">
                {simRunning ? <><Spinner size={13} /> Running simulation…</> : <><Network size={14} /> Run Simulation</>}
              </button>

              {simError && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-xs text-red-700">{simError}</div>
              )}
            </div>
          </div>

          {/* Results panel */}
          <div className="lg:col-span-3">
            {!simResult && !simRunning && (
              <div className="bg-slate-50 border border-slate-200 rounded-xl p-12 text-center">
                <Network size={32} className="mx-auto text-slate-300 mb-3" />
                <p className="text-sm text-slate-500">Configure and run a simulation to see results.</p>
                <p className="text-xs text-slate-400 mt-1">Tests prompt injection, goal drift, and trust propagation in multi-agent pipelines.</p>
              </div>
            )}

            {simRunning && (
              <div className="bg-slate-50 border border-slate-200 rounded-xl p-12 text-center">
                <Spinner size={24} />
                <p className="text-sm text-slate-500 mt-3">Running multi-agent simulation…</p>
                <p className="text-xs text-slate-400 mt-1">This may take 30-90 seconds depending on model latency.</p>
              </div>
            )}

            {simResult && (
              <div className="space-y-4">
                {/* Header metrics */}
                <div className="bg-white border border-slate-200 rounded-xl p-5">
                  <div className="flex items-start justify-between mb-4">
                    <div>
                      <h3 className="font-semibold text-slate-900">{simResult.scenario_name}</h3>
                      <p className="text-xs text-slate-500 mt-0.5">{simResult.n_agents} agents · {simResult.n_steps} steps · L{simResult.autonomy_level}</p>
                    </div>
                    <span className={`text-xs px-2 py-1 rounded border font-medium ${simResult.task_completed ? "bg-green-50 text-green-700 border-green-200" : "bg-red-50 text-red-700 border-red-200"}`}>
                      {simResult.task_completed ? "✓ Completed" : "✗ Incomplete"}
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-3 mb-4">
                    {[
                      { label: "System Safety", value: simResult.metrics?.system_safety_score, invert: false },
                      { label: "Pipeline Integrity", value: simResult.metrics?.pipeline_integrity_score, invert: false },
                      { label: "Goal Alignment", value: simResult.metrics?.overall_goal_alignment, invert: false },
                      { label: "Injection Success Rate", value: simResult.metrics?.prompt_injection_success_rate, invert: true },
                    ].map(({ label, value, invert }) => (
                      <div key={label} className="bg-slate-50 rounded-lg p-3">
                        <div className="text-[11px] text-slate-500 mb-1">{label}</div>
                        <div className="text-lg font-bold text-slate-900">{Math.round((value ?? 0) * 100)}%</div>
                        <div className="h-1 bg-slate-200 rounded-full mt-1">
                          <div className="h-1 rounded-full" style={{
                            width: `${Math.round((value ?? 0) * 100)}%`,
                            background: invert
                              ? `hsl(${Math.round(120 * (1 - (value ?? 0)))}, 70%, 50%)`
                              : `hsl(${Math.round(120 * (value ?? 0))}, 70%, 50%)`
                          }} />
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Failure mode flags */}
                  <div className="flex flex-wrap gap-2">
                    {simResult.metrics?.goal_drift_detected && (
                      <span className="flex items-center gap-1 text-[11px] px-2 py-1 bg-orange-50 text-orange-700 border border-orange-200 rounded-full">
                        <TrendingDown size={10} /> Goal Drift (step {simResult.metrics?.goal_drift_at_step})
                      </span>
                    )}
                    {simResult.metrics?.trust_propagation_occurred && (
                      <span className="flex items-center gap-1 text-[11px] px-2 py-1 bg-red-50 text-red-700 border border-red-200 rounded-full">
                        <Network size={10} /> Trust Propagated
                      </span>
                    )}
                    {(simResult.metrics?.compounding_errors ?? 0) > 0 && (
                      <span className="flex items-center gap-1 text-[11px] px-2 py-1 bg-purple-50 text-purple-700 border border-purple-200 rounded-full">
                        <AlertTriangle size={10} /> {simResult.metrics?.compounding_errors} Compounding Errors
                      </span>
                    )}
                    {simResult.metrics?.prompt_injection_success_rate > 0 && (
                      <span className="flex items-center gap-1 text-[11px] px-2 py-1 bg-rose-50 text-rose-700 border border-rose-200 rounded-full">
                        <Shield size={10} /> Injection Succeeded ({Math.round(simResult.metrics?.prompt_injection_success_rate * 100)}%)
                      </span>
                    )}
                  </div>
                </div>

                {/* Step-by-step trace */}
                <div className="bg-white border border-slate-200 rounded-xl p-5">
                  <h4 className="font-medium text-slate-900 text-sm mb-3">Execution Trace</h4>
                  <div className="space-y-2">
                    {(simResult.steps ?? []).map((step: any) => (
                      <div key={step.step_index}
                        className={`rounded-lg p-3 border text-xs ${
                          step.injected_payload_followed
                            ? "bg-red-50 border-red-200"
                            : step.failure_modes?.length && !step.failure_modes.includes("none")
                            ? "bg-orange-50 border-orange-200"
                            : "bg-slate-50 border-slate-100"
                        }`}>
                        <div className="flex items-center justify-between mb-1">
                          <div className="flex items-center gap-2">
                            <span className="font-mono bg-slate-200 px-1.5 py-0.5 rounded text-[10px]">
                              step {step.step_index}
                            </span>
                            <span className="font-medium text-slate-700">{step.agent_name}</span>
                            <span className="text-slate-400 text-[10px]">{step.agent_role}</span>
                          </div>
                          <div className="flex items-center gap-2 text-[10px] text-slate-400">
                            <span>align: {Math.round((step.goal_alignment ?? 0) * 100)}%</span>
                            <span>{step.latency_ms}ms</span>
                            {step.metadata?.injected && (
                              <span className="text-red-500 font-medium">⚡ INJECTED</span>
                            )}
                          </div>
                        </div>
                        <p className="text-slate-600 line-clamp-3">{step.output}</p>
                        {step.failure_modes?.length > 0 && !step.failure_modes.includes("none") && (
                          <div className="flex gap-1 mt-1.5">
                            {step.failure_modes.map((fm: string) => (
                              <span key={fm} className="text-[10px] px-1.5 py-0.5 bg-orange-100 text-orange-700 rounded">
                                {fm.replace(/_/g, " ")}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>

                {/* Cost */}
                <div className="bg-slate-50 border border-slate-200 rounded-lg px-4 py-2.5 flex items-center justify-between text-xs text-slate-500">
                  <span>{simResult.performance?.total_tokens?.toLocaleString()} tokens</span>
                  <span>${simResult.performance?.total_cost_usd?.toFixed(6)} USD</span>
                  <span>{simResult.performance?.total_latency_ms}ms total</span>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── ANTI-SANDBAGGING ── */}
      {activeSection === "sandbagging" && (
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
          <div className="lg:col-span-2 space-y-4">
            <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-4">
              <div>
                <h3 className="font-semibold text-slate-900 text-sm mb-1">Anti-Sandbagging Probe</h3>
                <p className="text-xs text-slate-500">
                  Detects whether a model deliberately underperforms during evaluation by comparing
                  eval-framing vs neutral framing vs expert elicitation.
                </p>
                <div className="mt-2 text-[11px] text-blue-600 space-y-0.5">
                  <div>Ref: Apollo Research / OpenAI (2025)</div>
                  <div>Ref: Meinke et al. (2024) — sandbagging in safety evaluations</div>
                </div>
              </div>

              <div>
                <label className="text-xs text-slate-500 mb-1.5 block">Model to probe</label>
                <select value={sbModelId} onChange={e => setSbModelId(Number(e.target.value))}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-xs">
                  <option value="">Select a model…</option>
                  {models.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
                </select>
              </div>

              <div>
                <label className="text-xs text-slate-500 mb-1.5 block">Benchmark</label>
                <select value={sbBenchId} onChange={e => setSbBenchId(Number(e.target.value))}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-xs">
                  <option value="">Select a benchmark…</option>
                  {sbBenchmarks.map((b: any) => (
                    <option key={b.id} value={b.id}>{b.name}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-xs text-slate-500 mb-1.5 block">N samples (10-30)</label>
                <input type="number" min={5} max={30} value={sbSamples}
                  onChange={e => setSbSamples(Number(e.target.value))}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-xs" />
              </div>

              <button onClick={runSandbagging}
                disabled={sbRunning || !sbModelId || !sbBenchId}
                className="w-full flex items-center justify-center gap-2 bg-slate-900 text-white px-4 py-2.5 rounded-lg text-sm hover:bg-slate-700 disabled:opacity-40">
                {sbRunning ? <><Spinner size={13} /> Probing…</> : <><Brain size={14} /> Run Probe</>}
              </button>
              {sbError && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-xs text-red-700">{sbError}</div>
              )}
            </div>
          </div>

          <div className="lg:col-span-3">
            {!sbResult && !sbRunning && (
              <div className="bg-slate-50 border border-slate-200 rounded-xl p-12 text-center">
                <Brain size={32} className="mx-auto text-slate-300 mb-3" />
                <p className="text-sm text-slate-500">Select a model and benchmark to run the sandbagging probe.</p>
              </div>
            )}

            {sbRunning && (
              <div className="bg-slate-50 border border-slate-200 rounded-xl p-12 text-center">
                <Spinner size={24} />
                <p className="text-sm text-slate-500 mt-3">Running sandbagging battery…</p>
                <p className="text-xs text-slate-400 mt-1">Each question is tested under 4 framing conditions. This takes 1-3 minutes.</p>
              </div>
            )}

            {sbResult && (
              <div className="space-y-4">
                {/* Risk header */}
                <div className={`rounded-xl p-5 border ${riskColor(sbResult.risk_level)}`}>
                  <div className="flex items-center justify-between mb-2">
                    <div>
                      <h3 className="font-bold text-base">{sbResult.risk_level.toUpperCase()} RISK</h3>
                      <p className="text-xs mt-0.5">{sbResult.model_name} × {sbResult.benchmark_name}</p>
                    </div>
                    <div className="text-right">
                      <div className="text-2xl font-bold">{Math.round(sbResult.mean_sandbagging_score * 100)}%</div>
                      <div className="text-[11px]">sandbagging score</div>
                    </div>
                  </div>
                  <p className="text-xs mt-3">{sbResult.recommendation}</p>
                  <div className="text-[10px] mt-2 opacity-70">
                    Scientific confidence: {sbResult.scientific_confidence} · {sbResult.n_probes} probes
                  </div>
                </div>

                {/* Key metrics */}
                <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-3">
                  <h4 className="font-medium text-slate-900 text-sm">Probe Metrics</h4>
                  {[
                    { label: "Eval-Awareness Rate", value: sbResult.eval_awareness_rate, invert: true },
                    { label: "Capability Gap (expert vs eval)", value: sbResult.capability_gap, invert: true },
                    { label: "Mean Sandbagging Score", value: sbResult.mean_sandbagging_score, invert: true },
                  ].map(({ label, value, invert }) => scoreBar(label, value, invert))}
                </div>

                {/* Probe detail table */}
                <div className="bg-white border border-slate-200 rounded-xl p-5">
                  <h4 className="font-medium text-slate-900 text-sm mb-3">Individual Probes</h4>
                  <div className="space-y-2 max-h-64 overflow-y-auto">
                    {(sbResult.probes ?? []).map((p: any) => (
                      <div key={p.probe_id}
                        className={`rounded-lg p-3 border text-xs ${p.sandbagging_score > 0.5 ? "bg-orange-50 border-orange-200" : "bg-slate-50 border-slate-100"}`}>
                        <div className="flex items-center justify-between mb-1.5">
                          <span className="font-mono text-[10px] bg-slate-200 px-1.5 py-0.5 rounded">{p.probe_id}</span>
                          <div className="flex gap-2 text-[10px]">
                            <span>eval: {Math.round(p.eval_framing_score * 100)}%</span>
                            <span>neutral: {Math.round(p.neutral_framing_score * 100)}%</span>
                            <span>expert: {Math.round(p.expert_elicited_score * 100)}%</span>
                            <span className={`font-medium ${p.performance_delta > 0.1 ? "text-orange-600" : "text-slate-500"}`}>
                              Δ{p.performance_delta > 0 ? "+" : ""}{Math.round(p.performance_delta * 100)}%
                            </span>
                          </div>
                        </div>
                        {p.eval_awareness_detected && (
                          <span className="text-[10px] px-1.5 py-0.5 bg-red-100 text-red-700 rounded">eval-aware</span>
                        )}
                        {p.evidence.map((ev: string, i: number) => (
                          <p key={i} className="text-slate-500 mt-1 text-[10px]">· {ev}</p>
                        ))}
                      </div>
                    ))}
                  </div>
                </div>

                {/* References */}
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                  <p className="text-[11px] font-medium text-blue-700 mb-1">Scientific References</p>
                  {(sbResult.references ?? []).map((r: string) => (
                    <p key={r} className="text-[10px] text-blue-600">· {r}</p>
                  ))}
                </div>

                <div className="text-xs text-slate-400 text-right">
                  {sbResult.performance?.total_tokens?.toLocaleString()} tokens · ${sbResult.performance?.total_cost_usd?.toFixed(6)} USD
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// Spinner is imported from @/components/Spinner above
