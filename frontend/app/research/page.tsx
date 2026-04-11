"use client";
import { useState, useEffect, useCallback } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { API_BASE } from "@/lib/config";
import { Plus, GitFork, FlaskConical, ScrollText, Users, ChevronRight,
         CheckCircle2, Clock, Copy, ExternalLink, BookOpen, Beaker } from "lucide-react";

const API = API_BASE;
const RISK_DOMAINS = [
  { value: "capability",  label: "Dangerous Capability",  icon: "⚡" },
  { value: "propensity",  label: "Propensity / Scheming", icon: "🎭" },
  { value: "agentic",     label: "Agentic Failure Modes", icon: "🤖" },
  { value: "safety",      label: "Safety Refusals",       icon: "🛡️" },
  { value: "alignment",   label: "Alignment",             icon: "🎯" },
  { value: "mixed",       label: "Multi-domain",          icon: "🔬" },
];
const STATUS_CFG = {
  draft:     { color: "bg-slate-100 text-slate-500",  label: "Draft"     },
  active:    { color: "bg-blue-100 text-blue-600",    label: "Active"    },
  published: { color: "bg-green-100 text-green-700",  label: "Published" },
  archived:  { color: "bg-slate-100 text-slate-400",  label: "Archived"  },
};
const CONFIDENCE_CFG = {
  A:            { color: "bg-green-100 text-green-700",  label: "Grade A — High confidence"  },
  B:            { color: "bg-blue-100 text-blue-700",    label: "Grade B — Moderate"         },
  C:            { color: "bg-yellow-100 text-yellow-700",label: "Grade C — Limited"          },
  D:            { color: "bg-red-100 text-red-700",      label: "Grade D — Insufficient"     },
  insufficient: { color: "bg-slate-100 text-slate-500",  label: "No replications yet"        },
};

export default function ResearchPage() {
  const [workspaces, setWorkspaces] = useState([]);
  const [selected, setSelected] = useState(null);
  const [replications, setReplications] = useState([]);
  const [repSummary, setRepSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("overview");
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [showRepForm, setShowRepForm] = useState(false);
  const [showSubmitForm, setShowSubmitForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [newWs, setNewWs] = useState({ name: "", description: "", hypothesis: "", protocol: "", risk_domain: "capability", visibility: "private" });
  const [repForm, setRepForm] = useState({ lab: "", notes: "" });
  const [submitForm, setSubmitForm] = useState({ lab: "", concordance: "0.85", successful: true, notes: "" });
  const [manifest, setManifest] = useState(null);
  const [manifestLoading, setManifestLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    fetch(`${API}/research/workspaces`).then(r => r.json()).then(d => setWorkspaces(d.workspaces ?? [])).finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const selectWorkspace = async (ws) => {
    setSelected(ws); setTab("overview"); setManifest(null);
    const r = await fetch(`${API}/research/workspaces/${ws.id}/replications`);
    if (r.ok) { const d = await r.json(); setReplications(d.replications ?? []); setRepSummary(d.summary); }
  };

  const create = async () => {
    setSaving(true);
    await fetch(`${API}/research/workspaces`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(newWs) });
    setShowCreateForm(false); setNewWs({ name: "", description: "", hypothesis: "", protocol: "", risk_domain: "capability", visibility: "private" }); load(); setSaving(false);
  };

  const fork = async (id) => { await fetch(`${API}/research/workspaces/${id}/fork?new_name=Fork`, { method: "POST" }); load(); };
  const publish = async (id) => {
    await fetch(`${API}/research/workspaces/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status: "published", visibility: "public" }) });
    load();
  };

  const requestReplication = async () => {
    if (!selected || !repForm.lab) return;
    setSaving(true);
    await fetch(`${API}/research/workspaces/${selected.id}/replications`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ workspace_id: selected.id, replicating_lab: repForm.lab, notes: repForm.notes }) });
    setShowRepForm(false); setRepForm({ lab: "", notes: "" });
    const r = await fetch(`${API}/research/workspaces/${selected.id}/replications`);
    const d = await r.json(); setReplications(d.replications ?? []); setRepSummary(d.summary); setSaving(false);
  };

  const submitReplication = async () => {
    if (!selected || !submitForm.lab) return;
    setSaving(true);
    const r = await fetch(`${API}/research/workspaces/${selected.id}/replications/submit`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ workspace_id: selected.id, replicating_lab: submitForm.lab, concordance_score: parseFloat(submitForm.concordance), successful: submitForm.successful, notes: submitForm.notes }) });
    const d = await r.json(); setRepSummary(d); setShowSubmitForm(false);
    const r2 = await fetch(`${API}/research/workspaces/${selected.id}/replications`);
    const d2 = await r2.json(); setReplications(d2.replications ?? []); setSaving(false);
  };

  const generateManifest = async () => {
    if (!selected) return; setManifestLoading(true);
    const r = await fetch(`${API}/research/manifests/generate/1`, { method: "POST" });
    if (r.ok) setManifest(await r.json()); setManifestLoading(false);
  };

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <div className="w-72 border-r border-slate-200 flex flex-col bg-white shrink-0">
        <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
          <div><h2 className="font-semibold text-slate-900 text-sm">Research Workspaces</h2><p className="text-[11px] text-slate-400">Mercury Research OS</p></div>
          <button onClick={() => setShowCreateForm(!showCreateForm)} className="p-2 bg-slate-900 text-white rounded-lg hover:bg-slate-700"><Plus size={14} /></button>
        </div>

        {showCreateForm && (
          <div className="px-4 py-4 border-b border-slate-100 bg-slate-50 space-y-2.5">
            <h3 className="text-xs font-semibold text-slate-700">New Workspace</h3>
            <input value={newWs.name} onChange={e => setNewWs(w => ({...w, name: e.target.value}))} placeholder="Name…" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-xs" />
            <textarea value={newWs.hypothesis} onChange={e => setNewWs(w => ({...w, hypothesis: e.target.value}))} placeholder="Research hypothesis…" rows={2} className="w-full border border-slate-200 rounded-lg px-3 py-2 text-xs resize-none" />
            <select value={newWs.risk_domain} onChange={e => setNewWs(w => ({...w, risk_domain: e.target.value}))} className="w-full border border-slate-200 rounded-lg px-3 py-2 text-xs">
              {RISK_DOMAINS.map(d => <option key={d.value} value={d.value}>{d.icon} {d.label}</option>)}
            </select>
            <div className="flex gap-2">
              <button onClick={create} disabled={saving || !newWs.name} className="flex-1 bg-slate-900 text-white py-1.5 rounded-lg text-xs hover:bg-slate-700 disabled:opacity-40">{saving ? "…" : "Create"}</button>
              <button onClick={() => setShowCreateForm(false)} className="px-3 border border-slate-200 rounded-lg text-xs text-slate-500">Cancel</button>
            </div>
          </div>
        )}

        <div className="flex-1 overflow-y-auto">
          {loading ? <div className="flex items-center justify-center py-12"><Spinner size={20} /></div>
          : workspaces.length === 0 ? (
            <div className="text-center py-12 px-4">
              <Beaker size={32} className="text-slate-300 mx-auto mb-3" />
              <p className="text-sm text-slate-500">No workspaces yet.</p>
            </div>
          ) : workspaces.map(ws => {
            const domain = RISK_DOMAINS.find(d => d.value === ws.risk_domain);
            const sc = STATUS_CFG[ws.status] || STATUS_CFG.draft;
            return (
              <button key={ws.id} onClick={() => selectWorkspace(ws)}
                className={`w-full text-left px-4 py-3.5 border-b border-slate-50 hover:bg-slate-50 transition-colors ${selected?.id === ws.id ? "bg-blue-50 border-l-2 border-l-blue-600" : ""}`}>
                <div className="flex items-center gap-2 mb-1">
                  <span>{domain?.icon ?? "🔬"}</span>
                  <span className="text-xs font-semibold text-slate-900 truncate flex-1">{ws.name}</span>
                  <ChevronRight size={12} className="text-slate-300 shrink-0" />
                </div>
                <div className="flex items-center gap-2">
                  <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${sc.color}`}>{sc.label}</span>
                  {ws.fork_count > 0 && <span className="text-[10px] text-slate-400 flex items-center gap-0.5"><GitFork size={9} />{ws.fork_count}</span>}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Main */}
      {selected ? (
        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="px-8 py-5 border-b border-slate-200 bg-white">
            <div className="flex items-start justify-between mb-3">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <h2 className="text-lg font-semibold text-slate-900">{selected.name}</h2>
                  <span className={`text-xs px-2 py-0.5 rounded font-medium ${STATUS_CFG[selected.status]?.color}`}>{STATUS_CFG[selected.status]?.label}</span>
                  {repSummary?.confidence_grade && repSummary.confidence_grade !== "insufficient" && (
                    <span className={`text-xs px-2 py-0.5 rounded border font-bold ${CONFIDENCE_CFG[repSummary.confidence_grade]?.color}`}>{CONFIDENCE_CFG[repSummary.confidence_grade]?.label}</span>
                  )}
                </div>
                <p className="text-xs text-slate-500">{selected.description || "No description"}</p>
              </div>
              <div className="flex gap-2">
                <button onClick={() => fork(selected.id)} className="flex items-center gap-1.5 text-xs px-3 py-1.5 border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600"><GitFork size={12} /> Fork</button>
                {selected.status !== "published" && <button onClick={() => publish(selected.id)} className="flex items-center gap-1.5 text-xs px-3 py-1.5 bg-green-600 text-white rounded-lg hover:bg-green-700"><ExternalLink size={12} /> Publish</button>}
              </div>
            </div>
            <div className="flex gap-1">
              {[
                { key: "overview", label: "Overview", icon: <FlaskConical size={12} /> },
                { key: "hypothesis", label: "Hypothesis", icon: <BookOpen size={12} /> },
                { key: "replications", label: `Replications${repSummary?.total ? ` (${repSummary.total})` : ""}`, icon: <Users size={12} /> },
                { key: "manifest", label: "Manifest", icon: <ScrollText size={12} /> },
              ].map(t => (
                <button key={t.key} onClick={() => setTab(t.key)} className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-colors ${tab === t.key ? "bg-slate-900 text-white" : "text-slate-500 hover:bg-slate-50"}`}>
                  {t.icon}{t.label}
                </button>
              ))}
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-8 space-y-5">
            {tab === "overview" && (
              <>
                <div className="grid grid-cols-3 gap-4">
                  {[["Risk Domain", RISK_DOMAINS.find(d => d.value === selected.risk_domain)?.label ?? selected.risk_domain],
                    ["Visibility", selected.visibility], ["Forks", selected.fork_count]].map(([l, v]) => (
                    <div key={l} className="bg-white border border-slate-200 rounded-xl p-4">
                      <div className="text-xs text-slate-400 mb-1">{l}</div>
                      <div className="font-semibold text-slate-900">{v}</div>
                    </div>
                  ))}
                </div>
                {selected.hypothesis && <div className="bg-blue-50 border border-blue-200 rounded-xl p-5"><h4 className="text-xs font-semibold text-blue-500 uppercase tracking-wide mb-2">Hypothesis</h4><p className="text-sm text-blue-900 leading-relaxed">{selected.hypothesis}</p></div>}
                {repSummary && (
                  <div className="bg-white border border-slate-200 rounded-xl p-5">
                    <h4 className="text-sm font-semibold text-slate-900 mb-3">Scientific Confidence</h4>
                    <div className="grid grid-cols-4 gap-3 text-center">
                      {[["Replications", repSummary.total ?? 0], ["Successful", repSummary.successful ?? 0],
                        ["Avg Concordance", repSummary.avg_concordance ? `${Math.round(repSummary.avg_concordance * 100)}%` : "—"],
                        ["Grade", repSummary.confidence_grade ?? "—"]].map(([l, v]) => (
                        <div key={l} className="bg-slate-50 rounded-lg py-3">
                          <div className="text-[11px] text-slate-400">{l}</div>
                          <div className="font-bold text-slate-900">{v}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}

            {tab === "hypothesis" && (
              <>
                <div className="bg-blue-50 border border-blue-200 rounded-xl p-5">
                  <h4 className="text-xs font-semibold text-blue-500 uppercase tracking-wide mb-2">Hypothesis</h4>
                  <p className="text-sm text-blue-900 leading-relaxed">{selected.hypothesis || <em>No hypothesis defined.</em>}</p>
                </div>
                <div className="bg-white border border-slate-200 rounded-xl p-5">
                  <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Protocol</h4>
                  <p className="text-sm text-slate-700 whitespace-pre-wrap leading-relaxed">{selected.protocol || <em>No protocol documented.</em>}</p>
                </div>
              </>
            )}

            {tab === "replications" && (
              <>
                <div className="flex items-center justify-between">
                  <h4 className="font-semibold text-slate-900">Multi-Lab Replication Network</h4>
                  <div className="flex gap-2">
                    <button onClick={() => setShowRepForm(!showRepForm)} className="flex items-center gap-1.5 text-xs px-3 py-1.5 border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600"><Plus size={12} /> Request</button>
                    <button onClick={() => setShowSubmitForm(!showSubmitForm)} className="flex items-center gap-1.5 text-xs px-3 py-1.5 bg-slate-900 text-white rounded-lg hover:bg-slate-700"><CheckCircle2 size={12} /> Submit Results</button>
                  </div>
                </div>
                {showRepForm && (
                  <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-3">
                    <h5 className="text-xs font-semibold text-slate-700">Request Independent Replication</h5>
                    <input value={repForm.lab} onChange={e => setRepForm(f => ({...f, lab: e.target.value}))} placeholder="Lab / organisation name…" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-xs" />
                    <textarea value={repForm.notes} onChange={e => setRepForm(f => ({...f, notes: e.target.value}))} placeholder="Notes…" rows={2} className="w-full border border-slate-200 rounded-lg px-3 py-2 text-xs resize-none" />
                    <div className="flex gap-2">
                      <button onClick={requestReplication} disabled={saving || !repForm.lab} className="bg-slate-900 text-white px-4 py-1.5 rounded-lg text-xs disabled:opacity-40">{saving ? "…" : "Send Request"}</button>
                      <button onClick={() => setShowRepForm(false)} className="text-xs text-slate-400">Cancel</button>
                    </div>
                  </div>
                )}
                {showSubmitForm && (
                  <div className="bg-green-50 border border-green-200 rounded-xl p-4 space-y-3">
                    <h5 className="text-xs font-semibold text-green-800">Submit Replication Results</h5>
                    <input value={submitForm.lab} onChange={e => setSubmitForm(f => ({...f, lab: e.target.value}))} placeholder="Your lab name…" className="w-full border border-green-200 rounded-lg px-3 py-2 text-xs" />
                    <div className="flex items-center gap-3">
                      <label className="text-xs text-slate-600">Concordance:</label>
                      <input type="number" min="0" max="1" step="0.05" value={submitForm.concordance} onChange={e => setSubmitForm(f => ({...f, concordance: e.target.value}))} className="w-24 border border-green-200 rounded-lg px-2 py-1 text-xs" />
                      <label className="flex items-center gap-1.5 text-xs text-slate-600"><input type="checkbox" checked={submitForm.successful} onChange={e => setSubmitForm(f => ({...f, successful: e.target.checked}))} />Successful</label>
                    </div>
                    <div className="flex gap-2">
                      <button onClick={submitReplication} disabled={saving || !submitForm.lab} className="bg-green-700 text-white px-4 py-1.5 rounded-lg text-xs disabled:opacity-40">{saving ? "…" : "Submit"}</button>
                      <button onClick={() => setShowSubmitForm(false)} className="text-xs text-slate-400">Cancel</button>
                    </div>
                  </div>
                )}
                {replications.length === 0
                  ? <div className="text-center py-10 text-slate-400 text-sm border border-dashed border-slate-200 rounded-xl">No replications yet.</div>
                  : replications.map((rep, i) => (
                    <div key={i} className={`border rounded-xl p-4 ${rep.successful ? "border-green-200 bg-green-50" : rep.status === "pending" ? "border-slate-200 bg-white" : "border-red-200 bg-red-50"}`}>
                      <div className="flex items-center gap-2">
                        {rep.status === "pending" ? <Clock size={14} className="text-slate-400" /> : rep.successful ? <CheckCircle2 size={14} className="text-green-600" /> : <CheckCircle2 size={14} className="text-red-500" />}
                        <span className="text-sm font-medium text-slate-800">{rep.lab}</span>
                        {rep.concordance_score !== undefined && <span className="ml-auto text-xs font-bold text-slate-700">{Math.round(rep.concordance_score * 100)}% concordance</span>}
                        <span className={`text-xs px-2 py-0.5 rounded font-medium ${rep.status === "pending" ? "bg-slate-100 text-slate-500" : rep.successful ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
                          {rep.status === "pending" ? "Pending" : rep.successful ? "Replicated ✓" : "Failed"}
                        </span>
                      </div>
                      {rep.notes && <p className="text-xs text-slate-500 mt-1 ml-5">{rep.notes}</p>}
                    </div>
                  ))}
              </>
            )}

            {tab === "manifest" && (
              <>
                <div className="flex items-center justify-between">
                  <h4 className="font-semibold text-slate-900">Reproducibility Manifest</h4>
                  <button onClick={generateManifest} disabled={manifestLoading} className="flex items-center gap-1.5 text-xs px-3 py-1.5 bg-slate-900 text-white rounded-lg hover:bg-slate-700 disabled:opacity-40">
                    {manifestLoading ? <><Spinner size={12} />Generating…</> : <><ScrollText size={12} /> Generate</>}
                  </button>
                </div>
                <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 text-xs text-slate-600">
                  Captures everything needed to replicate this evaluation: seed, temperature, benchmark hashes, model/judge versions, replication command.
                </div>
                {manifest && (
                  <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-slate-700">Generated Manifest</span>
                      <button onClick={() => { navigator.clipboard.writeText(JSON.stringify(manifest, null, 2)); setCopied(true); setTimeout(() => setCopied(false), 2000); }} className="flex items-center gap-1 text-[10px] text-blue-500 hover:underline">
                        {copied ? <><CheckCircle2 size={10} /> Copied</> : <><Copy size={10} /> Copy JSON</>}
                      </button>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      {[["Seed", manifest.seed], ["Temperature", manifest.temperature], ["Judge", manifest.judge_version ?? "auto"], ["Version", manifest.platform_version ?? "v0.6"]].map(([k, v]) => (
                        <div key={k} className="bg-slate-50 rounded-lg p-2">
                          <div className="text-slate-400 text-[10px]">{k}</div>
                          <div className="font-mono font-medium text-slate-800">{v ?? "—"}</div>
                        </div>
                      ))}
                    </div>
                    {manifest.replication_command && <div className="bg-slate-900 rounded-lg p-3 font-mono text-[10px] text-green-400 break-all">{manifest.replication_command}</div>}
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center bg-slate-50">
          <div className="text-center">
            <Beaker size={48} className="text-slate-200 mx-auto mb-4" />
            <h3 className="font-semibold text-slate-700 mb-1">Select a workspace</h3>
            <p className="text-sm text-slate-400">or create one to start your research.</p>
          </div>
        </div>
      )}
    </div>
  );
}