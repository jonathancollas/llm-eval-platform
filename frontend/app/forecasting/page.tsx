"use client";
import { useState, useMemo } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { useApi } from "@/lib/useApi";
import { forecastingApi } from "@/lib/api";
import { API_BASE } from "@/lib/config";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ReferenceLine, ResponsiveContainer, Area, AreaChart,
  BarChart, Bar,
} from "recharts";
import {
  TrendingUp, TrendingDown, Minus, AlertTriangle, CheckCircle2,
  Activity, Zap, BarChart2, RefreshCw, ChevronDown, ChevronRight,
} from "lucide-react";

// ── Types ─────────────────────────────────────────────────────────────────────
interface ForecastResult {
  capability: string;
  current_score: number;
  forecast_score: number;
  uncertainty_lower: number;
  uncertainty_upper: number;
  trend_direction: "improving" | "declining" | "plateau" | "emergent";
  confidence: "high" | "medium" | "low";
  scaling_law_type: string;
  capability_score: number;
  propensity_score: number;
  gap_to_frontier: number;
  forecast_horizon_label: string;
}

interface ReportData {
  benchmarks_analyzed: number;
  capabilities_covered: string[];
  forecasts: ForecastResult[];
  overall_trend: string;
  riskiest_capability: string;
  plateau_capabilities: string[];
  emerging_capabilities: string[];
  recommendations: string[];
  frontier_gaps: Record<string, number>;
  calibration_mae: number;
  created_at: string;
}

interface CalibrationData {
  records: Array<{
    capability: string;
    predicted_score: number;
    actual_score: number;
    absolute_error: number;
    horizon_label: string;
    recorded_at: string;
  }>;
  overall_mae: number;
  by_capability: Record<string, { count: number; mae: number }>;
}

// ── Demo seed data — used when no real data is available ──────────────────────
const DEMO_DATA_POINTS = [
  { model_name: "gpt-3", benchmark_name: "mmlu", capability: "reasoning", score: 0.45, date: "2020-06-01", score_type: "capability" },
  { model_name: "gpt-3.5", benchmark_name: "mmlu", capability: "reasoning", score: 0.58, date: "2022-03-01", score_type: "capability" },
  { model_name: "gpt-4", benchmark_name: "mmlu", capability: "reasoning", score: 0.73, date: "2023-03-01", score_type: "capability" },
  { model_name: "gpt-4o", benchmark_name: "mmlu", capability: "reasoning", score: 0.82, date: "2024-05-01", score_type: "capability" },
  { model_name: "gpt-4o-mini", benchmark_name: "mmlu", capability: "reasoning", score: 0.78, date: "2024-07-01", score_type: "capability" },
  { model_name: "gpt-3", benchmark_name: "cybersec", capability: "cybersecurity", score: 0.30, date: "2020-06-01", score_type: "capability" },
  { model_name: "gpt-3.5", benchmark_name: "cybersec", capability: "cybersecurity", score: 0.42, date: "2022-03-01", score_type: "capability" },
  { model_name: "gpt-4", benchmark_name: "cybersec", capability: "cybersecurity", score: 0.61, date: "2023-03-01", score_type: "capability" },
  { model_name: "gpt-4o", benchmark_name: "cybersec", capability: "cybersecurity", score: 0.72, date: "2024-05-01", score_type: "capability" },
  { model_name: "gpt-3", benchmark_name: "safety", capability: "safety", score: 0.60, date: "2020-06-01", score_type: "propensity" },
  { model_name: "gpt-3.5", benchmark_name: "safety", capability: "safety", score: 0.68, date: "2022-03-01", score_type: "propensity" },
  { model_name: "gpt-4", benchmark_name: "safety", capability: "safety", score: 0.78, date: "2023-03-01", score_type: "propensity" },
  { model_name: "gpt-4o", benchmark_name: "safety", capability: "safety", score: 0.83, date: "2024-05-01", score_type: "propensity" },
  { model_name: "gpt-3", benchmark_name: "hf-agentic", capability: "agentic", score: 0.20, date: "2020-06-01", score_type: "capability" },
  { model_name: "gpt-3.5", benchmark_name: "hf-agentic", capability: "agentic", score: 0.34, date: "2022-03-01", score_type: "capability" },
  { model_name: "gpt-4", benchmark_name: "hf-agentic", capability: "agentic", score: 0.55, date: "2023-03-01", score_type: "capability" },
  { model_name: "gpt-4o", benchmark_name: "hf-agentic", capability: "agentic", score: 0.68, date: "2024-05-01", score_type: "capability" },
];

const CAPABILITY_COLORS: Record<string, string> = {
  reasoning: "#3b82f6",
  cybersecurity: "#ef4444",
  safety: "#10b981",
  agentic: "#8b5cf6",
  knowledge: "#f59e0b",
  instruction_following: "#06b6d4",
  multimodal: "#f97316",
};

const CONFIDENCE_COLORS = { high: "text-green-700 bg-green-50 border-green-200", medium: "text-amber-700 bg-amber-50 border-amber-200", low: "text-red-700 bg-red-50 border-red-200" };
const TREND_ICONS = { improving: TrendingUp, declining: TrendingDown, plateau: Minus, emergent: Zap };
const TREND_COLORS = { improving: "text-green-600", declining: "text-red-600", plateau: "text-slate-500", emergent: "text-purple-600" };

function fmt(v: number) { return `${(v * 100).toFixed(1)}%`; }
function scoreColor(v: number) {
  if (v >= 0.8) return "text-green-700";
  if (v >= 0.6) return "text-amber-600";
  return "text-red-600";
}

// ── Scaling Curve Chart ───────────────────────────────────────────────────────
function ScalingCurveChart({ forecasts }: { forecasts: ForecastResult[] }) {
  const data = forecasts.map((f, i) => ({
    name: f.capability.replace("_", " "),
    current: Math.round(f.current_score * 100),
    forecast: Math.round(f.forecast_score * 100),
    lower: Math.round(f.uncertainty_lower * 100),
    upper: Math.round(f.uncertainty_upper * 100),
  }));

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5">
      <h3 className="font-semibold text-slate-900 text-sm mb-4">Current vs Forecast Score by Capability</h3>
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={data} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
          <XAxis dataKey="name" tick={{ fontSize: 11, fill: "#64748b" }} />
          <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: "#94a3b8" }} unit="%" />
          <Tooltip formatter={(v: number) => `${v}%`} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="current" name="Current" fill="#3b82f6" radius={[3, 3, 0, 0]} />
          <Bar dataKey="forecast" name="Forecast" fill="#8b5cf6" radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Trend Chart for one capability over time ──────────────────────────────────
function TrendChart({ capability, dataPoints }: { capability: string; dataPoints: typeof DEMO_DATA_POINTS }) {
  const pts = dataPoints
    .filter(d => d.capability === capability)
    .sort((a, b) => a.date.localeCompare(b.date));

  const color = CAPABILITY_COLORS[capability] ?? "#64748b";

  const chartData = pts.map((p, i) => ({
    idx: i,
    date: p.date.slice(0, 7),
    score: Math.round(p.score * 100),
    model: p.model_name,
  }));

  if (chartData.length < 2) {
    return (
      <div className="h-32 flex items-center justify-center text-xs text-slate-400">
        Not enough historical data
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={140}>
      <LineChart data={chartData} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
        <XAxis dataKey="date" tick={{ fontSize: 9, fill: "#94a3b8" }} />
        <YAxis domain={[0, 100]} tick={{ fontSize: 9, fill: "#94a3b8" }} unit="%" />
        <Tooltip
          formatter={(v: number) => `${v}%`}
          labelFormatter={(_, payload) => payload?.[0]?.payload?.model ?? ""}
        />
        <Line type="monotone" dataKey="score" stroke={color} strokeWidth={2}
          dot={{ fill: color, r: 3 }} name="Score" />
      </LineChart>
    </ResponsiveContainer>
  );
}

// ── Frontier Gap Chart ────────────────────────────────────────────────────────
function FrontierGapChart({ gaps }: { gaps: Record<string, number> }) {
  const data = Object.entries(gaps)
    .sort((a, b) => b[1] - a[1])
    .map(([cap, gap]) => ({
      name: cap.replace("_", " "),
      gap: Math.round(gap * 100),
      fill: gap > 0.2 ? "#ef4444" : gap > 0.1 ? "#f59e0b" : "#10b981",
    }));

  if (!data.length) return null;

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5">
      <h3 className="font-semibold text-slate-900 text-sm mb-1">Capability Gap to Frontier</h3>
      <p className="text-xs text-slate-400 mb-4">Distance from current score to best observed score per capability</p>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 20, left: 80, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" horizontal={false} />
          <XAxis type="number" domain={[0, 50]} tick={{ fontSize: 10, fill: "#94a3b8" }} unit="%" />
          <YAxis type="category" dataKey="name" tick={{ fontSize: 11, fill: "#64748b" }} width={75} />
          <Tooltip formatter={(v: number) => `${v}%`} />
          <Bar dataKey="gap" name="Gap" radius={[0, 3, 3, 0]}>
            {data.map((entry, i) => (
              <rect key={i} fill={entry.fill} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Calibration Chart ─────────────────────────────────────────────────────────
function CalibrationChart({ records }: { records: CalibrationData["records"] }) {
  if (!records.length) return null;
  const data = records.map(r => ({
    predicted: Math.round(r.predicted_score * 100),
    actual: Math.round(r.actual_score * 100),
    error: Math.round(r.absolute_error * 100),
    capability: r.capability,
    label: r.horizon_label,
  }));

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5">
      <h3 className="font-semibold text-slate-900 text-sm mb-4">Forecast Calibration — Predicted vs Actual</h3>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
          <XAxis dataKey="label" tick={{ fontSize: 10, fill: "#94a3b8" }} />
          <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: "#94a3b8" }} unit="%" />
          <Tooltip formatter={(v: number) => `${v}%`} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line type="monotone" dataKey="predicted" stroke="#3b82f6" strokeWidth={2} name="Predicted" dot={{ r: 3 }} />
          <Line type="monotone" dataKey="actual" stroke="#10b981" strokeWidth={2} name="Actual" dot={{ r: 3 }} />
          <Line type="monotone" dataKey="error" stroke="#ef4444" strokeDasharray="4 2" strokeWidth={1.5} name="Abs Error" dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Forecast Card ─────────────────────────────────────────────────────────────
function ForecastCard({
  forecast,
  dataPoints,
  expanded,
  onToggle,
}: {
  forecast: ForecastResult;
  dataPoints: typeof DEMO_DATA_POINTS;
  expanded: boolean;
  onToggle: () => void;
}) {
  const TrendIcon = TREND_ICONS[forecast.trend_direction] ?? Minus;
  const trendColor = TREND_COLORS[forecast.trend_direction] ?? "text-slate-500";
  const confidenceCls = CONFIDENCE_COLORS[forecast.confidence] ?? CONFIDENCE_COLORS.low;
  const capColor = CAPABILITY_COLORS[forecast.capability] ?? "#64748b";

  const delta = forecast.forecast_score - forecast.current_score;
  const deltaSign = delta >= 0 ? "+" : "";

  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
      <button
        className="w-full flex items-center gap-3 px-5 py-4 hover:bg-slate-50 transition-colors text-left"
        onClick={onToggle}
      >
        <div
          className="w-2.5 h-2.5 rounded-full shrink-0"
          style={{ background: capColor }}
        />
        <div className="flex-1 min-w-0">
          <div className="font-medium text-slate-900 text-sm capitalize">
            {forecast.capability.replace(/_/g, " ")}
          </div>
          <div className="text-xs text-slate-400 mt-0.5">
            {forecast.scaling_law_type} fit · {forecast.forecast_horizon_label}
          </div>
        </div>

        {/* Current → Forecast */}
        <div className="flex items-center gap-1.5 shrink-0">
          <span className={`text-sm font-semibold ${scoreColor(forecast.current_score)}`}>
            {fmt(forecast.current_score)}
          </span>
          <span className="text-slate-300">→</span>
          <span className={`text-sm font-semibold ${scoreColor(forecast.forecast_score)}`}>
            {fmt(forecast.forecast_score)}
          </span>
          <span className={`text-xs ml-1 ${delta >= 0 ? "text-green-600" : "text-red-600"}`}>
            ({deltaSign}{fmt(delta)})
          </span>
        </div>

        {/* Trend + confidence */}
        <div className="flex items-center gap-2 shrink-0 ml-2">
          <TrendIcon size={14} className={trendColor} />
          <span className={`text-[10px] px-1.5 py-0.5 rounded border font-medium ${confidenceCls}`}>
            {forecast.confidence}
          </span>
        </div>

        {expanded ? <ChevronDown size={14} className="text-slate-400 shrink-0" /> : <ChevronRight size={14} className="text-slate-400 shrink-0" />}
      </button>

      {expanded && (
        <div className="border-t border-slate-100 px-5 pt-4 pb-5 space-y-4 bg-slate-50/50">
          {/* Trend chart */}
          <div>
            <div className="text-[11px] font-medium text-slate-500 uppercase tracking-wide mb-2">
              Historical Trend
            </div>
            <TrendChart capability={forecast.capability} dataPoints={dataPoints} />
          </div>

          {/* Metrics grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { label: "Capability Score", value: fmt(forecast.capability_score), color: "text-blue-700" },
              { label: "Propensity Score", value: fmt(forecast.propensity_score), color: "text-violet-700" },
              { label: "Uncertainty Band", value: `${fmt(forecast.uncertainty_lower)}–${fmt(forecast.uncertainty_upper)}`, color: "text-slate-700" },
              { label: "Gap to Frontier", value: fmt(forecast.gap_to_frontier), color: forecast.gap_to_frontier > 0.1 ? "text-amber-700" : "text-green-700" },
            ].map(({ label, value, color }) => (
              <div key={label} className="bg-white rounded-lg border border-slate-200 px-3 py-2">
                <div className="text-[10px] text-slate-400 mb-0.5">{label}</div>
                <div className={`text-sm font-semibold ${color}`}>{value}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function ForecastingPage() {
  const [report, setReport] = useState<ReportData | null>(null);
  const [calibration, setCalibration] = useState<CalibrationData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedCap, setExpandedCap] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"forecasts" | "gaps" | "calibration" | "tasks">("forecasts");
  const [selectedCapability, setSelectedCapability] = useState<string>("reasoning");

  const { data: capabilities } = useApi<string[]>("/forecasting/capabilities");
  const { data: lhTasks } = useApi<any[]>("/forecasting/long-horizon/tasks");

  const runAnalysis = async () => {
    setLoading(true);
    setError(null);
    try {
      const [rep, cal] = await Promise.all([
        forecastingApi.report(DEMO_DATA_POINTS),
        forecastingApi.calibrationHistory(),
      ]);
      setReport(rep);
      setCalibration(cal);
    } catch (e: any) {
      setError(e.message ?? "Failed to run analysis");
    } finally {
      setLoading(false);
    }
  };

  const forecastForCapability = async (capability: string) => {
    if (!capability) return;
    const pts = DEMO_DATA_POINTS.filter(d => d.capability === capability);
    if (pts.length < 2) return;
    setLoading(true);
    try {
      const res = await forecastingApi.forecast(pts, capability, 3);
      // merge result into report if it exists
      if (report) {
        const updated = { ...report };
        const idx = updated.forecasts.findIndex(f => f.capability === capability);
        if (idx >= 0) updated.forecasts[idx] = res;
        else updated.forecasts.push(res);
        setReport(updated);
      }
    } catch (err) { console.warn("[error]", err); }
    setLoading(false);
  };

  const TABS = [
    { id: "forecasts", label: "Scaling Forecasts", icon: TrendingUp },
    { id: "gaps", label: "Frontier Gaps", icon: AlertTriangle },
    { id: "calibration", label: "Calibration Tracking", icon: CheckCircle2 },
    { id: "tasks", label: "Long-Horizon Tasks", icon: Activity },
  ] as const;

  return (
    <div className="p-4 sm:p-8 max-w-6xl space-y-6">
      <PageHeader
        title="Capability Forecasting"
        description="Scaling law fitting · trend projection · frontier gap analysis · calibration tracking"
        action={
          <button
            onClick={runAnalysis}
            disabled={loading}
            className="flex items-center gap-2 bg-violet-700 text-white px-4 py-2 rounded-lg text-sm hover:bg-violet-800 disabled:opacity-50"
          >
            {loading ? <Spinner size={14} /> : <RefreshCw size={14} />}
            Run Analysis
          </button>
        }
      />

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Summary stats */}
      {report && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: "Capabilities Covered", value: report.capabilities_covered.length, color: "text-violet-700 bg-violet-50 border-violet-100" },
            { label: "Benchmarks Analyzed", value: report.benchmarks_analyzed, color: "text-blue-700 bg-blue-50 border-blue-100" },
            { label: "Emerging Capabilities", value: report.emerging_capabilities.length, color: "text-purple-700 bg-purple-50 border-purple-100" },
            { label: "Calibration MAE", value: `${(report.calibration_mae * 100).toFixed(1)}%`, color: "text-slate-700 bg-slate-50 border-slate-200", isText: true },
          ].map(({ label, value, color, isText }) => (
            <div key={label} className={`border rounded-xl p-4 ${color}`}>
              <div className="text-2xl font-bold mb-0.5">{isText ? value : value}</div>
              <div className="text-[11px] opacity-70">{label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Scaling curve chart */}
      {report && report.forecasts.length > 0 && (
        <ScalingCurveChart forecasts={report.forecasts} />
      )}

      {/* Tabs */}
      <div className="border-b border-slate-200">
        <div className="flex gap-0 overflow-x-auto">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              className={`flex items-center gap-1.5 px-4 py-2.5 text-sm whitespace-nowrap border-b-2 transition-colors ${
                activeTab === id
                  ? "border-violet-600 text-violet-700 font-medium"
                  : "border-transparent text-slate-500 hover:text-slate-700"
              }`}
            >
              <Icon size={13} />
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* ── Tab: Scaling Forecasts ── */}
      {activeTab === "forecasts" && (
        <div className="space-y-3">
          {!report ? (
            <div className="bg-white border border-slate-200 rounded-xl p-10 text-center space-y-3">
              <BarChart2 size={32} className="mx-auto text-slate-300" />
              <div className="text-sm text-slate-500">
                Click <strong>Run Analysis</strong> to generate scaling law forecasts
              </div>
              <div className="text-xs text-slate-400">
                Uses demo historical data (GPT-3 → GPT-4o trajectory) to fit scaling laws
              </div>
            </div>
          ) : report.forecasts.length === 0 ? (
            <div className="text-sm text-slate-400 text-center py-8">No forecasts generated</div>
          ) : (
            report.forecasts.map(f => (
              <ForecastCard
                key={f.capability}
                forecast={f}
                dataPoints={DEMO_DATA_POINTS}
                expanded={expandedCap === f.capability}
                onToggle={() => setExpandedCap(v => v === f.capability ? null : f.capability)}
              />
            ))
          )}

          {report && (
            <div className="bg-violet-50 border border-violet-100 rounded-xl p-4 text-sm">
              <div className="font-medium text-violet-800 mb-1">Overall Trend: {report.overall_trend}</div>
              {report.emerging_capabilities.length > 0 && (
                <div className="text-violet-700 text-xs">
                  <Zap size={11} className="inline mr-1" />
                  Emergent: {report.emerging_capabilities.join(", ")}
                </div>
              )}
              {report.recommendations.map((r, i) => (
                <div key={i} className="text-violet-600 text-xs mt-0.5">· {r}</div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Tab: Frontier Gaps ── */}
      {activeTab === "gaps" && (
        <div className="space-y-4">
          {!report ? (
            <div className="text-sm text-slate-400 text-center py-8">
              Run analysis first to see frontier gaps
            </div>
          ) : (
            <>
              <FrontierGapChart gaps={report.frontier_gaps} />

              <div className="bg-white border border-slate-200 rounded-xl divide-y divide-slate-100">
                {Object.entries(report.frontier_gaps)
                  .sort((a, b) => b[1] - a[1])
                  .map(([cap, gap]) => (
                    <div key={cap} className="flex items-center px-5 py-3 gap-3">
                      <div
                        className="w-2 h-2 rounded-full shrink-0"
                        style={{ background: CAPABILITY_COLORS[cap] ?? "#64748b" }}
                      />
                      <div className="flex-1 text-sm capitalize text-slate-700">
                        {cap.replace(/_/g, " ")}
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="w-24 h-2 bg-slate-100 rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full"
                            style={{
                              width: `${Math.min(100, gap * 300)}%`,
                              background: gap > 0.2 ? "#ef4444" : gap > 0.1 ? "#f59e0b" : "#10b981",
                            }}
                          />
                        </div>
                        <span className={`text-sm font-semibold ${gap > 0.1 ? "text-amber-700" : "text-green-700"}`}>
                          {fmt(gap)}
                        </span>
                      </div>
                    </div>
                  ))}
              </div>

              <div className="text-xs text-slate-400 text-center">
                Gap = frontier score − current score. Zero means at frontier.
              </div>
            </>
          )}
        </div>
      )}

      {/* ── Tab: Calibration Tracking ── */}
      {activeTab === "calibration" && (
        <div className="space-y-4">
          {calibration && calibration.records.length > 0 ? (
            <>
              <CalibrationChart records={calibration.records} />

              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {Object.entries(calibration.by_capability).map(([cap, stats]) => (
                  <div key={cap} className="bg-white border border-slate-200 rounded-xl p-4">
                    <div className="text-xs text-slate-400 mb-1 capitalize">{cap.replace(/_/g, " ")}</div>
                    <div className="text-lg font-bold text-slate-900">{fmt(stats.mae)}</div>
                    <div className="text-[10px] text-slate-400">MAE · {stats.count} records</div>
                  </div>
                ))}
              </div>

              <div className="bg-slate-50 border border-slate-200 rounded-xl overflow-hidden">
                <table className="w-full text-xs">
                  <thead className="bg-slate-100 text-slate-500">
                    <tr>
                      <th className="text-left px-4 py-2">Capability</th>
                      <th className="text-right px-4 py-2">Predicted</th>
                      <th className="text-right px-4 py-2">Actual</th>
                      <th className="text-right px-4 py-2">Error</th>
                      <th className="text-right px-4 py-2">Horizon</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {calibration.records.map((r, i) => (
                      <tr key={i} className="hover:bg-white">
                        <td className="px-4 py-2 text-slate-700 capitalize">{r.capability}</td>
                        <td className="px-4 py-2 text-right text-blue-700 font-mono">{fmt(r.predicted_score)}</td>
                        <td className="px-4 py-2 text-right text-green-700 font-mono">{fmt(r.actual_score)}</td>
                        <td className={`px-4 py-2 text-right font-mono ${r.absolute_error > 0.1 ? "text-red-600" : "text-slate-600"}`}>
                          {fmt(r.absolute_error)}
                        </td>
                        <td className="px-4 py-2 text-right text-slate-400">{r.horizon_label}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <div className="bg-white border border-slate-200 rounded-xl p-10 text-center space-y-2">
              <CheckCircle2 size={28} className="mx-auto text-slate-300" />
              <div className="text-sm text-slate-500">No calibration records yet</div>
              <div className="text-xs text-slate-400">
                Use <code className="bg-slate-100 px-1 rounded">POST /forecasting/calibration/record</code> to log forecast accuracy over time
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Tab: Long-Horizon Tasks ── */}
      {activeTab === "tasks" && (
        <div className="space-y-3">
          {!lhTasks || lhTasks.length === 0 ? (
            <div className="text-sm text-slate-400 text-center py-8">No tasks found</div>
          ) : (
            lhTasks.map(task => (
              <div key={task.task_id} className="bg-white border border-slate-200 rounded-xl p-5">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-slate-900 text-sm">{task.name}</div>
                    <div className="text-xs text-slate-400 mt-0.5">{task.description}</div>
                  </div>
                  <div className="flex gap-2 shrink-0">
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-violet-50 text-violet-700 border border-violet-200 font-medium capitalize">
                      {task.domain}
                    </span>
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200">
                      {task.difficulty}
                    </span>
                  </div>
                </div>
                {task.sub_goals && (
                  <div className="mt-3 space-y-1">
                    {task.sub_goals.slice(0, 3).map((sg: any, i: number) => (
                      <div key={i} className="text-xs text-slate-500 flex items-center gap-1.5">
                        <span className="text-slate-300">·</span>
                        <span>{sg.description}</span>
                        {sg.is_critical && (
                          <span className="text-[9px] bg-red-50 text-red-600 border border-red-100 px-1 rounded">critical</span>
                        )}
                      </div>
                    ))}
                    {task.sub_goals.length > 3 && (
                      <div className="text-xs text-slate-400">+{task.sub_goals.length - 3} more steps</div>
                    )}
                  </div>
                )}
              </div>
            ))
          )}        </div>
      )}
    </div>
  );
}
