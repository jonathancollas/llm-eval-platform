"use client";
import { useEffect, useState }
import { ModelCatalogModal } from "@/components/ModelCatalogModal"; from "react";
import { modelsApi } from "@/lib/api";
import type { LLMModel, ModelProvider } from "@/lib/api";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState } from "@/components/EmptyState";
import { Badge } from "@/components/Badge";
import { Spinner } from "@/components/Spinner";
import { providerColor, formatCost, timeAgo } from "@/lib/utils";
import { Plus, Trash2, Zap, CheckCircle, XCircle } from "lucide-react";

const PROVIDERS: ModelProvider[] = ["ollama", "openai", "anthropic", "mistral", "groq", "custom"];

const PROVIDER_PRESETS: Record<string, { model_id: string; endpoint?: string; cost_in: number; cost_out: number }> = {
  "gpt-4o-mini": { model_id: "gpt-4o-mini", cost_in: 0.15, cost_out: 0.6 },
  "gpt-4o": { model_id: "gpt-4o", cost_in: 2.5, cost_out: 10 },
  "claude-3-5-haiku": { model_id: "claude-3-5-haiku-20241022", cost_in: 0.8, cost_out: 4 },
  "claude-sonnet-4": { model_id: "claude-sonnet-4-20250514", cost_in: 3, cost_out: 15 },
  "llama3.2:3b (Ollama)": { model_id: "llama3.2:3b", endpoint: "http://localhost:11434", cost_in: 0, cost_out: 0 },
  "llama3.1:8b (Ollama)": { model_id: "llama3.1:8b", endpoint: "http://localhost:11434", cost_in: 0, cost_out: 0 },
  "mistral:7b (Ollama)": { model_id: "mistral:7b", endpoint: "http://localhost:11434", cost_in: 0, cost_out: 0 },
  "phi4:14b (Ollama)": { model_id: "phi4:14b", endpoint: "http://localhost:11434", cost_in: 0, cost_out: 0 },
};

type TestResult = { ok: boolean; latency_ms: number; error: string | null };

export default function ModelsPage() {
  const [models, setModels] = useState<LLMModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [testing, setTesting] = useState<number | null>(null);
  const [testResults, setTestResults] = useState<Record<number, TestResult>>({});
  const [form, setForm] = useState({
    name: "", provider: "ollama" as ModelProvider, model_id: "",
    endpoint: "", api_key: "", context_length: 4096,
    cost_input_per_1k: 0, cost_output_per_1k: 0, notes: "",
  });
  const [saving, setSaving] = useState(false);
  const [showCatalog, setShowCatalog] = useState(false);

  const load = () => modelsApi.list().then(setModels).finally(() => setLoading(false));
  useEffect(() => { load(); }, []);

  const applyPreset = (preset: string) => {
    const p = PROVIDER_PRESETS[preset];
    if (!p) return;
    const provider = p.endpoint ? "ollama" : "openai";
    setForm(f => ({
      ...f, name: preset, model_id: p.model_id,
      endpoint: p.endpoint ?? "", provider,
      cost_input_per_1k: p.cost_in, cost_output_per_1k: p.cost_out,
    }));
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await modelsApi.create({
        name: form.name, provider: form.provider, model_id: form.model_id,
        endpoint: form.endpoint || null, api_key: form.api_key || undefined,
        context_length: form.context_length,
        cost_input_per_1k: form.cost_input_per_1k,
        cost_output_per_1k: form.cost_output_per_1k, notes: form.notes,
      });
      setShowForm(false);
      setForm({ name: "", provider: "ollama", model_id: "", endpoint: "", api_key: "", context_length: 4096, cost_input_per_1k: 0, cost_output_per_1k: 0, notes: "" });
      load();
    } catch (err) { alert(String(err)); } finally { setSaving(false); }
  };

  const handleTest = async (id: number) => {
    setTesting(id);
    try {
      const r = await modelsApi.test(id);
      setTestResults(prev => ({ ...prev, [id]: { ok: r.ok, latency_ms: r.latency_ms, error: r.error } }));
    } catch (err) {
      setTestResults(prev => ({ ...prev, [id]: { ok: false, latency_ms: 0, error: String(err) } }));
    } finally { setTesting(null); }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Delete this model?")) return;
    await modelsApi.delete(id);
    load();
  };

  return (
    <div>
      <PageHeader
        title="Model Registry"
        description="Manage your LLM endpoints — local (Ollama) and cloud APIs."
        action={
          <div className="flex gap-2">
          <button onClick={() => setShowCatalog(true)}
            className="flex items-center gap-2 border border-slate-200 px-4 py-2 rounded-lg text-sm hover:bg-slate-50 text-slate-700 transition-colors">
            🔍 Parcourir le catalogue
          </button>
          <button onClick={() => setShowForm(!showForm)}
            className="flex items-center gap-2 bg-slate-900 text-white px-4 py-2 rounded-lg text-sm hover:bg-slate-700 transition-colors">
            <Plus size={14} /> Add Model
          </button>
          </div>
        }
      />

      {/* Add form */}
      {showForm && (
        <div className="mx-8 mt-6 bg-white border border-slate-200 rounded-xl p-6">
          <h3 className="font-medium text-slate-900 mb-4">New Model</h3>

          {/* Presets */}
          <div className="mb-4">
            <p className="text-xs text-slate-500 mb-2">Quick presets</p>
            <div className="flex flex-wrap gap-2">
              {Object.keys(PROVIDER_PRESETS).map(p => (
                <button key={p} onClick={() => applyPreset(p)}
                  className="text-xs px-3 py-1 bg-slate-100 hover:bg-slate-200 rounded-md transition-colors text-slate-700">
                  {p}
                </button>
              ))}
            </div>
          </div>

          <form onSubmit={handleCreate} className="grid grid-cols-2 gap-4">
            {[
              { label: "Display name", key: "name", required: true },
              { label: "Model ID", key: "model_id", placeholder: "e.g. gpt-4o-mini", required: true },
              { label: "Endpoint (optional)", key: "endpoint", placeholder: "http://localhost:11434" },
              { label: "API Key (optional)", key: "api_key", type: "password" },
            ].map(({ label, key, placeholder, required, type }) => (
              <div key={key}>
                <label className="text-xs font-medium text-slate-600 mb-1 block">{label}</label>
                <input type={type ?? "text"} required={required} placeholder={placeholder}
                  value={(form as Record<string, string | number>)[key] as string}
                  onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900 focus:border-transparent"
                />
              </div>
            ))}

            <div>
              <label className="text-xs font-medium text-slate-600 mb-1 block">Provider</label>
              <select value={form.provider} onChange={e => setForm(f => ({ ...f, provider: e.target.value as ModelProvider }))}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900">
                {PROVIDERS.map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>

            <div>
              <label className="text-xs font-medium text-slate-600 mb-1 block">Context length</label>
              <input type="number" value={form.context_length}
                onChange={e => setForm(f => ({ ...f, context_length: +e.target.value }))}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900"
              />
            </div>

            <div>
              <label className="text-xs font-medium text-slate-600 mb-1 block">Cost / 1k input tokens ($)</label>
              <input type="number" step="0.001" value={form.cost_input_per_1k}
                onChange={e => setForm(f => ({ ...f, cost_input_per_1k: +e.target.value }))}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900"
              />
            </div>

            <div>
              <label className="text-xs font-medium text-slate-600 mb-1 block">Cost / 1k output tokens ($)</label>
              <input type="number" step="0.001" value={form.cost_output_per_1k}
                onChange={e => setForm(f => ({ ...f, cost_output_per_1k: +e.target.value }))}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900"
              />
            </div>

            <div className="col-span-2 flex gap-3 pt-2">
              <button type="submit" disabled={saving}
                className="bg-slate-900 text-white px-4 py-2 rounded-lg text-sm hover:bg-slate-700 transition-colors disabled:opacity-50">
                {saving ? "Saving…" : "Add Model"}
              </button>
              <button type="button" onClick={() => setShowForm(false)}
                className="px-4 py-2 text-sm text-slate-600 hover:text-slate-900">
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Model list */}
      <div className="p-8">
        {loading ? (
          <div className="flex justify-center py-20"><Spinner size={24} /></div>
        ) : models.length === 0 ? (
          <EmptyState icon="🤖" title="No models registered"
            description="Add your first model to start running evaluations."
            action={<button onClick={() => setShowForm(true)} className="bg-slate-900 text-white px-4 py-2 rounded-lg text-sm">Add Model</button>}
          />
        ) : (
          <div className="space-y-3">
            {models.map(m => {
              const tr = testResults[m.id];
              return (
                <div key={m.id} className="bg-white border border-slate-200 rounded-xl p-5 flex items-center gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-medium text-slate-900">{m.name}</span>
                      <Badge className={providerColor(m.provider)}>{m.provider}</Badge>
                      {m.has_api_key && <Badge className="bg-slate-100 text-slate-600">🔑 key stored</Badge>}
                    </div>
                    <div className="text-xs text-slate-400 font-mono">{m.model_id}</div>
                    {m.endpoint && <div className="text-xs text-slate-400 mt-0.5">{m.endpoint}</div>}
                  </div>

                  <div className="text-xs text-slate-500 text-right hidden lg:block">
                    <div>{m.context_length.toLocaleString()} ctx</div>
                    {m.cost_input_per_1k > 0 && (
                      <div>{formatCost(m.cost_input_per_1k)}/1k in · {formatCost(m.cost_output_per_1k)}/1k out</div>
                    )}
                  </div>

                  {tr && (
                    <div className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg ${tr.ok ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"}`}>
                      {tr.ok ? <CheckCircle size={12} /> : <XCircle size={12} />}
                      {tr.ok ? `${tr.latency_ms}ms` : tr.error?.slice(0, 40)}
                    </div>
                  )}

                  <div className="flex items-center gap-2">
                    <button onClick={() => handleTest(m.id)} disabled={testing === m.id}
                      className="flex items-center gap-1.5 text-xs px-3 py-1.5 border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors text-slate-600 disabled:opacity-50">
                      {testing === m.id ? <Spinner size={12} /> : <Zap size={12} />}
                      Test
                    </button>
                    <button onClick={() => handleDelete(m.id)}
                      className="p-1.5 text-slate-300 hover:text-red-500 transition-colors">
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    {showCatalog && <ModelCatalogModal onClose={() => { setShowCatalog(false); load(); }} />}
    </div>
  );
}
