"use client";
import { useState, useEffect } from "react";
import { benchmarksApi } from "@/lib/api";
import { Badge } from "./Badge";
import { Spinner } from "./Spinner";
import { benchmarkTypeColor } from "@/lib/utils";
import { X, Plus, CheckCircle, AlertTriangle, Shield } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "https://llm-eval-backend-kqlh.onrender.com/api";

interface CatalogBenchmark {
  key: string; name: string; type: string; domain: string;
  description: string; metric: string; num_samples: number;
  dataset_path: string; tags: string[];
  risk_threshold: number | null; is_frontier: boolean;
  methodology_note: string | null; paper_url?: string | null; year?: number | null;
}

const DOMAIN_ICONS: Record<string, string> = {
  "raisonnement": "🧠", "maths": "🔢", "factualité": "📚", "connaissances": "🎓",
  "code": "💻", "français": "🇫🇷", "multilingue": "🌍",
  "cybersécurité offensive": "🛡️", "CBRN-E": "☢️", "risques agentiques": "🤖",
  "méta-évaluation": "🔬", "alignment": "⚖️", "désinformation": "📡",
  "agentique": "🤖", "NLI": "🔗", "médecine": "🏥", "droit": "⚖️",
  "finance": "💹", "sciences": "🔭", "instruction following": "📋",
};

const FILTER_TABS = [
  { key: "all", label: "Tous" },
  { key: "raisonnement", label: "Raisonnement" },
  { key: "connaissances", label: "Connaissances" },
  { key: "maths", label: "Maths" },
  { key: "code", label: "Code" },
  { key: "français", label: "Français" },
  { key: "safety", label: "Safety" },
  { key: "frontier", label: "🛡️ Frontier" },
] as const;

type FilterKey = typeof FILTER_TABS[number]["key"];

export function BenchmarkCatalogModal({ onClose }: { onClose: () => void }) {
  const [catalog, setCatalog] = useState<CatalogBenchmark[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<FilterKey>("all");
  const [added, setAdded] = useState<Set<string>>(new Set());
  const [adding, setAdding] = useState<string | null>(null);
  const [addingAll, setAddingAll] = useState(false);
  const [addAllProgress, setAddAllProgress] = useState<{ done: number; total: number } | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/catalog/benchmarks`)
      .then(r => r.json())
      .then(setCatalog)
      .finally(() => setLoading(false));
  }, []);

  const filtered = catalog.filter(b => {
    if (filter === "all") return true;
    if (filter === "frontier") return b.is_frontier;
    if (filter === "safety") return b.type === "safety";
    if (filter === "français") return b.domain === "français" || b.domain === "multilingue";
    return b.domain === filter || b.type === filter;
  });

  const addOne = async (b: CatalogBenchmark): Promise<boolean> => {
    try {
      await benchmarksApi.create({
        name: b.name, type: b.type as any, description: b.description,
        tags: b.tags, metric: b.metric, num_samples: b.num_samples,
        config: {}, risk_threshold: b.risk_threshold ?? undefined,
      });
      return true;
    } catch (e: any) {
      // already exists = ok
      return String(e).includes("409") || String(e).includes("already");
    }
  };

  const handleAdd = async (b: CatalogBenchmark) => {
    setAdding(b.key);
    const ok = await addOne(b);
    if (ok) setAdded(prev => new Set([...prev, b.key]));
    setAdding(null);
  };

  const handleAddAll = async () => {
    const toAdd = filtered.filter(b => !added.has(b.key));
    if (!toAdd.length) return;
    // Safety gate for frontier
    if (filter !== "frontier" && toAdd.some(b => b.is_frontier)) {
      const confirmed = window.confirm(
        `${toAdd.filter(b => b.is_frontier).length} benchmark(s) frontier sont inclus dans la sélection. Confirmer l'ajout ?`
      );
      if (!confirmed) return;
    }
    setAddingAll(true);
    setAddAllProgress({ done: 0, total: toAdd.length });
    const newAdded = new Set(added);
    for (let i = 0; i < toAdd.length; i++) {
      const ok = await addOne(toAdd[i]);
      if (ok) newAdded.add(toAdd[i].key);
      setAddAllProgress({ done: i + 1, total: toAdd.length });
    }
    setAdded(newAdded);
    setAddingAll(false);
    setAddAllProgress(null);
  };

  const notAddedCount = filtered.filter(b => !added.has(b.key)).length;

  const countFor = (f: FilterKey) => {
    if (f === "all") return catalog.length;
    if (f === "frontier") return catalog.filter(b => b.is_frontier).length;
    if (f === "safety") return catalog.filter(b => b.type === "safety").length;
    if (f === "français") return catalog.filter(b => b.domain === "français" || b.domain === "multilingue").length;
    return catalog.filter(b => b.domain === f || b.type === f).length;
  };

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl w-full max-w-4xl max-h-[85vh] flex flex-col shadow-2xl">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <div>
            <h2 className="font-semibold text-slate-900">Catalogue de benchmarks</h2>
            <p className="text-xs text-slate-400 mt-0.5">INESIA · {catalog.length} benchmarks mondiaux</p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-lg"><X size={16} /></button>
        </div>

        {/* Filter tabs + Add All */}
        <div className="px-6 py-3 border-b border-slate-100 flex items-center gap-2 flex-wrap">
          <div className="flex gap-1.5 flex-wrap flex-1">
            {FILTER_TABS.map(({ key, label }) => (
              <button key={key} onClick={() => setFilter(key)}
                className={`text-xs px-2.5 py-1.5 rounded-lg transition-colors ${
                  filter === key ? "bg-slate-900 text-white" : "border border-slate-200 text-slate-600 hover:bg-slate-50"
                }`}>
                {label}
                <span className="ml-1 opacity-60">{countFor(key)}</span>
              </button>
            ))}
          </div>

          {/* Add All button */}
          {!addingAll && notAddedCount > 0 && (
            <button onClick={handleAddAll}
              className="flex items-center gap-1.5 text-xs px-3 py-2 bg-slate-900 text-white rounded-lg hover:bg-slate-700 transition-colors shrink-0">
              <Plus size={12} /> Tout ajouter ({notAddedCount})
            </button>
          )}
          {addingAll && addAllProgress && (
            <div className="flex items-center gap-2 text-xs text-slate-600 bg-slate-50 px-3 py-2 rounded-lg border border-slate-200 shrink-0">
              <Spinner size={12} />
              {addAllProgress.done}/{addAllProgress.total} ajoutés…
            </div>
          )}
        </div>

        {/* Frontier warning */}
        {filter === "frontier" && (
          <div className="mx-6 mt-4 bg-amber-50 border border-amber-200 rounded-xl p-3 flex items-start gap-2.5">
            <AlertTriangle size={14} className="text-amber-600 shrink-0 mt-0.5" />
            <p className="text-xs text-amber-700">
              Benchmarks frontier — seuils de risque stricts. Certains datasets (CBRN-E complet) sont restreints.
            </p>
          </div>
        )}

        {/* List */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-2">
          {loading ? (
            <div className="flex justify-center py-16"><Spinner size={24} /></div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-16 text-slate-400 text-sm">Aucun benchmark dans cette catégorie.</div>
          ) : (
            filtered.map(b => {
              const isAdded = added.has(b.key);
              const isAdding = adding === b.key;
              const icon = DOMAIN_ICONS[b.domain] ?? "📊";
              return (
                <div key={b.key}
                  className={`p-4 border rounded-xl transition-colors ${
                    b.is_frontier ? "border-red-100 hover:border-red-200 bg-red-50/30"
                    : "border-slate-100 hover:border-slate-200 hover:bg-slate-50"}`}>
                  <div className="flex items-start gap-3">
                    <span className="text-xl shrink-0 mt-0.5">{icon}</span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap mb-1">
                        <span className="font-medium text-slate-900 text-sm">{b.name}</span>
                        <Badge className={benchmarkTypeColor(b.type as any)}>{b.type}</Badge>
                        {b.is_frontier && <Badge className="bg-red-100 text-red-600"><Shield size={10} className="inline mr-1" />Frontier</Badge>}
                        {b.risk_threshold && <Badge className="bg-orange-100 text-orange-600">seuil {(b.risk_threshold * 100).toFixed(0)}%</Badge>}
                        {b.year && <Badge className="bg-slate-100 text-slate-400">{b.year}</Badge>}
                      </div>
                      <p className="text-xs text-slate-500 mb-1">{b.description}</p>
                      {b.methodology_note && <p className="text-xs text-slate-400 italic">{b.methodology_note}</p>}
                      <div className="flex items-center gap-3 mt-1.5 text-xs text-slate-400">
                        <span>métrique : <span className="font-mono">{b.metric}</span></span>
                        <span>{b.num_samples} items</span>
                        <span>{b.domain}</span>
                        {b.paper_url && (
                          <a href={b.paper_url} target="_blank" rel="noopener noreferrer"
                            className="text-blue-400 hover:text-blue-600 hover:underline">paper →</a>
                        )}
                      </div>
                    </div>
                    <button onClick={() => !isAdded && !addingAll && handleAdd(b)}
                      disabled={isAdding || isAdded || addingAll}
                      className={`shrink-0 flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-colors ${
                        isAdded ? "bg-green-50 text-green-600 border border-green-200"
                        : "bg-slate-900 text-white hover:bg-slate-700 disabled:opacity-40"}`}>
                      {isAdding ? <Spinner size={12} /> : isAdded ? <CheckCircle size={12} /> : <Plus size={12} />}
                      {isAdded ? "Ajouté" : "Ajouter"}
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>

        <div className="px-6 py-3 border-t border-slate-100 text-xs text-slate-400 flex items-center justify-between">
          <span>{added.size} benchmark{added.size !== 1 ? "s" : ""} ajouté{added.size !== 1 ? "s" : ""} cette session</span>
          <span>INESIA — ANSSI · Inria · LNE · PEReN</span>
        </div>
      </div>
    </div>
  );
}
