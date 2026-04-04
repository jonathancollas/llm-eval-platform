"use client";
import { useState, useEffect } from "react";
import { benchmarksApi } from "@/lib/api";
import { Badge } from "./Badge";
import { Spinner } from "./Spinner";
import { benchmarkTypeColor } from "@/lib/utils";
import { X, Plus, CheckCircle, AlertTriangle, Shield } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";

interface CatalogBenchmark {
  key: string; name: string; type: string; domain: string;
  description: string; metric: string; num_samples: number;
  dataset_path: string; tags: string[];
  risk_threshold: number | null; is_frontier: boolean;
  methodology_note: string | null;
}

const DOMAIN_ICONS: Record<string, string> = {
  "raisonnement": "🧠", "maths": "🔢", "factualité": "📚",
  "code": "💻", "français": "🇫🇷", "cybersécurité offensive": "🛡️",
  "CBRN-E": "☢️", "risques agentiques": "🤖", "méta-évaluation": "🔬",
};

export function BenchmarkCatalogModal({ onClose }: { onClose: () => void }) {
  const [catalog, setCatalog] = useState<CatalogBenchmark[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"all" | "academic" | "frontier">("all");
  const [added, setAdded] = useState<Set<string>>(new Set());
  const [adding, setAdding] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/catalog/benchmarks`)
      .then(r => r.json())
      .then(setCatalog)
      .finally(() => setLoading(false));
  }, []);

  const filtered = catalog.filter(b => {
    if (filter === "frontier") return b.is_frontier;
    if (filter === "academic") return !b.is_frontier;
    return true;
  });

  const handleAdd = async (b: CatalogBenchmark) => {
    setAdding(b.key);
    try {
      await benchmarksApi.create({
        name: b.name,
        type: b.type as any,
        description: b.description,
        tags: b.tags,
        metric: b.metric,
        num_samples: b.num_samples,
        config: {},
        risk_threshold: b.risk_threshold ?? undefined,
      });
      setAdded(prev => new Set([...prev, b.key]));
    } catch (e: any) {
      // Already exists is fine
      if (String(e).includes("already exists") || String(e).includes("409")) {
        setAdded(prev => new Set([...prev, b.key]));
      } else {
        alert(String(e));
      }
    } finally { setAdding(null); }
  };

  const frontierCount = catalog.filter(b => b.is_frontier).length;
  const academicCount = catalog.filter(b => !b.is_frontier).length;

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl w-full max-w-4xl max-h-[85vh] flex flex-col shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <div>
            <h2 className="font-semibold text-slate-900">Catalogue de benchmarks</h2>
            <p className="text-xs text-slate-400 mt-0.5">INESIA · {catalog.length} benchmarks disponibles</p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-lg"><X size={16} /></button>
        </div>

        {/* Filter tabs */}
        <div className="px-6 py-3 border-b border-slate-100 flex gap-2">
          {([
            { key: "all", label: `Tous (${catalog.length})` },
            { key: "academic", label: `Académiques (${academicCount})` },
            { key: "frontier", label: `Frontier (${frontierCount})`, icon: "🛡️" },
          ] as const).map(({ key, label, icon }) => (
            <button key={key} onClick={() => setFilter(key)}
              className={`text-sm px-3 py-1.5 rounded-lg transition-colors ${filter === key ? "bg-slate-900 text-white" : "border border-slate-200 text-slate-600 hover:bg-slate-50"}`}>
              {icon && <span className="mr-1">{icon}</span>}{label}
            </button>
          ))}
        </div>

        {/* Frontier warning */}
        {filter === "frontier" && (
          <div className="mx-6 mt-4 bg-amber-50 border border-amber-200 rounded-xl p-3 flex items-start gap-2.5">
            <AlertTriangle size={14} className="text-amber-600 shrink-0 mt-0.5" />
            <p className="text-xs text-amber-700">
              Les benchmarks frontier évaluent des comportements à risque élevé. Certains datasets (CBRN-E complet) sont restreints. Les scores déclenchent des alertes de sécurité automatiques.
            </p>
          </div>
        )}

        {/* List */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-2">
          {loading ? (
            <div className="flex justify-center py-16"><Spinner size={24} /></div>
          ) : (
            filtered.map(b => {
              const isAdded = added.has(b.key);
              const isAdding = adding === b.key;
              const icon = DOMAIN_ICONS[b.domain] ?? "📊";
              return (
                <div key={b.key}
                  className={`p-4 border rounded-xl transition-colors ${b.is_frontier ? "border-red-100 hover:border-red-200 bg-red-50/30" : "border-slate-100 hover:border-slate-200 hover:bg-slate-50"}`}>
                  <div className="flex items-start gap-3">
                    <span className="text-xl shrink-0 mt-0.5">{icon}</span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap mb-1">
                        <span className="font-medium text-slate-900 text-sm">{b.name}</span>
                        <Badge className={benchmarkTypeColor(b.type as any)}>{b.type}</Badge>
                        {b.is_frontier && (
                          <Badge className="bg-red-100 text-red-600">
                            <Shield size={10} className="inline mr-1" />Frontier
                          </Badge>
                        )}
                        {b.risk_threshold && (
                          <Badge className="bg-orange-100 text-orange-600">
                            seuil {(b.risk_threshold * 100).toFixed(0)}%
                          </Badge>
                        )}
                      </div>
                      <p className="text-xs text-slate-500 mb-2">{b.description}</p>
                      {b.methodology_note && (
                        <p className="text-xs text-slate-400 italic">{b.methodology_note}</p>
                      )}
                      <div className="flex items-center gap-3 mt-2 text-xs text-slate-400">
                        <span>métrique : <span className="font-mono">{b.metric}</span></span>
                        <span>{b.num_samples} items</span>
                        <span>{b.domain}</span>
                      </div>
                    </div>
                    <button
                      onClick={() => !isAdded && handleAdd(b)}
                      disabled={isAdding || isAdded}
                      className={`shrink-0 flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-colors ${
                        isAdded ? "bg-green-50 text-green-600 border border-green-200" :
                        "bg-slate-900 text-white hover:bg-slate-700 disabled:opacity-50"
                      }`}>
                      {isAdding ? <Spinner size={12} /> : isAdded ? <CheckCircle size={12} /> : <Plus size={12} />}
                      {isAdded ? "Ajouté" : "Ajouter"}
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>

        <div className="px-6 py-3 border-t border-slate-100 text-xs text-slate-400">
          Benchmarks développés et maintenus par l'INESIA — ANSSI · Inria · LNE · PEReN
        </div>
      </div>
    </div>
  );
}
