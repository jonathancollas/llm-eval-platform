"use client";
import { useEffect, useState, useCallback } from "react";
import { campaignsApi, modelsApi, benchmarksApi } from "@/lib/api";
import type { Campaign, LLMModel, Benchmark } from "@/lib/api";
import { PageHeader } from "@/components/PageHeader";
import { StatusBadge } from "@/components/StatusBadge";
import { EmptyState } from "@/components/EmptyState";
import { Spinner } from "@/components/Spinner";
import { timeAgo } from "@/lib/utils";
import { Plus, Play, Square, Trash2, BarChart2, RefreshCw, ChevronRight, ChevronLeft, Check } from "lucide-react";
import Link from "next/link";

type BenchmarkType = "academic" | "safety" | "coding" | "custom";
const BENCH_FILTERS = ["all", "academic", "safety", "coding", "custom", "inesia"] as const;

const BENCH_FILTER_LABELS: Record<string, string> = {
  all: "Tous", academic: "Académique", safety: "Safety",
  coding: "Code", custom: "Custom", inesia: "☿ INESIA",
};

function isBenchInFilter(b: Benchmark, f: string): boolean {
  if (f === "all") return true;
  if (f === "inesia") return b.tags?.some(t => ["INESIA","frontier","cyber","CBRN-E","agentique","méta-éval","français"].includes(t));
  return b.type === f;
}

// ── Wizard steps ─────────────────────────────────────────────────────────────
const STEPS = ["Paramètres", "Modèles", "Benchmarks", "Lancer"];

function StepIndicator({ current }: { current: number }) {
  return (
    <div className="flex items-center gap-2 mb-6">
      {STEPS.map((label, i) => (
        <div key={label} className="flex items-center gap-2">
          <div className={`flex items-center justify-center w-7 h-7 rounded-full text-xs font-medium transition-colors
            ${i < current ? "bg-green-500 text-white" : i === current ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-400"}`}>
            {i < current ? <Check size={12} /> : i + 1}
          </div>
          <span className={`text-sm ${i === current ? "font-medium text-slate-900" : "text-slate-400"}`}>{label}</span>
          {i < STEPS.length - 1 && <ChevronRight size={14} className="text-slate-200 mx-1" />}
        </div>
      ))}
    </div>
  );
}

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [models, setModels] = useState<LLMModel[]>([]);
  const [benches, setBenches] = useState<Benchmark[]>([]);
  const [loading, setLoading] = useState(true);
  const [showWizard, setShowWizard] = useState(false);
  const [step, setStep] = useState(0);
  const [saving, setSaving] = useState(false);
  const [runningId, setRunningId] = useState<number | null>(null);
  const [benchFilter, setBenchFilter] = useState("all");
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
        if (prev.some(c => c.status === "running" || c.status === "pending")) { load(); }
        return prev;
      });
    }, 3000);
    return () => clearInterval(interval);
  }, [load]);

  const toggleId = (arr: number[], id: number) =>
    arr.includes(id) ? arr.filter(x => x !== id) : [...arr, id];

  const resetWizard = () => {
    setStep(0);
    setForm({ name: "", description: "", model_ids: [], benchmark_ids: [], seed: 42, max_samples: 50, temperature: 0.0 });
    setShowWizard(false);
    setBenchFilter("all");
  };

  const handleCreate = async () => {
    setSaving(true);
    try {
      await campaignsApi.create({ ...form });
      resetWizard();
      load();
    } catch (err) { alert(String(err)); } finally { setSaving(false); }
  };

  const handleRun = async (id: number) => {
    setRunningId(id);
    try {
      await campaignsApi.run(id);
      load();
      const poll = setInterval(async () => {
        const updated = await campaignsApi.list();
        setCampaigns(updated);
        const c = updated.find((x: Campaign) => x.id === id);
        if (c && c.status !== "running") {
          clearInterval(poll);
          setRunningId(null);
        }
      }, 2000);
    } catch (e) {
      const msg = String(e);
      console.error("Run failed:", msg);
      alert(`Erreur au lancement: ${msg}`);
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

  const isRunning = (c: Campaign) => c.status === "running" || runningId === c.id;
  const filteredBenches = benches.filter(b => isBenchInFilter(b, benchFilter));

  const canNext = [
    form.name.trim().length > 0,
    form.model_ids.length > 0,
    form.benchmark_ids.length > 0,
    true,
  ][step];

  return (
    <div>
      <PageHeader
        title="Campaigns"
        description="Évaluations multi-modèles × multi-benchmarks."
        action={
          !showWizard && (
            <button onClick={() => setShowWizard(true)}
              className="flex items-center gap-2 bg-slate-900 text-white px-4 py-2 rounded-lg text-sm hover:bg-slate-700 transition-colors">
              <Plus size={14} /> Nouvelle campagne
            </button>
          )
        }
      />

      {/* ── WIZARD ────────────────────────────────────────────────────────── */}
      {showWizard && (
        <div className="mx-8 mt-6 bg-white border border-slate-200 rounded-2xl p-7">
          <StepIndicator current={step} />

          {/* Step 0 — Paramètres */}
          {step === 0 && (
            <div className="space-y-4 max-w-lg">
              <div>
                <label className="text-xs font-medium text-slate-600 mb-1 block">Nom de la campagne *</label>
                <input autoFocus required value={form.name}
                  onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                  placeholder="ex. MMLU comparison v1"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900" />
              </div>
              <div>
                <label className="text-xs font-medium text-slate-600 mb-1 block">Description</label>
                <input value={form.description}
                  onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900" />
              </div>
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="text-xs font-medium text-slate-600 mb-1 block">Max samples</label>
                  <input type="number" value={form.max_samples}
                    onChange={e => setForm(f => ({ ...f, max_samples: +e.target.value }))}
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900" />
                </div>
                <div>
                  <label className="text-xs font-medium text-slate-600 mb-1 block">Seed</label>
                  <input type="number" value={form.seed}
                    onChange={e => setForm(f => ({ ...f, seed: +e.target.value }))}
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900" />
                </div>
                <div>
                  <label className="text-xs font-medium text-slate-600 mb-1 block">Temperature</label>
                  <input type="number" step="0.1" min="0" max="2" value={form.temperature}
                    onChange={e => setForm(f => ({ ...f, temperature: +e.target.value }))}
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900" />
                </div>
              </div>
            </div>
          )}

          {/* Step 1 — Modèles */}
          {step === 1 && (
            <div>
              <div className="flex items-center justify-between mb-3">
                <p className="text-sm text-slate-600">Sélectionnez un ou plusieurs modèles à évaluer.</p>
                <span className="text-xs bg-slate-100 text-slate-600 px-2 py-1 rounded-full">
                  {form.model_ids.length} sélectionné{form.model_ids.length !== 1 ? "s" : ""}
                </span>
              </div>
              {models.length === 0 ? (
                <div className="py-10 text-center text-slate-400 text-sm">
                  Aucun modèle enregistré. <Link href="/models" className="text-blue-600 hover:underline">Ajouter →</Link>
                </div>
              ) : (
                <div className="grid grid-cols-2 gap-2 max-h-72 overflow-y-auto">
                  {models.map(m => {
                    const selected = form.model_ids.includes(m.id);
                    return (
                      <button key={m.id} type="button"
                        onClick={() => setForm(f => ({ ...f, model_ids: toggleId(f.model_ids, m.id) }))}
                        className={`flex items-center gap-3 p-3 rounded-xl border text-left transition-colors ${selected ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50"}`}>
                        <div className={`w-5 h-5 rounded-md border-2 flex items-center justify-center shrink-0 ${selected ? "border-white bg-white" : "border-slate-300"}`}>
                          {selected && <Check size={11} className="text-slate-900" />}
                        </div>
                        <div className="min-w-0">
                          <div className={`text-sm font-medium truncate ${selected ? "text-white" : "text-slate-900"}`}>{m.name}</div>
                          <div className={`text-xs truncate ${selected ? "text-slate-300" : "text-slate-400"}`}>{m.provider}</div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* Step 2 — Benchmarks */}
          {step === 2 && (
            <div>
              <div className="flex items-center justify-between mb-3">
                <div className="flex gap-1.5 flex-wrap">
                  {BENCH_FILTERS.map(f => (
                    <button key={f} onClick={() => setBenchFilter(f)}
                      className={`text-xs px-2.5 py-1 rounded-lg transition-colors ${benchFilter === f ? "bg-slate-900 text-white" : "border border-slate-200 text-slate-600 hover:bg-slate-50"}`}>
                      {BENCH_FILTER_LABELS[f]}
                      <span className="ml-1 opacity-50">{benches.filter(b => isBenchInFilter(b, f)).length}</span>
                    </button>
                  ))}
                </div>
                <span className="text-xs bg-slate-100 text-slate-600 px-2 py-1 rounded-full ml-3 shrink-0">
                  {form.benchmark_ids.length} sélectionné{form.benchmark_ids.length !== 1 ? "s" : ""}
                </span>
              </div>
              <div className="space-y-1.5 max-h-72 overflow-y-auto">
                {filteredBenches.length === 0 ? (
                  <div className="py-8 text-center text-slate-400 text-sm">Aucun benchmark dans cette catégorie.</div>
                ) : filteredBenches.map(b => {
                  const selected = form.benchmark_ids.includes(b.id);
                  return (
                    <button key={b.id} type="button"
                      onClick={() => setForm(f => ({ ...f, benchmark_ids: toggleId(f.benchmark_ids, b.id) }))}
                      className={`w-full flex items-center gap-3 p-3 rounded-xl border text-left transition-colors ${selected ? "border-slate-900 bg-slate-50" : "border-slate-100 bg-white hover:border-slate-200"}`}>
                      <div className={`w-5 h-5 rounded-md border-2 flex items-center justify-center shrink-0 ${selected ? "border-slate-900 bg-slate-900" : "border-slate-300"}`}>
                        {selected && <Check size={11} className="text-white" />}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-slate-900 truncate">{b.name}</div>
                        <div className="text-xs text-slate-400 truncate">{b.metric} · {b.num_samples ?? "all"} items</div>
                      </div>
                      <span className={`text-xs px-2 py-0.5 rounded-full shrink-0 ${b.type === "safety" ? "bg-red-50 text-red-600" : b.type === "academic" ? "bg-blue-50 text-blue-600" : "bg-slate-100 text-slate-500"}`}>
                        {b.type}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Step 3 — Review + Launch */}
          {step === 3 && (
            <div className="space-y-4 max-w-lg">
              <div className="bg-slate-50 rounded-xl p-5 space-y-3 text-sm">
                <div className="flex justify-between">
                  <span className="text-slate-500">Campagne</span>
                  <span className="font-medium text-slate-900">{form.name}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Modèles</span>
                  <span className="font-medium text-slate-900">{form.model_ids.length}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Benchmarks</span>
                  <span className="font-medium text-slate-900">{form.benchmark_ids.length}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Runs total</span>
                  <span className="font-medium text-slate-900">{form.model_ids.length * form.benchmark_ids.length}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Max samples / bench</span>
                  <span className="font-medium text-slate-900">{form.max_samples}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Temperature</span>
                  <span className="font-medium text-slate-900">{form.temperature}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Seed</span>
                  <span className="font-mono text-slate-900">{form.seed}</span>
                </div>
              </div>
              <div className="text-xs text-slate-400">
                La campagne sera créée en état <span className="font-mono">pending</span> — tu pourras la lancer depuis la liste.
              </div>
            </div>
          )}

          {/* Wizard nav */}
          <div className="flex items-center justify-between mt-6 pt-5 border-t border-slate-100">
            <button onClick={step === 0 ? resetWizard : () => setStep(s => s - 1)}
              className="flex items-center gap-1.5 text-sm text-slate-600 hover:text-slate-900 transition-colors">
              <ChevronLeft size={14} />
              {step === 0 ? "Annuler" : "Retour"}
            </button>
            {step < 3 ? (
              <button onClick={() => setStep(s => s + 1)} disabled={!canNext}
                className="flex items-center gap-1.5 bg-slate-900 text-white px-5 py-2 rounded-lg text-sm hover:bg-slate-700 disabled:opacity-40 transition-colors">
                Suivant <ChevronRight size={14} />
              </button>
            ) : (
              <button onClick={handleCreate} disabled={saving}
                className="flex items-center gap-2 bg-green-600 text-white px-5 py-2 rounded-lg text-sm hover:bg-green-700 disabled:opacity-50 transition-colors">
                {saving ? <Spinner size={13} /> : <Check size={14} />}
                {saving ? "Création…" : "Créer la campagne"}
              </button>
            )}
          </div>
        </div>
      )}

      {/* ── CAMPAIGN LIST ─────────────────────────────────────────────────── */}
      <div className="p-8 pt-6 space-y-3">
        {loading ? (
          <div className="flex justify-center py-20"><Spinner size={24} /></div>
        ) : campaigns.length === 0 ? (
          <EmptyState icon="🚀" title="Aucune campagne" description="Créez une campagne pour commencer à évaluer des modèles." />
        ) : (
          campaigns.map(c => {
            const running = isRunning(c);
            const modelCount = Array.isArray(c.model_ids) ? c.model_ids.length : JSON.parse(c.model_ids as any || "[]").length;
            const benchCount = Array.isArray(c.benchmark_ids) ? c.benchmark_ids.length : JSON.parse(c.benchmark_ids as any || "[]").length;
            return (
              <div key={c.id} className="bg-white border border-slate-200 rounded-xl p-5">
                <div className="flex items-start gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <span className="font-medium text-slate-900">{c.name}</span>
                      <StatusBadge status={c.status} />
                      {c.status === "running" && c.progress != null && (
                        <span className="text-xs text-slate-400">{c.progress.toFixed(0)}%</span>
                      )}
                    </div>
                    {c.description && <p className="text-xs text-slate-500 mb-2">{c.description}</p>}
                    <div className="flex gap-4 text-xs text-slate-400">
                      <span>{modelCount} modèle{modelCount !== 1 ? "s" : ""}</span>
                      <span>{benchCount} benchmark{benchCount !== 1 ? "s" : ""}</span>
                      <span>seed {c.seed}</span>
                      {c.created_at && <span>{timeAgo(c.created_at)}</span>}
                    </div>
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
                    {/* Run button — shown for pending and failed */}
                    {(c.status === "pending" || c.status === "failed") && !running && (
                      <button onClick={() => handleRun(c.id)}
                        className="flex items-center gap-1.5 text-xs px-3 py-1.5 bg-slate-900 text-white rounded-lg hover:bg-slate-700 transition-colors">
                        <Play size={13} /> Run
                      </button>
                    )}
                    {/* Re-run button — shown for completed */}
                    {c.status === "completed" && !running && (
                      <button onClick={() => handleRun(c.id)}
                        className="flex items-center gap-1.5 text-xs px-3 py-1.5 border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600 transition-colors">
                        <RefreshCw size={13} /> Re-run
                      </button>
                    )}
                    {/* Cancel button — only when actually running */}
                    {running && (
                      <button onClick={() => handleCancel(c.id)}
                        className="flex items-center gap-1.5 text-xs px-3 py-1.5 bg-red-50 text-red-600 border border-red-200 rounded-lg hover:bg-red-100 transition-colors">
                        <Square size={13} /> Cancel
                      </button>
                    )}
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
