"use client";
import { useEffect, useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { Plus, GitFork, Globe, Lock, FileText, Beaker } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "https://llm-eval-backend-kqlh.onrender.com/api";

interface Workspace {
  id: number; name: string; slug: string; description: string;
  status: string; risk_domain: string; visibility: string;
  fork_count: number; created_at: string;
}

const STATUS_COLORS: Record<string, string> = {
  draft: "bg-slate-100 text-slate-600", active: "bg-blue-100 text-blue-700",
  published: "bg-green-100 text-green-700", archived: "bg-slate-100 text-slate-400",
};

export default function ResearchPage() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: "", description: "", hypothesis: "", risk_domain: "capability", visibility: "private" });
  const [selected, setSelected] = useState<any>(null);

  const load = () => fetch(`${API}/research/workspaces`).then(r => r.json()).then(d => setWorkspaces(d.workspaces ?? [])).finally(() => setLoading(false));
  useEffect(() => { load(); }, []);

  const handleCreate = async () => {
    setCreating(true);
    try {
      await fetch(`${API}/research/workspaces`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(form) });
      setShowForm(false); setForm({ name: "", description: "", hypothesis: "", risk_domain: "capability", visibility: "private" }); load();
    } finally { setCreating(false); }
  };

  const handleFork = async (id: number) => {
    await fetch(`${API}/research/workspaces/${id}/fork?new_name=Fork`, { method: "POST" });
    load();
  };

  const loadDetail = async (id: number) => {
    const res = await fetch(`${API}/research/workspaces/${id}`);
    setSelected(await res.json());
  };

  if (loading) return <div className="p-8"><Spinner size={20} /></div>;

  return (
    <div>
      <PageHeader title="Research Workspaces" description="The research operating system for frontier AI evaluation."
        action={<button onClick={() => setShowForm(!showForm)} className="flex items-center gap-2 bg-slate-900 text-white px-4 py-2 rounded-lg text-sm hover:bg-slate-700"><Plus size={14} /> New Workspace</button>} />

      <div className="p-8 space-y-6">
        {showForm && (
          <div className="bg-white border border-slate-200 rounded-xl p-6 space-y-4">
            <h3 className="font-medium text-slate-900">New Research Workspace</h3>
            <div className="grid grid-cols-2 gap-4">
              <div><label className="text-xs font-medium text-slate-600 mb-1 block">Name</label>
                <input value={form.name} onChange={e => setForm(f => ({...f, name: e.target.value}))} className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" placeholder="e.g. Shutdown Resistance in Frontier Agents" /></div>
              <div><label className="text-xs font-medium text-slate-600 mb-1 block">Risk Domain</label>
                <select value={form.risk_domain} onChange={e => setForm(f => ({...f, risk_domain: e.target.value}))} className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm">
                  <option value="capability">Capability</option><option value="propensity">Propensity</option>
                  <option value="agentic">Agentic</option><option value="safety">Safety</option>
                </select></div>
              <div className="col-span-2"><label className="text-xs font-medium text-slate-600 mb-1 block">Hypothesis</label>
                <textarea value={form.hypothesis} onChange={e => setForm(f => ({...f, hypothesis: e.target.value}))} rows={3}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" placeholder="Research question and expected findings…" /></div>
              <div className="col-span-2"><label className="text-xs font-medium text-slate-600 mb-1 block">Description</label>
                <input value={form.description} onChange={e => setForm(f => ({...f, description: e.target.value}))} className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" /></div>
            </div>
            <div className="flex gap-2">
              <button onClick={handleCreate} disabled={creating || !form.name.trim()} className="bg-slate-900 text-white px-4 py-2 rounded-lg text-sm disabled:opacity-40">{creating ? "Creating…" : "Create"}</button>
              <button onClick={() => setShowForm(false)} className="text-sm text-slate-500">Cancel</button>
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {workspaces.map(ws => (
            <button key={ws.id} onClick={() => loadDetail(ws.id)}
              className={`text-left bg-white border rounded-xl p-5 hover:border-slate-300 transition-colors ${selected?.id === ws.id ? "border-slate-900 ring-1 ring-slate-900" : "border-slate-200"}`}>
              <div className="flex items-center gap-2 mb-2">
                <Beaker size={15} className="text-slate-400" />
                <span className="font-medium text-slate-900 text-sm">{ws.name}</span>
                <span className={`text-[10px] px-2 py-0.5 rounded-full ${STATUS_COLORS[ws.status] || STATUS_COLORS.draft}`}>{ws.status}</span>
                {ws.visibility === "public" ? <Globe size={12} className="text-green-500" /> : <Lock size={12} className="text-slate-300" />}
              </div>
              <p className="text-xs text-slate-500 line-clamp-2">{ws.description || "No description"}</p>
              <div className="flex items-center gap-3 mt-3 text-[10px] text-slate-400">
                <span>{ws.risk_domain}</span>
                {ws.fork_count > 0 && <span><GitFork size={10} className="inline" /> {ws.fork_count}</span>}
                <span className="ml-auto">{new Date(ws.created_at).toLocaleDateString("en-US")}</span>
              </div>
            </button>
          ))}
          {workspaces.length === 0 && (
            <div className="col-span-2 text-center py-16 text-slate-400">
              <Beaker size={40} className="mx-auto mb-3 text-slate-300" />
              <h3 className="font-semibold text-slate-700 mb-1">No workspaces</h3>
              <p className="text-sm">Create a research workspace to organize your evaluation science.</p>
            </div>
          )}
        </div>

        {selected && (
          <div className="bg-white border border-slate-200 rounded-xl p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-medium text-slate-900">{selected.name}</h3>
              <div className="flex gap-2">
                <button onClick={() => handleFork(selected.id)} className="flex items-center gap-1 text-xs border border-slate-200 px-3 py-1.5 rounded-lg hover:bg-slate-50"><GitFork size={12} /> Fork</button>
                <button onClick={() => setSelected(null)} className="text-xs text-slate-400">Close</button>
              </div>
            </div>
            {selected.hypothesis && <div className="bg-blue-50 border border-blue-200 rounded-lg p-3"><span className="text-[10px] font-medium text-blue-500 uppercase">Hypothesis</span><p className="text-sm text-blue-800 mt-1">{selected.hypothesis}</p></div>}
            {selected.protocol && <div className="bg-slate-50 rounded-lg p-3"><span className="text-[10px] font-medium text-slate-400 uppercase">Protocol</span><p className="text-sm text-slate-700 mt-1 whitespace-pre-wrap">{selected.protocol}</p></div>}
            <div className="grid grid-cols-4 gap-3 text-xs">
              <div className="bg-slate-50 rounded-lg p-3"><span className="text-slate-400">Campaigns</span><div className="font-bold text-slate-900 mt-1">{selected.campaign_ids?.length ?? 0}</div></div>
              <div className="bg-slate-50 rounded-lg p-3"><span className="text-slate-400">Models</span><div className="font-bold text-slate-900 mt-1">{selected.model_ids?.length ?? 0}</div></div>
              <div className="bg-slate-50 rounded-lg p-3"><span className="text-slate-400">Benchmarks</span><div className="font-bold text-slate-900 mt-1">{selected.benchmark_ids?.length ?? 0}</div></div>
              <div className="bg-slate-50 rounded-lg p-3"><span className="text-slate-400">Manifests</span><div className="font-bold text-slate-900 mt-1">{selected.manifests?.length ?? 0}</div></div>
            </div>
            {selected.doi && <div className="text-xs text-slate-500"><FileText size={12} className="inline mr-1" />DOI: <a href={selected.paper_url} className="text-blue-600 underline">{selected.doi}</a></div>}
          </div>
        )}
      </div>
    </div>
  );
}
