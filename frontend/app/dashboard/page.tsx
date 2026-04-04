"use client";
import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { resultsApi, campaignsApi, reportsApi } from "@/lib/api";
import type { DashboardData, Campaign, Report } from "@/lib/api";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { formatScore, formatCost, formatLatency, scoreColor } from "@/lib/utils";
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ResponsiveContainer, Tooltip, Legend,
} from "recharts";
import { Download, FileText, AlertTriangle } from "lucide-react";

const CHART_COLORS = ["#3b82f6", "#8b5cf6", "#10b981", "#f59e0b", "#ef4444", "#06b6d4"];

function RadarSection({ radar }: { radar: Record<string, Record<string, number>> }) {
  const models = Object.keys(radar);
  const benchmarks = Array.from(new Set(models.flatMap(m => Object.keys(radar[m]))));
  if (!benchmarks.length) return null;

  const data = benchmarks.map(bench => {
    const row: Record<string, string | number> = { bench };
    models.forEach(m => { row[m] = radar[m]?.[bench] ?? 0; });
    return row;
  });

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-6">
      <h3 className="font-medium text-slate-900 mb-4 text-sm">Radar — Performance by Benchmark</h3>
      <ResponsiveContainer width="100%" height={320}>
        <RadarChart data={data}>
          <PolarGrid stroke="#e2e8f0" />
          <PolarAngleAxis dataKey="bench" tick={{ fontSize: 11, fill: "#64748b" }} />
          <PolarRadiusAxis angle={90} domain={[0, 100]} tick={{ fontSize: 10, fill: "#94a3b8" }} />
          {models.map((m, i) => (
            <Radar key={m} name={m} dataKey={m} stroke={CHART_COLORS[i % CHART_COLORS.length]}
              fill={CHART_COLORS[i % CHART_COLORS.length]} fillOpacity={0.12} strokeWidth={2} />
          ))}
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Tooltip formatter={(v: number) => `${v.toFixed(1)}%`} />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}

function HeatmapSection({ heatmap }: { heatmap: DashboardData["heatmap"] }) {
  const models = [...new Set(heatmap.map(c => c.model_name))];
  const benchmarks = [...new Set(heatmap.map(c => c.benchmark_name))];
  if (!models.length) return null;

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-6">
      <h3 className="font-medium text-slate-900 mb-4 text-sm">Heatmap — Models × Benchmarks</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr>
              <th className="text-left text-xs text-slate-500 font-medium pb-3 pr-4">Model</th>
              {benchmarks.map(b => (
                <th key={b} className="text-center text-xs text-slate-500 font-medium pb-3 px-3 max-w-28">
                  <div className="truncate">{b}</div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {models.map(model => (
              <tr key={model}>
                <td className="font-medium text-slate-800 text-xs pr-4 py-2 whitespace-nowrap">{model}</td>
                {benchmarks.map(bench => {
                  const cell = heatmap.find(c => c.model_name === model && c.benchmark_name === bench);
                  const score = cell?.score;
                  const color = scoreColor(score ?? null);
                  return (
                    <td key={bench} className="px-3 py-2 text-center">
                      <div className="inline-flex items-center justify-center w-16 h-10 rounded-lg text-xs font-mono font-medium text-white"
                        style={{ backgroundColor: score !== null ? color : "#e2e8f0", color: score !== null ? "white" : "#94a3b8" }}>
                        {score != null ? `${(score * 100).toFixed(1)}%` : cell?.status ?? "—"}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {/* Color legend */}
      <div className="flex items-center gap-1 mt-4 text-xs text-slate-400">
        <span>Score:</span>
        {[["#ef4444", "<40%"], ["#f97316", "40-60%"], ["#eab308", "60-80%"], ["#22c55e", "≥80%"]].map(([c, l]) => (
          <span key={l} className="flex items-center gap-1 ml-2">
            <span className="w-3 h-3 rounded" style={{ backgroundColor: c }} />{l}
          </span>
        ))}
      </div>
    </div>
  );
}

function WinRateSection({ winRates }: { winRates: DashboardData["win_rates"] }) {
  if (!winRates.length) return null;
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-6">
      <h3 className="font-medium text-slate-900 mb-4 text-sm">Win Rate — Pairwise Comparison</h3>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-100">
            {["Model", "Win rate", "Wins", "Losses", "Ties"].map(h => (
              <th key={h} className={`text-xs font-medium text-slate-500 pb-2 ${h === "Model" ? "text-left" : "text-center"}`}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {winRates.map((r, i) => (
            <tr key={r.model_name} className="border-b border-slate-50">
              <td className="py-2 pr-4">
                <div className="flex items-center gap-2">
                  {i === 0 && <span className="text-amber-500">🏆</span>}
                  <span className="font-medium text-slate-800">{r.model_name}</span>
                </div>
              </td>
              <td className="py-2 text-center">
                <div className="flex items-center gap-2 justify-center">
                  <div className="w-20 bg-slate-100 rounded-full h-2">
                    <div className="bg-blue-500 h-2 rounded-full" style={{ width: `${r.win_rate * 100}%` }} />
                  </div>
                  <span className="font-mono text-xs font-medium text-slate-700">{(r.win_rate * 100).toFixed(0)}%</span>
                </div>
              </td>
              <td className="py-2 text-center text-green-600 font-medium text-xs">{r.wins}</td>
              <td className="py-2 text-center text-red-500 font-medium text-xs">{r.losses}</td>
              <td className="py-2 text-center text-slate-400 text-xs">{r.ties}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ReportPanel({ campaignId }: { campaignId: number }) {
  const [reports, setReports] = useState<Report[]>([]);
  const [generating, setGenerating] = useState(false);
  const [customInstructions, setCustomInstructions] = useState("");
  const [open, setOpen] = useState(false);

  useEffect(() => { reportsApi.list(campaignId).then(setReports); }, [campaignId]);

  const generate = async () => {
    setGenerating(true);
    try {
      await reportsApi.generate(campaignId, customInstructions);
      reportsApi.list(campaignId).then(setReports);
    } catch (err) { alert(String(err)); } finally { setGenerating(false); }
  };

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-medium text-slate-900 text-sm flex items-center gap-2">
          <FileText size={14} /> AI Report (Claude)
        </h3>
        <button onClick={() => setOpen(!open)} className="text-xs text-slate-500 hover:text-slate-700">
          {open ? "Hide" : "Generate"}
        </button>
      </div>

      {open && (
        <div className="space-y-3 mb-4">
          <textarea rows={2} placeholder="Optional: custom instructions for the analyst…"
            value={customInstructions} onChange={e => setCustomInstructions(e.target.value)}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900 resize-none" />
          <button onClick={generate} disabled={generating}
            className="flex items-center gap-2 bg-slate-900 text-white px-4 py-2 rounded-lg text-sm hover:bg-slate-700 disabled:opacity-50">
            {generating ? <><Spinner size={12} /> Generating…</> : "Generate Report"}
          </button>
        </div>
      )}

      {reports.length > 0 && (
        <div className="space-y-2">
          {reports.map(r => (
            <div key={r.id} className="flex items-center justify-between text-xs bg-slate-50 rounded-lg px-3 py-2">
              <span className="text-slate-700 font-medium">{r.title}</span>
              <a href={reportsApi.exportUrl(r.id)} download
                className="flex items-center gap-1 text-blue-600 hover:underline">
                <Download size={10} /> .md
              </a>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function DashboardContent() {
  const searchParams = useSearchParams();
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => { campaignsApi.list().then(c => setCampaigns(c.filter(x => x.status === "completed"))); }, []);

  useEffect(() => {
    const id = searchParams.get("campaign");
    if (id) setSelectedId(+id);
  }, [searchParams]);

  useEffect(() => {
    if (!selectedId) return;
    setLoading(true); setData(null);
    resultsApi.dashboard(selectedId).then(setData).finally(() => setLoading(false));
  }, [selectedId]);

  return (
    <div>
      <PageHeader
        title="Dashboard"
        description="Visual analysis of evaluation results."
        action={
          selectedId && data?.status === "completed" ? (
            <a href={resultsApi.exportUrl(selectedId)} download
              className="flex items-center gap-2 border border-slate-200 px-4 py-2 rounded-lg text-sm hover:bg-slate-50 text-slate-600">
              <Download size={14} /> Export CSV
            </a>
          ) : undefined
        }
      />

      <div className="p-8">
        {/* Campaign selector */}
        <div className="mb-6">
          <label className="text-xs font-medium text-slate-600 mb-1.5 block">Campaign</label>
          <select value={selectedId ?? ""}
            onChange={e => setSelectedId(e.target.value ? +e.target.value : null)}
            className="border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900 bg-white">
            <option value="">— Select a completed campaign —</option>
            {campaigns.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>

        {loading && <div className="flex justify-center py-20"><Spinner size={24} /></div>}

        {data && (
          <div className="space-y-6">
            {/* KPI bar */}
            <div className="grid grid-cols-3 gap-4">
              {[
                { label: "Total Cost", value: formatCost(data.total_cost_usd) },
                { label: "Avg Latency / Run", value: formatLatency(data.avg_latency_ms) },
                { label: "Models Compared", value: Object.keys(data.radar).length },
              ].map(({ label, value }) => (
                <div key={label} className="bg-white border border-slate-200 rounded-xl p-4">
                  <div className="text-xs text-slate-500 mb-1">{label}</div>
                  <div className="text-xl font-semibold text-slate-900">{value}</div>
                </div>
              ))}
            </div>

            {/* Alerts */}
            {data.alerts.length > 0 && (
              <div className="bg-red-50 border border-red-200 rounded-xl p-4 space-y-1.5">
                <div className="flex items-center gap-2 text-red-700 font-medium text-sm mb-2">
                  <AlertTriangle size={14} /> Safety Alerts
                </div>
                {data.alerts.map((a, i) => (
                  <p key={i} className="text-xs text-red-600">{a}</p>
                ))}
              </div>
            )}

            <div className="grid grid-cols-2 gap-6">
              <RadarSection radar={data.radar} />
              <WinRateSection winRates={data.win_rates} />
            </div>

            <HeatmapSection heatmap={data.heatmap} />

            {selectedId && <ReportPanel campaignId={selectedId} />}
          </div>
        )}

        {!selectedId && !loading && (
          <div className="text-center py-20 text-slate-400 text-sm">
            Select a completed campaign to view its dashboard.
          </div>
        )}
      </div>
    </div>
  );
}

export default function DashboardPage() {
  return (
    <Suspense fallback={<div className="flex justify-center py-20"><Spinner size={24} /></div>}>
      <DashboardContent />
    </Suspense>
  );
}
