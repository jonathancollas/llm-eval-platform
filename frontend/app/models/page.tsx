"use client";
import { useEffect, useState, useCallback } from "react";
import { modelsApi } from "@/lib/api";
import type { LLMModel, ModelProvider } from "@/lib/api";
import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/Badge";
import { EmptyState } from "@/components/EmptyState";
import { Spinner } from "@/components/Spinner";
import { ModelCatalogModal } from "@/components/ModelCatalogModal";
import { providerColor } from "@/lib/utils";
import { Plus, Zap, Eye, Wrench, Brain, CheckCircle2, XCircle, ChevronDown, ChevronUp, Trash2 } from "lucide-react";

const PROVIDERS: ModelProvider[] = ["openai", "anthropic", "mistral", "groq", "custom"];

const PROVIDER_LABELS: Record<string, string> = {
  openai: "OpenAI", anthropic: "Anthropic", mistral: "Mistral",
  groq: "Groq", custom: "Custom / OpenRouter",
};

function CapabilityBadge({ label, icon: Icon, active }: { label: string; icon: any; active: boolean }) {
  if (!active) return null;
  return (
    <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-violet-50 text-violet-700 border border-violet-100">
      <Icon size={10} />
      {label}
    </span>
  );
}

export default function ModelsPage() {
  const [models, setModels] = useState<LLMModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [showCatalog, setShowCatalog] = useState(false);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [testing, setTesting] = useState<number | null>(null);
  const [testResults, setTestResults] = useState<Record<number, { ok: boolean; latency_ms: number; response: string; error: string | null }>>({});
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({
    name: "", provider: "custom" as ModelProvider, model_id: "",
    endpoint: "", api_key: "", context_length: 4096,
    cost_input_per_1k: 0, cost_output_per_1k: 0, notes: "",
  });

  const load = useCallback(() =>
    modelsApi.list().then(setModels).finally(() => setLoading(false)), []);

  useEffect(() => { load(); }, [load]);

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
    if (!confirm("Supprimer ce modèle ?")) return;
    await modelsApi.delete(id).catch(e => alert(String(e)));
    load();
  };

  return (
    <div>
      <PageHeader
        title="Model Registry"
        description="Gérez vos modèles LLM. Les modèles OpenRouter sont importés automatiquement au démarrage."
        action={
          <div className="flex gap-2">
            <button onClick={() => setShowCatalog(true)}
              className="flex items-center gap-2 border border-slate-200 px-4 py-2 rounded-lg text-sm hover:bg-slate-50 text-slate-700 transition-colors">
              🔍 Catalogue OpenRouter
            </button>
            <button onClick={() => setShowForm(!showForm)}
              className="flex items-center gap-2 bg-slate-900 text-white px-4 py-2 rounded-lg text-sm hover:bg-slate-700 transition-colors">
              <Plus size={14} /> Ajouter manuellement
            </button>
          </div>
        }
      />

      {showForm && (
        <div className="mx-8 mt-6 bg-white border border-slate-200 rounded-xl p-6">
          <h3 className="font-medium text-slate-900 mb-4">Nouveau modèle</h3>
          <form onSubmit={handleCreate} className="grid grid-cols-2 gap-4">
            {[
              { label: "Nom *", key: "name", type: "text", placeholder: "ex. GPT-4o Mini" },
              { label: "Model ID *", key: "model_id", type: "text", placeholder: "ex. gpt-4o-mini" },
              { label: "Endpoint (optionnel)", key: "endpoint", type: "text", placeholder: "https://openrouter.ai/api/v1" },
              { label: "API Key (optionnel)", key: "api_key", type: "password", placeholder: "sk-..." },
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
              <select value={form.provider}
                onChange={e => setForm(f => ({ ...f, provider: e.target.value as ModelProvider }))}
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
                {creating ? "Création…" : "Ajouter"}
              </button>
              <button type="button" onClick={() => setShowForm(false)} className="px-4 py-2 text-sm text-slate-600">Annuler</button>
            </div>
          </form>
        </div>
      )}

      <div className="p-8 pt-6 space-y-3">
        {loading ? (
          <div className="flex justify-center py-20"><Spinner size={24} /></div>
        ) : models.length === 0 ? (
          <EmptyState icon="🤖" title="Aucun modèle" description="Ajoutez des modèles depuis le catalogue OpenRouter ou manuellement." />
        ) : (
          models.map(m => {
            const test = testResults[m.id];
            return (
              <div key={m.id} className="bg-white border border-slate-200 rounded-xl overflow-hidden">
                <div className="flex items-center gap-4 p-5 cursor-pointer hover:bg-slate-50 transition-colors"
                  onClick={() => setExpanded(expanded === m.id ? null : m.id)}>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <span className="font-medium text-slate-900">{m.name}</span>
                      <Badge className={providerColor(m.provider)}>{m.provider}</Badge>
                      {/* Capability badges */}
                      <CapabilityBadge label="Vision" icon={Eye} active={m.supports_vision} />
                      <CapabilityBadge label="Tools" icon={Wrench} active={m.supports_tools} />
                      <CapabilityBadge label="Reasoning" icon={Brain} active={m.supports_reasoning} />
                    </div>
                    <div className="flex gap-3 text-xs text-slate-400">
                      <span className="font-mono">{m.model_id}</span>
                      {m.context_length && <span>{(m.context_length / 1000).toFixed(0)}k ctx</span>}
                      {m.cost_input_per_1k > 0 && <span>${m.cost_input_per_1k.toFixed(4)}/1k in</span>}
                      {m.has_api_key && <span className="text-green-500">🔑 key</span>}
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    {test && (
                      <div className="flex items-center gap-1.5 text-xs">
                        {test.ok
                          ? <><CheckCircle2 size={13} className="text-green-500" /><span className="text-green-600">{test.latency_ms}ms</span></>
                          : <><XCircle size={13} className="text-red-500" /><span className="text-red-500 max-w-32 truncate">{test.error}</span></>
                        }
                      </div>
                    )}
                    <button onClick={e => { e.stopPropagation(); handleTest(m.id); }} disabled={testing === m.id}
                      className="flex items-center gap-1.5 text-xs px-3 py-1.5 border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600 transition-colors disabled:opacity-50">
                      {testing === m.id ? <Spinner size={11} /> : <Zap size={11} />}
                      {testing === m.id ? "Test…" : "Tester"}
                    </button>
                    <button onClick={e => { e.stopPropagation(); handleDelete(m.id); }}
                      className="p-1.5 text-slate-300 hover:text-red-500 rounded-lg hover:bg-red-50 transition-colors">
                      <Trash2 size={14} />
                    </button>
                    {expanded === m.id ? <ChevronUp size={14} className="text-slate-400" /> : <ChevronDown size={14} className="text-slate-400" />}
                  </div>
                </div>

                {expanded === m.id && (
                  <div className="border-t border-slate-100 px-5 py-4 bg-slate-50 text-xs text-slate-600 space-y-1.5">
                    {m.endpoint && <div><span className="font-medium">Endpoint :</span> <span className="font-mono">{m.endpoint}</span></div>}
                    {m.notes && <div><span className="font-medium">Notes :</span> {m.notes}</div>}
                    <div className="flex gap-4">
                      <span><span className="font-medium">Input :</span> ${m.cost_input_per_1k}/1k tokens</span>
                      <span><span className="font-medium">Output :</span> ${m.cost_output_per_1k}/1k tokens</span>
                    </div>
                    <div className="flex gap-3 pt-1">
                      <CapabilityBadge label="Vision" icon={Eye} active={m.supports_vision} />
                      <CapabilityBadge label="Function Calling" icon={Wrench} active={m.supports_tools} />
                      <CapabilityBadge label="Reasoning / CoT" icon={Brain} active={m.supports_reasoning} />
                    </div>
                    {test?.ok && (
                      <div className="mt-2 p-2 bg-green-50 rounded-lg border border-green-100">
                        <span className="font-medium text-green-700">Réponse :</span> {test.response}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {showCatalog && <ModelCatalogModal onClose={() => { setShowCatalog(false); load(); }} />}
    </div>
  );
}
