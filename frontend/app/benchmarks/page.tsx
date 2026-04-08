"use client";
import { useEffect, useState, useCallback } from "react";
import { benchmarksApi } from "@/lib/api";
import type { Benchmark, BenchmarkType } from "@/lib/api";
import { useBenchmarks } from "@/lib/useApi";
import { useSync } from "@/lib/useSync";
import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/Badge";
import { EmptyState } from "@/components/EmptyState";
import { Spinner } from "@/components/Spinner";
import { BenchmarkCatalogModal } from "@/components/BenchmarkCatalogModal";
import { benchmarkTypeColor } from "@/lib/utils";
import { Upload, Lock, AlertTriangle, Plus, ChevronDown, ChevronUp, Sparkles,
         Search, ChevronLeft, ChevronRight, Eye } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "https://llm-eval-backend-kqlh.onrender.com/api";

const TYPE_LABELS: Record<string, string> = {
  academic: "Academic", safety: "Safety", coding: "Coding", custom: "Custom",
};
const TYPE_ICONS: Record<string, string> = {
  academic: "🎓", safety: "🛡️", coding: "💻", custom: "🧩",
};
const FILTER_TABS = [
  { key: "all",      label: "Tous" },
  { key: "inesia",   label: "☿ INESIA" },
  { key: "academic", label: "Academic" },
  { key: "safety",   label: "Safety" },
  { key: "coding",   label: "Code" },
  { key: "custom",   label: "Custom" },
] as const;
type FilterKey = typeof FILTER_TABS[number]["key"];

function matchFilter(b: Benchmark, f: FilterKey): boolean {
  if (f === "all") return true;
  if (f === "inesia") {
    const tags = b.tags ?? [];
    return tags.some(t => ["INESIA","frontier","cyber","disinformation","MITRE","DISARM","ATLAS"].includes(t))
      || b.type === "safety"
      || (b.name ?? "").toLowerCase().includes("inesia");
  }
  return b.type === f;
}

// ── Benchmark Item Explorer ────────────────────────────────────────────────────
function ItemExplorer({ benchmarkId, onClose }: { benchmarkId: number; onClose: () => void }) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");

  const load = useCallback(() => {
    setLoading(true);
    fetch(`${API_BASE}/benchmarks/${benchmarkId}/items?page=${page}&page_size=20&search=${encodeURIComponent(search)}`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [benchmarkId, page, search]);

  useEffect(() => { load(); }, [load]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    setSearch(searchInput);
  };

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl w-full max-w-4xl max-h-[85vh] flex flex-col shadow-2xl">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <div>
            <h2 className="font-semibold text-slate-900">Explorer le dataset</h2>
            {data && <p className="text-xs text-slate-400 mt-0.5">{data.total} items · {data.source === "lm_eval" ? "lm-evaluation-harness" : data.dataset_path}</p>}
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-lg text-slate-500">✕</button>
        </div>

        {/* Info banners per source type */}
        {data?.source?.startsWith("huggingface:") && (
          <div className="mx-6 mt-4 bg-blue-50 border border-blue-200 rounded-xl px-4 py-3 text-sm text-blue-700">
            📡 Items loaded from HuggingFace via lm-eval — task <span className="font-mono">{data.source.split(":")[1]}</span>
          </div>
        )}
        {data?.source === "hf_error" && (
          <div className="mx-6 mt-4 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 text-sm text-amber-700">
            ⚠ {data.message}
          </div>
        )}
        {data?.source === "no_dataset" && (
          <div className="mx-6 mt-4 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 text-sm text-amber-700">
            ⚠ {data.message}
          </div>
        )}

        {(data?.source === "local" || data?.source?.startsWith("huggingface:")) && (
          <>
            <div className="px-6 py-3 border-b border-slate-100">
              <form onSubmit={handleSearch} className="flex gap-2">
                <div className="relative flex-1">
                  <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                  <input value={searchInput} onChange={e => setSearchInput(e.target.value)}
                    placeholder="Search items…"
                    className="w-full pl-9 pr-4 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-900" />
                </div>
                <button type="submit" className="px-4 py-2 bg-slate-900 text-white text-sm rounded-lg hover:bg-slate-700">
                  Chercher
                </button>
                {search && <button type="button" onClick={() => { setSearch(""); setSearchInput(""); setPage(1); }}
                  className="px-3 py-2 text-sm text-slate-500 hover:bg-slate-100 rounded-lg">Effacer</button>}
              </form>
            </div>

            <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
              {loading ? (
                <div className="flex justify-center py-12"><Spinner size={24} /></div>
              ) : data?.items?.length === 0 ? (
                <div className="text-center py-12 text-slate-400">No items found.</div>
              ) : data?.items?.map((item: any, i: number) => (
                <div key={i} className="bg-slate-50 rounded-xl p-4 text-sm border border-slate-100">
                  {/* Try to render common fields nicely */}
                  {item.question && (
                    <div className="mb-2">
                      <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">Question</span>
                      <p className="mt-1 text-slate-800">{item.question}</p>
                    </div>
                  )}
                  {item.prompt && !item.question && (
                    <div className="mb-2">
                      <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">Prompt</span>
                      <p className="mt-1 text-slate-800 whitespace-pre-wrap">{item.prompt}</p>
                    </div>
                  )}
                  {item.choices && (
                    <div className="mb-2 flex gap-2 flex-wrap">
                      {item.choices.map((c: string, ci: number) => (
                        <span key={ci} className={`text-xs px-2 py-1 rounded ${
                          item.answer === String.fromCharCode(65 + ci) || item.answer === ci
                            ? "bg-green-100 text-green-700 font-medium"
                            : "bg-white border border-slate-200 text-slate-600"
                        }`}>
                          {String.fromCharCode(65 + ci)}. {c}
                        </span>
                      ))}
                    </div>
                  )}
                  {item.answer != null && (
                    <div className="flex items-center gap-1.5 text-xs">
                      <span className="text-slate-500">Correct answer:</span>
                      <span className="font-mono font-medium text-green-700 bg-green-50 px-2 py-0.5 rounded">{String(item.answer)}</span>
                    </div>
                  )}
                  {item.expected_keywords && (
                    <div className="flex items-center gap-1.5 text-xs mt-1">
                      <span className="text-slate-500">Expected keywords:</span>
                      {item.expected_keywords.map((k: string) => (
                        <span key={k} className="font-mono text-blue-700 bg-blue-50 px-2 py-0.5 rounded">{k}</span>
                      ))}
                    </div>
                  )}
                  {item.category && (
                    <div className="mt-2">
                      <Badge className="bg-slate-100 text-slate-500 text-xs">{item.category}</Badge>
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* Pagination */}
            {data && data.total_pages > 1 && (
              <div className="px-6 py-3 border-t border-slate-100 flex items-center justify-between text-sm">
                <span className="text-slate-400 text-xs">Page {page} / {data.total_pages} · {data.total} items</span>
                <div className="flex gap-2">
                  <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
                    className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-40">
                    <ChevronLeft size={14} />
                  </button>
                  <button onClick={() => setPage(p => Math.min(data.total_pages, p + 1))} disabled={page === data.total_pages}
                    className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-40">
                    <ChevronRight size={14} />
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────
export default function BenchmarksPage() {
  const [benches, setBenches] = useState<Benchmark[]>([]);
  const [filter, setFilter] = useState<FilterKey>("all");
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [exploringId, setExploringId] = useState<number | null>(null);
  const [showCustomForm, setShowCustomForm] = useState(false);
  const [showCatalog, setShowCatalog] = useState(false);
  const [uploadId, setUploadId] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const [customForm, setCustomForm] = useState({
    name: "", description: "", type: "custom" as BenchmarkType, metric: "accuracy"
  });
  const { benchmarksAdded: newBenchmarks } = useSync();
  const [importing, setImporting] = useState(false);
  const [importMsg, setImportMsg] = useState<string | null>(null);

  const { benchmarks: swrBenches, isLoading: swrBenchLoading, refresh: refreshBenches } = useBenchmarks();
  useEffect(() => { setBenches(swrBenches); if (!swrBenchLoading) setLoading(false); }, [swrBenches, swrBenchLoading]);
  const load = useCallback(() => { refreshBenches(); }, [refreshBenches]);

  const filtered = benches.filter(b => matchFilter(b, filter));
  const countFor = (f: FilterKey) => benches.filter(b => matchFilter(b, f)).length;

  const handleCreateCustom = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);
    try {
      const b = await benchmarksApi.create({ ...customForm, tags: [customForm.type] });
      setUploadId(b.id);
      setShowCustomForm(false);
      load();
    } catch (err) { alert(String(err)); } finally { setCreating(false); }
  };

  const handleUpload = async (benchId: number, file: File) => {
    try {
      await benchmarksApi.uploadDataset(benchId, file);
      setUploadId(null);
      load();
    } catch (err) { alert(String(err)); }
  };

  const handleImportNew = async () => {
    setImporting(true);
    setImportMsg(null);
    try {
      const res = await fetch(`${API_BASE}/sync/benchmarks/import-all`, { method: "POST" });
      const data = await res.json();
      const n = data.added ?? 0;
      setImportMsg(`${n} new benchmark${n > 1 ? "s" : ""} imported!`);
      load();
      setTimeout(() => setImportMsg(null), 4000);
    } finally { setImporting(false); }
  };

  // HuggingFace import
  const [showHfImport, setShowHfImport] = useState(false);
  const [hfForm, setHfForm] = useState({ repo_id: "", split: "test", subset: "", max_items: 500 });
  const [hfLoading, setHfLoading] = useState(false);

  const handleHfImport = async () => {
    if (!hfForm.repo_id.trim()) return;
    setHfLoading(true);
    try {
      const res = await fetch(`${API_BASE}/benchmarks/import-huggingface`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...hfForm, subset: hfForm.subset || undefined }),
      });
      if (!res.ok) { const e = await res.json(); throw new Error(e.detail); }
      const data = await res.json();
      alert(`✅ ${data.items_imported} items imported from ${data.source}\nBenchmark: ${data.benchmark_name}`);
      setShowHfImport(false);
      setHfForm({ repo_id: "", split: "test", subset: "", max_items: 500 });
      load();
    } catch (e: any) { alert(`Error: ${e.message}`); }
    finally { setHfLoading(false); }
  };

  return (
    <div>
      <PageHeader
        title="Benchmark Library"
        description="Built-in benchmarks, INESIA catalog, and custom imports."
        action={
          <div className="flex gap-2">
            {newBenchmarks > 0 && (
              <button onClick={handleImportNew} disabled={importing}
                className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-blue-700 transition-colors disabled:opacity-50">
                {importing ? <Spinner size={14} /> : <Sparkles size={14} />}
                {importing ? "Import…" : `${newBenchmarks} nouveau${newBenchmarks > 1 ? "x" : ""}`}
              </button>
            )}
            <button onClick={() => setShowCatalog(true)}
              className="flex items-center gap-2 border border-slate-200 px-4 py-2 rounded-lg text-sm hover:bg-slate-50 text-slate-700 transition-colors">
              🔍 Catalogue
            </button>
            <button onClick={() => setShowHfImport(!showHfImport)}
              className="flex items-center gap-2 border border-yellow-300 px-4 py-2 rounded-lg text-sm hover:bg-yellow-50 text-yellow-700 transition-colors">
              🤗 HuggingFace
            </button>
            <button onClick={() => setShowCustomForm(!showCustomForm)}
              className="flex items-center gap-2 bg-slate-900 text-white px-4 py-2 rounded-lg text-sm hover:bg-slate-700 transition-colors">
              <Plus size={14} /> Import Custom
            </button>
          </div>
        }
      />

      {importMsg && (
        <div className="mx-8 mt-4 bg-green-50 border border-green-200 rounded-xl px-4 py-3 text-sm text-green-700">
          ✅ {importMsg}
        </div>
      )}

      {/* HuggingFace import form */}
      {showHfImport && (
        <div className="mx-8 mt-6 bg-white border border-yellow-200 rounded-xl p-6">
          <h3 className="font-medium text-slate-900 mb-4 flex items-center gap-2">🤗 Import depuis HuggingFace</h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-medium text-slate-600 mb-1 block">Repository ID *</label>
              <input value={hfForm.repo_id} onChange={e => setHfForm(f => ({ ...f, repo_id: e.target.value }))}
                placeholder="ex. cais/mmlu, tatsu-lab/alpaca_eval, Anthropic/hh-rlhf"
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-yellow-400" />
            </div>
            <div>
              <label className="text-xs font-medium text-slate-600 mb-1 block">Split</label>
              <select value={hfForm.split} onChange={e => setHfForm(f => ({ ...f, split: e.target.value }))}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm">
                <option value="test">test</option>
                <option value="train">train</option>
                <option value="validation">validation</option>
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-slate-600 mb-1 block">Subset (optionnel)</label>
              <input value={hfForm.subset} onChange={e => setHfForm(f => ({ ...f, subset: e.target.value }))}
                placeholder="ex. abstract_algebra, anatomy"
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="text-xs font-medium text-slate-600 mb-1 block">Max items</label>
              <input type="number" value={hfForm.max_items} onChange={e => setHfForm(f => ({ ...f, max_items: +e.target.value }))}
                min={10} max={5000}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" />
            </div>
          </div>
          <div className="flex items-center gap-3 mt-4">
            <button onClick={handleHfImport} disabled={hfLoading || !hfForm.repo_id.trim()}
              className="flex items-center gap-2 bg-yellow-500 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-yellow-600 disabled:opacity-40">
              {hfLoading ? <Spinner size={13} /> : null}
              {hfLoading ? "Importing…" : "Import"}
            </button>
            <button onClick={() => setShowHfImport(false)} className="text-sm text-slate-500 hover:text-slate-700">Cancel</button>
          </div>
        </div>
      )}

      {showCustomForm && (
        <div className="mx-8 mt-6 bg-white border border-slate-200 rounded-xl p-6">
          <h3 className="font-medium text-slate-900 mb-4">New custom benchmark</h3>
          <form onSubmit={handleCreateCustom} className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-medium text-slate-600 mb-1 block">Nom</label>
              <input required value={customForm.name}
                onChange={e => setCustomForm(f => ({ ...f, name: e.target.value }))}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900" />
            </div>
            <div>
              <label className="text-xs font-medium text-slate-600 mb-1 block">Type</label>
              <select value={customForm.type}
                onChange={e => setCustomForm(f => ({ ...f, type: e.target.value as BenchmarkType }))}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900">
                <option value="custom">Custom</option>
                <option value="academic">Academic</option>
                <option value="safety">Safety</option>
                <option value="coding">Coding</option>
              </select>
            </div>
            <div className="col-span-2">
              <label className="text-xs font-medium text-slate-600 mb-1 block">Description</label>
              <textarea value={customForm.description}
                onChange={e => setCustomForm(f => ({ ...f, description: e.target.value }))}
                rows={2}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900" />
            </div>
            <div>
              <label className="text-xs font-medium text-slate-600 mb-1 block">Metric</label>
              <input value={customForm.metric}
                onChange={e => setCustomForm(f => ({ ...f, metric: e.target.value }))}
                placeholder="accuracy"
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900" />
            </div>
            <div className="col-span-2 flex gap-3 pt-1">
              <button type="submit" disabled={creating}
                className="bg-slate-900 text-white px-4 py-2 rounded-lg text-sm hover:bg-slate-700 transition-colors disabled:opacity-50">
                {creating ? "Creating…" : "Create"}
              </button>
              <button type="button" onClick={() => setShowCustomForm(false)} className="px-4 py-2 text-sm text-slate-600">Cancel</button>
            </div>
          </form>
        </div>
      )}

      {uploadId && (
        <div className="mx-8 mt-4 bg-blue-50 border border-blue-200 rounded-xl p-4 flex items-center gap-4">
          <Upload size={16} className="text-blue-600 shrink-0" />
          <p className="text-sm text-blue-700">Benchmark created! Upload your JSON dataset:</p>
          <input type="file" accept=".json"
            onChange={e => e.target.files?.[0] && handleUpload(uploadId, e.target.files[0])}
            className="text-sm" />
          <button onClick={() => setUploadId(null)} className="ml-auto text-xs text-blue-500">fermer</button>
        </div>
      )}

      {/* Filter tabs */}
      <div className="px-8 pt-6 pb-2 flex gap-2 flex-wrap">
        {FILTER_TABS.map(({ key, label }) => (
          <button key={key} onClick={() => setFilter(key)}
            className={`text-sm px-3 py-1.5 rounded-lg transition-colors ${
              filter === key
                ? key === "inesia" ? "bg-purple-900 text-white" : "bg-slate-900 text-white"
                : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50"
            }`}>
            {label}
            <span className="ml-1.5 text-xs opacity-60">{countFor(key)}</span>
          </button>
        ))}
      </div>

      {/* List */}
      <div className="p-8 pt-4">
        {loading ? (
          <div className="flex justify-center py-20"><Spinner size={24} /></div>
        ) : filtered.length === 0 ? (
          <EmptyState icon="📚" title="No benchmarks" description="Import from the catalog or add a custom benchmark." />
        ) : (
          <div className="grid grid-cols-1 gap-3">
            {filtered.map(b => (
              <div key={b.id} className="bg-white border border-slate-200 rounded-xl overflow-hidden">
                <div className="flex items-center gap-4 p-5 cursor-pointer hover:bg-slate-50 transition-colors"
                  onClick={() => setExpanded(expanded === b.id ? null : b.id)}>
                  <span className="text-2xl">{TYPE_ICONS[b.type] ?? "📊"}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <span className="font-medium text-slate-900">{b.name}</span>
                      <Badge className={benchmarkTypeColor(b.type as any)}>{TYPE_LABELS[b.type] ?? b.type}</Badge>
                      {b.is_builtin && <Badge className="bg-slate-100 text-slate-500"><Lock size={10} className="inline mr-1" />Built-in</Badge>}
                      {b.risk_threshold && <Badge className="bg-red-100 text-red-600"><AlertTriangle size={10} className="inline mr-1" />Frontier</Badge>}
                      {b.has_dataset && <Badge className="bg-green-100 text-green-600">Dataset ✓</Badge>}
                    </div>
                    <p className="text-xs text-slate-500 truncate">{b.description}</p>
                  </div>
                  <div className="text-xs text-slate-400 text-right shrink-0 hidden sm:block">
                    <div>{b.num_samples ?? "all"} samples</div>
                    <div className="mt-0.5 font-mono">{b.metric}</div>
                  </div>
                  {expanded === b.id ? <ChevronUp size={14} className="text-slate-400 shrink-0" /> : <ChevronDown size={14} className="text-slate-400 shrink-0" />}
                </div>

                {expanded === b.id && (
                  <div className="border-t border-slate-100 px-5 py-4 bg-slate-50">
                    <div className="grid grid-cols-2 gap-4 mb-3 text-xs text-slate-600">
                      <div><span className="font-medium">Metric:</span> {b.metric}</div>
                      <div><span className="font-medium">Samples :</span> {b.num_samples ?? "no limit"}</div>
                      {b.risk_threshold && <div><span className="font-medium">Seuil risque :</span> {(b.risk_threshold * 100).toFixed(0)}%</div>}
                    </div>
                    <p className="text-slate-600 text-xs mb-3">{b.description}</p>
                    <div className="flex flex-wrap gap-1.5 mb-3">
                      {b.tags?.map((t: string) => <Badge key={t} className="bg-white border border-slate-200 text-slate-600">{t}</Badge>)}
                    </div>
                    <div className="flex gap-2 flex-wrap">
                      {/* Explorer button — always shown */}
                      <button onClick={e => { e.stopPropagation(); setExploringId(b.id); }}
                        className="flex items-center gap-1.5 text-xs px-3 py-1.5 bg-blue-50 text-blue-600 border border-blue-200 rounded-lg hover:bg-blue-100 transition-colors">
                        <Eye size={12} /> Explorer le dataset
                      </button>
                      {!b.is_builtin && (
                        <>
                          <label className="cursor-pointer flex items-center gap-1.5 text-xs px-3 py-1.5 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600">
                            <Upload size={12} /> Upload JSON
                            <input type="file" accept=".json" className="hidden"
                              onChange={e => e.target.files?.[0] && handleUpload(b.id, e.target.files[0])} />
                          </label>
                          <button onClick={() => benchmarksApi.delete(b.id).then(load)}
                            className="text-xs px-3 py-1.5 text-red-500 hover:bg-red-50 border border-red-100 rounded-lg">
                            Delete
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {showCatalog && <BenchmarkCatalogModal onClose={() => { setShowCatalog(false); load(); }} />}
      {exploringId !== null && <ItemExplorer benchmarkId={exploringId} onClose={() => setExploringId(null)} />}
    </div>
  );
}
