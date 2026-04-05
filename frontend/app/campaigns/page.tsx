"use client";
import { useEffect, useState, useCallback } from "react";
import { campaignsApi, modelsApi, benchmarksApi } from "@/lib/api";
import type { Campaign, LLMModel, Benchmark } from "@/lib/api";
import { PageHeader } from "@/components/PageHeader";
import { StatusBadge } from "@/components/StatusBadge";
import { EmptyState } from "@/components/EmptyState";
import { Spinner } from "@/components/Spinner";
import { formatCost, formatScore, timeAgo } from "@/lib/utils";
import { Plus, Play, Square, Trash2, BarChart2, RefreshCw } from "lucide-react";
import Link from "next/link";

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [models, setModels] = useState<LLMModel[]>([]);
  const [benches, setBenches] = useState<Benchmark[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [runningId, setRunningId] = useState<number | null>(null);
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
    setRunningId(id);
    try {
      await campaignsApi.run(id);
      load();
      // Poll until done
      const poll = setInterval(async () => {
        const updated = await campaignsApi.list();
        setCampaigns(updated);
        const c = updated.find((x: Campaign) => x.id === id);
        if (c && c.status !== "running" && c.status !== "pending") {
          clearInterval(poll);
          setRunningId(null);
        }
      }, 2000);
    } catch (e) {
      alert(String(e));
      setRunningId(null);
    }
  };

  const handleCancel = async (id: number) => {
    await campaignsApi.cancel(id).catch(e => alert(String(e)));
    setRunningId(null);
    load();
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Delete campaign and all results?")) return;
    await campaignsApi.delete(id).catch(e => alert(String(e)));
    load();
  };

  const isRunning = (c: Campaign) => c.status === "running" || c.status === "pending" || runningId === c.id;

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
                <label className="text-xs font-medium text-slate-600 mb-1 block">Max samples</label>
                <input type="number" value={form.max_samples} onChange={e => setForm(f => ({ ...f, max_samples: +e.target.value }))}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900" />
              </div>
              <div>
                <label className="text-xs font-medium text-slate-600 mb-1 block">Temperature</label>
                <input type="number" step="0.1" min="0" max="2" value={form.temperature} onChange={e => setForm(f => ({ ...f, temperature: +e.target.value }))}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900" />
              </div>
            </div>

            <div>
              <label className="text-xs font-medium text-slate-600 mb-2 block">
                Models * <span className="font-normal text-slate-400">({form.model_ids.length} selected)</span>
              </label>
              {models.length === 0 ? (
                <p className="text-xs text-slate-400">No models. <Link href="/models" className="text-blue-600 hover:underline">Add one →</Link></p>
              ) : (
                <div className="flex flex-wrap gap-2 max-h-40 overflow-y-auto">
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

            <div>
              <label className="text-xs font-medium text-slate-600 mb-2 block">
                Benchmarks * <span className="font-normal text-slate-400">({form.benchmark_ids.length} selected)</span>
              </label>
              {benches.length === 0 ? (
                <p className="text-xs text-slate-400">No benchmarks available.</p>
              ) : (
                <div className="flex flex-wrap gap-2 max-h-48 overflow-y-auto">
                  {benches.map(b => (
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
                className="bg-slate-900 text-white px-5 py-2 rounded-lg text-sm hover:bg-slate-700 transition-colors disabled:opacity-50 flex items-center gap-2">
                {saving && <Spinner size={13} />}
                {saving ? "Creating…" : "Create Campaign"}
              </button>
              <button type="button" onClick={() => setShowForm(false)} className="px-4 py-2 text-sm text-slate-600">Cancel</button>
            </div>
          </form>
        </div>
      )}

      <div className="p-8 pt-6 space-y-3">
        {loading ? (
          <div className="flex justify-center py-20"><Spinner size={24} /></div>
        ) : campaigns.length === 0 ? (
          <EmptyState icon="🚀" title="No campaigns yet" description="Create a campaign to start evaluating models." />
        ) : (
          campaigns.map(c => {
            const running = isRunning(c);
            return (
              <div key={c.id} className="bg-white border border-slate-200 rounded-xl p-5">
                <div className="flex items-start gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <span className="font-medium text-slate-900">{c.name}</span>
                      <StatusBadge status={c.status} />
                      {running && c.progress != null && (
                        <span className="text-xs text-slate-400">{c.progress.toFixed(0)}%</span>
                      )}
                    </div>
                    {c.description && <p className="text-xs text-slate-500 mb-2">{c.description}</p>}
                    <div className="flex gap-4 text-xs text-slate-400">
                      <span>{c.model_ids ? JSON.parse(c.model_ids).length : 0} model{JSON.parse(c.model_ids || "[]").length !== 1 ? "s" : ""}</span>
                      <span>{c.benchmark_ids ? JSON.parse(c.benchmark_ids).length : 0} benchmark{JSON.parse(c.benchmark_ids || "[]").length !== 1 ? "s" : ""}</span>
                      <span>seed {c.seed}</span>
                      {c.created_at && <span>{timeAgo(c.created_at)}</span>}
                    </div>

                    {/* Progress bar */}
                    {running && (
                      <div className="mt-3 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                        <div className="h-full bg-slate-900 rounded-full transition-all duration-500"
                          style={{ width: `${c.progress ?? 0}%` }} />
                      </div>
                    )}
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    {c.status === "completed" && (
                      <Link href={`/dashboard?campaign=${c.id}`}
                        className="flex items-center gap-1.5 text-xs px-3 py-1.5 border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600 transition-colors">
                        <BarChart2 size={13} /> Dashboard
                      </Link>
                    )}

                    {/* Run / Re-run button */}
                    {(c.status === "pending" || c.status === "failed" || c.status === "completed") && !running && (
                      <button onClick={() => handleRun(c.id)}
                        className="flex items-center gap-1.5 text-xs px-3 py-1.5 bg-slate-900 text-white rounded-lg hover:bg-slate-700 transition-colors">
                        {c.status === "completed" ? <RefreshCw size={13} /> : <Play size={13} />}
                        {c.status === "completed" ? "Re-run" : "Run"}
                      </button>
                    )}

                    {/* Running state */}
                    {running && (
                      <button onClick={() => handleCancel(c.id)}
                        className="flex items-center gap-1.5 text-xs px-3 py-1.5 bg-red-50 text-red-600 border border-red-200 rounded-lg hover:bg-red-100 transition-colors">
                        <Square size={13} /> Cancel
                      </button>
                    )}

                    {/* Spinner overlay when just clicked Run */}
                    {runningId === c.id && c.status !== "running" && (
                      <div className="flex items-center gap-1.5 text-xs text-slate-400">
                        <Spinner size={13} /> Starting…
                      </div>
                    )}

                    <button onClick={() => handleDelete(c.id)}
                      className="p-1.5 text-slate-300 hover:text-red-500 rounded-lg hover:bg-red-50 transition-colors">
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
