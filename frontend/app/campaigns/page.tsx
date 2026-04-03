"use client";
import { useEffect, useState, useCallback } from "react";
import { campaignsApi, modelsApi, benchmarksApi } from "@/lib/api";
import type { Campaign, LLMModel, Benchmark } from "@/lib/api";
import { PageHeader } from "@/components/PageHeader";
import { StatusBadge } from "@/components/StatusBadge";
import { EmptyState } from "@/components/EmptyState";
import { Spinner } from "@/components/Spinner";
import { formatCost, formatScore, timeAgo } from "@/lib/utils";
import { Plus, Play, Square, Trash2, BarChart2, ChevronRight } from "lucide-react";
import Link from "next/link";

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [models, setModels] = useState<LLMModel[]>([]);
  const [benches, setBenches] = useState<Benchmark[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    name: "", description: "", model_ids: [] as number[],
    benchmark_ids: [] as number[], seed: 42, max_samples: 50, temperature: 0.0,
  });

  const load = useCallback(() => {
    Promise.all([campaignsApi.list(), modelsApi.list(), benchmarksApi.list()])
      .then(([c, m, b]) => { setCampaigns(c); setModels(m); setBenches(b); })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
    // Poll running campaigns every 3s
    const interval = setInterval(() => {
      setCampaigns(prev => {
        if (prev.some(c => c.status === "running")) { load(); }
        return prev;
      });
    }, 3000);
    return () => clearInterval(interval);
  }, [load]);

  const toggleId = (arr: number[], id: number) =>
    arr.includes(id) ? arr.filter(x => x !== id) : [...arr, id];

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.model_ids.length) return alert("Select at least one model.");
    if (!form.benchmark_ids.length) return alert("Select at least one benchmark.");
    setSaving(true);
    try {
      await campaignsApi.create({ ...form });
      setShowForm(false);
      setForm({ name: "", description: "", model_ids: [], benchmark_ids: [], seed: 42, max_samples: 50, temperature: 0.0 });
      load();
    } catch (err) { alert(String(err)); } finally { setSaving(false); }
  };

  const handleRun = async (id: number) => {
    await campaignsApi.run(id).catch(e => alert(String(e)));
    load();
  };

  const handleCancel = async (id: number) => {
    await campaignsApi.cancel(id).catch(e => alert(String(e)));
    load();
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Delete campaign and all results?")) return;
    await campaignsApi.delete(id).catch(e => alert(String(e)));
    load();
  };

  return (
    <div>
      <PageHeader
        title="Campaigns"
        description="Multi-model × multi-benchmark evaluation runs."
        action={
          <button onClick={() => setShowForm(!showForm)}
            className="flex items-center gap-2 bg-slate-900 text-white px-4 py-2 rounded-lg text-sm hover:bg-slate-700 transition-colors">
            <Plus size={14} /> New Campaign
          </button>
        }
      />

      {showForm && (
        <div className="mx-8 mt-6 bg-white border border-slate-200 rounded-xl p-6">
          <h3 className="font-medium text-slate-900 mb-4">New Campaign</h3>
          <form onSubmit={handleCreate} className="space-y-5">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-xs font-medium text-slate-600 mb-1 block">Campaign name *</label>
                <input required value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                  placeholder="e.g. MMLU comparison v1"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900" />
              </div>
              <div>
                <label className="text-xs font-medium text-slate-600 mb-1 block">Description</label>
                <input value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900" />
              </div>
            </div>

            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="text-xs font-medium text-slate-600 mb-1 block">Seed</label>
                <input type="number" value={form.seed} onChange={e => setForm(f => ({ ...f, seed: +e.target.value }))}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900" />
              </div>
              <div>
                <label className="text-xs font-medium text-slate-600 mb-1 block">Max samples / benchmark</label>
                <input type="number" value={form.max_samples} onChange={e => setForm(f => ({ ...f, max_samples: +e.target.value }))}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900" />
              </div>
              <div>
                <label className="text-xs font-medium text-slate-600 mb-1 block">Temperature</label>
                <input type="number" step="0.1" min="0" max="2" value={form.temperature} onChange={e => setForm(f => ({ ...f, temperature: +e.target.value }))}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900" />
              </div>
            </div>

            {/* Model selection */}
            <div>
              <label className="text-xs font-medium text-slate-600 mb-2 block">
                Models * <span className="font-normal text-slate-400">({form.model_ids.length} selected)</span>
              </label>
              {models.length === 0 ? (
                <p className="text-xs text-slate-400">No models registered. <Link href="/models" className="text-blue-600 hover:underline">Add one →</Link></p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {models.map(m => (
                    <button key={m.id} type="button"
                      onClick={() => setForm(f => ({ ...f, model_ids: toggleId(f.model_ids, m.id) }))}
                      className={`text-sm px-3 py-1.5 rounded-lg border transition-colors ${form.model_ids.includes(m.id) ? "bg-slate-900 text-white border-slate-900" : "bg-white border-slate-200 text-slate-700 hover:bg-slate-50"}`}>
                      {m.name}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Benchmark selection */}
            <div>
              <label className="text-xs font-medium text-slate-600 mb-2 block">
                Benchmarks * <span className="font-normal text-slate-400">({form.benchmark_ids.length} selected)</span>
              </label>
              {benches.length === 0 ? (
                <p className="text-xs text-slate-400">No benchmarks available.</p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {benches.filter(b => b.has_dataset || b.is_builtin).map(b => (
                    <button key={b.id} type="button"
                      onClick={() => setForm(f => ({ ...f, benchmark_ids: toggleId(f.benchmark_ids, b.id) }))}
                      className={`text-sm px-3 py-1.5 rounded-lg border transition-colors ${form.benchmark_ids.includes(b.id) ? "bg-slate-900 text-white border-slate-900" : "bg-white border-slate-200 text-slate-700 hover:bg-slate-50"}`}>
                      {b.name}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="flex gap-3 pt-1">
              <button type="submit" disabled={saving}
                className="bg-slate-900 text-white px-4 py-2 rounded-lg text-sm hover:bg-slate-700 transition-colors disabled:opacity-50">
                {saving ? "Creating…" : "Create Campaign"}
              </button>
              <button type="button" onClick={() => setShowForm(false)} className="px-4 py-2 text-sm text-slate-600">Cancel</button>
            </div>
          </form>
        </div>
      )}

      <div className="p-8 pt-6">
        {loading ? (
          <div className="flex justify-center py-20"><Spinner size={24} /></div>
        ) : campaigns.length === 0 ? (
          <EmptyState icon="🚀" title="No campaigns yet"
            description="Create a campaign to run models against benchmarks."
            action={<button onClick={() => setShowForm(true)} className="bg-slate-900 text-white px-4 py-2 rounded-lg text-sm">Create Campaign</button>}
          />
        ) : (
          <div className="space-y-3">
            {campaigns.map(c => {
              const totalCost = c.runs.reduce((s, r) => s + r.total_cost_usd, 0);
              const avgScore = c.runs.filter(r => r.score !== null).reduce((s, r, _, a) => s + (r.score ?? 0) / a.length, 0);
              return (
                <div key={c.id} className="bg-white border border-slate-200 rounded-xl p-5">
                  <div className="flex items-start gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-3 mb-1 flex-wrap">
                        <span className="font-medium text-slate-900">{c.name}</span>
                        <StatusBadge status={c.status} />
                      </div>
                      {c.description && <p className="text-xs text-slate-400 mb-2">{c.description}</p>}
                      <div className="flex items-center gap-4 text-xs text-slate-500">
                        <span>{c.model_ids.length} model{c.model_ids.length !== 1 ? "s" : ""}</span>
                        <span>{c.benchmark_ids.length} benchmark{c.benchmark_ids.length !== 1 ? "s" : ""}</span>
                        {c.runs.length > 0 && <span>{formatScore(avgScore)} avg</span>}
                        {totalCost > 0 && <span>{formatCost(totalCost)}</span>}
                        <span>{timeAgo(c.created_at)}</span>
                      </div>
                    </div>

                    {/* Progress bar */}
                    {c.status === "running" && (
                      <div className="flex items-center gap-2 text-xs text-blue-600">
                        <Spinner size={12} />
                        <div className="w-32 bg-slate-100 rounded-full h-1.5">
                          <div className="bg-blue-500 h-1.5 rounded-full transition-all" style={{ width: `${c.progress}%` }} />
                        </div>
                        {c.progress.toFixed(0)}%
                      </div>
                    )}

                    <div className="flex items-center gap-2 shrink-0">
                      {c.status === "completed" && (
                        <Link href={`/dashboard?campaign=${c.id}`}
                          className="flex items-center gap-1.5 text-xs px-3 py-1.5 border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600">
                          <BarChart2 size={12} /> Dashboard
                        </Link>
                      )}
                      {(c.status === "pending" || c.status === "failed" || c.status === "cancelled") && (
                        <button onClick={() => handleRun(c.id)}
                          className="flex items-center gap-1.5 text-xs px-3 py-1.5 bg-emerald-50 border border-emerald-200 rounded-lg hover:bg-emerald-100 text-emerald-700">
                          <Play size={12} /> Run
                        </button>
                      )}
                      {c.status === "running" && (
                        <button onClick={() => handleCancel(c.id)}
                          className="flex items-center gap-1.5 text-xs px-3 py-1.5 bg-orange-50 border border-orange-200 rounded-lg text-orange-700">
                          <Square size={12} /> Cancel
                        </button>
                      )}
                      <button onClick={() => handleDelete(c.id)}
                        className="p-1.5 text-slate-300 hover:text-red-500 transition-colors">
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>

                  {/* Run breakdown */}
                  {c.runs.length > 0 && (
                    <div className="mt-4 pt-4 border-t border-slate-100 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
                      {c.runs.map(r => {
                        const m = models.find(x => x.id === r.model_id);
                        const b = benches.find(x => x.id === r.benchmark_id);
                        return (
                          <div key={r.id} className="bg-slate-50 rounded-lg px-3 py-2 text-xs">
                            <div className="font-medium text-slate-700 truncate">{m?.name ?? "?"}</div>
                            <div className="text-slate-400 truncate">{b?.name ?? "?"}</div>
                            <div className={`mt-1 font-mono font-medium ${r.score !== null ? (r.score >= 0.7 ? "text-green-600" : r.score >= 0.5 ? "text-amber-600" : "text-red-500") : "text-slate-400"}`}>
                              {r.score !== null ? formatScore(r.score) : r.status}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
