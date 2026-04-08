"use client";
import { useEffect, useState } from "react";
import { modelsApi } from "@/lib/api";
import type { LLMModel } from "@/lib/api";
import { Spinner } from "@/components/Spinner";
import { Check } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "https://llm-eval-backend-kqlh.onrender.com/api";

interface ModelSelectorProps {
  mode: "single" | "multi";
  selected: string[] | number[];  // model_ids (string for judge) or ids (number for campaign)
  onChange: (selected: any[]) => void;
  idType?: "model_id" | "db_id";  // "model_id" for judge/redbox, "db_id" for campaigns
  label?: string;
  maxHeight?: string;
}

export function ModelSelector({ mode, selected, onChange, idType = "db_id", label = "Select model", maxHeight = "max-h-64" }: ModelSelectorProps) {
  const [models, setModels] = useState<LLMModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"all" | "free" | "local">("all");
  const [search, setSearch] = useState("");
  const [pulling, setPulling] = useState<string | null>(null);
  const [ollamaSuggestions, setOllamaSuggestions] = useState<Record<string, string>>({});

  useEffect(() => {
    modelsApi.list().then(ms => { setModels(ms); setLoading(false); });
    fetch(`${API_BASE}/sync/ollama/suggestions`).then(r => r.json()).then(data => {
      if (data.suggestions) {
        const map: Record<string, string> = {};
        for (const s of data.suggestions) if (!s.already_installed) map[s.openrouter_id] = s.ollama_name;
        setOllamaSuggestions(map);
      }
    }).catch(() => {});
  }, []);

  const getId = (m: LLMModel) => idType === "model_id" ? ((m as any).model_id || m.name) : m.id;
  const isSelected = (m: LLMModel) => (selected as any[]).includes(getId(m));

  const toggle = (m: LLMModel) => {
    const id = getId(m);
    if (mode === "single") {
      onChange([id]);
    } else {
      onChange(isSelected(m) ? (selected as any[]).filter(x => x !== id) : [...selected, id]);
    }
  };

  const handlePullLocal = async (openrouterId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setPulling(openrouterId);
    try {
      await fetch(`${API_BASE}/sync/ollama/pull-and-register?openrouter_model_id=${encodeURIComponent(openrouterId)}`, { method: "POST" });
      const ms = await modelsApi.list();
      setModels(ms);
      setOllamaSuggestions(prev => { const n = {...prev}; delete n[openrouterId]; return n; });
    } catch {} finally { setPulling(null); }
  };

  const localCount = models.filter(m => (m as any).provider === "ollama").length;
  const freeCount = models.filter(m => (m as any).is_free).length;

  const filtered = models.filter(m => {
    if (filter === "free" && !(m as any).is_free) return false;
    if (filter === "local" && (m as any).provider !== "ollama") return false;
    if (search && !m.name.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  if (loading) return <div className="flex items-center gap-2 text-sm text-slate-400"><Spinner size={14} /> Loading models…</div>;

  return (
    <div>
      <label className="text-xs font-medium text-slate-600 mb-2 block">{label} {mode === "multi" && `(${(selected as any[]).length} selected)`}</label>

      {/* Search + filters */}
      <div className="flex items-center gap-2 mb-2">
        <input value={search} onChange={e => setSearch(e.target.value)}
          placeholder="Search…" className="flex-1 border border-slate-200 rounded-lg px-3 py-1.5 text-xs" />
        <div className="flex gap-1">
          <button onClick={() => setFilter("all")}
            className={`text-[10px] px-2 py-1 rounded-md border ${filter === "all" ? "bg-slate-900 text-white border-slate-900" : "border-slate-200 text-slate-500"}`}>
            All ({models.length})
          </button>
          <button onClick={() => setFilter("free")}
            className={`text-[10px] px-2 py-1 rounded-md border ${filter === "free" ? "bg-green-700 text-white border-green-700" : "border-slate-200 text-slate-500"}`}>
            Free ({freeCount})
          </button>
          {localCount > 0 && (
            <button onClick={() => setFilter("local")}
              className={`text-[10px] px-2 py-1 rounded-md border ${filter === "local" ? "bg-purple-700 text-white border-purple-700" : "border-purple-200 text-purple-500"}`}>
              🦙 ({localCount})
            </button>
          )}
        </div>
      </div>

      {/* Model grid */}
      <div className={`grid grid-cols-2 gap-1.5 ${maxHeight} overflow-y-auto`}>
        {filtered.map(m => {
          const sel = isSelected(m);
          const isLocal = (m as any).provider === "ollama";
          const orId = ((m as any).model_id || "").replace("openrouter/", "");
          const canPull = !isLocal && ollamaSuggestions[orId];

          return (
            <button key={m.id} type="button" onClick={() => toggle(m)}
              className={`flex items-center gap-2 p-2.5 rounded-lg border text-left transition-colors text-xs ${
                sel ? "border-slate-900 bg-slate-900 text-white" : isLocal ? "border-purple-200 bg-purple-50" : "border-slate-200 hover:border-slate-300"
              }`}>
              <div className={`w-4 h-4 rounded border-2 flex items-center justify-center shrink-0 ${sel ? "border-white bg-white" : "border-slate-300"}`}>
                {sel && <Check size={10} className="text-slate-900" />}
              </div>
              <div className="min-w-0 flex-1">
                <div className={`font-medium truncate ${sel ? "text-white" : "text-slate-800"}`}>{m.name}</div>
                <div className={sel ? "text-slate-300" : "text-slate-400"}>
                  {isLocal && <span className="font-bold text-purple-500 mr-1">🦙 LOCAL</span>}
                  {(m as any).is_free && !isLocal && <span className="font-bold text-green-500 mr-1">FREE</span>}
                  {(m as any).provider}
                </div>
              </div>
              {canPull && (
                <button onClick={(e) => handlePullLocal(orId, e)} disabled={pulling === orId}
                  className="shrink-0 text-[9px] px-1.5 py-0.5 rounded border border-purple-200 text-purple-600 hover:bg-purple-100 disabled:opacity-40">
                  {pulling === orId ? "⏳" : "🦙"} Local
                </button>
              )}
            </button>
          );
        })}
      </div>
      {filtered.length === 0 && <div className="text-xs text-slate-400 py-4 text-center">No models match.</div>}
    </div>
  );
}
