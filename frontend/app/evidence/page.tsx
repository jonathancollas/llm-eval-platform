"use client";
import { useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { FlaskConical, Database, Lightbulb } from "lucide-react";
import { useEvidenceTrials, useEvidenceRwd, useEvidenceRwe } from "@/lib/useApi";

type Tab = "trials" | "rwd" | "rwe";

const GRADE_COLORS: Record<string, string> = {
  A: "bg-green-600 text-white", B: "bg-blue-100 text-blue-700",
  C: "bg-yellow-100 text-yellow-700", D: "bg-red-100 text-red-700",
};

export default function EvidencePage() {
  const [tab, setTab] = useState<Tab>("trials");
  const [selected, setSelected] = useState<any>(null);
  const [showDesign, setShowDesign] = useState(false);

  const { trials, isLoading: loadingTrials } = useEvidenceTrials();
  const { datasets: rwdList, isLoading: loadingRwd } = useEvidenceRwd();
  const { evidence: rweList, isLoading: loadingRwe } = useEvidenceRwe();
  const loading = loadingTrials || loadingRwd || loadingRwe;

  const TABS = [
    { key: "trials" as Tab, label: "🧪 Trials (RCT)", count: trials.length },
    { key: "rwd" as Tab, label: "📊 Real World Data", count: rwdList.length },
    { key: "rwe" as Tab, label: "💡 Evidence (RWE)", count: rweList.length },
  ];

  return (
    <div>
      <PageHeader title="Evidence-Based Evaluation" description="RCT × RWD → RWE — Clinical trial rigor for AI safety science." />

      <div className="p-4 sm:p-8 space-y-6">
        {/* Tabs */}
        <div className="flex gap-2 border-b border-slate-200 pb-3">
          {TABS.map(t => (
            <button key={t.key} onClick={() => setTab(t.key)}
              className={`text-sm px-4 py-2 rounded-t-lg transition-colors ${tab === t.key ? "bg-slate-900 text-white font-medium" : "text-slate-500 hover:bg-slate-50"}`}>
              {t.label} <span className="text-xs opacity-60">({t.count})</span>
            </button>
          ))}
        </div>

        {loading && <div className="flex items-center gap-2 text-slate-400"><Spinner size={16} /> Loading…</div>}

        {/* TRIALS TAB */}
        {tab === "trials" && !loading && (
          <div className="space-y-4">
            <div className="bg-indigo-50 border border-indigo-200 rounded-xl p-4 text-xs text-indigo-700">
              <strong>Randomized Control Trials</strong> — Design controlled experiments with multiple arms, randomization, blinding, and statistical power analysis.
              Compare models/configurations with scientific rigor. Results include p-values, effect sizes, and bootstrap confidence intervals.
            </div>

            {trials.map(t => (
              <div key={t.id} className="bg-white border border-slate-200 rounded-xl p-5">
                <div className="flex items-center gap-3 mb-2">
                  <FlaskConical size={15} className="text-indigo-500" />
                  <span className="font-medium text-slate-900">{t.name}</span>
                  <span className={`text-[10px] px-2 py-0.5 rounded-full ${
                    t.status === "completed" ? "bg-green-100 text-green-700" : "bg-slate-100 text-slate-500"
                  }`}>{t.status}</span>
                  <span className="text-xs text-slate-400">{t.arms} arms · {t.trial_type}</span>
                  {t.p_value != null && <span className="text-xs font-mono text-slate-600 ml-auto">p={t.p_value}</span>}
                  {t.conclusion && <span className={`text-xs px-2 py-0.5 rounded-full ${t.conclusion === "significant" ? "bg-green-100 text-green-700" : "bg-slate-100 text-slate-500"}`}>{t.conclusion}</span>}
                </div>
                {t.hypothesis && <p className="text-xs text-slate-500">{t.hypothesis}</p>}
              </div>
            ))}

            {trials.length === 0 && (
              <div className="text-center py-16 text-slate-400">
                <FlaskConical size={40} className="mx-auto mb-3 text-slate-300" />
                <h3 className="font-semibold text-slate-700 mb-1">No trials yet</h3>
                <p className="text-sm">Design an RCT via <code className="bg-slate-100 px-1.5 py-0.5 rounded text-xs">POST /evidence/trials</code></p>
              </div>
            )}
          </div>
        )}

        {/* RWD TAB */}
        {tab === "rwd" && !loading && (
          <div className="space-y-4">
            <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 text-xs text-emerald-700">
              <strong>Real World Data</strong> — Aggregated production telemetry. Captures how models actually behave in deployment: latency, safety flags, error rates, score distributions.
            </div>

            {rwdList.map(d => (
              <div key={d.id} className="bg-white border border-slate-200 rounded-xl p-5 flex items-center gap-4">
                <Database size={15} className="text-emerald-500 shrink-0" />
                <div className="flex-1">
                  <div className="font-medium text-slate-900 text-sm">{d.name}</div>
                  <div className="text-xs text-slate-400 mt-0.5">{d.total_events} events · Safety rate: {(d.safety_flag_rate * 100).toFixed(1)}%</div>
                </div>
                {d.avg_score != null && <div className="text-right"><div className="text-lg font-bold text-slate-900">{(d.avg_score * 100).toFixed(0)}%</div><div className="text-[10px] text-slate-400">avg score</div></div>}
              </div>
            ))}

            {rwdList.length === 0 && (
              <div className="text-center py-16 text-slate-400">
                <Database size={40} className="mx-auto mb-3 text-slate-300" />
                <h3 className="font-semibold text-slate-700 mb-1">No RWD collected</h3>
                <p className="text-sm">Collect production data via <code className="bg-slate-100 px-1.5 py-0.5 rounded text-xs">POST /evidence/rwd/collect</code></p>
              </div>
            )}
          </div>
        )}

        {/* RWE TAB */}
        {tab === "rwe" && !loading && (
          <div className="space-y-4">
            <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-xs text-amber-700">
              <strong>Real World Evidence</strong> — Synthesizes RCT results with RWD observations. Answers the critical question:
              <em> does the model behave in production as predicted by controlled evaluation?</em>
              Grades: A (strong concordance) → D (insufficient evidence).
            </div>

            {rweList.map(e => (
              <div key={e.id} className="bg-white border border-slate-200 rounded-xl p-5">
                <div className="flex items-center gap-3 mb-3">
                  <Lightbulb size={15} className="text-amber-500" />
                  <span className="font-medium text-slate-900">{e.name}</span>
                  <span className={`text-xs px-2.5 py-1 rounded-full font-bold ${GRADE_COLORS[e.evidence_grade] || GRADE_COLORS.D}`}>
                    Grade {e.evidence_grade}
                  </span>
                </div>
                <div className="grid grid-cols-4 gap-3 text-xs">
                  <div className="bg-indigo-50 rounded-lg p-3"><span className="text-indigo-400">RCT Score</span><div className="font-bold text-indigo-900 mt-1">{e.rct_score != null ? `${(e.rct_score * 100).toFixed(0)}%` : "—"}</div></div>
                  <div className="bg-emerald-50 rounded-lg p-3"><span className="text-emerald-400">RWD Score</span><div className="font-bold text-emerald-900 mt-1">{e.rwd_score != null ? `${(e.rwd_score * 100).toFixed(0)}%` : "—"}</div></div>
                  <div className="bg-slate-50 rounded-lg p-3"><span className="text-slate-400">Concordance</span><div className="font-bold text-slate-900 mt-1">{e.concordance != null ? `${(e.concordance * 100).toFixed(0)}%` : "—"}</div></div>
                  <div className={`rounded-lg p-3 ${(e.behavior_drift ?? 0) < -0.05 ? "bg-red-50" : "bg-green-50"}`}>
                    <span className="text-slate-400">Drift</span>
                    <div className={`font-bold mt-1 ${(e.behavior_drift ?? 0) < -0.05 ? "text-red-700" : "text-green-700"}`}>{e.behavior_drift != null ? `${e.behavior_drift > 0 ? "+" : ""}${(e.behavior_drift * 100).toFixed(1)}%` : "—"}</div>
                  </div>
                </div>
              </div>
            ))}

            {rweList.length === 0 && (
              <div className="text-center py-16 text-slate-400">
                <Lightbulb size={40} className="mx-auto mb-3 text-slate-300" />
                <h3 className="font-semibold text-slate-700 mb-1">No evidence synthesized</h3>
                <p className="text-sm">Run a trial, collect RWD, then synthesize via <code className="bg-slate-100 px-1.5 py-0.5 rounded text-xs">POST /evidence/rwe/synthesize</code></p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
