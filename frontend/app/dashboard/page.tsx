"use client";
import { useEffect, useState, useMemo, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { resultsApi, campaignsApi, reportsApi, genomeApi, judgeApi } from "@/lib/api";
import type { DashboardData, Campaign, Report, GenomeData, FailedItemsData, FailedItem, FailedRun } from "@/lib/api";
import { API_BASE } from "@/lib/config";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { formatScore, formatCost, formatLatency, scoreColor } from "@/lib/utils";
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ResponsiveContainer, Tooltip, Legend,
} from "recharts";
import { Download, FileText, AlertTriangle, XCircle, Zap, Bug, ChevronDown, ChevronUp, ThumbsUp, ThumbsDown, Gavel } from "lucide-react";

const CHART_COLORS = ["#3b82f6", "#8b5cf6", "#10b981", "#f59e0b", "#ef4444", "#06b6d4"];

// ── Tabs ──────────────────────────────────────────────────────────────────────
type Tab = "overview" | "genome" | "errors" | "signals" | "report";

// ── Radar — performance by benchmark ──────────────────────────────────────────
function RadarSection({ radar }: { radar: Record<string, Record<string, number>> }) {
  const models = Object.keys(radar);
  const benchmarks = Array.from(new Set(models.flatMap(m => Object.keys(radar[m]))));
  if (!benchmarks.length) return null;

  const data = useMemo(() => benchmarks.map(bench => {
    const row: Record<string, string | number> = { bench };
    models.forEach(m => { row[m] = radar[m]?.[bench] ?? 0; });
    return row;
  }), [radar]);

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

// ── Heatmap ───────────────────────────────────────────────────────────────────
function HeatmapSection({ heatmap }: { heatmap: DashboardData["heatmap"] }) {
  const models = [...new Set(heatmap.map(c => c.model_name))];
  const benchmarks = [...new Set(heatmap.map(c => c.benchmark_name))];
  if (!models.length) return null;

  // Check if any cell has capability/propensity split
  const hasCapProp = heatmap.some(c => (c as any).capability_score != null || (c as any).propensity_score != null);

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-medium text-slate-900 text-sm">Heatmap — Models × Benchmarks</h3>
        {hasCapProp && (
          <div className="flex items-center gap-3 text-[10px] text-slate-400">
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-blue-400 inline-block" />Capability</span>
            <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-orange-400 inline-block" />Propensity</span>
          </div>
        )}
      </div>
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
                  const cell = heatmap.find(c => c.model_name === model && c.benchmark_name === bench) as any;
                  const score = cell?.score;
                  const capScore = cell?.capability_score;
                  const propScore = cell?.propensity_score;
                  const color = scoreColor(score ?? null);
                  return (
                    <td key={bench} className="px-3 py-2 text-center">
                      {capScore != null && propScore != null ? (
                        // Split capability / propensity display
                        <div className="inline-flex flex-col items-center gap-0.5" title={`Capability: ${(capScore*100).toFixed(1)}% | Propensity: ${(propScore*100).toFixed(1)}%`}>
                          <div className="w-16 h-5 rounded-t flex items-center justify-center text-[10px] font-mono font-bold text-white"
                            style={{ backgroundColor: scoreColor(capScore) }}>
                            {(capScore * 100).toFixed(0)}%
                          </div>
                          <div className="w-16 h-5 rounded-b flex items-center justify-center text-[10px] font-mono font-bold text-white"
                            style={{ backgroundColor: scoreColor(propScore) }}>
                            {(propScore * 100).toFixed(0)}%
                          </div>
                        </div>
                      ) : (
                        <div className="inline-flex items-center justify-center w-16 h-10 rounded-lg text-xs font-mono font-medium"
                          style={{ backgroundColor: score != null ? color : "#e2e8f0", color: score != null ? "white" : "#94a3b8" }}>
                          {score != null ? `${(score * 100).toFixed(1)}%` : cell?.status ?? "—"}
                        </div>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
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

// ── Win rates ─────────────────────────────────────────────────────────────────
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

// ── Genome Section ────────────────────────────────────────────────────────────
function GenomeSection({ genome }: { genome: GenomeData }) {
  if (!genome.computed || !Object.keys(genome.models).length) {
    return (
      <div className="bg-slate-50 border border-slate-200 rounded-xl p-8 text-center">
        <div className="text-3xl mb-2">🧬</div>
        <p className="text-sm text-slate-500">Failure Genome not computed for this campaign.</p>
        <p className="text-xs text-slate-400 mt-1">It is automatically calculated at the end of the benchmark.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {Object.entries(genome.models).map(([modelName, dna]) => {
        const entries = Object.entries(dna).filter(([k]) => genome.ontology[k]).sort(([, a], [, b]) => b - a);
        const topFailure = entries[0];
        return (
          <div key={modelName} className="bg-white border border-slate-200 rounded-xl p-5">
            <div className="flex items-center justify-between mb-3">
              <h4 className="font-medium text-slate-900 text-sm">{modelName}</h4>
              {topFailure && topFailure[1] > 0.1 && (
                <span className="text-xs px-2 py-0.5 rounded-full font-medium"
                  style={{ backgroundColor: genome.ontology[topFailure[0]]?.color + "20", color: genome.ontology[topFailure[0]]?.color }}>
                  {genome.ontology[topFailure[0]]?.label}: {Math.round(topFailure[1] * 100)}%
                </span>
              )}
            </div>
            <div className="space-y-1.5">
              {entries.filter(([, v]) => v > 0).map(([key, val]) => {
                const meta = genome.ontology[key];
                if (!meta) return null;
                const pct = Math.round(val * 100);
                return (
                  <div key={key} className="flex items-center gap-3">
                    <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: meta.color }} />
                    <span className="text-xs text-slate-600 w-36 shrink-0">{meta.label}</span>
                    <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                      <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, backgroundColor: meta.color }} />
                    </div>
                    <span className="text-xs font-mono text-slate-500 w-8 text-right">{pct}%</span>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Failed Items Section ──────────────────────────────────────────────────────
const ERROR_TYPE_LABELS: Record<string, { label: string; color: string; icon: typeof Bug }> = {
  wrong_answer: { label: "Wrong answer", color: "text-orange-600 bg-orange-50", icon: XCircle },
  timeout: { label: "Timeout", color: "text-red-600 bg-red-50", icon: Zap },
  rate_limit: { label: "Rate limit", color: "text-amber-600 bg-amber-50", icon: Zap },
  credits: { label: "Credits", color: "text-purple-600 bg-purple-50", icon: Zap },
  api_error: { label: "API Error", color: "text-red-600 bg-red-50", icon: Bug },
  infra: { label: "Infra Error", color: "text-red-700 bg-red-50", icon: Bug },
};

function FailedItemsSection({ failedData, campaignId, onRefresh }: { failedData: FailedItemsData; campaignId: number; onRefresh: () => void }) {
  const [expanded, setExpanded] = useState<number | null>(null);
  const [filter, setFilter] = useState<string>("all");
  const [verdicts, setVerdicts] = useState<Record<number, boolean | null>>(() => {
    const init: Record<number, boolean | null> = {};
    failedData.items.forEach(it => { if (it.human_verdict != null) init[it.id] = it.human_verdict; });
    return init;
  });
  const [reviewing, setReviewing] = useState<number | null>(null);
  const [llmJudging, setLlmJudging] = useState(false);
  const [llmResult, setLlmResult] = useState<string | null>(null);

  const allErrors = [
    ...failedData.failed_runs.map(r => ({ ...r, id: r.run_id, item_index: -1, prompt: "", response: r.error_message ?? "", expected: null, score: 0, latency_ms: 0, model_name: r.model_name, benchmark_name: r.benchmark_name, error_type: "infra" })),
    ...failedData.items,
  ];

  const filtered = filter === "all" ? allErrors : allErrors.filter(e => e.error_type === filter);
  const errorTypes = [...new Set(allErrors.map(e => e.error_type))];

  const setVerdict = async (resultId: number, verdict: boolean | null) => {
    setReviewing(resultId);
    try {
      await resultsApi.humanReview(resultId, verdict);
      setVerdicts(v => ({ ...v, [resultId]: verdict }));
    } catch {}
    setReviewing(null);
  };

  const runLlmJudge = async () => {
    setLlmJudging(true);
    setLlmResult(null);
    try {
      const res = await judgeApi.evaluate(campaignId, ["claude-sonnet-4-20250514"], "correctness", 50);
      setLlmResult(`✅ LLM Judge completed: ${res.evaluations_created} items evaluated. Avg score: ${Object.values(res.avg_scores as Record<string, number>).map((s: number) => `${(s * 100).toFixed(1)}%`).join(", ")}`);
      onRefresh();
    } catch (e: any) {
      setLlmResult(`❌ ${e?.message ?? "Judge failed"}`);
    }
    setLlmJudging(false);
  };

  if (!allErrors.length) {
    return (
      <div className="bg-green-50 border border-green-200 rounded-xl p-6 text-center">
        <div className="text-2xl mb-1">✅</div>
        <p className="text-sm text-green-700 font-medium">No errors detected</p>
        <p className="text-xs text-green-500">All items were processed correctly.</p>
      </div>
    );
  }

  const reviewedCount = Object.values(verdicts).filter(v => v === true).length;

  return (
    <div className="space-y-3">
      {/* LLM Judge banner */}
      <div className="bg-white border border-slate-200 rounded-xl px-4 py-3 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2 text-sm text-slate-700">
          <Gavel size={15} className="text-slate-500" />
          <span className="font-medium">LLM Verify</span>
          <span className="text-xs text-slate-400">Re-evaluate results with an LLM judge to catch false positives</span>
        </div>
        <div className="flex items-center gap-3">
          {llmResult && <span className="text-xs text-slate-600">{llmResult}</span>}
          <button onClick={runLlmJudge} disabled={llmJudging}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 bg-slate-900 text-white rounded-lg hover:bg-slate-700 disabled:opacity-40">
            {llmJudging ? <><Spinner size={11} /> Running…</> : <><Gavel size={11} /> Run LLM Judge</>}
          </button>
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-5">
        <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
          <h3 className="font-medium text-slate-900 text-sm flex items-center gap-2">
            <AlertTriangle size={14} className="text-red-500" />
            Detected issues ({allErrors.length})
            {reviewedCount > 0 && (
              <span className="text-xs text-green-600 font-normal ml-1">· {reviewedCount} marked as false positive</span>
            )}
          </h3>
          <div className="flex gap-1 flex-wrap">
            <button onClick={() => setFilter("all")}
              className={`text-xs px-2 py-1 rounded-lg transition-colors ${filter === "all" ? "bg-slate-900 text-white" : "border border-slate-200 text-slate-500 hover:bg-slate-50"}`}>
              Tous
            </button>
            {errorTypes.map(et => {
              const cfg = ERROR_TYPE_LABELS[et] ?? { label: et, color: "text-slate-600 bg-slate-50" };
              return (
                <button key={et} onClick={() => setFilter(et)}
                  className={`text-xs px-2 py-1 rounded-lg transition-colors ${filter === et ? "bg-slate-900 text-white" : "border border-slate-200 text-slate-500 hover:bg-slate-50"}`}>
                  {cfg.label} ({allErrors.filter(e => e.error_type === et).length})
                </button>
              );
            })}
          </div>
        </div>

        <div className="space-y-1 max-h-[600px] overflow-y-auto">
          {filtered.map((item, idx) => {
            const cfg = ERROR_TYPE_LABELS[item.error_type] ?? { label: item.error_type, color: "text-slate-600 bg-slate-50", icon: Bug };
            const isExpanded = expanded === idx;
            const Icon = cfg.icon;
            const hasId = (item as FailedItem).id != null && item.item_index >= 0;
            const resultId = (item as FailedItem).id;
            const verdict = verdicts[resultId];
            const isFalsePositive = verdict === true;
            const isWrong = verdict === false;
            const isReviewing = reviewing === resultId;

            return (
              <div key={idx} className={`rounded-lg transition-colors ${isFalsePositive ? "bg-green-50 border border-green-200" : ""}`}>
                <div className="flex items-center gap-2 text-xs hover:bg-slate-50 rounded-lg px-3 py-2 transition-colors">
                  <button onClick={() => setExpanded(isExpanded ? null : idx)} className="flex items-center gap-2 flex-1 min-w-0 text-left">
                    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium ${cfg.color} shrink-0`}>
                      <Icon size={10} />{cfg.label}
                    </span>
                    {isFalsePositive && (
                      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-green-100 text-green-700 border border-green-200 shrink-0">
                        ✓ False positive
                      </span>
                    )}
                    {isWrong && (
                      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-red-100 text-red-700 border border-red-200 shrink-0">
                        ✗ Confirmed wrong
                      </span>
                    )}
                    <span className="text-slate-500 w-24 shrink-0 truncate">{item.model_name}</span>
                    <span className="text-slate-400 w-28 shrink-0 truncate">{item.benchmark_name}</span>
                    {item.item_index >= 0 && <span className="text-slate-300 shrink-0">Q#{item.item_index + 1}</span>}
                    <span className="text-slate-400 flex-1 truncate">{item.prompt || item.response}</span>
                    {isExpanded ? <ChevronUp size={12} className="text-slate-300 shrink-0" /> : <ChevronDown size={12} className="text-slate-300 shrink-0" />}
                  </button>
                  {/* Human review buttons — only for eval items (not infra runs) */}
                  {hasId && (
                    <div className="flex items-center gap-1 shrink-0">
                      <button
                        onClick={() => setVerdict(resultId, isFalsePositive ? null : true)}
                        disabled={isReviewing}
                        title={isFalsePositive ? "Undo: reset verdict" : "Mark as correct (false positive)"}
                        className={`p-1 rounded transition-colors disabled:opacity-40 ${isFalsePositive ? "text-green-600 bg-green-100 hover:bg-green-200" : "text-slate-300 hover:text-green-600 hover:bg-green-50"}`}>
                        <ThumbsUp size={12} />
                      </button>
                      <button
                        onClick={() => setVerdict(resultId, isWrong ? null : false)}
                        disabled={isReviewing}
                        title={isWrong ? "Undo: reset verdict" : "Confirm as wrong answer"}
                        className={`p-1 rounded transition-colors disabled:opacity-40 ${isWrong ? "text-red-600 bg-red-100 hover:bg-red-200" : "text-slate-300 hover:text-red-500 hover:bg-red-50"}`}>
                        <ThumbsDown size={12} />
                      </button>
                      {isReviewing && <Spinner size={10} />}
                    </div>
                  )}
                </div>
                {isExpanded && (
                  <div className="bg-slate-50 rounded-lg p-3 mx-3 mb-1 border border-slate-100 text-xs space-y-1.5">
                    {item.prompt && (
                      <div><span className="font-medium text-slate-400 uppercase text-[10px]">Prompt</span>
                        <p className="mt-0.5 text-slate-700">{item.prompt}</p></div>
                    )}
                    {item.response && (
                      <div><span className="font-medium text-slate-400 uppercase text-[10px]">Answer</span>
                        <p className="mt-0.5 text-slate-700 font-mono">{item.response}</p></div>
                    )}
                    {item.expected && (
                      <div className="flex items-center gap-2">
                        <span className="text-slate-400">Expected:</span>
                        <span className="font-mono text-green-700 bg-green-50 px-1.5 py-0.5 rounded">{item.expected}</span>
                      </div>
                    )}
                    {item.latency_ms > 0 && <span className="text-slate-400">{item.latency_ms}ms</span>}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ── Report Panel ──────────────────────────────────────────────────────────────
function ReportPanel({ campaignId }: { campaignId: number }) {
  const [reports, setReports] = useState<Report[]>([]);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [customInstructions, setCustomInstructions] = useState("");
  const [open, setOpen] = useState(false);
  const [ollamaModels, setOllamaModels] = useState<string[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>("");  // "" = auto (default)

  useEffect(() => { reportsApi.list(campaignId).then(setReports).catch(() => {}); }, [campaignId]);

  // Discover locally installed Ollama models
  useEffect(() => {
    fetch("http://localhost:11434/api/tags")
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d?.models) setOllamaModels(d.models.map((m: any) => m.name));
      })
      .catch(() => {});
  }, []);

  const generate = async () => {
    setGenerating(true);
    setError(null);
    try {
      await reportsApi.generate(campaignId, customInstructions, selectedModel);
      reportsApi.list(campaignId).then(setReports);
    } catch (err: any) {
      setError(err?.message ?? String(err));
    } finally { setGenerating(false); }
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
          {/* Model selector */}
          <div>
            <label className="text-xs font-medium text-slate-600 mb-1 block">Model for report generation</label>
            <select value={selectedModel} onChange={e => setSelectedModel(e.target.value)}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900">
              <option value="">🤖 Auto (Ollama local → Claude Sonnet)</option>
              {ollamaModels.map(m => (
                <option key={m} value={m}>🦙 {m} (local)</option>
              ))}
              <option value="__anthropic__" disabled>─ Cloud ─</option>
            </select>
            {ollamaModels.length > 0 && (
              <p className="text-[10px] text-slate-400 mt-1">🦙 {ollamaModels.length} local model(s) detected via Ollama</p>
            )}
            {ollamaModels.length === 0 && (
              <p className="text-[10px] text-slate-400 mt-1">No local Ollama models detected — using Claude Sonnet by default</p>
            )}
          </div>
          <textarea rows={2} placeholder="Custom instructions for the analyst…"
            value={customInstructions} onChange={e => setCustomInstructions(e.target.value)}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900 resize-none" />
          <div className="flex items-center gap-3">
            <button onClick={generate} disabled={generating}
              className="flex items-center gap-2 bg-slate-900 text-white px-4 py-2 rounded-lg text-sm hover:bg-slate-700 disabled:opacity-50">
              {generating ? <><Spinner size={12} /> Generating… (may take 1-2 min)</> : "Generate report"}
            </button>
          </div>
          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-xs text-red-600">
              <span className="font-medium">Error : </span>{error}
              <p className="text-red-400 mt-1">Check that the backend is active and the model is configured.</p>
            </div>
          )}
        </div>
      )}

      {reports.length > 0 && (
        <div className="space-y-2">
          {reports.map(r => (
            <div key={r.id} className="flex items-center justify-between text-xs bg-slate-50 rounded-lg px-3 py-2">
              <span className="text-slate-700 font-medium">{r.title}</span>
              <div className="flex items-center gap-2">
                <a href={reportsApi.exportUrl(r.id)} download
                  className="flex items-center gap-1 text-blue-600 hover:underline">
                  <Download size={10} /> .md
                </a>
                <a href={reportsApi.exportHtmlUrl(r.id)} download
                  className="flex items-center gap-1 text-purple-600 hover:underline">
                  <Download size={10} /> .html
                </a>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main Dashboard ────────────────────────────────────────────────────────────
function DashboardContent() {
  const searchParams = useSearchParams();
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [data, setData] = useState<DashboardData | null>(null);
  const [genome, setGenome] = useState<GenomeData | null>(null);
  const [failedData, setFailedData] = useState<FailedItemsData | null>(null);
  const [insights, setInsights] = useState<any>(null);
  const [compositionalRisk, setCompositionalRisk] = useState<any>(null);
  const [riskLoading, setRiskLoading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState<Tab>("overview");

  useEffect(() => { campaignsApi.list().then(c => setCampaigns(c.filter(x => x.status === "completed"))); }, []);

  useEffect(() => {
    const id = searchParams.get("campaign");
    if (id) setSelectedId(+id);
  }, [searchParams]);

  useEffect(() => {
    if (!selectedId) return;
    setLoading(true); setData(null); setGenome(null); setFailedData(null); setInsights(null);
    Promise.all([
      resultsApi.dashboard(selectedId),
      genomeApi.campaign(selectedId).catch(() => null),
      resultsApi.failedItems(selectedId).catch(() => null),
      resultsApi.insights(selectedId).catch(() => null),
    ]).then(([d, g, f, ins]) => {
      setData(d);
      setGenome(g);
      setFailedData(f);
      setInsights(ins);
    }).finally(() => setLoading(false));
  }, [selectedId]);

  const refreshFailedData = () => {
    if (!selectedId) return;
    resultsApi.failedItems(selectedId).then(setFailedData).catch(() => {});
  };

  useEffect(() => {
    if (!selectedId || !data) {
      setCompositionalRisk(null);
      return;
    }

    const domainScores: Record<string, number> = {};
    const setDomain = (key: string, score: number) => {
      const capped = Math.max(0, Math.min(1, score));
      domainScores[key] = Math.max(domainScores[key] ?? 0, capped);
    };

    for (const cell of data.heatmap) {
      if (cell.score == null) continue;
      const benchmark = cell.benchmark_name.toLowerCase();
      const risk = 1 - cell.score;
      if (/(cyber|mitre|attack|ckb)/.test(benchmark)) setDomain("cyber", risk);
      if (/(cbrn|bio|nuclear|radiological|chemical)/.test(benchmark)) setDomain("cbrn", risk);
      if (/(fimi|disarm|persuasion|information|influence)/.test(benchmark)) setDomain("persuasion", risk);
      if (/(scheming|sandbag|shutdown|sycophancy|alignment)/.test(benchmark)) {
        setDomain("scheming", risk);
        setDomain("sycophancy", risk * 0.8);
      }
      if (/(agentic|autonomy|goal drift|scope creep|failure mode)/.test(benchmark)) {
        setDomain("goal_drift", risk);
        setDomain("scope_creep", risk * 0.9);
        setDomain("error_compounding", risk * 0.85);
      }
    }

    if (Object.keys(domainScores).length === 0) {
      setCompositionalRisk(null);
      return;
    }

    const campaign = campaigns.find(c => c.id === selectedId);
    const desc = campaign?.description ?? "";
    const autonomyLevel = (desc.match(/Autonomy:\s*(L[1-5])/i)?.[1] ?? "L2").toUpperCase();
    const memoryType = /Memory:\s*enabled/i.test(desc) ? "persistent" : "session";
    const toolText = desc.match(/Tools:\s*([^|]+)/i)?.[1] ?? "";
    const toolMap: Record<string, string> = {
      "web search": "web_search",
      "code execution": "code_execution",
      "file system": "file_system",
      "email/calendar": "email",
      "database": "database",
      "external apis": "external_apis",
      "browser automation": "browser",
    };
    const tools = toolText
      .split(",")
      .map(t => t.trim().toLowerCase())
      .map(t => toolMap[t])
      .filter(Boolean);

    setRiskLoading(true);
    fetch(`${API_BASE}/science/compositional-risk`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model_name: data.campaign_name,
        domain_scores: domainScores,
        propensity_scores: {},
        autonomy_level: autonomyLevel,
        tools,
        memory_type: memoryType,
      }),
    })
      .then(async (res) => (res.ok ? res.json() : null))
      .then((json) => setCompositionalRisk(json))
      .catch(() => setCompositionalRisk(null))
      .finally(() => setRiskLoading(false));
  }, [selectedId, data, campaigns]);

  const signalCount = insights?.signals?.length ?? 0;

  const TABS: { key: Tab; label: string; badge?: number }[] = [
    { key: "overview", label: "📊 Overview" },
    { key: "genome", label: "🧬 Genome" },
    { key: "errors", label: "⚠️ Errors", badge: failedData ? failedData.total_failed + failedData.failed_runs.length : 0 },
    { key: "signals" as Tab, label: "🔗 Signals", badge: signalCount },
    { key: "report", label: "📝 Report" },
  ];

  return (
    <div>
      <PageHeader
        title="Dashboard"
        description="Visual analysis of evaluation results."
        action={
          selectedId && data?.status === "completed" ? (
            <div className="flex gap-2">
              <a href={resultsApi.exportUrl(selectedId)} download
                className="flex items-center gap-2 border border-slate-200 px-4 py-2 rounded-lg text-sm hover:bg-slate-50 text-slate-600">
                <Download size={14} /> Export CSV
              </a>
              <a href={`${API_BASE}/campaigns/${selectedId}/manifest`} download={`manifest-campaign-${selectedId}.json`}
                className="flex items-center gap-2 border border-purple-200 px-4 py-2 rounded-lg text-sm hover:bg-purple-50 text-purple-700">
                📋 Manifest
              </a>
            </div>
          ) : undefined
        }
      />

      <div className="p-4 sm:p-8">
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
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              {[
                { label: "Total cost", value: formatCost(data.total_cost_usd) },
                { label: "Average latency / run", value: formatLatency(data.avg_latency_ms) },
                { label: "Compared models", value: Object.keys(data.radar).length },
                { label: "Errors", value: failedData ? failedData.total_failed + failedData.failed_runs.length : "—",
                  alert: failedData && (failedData.total_failed + failedData.failed_runs.length) > 0 },
              ].map(({ label, value, alert }) => (
                <div key={label} className={`bg-white border rounded-xl p-4 ${alert ? "border-red-200" : "border-slate-200"}`}>
                  <div className="text-xs text-slate-500 mb-1">{label}</div>
                  <div className={`text-xl font-semibold ${alert ? "text-red-600" : "text-slate-900"}`}>{value}</div>
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

            {/* Tab navigation */}
            <div className="flex gap-1 overflow-x-auto border-b border-slate-100">
              {TABS.map(({ key, label, badge }) => (
                <button key={key} onClick={() => setTab(key)}
                  className={`px-4 py-2.5 text-sm border-b-2 transition-colors flex items-center gap-1.5
                    ${tab === key ? "border-slate-900 text-slate-900 font-medium" : "border-transparent text-slate-400 hover:text-slate-600"}`}>
                  {label}
                  {badge != null && badge > 0 && (
                    <span className="bg-red-500 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full">{badge}</span>
                  )}
                </button>
              ))}
            </div>

            {/* Tab content */}
            {tab === "overview" && (
              <div className="space-y-6">
                {(riskLoading || compositionalRisk?.system_threat_profile) && (
                  <div className="bg-white border border-slate-200 rounded-xl p-5">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="font-medium text-slate-900 text-sm">System Threat Profile</h3>
                      {riskLoading ? (
                        <span className="text-xs text-slate-400">Computing…</span>
                      ) : (
                        <span className={`text-[11px] px-2 py-0.5 rounded border font-bold ${
                          compositionalRisk?.system_threat_profile?.overall_risk_level === "critical" ? "bg-red-100 text-red-700 border-red-200" :
                          compositionalRisk?.system_threat_profile?.overall_risk_level === "high" ? "bg-orange-100 text-orange-700 border-orange-200" :
                          compositionalRisk?.system_threat_profile?.overall_risk_level === "medium" ? "bg-yellow-100 text-yellow-700 border-yellow-200" :
                          "bg-green-100 text-green-700 border-green-200"
                        }`}>
                          {(compositionalRisk?.system_threat_profile?.overall_risk_level ?? "low").toUpperCase()}
                        </span>
                      )}
                    </div>
                    {!riskLoading && compositionalRisk?.system_threat_profile && (
                      <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 text-xs">
                        <div className="bg-slate-50 rounded-lg p-3">
                          <div className="text-slate-400">Dominant vector</div>
                          <div className="font-medium text-slate-800 mt-0.5">{compositionalRisk.system_threat_profile.dominant_threat_vector}</div>
                        </div>
                        <div className="bg-slate-50 rounded-lg p-3">
                          <div className="text-slate-400">Composite score</div>
                          <div className="font-medium text-slate-800 mt-0.5">
                            {Math.round((compositionalRisk?.scores?.composite_risk_score ?? 0) * 100)}%
                          </div>
                        </div>
                        <div className="bg-slate-50 rounded-lg p-3">
                          <div className="text-slate-400">Composition ×</div>
                          <div className="font-medium text-slate-800 mt-0.5">{compositionalRisk.system_threat_profile.composition_multiplier}x</div>
                        </div>
                        <div className="bg-slate-50 rounded-lg p-3">
                          <div className="text-slate-400">Autonomy cert</div>
                          <div className="font-medium text-slate-800 mt-0.5">{compositionalRisk.system_threat_profile.autonomy_certification}</div>
                        </div>
                      </div>
                    )}
                  </div>
                )}
                <div className="grid grid-cols-2 gap-6">
                  <RadarSection radar={data.radar} />
                  <WinRateSection winRates={data.win_rates} />
                </div>
                <HeatmapSection heatmap={data.heatmap} />
              </div>
            )}

            {tab === "genome" && genome && <GenomeSection genome={genome} />}

            {tab === "errors" && failedData && selectedId && <FailedItemsSection failedData={failedData} campaignId={selectedId} onRefresh={refreshFailedData} />}

            {tab === "signals" && insights && (
              <div className="space-y-4 max-w-3xl">
                {/* Cross-module signals */}
                {insights.signals?.length > 0 ? (
                  <div className="space-y-2">
                    <h3 className="text-sm font-medium text-slate-900 mb-2">Signaux inter-modules</h3>
                    {insights.signals.map((sig: any, i: number) => (
                      <div key={i} className={`border rounded-xl p-4 ${
                        sig.severity === "high" ? "border-red-200 bg-red-50" : "border-yellow-200 bg-yellow-50"
                      }`}>
                        <div className="flex items-center gap-2 mb-1">
                          <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${
                            sig.type === "genome_redbox" ? "bg-red-100 text-red-700" :
                            sig.type === "judge_disagreement" ? "bg-purple-100 text-purple-700" :
                            "bg-orange-100 text-orange-700"
                          }`}>{
                            sig.type === "genome_redbox" ? "🧬→🔴 Genome → REDBOX" :
                            sig.type === "judge_disagreement" ? "⚖️ Judge Disagreement" :
                            "🔴 REDBOX Alert"
                          }</span>
                          <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${
                            sig.severity === "high" ? "bg-red-600 text-white" : "bg-yellow-500 text-white"
                          }`}>{sig.severity}</span>
                        </div>
                        <p className="text-xs text-slate-700">{sig.message}</p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="bg-green-50 border border-green-200 rounded-xl p-6 text-center">
                    <div className="text-2xl mb-1">✅</div>
                    <p className="text-sm text-green-700">No signals d'alerte inter-modules</p>
                  </div>
                )}

                {/* Module status */}
                <div className="bg-white border border-slate-200 rounded-xl p-5">
                  <h3 className="text-sm font-medium text-slate-900 mb-3">Modules actifs</h3>
                  <div className="grid grid-cols-4 gap-3">
                    {Object.entries(insights.modules_active ?? {}).map(([mod, active]: any) => (
                      <div key={mod} className={`text-center p-3 rounded-lg border ${active ? "bg-green-50 border-green-200" : "bg-slate-50 border-slate-200"}`}>
                        <div className="text-lg">{mod === "eval" ? "📊" : mod === "genome" ? "🧬" : mod === "judge" ? "⚖️" : "🔴"}</div>
                        <div className="text-xs font-medium text-slate-700 capitalize">{mod}</div>
                        <div className={`text-[10px] ${active ? "text-green-600" : "text-slate-400"}`}>{active ? "Active" : "Inactive"}</div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Judge summary from insights */}
                {insights.judge?.total_evaluations > 0 && (
                  <div className="bg-white border border-slate-200 rounded-xl p-5">
                    <h3 className="text-sm font-medium text-slate-900 mb-3">⚖️ Judge Summary</h3>
                    <div className="space-y-2">
                      {Object.entries(insights.judge.judges ?? {}).map(([judge, stats]: any) => (
                        <div key={judge} className="flex items-center gap-3 text-xs">
                          <span className="text-slate-600 flex-1 truncate">{judge}</span>
                          <span className="font-mono font-bold text-slate-900">{(stats.avg_score * 100).toFixed(1)}%</span>
                          <span className="text-slate-400">{stats.n} evals</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* REDBOX summary from insights */}
                {insights.redbox?.total_tested > 0 && (
                  <div className={`border rounded-xl p-5 ${insights.redbox.breach_rate > 0.3 ? "bg-red-50 border-red-200" : "bg-white border-slate-200"}`}>
                    <h3 className="text-sm font-medium text-slate-900 mb-3">🔴 REDBOX Summary</h3>
                    <div className="grid grid-cols-3 gap-4 text-center">
                      <div>
                        <div className="text-xs text-slate-400">Tested</div>
                        <div className="text-lg font-bold text-slate-900">{insights.redbox.total_tested}</div>
                      </div>
                      <div>
                        <div className="text-xs text-slate-400">Breached</div>
                        <div className="text-lg font-bold text-red-600">{insights.redbox.total_breached}</div>
                      </div>
                      <div>
                        <div className="text-xs text-slate-400">Avg Severity</div>
                        <div className="text-lg font-bold text-slate-900">{Math.round(insights.redbox.avg_severity * 100)}%</div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {tab === "report" && selectedId && <ReportPanel campaignId={selectedId} />}
          </div>
        )}

        {!selectedId && !loading && (
          <div className="text-center py-20 text-slate-400 text-sm">
            Select a completed campaign to display the dashboard.
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
