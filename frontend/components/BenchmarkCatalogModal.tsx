"use client";
import { useState, useEffect } from "react";
import { benchmarksApi } from "@/lib/api";
import { Badge } from "./Badge";
import { Spinner } from "./Spinner";
import { benchmarkTypeColor } from "@/lib/utils";
import { X, Plus, CheckCircle, AlertTriangle, Shield, ExternalLink } from "lucide-react";

import { API_BASE } from "@/lib/config";

interface CatalogBenchmark {
  key: string; name: string; type: string; domain: string;
  description: string; metric: string; num_samples: number;
  dataset_path: string; tags: string[];
  risk_threshold: number | null; is_frontier: boolean;
  methodology_note: string | null; paper_url?: string | null; year?: number | null;
}

interface HFDiscoveredBenchmark {
  id: string; name: string; downloads: number; likes: number;
  description: string; tags: string[]; gated: boolean; card_data: Record<string, unknown>;
}

const DOMAIN_ICONS: Record<string, string> = {
  "reasoning": "🧠", "raisonnement": "🧠", "maths": "🔢", "math": "🔢",
  "factuality": "📚", "factualité": "📚", "knowledge": "🎓", "connaissances": "🎓",
  "code": "💻", "french": "🇫🇷", "français": "🇫🇷", "multilingual": "🌍",
  "cyber": "🔒", "disinformation": "📡", "alignment": "⚖️",
  "NLI": "🔗", "medicine": "🏥", "law": "⚖️",
  "finance": "💹", "science": "🔭", "instruction following": "📋",
};

const FILTER_TABS = [
  { key: "all", label: "All" },
  { key: "inesia", label: "☿ INESIA" },
  { key: "raisonnement", label: "Reasoning" },
  { key: "connaissances", label: "Knowledge" },
  { key: "maths", label: "Maths" },
  { key: "code", label: "Code" },
  { key: "french", label: "French" },
  { key: "safety", label: "Safety" },
  { key: "frontier", label: "🛡️ Frontier" },
] as const;

type FilterKey = typeof FILTER_TABS[number]["key"];
type TabMode = "catalog" | "discovered";

export function BenchmarkCatalogModal({ onClose }: { onClose: () => void }) {
  const [tabMode, setTabMode] = useState<TabMode>("catalog");

  // ── Catalog tab state ─────────────────────────────────────────────────────
  const [catalog, setCatalog] = useState<CatalogBenchmark[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterKey>("all");
  const [added, setAdded] = useState<Set<string>>(new Set());
  const [adding, setAdding] = useState<string | null>(null);
  const [addingAll, setAddingAll] = useState(false);
  const [addAllProgress, setAddAllProgress] = useState<{ done: number; total: number } | null>(null);

  // ── Discovered tab state ──────────────────────────────────────────────────
  const [hfBenches, setHfBenches] = useState<HFDiscoveredBenchmark[]>([]);
  const [hfLoading, setHfLoading] = useState(false);
  const [hfError, setHfError] = useState<string | null>(null);
  const [hfSearch, setHfSearch] = useState("");
  const [hfImporting, setHfImporting] = useState<string | null>(null);
  const [hfImported, setHfImported] = useState<Set<string>>(new Set());

  useEffect(() => {
    setError(null);
    fetch(`${API_BASE}/catalog/benchmarks`)
      .then(async (r) => {
        const data = await r.json().catch(() => null);
        if (!r.ok) throw new Error(data?.detail ?? `HTTP ${r.status} ${r.statusText}`);
        if (!Array.isArray(data)) throw new Error("Invalid catalog response");
        setCatalog(data);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  const loadHfBenches = () => {
    if (hfBenches.length > 0) return; // already loaded
    setHfLoading(true);
    setHfError(null);
    fetch(`${API_BASE}/catalog/benchmarks/online`)
      .then(async (r) => {
        const data = await r.json().catch(() => null);
        if (!r.ok) throw new Error(data?.detail ?? `HTTP ${r.status} ${r.statusText}`);
        if (!Array.isArray(data)) throw new Error("Invalid response");
        setHfBenches(data);
      })
      .catch((e) => setHfError(String(e)))
      .finally(() => setHfLoading(false));
  };

  const handleTabChange = (mode: TabMode) => {
    setTabMode(mode);
    if (mode === "discovered") loadHfBenches();
  };

  const filtered = catalog.filter(b => {
    if (filter === "all") return true;
    if (filter === "frontier") return b.is_frontier;
    if (filter === "inesia") return b.tags?.includes("INESIA") || b.is_frontier || b.domain?.includes("CBRN") || b.domain?.includes("cyber") || b.domain?.includes("disinformation") || b.domain === "french";
    if (filter === "safety") return b.type === "safety";
    if (filter === "french") return b.domain === "french" || b.domain === "multilingual";
    return b.domain === filter || b.type === filter;
  });

  const filteredHf = hfBenches.filter(b =>
    !hfSearch || b.id.toLowerCase().includes(hfSearch.toLowerCase())
  );

  const addOne = async (b: CatalogBenchmark): Promise<boolean> => {
    try {
      await benchmarksApi.create({
        name: b.name, type: b.type as any, description: b.description,
        tags: b.tags, metric: b.metric, num_samples: b.num_samples,
        config: {}, risk_threshold: b.risk_threshold ?? undefined,
      });
      return true;
    } catch (e: any) {
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
    if (filter !== "frontier" && toAdd.some(b => b.is_frontier)) {
      const confirmed = window.confirm(
        `${toAdd.filter(b => b.is_frontier).length} frontier benchmark(s) are included. Confirm?`
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

  const handleHfImport = async (b: HFDiscoveredBenchmark) => {
    setHfImporting(b.id);
    try {
      const res = await fetch(`${API_BASE}/benchmarks/import-huggingface`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo_id: b.id, split: "test", max_items: 200 }),
      });
      if (res.ok) {
        setHfImported(prev => new Set([...prev, b.id]));
      }
    } catch {}
    setHfImporting(null);
  };

  const notAddedCount = filtered.filter(b => !added.has(b.key)).length;

  const countFor = (f: FilterKey) => {
    if (f === "all") return catalog.length;
    if (f === "frontier") return catalog.filter(b => b.is_frontier).length;
    if (f === "inesia") return catalog.filter(b => b.tags?.includes("INESIA") || b.is_frontier || b.domain?.includes("CBRN") || b.domain?.includes("cyber") || b.domain?.includes("disinformation") || b.domain === "french").length;
    if (f === "safety") return catalog.filter(b => b.type === "safety").length;
    if (f === "french") return catalog.filter(b => b.domain === "french" || b.domain === "multilingual").length;
    return catalog.filter(b => b.domain === f || b.type === f).length;
  };

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl w-full max-w-4xl max-h-[85vh] flex flex-col shadow-2xl">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <div>
            <h2 className="font-semibold text-slate-900">Benchmark catalog</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              {tabMode === "catalog"
                ? `INESIA · ${catalog.length} worldwide benchmarks`
                : `HuggingFace · ${hfBenches.length} datasets discovered`}
            </p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-lg"><X size={16} /></button>
        </div>

        {/* Tab switcher */}
        <div className="px-6 pt-3 border-b border-slate-100 flex gap-2">
          <button
            onClick={() => handleTabChange("catalog")}
            className={`pb-2.5 text-xs font-medium border-b-2 transition-colors px-1 ${
              tabMode === "catalog" ? "border-slate-900 text-slate-900" : "border-transparent text-slate-400 hover:text-slate-600"
            }`}
          >
            📋 INESIA Catalog
          </button>
          <button
            onClick={() => handleTabChange("discovered")}
            className={`pb-2.5 text-xs font-medium border-b-2 transition-colors px-1 flex items-center gap-1.5 ${
              tabMode === "discovered" ? "border-yellow-500 text-yellow-700" : "border-transparent text-slate-400 hover:text-slate-600"
            }`}
          >
            🤗 Découverts
            {hfBenches.length > 0 && (
              <span className="bg-yellow-100 text-yellow-700 text-[10px] px-1.5 py-0.5 rounded-full font-bold">{hfBenches.length}</span>
            )}
          </button>
        </div>

        {/* ── CATALOG TAB ── */}
        {tabMode === "catalog" && (
          <>
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
              {!addingAll && notAddedCount > 0 && (
                <button onClick={handleAddAll}
                  className="flex items-center gap-1.5 text-xs px-3 py-2 bg-slate-900 text-white rounded-lg hover:bg-slate-700 transition-colors shrink-0">
                  <Plus size={12} /> Add all ({notAddedCount})
                </button>
              )}
              {addingAll && addAllProgress && (
                <div className="flex items-center gap-2 text-xs text-slate-600 bg-slate-50 px-3 py-2 rounded-lg border border-slate-200 shrink-0">
                  <Spinner size={12} />
                  {addAllProgress.done}/{addAllProgress.total} added…
                </div>
              )}
            </div>

            {filter === "frontier" && (
              <div className="mx-6 mt-4 bg-amber-50 border border-amber-200 rounded-xl p-3 flex items-start gap-2.5">
                <AlertTriangle size={14} className="text-amber-600 shrink-0 mt-0.5" />
                <p className="text-xs text-amber-700">
                  Frontier benchmarks — strict risk thresholds. Some datasets may be restricted.
                </p>
              </div>
            )}

            <div className="flex-1 overflow-y-auto px-6 py-4 space-y-2">
              {loading ? (
                <div className="flex justify-center py-16"><Spinner size={24} /></div>
              ) : error ? (
                <div className="text-center py-16 text-red-500 text-sm">
                  Unable to load benchmark catalog.
                  <br /><span className="text-xs text-slate-400">{error}</span>
                </div>
              ) : filtered.length === 0 ? (
                <div className="text-center py-16 text-slate-400 text-sm">No benchmarks in this category.</div>
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
                            {b.risk_threshold && <Badge className="bg-orange-100 text-orange-600">threshold {(b.risk_threshold * 100).toFixed(0)}%</Badge>}
                            {b.year && <Badge className="bg-slate-100 text-slate-400">{b.year}</Badge>}
                          </div>
                          <p className="text-xs text-slate-500 mb-1">{b.description}</p>
                          {b.methodology_note && <p className="text-xs text-slate-400 italic">{b.methodology_note}</p>}
                          <div className="flex items-center gap-3 mt-1.5 text-xs text-slate-400">
                            <span>metric: <span className="font-mono">{b.metric}</span></span>
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
                          {isAdded ? "Added" : "Add"}
                        </button>
                      </div>
                    </div>
                  );
                })
              )}
            </div>

            <div className="px-6 py-3 border-t border-slate-100 text-xs text-slate-400 flex items-center justify-between">
              <span>{added.size} benchmark{added.size !== 1 ? "s" : ""} added this session</span>
              <span>INESIA — ANSSI · Inria · LNE · PEReN</span>
            </div>
          </>
        )}

        {/* ── DISCOVERED TAB ── */}
        {tabMode === "discovered" && (
          <>
            <div className="px-6 py-3 border-b border-slate-100 flex items-center gap-3">
              <input
                value={hfSearch}
                onChange={e => setHfSearch(e.target.value)}
                placeholder="Filter by dataset name…"
                className="flex-1 text-sm border border-slate-200 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-yellow-400"
              />
              <span className="text-xs text-slate-400 shrink-0">{filteredHf.length} datasets</span>
            </div>

            <div className="flex-1 overflow-y-auto px-6 py-4 space-y-2">
              {hfLoading ? (
                <div className="flex justify-center py-16"><Spinner size={24} /></div>
              ) : hfError ? (
                <div className="text-center py-16 text-red-500 text-sm">
                  Unable to load HuggingFace benchmarks.
                  <br /><span className="text-xs text-slate-400">{hfError}</span>
                </div>
              ) : filteredHf.length === 0 ? (
                <div className="text-center py-16 text-slate-400 text-sm">No datasets found.</div>
              ) : (
                filteredHf.map(b => {
                  const isImported = hfImported.has(b.id);
                  const isImporting = hfImporting === b.id;
                  return (
                    <div key={b.id} className="p-4 border border-slate-100 hover:border-yellow-200 hover:bg-yellow-50/30 rounded-xl transition-colors">
                      <div className="flex items-start gap-3">
                        <span className="text-xl shrink-0 mt-0.5">🤗</span>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap mb-1">
                            <span className="font-medium text-slate-900 text-sm font-mono">{b.id}</span>
                            {b.gated && <Badge className="bg-amber-100 text-amber-700">Gated</Badge>}
                          </div>
                          {b.description && <p className="text-xs text-slate-500 mb-1 truncate">{b.description}</p>}
                          <div className="flex items-center gap-3 mt-1 text-xs text-slate-400">
                            {b.downloads > 0 && <span>⬇ {(b.downloads / 1000).toFixed(0)}k</span>}
                            {b.likes > 0 && <span>♥ {b.likes}</span>}
                            <a href={`https://huggingface.co/datasets/${b.id}`} target="_blank" rel="noopener noreferrer"
                              className="flex items-center gap-0.5 text-blue-400 hover:text-blue-600 hover:underline">
                              HF <ExternalLink size={10} />
                            </a>
                          </div>
                          {b.tags.length > 0 && (
                            <div className="flex flex-wrap gap-1 mt-1.5">
                              {b.tags.filter(t => !["benchmark", "datasets"].includes(t)).slice(0, 5).map(t => (
                                <span key={t} className="text-[10px] bg-slate-100 text-slate-500 px-1.5 py-0.5 rounded">{t}</span>
                              ))}
                            </div>
                          )}
                        </div>
                        <button
                          onClick={() => !isImported && !isImporting && handleHfImport(b)}
                          disabled={isImporting || isImported}
                          className={`shrink-0 flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-colors ${
                            isImported ? "bg-green-50 text-green-600 border border-green-200"
                            : "bg-yellow-500 text-white hover:bg-yellow-600 disabled:opacity-40"}`}
                        >
                          {isImporting ? <Spinner size={12} /> : isImported ? <CheckCircle size={12} /> : <Plus size={12} />}
                          {isImported ? "Imported" : "Import"}
                        </button>
                      </div>
                    </div>
                  );
                })
              )}
            </div>

            <div className="px-6 py-3 border-t border-slate-100 text-xs text-slate-400 flex items-center justify-between">
              <span>{hfImported.size} dataset{hfImported.size !== 1 ? "s" : ""} imported this session</span>
              <span>Source: <a href="https://huggingface.co/datasets" target="_blank" className="text-blue-400 hover:underline">HuggingFace Hub</a></span>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

