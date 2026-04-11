"use client";
import { useEffect, useState, useCallback } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { AppErrorBoundary } from "@/components/AppErrorBoundary";
import { useModels } from "@/lib/useApi";
import { API_BASE } from "@/lib/config";
import {
  Activity, AlertTriangle, Shield, Clock, Zap,
  CheckCircle2, XCircle, RefreshCw, TrendingDown, TrendingUp, Minus,
} from "lucide-react";

// ── Types ─────────────────────────────────────────────────────────────────────

interface NISTDimension {
  dimension: string; score: number; status: "healthy" | "warning" | "critical";
  signal: string; reference: string;
}
interface DriftAlert {
  alert_id: string; alert_type: string; severity: string;
  metric: string; baseline: number; current: number; delta: number;
  description: string; recommended_action: string; nist_dimension: string;
}
interface MonitoringReport {
  model_id: number | null; model_name: string; window_hours: number;
  n_inferences: number; generated_at: string;
  health: { overall_score: number; status: string };
  nist_dimensions: NISTDimension[];
  metrics: {
    avg_score: number | null; avg_latency_ms: number;
    error_rate: number; safety_flag_rate: number;
    refusal_rate: number; score_trend: string; score_volatility: number;
  };
  drift_alerts: DriftAlert[];
  judge_monitoring: { coverage: number; validity_warning: string | null };
}

interface FleetModel {
  model_id: number; model_name: string; n_inferences: number;
  health_status: string; overall_health: number; worst_dimension: string | null;
  top_alert: { type: string; severity: string; description: string } | null;
  metrics: { avg_score: number | null; error_rate: number; safety_flag_rate: number; score_trend: string };
}
interface FleetDashboard {
  models: FleetModel[]; window_hours: number; n_active_models: number;
  critical_count: number; warning_count: number; generated_at: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const statusColor = (s: string) =>
  s === "critical" ? "text-red-700 bg-red-50 border-red-200"
  : s === "warning" ? "text-yellow-700 bg-yellow-50 border-yellow-200"
  : s === "healthy" ? "text-green-700 bg-green-50 border-green-200"
  : "text-slate-500 bg-slate-50 border-slate-200";

const statusDot = (s: string) =>
  s === "critical" ? "bg-red-500" : s === "warning" ? "bg-yellow-400" : "bg-green-500";

const severityColor = (s: string) =>
  s === "critical" ? "border-red-300 bg-red-50 text-red-800"
  : s === "high" ? "border-orange-300 bg-orange-50 text-orange-800"
  : "border-yellow-200 bg-yellow-50 text-yellow-800";

const DIMENSION_LABELS: Record<string, string> = {
  functionality_drift: "Functionality Drift",
  operational_reliability: "Operational Reliability",
  human_factors: "Human Factors",
  security_posture: "Security Posture",
  fairness_bias: "Fairness & Bias",
  societal_impact: "Societal Impact",
};

function TrendIcon({ trend }: { trend: string }) {
  if (trend === "improving") return <TrendingUp size={12} className="text-green-500" />;
  if (trend === "degrading") return <TrendingDown size={12} className="text-red-500" />;
  return <Minus size={12} className="text-slate-400" />;
}

function ScoreGauge({ score, size = "md" }: { score: number; size?: "sm" | "md" }) {
  const pct = Math.round(score * 100);
  const color = score >= 0.75 ? "#22c55e" : score >= 0.5 ? "#f59e0b" : "#ef4444";
  const r = size === "sm" ? 20 : 28;
  const circ = 2 * Math.PI * r;
  const dash = circ * score;
  return (
    <svg width={r * 2 + 8} height={r * 2 + 8} viewBox={`0 0 ${r * 2 + 8} ${r * 2 + 8}`}>
      <circle cx={r + 4} cy={r + 4} r={r} fill="none" stroke="#e2e8f0" strokeWidth={size === "sm" ? 4 : 6} />
      <circle cx={r + 4} cy={r + 4} r={r} fill="none" stroke={color} strokeWidth={size === "sm" ? 4 : 6}
        strokeDasharray={`${dash} ${circ}`} strokeDashoffset={circ / 4}
        strokeLinecap="round" transform={`rotate(-90 ${r + 4} ${r + 4})`} style={{ transition: "stroke-dasharray 0.5s" }} />
      <text x={r + 4} y={r + 6} textAnchor="middle" fontSize={size === "sm" ? 10 : 13}
        fontWeight="bold" fill={color}>{pct}</text>
    </svg>
  );
}

// ── NIST Dashboard ────────────────────────────────────────────────────────────

function NISTDashboard({ report }: { report: MonitoringReport }) {
  return (
    <div className="space-y-5">
      {/* Health header */}
      <div className={`rounded-xl p-5 border flex items-center justify-between ${statusColor(report.health.status)}`}>
        <div>
          <h2 className="font-bold text-base">{report.model_name}</h2>
          <p className="text-xs mt-0.5 opacity-70">
            {report.n_inferences.toLocaleString()} inferences · {report.window_hours}h window ·{" "}
            {new Date(report.generated_at).toLocaleTimeString()}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <ScoreGauge score={report.health.overall_score} />
          <div className="text-right">
            <div className="text-xs font-medium uppercase tracking-wide opacity-70">Overall Health</div>
            <div className="text-sm font-bold capitalize">{report.health.status}</div>
          </div>
        </div>
      </div>

      {/* NIST 6 dimensions */}
      <div>
        <div className="text-xs font-medium text-slate-500 mb-2 flex items-center gap-2">
          NIST AI 800-4 (March 2026) — 6 Monitoring Dimensions
        </div>
        <div className="grid grid-cols-2 gap-2">
          {report.nist_dimensions.map(d => (
            <div key={d.dimension} className={`rounded-xl p-3 border ${statusColor(d.status)}`}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium">{DIMENSION_LABELS[d.dimension] ?? d.dimension}</span>
                <div className="flex items-center gap-1.5">
                  <div className={`w-2 h-2 rounded-full ${statusDot(d.status)}`} />
                  <span className="text-xs font-bold">{Math.round(d.score * 100)}%</span>
                </div>
              </div>
              <div className="h-1 bg-white/50 rounded-full">
                <div className="h-1 rounded-full transition-all"
                  style={{ width: `${Math.round(d.score * 100)}%`, background: d.status === "healthy" ? "#22c55e" : d.status === "warning" ? "#f59e0b" : "#ef4444" }} />
              </div>
              <p className="text-[11px] mt-1.5 opacity-80 leading-tight">{d.signal}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Key metrics row */}
      <div className="grid grid-cols-4 gap-2">
        {[
          { label: "Avg Score", value: report.metrics.avg_score != null ? `${Math.round(report.metrics.avg_score * 100)}%` : "—", icon: <Activity size={12} /> },
          { label: "Avg Latency", value: `${Math.round(report.metrics.avg_latency_ms)}ms`, icon: <Clock size={12} /> },
          { label: "Error Rate", value: `${(report.metrics.error_rate * 100).toFixed(1)}%`, icon: <XCircle size={12} /> },
          { label: "Safety Flags", value: `${(report.metrics.safety_flag_rate * 100).toFixed(1)}%`, icon: <Shield size={12} /> },
        ].map(({ label, value, icon }) => (
          <div key={label} className="bg-white border border-slate-200 rounded-xl p-3">
            <div className="flex items-center gap-1 text-slate-400 text-[10px] mb-1">{icon}{label}</div>
            <div className="text-sm font-bold text-slate-900">{value}</div>
          </div>
        ))}
      </div>

      {/* Trend + volatility */}
      <div className="bg-white border border-slate-200 rounded-xl px-4 py-3 flex items-center gap-4 text-xs">
        <div className="flex items-center gap-1.5 text-slate-600">
          <TrendIcon trend={report.metrics.score_trend} />
          Score trend: <span className="font-medium capitalize">{report.metrics.score_trend}</span>
        </div>
        <div className="text-slate-400">|</div>
        <div className="text-slate-600">
          Score volatility: <span className="font-medium">{report.metrics.score_volatility.toFixed(3)}</span>
        </div>
        <div className="text-slate-400">|</div>
        <div className="text-slate-600">
          Judge coverage: <span className="font-medium">{Math.round(report.judge_monitoring.coverage * 100)}%</span>
        </div>
      </div>

      {/* Drift alerts */}
      {report.drift_alerts.length > 0 && (
        <div>
          <div className="text-xs font-medium text-slate-500 mb-2">Drift Alerts</div>
          <div className="space-y-2">
            {report.drift_alerts.map(a => (
              <div key={a.alert_id} className={`rounded-xl p-4 border ${severityColor(a.severity)}`}>
                <div className="flex items-start justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <AlertTriangle size={13} />
                    <span className="text-xs font-semibold capitalize">{a.alert_type.replace(/_/g, " ")}</span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/50 font-medium uppercase">{a.severity}</span>
                  </div>
                  <span className="text-[10px] opacity-60">{a.nist_dimension}</span>
                </div>
                <p className="text-xs mb-1">{a.description}</p>
                <p className="text-[11px] opacity-80">
                  Baseline: {typeof a.baseline === "number" ? a.baseline.toFixed(4) : a.baseline} →
                  Current: {typeof a.current === "number" ? a.current.toFixed(4) : a.current}
                  (Δ{a.delta > 0 ? "+" : ""}{typeof a.delta === "number" ? a.delta.toFixed(4) : a.delta})
                </p>
                <p className="text-[11px] mt-1.5 font-medium">→ {a.recommended_action}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Judge validity warning */}
      {report.judge_monitoring.validity_warning && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-xs text-blue-700">
          <span className="font-medium">LLM-as-judge validity: </span>
          {report.judge_monitoring.validity_warning}
        </div>
      )}
    </div>
  );
}

// ── Fleet Dashboard ───────────────────────────────────────────────────────────

function FleetView({ fleet, onSelectModel }: { fleet: FleetDashboard; onSelectModel: (id: number) => void }) {
  return (
    <div className="space-y-4">
      {/* Summary bar */}
      <div className="grid grid-cols-3 gap-3">
        {[
          { label: "Active Models", value: fleet.n_active_models, color: "text-slate-900" },
          { label: "Critical", value: fleet.critical_count, color: "text-red-600" },
          { label: "Warning", value: fleet.warning_count, color: "text-yellow-600" },
        ].map(({ label, value, color }) => (
          <div key={label} className="bg-white border border-slate-200 rounded-xl p-4 text-center">
            <div className={`text-2xl font-bold ${color}`}>{value}</div>
            <div className="text-xs text-slate-500 mt-0.5">{label}</div>
          </div>
        ))}
      </div>

      {/* Model rows */}
      {fleet.models.length === 0 ? (
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-12 text-center">
          <Activity size={28} className="mx-auto text-slate-300 mb-3" />
          <p className="text-sm text-slate-500">No telemetry data in this window.</p>
          <p className="text-xs text-slate-400 mt-1">Ingest events via POST /api/monitoring/ingest to start monitoring.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {fleet.models.map(m => (
            <button key={m.model_id} onClick={() => onSelectModel(m.model_id)}
              className="w-full text-left bg-white border border-slate-200 rounded-xl p-4 hover:border-slate-400 transition-colors">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className={`w-2.5 h-2.5 rounded-full ${statusDot(m.health_status)}`} />
                  <div>
                    <span className="text-sm font-medium text-slate-900">{m.model_name}</span>
                    <span className="text-xs text-slate-400 ml-2">{m.n_inferences.toLocaleString()} inferences</span>
                  </div>
                </div>
                <div className="flex items-center gap-4 text-xs text-slate-500">
                  <span className="flex items-center gap-1">
                    <TrendIcon trend={m.metrics.score_trend} />
                    {m.metrics.avg_score != null ? `${Math.round(m.metrics.avg_score * 100)}%` : "—"}
                  </span>
                  <span className={`px-2 py-0.5 rounded border font-medium text-[11px] ${statusColor(m.health_status)}`}>
                    {Math.round(m.overall_health * 100)}% {m.health_status}
                  </span>
                </div>
              </div>
              {m.top_alert && (
                <div className={`mt-2 text-[11px] px-3 py-1.5 rounded border ${severityColor(m.top_alert.severity)}`}>
                  ⚠ {m.top_alert.description}
                </div>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

function TelemetryContent() {
  const [view, setView] = useState<"fleet" | "model">("fleet");
  const [hours, setHours] = useState(24);
  const [selectedModelId, setSelectedModelId] = useState<number | null>(null);
  const [fleet, setFleet] = useState<FleetDashboard | null>(null);
  const [report, setReport] = useState<MonitoringReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { models } = useModels();

  const loadFleet = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const res = await fetch(`${API_BASE}/monitoring/dashboard?window_hours=${hours}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setFleet(await res.json());
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  }, [hours]);

  const loadReport = useCallback(async (modelId: number | null) => {
    setLoading(true); setError(null);
    const url = modelId
      ? `${API_BASE}/monitoring/report?model_id=${modelId}&window_hours=${hours}`
      : `${API_BASE}/monitoring/report?window_hours=${hours}`;
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setReport(await res.json());
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  }, [hours]);

  useEffect(() => {
    if (view === "fleet") loadFleet();
    else loadReport(selectedModelId);
  }, [view, hours, selectedModelId]);

  const selectModel = (id: number) => {
    setSelectedModelId(id); setView("model");
  };

  return (
    <div>
      <PageHeader
        title="Runtime Monitoring"
        subtitle="NIST AI 800-4 · Post-deployment continuous safety monitoring"
        actions={
          <div className="flex items-center gap-2">
            <select value={hours} onChange={e => setHours(Number(e.target.value))}
              className="border border-slate-200 rounded-lg px-3 py-1.5 text-xs text-slate-700">
              {[1, 6, 24, 72, 168].map(h => (
                <option key={h} value={h}>{h}h</option>
              ))}
            </select>
            <button onClick={() => view === "fleet" ? loadFleet() : loadReport(selectedModelId)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 rounded-lg text-xs text-slate-700">
              <RefreshCw size={12} />Refresh
            </button>
          </div>
        }
      />

      {/* View switcher */}
      <div className="px-6 pt-4 pb-0 flex items-center gap-2">
        <button onClick={() => setView("fleet")}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${view === "fleet" ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}>
          🌐 Fleet Overview
        </button>
        <button onClick={() => setView("model")}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${view === "model" ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}>
          🔬 Model Deep-Dive
        </button>
        {view === "model" && (
          <select value={selectedModelId ?? ""} onChange={e => setSelectedModelId(e.target.value ? Number(e.target.value) : null)}
            className="ml-2 border border-slate-200 rounded-lg px-3 py-1.5 text-xs">
            <option value="">All models (aggregate)</option>
            {models.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
          </select>
        )}
      </div>

      <div className="p-6">
        {loading && <div className="flex justify-center py-20"><Spinner size={28} /></div>}
        {error && <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">{error}</div>}

        {!loading && !error && view === "fleet" && fleet && (
          <FleetView fleet={fleet} onSelectModel={selectModel} />
        )}
        {!loading && !error && view === "model" && report && (
          <NISTDashboard report={report} />
        )}

        {/* Regulatory footer */}
        <div className="mt-6 bg-slate-50 border border-slate-200 rounded-xl px-4 py-3">
          <p className="text-[11px] text-slate-400 leading-relaxed">
            <span className="font-medium text-slate-500">Regulatory basis: </span>
            NIST AI 800-4 (March 2026) — 6-dimension mandatory monitoring framework ·
            EU AI Act Art. 9 — continuous monitoring of high-risk AI systems (current law) ·
            INESIA (2026) — post-deployment evaluation as first-class obligation
          </p>
        </div>
      </div>
    </div>
  );
}

export default function TelemetryPage() {
  return (
    <AppErrorBoundary>
      <TelemetryContent />
    </AppErrorBoundary>
  );
}
