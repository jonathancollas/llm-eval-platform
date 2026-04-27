"use client";
import { useState, useMemo } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { API_BASE } from "@/lib/config";
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ResponsiveContainer, Tooltip, Legend,
  LineChart, Line, XAxis, YAxis, CartesianGrid,
} from "recharts";
import { Plus, Trash2, BarChart3, TrendingUp, AlertCircle } from "lucide-react";

const API = API_BASE;

// ── Types ─────────────────────────────────────────────────────────────────────

interface CIBound { lower: number; upper: number; level: number }

interface MetricDetail {
  value: number;
  grade: string;
  interpretation: string;
  ci: CIBound | null;
}

interface CapabilityBreakdownRow {
  capability: string;
  autonomy: number;
  adaptivity: number;
  efficiency: number;
  composite: number;
  n_steps: number;
}

interface MetricsResult {
  model_name: string;
  composite_frontier_score: number;
  frontier_grade: string;
  frontier_grade_interpretation: string;
  autonomy: MetricDetail & { n_steps: number; n_error_steps: number; n_retry_steps: number };
  adaptivity: MetricDetail & { n_error_episodes: number; n_successful_recoveries: number; mean_recovery_time_steps: number };
  efficiency: MetricDetail & { tokens_per_step: number; steps_to_completion: number; max_steps: number; step_efficiency: number };
  generalization: MetricDetail & { benchmarks_evaluated: number; score_variance: number; worst_score: number; best_score: number; coefficient_of_variation: number };
  capability_breakdown: CapabilityBreakdownRow[];
  created_at: string;
}

interface LeaderboardRow {
  rank: number;
  model_name: string;
  composite_frontier_score: number;
  frontier_grade: string;
  frontier_grade_interpretation: string;
  autonomy: number;
  adaptivity: number;
  efficiency: number;
  generalization: number;
  version_count: number;
  created_at: string;
}

interface TrendPoint {
  version: string;
  composite_frontier_score: number;
  autonomy: number;
  adaptivity: number;
  efficiency: number;
  generalization: number;
  created_at: string;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const CHART_COLORS = ["#3b82f6", "#8b5cf6", "#10b981", "#f59e0b", "#ef4444", "#06b6d4"];

const GRADE_COLORS: Record<string, string> = {
  A: "bg-green-100 text-green-700 border border-green-200",
  B: "bg-blue-100 text-blue-700 border border-blue-200",
  C: "bg-amber-100 text-amber-700 border border-amber-200",
  D: "bg-red-100 text-red-600 border border-red-200",
};

const METRIC_LABELS = ["Autonomy", "Adaptivity", "Efficiency", "Generalization"] as const;
type MetricKey = "autonomy" | "adaptivity" | "efficiency" | "generalization";

const METRIC_DESCRIPTIONS: Record<MetricKey, string> = {
  autonomy: "Fraction of steps completed without error or retry — measures independence from human intervention.",
  adaptivity: "Recovery rate after unexpected errors — how well the model bounces back.",
  efficiency: "Goal progress per unit resource (steps, tokens) — lower waste, higher score.",
  generalization: "Cross-distribution consistency (IRT-inspired) — how stable performance is across benchmarks.",
};

// ── Default form values ───────────────────────────────────────────────────────

const DEFAULT_STEPS = JSON.stringify([
  { tool_success: true, input_tokens: 120, output_tokens: 60, capability: "reasoning" },
  { tool_success: true, input_tokens: 100, output_tokens: 50, capability: "reasoning" },
  { tool_success: false, error_type: "timeout", input_tokens: 50, output_tokens: 0, capability: "agentic" },
  { tool_success: true, input_tokens: 90, output_tokens: 45, capability: "agentic" },
  { tool_success: true, input_tokens: 110, output_tokens: 55, capability: "reasoning" },
], null, 2);

const DEFAULT_BENCHMARKS = JSON.stringify({
  mmlu: 0.72,
  hellaswag: 0.80,
  arc_challenge: 0.68,
  gsm8k: 0.65,
}, null, 2);

// ── Radar chart for frontier metrics ─────────────────────────────────────────

function FrontierRadar({ results }: { results: MetricsResult[] }) {
  if (!results.length) return null;

  const data = METRIC_LABELS.map(label => {
    const key = label.toLowerCase() as MetricKey;
    const row: Record<string, string | number> = { metric: label };
    results.forEach(r => {
      row[r.model_name] = Math.round((r[key].value ?? 0) * 100);
    });
    return row;
  });

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-6">
      <h3 className="font-medium text-slate-900 mb-1 text-sm">Frontier Metrics — Radar</h3>
      <p className="text-xs text-slate-400 mb-4">Spider chart comparing all 4 frontier metrics per model (0–100 scale)</p>
      <ResponsiveContainer width="100%" height={300}>
        <RadarChart data={data}>
          <PolarGrid stroke="#e2e8f0" />
          <PolarAngleAxis dataKey="metric" tick={{ fontSize: 12, fill: "#475569" }} />
          <PolarRadiusAxis angle={90} domain={[0, 100]} tick={{ fontSize: 10, fill: "#94a3b8" }} />
          {results.map((r, i) => (
            <Radar
              key={r.model_name}
              name={r.model_name}
              dataKey={r.model_name}
              stroke={CHART_COLORS[i % CHART_COLORS.length]}
              fill={CHART_COLORS[i % CHART_COLORS.length]}
              fillOpacity={0.12}
              strokeWidth={2}
            />
          ))}
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Tooltip formatter={(v: number) => `${v}%`} />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Per-capability breakdown table ────────────────────────────────────────────

function CapabilityBreakdownTable({ breakdown }: { breakdown: CapabilityBreakdownRow[] }) {
  if (!breakdown.length) return null;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-slate-100">
            <th className="text-left px-3 py-2 text-slate-500 font-medium">Capability</th>
            <th className="text-center px-3 py-2 text-slate-500 font-medium">Autonomy</th>
            <th className="text-center px-3 py-2 text-slate-500 font-medium">Adaptivity</th>
            <th className="text-center px-3 py-2 text-slate-500 font-medium">Efficiency</th>
            <th className="text-center px-3 py-2 text-slate-500 font-medium">Composite</th>
            <th className="text-center px-3 py-2 text-slate-500 font-medium">Steps</th>
          </tr>
        </thead>
        <tbody>
          {breakdown.map(row => (
            <tr key={row.capability} className="border-b border-slate-50 hover:bg-slate-50">
              <td className="px-3 py-2 font-medium capitalize text-slate-700">{row.capability}</td>
              {(["autonomy", "adaptivity", "efficiency", "composite"] as const).map(k => {
                const v = row[k];
                const pct = (v * 100).toFixed(0);
                const color = v >= 0.8 ? "text-green-600" : v >= 0.65 ? "text-blue-600" : v >= 0.45 ? "text-amber-600" : "text-red-500";
                return <td key={k} className={`px-3 py-2 text-center font-mono font-medium ${color}`}>{pct}%</td>;
              })}
              <td className="px-3 py-2 text-center text-slate-400">{row.n_steps}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Confidence interval pill ──────────────────────────────────────────────────

function CIPill({ ci }: { ci: CIBound | null }) {
  if (!ci) return null;
  return (
    <span className="text-[10px] text-slate-400 font-mono ml-1">
      [{(ci.lower * 100).toFixed(1)}%, {(ci.upper * 100).toFixed(1)}%]
    </span>
  );
}

// ── Metric detail card ────────────────────────────────────────────────────────

function MetricCard({ label, metricKey, data }: { label: string; metricKey: MetricKey; data: MetricDetail }) {
  const pct = (data.value * 100).toFixed(1);
  const barColor =
    data.value >= 0.8 ? "bg-green-500" :
    data.value >= 0.65 ? "bg-blue-500" :
    data.value >= 0.45 ? "bg-amber-500" : "bg-red-400";

  return (
    <div className="bg-white border border-slate-200 rounded-lg p-4">
      <div className="flex items-start justify-between mb-2">
        <div>
          <div className="font-medium text-slate-900 text-sm">{label}</div>
          <div className="text-xs text-slate-400 mt-0.5 leading-tight">{METRIC_DESCRIPTIONS[metricKey]}</div>
        </div>
        <span className={`ml-2 shrink-0 text-xs font-bold px-2 py-0.5 rounded ${GRADE_COLORS[data.grade] ?? "bg-slate-100 text-slate-600"}`}>
          {data.grade}
        </span>
      </div>
      <div className="flex items-baseline gap-1 mt-3">
        <span className="text-2xl font-bold text-slate-900">{pct}%</span>
        <CIPill ci={data.ci} />
      </div>
      <div className="mt-2 h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all ${barColor}`} style={{ width: `${Math.min(100, data.value * 100)}%` }} />
      </div>
      <div className="text-xs text-slate-500 mt-1.5 italic">{data.interpretation}</div>
    </div>
  );
}

// ── Leaderboard table ─────────────────────────────────────────────────────────

function LeaderboardTable({ rows, onSelectModel }: { rows: LeaderboardRow[]; onSelectModel: (name: string) => void }) {
  if (!rows.length) {
    return (
      <div className="py-12 text-center text-slate-400">
        <div className="text-3xl mb-2">🏆</div>
        <p className="text-sm font-medium text-slate-600">No models ranked yet</p>
        <p className="text-xs mt-1">Compute frontier metrics to populate the leaderboard.</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-100">
            <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wide w-8">#</th>
            <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Model</th>
            <th className="text-center px-3 py-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Score</th>
            <th className="text-center px-3 py-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Autonomy</th>
            <th className="text-center px-3 py-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Adaptivity</th>
            <th className="text-center px-3 py-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Efficiency</th>
            <th className="text-center px-3 py-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Generalization</th>
            <th className="text-center px-3 py-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Grade</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(row => (
            <tr key={row.model_name}
              className="border-b border-slate-50 hover:bg-slate-50 cursor-pointer transition-colors"
              onClick={() => onSelectModel(row.model_name)}>
              <td className="px-4 py-3 text-slate-400 font-mono text-xs">
                {row.rank === 1 ? "🥇" : row.rank === 2 ? "🥈" : row.rank === 3 ? "🥉" : `#${row.rank}`}
              </td>
              <td className="px-4 py-3">
                <div className="font-medium text-slate-900">{row.model_name}</div>
                <div className="text-xs text-slate-400">{row.frontier_grade_interpretation}</div>
              </td>
              {(["composite_frontier_score", "autonomy", "adaptivity", "efficiency", "generalization"] as const).map(k => {
                const v = row[k];
                const color = v >= 0.8 ? "text-green-600" : v >= 0.65 ? "text-blue-600" : v >= 0.45 ? "text-amber-600" : "text-red-500";
                return (
                  <td key={k} className={`px-3 py-3 text-center font-mono font-semibold text-sm ${color}`}>
                    {(v * 100).toFixed(1)}%
                  </td>
                );
              })}
              <td className="px-3 py-3 text-center">
                <span className={`text-xs font-bold px-2 py-0.5 rounded ${GRADE_COLORS[row.frontier_grade] ?? "bg-slate-100"}`}>
                  {row.frontier_grade}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Trend chart ───────────────────────────────────────────────────────────────

function TrendChart({ model, trend }: { model: string; trend: TrendPoint[] }) {
  const data = trend.map((t, i) => ({
    version: t.version || `v${i + 1}`,
    Composite: Math.round(t.composite_frontier_score * 100),
    Autonomy: Math.round(t.autonomy * 100),
    Adaptivity: Math.round(t.adaptivity * 100),
    Efficiency: Math.round(t.efficiency * 100),
    Generalization: Math.round(t.generalization * 100),
  }));

  const COLORS = { Composite: "#1e293b", Autonomy: "#3b82f6", Adaptivity: "#8b5cf6", Efficiency: "#10b981", Generalization: "#f59e0b" };

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-6">
      <h3 className="font-medium text-slate-900 mb-1 text-sm">Metric Trend — {model}</h3>
      <p className="text-xs text-slate-400 mb-4">Frontier metric evolution over model versions</p>
      {trend.length < 2 ? (
        <div className="text-center py-8 text-slate-400 text-xs">Submit metrics for multiple versions to see the trend.</div>
      ) : (
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={data} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis dataKey="version" tick={{ fontSize: 11, fill: "#64748b" }} />
            <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: "#94a3b8" }} unit="%" />
            <Tooltip formatter={(v: number) => `${v}%`} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            {(Object.entries(COLORS) as [string, string][]).map(([key, color]) => (
              <Line
                key={key}
                type="monotone"
                dataKey={key}
                stroke={color}
                strokeWidth={key === "Composite" ? 2.5 : 1.5}
                dot={{ r: 3 }}
                strokeDasharray={key === "Composite" ? undefined : "4 2"}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

// ── Compute form ──────────────────────────────────────────────────────────────

interface FormState {
  modelName: string;
  version: string;
  steps: string;
  benchmarkScores: string;
  capabilityScore: string;
  propensityScore: string;
  safetyScore: string;
  maxSteps: string;
  taskCompleted: boolean;
}

const DEFAULT_FORM: FormState = {
  modelName: "",
  version: "",
  steps: DEFAULT_STEPS,
  benchmarkScores: DEFAULT_BENCHMARKS,
  capabilityScore: "0.75",
  propensityScore: "0.60",
  safetyScore: "0.90",
  maxSteps: "10",
  taskCompleted: true,
};

function ComputeForm({ onResult }: { onResult: (r: MetricsResult) => void }) {
  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const setField = (k: keyof FormState, v: string | boolean) =>
    setForm(prev => ({ ...prev, [k]: v }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      let parsedSteps: unknown;
      let parsedBenchmarks: unknown;
      try { parsedSteps = JSON.parse(form.steps); } catch { throw new Error("Invalid JSON in steps"); }
      try { parsedBenchmarks = JSON.parse(form.benchmarkScores); } catch { throw new Error("Invalid JSON in benchmark scores"); }

      const res = await fetch(`${API}/forecasting/metrics/compute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model_name: form.modelName,
          version: form.version || undefined,
          steps: parsedSteps,
          benchmark_scores: parsedBenchmarks,
          capability_score: parseFloat(form.capabilityScore),
          propensity_score: parseFloat(form.propensityScore),
          safety_score: parseFloat(form.safetyScore),
          max_steps: parseInt(form.maxSteps, 10),
          task_completed: form.taskCompleted,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error((err as { detail?: string }).detail ?? `HTTP ${res.status}`);
      }
      const result = await res.json() as MetricsResult;
      onResult(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-slate-700 mb-1">Model name *</label>
          <input
            required
            value={form.modelName}
            onChange={e => setField("modelName", e.target.value)}
            placeholder="e.g. gpt-4o"
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-700 mb-1">Version tag</label>
          <input
            value={form.version}
            onChange={e => setField("version", e.target.value)}
            placeholder="e.g. v1.0 (optional)"
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
        </div>
      </div>

      <div>
        <label className="block text-xs font-medium text-slate-700 mb-1">
          Trajectory steps (JSON array)
          <span className="text-slate-400 font-normal ml-1">— each step: tool_success, error_type, input_tokens, output_tokens, capability, step_type</span>
        </label>
        <textarea
          value={form.steps}
          onChange={e => setField("steps", e.target.value)}
          rows={6}
          className="w-full border border-slate-200 rounded-lg px-3 py-2 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-blue-400"
        />
      </div>

      <div>
        <label className="block text-xs font-medium text-slate-700 mb-1">Benchmark scores (JSON object)</label>
        <textarea
          value={form.benchmarkScores}
          onChange={e => setField("benchmarkScores", e.target.value)}
          rows={4}
          className="w-full border border-slate-200 rounded-lg px-3 py-2 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-blue-400"
        />
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {(["capabilityScore", "propensityScore", "safetyScore"] as const).map(k => (
          <div key={k}>
            <label className="block text-xs font-medium text-slate-700 mb-1 capitalize">
              {k.replace("Score", " score").replace("capability", "Capability").replace("propensity", "Propensity").replace("safety", "Safety")}
            </label>
            <input
              type="number" min="0" max="1" step="0.01"
              value={form[k]}
              onChange={e => setField(k, e.target.value)}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
            />
          </div>
        ))}
        <div>
          <label className="block text-xs font-medium text-slate-700 mb-1">Max steps</label>
          <input
            type="number" min="1"
            value={form.maxSteps}
            onChange={e => setField("maxSteps", e.target.value)}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
        </div>
      </div>

      <label className="flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
        <input
          type="checkbox"
          checked={form.taskCompleted}
          onChange={e => setField("taskCompleted", e.target.checked)}
          className="rounded"
        />
        Task completed
      </label>

      {error && (
        <div className="flex items-center gap-2 text-red-600 text-xs bg-red-50 border border-red-200 rounded-lg px-3 py-2">
          <AlertCircle size={14} />{error}
        </div>
      )}

      <button
        type="submit"
        disabled={loading}
        className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors disabled:opacity-50"
      >
        {loading ? <Spinner size={14} /> : <Plus size={14} />}
        Compute & add to leaderboard
      </button>
    </form>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function FrontierMetricsPage() {
  const [results, setResults] = useState<MetricsResult[]>([]);
  const [leaderboard, setLeaderboard] = useState<LeaderboardRow[]>([]);
  const [trend, setTrend] = useState<{ model: string; data: TrendPoint[] } | null>(null);
  const [activeTab, setActiveTab] = useState<"compute" | "leaderboard" | "radar" | "trend">("compute");
  const [selectedResult, setSelectedResult] = useState<MetricsResult | null>(null);
  const [trendLoading, setTrendLoading] = useState(false);

  const refreshLeaderboard = async () => {
    try {
      const res = await fetch(`${API}/forecasting/metrics/leaderboard`);
      if (res.ok) {
        const d = await res.json() as { rows: LeaderboardRow[] };
        setLeaderboard(d.rows);
      }
    } catch { /* ignore */ }
  };

  const handleResult = (result: MetricsResult) => {
    setResults(prev => {
      const existing = prev.findIndex(r => r.model_name === result.model_name);
      if (existing >= 0) {
        const next = [...prev];
        next[existing] = result;
        return next;
      }
      return [...prev, result];
    });
    setSelectedResult(result);
    refreshLeaderboard();
    setActiveTab("leaderboard");
  };

  const handleSelectModel = async (modelName: string) => {
    setTrendLoading(true);
    try {
      const res = await fetch(`${API}/forecasting/metrics/leaderboard/trend/${encodeURIComponent(modelName)}`);
      if (res.ok) {
        const d = await res.json() as { model_name: string; trend: TrendPoint[] };
        setTrend({ model: d.model_name, data: d.trend });
        setActiveTab("trend");
      }
    } catch { /* ignore */ }
    setTrendLoading(false);
  };

  const radarResults = useMemo(() => results.slice(0, 6), [results]);

  const TABS = [
    { key: "compute" as const, label: "Compute", icon: Plus },
    { key: "leaderboard" as const, label: "Leaderboard", icon: BarChart3 },
    { key: "radar" as const, label: "Radar chart", icon: BarChart3 },
    { key: "trend" as const, label: "Trend", icon: TrendingUp },
  ];

  return (
    <div>
      <PageHeader
        title="Frontier Metrics"
        description="Autonomy · Adaptivity · Efficiency · Generalization — M5 frontier evaluation suite."
      />
      <div className="p-4 sm:p-8 space-y-6">

        {/* Tabs */}
        <div className="flex gap-1 border-b border-slate-200">
          {TABS.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px ${
                activeTab === key
                  ? "border-blue-600 text-blue-600"
                  : "border-transparent text-slate-500 hover:text-slate-700"
              }`}
            >
              <Icon size={13} />{label}
              {key === "leaderboard" && leaderboard.length > 0 && (
                <span className="ml-1 text-[10px] bg-blue-100 text-blue-600 px-1.5 py-0.5 rounded-full">{leaderboard.length}</span>
              )}
            </button>
          ))}
        </div>

        {/* Compute tab */}
        {activeTab === "compute" && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-white border border-slate-200 rounded-xl p-6">
              <h2 className="font-medium text-slate-900 mb-4 text-sm">Compute frontier metrics</h2>
              <ComputeForm onResult={handleResult} />
            </div>

            {/* Metric definitions */}
            <div className="space-y-4">
              <h2 className="font-medium text-slate-900 text-sm">Metric definitions</h2>
              {METRIC_LABELS.map(label => {
                const key = label.toLowerCase() as MetricKey;
                return (
                  <div key={key} className="bg-white border border-slate-200 rounded-xl p-4">
                    <div className="font-medium text-slate-800 text-sm mb-1">{label}</div>
                    <p className="text-xs text-slate-500">{METRIC_DESCRIPTIONS[key]}</p>
                  </div>
                );
              })}
              <div className="bg-slate-50 border border-slate-200 rounded-xl p-4">
                <div className="font-medium text-slate-700 text-xs mb-2">Composite score formula</div>
                <code className="text-xs text-slate-600 font-mono">
                  composite = 0.3 × autonomy + 0.3 × adaptivity + 0.2 × efficiency + 0.2 × generalization
                </code>
              </div>
            </div>
          </div>
        )}

        {/* Leaderboard tab */}
        {activeTab === "leaderboard" && (
          <div className="space-y-6">
            {selectedResult && (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h2 className="font-medium text-slate-900 text-sm">
                    Last computed — {selectedResult.model_name}
                    <span className={`ml-2 text-xs font-bold px-2 py-0.5 rounded ${GRADE_COLORS[selectedResult.frontier_grade] ?? ""}`}>
                      {selectedResult.frontier_grade}
                    </span>
                  </h2>
                  <button
                    onClick={() => setSelectedResult(null)}
                    className="text-xs text-slate-400 hover:text-slate-600 flex items-center gap-1"
                  >
                    <Trash2 size={12} /> Clear
                  </button>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {METRIC_LABELS.map(label => {
                    const key = label.toLowerCase() as MetricKey;
                    return <MetricCard key={key} label={label} metricKey={key} data={selectedResult[key]} />;
                  })}
                </div>
                {selectedResult.capability_breakdown.length > 0 && (
                  <div className="bg-white border border-slate-200 rounded-xl p-4">
                    <h3 className="font-medium text-slate-900 text-sm mb-3">Per-capability breakdown</h3>
                    <CapabilityBreakdownTable breakdown={selectedResult.capability_breakdown} />
                  </div>
                )}
              </div>
            )}

            <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
              <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
                <h2 className="font-medium text-slate-900 text-sm">Frontier metrics leaderboard</h2>
                <button onClick={refreshLeaderboard} className="text-xs text-blue-600 hover:underline">Refresh</button>
              </div>
              <LeaderboardTable rows={leaderboard} onSelectModel={handleSelectModel} />
            </div>
          </div>
        )}

        {/* Radar tab */}
        {activeTab === "radar" && (
          <div className="space-y-6">
            {radarResults.length === 0 ? (
              <div className="py-16 text-center text-slate-400">
                <div className="text-3xl mb-2">📡</div>
                <p className="text-sm font-medium text-slate-600">No results to display</p>
                <p className="text-xs mt-1">Compute frontier metrics for at least one model first.</p>
                <button onClick={() => setActiveTab("compute")} className="mt-3 text-xs text-blue-600 hover:underline">
                  Go to Compute →
                </button>
              </div>
            ) : (
              <>
                <FrontierRadar results={radarResults} />
                {selectedResult && selectedResult.capability_breakdown.length > 0 && (
                  <div className="bg-white border border-slate-200 rounded-xl p-6">
                    <h3 className="font-medium text-slate-900 text-sm mb-3">
                      Per-capability breakdown — {selectedResult.model_name}
                    </h3>
                    <CapabilityBreakdownTable breakdown={selectedResult.capability_breakdown} />
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* Trend tab */}
        {activeTab === "trend" && (
          <div>
            {trendLoading ? (
              <div className="flex justify-center py-16"><Spinner size={24} /></div>
            ) : trend ? (
              <TrendChart model={trend.model} trend={trend.data} />
            ) : (
              <div className="py-16 text-center text-slate-400">
                <div className="text-3xl mb-2">📈</div>
                <p className="text-sm font-medium text-slate-600">No trend data</p>
                <p className="text-xs mt-1">Click a model in the leaderboard to view its metric trend over versions.</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
