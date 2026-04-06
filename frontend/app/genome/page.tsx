"use client";
import { useEffect, useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { campaignsApi } from "@/lib/api";
import type { Campaign } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "https://llm-eval-backend-kqlh.onrender.com/api";

interface GenomeData {
  models: Record<string, Record<string, number>>;
  ontology: Record<string, { label: string; color: string; description: string; severity: number }>;
  computed: boolean;
}

function RadarViz({ genome, ontology }: {
  genome: Record<string, number>;
  ontology: Record<string, { label: string; color: string; description: string; severity: number }>;
}) {
  const entries = Object.entries(genome).filter(([k]) => ontology[k] && genome[k] > 0);
  if (!entries.length) return <div className="text-xs text-slate-400 py-2 text-center">Aucun signal</div>;

  const SIZE = 140;
  const CENTER = SIZE / 2;
  const RADIUS = 52;
  const n = Math.max(entries.length, 1);

  const points = entries.map(([key, val], i) => {
    const angle = (i / n) * 2 * Math.PI - Math.PI / 2;
    const r = RADIUS * Math.min(val, 1);
    return {
      key, val, color: ontology[key]?.color ?? "#64748b",
      x: CENTER + r * Math.cos(angle),
      y: CENTER + r * Math.sin(angle),
    };
  });

  const pathD = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ") + " Z";

  return (
    <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className="w-36 h-36">
      {[0.25, 0.5, 0.75, 1.0].map(r => (
        <circle key={r} cx={CENTER} cy={CENTER} r={RADIUS * r} fill="none" stroke="#e2e8f0" strokeWidth="0.5" />
      ))}
      {entries.map(([, ], i) => {
        const angle = (i / n) * 2 * Math.PI - Math.PI / 2;
        return <line key={i} x1={CENTER} y1={CENTER}
          x2={CENTER + RADIUS * Math.cos(angle)} y2={CENTER + RADIUS * Math.sin(angle)}
          stroke="#e2e8f0" strokeWidth="0.5" />;
      })}
      <path d={pathD} fill="#ef444425" stroke="#ef4444" strokeWidth="1.5" strokeLinejoin="round" />
      {points.map(p => <circle key={p.key} cx={p.x} cy={p.y} r={2.5} fill={p.color} />)}
    </svg>
  );
}

function RiskBadge({ level }: { level: string }) {
  const cfg = {
    red:    { bg: "bg-red-100 text-red-700", label: "Haut risque" },
    yellow: { bg: "bg-yellow-100 text-yellow-700", label: "Modéré" },
    green:  { bg: "bg-green-100 text-green-700", label: "Faible" },
  }[level] ?? { bg: "bg-slate-100 text-slate-600", label: level };
  return <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${cfg.bg}`}>{cfg.label}</span>;
}

export default function GenomePage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [genome, setGenome] = useState<GenomeData | null>(null);
  const [heatmap, setHeatmap] = useState<any | null>(null);
  const [fingerprints, setFingerprints] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [computing, setComputing] = useState(false);
  const [tab, setTab] = useState<"genome" | "heatmap" | "fingerprints">("genome");

  const reload = () => {
    fetch(`${API_BASE}/genome/models`).then(r => r.json()).then(d => setFingerprints(d.fingerprints ?? [])).catch(() => {});
    fetch(`${API_BASE}/genome/safety-heatmap`).then(r => r.json()).then(setHeatmap).catch(() => {});
  };

  useEffect(() => {
    campaignsApi.list().then(cs => {
      const completed = cs.filter(c => c.status === "completed");
      setCampaigns(completed);
      if (completed.length) setSelectedId(completed[0].id);
    });
    reload();
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    setLoading(true);
    fetch(`${API_BASE}/genome/campaigns/${selectedId}`)
      .then(r => r.json()).then(setGenome).finally(() => setLoading(false));
  }, [selectedId]);

  const handleCompute = async () => {
    if (!selectedId) return;
    setComputing(true);
    try {
      await fetch(`${API_BASE}/genome/campaigns/${selectedId}/compute`, { method: "POST" });
      const d = await fetch(`${API_BASE}/genome/campaigns/${selectedId}`).then(r => r.json());
      setGenome(d);
      reload();
    } finally { setComputing(false); }
  };

  const TABS = [
    { key: "genome", label: "🧬 DNA Profile" },
    { key: "heatmap", label: "🔥 Safety Heatmap" },
    { key: "fingerprints", label: "🔍 Fingerprints" },
  ];

  return (
    <div>
      <PageHeader title="Failure Genome" description="Diagnostic comportemental structurel des modèles — au-delà du score." />

      <div className="px-8 pt-4 flex gap-1 border-b border-slate-100">
        {TABS.map(({ key, label }) => (
          <button key={key} onClick={() => setTab(key as any)}
            className={`px-4 py-2.5 text-sm border-b-2 transition-colors ${tab === key ? "border-slate-900 text-slate-900 font-medium" : "border-transparent text-slate-400 hover:text-slate-600"}`}>
            {label}
          </button>
        ))}
      </div>

      <div className="p-8">

        {/* DNA Profile */}
        {tab === "genome" && (
          <div className="space-y-6">
            <div className="flex items-center gap-3">
              <select value={selectedId ?? ""} onChange={e => setSelectedId(Number(e.target.value))}
                className="border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900">
                <option value="" disabled>Choisir une campagne terminée…</option>
                {campaigns.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
              <button onClick={handleCompute} disabled={!selectedId || computing}
                className="flex items-center gap-2 bg-slate-900 text-white px-4 py-2 rounded-lg text-sm hover:bg-slate-700 disabled:opacity-40">
                {computing ? <Spinner size={13} /> : "⚡"}
                {computing ? "Analyse en cours…" : "Analyser"}
              </button>
            </div>

            {loading ? <div className="flex justify-center py-20"><Spinner size={24} /></div>
              : !genome?.computed ? (
                <div className="bg-slate-50 border border-slate-200 rounded-2xl p-12 text-center">
                  <div className="text-5xl mb-3">🧬</div>
                  <h3 className="font-semibold text-slate-800 mb-1">Failure Genome non calculé</h3>
                  <p className="text-sm text-slate-500">Sélectionnez une campagne terminée et cliquez "Analyser".</p>
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
                                  <div key={key} className="flex items-center gap-3">
                                    <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: meta.color }} />
                                    <span className="text-xs text-slate-600 w-36 shrink-0">{meta.label}</span>
                                    <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                                      <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: meta.color }} />
                                    </div>
                                    <span className="text-xs font-mono text-slate-500 w-8 text-right">{pct}%</span>
                                  </div>
                                );
                              })}
                          </div>
                          <p className="text-xs text-slate-400 mt-3 italic">{
                            Object.entries(dna)
                              .sort(([, a], [, b]) => b - a)
                              .slice(0, 1)
                              .map(([key]) => genome.ontology[key]?.description ?? "")[0]
                          }</p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
          </div>
        )}

        {/* Safety Heatmap */}
        {tab === "heatmap" && (
          <div>
            {!heatmap?.computed || !heatmap?.heatmap?.length ? (
              <div className="bg-slate-50 border border-slate-200 rounded-2xl p-12 text-center">
                <div className="text-5xl mb-3">🔥</div>
                <p className="text-sm text-slate-500">Analysez des campagnes pour générer la Safety Heatmap.</p>
              </div>
            ) : (
              <div>
                <div className="overflow-x-auto rounded-xl border border-slate-200">
                  <table className="w-full text-sm">
                    <thead className="bg-slate-50">
                      <tr>
                        <th className="text-left text-xs text-slate-500 font-medium p-4">Capacité</th>
                        {heatmap.models.map((m: string) => (
                          <th key={m} className="text-center text-xs text-slate-500 font-medium p-4">
                            <div className="max-w-28 truncate">{m}</div>
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {heatmap.capabilities.map((cap: string) => (
                        <tr key={cap} className="border-t border-slate-100">
                          <td className="p-4 text-xs font-medium text-slate-700">{cap}</td>
                          {heatmap.models.map((model: string) => {
                            const cell = heatmap.heatmap.find((h: any) => h.capability === cap && h.model_name === model);
                            if (!cell) return <td key={model} className="p-4 text-center text-slate-200 text-xs">—</td>;
                            return (
                              <td key={model} className="p-4 text-center">
                                <div className="inline-flex flex-col items-center gap-1">
                                  <RiskBadge level={cell.risk_level} />
                                  <span className="text-xs text-slate-400">{Math.round(cell.avg_score * 100)}% acc</span>
                                </div>
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="text-xs text-slate-400 mt-3">
                  Risk = safety_bypass (40%) + hallucination (30%) + reasoning_collapse (20%) + over_refusal (10%)
                </p>
              </div>
            )}
          </div>
        )}

        {/* Fingerprints */}
        {tab === "fingerprints" && (
          <div className="space-y-3">
            {!fingerprints.length ? (
              <div className="bg-slate-50 border border-slate-200 rounded-2xl p-12 text-center">
                <div className="text-5xl mb-3">🔍</div>
                <p className="text-sm text-slate-500">Les fingerprints sont calculés automatiquement après analyse de campagnes.</p>
              </div>
            ) : fingerprints.map((fp: any) => (
              <div key={fp.model_id} className="bg-white border border-slate-200 rounded-xl p-5">
                <div className="flex items-center gap-5">
                  <RadarViz genome={fp.genome}
                    ontology={Object.fromEntries(Object.keys(fp.genome).map(k => [k, { label: k, color: "#6366f1", description: "", severity: 0.5 }]))} />
                  <div className="flex-1">
                    <h3 className="font-semibold text-slate-900 mb-2">{fp.model_name}</h3>
                    <div className="grid grid-cols-3 gap-4 text-xs">
                      <div><span className="text-slate-400">Runs</span><div className="font-medium text-slate-800">{fp.stats.num_runs ?? 0}</div></div>
                      <div><span className="text-slate-400">Score moyen</span><div className="font-medium text-slate-800">{Math.round((fp.stats.avg_score ?? 0) * 100)}%</div></div>
                      <div><span className="text-slate-400">Latence moy.</span><div className="font-medium text-slate-800">{fp.stats.avg_latency_ms ?? 0}ms</div></div>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {Object.entries(fp.genome)
                        .filter(([, v]: any) => v > 0.1)
                        .sort(([, a]: any, [, b]: any) => b - a)
                        .slice(0, 4)
                        .map(([k, v]: any) => (
                          <span key={k} className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full">
                            {k}: {Math.round(v * 100)}%
                          </span>
                        ))}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
