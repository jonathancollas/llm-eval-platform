"use client";
import { useEffect, useState, useCallback, useMemo } from "react";
import { modelsApi } from "@/lib/api";
import type { LLMModel, ModelProvider } from "@/lib/api";
import { useModels } from "@/lib/useApi";
import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/Badge";
import { EmptyState } from "@/components/EmptyState";
import { Spinner } from "@/components/Spinner";
import { ModelCatalogModal } from "@/components/ModelCatalogModal";
import { providerColor } from "@/lib/utils";
import { Plus, Zap, Eye, Wrench, Brain, CheckCircle2, XCircle,
         ChevronDown, ChevronUp, Trash2, Search, ExternalLink, Shield } from "lucide-react";

const PROVIDERS: ModelProvider[] = ["openai", "anthropic", "mistral", "groq", "ollama", "custom"];
const PROVIDER_LABELS: Record<string, string> = {
  openai: "OpenAI", anthropic: "Anthropic", mistral: "Mistral",
  groq: "Groq", ollama: "Ollama (local)", custom: "Custom / OpenRouter",
};

// ── Filter bar ─────────────────────────────────────────────────────────────────
interface Filters {
  search: string;
  onlyFree: boolean;
  onlyVision: boolean;
  onlyTools: boolean;
  onlyReasoning: boolean;
  provider: string;
}

function applyFilters(models: LLMModel[], f: Filters): LLMModel[] {
  return models.filter(m => {
    if (f.search) {
      const q = f.search.toLowerCase();
      if (!m.name.toLowerCase().includes(q) && !m.model_id.toLowerCase().includes(q)) return false;
    }
    if (f.onlyFree && !m.is_free) return false;
    if (f.onlyVision && !m.supports_vision) return false;
    if (f.onlyTools && !m.supports_tools) return false;
    if (f.onlyReasoning && !m.supports_reasoning) return false;
    if (f.provider && m.provider !== f.provider) return false;
    return true;
  });
}

function FilterChip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick}
      className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${
        active ? "bg-slate-900 text-white border-slate-900" : "border-slate-200 text-slate-600 hover:bg-slate-50"
      }`}>
      {label}
    </button>
  );
}

// ── Model detail panel ─────────────────────────────────────────────────────────
function ModelDetail({ m }: { m: LLMModel }) {
  const createdDate = m.model_created_at
    ? new Date(m.model_created_at * 1000).toLocaleDateString("en-US", { year: "numeric", month: "short" })
    : null;

  return (
    <div className="border-t border-slate-100 px-5 py-4 bg-slate-50 text-xs text-slate-600 space-y-3">
      {/* Costs */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-white rounded-lg p-2.5 border border-slate-100">
          <div className="text-slate-400 mb-0.5">Input</div>
          <div className="font-medium text-slate-800">
            {m.is_free ? "🆓 Gratuit" : `$${m.cost_input_per_1k.toFixed(4)}/1k`}
          </div>
        </div>
        <div className="bg-white rounded-lg p-2.5 border border-slate-100">
          <div className="text-slate-400 mb-0.5">Output</div>
          <div className="font-medium text-slate-800">
            {m.is_free ? "🆓 Gratuit" : `$${m.cost_output_per_1k.toFixed(4)}/1k`}
          </div>
        </div>
        <div className="bg-white rounded-lg p-2.5 border border-slate-100">
          <div className="text-slate-400 mb-0.5">Contexte</div>
          <div className="font-medium text-slate-800">{(m.context_length / 1000).toFixed(0)}k tokens</div>
        </div>
      </div>

      {/* Capabilities */}
      <div className="flex flex-wrap gap-1.5">
        {m.supports_vision    && <Badge className="bg-purple-50 text-purple-700 border border-purple-100"><Eye size={10} className="inline mr-1" />Vision</Badge>}
        {m.supports_tools     && <Badge className="bg-blue-50 text-blue-700 border border-blue-100"><Wrench size={10} className="inline mr-1" />Function Calling</Badge>}
        {m.supports_reasoning && <Badge className="bg-amber-50 text-amber-700 border border-amber-100"><Brain size={10} className="inline mr-1" />Reasoning</Badge>}
        {m.is_moderated       && <Badge className="bg-red-50 text-red-600 border border-red-100"><Shield size={10} className="inline mr-1" />Moderate</Badge>}
        {m.max_output_tokens > 0 && <Badge className="bg-slate-100 text-slate-600">Max output: {(m.max_output_tokens / 1000).toFixed(0)}k</Badge>}
      </div>

      {/* Technical details */}
      <div className="grid grid-cols-2 gap-x-6 gap-y-1">
        {m.tokenizer      && <div><span className="text-slate-400">Tokenizer:</span> <span className="font-mono">{m.tokenizer}</span></div>}
        {m.instruct_type  && <div><span className="text-slate-400">Format:</span> <span className="font-mono">{m.instruct_type}</span></div>}
        {createdDate      && <div><span className="text-slate-400">Sortie:</span> {createdDate}</div>}
        {m.endpoint && !m.endpoint.includes("openrouter.ai") && <div className="col-span-2"><span className="text-slate-400">Endpoint:</span> <span className="font-mono text-xs">{m.endpoint}</span></div>}
      </div>

      {/* Tags */}
      {m.tags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {m.tags.map(t => <Badge key={t} className="bg-white border border-slate-200 text-slate-500">{t}</Badge>)}
        </div>
      )}

      {/* Notes */}
      {m.notes && !m.notes.startsWith("Via OpenRouter") && (
        <p className="text-slate-500 italic">{m.notes}</p>
      )}

      {/* Links */}
      <div className="flex gap-3 pt-1">
        {m.hugging_face_id && (
          <a href={`https://huggingface.co/${m.hugging_face_id}`} target="_blank" rel="noopener noreferrer"
            className="flex items-center gap-1 text-xs text-blue-600 hover:underline">
            <ExternalLink size={11} /> HuggingFace
          </a>
        )}
        <a href={`https://openrouter.ai/models/${m.model_id}`} target="_blank" rel="noopener noreferrer"
          className="flex items-center gap-1 text-xs text-blue-600 hover:underline">
          <ExternalLink size={11} /> OpenRouter
        </a>
      </div>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────
export default function ModelsPage() {
  const [models, setModels] = useState<LLMModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [showCatalog, setShowCatalog] = useState(false);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [testing, setTesting] = useState<number | null>(null);
  const [testResults, setTestResults] = useState<Record<number, any>>({});
  const [creating, setCreating] = useState(false);
  const [filters, setFilters] = useState<Filters>({
    search: "", onlyFree: false, onlyVision: false,
    onlyTools: false, onlyReasoning: false, provider: "",
  });
  const [form, setForm] = useState({
    name: "", provider: "custom" as ModelProvider, model_id: "",
    endpoint: "", api_key: "", context_length: 4096,
    cost_input_per_1k: 0, cost_output_per_1k: 0, notes: "",
  });
  const [ollamaStatus, setOllamaStatus] = useState<{ available: boolean; total: number } | null>(null);
  const [importingOllama, setImportingOllama] = useState(false);

  // SWR — cached, deduped, auto-refresh
  const { models: swrModels, isLoading: swrLoading, refresh: refreshModels } = useModels();
  useEffect(() => { setModels(swrModels); if (!swrLoading) setLoading(false); }, [swrModels, swrLoading]);
  const load = useCallback(() => { refreshModels(); }, [refreshModels]);

  // Check Ollama on mount
  useEffect(() => {
    import("@/lib/api").then(({ ollamaApi }) => {
      ollamaApi.check().then(setOllamaStatus).catch(() => {});
    });
  }, []);

  const handleImportOllama = async () => {
    setImportingOllama(true);
    try {
      const { ollamaApi } = await import("@/lib/api");
      const result = await ollamaApi.import();
      if (result.added > 0) load();
      alert(result.available ? `${result.added} model(s) Ollama importé(s)` : "Ollama non disponible");
    } catch (e: any) { alert(String(e)); }
    finally { setImportingOllama(false); };
  };

  const filtered = useMemo(() => applyFilters(models, filters), [models, filters]);

  const freeCount       = useMemo(() => models.filter(m => m.is_free).length, [models]);
  const visionCount     = useMemo(() => models.filter(m => m.supports_vision).length, [models]);
  const toolsCount      = useMemo(() => models.filter(m => m.supports_tools).length, [models]);
  const reasoningCount  = useMemo(() => models.filter(m => m.supports_reasoning).length, [models]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);
    try {
      await modelsApi.create({
        name: form.name, provider: form.provider, model_id: form.model_id,
        endpoint: form.endpoint || undefined, api_key: form.api_key || undefined,
        context_length: form.context_length,
        cost_input_per_1k: form.cost_input_per_1k,
        cost_output_per_1k: form.cost_output_per_1k,
        notes: form.notes,
      });
      setForm({ name: "", provider: "custom" as ModelProvider, model_id: "", endpoint: "", api_key: "", context_length: 4096, cost_input_per_1k: 0, cost_output_per_1k: 0, notes: "" });
      setShowForm(false);
      load();
    } catch (err) { alert(String(err)); } finally { setCreating(false); }
  };

  const handleTest = async (id: number) => {
    setTesting(id);
    try {
      const result = await modelsApi.test(id);
      setTestResults(prev => ({ ...prev, [id]: result }));
    } catch (e) {
      setTestResults(prev => ({ ...prev, [id]: { ok: false, latency_ms: 0, response: "", error: String(e) } }));
    } finally { setTesting(null); }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Delete ce model ?")) return;
    await modelsApi.delete(id).catch(e => alert(String(e)));
    load();
  };

  const setFilter = (key: keyof Filters, value: any) =>
    setFilters(f => ({ ...f, [key]: value }));

  return (
    <div>
      <PageHeader
        title="Model Registry"
        description={`${models.length} models · ${freeCount} gratuits`}
        action={
          <div className="flex gap-2">
            {ollamaStatus?.available && (
              <button onClick={handleImportOllama} disabled={importingOllama}
                className="flex items-center gap-2 border border-purple-200 px-4 py-2 rounded-lg text-sm hover:bg-purple-50 text-purple-700 transition-colors disabled:opacity-50">
                {importingOllama ? <Spinner size={13} /> : "🦙"} Ollama ({ollamaStatus.total})
              </button>
            )}
            <button onClick={() => setShowCatalog(true)}
              className="flex items-center gap-2 border border-slate-200 px-4 py-2 rounded-lg text-sm hover:bg-slate-50 text-slate-700 transition-colors">
              🔍 Catalogue OpenRouter
            </button>
            <button onClick={() => setShowForm(!showForm)}
              className="flex items-center gap-2 bg-slate-900 text-white px-4 py-2 rounded-lg text-sm hover:bg-slate-700 transition-colors">
              <Plus size={14} /> Ajouter
            </button>
          </div>
        }
      />

      {/* ── Filter bar ────────────────────────────────────────────────────── */}
      <div className="px-8 pt-4 pb-2 space-y-3">
        {/* Search */}
        <div className="relative max-w-sm">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input value={filters.search}
            onChange={e => setFilter("search", e.target.value)}
            placeholder="Search by name or model ID…"
            className="w-full pl-9 pr-4 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-900" />
        </div>

        {/* Filter chips */}
        <div className="flex gap-2 flex-wrap">
          <FilterChip label={`🆓 Gratuit (${freeCount})`}      active={filters.onlyFree}      onClick={() => setFilter("onlyFree", !filters.onlyFree)} />
          <FilterChip label={`👁 Vision (${visionCount})`}     active={filters.onlyVision}    onClick={() => setFilter("onlyVision", !filters.onlyVision)} />
          <FilterChip label={`🔧 Tools (${toolsCount})`}       active={filters.onlyTools}     onClick={() => setFilter("onlyTools", !filters.onlyTools)} />
          <FilterChip label={`🧠 Reasoning (${reasoningCount})`} active={filters.onlyReasoning} onClick={() => setFilter("onlyReasoning", !filters.onlyReasoning)} />
          {(filters.onlyFree || filters.onlyVision || filters.onlyTools || filters.onlyReasoning || filters.search || filters.provider) && (
            <button onClick={() => setFilters({ search: "", onlyFree: false, onlyVision: false, onlyTools: false, onlyReasoning: false, provider: "" })}
              className="text-xs px-3 py-1.5 text-slate-400 hover:text-slate-700">
              Réinitialiser
            </button>
          )}
          <span className="text-xs text-slate-400 self-center ml-auto">
            {filtered.length} / {models.length} models
          </span>
        </div>
      </div>

      {showForm && (
        <div className="mx-8 mt-4 bg-white border border-slate-200 rounded-xl p-6">
          <h3 className="font-medium text-slate-900 mb-4">Nouveau model</h3>
          <form onSubmit={handleCreate} className="grid grid-cols-2 gap-4">
            {[
              { label: "Nom *", key: "name", type: "text", placeholder: "ex. GPT-4o Mini" },
              { label: "Model ID *", key: "model_id", type: "text", placeholder: "ex. gpt-4o-mini" },
              { label: "Endpoint", key: "endpoint", type: "text", placeholder: "https://openrouter.ai/api/v1" },
              { label: "API Key", key: "api_key", type: "password", placeholder: "sk-..." },
            ].map(({ label, key, type, placeholder }) => (
              <div key={key}>
                <label className="text-xs font-medium text-slate-600 mb-1 block">{label}</label>
                <input type={type} required={label.includes("*")} value={(form as any)[key]} placeholder={placeholder}
                  onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900" />
              </div>
            ))}
            <div>
              <label className="text-xs font-medium text-slate-600 mb-1 block">Provider</label>
              <select value={form.provider} onChange={e => setForm(f => ({ ...f, provider: e.target.value as ModelProvider }))}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900">
                {PROVIDERS.map(p => <option key={p} value={p}>{PROVIDER_LABELS[p]}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-slate-600 mb-1 block">Context length</label>
              <input type="number" value={form.context_length}
                onChange={e => setForm(f => ({ ...f, context_length: +e.target.value }))}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900" />
            </div>
            <div className="col-span-2 flex gap-3 pt-1">
              <button type="submit" disabled={creating}
                className="bg-slate-900 text-white px-4 py-2 rounded-lg text-sm hover:bg-slate-700 transition-colors disabled:opacity-50">
                {creating ? "Creating…" : "Ajouter"}
              </button>
              <button type="button" onClick={() => setShowForm(false)} className="px-4 py-2 text-sm text-slate-600">Cancel</button>
            </div>
          </form>
        </div>
      )}

      {/* ── Model list ────────────────────────────────────────────────────── */}
      <div className="p-8 pt-4 space-y-2">
        {loading ? (
          <div className="flex justify-center py-20"><Spinner size={24} /></div>
        ) : filtered.length === 0 ? (
          <EmptyState icon="🤖" title={models.length === 0 ? "No models" : "No results"}
            description={models.length === 0 ? "Add models from the OpenRouter catalog." : "Adjust your filters."} />
        ) : (
          filtered.map(m => {
            const test = testResults[m.id];
            const isExpanded = expanded === m.id;
            return (
              <div key={m.id} className="bg-white border border-slate-200 rounded-xl overflow-hidden">
                <div className="flex items-center gap-4 px-5 py-4 cursor-pointer hover:bg-slate-50 transition-colors"
                  onClick={() => setExpanded(isExpanded ? null : m.id)}>

                  {/* Free badge */}
                  {m.is_free && (
                    <span className="text-xs font-bold text-green-600 bg-green-50 border border-green-200 px-2 py-0.5 rounded-full shrink-0">
                      FREE
                    </span>
                  )}

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5 flex-wrap">
                      <span className="font-medium text-slate-900">{m.name}</span>
                      <Badge className={providerColor(m.provider)}>{m.provider}</Badge>
                      {m.supports_vision    && <Badge className="bg-purple-50 text-purple-600 border border-purple-100"><Eye size={9} className="inline mr-0.5" />Vision</Badge>}
                      {m.supports_tools     && <Badge className="bg-blue-50 text-blue-600 border border-blue-100"><Wrench size={9} className="inline mr-0.5" />Tools</Badge>}
                      {m.supports_reasoning && <Badge className="bg-amber-50 text-amber-600 border border-amber-100"><Brain size={9} className="inline mr-0.5" />Reasoning</Badge>}
                    </div>
                    <div className="flex gap-3 text-xs text-slate-400">
                      <span className="font-mono truncate max-w-48">{m.model_id}</span>
                      <span>{(m.context_length / 1000).toFixed(0)}k ctx</span>
                      {!m.is_free && m.cost_input_per_1k > 0 && <span>${m.cost_input_per_1k.toFixed(4)}/1k</span>}
                      {m.has_api_key && <span className="text-green-500">🔑</span>}
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    {test && (
                      <div className="flex items-center gap-1.5 text-xs">
                        {test.ok
                          ? <><CheckCircle2 size={13} className="text-green-500" /><span className="text-green-600">{test.latency_ms}ms</span></>
                          : <><XCircle size={13} className="text-red-500" /><span className="text-red-500 max-w-32 truncate text-xs">{test.error}</span></>
                        }
                      </div>
                    )}
                    <button onClick={e => { e.stopPropagation(); handleTest(m.id); }} disabled={testing === m.id}
                      className="flex items-center gap-1 text-xs px-2.5 py-1.5 border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600 transition-colors disabled:opacity-50">
                      {testing === m.id ? <Spinner size={11} /> : <Zap size={11} />}
                      {testing === m.id ? "…" : "Test"}
                    </button>
                    <button onClick={e => { e.stopPropagation(); handleDelete(m.id); }}
                      className="p-1.5 text-slate-300 hover:text-red-500 rounded-lg hover:bg-red-50 transition-colors">
                      <Trash2 size={13} />
                    </button>
                    {isExpanded ? <ChevronUp size={14} className="text-slate-400" /> : <ChevronDown size={14} className="text-slate-400" />}
                  </div>
                </div>

                {isExpanded && <ModelDetail m={m} />}
              </div>
            );
          })
        )}
      </div>

      {showCatalog && <ModelCatalogModal onClose={() => { setShowCatalog(false); load(); }} />}
    </div>
  );
}
