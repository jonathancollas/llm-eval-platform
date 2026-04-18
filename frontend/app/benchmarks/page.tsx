"use client";
import { useEffect, useState, useCallback } from "react";
import { benchmarksApi } from "@/lib/api";
import type { Benchmark } from "@/lib/api";
import { useBenchmarks } from "@/lib/useApi";
import { useSync } from "@/lib/useSync";
import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/Badge";
import { EmptyState } from "@/components/EmptyState";
import { Spinner } from "@/components/Spinner";
import { BenchmarkCatalogModal } from "@/components/BenchmarkCatalogModal";
import { BenchmarkWizard } from "@/components/BenchmarkWizard";
import { SecurityBenchmarkWizard } from "@/components/SecurityBenchmarkWizard";
import { benchmarkTypeColor } from "@/lib/utils";
import { Upload, Lock, AlertTriangle, Plus, ChevronDown, ChevronUp, Sparkles,
         Search, ChevronLeft, ChevronRight, Eye, Shield, GitFork, Quote } from "lucide-react";

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
function BenchmarkCard({
  benchmarkId,
  benchmarkName,
  onForked,
}: {
  benchmarkId: number;
  benchmarkName: string;
  onForked?: () => void;
}) {
  const [card, setCard] = useState<any | null>(null);
  const [lineage, setLineage] = useState<any | null>(null);
  const [citations, setCitations] = useState<any | null>(null);
  const [open, setOpen] = useState(false);
  const [forking, setForking] = useState(false);

  const load = async () => {
    if (card) { setOpen(o => !o); return; }
    try {
      const [cardRes, lineageRes, citationRes] = await Promise.all([
        fetch(`${API_BASE}/benchmarks/${benchmarkId}/card`),
        fetch(`${API_BASE}/benchmarks/${benchmarkId}/lineage`),
        fetch(`${API_BASE}/benchmarks/${benchmarkId}/citations`),
      ]);
      setCard(cardRes.ok ? await cardRes.json() : null);
      setLineage(lineageRes.ok ? await lineageRes.json() : null);
      setCitations(citationRes.ok ? await citationRes.json() : null);
      setOpen(true);
    } catch (err) { console.warn("[error]", err); }
  };

  const handleFork = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setForking(true);
    try {
      await benchmarksApi.fork(benchmarkId, { fork_type: "extension", changes_description: "Forked from benchmark card" });
      setCard(null);
      setLineage(null);
      setCitations(null);
      onForked?.();
      await load();
    } finally {
      setForking(false);
    }
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
          <div className="flex items-center justify-between gap-2">
            <div className="text-[10px] text-slate-500">
              {benchmarkName}
              {citations && <span className="ml-2 text-slate-400">· {citations.citation_count} citations</span>}
            </div>
            <button
              onClick={handleFork}
              disabled={forking}
              className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-1 text-[10px] font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-60"
            >
              <GitFork size={10} />
              {forking ? "Forking..." : "Fork"}
            </button>
          </div>

          {lineage && (
            <div className="rounded-lg border border-slate-100 bg-slate-50 p-2">
              <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">Fork Lineage</div>
              <div className="text-slate-700">
                {lineage.parent ? (
                  <div className="mb-1">Parent: <span className="font-medium">{lineage.parent.name}</span></div>
                ) : (
                  <div className="mb-1 text-slate-500">Parent: none (root benchmark)</div>
                )}
                {lineage.children?.length > 0 ? (
                  <div className="space-y-0.5">
                    {lineage.children.map((child: any) => (
                      <div key={child.id} className="text-[11px] text-slate-600">
                        └─ {child.name}
                        {child.fork_type ? ` · ${child.fork_type}` : ""}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-slate-500">No forks yet.</div>
                )}
              </div>
            </div>
          )}

          {citations && (
            <div className="rounded-lg border border-blue-100 bg-blue-50/50 p-2">
              <div className="text-[10px] font-bold text-blue-700 uppercase tracking-wider mb-1 flex items-center gap-1">
                <Quote size={10} /> Citation Graph
              </div>
              <div className="text-[11px] text-slate-600 mb-1">
                Influence score: <span className="font-semibold">{citations.influence_score}</span>
              </div>
              <div className="space-y-1">
                {(citations.citations_by_year || []).map((entry: any) => {
                  const max = Math.max(...(citations.citations_by_year || []).map((e: any) => e.count), 1);
                  return (
                    <div key={entry.year} className="flex items-center gap-2">
                      <span className="w-10 text-[10px] text-slate-500">{entry.year}</span>
                      <div className="h-2 rounded bg-blue-200" style={{ width: `${Math.max(8, Math.round((entry.count / max) * 120))}px` }} />
                      <span className="text-[10px] text-slate-500">{entry.count}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

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
  const [showCatalog, setShowCatalog] = useState(false);
  const [showWizard, setShowWizard] = useState(false);
  const [uploadId, setUploadId] = useState<number | null>(null);
  const { benchmarksAdded: newBenchmarks } = useSync();
  const [importing, setImporting] = useState(false);
  const [importMsg, setImportMsg] = useState<string | null>(null);
  // Security wizard state
  const [showSecurityWizard, setShowSecurityWizard] = useState(false);
  // Tag management state
  const [editingTagsId, setEditingTagsId] = useState<number | null>(null);
  const [newTagInput, setNewTagInput] = useState("");
  // Giskard full scan state
  const [giskardScanBenchId, setGiskardScanBenchId] = useState<number | null>(null);
  const [giskardScanModelId, setGiskardScanModelId] = useState<number | "">("");
  const [giskardScanRunning, setGiskardScanRunning] = useState(false);
  const [giskardScanResult, setGiskardScanResult] = useState<any | null>(null);
  const [giskardScanError, setGiskardScanError] = useState<string | null>(null);
  const [models, setModels] = useState<any[]>([]);
  useEffect(() => {
    fetch(`${API_BASE}/models?limit=100`).then(r => r.ok ? r.json() : null).then(d => d && setModels(d.items ?? [])).catch((err) => console.warn("[fetch error]", err));
  }, []);

  const handleFlipSource = async (b: Benchmark) => {
    const newSource = b.source === "inesia" ? "public" : "inesia";
    try {
      await fetch(`${API_BASE}/benchmarks/${b.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source: newSource }),
      });
      load();
    } catch (err) { console.warn("[error]", err); }
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
    } catch (err) { console.warn("[error]", err); }
  };

  const handleRemoveTag = async (b: Benchmark, tag: string) => {
    try {
      await fetch(`${API_BASE}/benchmarks/${b.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tags: b.tags.filter(t => t !== tag) }),
      });
      load();
    } catch (err) { console.warn("[error]", err); }
  };

  const { benchmarks: swrBenches, isLoading: swrBenchLoading, refresh: refreshBenches } = useBenchmarks();
  useEffect(() => { setBenches(swrBenches); if (!swrBenchLoading) setLoading(false); }, [swrBenches, swrBenchLoading]);
  const load = useCallback(() => { refreshBenches(); }, [refreshBenches]);

  const filtered = benches.filter(b => matchFilter(b, filter));
  const countFor = (f: FilterKey) => benches.filter(b => matchFilter(b, f)).length;

  const handleUpload = async (benchId: number, file: File) => {
    try {
      await benchmarksApi.uploadDataset(benchId, file);
      load();
    } catch (err) { console.error(String(err)); }
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

  const runGiskardScan = async (benchId: number) => {
    if (!giskardScanModelId) return;
    setGiskardScanRunning(true);
    setGiskardScanResult(null);
    setGiskardScanError(null);
    try {
      const res = await fetch(`${API_BASE}/benchmarks/giskard/scan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model_id: giskardScanModelId, max_samples: 20 }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? `HTTP ${res.status}`);
      setGiskardScanResult(data);
    } catch (e: any) {
      setGiskardScanError(e.message);
    } finally {
      setGiskardScanRunning(false);
    }
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
            <button onClick={() => setShowWizard(true)}
              className="flex items-center gap-2 bg-slate-900 text-white px-4 py-2 rounded-lg text-sm hover:bg-slate-700 transition-colors">
              <Plus size={14} /> Nouveau benchmark
            </button>
            <button onClick={() => setShowSecurityWizard(true)}
              className="flex items-center gap-2 bg-red-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-red-700 transition-colors">
              <Shield size={14} /> Security Wizard
            </button>
          </div>
        }
      />

      {importMsg && (
        <div className="mx-4 sm:mx-8 mt-4 bg-green-50 border border-green-200 rounded-xl px-4 py-3 text-sm text-green-700">
          ✅ {importMsg}
        </div>
      )}

      {/* Filter tabs */}
      <div className="px-4 sm:px-8 pt-6 pb-2 flex gap-2 flex-wrap">
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
      <div className="p-4 sm:p-8 pt-4">
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
                      <Badge className="bg-blue-100 text-blue-700 border border-blue-200 text-[10px]">
                        <Quote size={10} className="inline mr-1" />{b.citation_count ?? 0}
                      </Badge>
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
                    <BenchmarkCard benchmarkId={b.id} benchmarkName={b.name} onForked={load} />

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
                      {/* Giskard full scan — shown only for giskard benchmarks */}
                      {b.name.toLowerCase().includes("giskard") && (
                        <div className="w-full mt-2 border border-green-200 rounded-xl bg-green-50 p-3 space-y-2" onClick={e => e.stopPropagation()}>
                          <p className="text-xs font-semibold text-green-800 flex items-center gap-1.5">
                            <Shield size={12} /> Giskard Full Vulnerability Scan
                          </p>
                          <p className="text-xs text-green-700">
                            Run the Giskard LLM scanner against a model to get a structured vulnerability report.
                          </p>
                          <div className="flex gap-2 flex-wrap items-center">
                            <select
                              value={giskardScanModelId}
                              onChange={e => { setGiskardScanModelId(Number(e.target.value) || ""); setGiskardScanBenchId(b.id); setGiskardScanResult(null); setGiskardScanError(null); }}
                              className="text-xs border border-green-300 rounded-lg px-2 py-1.5 bg-white text-slate-700 focus:outline-none"
                            >
                              <option value="">Select model…</option>
                              {models.map((m: any) => (
                                <option key={m.id} value={m.id}>{m.name}</option>
                              ))}
                            </select>
                            <button
                              onClick={() => runGiskardScan(b.id)}
                              disabled={giskardScanRunning || !giskardScanModelId}
                              className="flex items-center gap-1.5 text-xs px-3 py-1.5 bg-green-700 text-white rounded-lg hover:bg-green-800 disabled:opacity-40 transition-colors"
                            >
                              {giskardScanRunning && giskardScanBenchId === b.id ? <Spinner size={11} /> : <Shield size={11} />}
                              {giskardScanRunning && giskardScanBenchId === b.id ? "Scanning…" : "Run Giskard scan"}
                            </button>
                          </div>
                          {giskardScanError && giskardScanBenchId === b.id && (
                            <p className="text-xs text-red-700 bg-red-50 border border-red-200 rounded p-2">{giskardScanError}</p>
                          )}
                          {giskardScanResult && giskardScanBenchId === b.id && (
                            <div className="bg-white border border-green-200 rounded-lg p-3 text-xs space-y-2">
                              <div className="flex items-center gap-3 flex-wrap">
                                <span className="font-semibold text-slate-800">{giskardScanResult.model_name}</span>
                                <span className={`px-2 py-0.5 rounded font-bold ${
                                  giskardScanResult.safety_score >= 0.8 ? "bg-green-100 text-green-700"
                                  : giskardScanResult.safety_score >= 0.5 ? "bg-yellow-100 text-yellow-700"
                                  : "bg-red-100 text-red-700"
                                }`}>
                                  Safety: {Math.round((giskardScanResult.safety_score ?? 0) * 100)}%
                                </span>
                                <span className="text-slate-400">{giskardScanResult.num_items} items</span>
                                {giskardScanResult.metrics?.giskard_available !== undefined && (
                                  <span className={`text-[10px] px-2 py-0.5 rounded font-bold ${
                                    giskardScanResult.metrics.giskard_available
                                      ? "bg-green-100 text-green-700"
                                      : "bg-yellow-100 text-yellow-700"
                                  }`}>
                                    Giskard SDK: {giskardScanResult.metrics.giskard_available ? "installed" : "fallback"}
                                  </span>
                                )}
                              </div>
                              {giskardScanResult.metrics?.vulnerability_scores && Object.keys(giskardScanResult.metrics.vulnerability_scores).length > 0 && (
                                <div>
                                  <p className="text-slate-500 font-semibold mb-1">Vulnerability breakdown:</p>
                                  <div className="space-y-1">
                                    {Object.entries(giskardScanResult.metrics.vulnerability_scores as Record<string, number>).map(([vuln, score]) => (
                                      <div key={vuln} className="flex items-center gap-2">
                                        <span className="text-slate-600 flex-1 truncate">{vuln}</span>
                                        <div className="w-20 h-1.5 bg-slate-200 rounded-full overflow-hidden">
                                          <div
                                            className={`h-full rounded-full ${score >= 0.8 ? "bg-green-500" : score >= 0.5 ? "bg-yellow-500" : "bg-red-500"}`}
                                            style={{ width: `${Math.round(score * 100)}%` }}
                                          />
                                        </div>
                                        <span className={`font-mono font-bold w-9 text-right ${score >= 0.8 ? "text-green-700" : score >= 0.5 ? "text-yellow-700" : "text-red-700"}`}>
                                          {Math.round(score * 100)}%
                                        </span>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              )}
                              {giskardScanResult.metrics?.alerts?.length > 0 && (
                                <div className="bg-red-50 border border-red-200 rounded p-2 space-y-0.5">
                                  {(giskardScanResult.metrics.alerts as string[]).map((alert: string, ai: number) => (
                                    <p key={ai} className="text-red-700">⚠ {alert}</p>
                                  ))}
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      )}
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
      {showWizard && (
        <BenchmarkWizard
          onClose={() => setShowWizard(false)}
          onCreated={() => { setShowWizard(false); load(); }}
        />
      )}
      {showSecurityWizard && (
        <SecurityBenchmarkWizard
          onClose={() => setShowSecurityWizard(false)}
          onCreated={() => { setShowSecurityWizard(false); load(); }}
        />
      )}
    </div>
  );
}
