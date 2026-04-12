"use client";
import { useEffect, useState, useCallback } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { Badge } from "@/components/Badge";
import { modelsApi } from "@/lib/api";
import type { LLMModel, LLMModelSlim } from "@/lib/api";
import { Plus, AlertTriangle, Shield, CheckCircle2, X, Search } from "lucide-react";
import { API_BASE as API } from "@/lib/config";

interface Incident {
  incident_id: string; title: string; category: string; severity: string;
  status: string; reproducibility: number; affected_models: string[];
  atlas_technique: string | null; created_at: string;
}

const SEV  = { critical: "bg-red-600 text-white", high: "bg-red-100 text-red-700", medium: "bg-yellow-100 text-yellow-700", low: "bg-green-100 text-green-700" };
const STAT = { open: "bg-red-50 text-red-600", confirmed: "bg-orange-50 text-orange-600", mitigated: "bg-blue-50 text-blue-600", closed: "bg-green-50 text-green-600" };

// ── Inline model picker for SIX ─────────────────────────────────────────────
function ModelPicker({ selected, onChange }: {
  selected: string[];
  onChange: (models: string[]) => void;
}) {
  const [models, setModels] = useState<LLMModelSlim[]>([]);
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState(false);

  useEffect(() => {
    modelsApi.list().then(setModels).catch(() => {});
  }, []);

  const filtered = models.filter(m =>
    m.name.toLowerCase().includes(search.toLowerCase()) ||
    m.model_id.toLowerCase().includes(search.toLowerCase())
  );

  const toggle = (name: string) => {
    onChange(selected.includes(name)
      ? selected.filter(s => s !== name)
      : [...selected, name]
    );
  };

  return (
    <div>
      <label className="text-xs font-medium text-slate-600 mb-1 block">
        Affected Models
      </label>

      {/* Selected chips */}
      <div className="flex flex-wrap gap-1.5 mb-2 min-h-[28px]">
        {selected.map(name => (
          <span key={name} className="inline-flex items-center gap-1 text-xs bg-red-100 text-red-700 border border-red-200 rounded-full px-2.5 py-0.5">
            {name}
            <button onClick={() => toggle(name)} className="hover:text-red-900">
              <X size={10} />
            </button>
          </span>
        ))}
        {selected.length === 0 && (
          <span className="text-xs text-slate-400 italic">No models selected</span>
        )}
      </div>

      {/* Toggle explorer */}
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-xs text-blue-600 hover:underline mb-2"
      >
        <Search size={11} />
        {open ? "Close" : `Select from registry (${models.length} models)`}
      </button>

      {open && (
        <div className="border border-slate-200 rounded-lg overflow-hidden">
          <div className="p-2 border-b border-slate-100">
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search models…"
              className="w-full text-xs px-2 py-1.5 border border-slate-200 rounded focus:outline-none focus:ring-1 focus:ring-red-400"
            />
          </div>
          <div className="max-h-48 overflow-y-auto">
            {filtered.slice(0, 40).map(m => (
              <button
                key={m.id}
                type="button"
                onClick={() => toggle(m.name)}
                className={`w-full text-left px-3 py-2 text-xs flex items-center gap-2 hover:bg-slate-50 transition-colors ${
                  selected.includes(m.name) ? "bg-red-50" : ""
                }`}
              >
                <span className={`w-3 h-3 rounded-full border flex-shrink-0 flex items-center justify-center ${
                  selected.includes(m.name) ? "bg-red-500 border-red-500" : "border-slate-300"
                }`}>
                  {selected.includes(m.name) && (
                    <span className="text-white text-[8px]">✓</span>
                  )}
                </span>
                <span className="font-medium text-slate-800 truncate">{m.name}</span>
                <span className="text-slate-400 font-mono truncate">{m.model_id}</span>
                {(m as any).is_open_weight && (
                  <Badge className="bg-emerald-100 text-emerald-700 text-[9px] ml-auto shrink-0">OW</Badge>
                )}
              </button>
            ))}
            {filtered.length === 0 && (
              <div className="px-3 py-4 text-xs text-slate-400 text-center">No models found</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function IncidentsPage() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [creating, setCreating] = useState(false);
  const [filter, setFilter] = useState<string>("all");
  const [selected, setSelected] = useState<any>(null);
  const [form, setForm] = useState({
    title: "", category: "prompt_injection", severity: "medium",
    description: "", reproducibility: 0.5,
    affected_models: [] as string[],
    atlas_technique: "",
  });

  const load = useCallback(() => {
    fetch(`${API}/research/incidents`)
      .then(r => r.ok ? r.json() : { incidents: [] })
      .then(d => setIncidents(d.incidents ?? []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    setCreating(true);
    try {
      const payload = {
        ...form,
        affected_models: form.affected_models,
        atlas_technique: form.atlas_technique || undefined,
      };
      await fetch(`${API}/research/incidents`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setShowForm(false);
      setForm({ title: "", category: "prompt_injection", severity: "medium", description: "", reproducibility: 0.5, affected_models: [], atlas_technique: "" });
      load();
    } catch {}
    finally { setCreating(false); }
  };

  const loadDetail = async (id: string) => {
    const res = await fetch(`${API}/research/incidents/${id}`);
    if (res.ok) setSelected(await res.json());
  };

  const filtered = filter === "all" ? incidents : incidents.filter(i =>
    i.severity === filter || i.status === filter || i.category === filter
  );
  const categories = [...new Set(incidents.map(i => i.category))];

  return (
    <div>
      <PageHeader
        title="Safety Incident Exchange (SIX)"
        description="The CVE of AI safety — global incident registry."
        action={
          <button onClick={() => setShowForm(!showForm)}
            className="flex items-center gap-2 bg-red-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-red-700">
            <Plus size={14} /> Report Incident
          </button>
        }
      />

      <div className="p-4 sm:p-8 space-y-6">
        {showForm && (
          <div className="bg-white border border-red-200 rounded-xl p-6 space-y-4">
            <h3 className="font-medium text-red-700">Report a Safety Incident</h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-xs font-medium text-slate-600 mb-1 block">Title</label>
                <input value={form.title} onChange={e => setForm(f => ({...f, title: e.target.value}))}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                  placeholder="e.g. Strategic deception in multi-turn agent session" />
              </div>
              <div>
                <label className="text-xs font-medium text-slate-600 mb-1 block">Category</label>
                <select value={form.category} onChange={e => setForm(f => ({...f, category: e.target.value}))}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm">
                  <option value="prompt_injection">Prompt Injection</option>
                  <option value="jailbreak">Jailbreak</option>
                  <option value="scheming">Scheming / Deception</option>
                  <option value="shutdown_resistance">Shutdown Resistance</option>
                  <option value="sycophancy">Sycophancy</option>
                  <option value="goal_drift">Goal Drift</option>
                  <option value="data_extraction">Data Extraction</option>
                  <option value="persuasion">Persuasion</option>
                  <option value="hallucination">Hallucination</option>
                  <option value="other">Other</option>
                </select>
              </div>
              <div>
                <label className="text-xs font-medium text-slate-600 mb-1 block">Severity</label>
                <select value={form.severity} onChange={e => setForm(f => ({...f, severity: e.target.value}))}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm">
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                  <option value="critical">Critical</option>
                </select>
              </div>
              <div>
                <label className="text-xs font-medium text-slate-600 mb-1 block">Reproducibility (0–1)</label>
                <input type="number" step="0.1" min="0" max="1" value={form.reproducibility}
                  onChange={e => setForm(f => ({...f, reproducibility: +e.target.value}))}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" />
              </div>
              <div className="col-span-2">
                <label className="text-xs font-medium text-slate-600 mb-1 block">Description</label>
                <textarea value={form.description} onChange={e => setForm(f => ({...f, description: e.target.value}))}
                  rows={3} className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                  placeholder="Detailed description of the incident…" />
              </div>

              {/* ── Model Picker — replaces comma-separated text field ── */}
              <div className="col-span-2">
                <ModelPicker
                  selected={form.affected_models}
                  onChange={models => setForm(f => ({...f, affected_models: models}))}
                />
              </div>

              <div>
                <label className="text-xs font-medium text-slate-600 mb-1 block">ATLAS Technique ID</label>
                <input value={form.atlas_technique} onChange={e => setForm(f => ({...f, atlas_technique: e.target.value}))}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                  placeholder="e.g. AML.T0051" />
              </div>
            </div>
            <div className="flex gap-2">
              <button onClick={handleCreate} disabled={creating || !form.title.trim()}
                className="bg-red-600 text-white px-4 py-2 rounded-lg text-sm disabled:opacity-40">
                {creating ? "Reporting…" : "Submit Incident"}
              </button>
              <button onClick={() => setShowForm(false)} className="text-sm text-slate-500">Cancel</button>
            </div>
          </div>
        )}

        {/* Filters */}
        <div className="flex gap-2 flex-wrap">
          {["all", "critical", "high", "medium", "open", "confirmed", ...categories].map(f => (
            <button key={f} onClick={() => setFilter(f)}
              className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${
                filter === f ? "bg-slate-900 text-white border-slate-900" : "border-slate-200 text-slate-500 hover:bg-slate-50"
              }`}>
              {f}
            </button>
          ))}
        </div>

        {/* Incident list */}
        {loading ? (
          <div className="flex justify-center py-12"><Spinner size={24} /></div>
        ) : (
          <div className="space-y-2">
            {filtered.map(inc => (
              <button key={inc.incident_id} onClick={() => loadDetail(inc.incident_id)}
                className={`w-full text-left bg-white border rounded-xl p-4 hover:border-slate-300 transition-colors ${
                  selected?.incident_id === inc.incident_id ? "border-slate-900" : "border-slate-200"
                }`}>
                <div className="flex items-center gap-3 flex-wrap">
                  <span className="font-mono text-xs font-bold text-slate-500">{inc.incident_id}</span>
                  <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${SEV[inc.severity as keyof typeof SEV] || SEV.medium}`}>{inc.severity}</span>
                  <span className={`text-[10px] px-2 py-0.5 rounded-full ${STAT[inc.status as keyof typeof STAT] || STAT.open}`}>{inc.status}</span>
                  <span className="text-xs text-slate-400">{inc.category}</span>
                  {inc.atlas_technique && <span className="text-[10px] text-blue-500 font-mono">{inc.atlas_technique}</span>}
                  <span className="text-xs text-slate-300 ml-auto">{new Date(inc.created_at).toLocaleDateString("en-US")}</span>
                </div>
                <div className="text-sm text-slate-800 mt-1">{inc.title}</div>
                {inc.affected_models.length > 0 && (
                  <div className="flex gap-1 flex-wrap mt-1.5">
                    {inc.affected_models.map(m => (
                      <span key={m} className="text-[10px] bg-red-50 text-red-600 border border-red-100 px-1.5 py-0.5 rounded">
                        {m}
                      </span>
                    ))}
                  </div>
                )}
              </button>
            ))}
            {filtered.length === 0 && (
              <div className="text-center py-16 text-slate-400">
                <Shield size={40} className="mx-auto mb-3 text-slate-300" />
                <h3 className="font-semibold text-slate-700 mb-1">No incidents</h3>
                <p className="text-sm">Report an AI safety incident to build the global registry.</p>
              </div>
            )}
          </div>
        )}

        {/* Detail panel */}
        {selected && (
          <div className="bg-white border border-slate-200 rounded-xl p-6 space-y-3">
            <div className="flex items-center gap-3">
              <span className="font-mono font-bold text-slate-700">{selected.incident_id}</span>
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${SEV[selected.severity as keyof typeof SEV] || SEV.medium}`}>{selected.severity}</span>
              <button onClick={() => setSelected(null)} className="ml-auto text-xs text-slate-400">Close</button>
            </div>
            <h3 className="font-medium text-slate-900">{selected.title}</h3>
            {selected.description && <p className="text-sm text-slate-600">{selected.description}</p>}
            <div className="grid grid-cols-3 gap-3 text-xs">
              <div className="bg-slate-50 rounded-lg p-3">
                <span className="text-slate-400">Reproducibility</span>
                <div className="font-bold text-slate-900 mt-1">{Math.round(selected.reproducibility * 100)}%</div>
              </div>
              <div className="bg-slate-50 rounded-lg p-3">
                <span className="text-slate-400">Mitigation</span>
                <div className="font-bold text-slate-900 mt-1">{selected.mitigation_status}</div>
              </div>
              <div className="bg-slate-50 rounded-lg p-3">
                <span className="text-slate-400">ATLAS</span>
                <div className="font-bold text-slate-900 mt-1">{selected.atlas_technique || "—"}</div>
              </div>
            </div>
            {selected.affected_models?.length > 0 && (
              <div>
                <div className="text-xs text-slate-400 mb-1.5">Affected models</div>
                <div className="flex flex-wrap gap-1.5">
                  {selected.affected_models.map((m: string) => (
                    <span key={m} className="text-xs bg-red-50 text-red-700 border border-red-200 px-2 py-0.5 rounded-full">{m}</span>
                  ))}
                </div>
              </div>
            )}
            {selected.mitigation && (
              <div className="bg-green-50 border border-green-200 rounded-lg p-3 text-xs text-green-700">
                {selected.mitigation}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
