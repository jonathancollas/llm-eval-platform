"use client";
import { useEffect, useState } from "react";
import { use } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { formatScore, formatCost, formatLatency } from "@/lib/utils";
import { FileText, RefreshCw, ArrowLeft, AlertTriangle } from "lucide-react";
import ReactMarkdown from "react-markdown";

import { API_BASE } from "@/lib/config";

interface LeaderboardRow {
  rank: number; model_name: string; model_provider: string;
  scores: Record<string, number | null>; avg_score: number | null;
  num_benchmarks_run: number; total_cost_usd: number; avg_latency_ms: number;
}
interface DomainData {
  domain: string; label: string; description: string; icon: string;
  benchmarks: string[]; rows: LeaderboardRow[];
  total_runs: number; last_updated: string;
}
interface Report { domain: string; label: string; content_markdown: string; generated_at: string; model_used: string; }

function ScoreCell({ score }: { score: number | null | undefined }) {
  if (score == null) return <td className="px-3 py-3 text-center text-slate-200 text-xs">—</td>;
  const pct = (score * 100).toFixed(1);
  const color = score >= 0.8 ? "bg-green-100 text-green-700" : score >= 0.6 ? "bg-amber-100 text-amber-700" : score >= 0.4 ? "bg-orange-100 text-orange-700" : "bg-red-100 text-red-600";
  return (
    <td className="px-3 py-3 text-center">
      <span className={`inline-block px-2 py-0.5 rounded text-xs font-mono font-medium ${color}`}>{pct}%</span>
    </td>
  );
}

export default function DomainLeaderboardPage({ params }: { params: Promise<{ domain: string }> }) {
  const { domain } = use(params);
  const [data, setData] = useState<DomainData | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [loadingData, setLoadingData] = useState(true);
  const [generatingReport, setGeneratingReport] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);
  const [showReport, setShowReport] = useState(false);

  useEffect(() => {
    setLoadingData(true);
    Promise.all([
      fetch(`${API_BASE}/leaderboard/${domain}`).then(r => r.json()),
      fetch(`${API_BASE}/leaderboard/${domain}/report`).then(r => r.json()).catch(() => null),
    ]).then(([d, r]) => { setData(d); if (r) setReport(r); }).finally(() => setLoadingData(false));
  }, [domain]);

  const generateReport = async (forceRefresh = false) => {
    setGeneratingReport(true);
    setReportError(null);
    try {
      const res = await fetch(`${API_BASE}/leaderboard/${domain}/report?force_refresh=${forceRefresh}`, { method: "POST" });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail ?? "Error during generation");
      }
      const r = await res.json();
      setReport(r);
      setShowReport(true);
    } catch (e) {
      setReportError(String(e));
    } finally {
      setGeneratingReport(false);
    }
  };

  if (loadingData) return <div className="flex justify-center items-center h-64"><Spinner size={32} /></div>;
  if (!data) return <div className="p-8 text-red-500">Domain not found.</div>;

  return (
    <div>
      <PageHeader
        title={`${data.icon} Leaderboard — ${data.label}`}
        description={data.description}
        action={
          <Link href="/leaderboard" className="flex items-center gap-2 text-sm text-slate-600 hover:text-slate-900">
            <ArrowLeft size={14} /> Back
          </Link>
        }
      />

      <div className="p-8 space-y-6">

        {/* Stats bar */}
        <div className="grid grid-cols-3 gap-4">
          {[
            { label: "Evaluated models", value: data.rows.length },
            { label: "Benchmarks covered", value: data.benchmarks.length },
            { label: "Completed runs", value: data.total_runs },
          ].map(({ label, value }) => (
            <div key={label} className="bg-white border border-slate-200 rounded-xl p-4">
              <div className="text-xs text-slate-500 mb-1">{label}</div>
              <div className="text-2xl font-semibold text-slate-900">{value}</div>
            </div>
          ))}
        </div>

        {/* Leaderboard table */}
        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
            <h2 className="font-medium text-slate-900 text-sm">Rankings</h2>
            <span className="text-xs text-slate-400">
              {data.total_runs > 0 ? `Updated ${new Date(data.last_updated).toLocaleDateString("en-US")}` : "No data"}
            </span>
          </div>

          {data.rows.length === 0 ? (
            <div className="py-16 text-center text-slate-400 text-sm">
              <div className="text-3xl mb-3">📊</div>
              <p className="font-medium text-slate-600 mb-1">No data yet for this domain</p>
              <p className="text-xs mb-4">Create a campaign with benchmarks from this domain.</p>
              <Link href="/campaigns" className="text-xs text-blue-600 hover:underline">Create a campaign →</Link>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100 bg-slate-50">
                    <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wide w-10">#</th>
                    <th className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Model</th>
                    <th className="text-center px-3 py-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Avg.</th>
                    {data.benchmarks.map(b => (
                      <th key={b} className="text-center px-3 py-3 text-xs font-medium text-slate-500 uppercase tracking-wide max-w-24">
                        <div className="truncate max-w-20" title={b}>{b.split(" ")[0]}</div>
                      </th>
                    ))}
                    <th className="text-center px-3 py-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Cost</th>
                    <th className="text-center px-3 py-3 text-xs font-medium text-slate-500 uppercase tracking-wide">Latency</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map(row => (
                    <tr key={row.model_name} className="border-b border-slate-50 hover:bg-slate-50 transition-colors">
                      <td className="px-4 py-3 text-slate-400 font-mono text-xs">
                        {row.rank === 1 ? "🥇" : row.rank === 2 ? "🥈" : row.rank === 3 ? "🥉" : `#${row.rank}`}
                      </td>
                      <td className="px-4 py-3">
                        <div className="font-medium text-slate-900 text-sm">{row.model_name}</div>
                        <div className="text-xs text-slate-400 capitalize">{row.model_provider}</div>
                      </td>
                      <td className="px-3 py-3 text-center">
                        <span className={`font-mono font-bold text-sm ${
                          row.avg_score === null ? "text-slate-300"
                          : row.avg_score >= 0.8 ? "text-green-600"
                          : row.avg_score >= 0.6 ? "text-amber-600"
                          : "text-red-500"}`}>
                          {row.avg_score !== null ? `${(row.avg_score * 100).toFixed(1)}%` : "—"}
                        </span>
                      </td>
                      {data.benchmarks.map(b => (
                        <ScoreCell key={b} score={row.scores[b]} />
                      ))}
                      <td className="px-3 py-3 text-center text-slate-500 text-xs font-mono">{formatCost(row.total_cost_usd)}</td>
                      <td className="px-3 py-3 text-center text-slate-500 text-xs font-mono">{formatLatency(row.avg_latency_ms)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Claude Report section */}
        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <FileText size={16} className="text-slate-500" />
              <h2 className="font-medium text-slate-900 text-sm">Analyse narrative — Claude</h2>
              {report && <span className="text-xs text-slate-400">Generated on {new Date(report.generated_at).toLocaleDateString("en-US")}</span>}
            </div>
            <div className="flex gap-2">
              {report && (
                <button onClick={() => setShowReport(!showReport)}
                  className="text-xs px-3 py-1.5 border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600">
                  {showReport ? "Hide" : "Show"}
                </button>
              )}
              <button onClick={() => generateReport(!!report)}
                disabled={generatingReport || data.rows.length === 0}
                className="flex items-center gap-1.5 text-xs px-3 py-1.5 bg-slate-900 text-white rounded-lg hover:bg-slate-700 disabled:opacity-50 transition-colors">
                {generatingReport ? <Spinner size={12} /> : <RefreshCw size={12} />}
                {generatingReport ? "Generating…" : report ? "Regenerate" : "Generate report"}
              </button>
            </div>
          </div>

          {reportError && (
            <div className="mx-6 my-4 bg-red-50 border border-red-200 rounded-xl p-3 flex items-start gap-2">
              <AlertTriangle size={14} className="text-red-500 shrink-0 mt-0.5" />
              <p className="text-xs text-red-600">{reportError}</p>
            </div>
          )}

          {!report && !generatingReport && data.rows.length === 0 && (
            <div className="px-6 py-8 text-center text-slate-400 text-sm">
              Evaluation data is needed to generate a report.
            </div>
          )}

          {!report && !generatingReport && data.rows.length > 0 && (
            <div className="px-6 py-8 text-center text-slate-400 text-sm">
              <p className="mb-2">Click "Generate report" to get a narrative analysis.</p>
              <p className="text-xs text-slate-300">The analysis is cached until the next regeneration.</p>
            </div>
          )}

          {generatingReport && (
            <div className="px-6 py-12 flex flex-col items-center gap-3 text-slate-500">
              <Spinner size={24} />
              <p className="text-sm">Generating analysis…</p>
            </div>
          )}

          {report && showReport && (
            <div className="px-6 py-6 prose prose-sm prose-slate max-w-none">
              <ReactMarkdown>{report.content_markdown}</ReactMarkdown>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
