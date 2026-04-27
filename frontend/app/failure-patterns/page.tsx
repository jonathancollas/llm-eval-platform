"use client";
import { useEffect, useState, useCallback } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { Badge } from "@/components/Badge";
import {
  AlertTriangle, CheckCircle2, XCircle, Search, RefreshCw,
  ChevronDown, ChevronUp, BookOpen, Shield, Zap, FlaskConical,
} from "lucide-react";
import { API_BASE } from "@/lib/config";

// ── Types ─────────────────────────────────────────────────────────────────────

interface FailureCluster {
  cluster_id: string;
  name: string;
  failure_type: string;
  n_instances: number;
  reproducibility_score: number;
  affected_models: string[];
  representative_traces: string[];
  hypothesis: string;
  is_novel: boolean;
  severity: string;
  common_keywords: string[];
  severity_distribution: Record<string, number>;
  recommended_benchmark: string | null;
  cross_model: boolean;
  queued_at?: string;
  status?: string;
}

interface TaxonomyEntry extends FailureCluster {
  pattern_id: string;
  confirmed_at: string;
  confirmed_by: string;
  reviewer_notes: string;
  eval_creation_required: boolean;
  eval_creation_note: string;
}

interface AnomalyAlert {
  alert_id: string;
  alert_type: string;
  severity: string;
  description: string;
  metric_value: number;
  threshold: number;
  affected_count: number;
  recommendation: string;
  benchmark?: string;
  baseline_score?: number;
  current_score?: number;
  delta?: number;
}

// ── Severity colours ──────────────────────────────────────────────────────────

const SEV_COLOR: Record<string, string> = {
  critical: "bg-red-600 text-white",
  high: "bg-red-100 text-red-700",
  medium: "bg-yellow-100 text-yellow-700",
  low: "bg-green-100 text-green-700",
  unknown: "bg-slate-100 text-slate-500",
};

const ALERT_COLOR: Record<string, string> = {
  impossible_scores: "bg-red-50 border-red-200 text-red-800",
  uniform_scores: "bg-orange-50 border-orange-200 text-orange-800",
  bimodal_collapse: "bg-yellow-50 border-yellow-200 text-yellow-800",
  regression: "bg-red-50 border-red-200 text-red-800",
  improvement: "bg-blue-50 border-blue-200 text-blue-800",
  novel_cluster: "bg-purple-50 border-purple-200 text-purple-800",
};

// ── Tab type ──────────────────────────────────────────────────────────────────

type Tab = "pending" | "taxonomy" | "anomalies";

// ── Expand/collapse cluster card ──────────────────────────────────────────────

function ClusterCard({
  cluster,
  actions,
}: {
  cluster: FailureCluster;
  actions?: React.ReactNode;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border border-slate-200 rounded-xl bg-white shadow-sm hover:shadow-md transition-shadow">
      <div
        className="flex items-start gap-3 p-4 cursor-pointer"
        onClick={() => setExpanded(v => !v)}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-slate-900 text-sm truncate">{cluster.name}</span>
            <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${SEV_COLOR[cluster.severity] ?? SEV_COLOR.unknown}`}>
              {cluster.severity}
            </span>
            {cluster.is_novel && (
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-purple-100 text-purple-700 font-medium">
                NOVEL
              </span>
            )}
            {cluster.cross_model && (
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 font-medium">
                CROSS-MODEL
              </span>
            )}
          </div>
          <div className="text-xs text-slate-500 mt-1">
            {cluster.n_instances} instance{cluster.n_instances !== 1 ? "s" : ""} ·{" "}
            {cluster.affected_models.join(", ")} ·{" "}
            reproducibility {(cluster.reproducibility_score * 100).toFixed(0)}%
          </div>
          <div className="text-xs text-slate-600 mt-1.5 line-clamp-2">{cluster.hypothesis}</div>
        </div>
        <div className="shrink-0 text-slate-400 mt-1">
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </div>
      </div>

      {expanded && (
        <div className="border-t border-slate-100 px-4 pb-4 pt-3 space-y-3">
          {cluster.common_keywords.length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-wider text-slate-400 mb-1">Keywords</div>
              <div className="flex flex-wrap gap-1">
                {cluster.common_keywords.map(kw => (
                  <span key={kw} className="text-[11px] bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full">
                    {kw}
                  </span>
                ))}
              </div>
            </div>
          )}

          {cluster.representative_traces.length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-wider text-slate-400 mb-1">Representative traces</div>
              <div className="space-y-1">
                {cluster.representative_traces.map((trace, i) => (
                  <div key={i} className="text-xs bg-slate-50 border border-slate-200 rounded p-2 font-mono text-slate-700 break-all">
                    {trace || <em className="text-slate-400">empty</em>}
                  </div>
                ))}
              </div>
            </div>
          )}

          {cluster.recommended_benchmark && (
            <div className="text-xs text-slate-600 flex items-center gap-1.5">
              <BookOpen size={12} className="text-slate-400 shrink-0" />
              <span>Suggested benchmark: <span className="font-medium">{cluster.recommended_benchmark}</span></span>
            </div>
          )}

          {actions && (
            <div className="pt-1 border-t border-slate-100 flex gap-2 flex-wrap">
              {actions}
            </div>
          )}
        </div>
      )}

      {/* Always show actions when not expanded but only if they exist */}
      {!expanded && actions && (
        <div className="border-t border-slate-100 px-4 py-2 flex gap-2 flex-wrap">
          {actions}
        </div>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function FailurePatternsPage() {
  const [tab, setTab] = useState<Tab>("pending");
  const [pending, setPending] = useState<FailureCluster[]>([]);
  const [taxonomy, setTaxonomy] = useState<TaxonomyEntry[]>([]);
  const [anomalyScores, setAnomalyScores] = useState("");
  const [anomalyModel, setAnomalyModel] = useState("");
  const [anomalyResult, setAnomalyResult] = useState<{ alerts: AnomalyAlert[]; is_clean: boolean; summary: string } | null>(null);
  const [loading, setLoading] = useState(false);
  const [anomalyLoading, setAnomalyLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [reviewing, setReviewing] = useState<Record<string, boolean>>({});
  const [reviewerName, setReviewerName] = useState("human");
  const [reviewNotes, setReviewNotes] = useState("");
  const [pendingGateNote, setPendingGateNote] = useState("");

  const fetchPending = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/failure-patterns/pending`);
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setPending(data.pending ?? []);
      setPendingGateNote(data.gate_policy ?? "");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchTaxonomy = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/failure-patterns/taxonomy`);
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setTaxonomy(data.taxonomy ?? []);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (tab === "pending") fetchPending();
    else if (tab === "taxonomy") fetchTaxonomy();
  }, [tab, fetchPending, fetchTaxonomy]);

  const confirm = async (clusterId: string, suggestedName?: string) => {
    setReviewing(r => ({ ...r, [clusterId]: true }));
    try {
      const res = await fetch(`${API_BASE}/failure-patterns/${clusterId}/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reviewer: reviewerName || "human",
          notes: reviewNotes,
          suggested_name: suggestedName,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      fetchPending();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setReviewing(r => ({ ...r, [clusterId]: false }));
    }
  };

  const reject = async (clusterId: string) => {
    setReviewing(r => ({ ...r, [clusterId]: true }));
    try {
      const res = await fetch(`${API_BASE}/failure-patterns/${clusterId}/reject`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reviewer: reviewerName || "human", reason: reviewNotes }),
      });
      if (!res.ok) throw new Error(await res.text());
      fetchPending();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setReviewing(r => ({ ...r, [clusterId]: false }));
    }
  };

  const retirePattern = async (patternId: string) => {
    try {
      const res = await fetch(`${API_BASE}/failure-patterns/taxonomy/${patternId}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await res.text());
      fetchTaxonomy();
    } catch (e: any) {
      setError(e.message);
    }
  };

  const runAnomalyCheck = async () => {
    setAnomalyLoading(true);
    setError(null);
    try {
      const scores = anomalyScores.split(/[\s,]+/).map(s => parseFloat(s.trim())).filter(v => !isNaN(v));
      const res = await fetch(`${API_BASE}/failure-patterns/anomalies`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scores, model_name: anomalyModel || "unknown", campaign_id: 0 }),
      });
      if (!res.ok) throw new Error(await res.text());
      setAnomalyResult(await res.json());
    } catch (e: any) {
      setError(e.message);
    } finally {
      setAnomalyLoading(false);
    }
  };

  const filteredPending = pending.filter(c =>
    !search ||
    c.name.toLowerCase().includes(search.toLowerCase()) ||
    c.failure_type.toLowerCase().includes(search.toLowerCase()) ||
    c.common_keywords.some(k => k.includes(search.toLowerCase()))
  );

  const filteredTaxonomy = taxonomy.filter(t =>
    !search ||
    t.name.toLowerCase().includes(search.toLowerCase()) ||
    t.failure_type.toLowerCase().includes(search.toLowerCase())
  );

  const tabs: { id: Tab; label: string; icon: React.ReactNode; count?: number }[] = [
    { id: "pending", label: "Pending Review", icon: <AlertTriangle size={14} />, count: pending.length },
    { id: "taxonomy", label: "Confirmed Taxonomy", icon: <BookOpen size={14} />, count: taxonomy.length },
    { id: "anomalies", label: "Anomaly Detector", icon: <Zap size={14} /> },
  ];

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
        <PageHeader
          title="Failure Patterns"
          description="Automated failure mode discovery with human validation gate — M4 Automated Eval"
        />

        {/* Gate policy notice */}
        <div className="mb-6 p-4 bg-amber-50 border border-amber-200 rounded-xl flex gap-3">
          <Shield size={16} className="text-amber-600 shrink-0 mt-0.5" />
          <div className="text-sm text-amber-800">
            <span className="font-semibold">Human Validation Gate: </span>
            Automated clustering discovers failure pattern candidates. A human reviewer must
            explicitly confirm or reject each cluster before it enters the canonical taxonomy.{" "}
            <span className="font-semibold">Eval case creation is always human-only</span> — no
            auto-generated eval enters the benchmark suite.
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mb-6 bg-white border border-slate-200 rounded-xl p-1 w-fit">
          {tabs.map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                tab === t.id
                  ? "bg-slate-900 text-white"
                  : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              {t.icon}
              {t.label}
              {t.count !== undefined && t.count > 0 && (
                <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-bold ${
                  tab === t.id ? "bg-white text-slate-900" : "bg-slate-100 text-slate-600"
                }`}>
                  {t.count}
                </span>
              )}
            </button>
          ))}
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
            {error}
          </div>
        )}

        {/* ── Pending Review Tab ──────────────────────────────────────────── */}
        {tab === "pending" && (
          <div>
            <div className="flex items-center gap-3 mb-4">
              <div className="relative flex-1 max-w-sm">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  placeholder="Search clusters…"
                  className="w-full pl-8 pr-3 py-2 text-sm border border-slate-200 rounded-lg bg-white"
                />
              </div>
              <div className="flex items-center gap-2">
                <label className="text-xs text-slate-500 whitespace-nowrap">Reviewer:</label>
                <input
                  value={reviewerName}
                  onChange={e => setReviewerName(e.target.value)}
                  placeholder="your name"
                  className="w-28 px-2 py-1.5 text-sm border border-slate-200 rounded-lg bg-white"
                />
              </div>
              <button
                onClick={fetchPending}
                className="flex items-center gap-1.5 px-3 py-2 text-sm text-slate-600 border border-slate-200 rounded-lg hover:bg-slate-50 bg-white"
              >
                <RefreshCw size={13} />
              </button>
            </div>

            {pendingGateNote && (
              <p className="text-xs text-slate-500 mb-4 italic">{pendingGateNote}</p>
            )}

            {loading ? (
              <div className="flex justify-center py-16"><Spinner /></div>
            ) : filteredPending.length === 0 ? (
              <div className="text-center py-16 text-slate-400">
                <CheckCircle2 size={40} className="mx-auto mb-3 text-green-400" />
                <div className="text-sm font-medium text-slate-500">No clusters pending review</div>
                <div className="text-xs mt-1">
                  Run a clustering job from a campaign to discover new failure patterns.
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                {filteredPending.map(cluster => (
                  <ClusterCard
                    key={cluster.cluster_id}
                    cluster={cluster}
                    actions={
                      <>
                        <button
                          disabled={reviewing[cluster.cluster_id]}
                          onClick={() => confirm(cluster.cluster_id, cluster.name)}
                          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
                        >
                          <CheckCircle2 size={12} />
                          Confirm pattern
                        </button>
                        <button
                          disabled={reviewing[cluster.cluster_id]}
                          onClick={() => reject(cluster.cluster_id)}
                          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-white text-red-600 border border-red-200 rounded-lg hover:bg-red-50 disabled:opacity-50"
                        >
                          <XCircle size={12} />
                          Reject
                        </button>
                      </>
                    }
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {/* ── Confirmed Taxonomy Tab ──────────────────────────────────────── */}
        {tab === "taxonomy" && (
          <div>
            <div className="flex items-center gap-3 mb-4">
              <div className="relative flex-1 max-w-sm">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  placeholder="Search taxonomy…"
                  className="w-full pl-8 pr-3 py-2 text-sm border border-slate-200 rounded-lg bg-white"
                />
              </div>
              <button
                onClick={fetchTaxonomy}
                className="flex items-center gap-1.5 px-3 py-2 text-sm text-slate-600 border border-slate-200 rounded-lg hover:bg-slate-50 bg-white"
              >
                <RefreshCw size={13} />
              </button>
            </div>

            {loading ? (
              <div className="flex justify-center py-16"><Spinner /></div>
            ) : filteredTaxonomy.length === 0 ? (
              <div className="text-center py-16 text-slate-400">
                <BookOpen size={40} className="mx-auto mb-3" />
                <div className="text-sm font-medium text-slate-500">No confirmed patterns yet</div>
                <div className="text-xs mt-1">
                  Confirm pending clusters to build the canonical failure taxonomy.
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                {filteredTaxonomy.map(entry => (
                  <div key={entry.pattern_id} className="border border-slate-200 rounded-xl bg-white p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-semibold text-slate-900 text-sm">{entry.name}</span>
                          <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${SEV_COLOR[entry.severity] ?? SEV_COLOR.unknown}`}>
                            {entry.severity}
                          </span>
                          <span className="text-[10px] px-2 py-0.5 rounded-full bg-green-100 text-green-700 font-medium">
                            CONFIRMED
                          </span>
                        </div>
                        <div className="text-xs text-slate-500 mt-1">
                          Confirmed by <span className="font-medium">{entry.confirmed_by}</span> on{" "}
                          {new Date(entry.confirmed_at).toLocaleDateString()}
                          {entry.reviewer_notes && ` · "${entry.reviewer_notes}"`}
                        </div>
                        <div className="mt-2 p-3 bg-amber-50 border border-amber-100 rounded-lg">
                          <div className="text-[10px] uppercase tracking-wider text-amber-600 font-semibold mb-1 flex items-center gap-1">
                            <FlaskConical size={10} /> Eval Creation Required
                          </div>
                          <div className="text-xs text-amber-800">{entry.eval_creation_note}</div>
                        </div>
                      </div>
                      <button
                        onClick={() => retirePattern(entry.pattern_id)}
                        className="text-xs text-slate-400 hover:text-red-500 border border-slate-200 px-2 py-1 rounded-lg hover:border-red-200 transition-colors shrink-0"
                      >
                        Retire
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ── Anomaly Detector Tab ────────────────────────────────────────── */}
        {tab === "anomalies" && (
          <div className="space-y-6">
            <div className="bg-white border border-slate-200 rounded-xl p-5">
              <h3 className="text-sm font-semibold text-slate-900 mb-1">Score Distribution Anomaly Check</h3>
              <p className="text-xs text-slate-500 mb-4">
                Paste a list of evaluation scores (space or comma separated, values 0–1) to check for
                statistical anomalies: impossible scores, suspiciously uniform distributions, or
                bimodal collapse.
              </p>

              <div className="space-y-3">
                <div>
                  <label className="text-xs font-medium text-slate-600 block mb-1">Model name (optional)</label>
                  <input
                    value={anomalyModel}
                    onChange={e => setAnomalyModel(e.target.value)}
                    placeholder="e.g. gpt-4o"
                    className="w-full max-w-xs px-3 py-2 text-sm border border-slate-200 rounded-lg bg-white"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-slate-600 block mb-1">Scores</label>
                  <textarea
                    value={anomalyScores}
                    onChange={e => setAnomalyScores(e.target.value)}
                    placeholder="0.8, 0.9, 0.85, 0.88, 0.87, 0.9, 0.86 …"
                    rows={3}
                    className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg bg-white font-mono resize-none"
                  />
                </div>
                <button
                  onClick={runAnomalyCheck}
                  disabled={anomalyLoading || !anomalyScores.trim()}
                  className="flex items-center gap-2 px-4 py-2 text-sm font-medium bg-slate-900 text-white rounded-lg hover:bg-slate-700 disabled:opacity-50"
                >
                  {anomalyLoading ? <Spinner /> : <Zap size={14} />}
                  Analyse scores
                </button>
              </div>
            </div>

            {anomalyResult && (
              <div className="bg-white border border-slate-200 rounded-xl p-5">
                <div className="flex items-center gap-2 mb-4">
                  {anomalyResult.is_clean ? (
                    <CheckCircle2 size={16} className="text-green-500" />
                  ) : (
                    <AlertTriangle size={16} className="text-amber-500" />
                  )}
                  <span className="font-semibold text-sm text-slate-900">
                    {anomalyResult.is_clean ? "Score distribution looks clean" : "Anomalies detected"}
                  </span>
                  <span className="text-xs text-slate-500">— {anomalyResult.summary}</span>
                </div>

                {anomalyResult.alerts.length > 0 ? (
                  <div className="space-y-3">
                    {anomalyResult.alerts.map(alert => (
                      <div
                        key={alert.alert_id}
                        className={`p-4 border rounded-xl text-sm ${ALERT_COLOR[alert.alert_type] ?? "bg-slate-50 border-slate-200 text-slate-800"}`}
                      >
                        <div className="flex items-center gap-2 mb-1">
                          <span className="font-semibold capitalize">{alert.alert_type.replace(/_/g, " ")}</span>
                          <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-bold ${SEV_COLOR[alert.severity] ?? SEV_COLOR.unknown}`}>
                            {alert.severity}
                          </span>
                        </div>
                        <p className="text-xs mb-2">{alert.description}</p>
                        <p className="text-xs italic opacity-80">
                          <span className="font-medium not-italic">Recommendation:</span> {alert.recommendation}
                        </p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-green-700">
                    No statistical anomalies detected in this score distribution.
                  </p>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
