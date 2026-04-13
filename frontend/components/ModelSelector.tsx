"use client";
import { useEffect, useState, useCallback } from "react";
import { modelsApi } from "@/lib/api";
import type { LLMModelSlim } from "@/lib/api";
import { Spinner } from "@/components/Spinner";
import { Check, Download, CheckCircle2 } from "lucide-react";

import { API_BASE } from "@/lib/config";

type ModelIdType = "model_id" | "db_id";
type SelectedFor<T extends ModelIdType> = T extends "model_id" ? string[] : number[];

interface ModelSelectorBaseProps {
  mode: "single" | "multi";
  label?: string;
  maxHeight?: string;
}

type ModelSelectorProps<T extends ModelIdType = "db_id"> = ModelSelectorBaseProps & {
  selected: SelectedFor<T>;
  onChange: (selected: SelectedFor<T>) => void;
  idType: T;
};

export function ModelSelector<T extends ModelIdType = "db_id">({ mode, selected, onChange, idType, label = "Select model", maxHeight = "max-h-64" }: ModelSelectorProps<T>) {
  const [models, setModels] = useState<LLMModelSlim[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"all" | "free" | "local" | "open">("all");
  const [search, setSearch] = useState("");
  const [pulling, setPulling] = useState<number | null>(null);
  const [pullStatus, setPullStatus] = useState<Record<number, "pulling" | "done" | "error">>({});
  const [ollamaSuggestions, setOllamaSuggestions] = useState<Record<string, string>>({});

  const loadModels = useCallback(() => {
    modelsApi.list().then(ms => { setModels(ms); setLoading(false); });
  }, []);

  // Known OpenRouter → Ollama mappings (client-side fallback)
  const KNOWN_OLLAMA: Record<string, string> = {
    "meta-llama/llama-3.3-70b-instruct": "llama3.3:70b",
    "meta-llama/llama-3.2-3b-instruct": "llama3.2:3b",
    "meta-llama/llama-3.2-1b-instruct": "llama3.2:1b",
    "meta-llama/llama-3.1-8b-instruct": "llama3.1:8b",
    "meta-llama/llama-3.1-70b-instruct": "llama3.1:70b",
    "google/gemma-3-27b-it": "gemma3:27b",
    "google/gemma-3-12b-it": "gemma3:12b",
    "google/gemma-2-9b-it": "gemma2:9b",
    "google/gemma-2-27b-it": "gemma2:27b",
    "mistralai/mistral-7b-instruct": "mistral:7b",
    "mistralai/mixtral-8x7b-instruct": "mixtral:8x7b",
    "mistralai/mistral-small-24b-instruct-2501": "mistral-small:24b",
    "qwen/qwen-2.5-7b-instruct": "qwen2.5:7b",
    "qwen/qwen-2.5-14b-instruct": "qwen2.5:14b",
    "qwen/qwen-2.5-32b-instruct": "qwen2.5:32b",
    "qwen/qwen-2.5-72b-instruct": "qwen2.5:72b",
    "deepseek/deepseek-r1-distill-qwen-7b": "deepseek-r1:7b",
    "deepseek/deepseek-r1-distill-qwen-14b": "deepseek-r1:14b",
    "microsoft/phi-3-mini-128k-instruct": "phi3:mini",
    "microsoft/phi-3-medium-128k-instruct": "phi3:medium",
  };
  // Also match :free variants
  const KNOWN_OLLAMA_FULL: Record<string, string> = {};
  for (const [k, v] of Object.entries(KNOWN_OLLAMA)) {
    KNOWN_OLLAMA_FULL[k] = v;
    KNOWN_OLLAMA_FULL[k + ":free"] = v;
  }

  useEffect(() => {
    loadModels();
    // Try server-side suggestions first, fallback to client-side map
    fetch(`${API_BASE}/sync/ollama/suggestions`).then(r => r.json()).then(data => {
      if (data.suggestions && data.suggestions.length > 0) {
        const map: Record<string, string> = {};
        for (const s of data.suggestions) if (!s.already_installed) map[s.openrouter_id] = s.ollama_name;
        setOllamaSuggestions(map);
      } else {
        // Fallback: use client-side mappings
        setOllamaSuggestions(KNOWN_OLLAMA_FULL);
      }
    }).catch(() => {
      // Ollama not running — use client-side mappings anyway
      setOllamaSuggestions(KNOWN_OLLAMA_FULL);
    });
  }, [loadModels]);

  const getId = (m: LLMModelSlim): SelectedFor<T>[number] =>
    (idType === "model_id" ? ((m as any).model_id || m.name) : m.id) as SelectedFor<T>[number];
  const selectedValues = selected as Array<SelectedFor<T>[number]>;
  const isSelected = (m: LLMModelSlim) => selectedValues.includes(getId(m));

  const toggle = (m: LLMModelSlim) => {
    const id = getId(m);
    if (mode === "single") onChange([id] as SelectedFor<T>);
    else onChange((isSelected(m) ? selectedValues.filter(x => x !== id) : [...selectedValues, id]) as SelectedFor<T>);
  };

  const handleDownload = async (model: LLMModelSlim, e: React.MouseEvent) => {
    e.stopPropagation();
    const orId = ((model as any).model_id || "").replace("openrouter/", "").replace(":free", "");
    const ollamaName = ollamaSuggestions[orId] || ollamaSuggestions[orId + ":free"];
    setPulling(model.id);
    setPullStatus(prev => ({ ...prev, [model.id]: "pulling" }));

    try {
      if (ollamaName) {
        // Backend has a known mapping — use pull-and-register
        const res = await fetch(`${API_BASE}/sync/ollama/pull-and-register?openrouter_model_id=${encodeURIComponent(orId)}`, { method: "POST" });
        const data = await res.json();
        if (data.status === "ok" || data.status === "pulled") {
          setPullStatus(prev => ({ ...prev, [model.id]: "done" }));
          setTimeout(() => loadModels(), 1500);
        } else {
          setPullStatus(prev => ({ ...prev, [model.id]: "error" }));
        }
      } else {
        // No backend mapping — attempt direct Ollama pull using model name heuristic
        const guessedName = orId.split("/").pop()?.replace(/-instruct.*/, "").replace(/-it$/, "") ?? orId;
        const ollamaRes = await fetch(`${API_BASE}/sync/ollama/pull`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ model_name: guessedName }),
        });
        const data = await ollamaRes.json();
        if (data.status === "pulled" || data.status === "pulling") {
          setPullStatus(prev => ({ ...prev, [model.id]: "done" }));
          setTimeout(() => loadModels(), 1500);
        } else {
          setPullStatus(prev => ({ ...prev, [model.id]: "error" }));
        }
      }
    } catch {
      setPullStatus(prev => ({ ...prev, [model.id]: "error" }));
    } finally {
      setPulling(null);
    }
  };

  const localCount = models.filter(m => (m as any).provider === "ollama").length;
  const freeCount = models.filter(m => (m as any).is_free).length;
  const openWeightCount = models.filter(m => (m as any).is_open_weight).length;

  const filtered = models.filter(m => {
    if (filter === "free" && !(m as any).is_free) return false;
    if (filter === "local" && (m as any).provider !== "ollama") return false;
    if (filter === "open" && !(m as any).is_open_weight) return false;
    if (search && !m.name.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  if (loading) return <div className="flex items-center gap-2 text-sm text-slate-400"><Spinner size={14} /> Loading models…</div>;

  return (
    <div>
      <label className="text-xs font-medium text-slate-600 mb-2 block">{label} {mode === "multi" && `(${selected.length} selected)`}</label>

      <div className="flex items-center gap-2 mb-2">
        <input value={search} onChange={e => setSearch(e.target.value)}
          placeholder="Search…" className="flex-1 border border-slate-200 rounded-lg px-3 py-1.5 text-xs" />
        <div className="flex gap-1">
          {[
            { key: "all" as const, label: `All (${models.length})`, cls: "bg-slate-900 text-white border-slate-900" },
            { key: "free" as const, label: `Free (${freeCount})`, cls: "bg-green-700 text-white border-green-700" },
            ...(openWeightCount > 0 ? [{ key: "open" as const, label: `Open (${openWeightCount})`, cls: "bg-orange-600 text-white border-orange-600" }] : []),
            ...(localCount > 0 ? [{ key: "local" as const, label: `🦙 (${localCount})`, cls: "bg-purple-700 text-white border-purple-700" }] : []),
          ].map(f => (
            <button key={f.key} onClick={() => setFilter(f.key)}
              className={`text-[10px] px-2 py-1 rounded-md border ${filter === f.key ? f.cls : "border-slate-200 text-slate-500"}`}>
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <div className={`grid grid-cols-1 gap-1.5 ${maxHeight} overflow-y-auto`}>
        {filtered.map(m => {
          const sel = isSelected(m);
          const isLocal = (m as any).provider === "ollama";
          const orId = ((m as any).model_id || "").replace("openrouter/", "").replace(":free", "");
          // Show Download for all open-weight models — Ollama name from suggestions or derive from model_id
          const ollamaName = ollamaSuggestions[orId] || ollamaSuggestions[orId + ":free"];
          const canDownload = !isLocal && ((m as any).is_open_weight || !!ollamaName);
          const downloadTarget = ollamaName || orId.split("/").pop()?.replace(/-instruct.*/, "").replace(/-it$/, "");
          const status = pullStatus[m.id];

          return (
            <div key={m.id} className={`flex items-center gap-2 p-2 rounded-lg border transition-colors ${
              sel ? "border-slate-900 bg-slate-900 text-white" : isLocal ? "border-purple-200 bg-purple-50" : "border-slate-200 hover:border-slate-300"
            }`}>
              {/* Checkbox + model info (clickable) */}
              <button type="button" onClick={() => toggle(m)} className="flex items-center gap-2 flex-1 min-w-0 text-left">
                <div className={`w-4 h-4 rounded border-2 flex items-center justify-center shrink-0 ${sel ? "border-white bg-white" : "border-slate-300"}`}>
                  {sel && <Check size={10} className="text-slate-900" />}
                </div>
                <div className="min-w-0 flex-1">
                  <div className={`text-xs font-medium truncate ${sel ? "text-white" : "text-slate-800"}`}>{m.name}</div>
                  <div className={`text-[10px] ${sel ? "text-slate-300" : "text-slate-400"}`}>
                    {isLocal && <span className="font-bold text-purple-500 mr-1">🦙 LOCAL</span>}
                    {(m as any).is_open_weight && !isLocal && <span className="font-bold text-orange-500 mr-1">OPEN</span>}
                    {(m as any).is_free && !isLocal && <span className="font-bold text-green-500 mr-1">FREE</span>}
                    {(m as any).provider}
                  </div>
                </div>
              </button>

              {/* Download button — visible for all open-weight models (#67) */}
              {canDownload && !status && (
                <button onClick={(e) => handleDownload(m, e)} disabled={pulling === m.id}
                  title={`Run locally via Ollama: ${downloadTarget}`}
                  className="shrink-0 flex items-center gap-1 text-[10px] px-2.5 py-1.5 rounded-md bg-purple-600 text-white hover:bg-purple-700 disabled:opacity-40 transition-colors font-medium">
                  <Download size={11} /> Run locally
                </button>
              )}
              {status === "pulling" && (
                <div className="shrink-0 flex items-center gap-1 text-[10px] px-2.5 py-1.5 rounded-md bg-purple-100 text-purple-600">
                  <Spinner size={10} /> Downloading…
                </div>
              )}
              {status === "done" && (
                <div className="shrink-0 flex items-center gap-1 text-[10px] px-2.5 py-1.5 rounded-md bg-green-100 text-green-700 font-medium">
                  <CheckCircle2 size={11} /> Ready
                </div>
              )}
              {status === "error" && (
                <div className="shrink-0 text-[10px] px-2.5 py-1.5 rounded-md bg-red-100 text-red-600">
                  Failed — is Ollama running?
                </div>
              )}
            </div>
          );
        })}
      </div>
      {filtered.length === 0 && <div className="text-xs text-slate-400 py-4 text-center">No models match.</div>}
    </div>
  );
}
