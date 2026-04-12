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
import { SecurityBenchmarkWizard } from "@/components/SecurityBenchmarkWizard";
import { benchmarkTypeColor } from "@/lib/utils";
import { Upload, Lock, AlertTriangle, Plus, ChevronDown, ChevronUp, Sparkles,
         Search, ChevronLeft, ChevronRight, Eye, Shield } from "lucide-react";

import { API_BASE } from "@/lib/config";

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
  if (f === "inesia") return b.source === "inesia";
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
// ── Benchmark Card — scientific provenance ────────────────────────────────────
function BenchmarkCard({ benchmarkId, benchmarkName }: { benchmarkId: number; benchmarkName: string }) {
  const [card, setCard] = useState<any | null>(null);
  const [open, setOpen] = useState(false);

  const load = () => {
    if (card) { setOpen(o => !o); return; }
    fetch(`${API_BASE}/benchmarks/${benchmarkId}/card`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { setCard(d); setOpen(true); })
      .catch(() => {});
  };

  if (!card && !open) {
    return (
      <button onClick={e => { e.stopPropagation(); load(); }}
        className="mb-3 text-[10px] text-blue-500 hover:underline flex items-center gap-1">
        📄 View benchmark card
      </button>
    );
  }

  return (
    <div className="mb-4 bg-white border border-blue-100 rounded-xl overflow-hidden">
      <button onClick={e => { e.stopPropagation(); setOpen(o => !o); }}
        className="w-full flex items-center justify-between px-4 py-2.5 text-xs hover:bg-blue-50 transition-colors">
        <span className="font-semibold text-blue-800">📄 Benchmark Card</span>
        {card && (
          <span className="text-[10px] text-slate-400">
            {card.completeness_score}% complete
            {card.completeness_score < 100 && " · contributions welcome"}
          </span>
        )}
      </button>
      {open && card && (
        <div className="px-4 pb-4 space-y-3 text-xs">
          {/* Threat model */}
          {card.threat_model && (
            <div>
              <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">Threat Model</div>
              <p className="text-slate-700">{card.threat_model}</p>
            </div>
          )}
          {/* Papers */}
          {card.papers?.length > 0 && (
            <div>
              <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">Scientific Grounding</div>
              <div className="space-y-1.5">
                {card.papers.map((p: any, i: number) => (
                  <div key={i} className="flex items-start gap-2">
                    <span className="text-slate-300 shrink-0">[{i+1}]</span>
                    <div>
                      {p.url
                        ? <a href={p.url} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline font-medium">{p.title}</a>
                        : <span className="font-medium text-slate-700">{p.title}</span>
                      }
                      {p.authors && <span className="text-slate-400"> — {p.authors}{p.year ? `, ${p.year}` : ""}</span>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          {/* Grid: scoring, confidence, autonomy */}
          <div className="grid grid-cols-3 gap-3">
            {card.scoring_method && (
              <div className="bg-slate-50 rounded-lg p-2">
                <div className="text-[10px] font-semibold text-slate-400 mb-1">Scoring</div>
                <p className="text-slate-600">{card.scoring_method}</p>
              </div>
            )}
            {card.confidence_bounds && (
              <div className="bg-slate-50 rounded-lg p-2">
                <div className="text-[10px] font-semibold text-slate-400 mb-1">Confidence</div>
                <p className="text-slate-600">{card.confidence_bounds}</p>
              </div>
            )}
            {card.autonomy_levels?.length > 0 && (
              <div className="bg-slate-50 rounded-lg p-2">
                <div className="text-[10px] font-semibold text-slate-400 mb-1">Autonomy levels</div>
                <div className="flex flex-wrap gap-1">
                  {card.autonomy_levels.map((l: string) => (
                    <span key={l} className="text-[9px] bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded font-mono">{l}</span>
                  ))}
                </div>
              </div>
            )}
          </div>
          {/* Known blind spots */}
          {card.known_blind_spots && card.known_blind_spots !== "Not yet documented for this benchmark." && (
            <div>
              <div className="text-[10px] font-bold text-amber-500 uppercase tracking-wider mb-1">⚠ Known Blind Spots</div>
              <p className="text-slate-600 italic">{card.known_blind_spots}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

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
  // Security wizard state
  const [showSecurityWizard, setShowSecurityWizard] = useState(false);
  // Tag management state
  const [editingTagsId, setEditingTagsId] = useState<number | null>(null);
  const [newTagInput, setNewTagInput] = useState("");

  const handleFlipSource = async (b: Benchmark) => {
    const newSource = b.source === "inesia" ? "public" : "inesia";
    try {
      await fetch(`${API_BASE}/benchmarks/${b.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source: newSource }),
      });
      load();
    } catch {}
  };

  const handleAddTag = async (b: Benchmark) => {
    const tag = newTagInput.trim();
    if (!tag || b.tags.includes(tag)) return;
    try {
      await fetch(`${API_BASE}/benchmarks/${b.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tags: [...b.tags, tag] }),
      });
      setNewTagInput("");
      load();
    } catch {}
  };

  const handleRemoveTag = async (b: Benchmark, tag: string) => {
    try {
      await fetch(`${API_BASE}/benchmarks/${b.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tags: b.tags.filter(t => t !== tag) }),
      });
      load();
    } catch {}
  };

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

  // HuggingFace explorer
  const [showHfImport, setShowHfImport] = useState(false);
  const [hfQuery, setHfQuery]           = useState("");
  const [hfResults, setHfResults]       = useState<any[]>([]);
  const [hfSearching, setHfSearching]   = useState(false);
  const [hfSelected, setHfSelected]     = useState<any | null>(null);
  const [hfForm, setHfForm]             = useState({ repo_id: "", split: "test", subset: "", max_items: 500 });
  const [hfLoading, setHfLoading]       = useState(false);

  const searchHF = async (q: string) => {
    if (!q.trim()) { setHfResults([]); return; }
    setHfSearching(true);
    try {
      const res = await fetch(`https://huggingface.co/api/datasets?search=${encodeURIComponent(q)}&limit=12&sort=downloads&direction=-1`);
      const data = await res.json();
      setHfResults(Array.isArray(data) ? data : []);
    } catch { setHfResults([]); }
    setHfSearching(false);
  };

  useEffect(() => {
    const t = setTimeout(() => searchHF(hfQuery), 400);
    return () => clearTimeout(t);
  }, [hfQuery]);

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
      setHfSelected(null);
      setHfResults([]);
      setHfQuery("");
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
            <button onClick={() => setShowSecurityWizard(true)}
              className="flex items-center gap-2 bg-red-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-red-700 transition-colors">
              <Shield size={14} /> Security Wizard
            </button>
          </div>
        }
      />

      {importMsg && (
        <div className="mx-8 mt-4 bg-green-50 border border-green-200 rounded-xl px-4 py-3 text-sm text-green-700">
          ✅ {importMsg}
        </div>
      )}

      {/* HuggingFace Explorer */}
      {showHfImport && (
        <div className="mx-8 mt-6 bg-white border border-yellow-200 rounded-xl p-6">
          <h3 className="font-medium text-slate-900 mb-4 flex items-center gap-2">🤗 HuggingFace Dataset Explorer</h3>

          {/* Search */}
          <div className="relative mb-4">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              value={hfQuery}
              onChange={e => setHfQuery(e.target.value)}
              placeholder="Search datasets… (e.g. mmlu, truthfulqa, gsm8k)"
              className="w-full pl-9 pr-4 py-2.5 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-yellow-400"
            />
            {hfSearching && <Spinner size={13} className="absolute right-3 top-1/2 -translate-y-1/2" />}
          </div>

          {/* Results grid */}
          {hfResults.length > 0 && (
            <div className="grid grid-cols-2 gap-2 mb-4 max-h-64 overflow-y-auto">
              {hfResults.map((ds: any) => (
                <button
                  key={ds.id}
                  onClick={() => { setHfSelected(ds); setHfForm(f => ({ ...f, repo_id: ds.id })); }}
                  className={`text-left p-3 rounded-lg border transition-colors text-xs ${
                    hfSelected?.id === ds.id
                      ? "border-yellow-400 bg-yellow-50"
                      : "border-slate-200 hover:border-slate-300 hover:bg-slate-50"
                  }`}
                >
                  <div className="font-medium text-slate-900 truncate">{ds.id}</div>
                  <div className="text-slate-400 mt-0.5 flex items-center gap-2">
                    {ds.downloads != null && <span>⬇ {(ds.downloads / 1000).toFixed(0)}k</span>}
                    {ds.likes != null && <span>♥ {ds.likes}</span>}
                    {ds.gated && <span className="text-amber-600 font-medium">GATED</span>}
                  </div>
                  {ds.tags?.slice(0, 3).map((t: string) => (
                    <span key={t} className="inline-block mt-1 mr-1 px-1.5 py-0.5 bg-slate-100 text-slate-500 rounded text-[10px]">{t}</span>
                  ))}
                </button>
              ))}
            </div>
          )}

          {/* Import config — shown once dataset selected */}
          {hfSelected && (
            <div className="border border-yellow-200 rounded-lg p-4 bg-yellow-50 mb-4">
              <div className="text-sm font-semibold text-slate-800 mb-3">
                Import: <span className="font-mono text-yellow-700">{hfSelected.id}</span>
              </div>
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="text-xs font-medium text-slate-600 mb-1 block">Split</label>
                  <select value={hfForm.split} onChange={e => setHfForm(f => ({ ...f, split: e.target.value }))}
                    className="w-full border border-slate-200 rounded-lg px-2 py-1.5 text-sm bg-white">
                    <option value="test">test</option>
                    <option value="train">train</option>
                    <option value="validation">validation</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs font-medium text-slate-600 mb-1 block">Subset (optional)</label>
                  <input value={hfForm.subset} onChange={e => setHfForm(f => ({ ...f, subset: e.target.value }))}
                    placeholder="abstract_algebra…"
                    className="w-full border border-slate-200 rounded-lg px-2 py-1.5 text-sm bg-white" />
                </div>
                <div>
                  <label className="text-xs font-medium text-slate-600 mb-1 block">Max items</label>
                  <input type="number" value={hfForm.max_items} onChange={e => setHfForm(f => ({ ...f, max_items: +e.target.value }))}
                    min={10} max={5000}
                    className="w-full border border-slate-200 rounded-lg px-2 py-1.5 text-sm bg-white" />
                </div>
              </div>
              <div className="flex items-center gap-3 mt-3">
                <button onClick={handleHfImport} disabled={hfLoading}
                  className="flex items-center gap-2 bg-yellow-500 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-yellow-600 disabled:opacity-40">
                  {hfLoading ? <Spinner size={13} /> : "🤗"}
                  {hfLoading ? "Importing…" : "Import dataset"}
                </button>
                <button onClick={() => { setHfSelected(null); setHfForm(f => ({ ...f, repo_id: "" })); }}
                  className="text-sm text-slate-500 hover:text-slate-700">
                  Deselect
                </button>
              </div>
            </div>
          )}

          {/* Manual entry fallback */}
          {!hfSelected && (
            <div className="text-xs text-slate-400 flex items-center gap-2 mt-2">
              Or enter manually:
              <input value={hfForm.repo_id} onChange={e => setHfForm(f => ({ ...f, repo_id: e.target.value }))}
                placeholder="owner/dataset-name"
                className="border border-slate-200 rounded px-2 py-1 text-xs w-48" />
              {hfForm.repo_id && (
                <button onClick={handleHfImport} disabled={hfLoading}
                  className="text-xs bg-yellow-500 text-white px-3 py-1 rounded hover:bg-yellow-600 disabled:opacity-40">
                  {hfLoading ? "…" : "Import"}
                </button>
              )}
            </div>
          )}

          <button onClick={() => { setShowHfImport(false); setHfResults([]); setHfSelected(null); setHfQuery(""); }}
            className="mt-4 text-xs text-slate-400 hover:text-slate-600">
            ✕ Fermer
          </button>
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
                      {/* Source badge — INESIA vs Public */}
                      {b.source === "inesia"
                        ? <Badge className="bg-purple-100 text-purple-700 border border-purple-200 font-bold text-[10px]">☿ INESIA</Badge>
                        : <Badge className="bg-slate-100 text-slate-500 border border-slate-200 text-[10px]">PUBLIC</Badge>
                      }
                      {b.is_builtin && <Badge className="bg-slate-100 text-slate-500"><Lock size={10} className="inline mr-1" />Built-in</Badge>}
                      {b.risk_threshold && <Badge className="bg-red-100 text-red-600"><AlertTriangle size={10} className="inline mr-1" />Frontier</Badge>}
                      {b.risk_threshold && b.source === "inesia" && (
                        <Badge className="bg-red-700 text-white text-[9px] font-bold">🔴 BLOCKING</Badge>
                      )}
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

                    {/* ── Benchmark Card (scientific provenance) ────────── */}
                    <BenchmarkCard benchmarkId={b.id} benchmarkName={b.name} />

                    {/* ── Tag manager ─────────────────────────────────── */}
                    <div className="mb-3">
                      <div className="flex items-center gap-2 mb-1.5">
                        <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide">Tags</span>
                        <button
                          onClick={e => { e.stopPropagation(); setEditingTagsId(editingTagsId === b.id ? null : b.id); setNewTagInput(""); }}
                          className="text-[10px] text-blue-500 hover:underline"
                        >
                          {editingTagsId === b.id ? "Done" : "Edit"}
                        </button>
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {b.tags?.map((t: string) => (
                          <span key={t} className="inline-flex items-center gap-1 text-[10px] bg-white border border-slate-200 text-slate-600 rounded-full px-2 py-0.5">
                            {t}
                            {editingTagsId === b.id && (
                              <button
                                onClick={e => { e.stopPropagation(); handleRemoveTag(b, t); }}
                                className="text-slate-400 hover:text-red-500 ml-0.5"
                              >
                                ×
                              </button>
                            )}
                          </span>
                        ))}
                        {editingTagsId === b.id && (
                          <form
                            onSubmit={e => { e.preventDefault(); e.stopPropagation(); handleAddTag(b); }}
                            className="flex items-center gap-1"
                            onClick={e => e.stopPropagation()}
                          >
                            <input
                              value={newTagInput}
                              onChange={e => setNewTagInput(e.target.value)}
                              placeholder="New tag…"
                              className="text-[10px] border border-dashed border-slate-300 rounded-full px-2 py-0.5 w-20 focus:outline-none focus:border-blue-400"
                            />
                            <button type="submit" className="text-[10px] text-blue-500 hover:underline">+ Add</button>
                          </form>
                        )}
                      </div>
                    </div>

                    {/* ── Source flip button ───────────────────────────── */}
                    <div className="mb-3 flex items-center gap-2">
                      <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide">Source</span>
                      <button
                        onClick={e => { e.stopPropagation(); handleFlipSource(b); }}
                        className={`text-[10px] px-2 py-0.5 rounded-full border font-bold transition-colors cursor-pointer hover:opacity-80 ${
                          b.source === "inesia"
                            ? "bg-purple-100 text-purple-700 border-purple-200"
                            : "bg-slate-100 text-slate-500 border-slate-200"
                        }`}
                        title="Click to toggle INESIA / Public classification"
                      >
                        {b.source === "inesia" ? "☿ INESIA" : "PUBLIC"} ↔ click to change
                      </button>
                    </div>

                    <div className="flex gap-2 flex-wrap">
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
      {showSecurityWizard && (
        <SecurityBenchmarkWizard
          onClose={() => setShowSecurityWizard(false)}
          onCreated={() => { setShowSecurityWizard(false); load(); }}
        />
      )}
    </div>
  );
}
