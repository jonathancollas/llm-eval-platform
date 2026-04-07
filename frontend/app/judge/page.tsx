"use client";
import { useEffect, useState } from "react";
import { campaignsApi, judgeApi } from "@/lib/api";
import type { Campaign } from "@/lib/api";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { AlertTriangle } from "lucide-react";

const JUDGE_MODELS = [
  { id: "claude-sonnet-4-20250514", label: "Claude Sonnet 4", provider: "Anthropic" },
  { id: "openai/gpt-4o", label: "GPT-4o", provider: "OpenAI" },
  { id: "google/gemini-2.0-flash-001", label: "Gemini 2.0 Flash", provider: "Google" },
  { id: "meta-llama/llama-3.3-70b-instruct", label: "Llama 3.3 70B", provider: "Meta" },
];

const CRITERIA = [
  { key: "correctness", label: "Correctness", desc: "Is the answer factually correct?" },
  { key: "helpfulness", label: "Helpfulness", desc: "Is the response helpful and complete?" },
  { key: "safety", label: "Safety", desc: "Does the response avoid harmful content?" },
  { key: "reasoning_quality", label: "Reasoning", desc: "Is the reasoning chain sound?" },
  { key: "factual_accuracy", label: "Factual accuracy", desc: "Are all facts verifiable?" },
];

type Tab = "evaluate" | "agreement" | "bias" | "calibrate";

export default function JudgePage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [selectedJudges, setSelectedJudges] = useState<string[]>(["claude-sonnet-4-20250514"]);
  const [criteria, setCriteria] = useState("correctness");
  const [maxItems, setMaxItems] = useState(30);
  const [evaluating, setEvaluating] = useState(false);
  const [evalResult, setEvalResult] = useState<any>(null);
  const [agreement, setAgreement] = useState<any>(null);
  const [bias, setBias] = useState<any>(null);
  const [summary, setSummary] = useState<any>(null);
  const [tab, setTab] = useState<Tab>("evaluate");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    campaignsApi.list().then(cs => setCampaigns(cs.filter(c => c.status === "completed")));
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    judgeApi.summary(selectedId).then(setSummary).catch(() => {});
    judgeApi.agreement(selectedId).then(setAgreement).catch(() => {});
    judgeApi.bias(selectedId).then(setBias).catch(() => {});
  }, [selectedId]);

  const toggleJudge = (id: string) =>
    setSelectedJudges(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);

  const runEval = async () => {
    if (!selectedId || !selectedJudges.length) return;
    setEvaluating(true); setError(null); setEvalResult(null);
    try {
      const result = await judgeApi.evaluate(selectedId, selectedJudges, criteria, maxItems);
      setEvalResult(result);
      // Refresh metrics
      judgeApi.summary(selectedId).then(setSummary).catch(() => {});
      judgeApi.agreement(selectedId).then(setAgreement).catch(() => {});
      judgeApi.bias(selectedId).then(setBias).catch(() => {});
    } catch (e: any) {
      setError(e.message ?? String(e));
    } finally { setEvaluating(false); }
  };

  const TABS: { key: Tab; label: string }[] = [
    { key: "evaluate", label: "⚖️ Évaluer" },
    { key: "agreement", label: "🤝 Agreement" },
    { key: "bias", label: "🎯 Bias Detection" },
    { key: "calibrate", label: "🔬 Calibration" },
  ];

  return (
    <div>
      <PageHeader title="LLM-as-Judge" description="Évaluation multi-juges avec calibration et détection de biais." />

      <div className="px-8 pt-4 flex gap-1 border-b border-slate-100">
        {TABS.map(({ key, label }) => (
          <button key={key} onClick={() => setTab(key)}
            className={`px-4 py-2.5 text-sm border-b-2 transition-colors ${
              tab === key ? "border-slate-900 text-slate-900 font-medium" : "border-transparent text-slate-400 hover:text-slate-600"
            }`}>{label}</button>
        ))}
      </div>

      <div className="p-8">
        {/* Campaign selector */}
        <div className="mb-6">
          <select value={selectedId ?? ""} onChange={e => setSelectedId(+e.target.value || null)}
            className="border border-slate-200 rounded-lg px-3 py-2 text-sm">
            <option value="">— Campagne terminée —</option>
            {campaigns.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>

        {/* EVALUATE TAB */}
        {tab === "evaluate" && (
          <div className="space-y-6 max-w-3xl">
            <div>
              <label className="text-xs font-medium text-slate-600 mb-2 block">Juges LLM (multi-select)</label>
              <div className="grid grid-cols-2 gap-2">
                {JUDGE_MODELS.map(j => (
                  <button key={j.id} onClick={() => toggleJudge(j.id)}
                    className={`flex items-center gap-3 p-3 rounded-xl border text-left transition-colors ${
                      selectedJudges.includes(j.id) ? "border-slate-900 bg-slate-50" : "border-slate-200 hover:border-slate-300"
                    }`}>
                    <div className={`w-4 h-4 rounded border-2 flex items-center justify-center ${
                      selectedJudges.includes(j.id) ? "border-slate-900 bg-slate-900" : "border-slate-300"
                    }`}>
                      {selectedJudges.includes(j.id) && <span className="text-white text-[10px]">✓</span>}
                    </div>
                    <div>
                      <div className="text-sm font-medium text-slate-900">{j.label}</div>
                      <div className="text-xs text-slate-400">{j.provider}</div>
                    </div>
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="text-xs font-medium text-slate-600 mb-2 block">Critère d'évaluation</label>
              <div className="flex flex-wrap gap-2">
                {CRITERIA.map(c => (
                  <button key={c.key} onClick={() => setCriteria(c.key)}
                    className={`text-xs px-3 py-1.5 rounded-lg transition-colors ${
                      criteria === c.key ? "bg-slate-900 text-white" : "border border-slate-200 text-slate-600 hover:bg-slate-50"
                    }`}>{c.label}</button>
                ))}
              </div>
              <p className="text-xs text-slate-400 mt-1">{CRITERIA.find(c => c.key === criteria)?.desc}</p>
            </div>

            <div>
              <label className="text-xs font-medium text-slate-600 mb-1 block">Max items à juger</label>
              <input type="number" value={maxItems} onChange={e => setMaxItems(+e.target.value)}
                min={5} max={200} className="border border-slate-200 rounded-lg px-3 py-2 text-sm w-32" />
            </div>

            <button onClick={runEval} disabled={evaluating || !selectedId || !selectedJudges.length}
              className="flex items-center gap-2 bg-slate-900 text-white px-6 py-2.5 rounded-lg text-sm font-medium hover:bg-slate-700 disabled:opacity-40">
              {evaluating ? <><Spinner size={13} /> Évaluation en cours ({selectedJudges.length} juges × {maxItems} items)…</> : "Lancer l'évaluation"}
            </button>

            {error && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-xs text-red-600">{error}</div>
            )}

            {evalResult && (
              <div className="bg-green-50 border border-green-200 rounded-xl p-5 space-y-2">
                <div className="text-sm font-medium text-green-800">✅ Évaluation terminée</div>
                <div className="text-xs text-green-600">{evalResult.evaluations_created} évaluations créées sur {evalResult.items_judged} items</div>
                <div className="grid grid-cols-2 gap-3 mt-3">
                  {Object.entries(evalResult.avg_scores ?? {}).map(([judge, score]: any) => (
                    <div key={judge} className="bg-white rounded-lg p-3 border border-green-100">
                      <div className="text-xs text-slate-500 truncate">{judge}</div>
                      <div className="text-lg font-bold text-slate-900">{(score * 100).toFixed(1)}%</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Summary */}
            {summary?.computed && (
              <div className="bg-white border border-slate-200 rounded-xl p-5">
                <h3 className="text-sm font-medium text-slate-900 mb-3">Résumé des évaluations</h3>
                <div className="space-y-2">
                  {Object.entries(summary.judges ?? {}).map(([judge, stats]: any) => (
                    <div key={judge} className="flex items-center gap-3 text-xs">
                      <span className="text-slate-600 w-48 truncate font-medium">{judge}</span>
                      <span className="text-slate-900 font-mono">{(stats.avg_score * 100).toFixed(1)}%</span>
                      <span className="text-slate-400">±{(stats.std_dev * 100).toFixed(1)}%</span>
                      <span className="text-slate-300">{stats.n_evaluations} evals</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* AGREEMENT TAB */}
        {tab === "agreement" && (
          <div className="space-y-4 max-w-2xl">
            {!agreement?.computed ? (
              <div className="bg-slate-50 border border-slate-200 rounded-xl p-8 text-center">
                <p className="text-sm text-slate-500">Lancez une évaluation multi-juges pour voir l'agreement.</p>
              </div>
            ) : Object.keys(agreement.agreement).length === 0 ? (
              <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-5 text-sm text-yellow-700">
                <AlertTriangle size={14} className="inline mr-2" />
                {agreement.note ?? "Il faut au moins 2 juges pour calculer l'agreement."}
              </div>
            ) : (
              <div className="space-y-3">
                {Object.entries(agreement.agreement).map(([pair, stats]: any) => (
                  <div key={pair} className="bg-white border border-slate-200 rounded-xl p-5">
                    <div className="text-sm font-medium text-slate-900 mb-3">{pair}</div>
                    <div className="grid grid-cols-3 gap-4">
                      <div>
                        <div className="text-xs text-slate-400">Cohen's κ</div>
                        <div className={`text-lg font-bold ${stats.cohens_kappa > 0.6 ? "text-green-600" : stats.cohens_kappa > 0.4 ? "text-yellow-600" : "text-red-600"}`}>
                          {stats.cohens_kappa}
                        </div>
                      </div>
                      <div>
                        <div className="text-xs text-slate-400">Pearson r</div>
                        <div className="text-lg font-bold text-slate-900">{stats.pearson_r}</div>
                      </div>
                      <div>
                        <div className="text-xs text-slate-400">Avg diff</div>
                        <div className="text-lg font-bold text-slate-900">{stats.avg_diff}</div>
                      </div>
                    </div>
                    <div className="text-xs text-slate-400 mt-2">{stats.n_items} items comparés</div>
                  </div>
                ))}
                <div className="bg-slate-50 rounded-lg p-3 text-xs text-slate-500 space-y-1">
                  <div><span className="font-medium">κ &gt; 0.8 :</span> Agreement quasi-parfait</div>
                  <div><span className="font-medium">0.6 &lt; κ &lt; 0.8 :</span> Substantiel</div>
                  <div><span className="font-medium">0.4 &lt; κ &lt; 0.6 :</span> Modéré</div>
                  <div><span className="font-medium">κ &lt; 0.4 :</span> Les juges sont en désaccord significatif</div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* BIAS TAB */}
        {tab === "bias" && (
          <div className="space-y-4 max-w-2xl">
            {!bias?.computed ? (
              <div className="bg-slate-50 border border-slate-200 rounded-xl p-8 text-center">
                <p className="text-sm text-slate-500">Lancez une évaluation pour détecter les biais.</p>
              </div>
            ) : bias.biases.length === 0 ? (
              <div className="bg-green-50 border border-green-200 rounded-xl p-5">
                <div className="text-sm font-medium text-green-700">✅ Aucun biais significatif détecté</div>
                <div className="text-xs text-green-500 mt-1">{bias.total_evaluations} évaluations analysées</div>
              </div>
            ) : (
              <div className="space-y-3">
                {bias.biases.map((b: any, i: number) => (
                  <div key={i} className={`border rounded-xl p-4 ${b.magnitude > 0.2 ? "border-red-200 bg-red-50" : "border-yellow-200 bg-yellow-50"}`}>
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${
                        b.bias_type === "length_bias" ? "bg-purple-100 text-purple-700" : "bg-orange-100 text-orange-700"
                      }`}>{b.bias_type === "length_bias" ? "📏 Length bias" : "🎯 Model preference"}</span>
                      <span className="text-xs text-slate-500">{b.judge}</span>
                      <span className="ml-auto text-xs font-mono font-bold text-slate-700">Δ {b.magnitude.toFixed(2)}</span>
                    </div>
                    <p className="text-xs text-slate-600">{b.description}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* CALIBRATE TAB */}
        {tab === "calibrate" && (
          <div className="space-y-4 max-w-2xl">
            <div className="bg-blue-50 border border-blue-200 rounded-xl p-5 text-sm text-blue-700">
              <div className="font-medium mb-1">🔬 Calibration Oracle</div>
              <p className="text-xs text-blue-500">
                Uploadez des labels humains (oracle) pour calibrer les juges LLM.
                Format : JSON array de {`{result_id, score}`} où score est le jugement humain (0-1).
              </p>
            </div>
            <textarea rows={6} placeholder={'[\n  {"result_id": 1, "score": 0.8},\n  {"result_id": 2, "score": 0.2}\n]'}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono resize-none"
              id="oracle-input" />
            <button onClick={async () => {
              if (!selectedId) return;
              try {
                const el = document.getElementById("oracle-input") as HTMLTextAreaElement;
                const labels = JSON.parse(el.value);
                const result = await judgeApi.calibrate(selectedId, labels);
                alert(JSON.stringify(result.calibration, null, 2));
              } catch (e: any) { alert("Erreur: " + e.message); }
            }} disabled={!selectedId}
              className="bg-slate-900 text-white px-5 py-2 rounded-lg text-sm hover:bg-slate-700 disabled:opacity-40">
              Calibrer les juges
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
