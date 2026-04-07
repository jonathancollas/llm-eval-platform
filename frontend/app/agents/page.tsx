"use client";
import { useEffect, useState } from "react";
import { modelsApi } from "@/lib/api";
import type { LLMModel } from "@/lib/api";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { ChevronDown, ChevronUp, Play, Zap, CheckCircle2, XCircle, ArrowRight } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "https://llm-eval-backend-kqlh.onrender.com/api";

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

type Tab = "trajectories" | "upload" | "dashboard";

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
  const [trajectories, setTrajectories] = useState<Trajectory[]>([]);
  const [selectedTraj, setSelectedTraj] = useState<TrajectoryDetail | null>(null);
  const [models, setModels] = useState<LLMModel[]>([]);
  const [dashboard, setDashboard] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [evaluating, setEvaluating] = useState(false);

  // Upload form
  const [uploadJson, setUploadJson] = useState("");
  const [uploading, setUploading] = useState(false);

  const loadTrajectories = () => {
    fetch(`${API_BASE}/agents/trajectories`).then(r => r.json())
      .then(d => setTrajectories(d.trajectories ?? [])).catch(() => {});
  };

  useEffect(() => {
    loadTrajectories();
    modelsApi.list().then(setModels).catch(() => {});
    fetch(`${API_BASE}/agents/dashboard`).then(r => r.json()).then(setDashboard).catch(() => {});
  }, []);

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
      loadTrajectories();
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
      if (res.ok) { setUploadJson(""); loadTrajectories(); setTab("trajectories"); }
    } catch (e: any) { alert("Erreur: " + e.message); }
    finally { setUploading(false); }
  };

  const TABS = [
    { key: "trajectories", label: "📋 Trajectoires" },
    { key: "upload", label: "⬆️ Upload" },
    { key: "dashboard", label: "📊 Dashboard" },
  ];

  return (
    <div>
      <PageHeader title="Agent Evaluation" description="Évaluation multi-step d'agents LLM sur 6 axes." />

      <div className="px-8 pt-4 flex gap-1 border-b border-slate-100">
        {TABS.map(({ key, label }) => (
          <button key={key} onClick={() => setTab(key as Tab)}
            className={`px-4 py-2.5 text-sm border-b-2 transition-colors ${
              tab === key ? "border-slate-900 text-slate-900 font-medium" : "border-transparent text-slate-400 hover:text-slate-600"
            }`}>{label}</button>
        ))}
      </div>

      <div className="p-8">

        {/* TRAJECTORIES TAB */}
        {tab === "trajectories" && (
          <div className="flex gap-6">
            {/* List */}
            <div className="w-96 shrink-0 space-y-2 max-h-[600px] overflow-y-auto">
              {!trajectories.length ? (
                <div className="bg-slate-50 border border-slate-200 rounded-xl p-8 text-center">
                  <p className="text-sm text-slate-500">Aucune trajectoire. Uploadez-en une.</p>
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
                <div className="text-center py-20 text-slate-400 text-sm">Sélectionnez une trajectoire.</div>
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
                      <span className="text-green-700 font-medium">Réponse finale : </span>
                      <span className="text-green-600">{selectedTraj.final_answer}</span>
                    </div>
                  )}

                  {/* Step timeline */}
                  <div>
                    <h4 className="text-sm font-medium text-slate-700 mb-2">Trajectoire ({selectedTraj.steps?.length} étapes)</h4>
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
              Upload & créer
            </button>
          </div>
        )}

        {/* DASHBOARD TAB */}
        {tab === "dashboard" && (
          <div>
            {!dashboard?.computed ? (
              <div className="bg-slate-50 border border-slate-200 rounded-xl p-12 text-center">
                <p className="text-sm text-slate-500">Évaluez des trajectoires pour générer le dashboard.</p>
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
      </div>
    </div>
  );
}
