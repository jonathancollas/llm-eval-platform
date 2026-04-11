"use client";
import { useEffect, useState, useCallback } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { AppErrorBoundary } from "@/components/AppErrorBoundary";
import { campaignsApi } from "@/lib/api";
import { API_BASE } from "@/lib/config";
import type { Campaign } from "@/lib/api";
import Link from "next/link";

interface GenomeData {
  models: Record<string, Record<string, number>>;
  ontology: Record<string, { label: string; color: string; description: string; severity: number }>;
  computed: boolean;
  genome_version?: string;
}

// ── Radar viz ─────────────────────────────────────────────────────────────────
function RadarViz({ genome, ontology }: {
  genome: Record<string, number>;
  ontology: Record<string, { label: string; color: string; description: string; severity: number }>;
}) {
  const entries = Object.entries(genome).filter(([k]) => ontology[k] && genome[k] > 0);
  if (!entries.length) return <div className="text-xs text-slate-400 py-2 text-center">No signals</div>;

  const SIZE = 140, CENTER = SIZE / 2, RADIUS = 52;
  const n = Math.max(entries.length, 1);
  const points = entries.map(([key, val], i) => {
    const angle = (i / n) * 2 * Math.PI - Math.PI / 2;
    const r = RADIUS * Math.min(val, 1);
    return { key, val, color: ontology[key]?.color ?? "#64748b", x: CENTER + r * Math.cos(angle), y: CENTER + r * Math.sin(angle) };
  });
  const pathD = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ") + " Z";

  return (
    <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className="w-36 h-36">
      {[0.25, 0.5, 0.75, 1.0].map(r => (
        <circle key={r} cx={CENTER} cy={CENTER} r={RADIUS * r} fill="none" stroke="#e2e8f0" strokeWidth="0.5" />
      ))}
      {entries.map((_, i) => {
        const angle = (i / n) * 2 * Math.PI - Math.PI / 2;
        return <line key={i} x1={CENTER} y1={CENTER} x2={CENTER + RADIUS * Math.cos(angle)} y2={CENTER + RADIUS * Math.sin(angle)} stroke="#e2e8f0" strokeWidth="0.5" />;
      })}
      <path d={pathD} fill="#ef444425" stroke="#ef4444" strokeWidth="1.5" strokeLinejoin="round" />
      {points.map(p => <circle key={p.key} cx={p.x} cy={p.y} r={2.5} fill={p.color} />)}
    </svg>
  );
}

function RiskBadge({ level }: { level: string }) {
  const cfg = {
    red:    { bg: "bg-red-100 text-red-700",     label: "Haut risque" },
    yellow: { bg: "bg-yellow-100 text-yellow-700", label: "Moderate" },
    green:  { bg: "bg-green-100 text-green-700",  label: "Faible" },
  }[level] ?? { bg: "bg-slate-100 text-slate-600", label: level };
  return <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${cfg.bg}`}>{cfg.label}</span>;
}

// ── Signal row — expandable with heuristic explanation + papers (#83/#90) ──────
interface HeuristicDetail {
  label: string; description: string; detection_logic: string;
  severity_weight: number; false_positive_profile: string;
  failure_cases: string[]; eval_dimension: string;
  papers: { title: string; authors: string; year: number; url?: string }[];
}

function SignalRow({ sigKey, meta, pct }: {
  sigKey: string;
  meta: { label: string; color: string; description: string; severity: number };
  pct: number;
}) {
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState<HeuristicDetail | null>(null);
  const [loading, setLoading] = useState(false);

  const loadDetail = async () => {
    if (detail || loading) { setOpen(o => !o); return; }
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/genome/heuristics/signal/${sigKey}`);
      if (res.ok) setDetail(await res.json());
    } catch {}
    setLoading(false);
    setOpen(true);
  };

  return (
    <div className="rounded-lg border border-transparent hover:border-slate-100 transition-colors">
      {/* Main row */}
      <button
        className="w-full flex items-center gap-3 py-1 text-left"
        onClick={loadDetail}
        title="Click to see heuristic explanation and papers"
      >
        <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: meta.color }} />
        <span className="text-xs text-slate-600 w-36 shrink-0">{meta.label}</span>
        <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
          <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, backgroundColor: meta.color }} />
        </div>
        <span className="text-xs font-mono text-slate-500 w-8 text-right">{pct}%</span>
        {meta.severity >= 4 && <RiskBadge level="red" />}
        {meta.severity === 3 && <RiskBadge level="yellow" />}
        {loading
          ? <span className="text-[10px] text-slate-300">…</span>
          : <span className="text-[10px] text-slate-300">{open ? "▲" : "▼"}</span>
        }
      </button>

      {/* Expandable heuristic detail */}
      {open && (
        <div className="ml-5 mb-2 px-3 py-3 bg-slate-50 rounded-lg border border-slate-100 text-xs space-y-2">
          <p className="text-slate-600 leading-relaxed">
            <span className="font-medium text-slate-700">Description : </span>
            {detail?.description ?? meta.description}
          </p>
          {detail?.detection_logic && (
            <p className="text-slate-600">
              <span className="font-medium text-slate-700">Détection : </span>
              {detail.detection_logic}
            </p>
          )}
          {detail?.false_positive_profile && (
            <p className="text-slate-500 italic">
              <span className="not-italic font-medium text-slate-600">Faux positifs : </span>
              {detail.false_positive_profile}
            </p>
          )}
          {detail?.failure_cases && detail.failure_cases.length > 0 && (
            <div>
              <span className="font-medium text-slate-700">Cas d&apos;échec : </span>
              <ul className="mt-0.5 space-y-0.5 pl-3">
                {detail.failure_cases.map((c, i) => (
                  <li key={i} className="text-slate-500 list-disc list-inside">{c}</li>
                ))}
              </ul>
            </div>
          )}
          {detail?.eval_dimension && (
            <span className="inline-block px-2 py-0.5 rounded bg-blue-50 text-blue-600 border border-blue-100 font-medium capitalize">
              {detail.eval_dimension}
            </span>
          )}
          {detail?.papers && detail.papers.length > 0 && (
            <div className="pt-1 border-t border-slate-200">
              <span className="font-medium text-slate-600">📚 Références scientifiques :</span>
              <ul className="mt-1 space-y-1">
                {detail.papers.map((p, i) => (
                  <li key={i} className="text-slate-500">
                    {p.url
                      ? <a href={p.url} target="_blank" rel="noopener noreferrer"
                           className="text-blue-500 hover:underline font-medium">{p.title}</a>
                      : <span className="font-medium">{p.title}</span>
                    }
                    {" "}— {p.authors} ({p.year})
                  </li>
                ))}
              </ul>
            </div>
          )}
          {!detail && !loading && (
            <p className="text-slate-400 italic">No detailed heuristic found for this signal.</p>
          )}
        </div>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
function GenomePage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [genome, setGenome] = useState<GenomeData | null>(null);
  const [heatmap, setHeatmap] = useState<any | null>(null);
  const [fingerprints, setFingerprints] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [computing, setComputing] = useState(false);
  const [computeError, setComputeError] = useState<string | null>(null);
  const [tab, setTab] = useState<"genome" | "heatmap" | "fingerprints">("genome");

  const reload = useCallback(() => {
    fetch(`${API_BASE}/genome/models`)
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setFingerprints(d.fingerprints ?? []))
      .catch(() => {});
    fetch(`${API_BASE}/genome/safety-heatmap`)
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setHeatmap(d))
      .catch(() => {});
  }, []);

  const fetchGenome = useCallback((id: number) => {
    setLoading(true);
    setComputeError(null);
    fetch(`${API_BASE}/genome/campaigns/${id}`)
      .then(r => r.ok ? r.json() : null)
      .then(d => setGenome(d ?? null))
      .catch(e => setComputeError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    campaignsApi.list()
      .then(cs => {
        const completed = cs.filter(c => c.status === "completed");
        setCampaigns(completed);
        if (completed.length) { setSelectedId(completed[0].id); }
      })
      .catch(() => {});
    reload();
  }, [reload]);

  useEffect(() => {
    if (selectedId) fetchGenome(selectedId);
  }, [selectedId, fetchGenome]);

  const handleCompute = async (hybrid = false) => {
    if (!selectedId) return;
    setComputing(true);
    setComputeError(null);
    try {
      const endpoint = hybrid
        ? `${API_BASE}/genome/campaigns/${selectedId}/compute-hybrid`
        : `${API_BASE}/genome/campaigns/${selectedId}/compute`;
      const res = await fetch(endpoint, { method: "POST" });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      fetchGenome(selectedId);
      reload();
    } catch (e: any) {
      setComputeError(e.message ?? String(e));
    } finally {
      setComputing(false);
    }
  };

  const TABS = [
    { key: "genome",       label: "🧬 DNA Profile" },
    { key: "heatmap",      label: "🔥 Safety Heatmap" },
    { key: "fingerprints", label: "🔍 Fingerprints" },
  ];

  return (
    <div>
      <PageHeader
        title="Genomia"
        description="Structural behavioral diagnostic of models — beyond the score."
      />

      <div className="px-8 pt-4 flex gap-1 border-b border-slate-100">
        {TABS.map(({ key, label }) => (
          <button key={key} onClick={() => setTab(key as any)}
            className={`px-4 py-2.5 text-sm border-b-2 transition-colors ${
              tab === key ? "border-slate-900 text-slate-900 font-medium" : "border-transparent text-slate-400 hover:text-slate-600"
            }`}>{label}</button>
        ))}
        <Link href="/methodology" className="ml-auto px-4 py-2.5 text-xs text-slate-400 hover:text-blue-500 flex items-center gap-1">
          📚 Scientific papers →
        </Link>
      </div>

      <div className="p-8">

        {/* ── DNA Profile ───────────────────────────────────────────────── */}
        {tab === "genome" && (
          <div className="space-y-6">
            <div className="flex items-center gap-3 flex-wrap">
              <select value={selectedId ?? ""} onChange={e => setSelectedId(Number(e.target.value))}
                className="border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900">
                <option value="" disabled>Select a completed campaign…</option>
                {campaigns.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
              <button onClick={() => handleCompute(false)} disabled={!selectedId || computing}
                className="flex items-center gap-2 bg-slate-900 text-white px-4 py-2 rounded-lg text-sm hover:bg-slate-700 disabled:opacity-40">
                {computing ? <Spinner size={13} /> : "⚡"} {computing ? "Analysis in progress…" : "Analyze"}
              </button>
              <button onClick={() => handleCompute(true)} disabled={!selectedId || computing}
                className="flex items-center gap-2 border border-purple-300 text-purple-700 px-4 py-2 rounded-lg text-sm hover:bg-purple-50 disabled:opacity-40"
                title="Uses Claude for uncertain classifications — more accurate but slower">
                {computing ? <Spinner size={13} /> : "🧠"} Hybrid (LLM)
              </button>
            </div>

            {computeError && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-xs text-red-600 flex items-center gap-2">
                ⚠️ {computeError}
              </div>
            )}

            {loading
              ? <div className="flex justify-center py-20"><Spinner size={24} /></div>
              : !genome?.computed
              ? (
                <div className="bg-slate-50 border border-slate-200 rounded-2xl p-12 text-center">
                  <div className="text-5xl mb-3">🧬</div>
                  <h3 className="font-semibold text-slate-800 mb-1">Genomia not computed</h3>
                  <p className="text-sm text-slate-500">Select a completed campaign and click "Analyze".</p>
                </div>
              ) : (
                <div className="space-y-4">
                  {Object.entries(genome.models).map(([modelName, dna]) => (
                    <div key={modelName} className="bg-white border border-slate-200 rounded-2xl p-6">
                      <div className="flex items-start gap-6">
                        <RadarViz genome={dna} ontology={genome.ontology} />
                        <div className="flex-1">
                          <h3 className="font-semibold text-slate-900 mb-4">{modelName}</h3>
                          <div className="space-y-2">
                            {Object.entries(dna)
                              .filter(([, v]) => v > 0)
                              .sort(([, a], [, b]) => b - a)
                              .map(([key, val]) => {
                                const meta = genome.ontology[key];
                                if (!meta) return null;
                                const pct = Math.round(val * 100);
                                return (
                                  <SignalRow
                                    key={key}
                                    sigKey={key}
                                    meta={meta}
                                    pct={pct}
                                  />
                                );
                              })}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )
            }
          </div>
        )}

        {/* ── Safety Heatmap ────────────────────────────────────────────── */}
        {tab === "heatmap" && (
          <div className="space-y-4">
            {!heatmap?.computed || !heatmap?.heatmap?.length ? (
              <div className="bg-slate-50 border border-slate-200 rounded-2xl p-12 text-center">
                <div className="text-4xl mb-3">🔥</div>
                <h3 className="font-semibold text-slate-800 mb-1">No heatmap data</h3>
                <p className="text-sm text-slate-500">Run evaluations and compute Genomia to see the safety heatmap.</p>
              </div>
            ) : (
              <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
                <div className="px-5 py-3 border-b border-slate-100">
                  <h3 className="font-medium text-slate-900 text-sm">Safety Capability Heatmap</h3>
                  <p className="text-xs text-slate-500 mt-0.5">{heatmap.models?.length} models × {heatmap.capabilities?.length} failure modes</p>
                </div>
                <div className="overflow-x-auto p-4">
                  <table className="text-xs">
                    <thead>
                      <tr>
                        <th className="text-left font-medium text-slate-500 pr-4 pb-2">Model</th>
                        {heatmap.capabilities?.map((cap: string) => (
                          <th key={cap} className="text-center font-medium text-slate-500 px-2 pb-2 max-w-20">
                            <div className="truncate text-[10px]" style={{ writingMode: "vertical-lr", transform: "rotate(180deg)", height: 60 }}>{cap}</div>
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {heatmap.models?.map((model: string) => (
                        <tr key={model}>
                          <td className="font-medium text-slate-700 pr-4 py-1.5 whitespace-nowrap text-xs">{model}</td>
                          {heatmap.capabilities?.map((cap: string) => {
                            const cell = heatmap.heatmap?.find((c: any) => c.model_name === model && c.capability === cap);
                            const score = cell?.score ?? null;
                            const bg = score == null ? "#f1f5f9"
                              : score > 0.7 ? "#ef4444"
                              : score > 0.4 ? "#f97316"
                              : score > 0.2 ? "#eab308"
                              : "#22c55e";
                            return (
                              <td key={cap} className="px-2 py-1.5 text-center">
                                <div className="w-10 h-7 rounded flex items-center justify-center text-[10px] font-mono font-medium"
                                  style={{ backgroundColor: bg, color: score != null ? "white" : "#94a3b8" }}>
                                  {score != null ? `${(score * 100).toFixed(0)}%` : "—"}
                                </div>
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="px-4 py-3 border-t border-slate-100 flex items-center gap-4 text-[10px] text-slate-400">
                  {[["#ef4444", ">70%"], ["#f97316", "40-70%"], ["#eab308", "20-40%"], ["#22c55e", "<20%"]].map(([c, l]) => (
                    <span key={l} className="flex items-center gap-1">
                      <span className="w-3 h-3 rounded" style={{ backgroundColor: c }} />{l}
                    </span>
                  ))}
                  <span className="ml-2 text-slate-300">Higher % = more risk signals detected</span>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── Fingerprints ──────────────────────────────────────────────── */}
        {tab === "fingerprints" && (
          <div className="space-y-3">
            {fingerprints.length === 0 ? (
              <div className="bg-slate-50 border border-slate-200 rounded-2xl p-12 text-center">
                <div className="text-4xl mb-3">🔍</div>
                <h3 className="font-semibold text-slate-800 mb-1">No fingerprints yet</h3>
                <p className="text-sm text-slate-500">Run evaluations across multiple campaigns to build behavioral fingerprints.</p>
              </div>
            ) : (
              fingerprints.map((fp: any) => (
                <div key={fp.model_id} className="bg-white border border-slate-200 rounded-xl p-5">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="font-medium text-slate-900">{fp.model_name}</h3>
                    <div className="text-xs text-slate-400">{fp.stats?.num_runs ?? 0} runs</div>
                  </div>
                  <div className="grid grid-cols-3 gap-3 text-xs mb-3">
                    <div className="bg-slate-50 rounded-lg p-2">
                      <div className="text-slate-400">Avg Score</div>
                      <div className="font-bold text-slate-800">{fp.stats?.avg_score != null ? `${(fp.stats.avg_score * 100).toFixed(1)}%` : "—"}</div>
                    </div>
                    <div className="bg-slate-50 rounded-lg p-2">
                      <div className="text-slate-400">Refusal Rate</div>
                      <div className="font-bold text-slate-800">{fp.stats?.refusal_rate != null ? `${(fp.stats.refusal_rate * 100).toFixed(1)}%` : "—"}</div>
                    </div>
                    <div className="bg-slate-50 rounded-lg p-2">
                      <div className="text-slate-400">Avg Latency</div>
                      <div className="font-bold text-slate-800">{fp.stats?.avg_latency ? `${fp.stats.avg_latency}ms` : "—"}</div>
                    </div>
                  </div>
                  {fp.genome && Object.keys(fp.genome).length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {Object.entries(fp.genome)
                        .filter(([, v]: any) => v > 0.05)
                        .sort(([, a]: any, [, b]: any) => b - a)
                        .slice(0, 6)
                        .map(([key, val]: any) => (
                          <span key={key} className="text-[10px] px-2 py-0.5 bg-red-50 text-red-600 border border-red-100 rounded-full">
                            {key}: {(val * 100).toFixed(0)}%
                          </span>
                        ))}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        )}

      </div>
    </div>
  );
}

export default function GenomePageWrapper() {
  return (
    <AppErrorBoundary>
      <GenomePage />
    </AppErrorBoundary>
  );
}
