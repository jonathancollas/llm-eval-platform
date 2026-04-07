"use client";
import { useEffect, useState } from "react";
import { campaignsApi } from "@/lib/api";
import type { Campaign } from "@/lib/api";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { Shield, CheckCircle2, AlertTriangle, XCircle } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "https://llm-eval-backend-kqlh.onrender.com/api";

interface PolicyFramework {
  id: string; name: string; description: string; version: string; num_checks: number;
}
interface PolicyCheck {
  id: string; label: string; description: string; score: number; weight: number; status: "pass" | "warn" | "fail";
}
interface PolicyEvaluation {
  model_name: string; policy_name: string; overall_score: number;
  overall_status: "compliant" | "partially_compliant" | "non_compliant";
  checks: PolicyCheck[]; passed: number; total_checks: number;
}

const STATUS_CONFIG = {
  compliant: { label: "Conforme", color: "bg-green-100 text-green-700 border-green-200", icon: CheckCircle2 },
  partially_compliant: { label: "Partiellement conforme", color: "bg-yellow-100 text-yellow-700 border-yellow-200", icon: AlertTriangle },
  non_compliant: { label: "Non conforme", color: "bg-red-100 text-red-700 border-red-200", icon: XCircle },
};

const CHECK_STATUS = {
  pass: { color: "bg-green-500", label: "✓" },
  warn: { color: "bg-yellow-500", label: "!" },
  fail: { color: "bg-red-500", label: "✗" },
};

export default function PolicyPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [frameworks, setFrameworks] = useState<PolicyFramework[]>([]);
  const [selectedCampaign, setSelectedCampaign] = useState<number | null>(null);
  const [selectedPolicy, setSelectedPolicy] = useState<string>("eu_ai_act");
  const [evaluations, setEvaluations] = useState<Record<string, PolicyEvaluation> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    campaignsApi.list().then(cs => setCampaigns(cs.filter(c => c.status === "completed")));
    fetch(`${API_BASE}/policy/frameworks`).then(r => r.json()).then(d => setFrameworks(d.frameworks ?? [])).catch(() => {});
  }, []);

  const runEvaluation = async () => {
    if (!selectedCampaign) return;
    setLoading(true); setError(null); setEvaluations(null);
    try {
      const res = await fetch(`${API_BASE}/policy/evaluate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ campaign_id: selectedCampaign, policy_id: selectedPolicy }),
      });
      if (!res.ok) { const e = await res.json(); throw new Error(e.detail); }
      const data = await res.json();
      setEvaluations(data.evaluations ?? {});
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  };

  return (
    <div>
      <PageHeader title="Compliance & Policy" description="Simulez la conformité réglementaire de vos modèles." />

      <div className="p-8 space-y-6">
        {/* Selector bar */}
        <div className="flex items-end gap-4 flex-wrap">
          <div>
            <label className="text-xs font-medium text-slate-600 mb-1 block">Campagne</label>
            <select value={selectedCampaign ?? ""} onChange={e => setSelectedCampaign(+e.target.value || null)}
              className="border border-slate-200 rounded-lg px-3 py-2 text-sm min-w-64">
              <option value="">— Campagne terminée —</option>
              {campaigns.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs font-medium text-slate-600 mb-1 block">Cadre réglementaire</label>
            <div className="flex gap-2">
              {frameworks.map(f => (
                <button key={f.id} onClick={() => setSelectedPolicy(f.id)}
                  className={`px-4 py-2 rounded-lg text-sm border transition-colors ${
                    selectedPolicy === f.id ? "bg-slate-900 text-white border-slate-900" : "border-slate-200 text-slate-600 hover:bg-slate-50"
                  }`}>
                  {f.id === "eu_ai_act" ? "🇪🇺" : f.id === "hipaa" ? "🏥" : "💰"} {f.name}
                </button>
              ))}
            </div>
          </div>
          <button onClick={runEvaluation} disabled={loading || !selectedCampaign}
            className="flex items-center gap-2 bg-slate-900 text-white px-5 py-2 rounded-lg text-sm hover:bg-slate-700 disabled:opacity-40">
            {loading ? <Spinner size={13} /> : <Shield size={14} />}
            {loading ? "Évaluation…" : "Évaluer la conformité"}
          </button>
        </div>

        {/* Policy description */}
        {frameworks.find(f => f.id === selectedPolicy) && (
          <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 text-xs text-slate-600">
            <span className="font-medium text-slate-800">{frameworks.find(f => f.id === selectedPolicy)?.name}</span>
            {" — "}{frameworks.find(f => f.id === selectedPolicy)?.description}
            <span className="text-slate-400 ml-2">({frameworks.find(f => f.id === selectedPolicy)?.num_checks} checks)</span>
          </div>
        )}

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-600">{error}</div>
        )}

        {/* Results */}
        {evaluations && Object.entries(evaluations).map(([modelName, evalData]) => {
          const status = STATUS_CONFIG[evalData.overall_status];
          const StatusIcon = status.icon;
          return (
            <div key={modelName} className="bg-white border border-slate-200 rounded-xl overflow-hidden">
              {/* Model header */}
              <div className="px-6 py-4 flex items-center justify-between border-b border-slate-100">
                <div>
                  <h3 className="font-medium text-slate-900">{modelName}</h3>
                  <span className="text-xs text-slate-400">{evalData.policy_name}</span>
                </div>
                <div className="flex items-center gap-3">
                  <div className="text-right">
                    <div className="text-2xl font-bold text-slate-900">{Math.round(evalData.overall_score * 100)}%</div>
                    <div className="text-xs text-slate-400">{evalData.passed}/{evalData.total_checks} checks</div>
                  </div>
                  <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border ${status.color}`}>
                    <StatusIcon size={13} />
                    {status.label}
                  </div>
                </div>
              </div>

              {/* Checks grid */}
              <div className="p-6 space-y-2">
                {evalData.checks.map(check => {
                  const cs = CHECK_STATUS[check.status];
                  const pct = Math.round(check.score * 100);
                  return (
                    <div key={check.id} className="flex items-center gap-3">
                      <div className={`w-5 h-5 rounded-full flex items-center justify-center text-white text-[10px] font-bold shrink-0 ${cs.color}`}>
                        {cs.label}
                      </div>
                      <span className="text-xs text-slate-700 w-44 shrink-0">{check.label}</span>
                      <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
                        <div className={`h-full rounded-full transition-all ${
                          check.status === "pass" ? "bg-green-500" : check.status === "warn" ? "bg-yellow-500" : "bg-red-500"
                        }`} style={{ width: `${pct}%` }} />
                      </div>
                      <span className="text-xs font-mono text-slate-500 w-10 text-right">{pct}%</span>
                      <span className="text-[10px] text-slate-400 w-8 text-right">{Math.round(check.weight * 100)}%w</span>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}

        {/* Empty state */}
        {!evaluations && !loading && (
          <div className="bg-slate-50 border border-slate-200 rounded-2xl p-12 text-center">
            <Shield size={40} className="text-slate-300 mx-auto mb-3" />
            <h3 className="font-semibold text-slate-700 mb-1">Simulation de conformité</h3>
            <p className="text-sm text-slate-500 max-w-md mx-auto">
              Sélectionnez une campagne et un cadre réglementaire pour évaluer la conformité de vos modèles.
              Les résultats intègrent le Failure Genome et les données REDBOX.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
