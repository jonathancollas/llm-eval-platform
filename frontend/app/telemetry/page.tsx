"use client";
import { useEffect, useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { Activity, AlertTriangle, Shield, Clock, Zap } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "https://llm-eval-backend-kqlh.onrender.com/api";

interface DriftSignal { type: string; severity: string; detail: string; }
interface TelemetryDash {
  period_hours: number; total_events: number; avg_latency_ms: number;
  safety_flag_rate: number; error_rate: number; avg_score: number | null;
  drift_signals: DriftSignal[]; safety_flags_by_type: Record<string, number>;
}

export default function TelemetryPage() {
  const [data, setData] = useState<TelemetryDash | null>(null);
  const [loading, setLoading] = useState(true);
  const [hours, setHours] = useState(24);

  const load = () => {
    setLoading(true);
    fetch(`${API}/research/telemetry/dashboard?hours=${hours}`)
      .then(r => r.json()).then(setData).finally(() => setLoading(false));
  };
  useEffect(() => { load(); const p = setInterval(load, 30000); return () => clearInterval(p); }, [hours]);

  return (
    <div>
      <PageHeader title="Continuous Monitoring" description="Post-deployment telemetry, drift detection, and safety regression alerts." />

      <div className="p-8 space-y-6">
        {/* Time range selector */}
        <div className="flex gap-2">
          {[1, 6, 12, 24, 48, 168].map(h => (
            <button key={h} onClick={() => setHours(h)}
              className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${hours === h ? "bg-slate-900 text-white border-slate-900" : "border-slate-200 text-slate-500 hover:bg-slate-50"}`}>
              {h < 24 ? `${h}h` : `${h/24}d`}
            </button>
          ))}
        </div>

        {loading && !data ? <div className="flex items-center gap-2 text-slate-400"><Spinner size={16} /> Loading telemetry…</div> : null}

        {data && (
          <>
            {/* Drift alerts */}
            {data.drift_signals.length > 0 && (
              <div className="space-y-2">
                {data.drift_signals.map((sig, i) => (
                  <div key={i} className={`flex items-center gap-3 rounded-xl p-4 border ${
                    sig.severity === "high" ? "bg-red-50 border-red-200" : "bg-yellow-50 border-yellow-200"
                  }`}>
                    <AlertTriangle size={16} className={sig.severity === "high" ? "text-red-500" : "text-yellow-500"} />
                    <div>
                      <span className="text-xs font-bold uppercase">{sig.type.replace("_", " ")}</span>
                      <p className="text-sm text-slate-700">{sig.detail}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Metric cards */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              <MetricCard icon={Activity} label="Events" value={data.total_events.toLocaleString()} />
              <MetricCard icon={Clock} label="Avg Latency" value={`${data.avg_latency_ms}ms`}
                alert={data.avg_latency_ms > 10000} />
              <MetricCard icon={Shield} label="Safety Flag Rate" value={`${(data.safety_flag_rate * 100).toFixed(1)}%`}
                alert={data.safety_flag_rate > 0.05} />
              <MetricCard icon={AlertTriangle} label="Error Rate" value={`${(data.error_rate * 100).toFixed(1)}%`}
                alert={data.error_rate > 0.10} />
              <MetricCard icon={Zap} label="Avg Score" value={data.avg_score != null ? `${(data.avg_score * 100).toFixed(0)}%` : "—"} />
            </div>

            {/* Safety flags breakdown */}
            {Object.keys(data.safety_flags_by_type).length > 0 && (
              <div className="bg-white border border-slate-200 rounded-xl p-5">
                <h3 className="text-sm font-medium text-slate-800 mb-3">Safety Flags by Type</h3>
                <div className="space-y-2">
                  {Object.entries(data.safety_flags_by_type).sort((a, b) => b[1] - a[1]).map(([type, count]) => (
                    <div key={type} className="flex items-center gap-3">
                      <span className="text-xs text-slate-600 w-40 truncate">{type}</span>
                      <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
                        <div className="h-full bg-red-500 rounded-full" style={{ width: `${Math.min(100, (count / data.total_events) * 100 * 20)}%` }} />
                      </div>
                      <span className="text-xs font-mono text-slate-500 w-12 text-right">{count}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Empty state */}
            {data.total_events === 0 && (
              <div className="bg-slate-50 border border-slate-200 rounded-2xl p-12 text-center">
                <Activity size={40} className="text-slate-300 mx-auto mb-3" />
                <h3 className="font-semibold text-slate-700 mb-1">No telemetry data</h3>
                <p className="text-sm text-slate-500 max-w-md mx-auto">
                  Ingest production telemetry via <code className="bg-slate-100 px-1.5 py-0.5 rounded text-xs">POST /research/telemetry/ingest</code> to enable continuous monitoring and drift detection.
                </p>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function MetricCard({ icon: Icon, label, value, alert = false }: { icon: any; label: string; value: string; alert?: boolean }) {
  return (
    <div className={`bg-white border rounded-xl p-4 ${alert ? "border-red-200 bg-red-50" : "border-slate-200"}`}>
      <div className="flex items-center gap-2 mb-2">
        <Icon size={14} className={alert ? "text-red-500" : "text-slate-400"} />
        <span className="text-xs text-slate-500">{label}</span>
      </div>
      <div className={`text-xl font-bold ${alert ? "text-red-700" : "text-slate-900"}`}>{value}</div>
    </div>
  );
}
