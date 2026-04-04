"use client";
import { useEffect, useState } from "react";
import { BenchmarkCatalogModal } from "@/components/BenchmarkCatalogModal";
import { benchmarksApi } from "@/lib/api";
import type { Benchmark, BenchmarkType } from "@/lib/api";
import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/Badge";
import { EmptyState } from "@/components/EmptyState";
import { Spinner } from "@/components/Spinner";
import { benchmarkTypeColor } from "@/lib/utils";
import { Upload, Lock, AlertTriangle, Plus, ChevronDown, ChevronUp } from "lucide-react";

const TYPE_LABELS: Record<BenchmarkType, string> = {
  academic: "Academic", safety: "Safety", coding: "Coding", custom: "Custom",
};

const TYPE_ICONS: Record<BenchmarkType, string> = {
  academic: "🎓", safety: "🛡️", coding: "💻", custom: "🧩",
};

export default function BenchmarksPage() {
  const [benches, setBenches] = useState<Benchmark[]>([]);
  const [filter, setFilter] = useState<BenchmarkType | "all">("all");
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [showCustomForm, setShowCustomForm] = useState(false);
  const [uploadId, setUploadId] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const [showCatalog, setShowCatalog] = useState(false);
  const [customForm, setCustomForm] = useState({ name: "", description: "", type: "custom" as BenchmarkType, metric: "accuracy" });

  const load = () => benchmarksApi.list().then(setBenches).finally(() => setLoading(false));
  useEffect(() => { load(); }, []);

  const filtered = filter === "all" ? benches : benches.filter(b => b.type === filter);

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

  return (
    <div>
      <PageHeader
        title="Benchmark Library"
        description="Built-in and custom evaluation benchmarks."
        action={
          <div className="flex gap-2">
          <button onClick={() => setShowCatalog(true)}
            className="flex items-center gap-2 border border-slate-200 px-4 py-2 rounded-lg text-sm hover:bg-slate-50 text-slate-700 transition-colors">
            🔍 Parcourir le catalogue
          </button>
          <button onClick={() => setShowCustomForm(!showCustomForm)}
            className="flex items-center gap-2 bg-slate-900 text-white px-4 py-2 rounded-lg text-sm hover:bg-slate-700 transition-colors">
            <Plus size={14} /> Import Custom
          </button>
          </div>
        }
      />

      {showCustomForm && (
        <div className="mx-8 mt-6 bg-white border border-slate-200 rounded-xl p-6">
          <h3 className="font-medium text-slate-900 mb-4">New Custom Benchmark</h3>
          <form onSubmit={handleCreateCustom} className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-medium text-slate-600 mb-1 block">Name</label>
              <input required value={customForm.name} onChange={e => setCustomForm(f => ({ ...f, name: e.target.value }))}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900" />
            </div>
            <div>
              <label className="text-xs font-medium text-slate-600 mb-1 block">Type</label>
              <select value={customForm.type} onChange={e => setCustomForm(f => ({ ...f, type: e.target.value as BenchmarkType }))}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900">
                <option value="custom">Custom</option>
                <option value="academic">Academic</option>
                <option value="safety">Safety</option>
                <option value="coding">Coding</option>
              </select>
            </div>
            <div className="col-span-2">
              <label className="text-xs font-medium text-slate-600 mb-1 block">Description</label>
              <textarea value={customForm.description} onChange={e => setCustomForm(f => ({ ...f, description: e.target.value }))}
                rows={2} className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900" />
            </div>
            <div>
              <label className="text-xs font-medium text-slate-600 mb-1 block">Primary metric</label>
              <input value={customForm.metric} onChange={e => setCustomForm(f => ({ ...f, metric: e.target.value }))}
                placeholder="accuracy"
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900" />
            </div>
            <div className="col-span-2 flex gap-3 pt-1">
              <button type="submit" disabled={creating}
                className="bg-slate-900 text-white px-4 py-2 rounded-lg text-sm hover:bg-slate-700 transition-colors disabled:opacity-50">
                {creating ? "Creating…" : "Create — then upload dataset"}
              </button>
              <button type="button" onClick={() => setShowCustomForm(false)} className="px-4 py-2 text-sm text-slate-600">Cancel</button>
            </div>
          </form>
        </div>
      )}

      {/* Upload prompt */}
      {uploadId && (
        <div className="mx-8 mt-4 bg-blue-50 border border-blue-200 rounded-xl p-4 flex items-center gap-4">
          <Upload size={16} className="text-blue-600 shrink-0" />
          <p className="text-sm text-blue-700">
            Benchmark created! Now upload your JSON dataset:
          </p>
          <input type="file" accept=".json"
            onChange={e => e.target.files?.[0] && handleUpload(uploadId, e.target.files[0])}
            className="text-sm text-blue-700" />
          <button onClick={() => setUploadId(null)} className="ml-auto text-xs text-blue-500">dismiss</button>
        </div>
      )}

      {/* Filter tabs */}
      <div className="px-8 pt-6 pb-2 flex gap-2">
        {(["all", "academic", "safety", "coding", "custom"] as const).map(t => (
          <button key={t} onClick={() => setFilter(t)}
            className={`text-sm px-3 py-1.5 rounded-lg transition-colors ${filter === t ? "bg-slate-900 text-white" : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50"}`}>
            {t === "all" ? "All" : TYPE_LABELS[t as BenchmarkType]}
            <span className="ml-1.5 text-xs opacity-60">
              {t === "all" ? benches.length : benches.filter(b => b.type === t).length}
            </span>
          </button>
        ))}
      </div>

      {/* Gallery */}
      <div className="p-8 pt-4">
        {loading ? (
          <div className="flex justify-center py-20"><Spinner size={24} /></div>
        ) : filtered.length === 0 ? (
          <EmptyState icon="📚" title="No benchmarks" description="Import a custom benchmark to get started." />
        ) : (
          <div className="grid grid-cols-1 gap-3">
            {filtered.map(b => (
              <div key={b.id} className="bg-white border border-slate-200 rounded-xl overflow-hidden">
                <div
                  className="flex items-center gap-4 p-5 cursor-pointer hover:bg-slate-50 transition-colors"
                  onClick={() => setExpanded(expanded === b.id ? null : b.id)}>
                  <span className="text-2xl">{TYPE_ICONS[b.type]}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <span className="font-medium text-slate-900">{b.name}</span>
                      <Badge className={benchmarkTypeColor(b.type)}>{TYPE_LABELS[b.type]}</Badge>
                      {b.is_builtin && <Badge className="bg-slate-100 text-slate-500"><Lock size={10} className="inline mr-1" />Built-in</Badge>}
                      {b.risk_threshold && <Badge className="bg-red-100 text-red-600"><AlertTriangle size={10} className="inline mr-1" />Risk threshold</Badge>}
                      {!b.has_dataset && !b.is_builtin && <Badge className="bg-orange-100 text-orange-600">⚠ No dataset</Badge>}
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
                  <div className="border-t border-slate-100 px-5 py-4 bg-slate-50 text-sm">
                    <div className="grid grid-cols-2 gap-4 mb-3 text-xs text-slate-600">
                      <div><span className="font-medium">Primary metric:</span> {b.metric}</div>
                      <div><span className="font-medium">Max samples:</span> {b.num_samples ?? "no limit"}</div>
                      {b.risk_threshold && <div><span className="font-medium">Risk threshold:</span> {(b.risk_threshold * 100).toFixed(0)}%</div>}
                    </div>
                    <p className="text-slate-600 text-xs">{b.description}</p>
                    <div className="flex flex-wrap gap-1.5 mt-3">
                      {b.tags.map(t => <Badge key={t} className="bg-white border border-slate-200 text-slate-600">{t}</Badge>)}
                    </div>
                    {!b.is_builtin && (
                      <div className="mt-3 flex gap-2">
                        <label className="cursor-pointer flex items-center gap-1.5 text-xs px-3 py-1.5 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600">
                          <Upload size={12} /> Upload JSON
                          <input type="file" accept=".json" className="hidden"
                            onChange={e => e.target.files?.[0] && handleUpload(b.id, e.target.files[0])} />
                        </label>
                        <button onClick={() => benchmarksApi.delete(b.id).then(load)}
                          className="text-xs px-3 py-1.5 text-red-500 hover:bg-red-50 border border-red-100 rounded-lg">
                          Delete
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    {showCatalog && <BenchmarkCatalogModal onClose={() => { setShowCatalog(false); load(); }} />}
    </div>
  );
}
