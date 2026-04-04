"use client";
import { useState, useEffect, useCallback } from "react";
import { modelsApi } from "@/lib/api";
import { formatCost } from "@/lib/utils";
import { Badge } from "./Badge";
import { Spinner } from "./Spinner";
import { X, Plus, CheckCircle, Search } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "https://llm-eval-backend-kqlh.onrender.com/api";

interface CatalogModel {
  id: string; name: string; provider: string; context_length: number;
  cost_input_per_1k: number; cost_output_per_1k: number;
  is_free: boolean; is_open_source: boolean; description: string; tags: string[];
}

export function ModelCatalogModal({ onClose }: { onClose: () => void }) {
  const [models, setModels] = useState<CatalogModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [freeOnly, setFreeOnly] = useState(false);
  const [ossOnly, setOssOnly] = useState(false);
  const [added, setAdded] = useState<Set<string>>(new Set());
  const [adding, setAdding] = useState<string | null>(null);
  const [addingAll, setAddingAll] = useState(false);
  const [addAllProgress, setAddAllProgress] = useState<{ done: number; total: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams();
    if (search) params.set("search", search);
    if (freeOnly) params.set("free_only", "true");
    if (ossOnly) params.set("open_source_only", "true");
    fetch(`${API_BASE}/catalog/models?${params}`)
      .then(r => r.json())
      .then(setModels)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false));
  }, [search, freeOnly, ossOnly]);

  useEffect(() => { load(); }, [freeOnly, ossOnly]);

  const addOne = async (m: CatalogModel): Promise<boolean> => {
    try {
      await modelsApi.create({
        name: m.name,
        provider: "custom",
        model_id: m.id,
        endpoint: "https://openrouter.ai/api/v1",
        cost_input_per_1k: m.cost_input_per_1k,
        cost_output_per_1k: m.cost_output_per_1k,
        context_length: m.context_length,
        tags: m.tags,
        notes: `Via OpenRouter. ${m.description.slice(0, 100)}`,
      });
      return true;
    } catch {
      return false;
    }
  };

  const handleAdd = async (m: CatalogModel) => {
    setAdding(m.id);
    const ok = await addOne(m);
    if (ok) setAdded(prev => new Set([...prev, m.id]));
    setAdding(null);
  };

  const handleAddAll = async () => {
    const toAdd = models.filter(m => !added.has(m.id));
    if (!toAdd.length) return;
    setAddingAll(true);
    setAddAllProgress({ done: 0, total: toAdd.length });
    const newAdded = new Set(added);
    for (let i = 0; i < toAdd.length; i++) {
      const ok = await addOne(toAdd[i]);
      if (ok) newAdded.add(toAdd[i].id);
      setAddAllProgress({ done: i + 1, total: toAdd.length });
    }
    setAdded(newAdded);
    setAddingAll(false);
    setAddAllProgress(null);
  };

  const notAddedCount = models.filter(m => !added.has(m.id)).length;

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl w-full max-w-4xl max-h-[85vh] flex flex-col shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <div>
            <h2 className="font-semibold text-slate-900">Catalogue de modèles</h2>
            <p className="text-xs text-slate-400 mt-0.5">via OpenRouter · {models.length} modèles</p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-lg"><X size={16} /></button>
        </div>

        {/* Filters */}
        <div className="px-6 py-3 border-b border-slate-100 flex items-center gap-3 flex-wrap">
          <div className="relative flex-1 min-w-48">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input value={search} onChange={e => setSearch(e.target.value)}
              onKeyDown={e => e.key === "Enter" && load()}
              placeholder="Rechercher… (Entrée)"
              className="w-full pl-9 pr-4 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-900" />
          </div>
          <button onClick={() => setFreeOnly(!freeOnly)}
            className={`text-xs px-3 py-2 rounded-lg border transition-colors ${freeOnly ? "bg-emerald-50 border-emerald-200 text-emerald-700" : "border-slate-200 text-slate-600 hover:bg-slate-50"}`}>
            Gratuits
          </button>
          <button onClick={() => setOssOnly(!ossOnly)}
            className={`text-xs px-3 py-2 rounded-lg border transition-colors ${ossOnly ? "bg-violet-50 border-violet-200 text-violet-700" : "border-slate-200 text-slate-600 hover:bg-slate-50"}`}>
            Open source
          </button>
          {/* Add All button */}
          {!addingAll && notAddedCount > 0 && (
            <button onClick={handleAddAll}
              className="flex items-center gap-2 text-xs px-3 py-2 bg-slate-900 text-white rounded-lg hover:bg-slate-700 transition-colors">
              <Plus size={12} /> Tout ajouter ({notAddedCount})
            </button>
          )}
          {addingAll && addAllProgress && (
            <div className="flex items-center gap-2 text-xs text-slate-600 bg-slate-50 px-3 py-2 rounded-lg border border-slate-200">
              <Spinner size={12} />
              {addAllProgress.done}/{addAllProgress.total} ajoutés…
            </div>
          )}
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-2">
          {loading ? (
            <div className="flex justify-center py-16"><Spinner size={24} /></div>
          ) : error ? (
            <div className="text-center py-16 text-red-500 text-sm">
              Impossible de charger le catalogue.
              <br /><span className="text-xs text-slate-400">Vérifiez que OPENROUTER_API_KEY est configurée dans Render.</span>
            </div>
          ) : models.length === 0 ? (
            <div className="text-center py-16 text-slate-400 text-sm">Aucun modèle trouvé.</div>
          ) : (
            models.map(m => {
              const isAdded = added.has(m.id);
              const isAdding = adding === m.id;
              return (
                <div key={m.id} className="flex items-center gap-4 p-4 border border-slate-100 rounded-xl hover:border-slate-200 hover:bg-slate-50 transition-colors">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap mb-1">
                      <span className="font-medium text-slate-900 text-sm">{m.name}</span>
                      {m.is_free && <Badge className="bg-emerald-100 text-emerald-700">Gratuit</Badge>}
                      {m.is_open_source && <Badge className="bg-violet-100 text-violet-700">Open source</Badge>}
                      {m.tags.filter(t => t !== "gratuit" && t !== "open-source").slice(0, 2).map(t => (
                        <Badge key={t} className="bg-slate-100 text-slate-600">{t}</Badge>
                      ))}
                    </div>
                    <div className="text-xs font-mono text-slate-400">{m.id}</div>
                    {m.description && <p className="text-xs text-slate-500 mt-1 truncate">{m.description}</p>}
                  </div>
                  <div className="text-right text-xs text-slate-500 shrink-0 hidden md:block">
                    <div>{(m.context_length / 1000).toFixed(0)}k ctx</div>
                    {m.cost_input_per_1k > 0
                      ? <div className="text-slate-400">{formatCost(m.cost_input_per_1k)}/1k in</div>
                      : <div className="text-emerald-600">$0.00</div>}
                  </div>
                  <button onClick={() => !isAdded && !addingAll && handleAdd(m)}
                    disabled={isAdding || isAdded || addingAll}
                    className={`shrink-0 flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-colors ${
                      isAdded ? "bg-green-50 text-green-600 border border-green-200"
                      : "bg-slate-900 text-white hover:bg-slate-700 disabled:opacity-40"}`}>
                    {isAdding ? <Spinner size={12} /> : isAdded ? <CheckCircle size={12} /> : <Plus size={12} />}
                    {isAdded ? "Ajouté" : "Ajouter"}
                  </button>
                </div>
              );
            })
          )}
        </div>

        <div className="px-6 py-3 border-t border-slate-100 text-xs text-slate-400 flex items-center justify-between">
          <span>{added.size} modèle{added.size !== 1 ? "s" : ""} ajouté{added.size !== 1 ? "s" : ""} cette session</span>
          <span>Données via <a href="https://openrouter.ai" target="_blank" className="text-blue-500 hover:underline">OpenRouter</a></span>
        </div>
      </div>
    </div>
  );
}
