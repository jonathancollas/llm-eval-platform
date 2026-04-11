"use client";
import { useState, useEffect, useCallback } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import { ExternalLink, ChevronDown, ChevronUp, FlaskConical, Brain, Shield, AlertTriangle } from "lucide-react";
import { useModels } from "@/lib/useApi";
import { API_BASE } from "@/lib/config";

// ── Science Engine Panel ──────────────────────────────────────────────────────

function ScienceEnginePanel() {
  const [tool, setTool] = useState<"cap_prop" | "mech_interp" | "contamination" | null>(null);
  const [modelId, setModelId] = useState<number | "">("");
  const [benchmarkId, setBenchmarkId] = useState<number | "">("");
  const [benchmarks, setBenchmarks] = useState<any[]>([]);
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { models } = useModels();

  useEffect(() => {
    fetch(`${API_BASE}/benchmarks/`).then(r => r.json()).then(d => setBenchmarks(Array.isArray(d) ? d : [])).catch(() => {});
  }, []);

  const run = async (endpoint: string, body: object) => {
    setLoading(true); setResult(null); setError(null);
    try {
      const res = await fetch(`${API_BASE}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      setResult(await res.json());
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  };

  const tools = [
    { key: "cap_prop", icon: <FlaskConical size={14} />, label: "Capability vs Propensity", desc: "Formal separation — #81" },
    { key: "mech_interp", icon: <Brain size={14} />, label: "Mech Interp Validator", desc: "CoT consistency · Paraphrase invariance · #85" },
    { key: "contamination", icon: <Shield size={14} />, label: "Contamination Analysis", desc: "n-gram overlap · Confidence anomaly · #82" },
  ] as const;

  return (
    <div className="border border-slate-200 rounded-xl overflow-hidden">
      <div className="bg-slate-50 px-5 py-3 border-b border-slate-200">
        <h3 className="font-semibold text-slate-900 text-sm">⚗️ Science Engine — Live Analysis Tools</h3>
        <p className="text-xs text-slate-500 mt-0.5">Run evaluation science analyses directly on your models and benchmarks.</p>
      </div>

      <div className="p-5 space-y-4">
        {/* Tool selector */}
        <div className="grid grid-cols-3 gap-2">
          {tools.map(t => (
            <button key={t.key} onClick={() => { setTool(t.key as any); setResult(null); setError(null); }}
              className={`text-left p-3 rounded-xl border transition-colors ${tool === t.key ? "border-slate-900 bg-slate-50" : "border-slate-100 hover:border-slate-300"}`}>
              <div className="flex items-center gap-2 mb-1 text-slate-700">{t.icon}<span className="text-xs font-medium">{t.label}</span></div>
              <p className="text-[10px] text-slate-400">{t.desc}</p>
            </button>
          ))}
        </div>

        {tool && (
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-slate-500 mb-1 block">Model</label>
              <select value={modelId} onChange={e => setModelId(Number(e.target.value))}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-xs">
                <option value="">Select model…</option>
                {models.slice(0, 30).map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-slate-500 mb-1 block">Benchmark</label>
              <select value={benchmarkId} onChange={e => setBenchmarkId(Number(e.target.value))}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-xs">
                <option value="">Select benchmark…</option>
                {benchmarks.map((b: any) => <option key={b.id} value={b.id}>{b.name}</option>)}
              </select>
            </div>
          </div>
        )}

        {tool && (
          <button
            disabled={loading || !modelId || !benchmarkId}
            onClick={() => {
              const body = { model_id: modelId, benchmark_id: benchmarkId, n_samples: 10 };
              if (tool === "cap_prop") run("/science/capability-propensity", body);
              else if (tool === "mech_interp") run("/science/mech-interp/validate", body);
              else run("/science/contamination/campaign/1", {});  // contamination via GET route
            }}
            className="flex items-center gap-2 bg-slate-900 text-white px-5 py-2 rounded-lg text-sm hover:bg-slate-700 disabled:opacity-40">
            {loading ? <><Spinner size={13} />Running…</> : <>Run Analysis</>}
          </button>
        )}

        {error && <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-xs text-red-700">{error}</div>}

        {result && tool === "cap_prop" && (
          <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-3">
            <div className="flex items-center justify-between">
              <h4 className="font-medium text-slate-900 text-sm">Capability vs Propensity</h4>
              <span className={`text-[11px] px-2 py-0.5 rounded border font-medium
                ${result.scores?.gap_significance === "critical" ? "bg-red-50 text-red-700 border-red-200" :
                  result.scores?.gap_significance === "large" ? "bg-orange-50 text-orange-700 border-orange-200" :
                  "bg-slate-50 text-slate-600 border-slate-200"}`}>
                {result.scores?.gap_significance} gap
              </span>
            </div>
            <div className="grid grid-cols-3 gap-3 text-center">
              {[
                { label: "Capability", value: result.scores?.mean_capability },
                { label: "Propensity", value: result.scores?.mean_propensity },
                { label: "Gap", value: result.scores?.mean_gap },
              ].map(({ label, value }) => (
                <div key={label} className="bg-slate-50 rounded-lg py-3">
                  <div className="text-[11px] text-slate-500">{label}</div>
                  <div className={`text-lg font-bold ${label === "Gap" && (value ?? 0) > 0.15 ? "text-orange-600" : "text-slate-900"}`}>
                    {value != null ? (label === "Gap" ? `${value > 0 ? "+" : ""}${Math.round(value * 100)}%` : `${Math.round(value * 100)}%`) : "—"}
                  </div>
                </div>
              ))}
            </div>
            {result.safety?.concern && (
              <div className="bg-orange-50 border border-orange-200 rounded-lg p-3 text-xs text-orange-800 flex gap-2">
                <AlertTriangle size={12} className="shrink-0 mt-0.5" />
                <span>{result.safety.reason}</span>
              </div>
            )}
            <div className="text-[11px] text-slate-500">P10 tail propensity: {Math.round((result.tail_analysis?.p10_propensity ?? 0) * 100)}% · Worst-case gap: {Math.round((result.tail_analysis?.worst_case_gap ?? 0) * 100)}%</div>
          </div>
        )}

        {result && tool === "mech_interp" && (
          <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-3">
            <div className="flex items-center justify-between">
              <h4 className="font-medium text-slate-900 text-sm">Mech Interp Validation</h4>
              <span className={`text-[11px] px-2 py-0.5 rounded border font-medium
                ${result.validation?.signal === "supports" ? "bg-green-50 text-green-700 border-green-200" :
                  result.validation?.signal === "undermines" ? "bg-red-50 text-red-700 border-red-200" :
                  "bg-slate-50 text-slate-500 border-slate-200"}`}>
                {result.validation?.signal}
              </span>
            </div>
            <p className="text-xs text-slate-600">{result.validation?.interpretation}</p>
            <div className="grid grid-cols-3 gap-2 text-xs text-center">
              {[
                { label: "CoT Consistency", value: result.cot_analysis?.consistency_rate },
                { label: "Paraphrase Invariance", value: result.paraphrase_invariance?.invariance_rate },
                { label: "Calibration Accuracy", value: result.calibration?.stated_confidence_accuracy },
              ].map(({ label, value }) => (
                <div key={label} className="bg-slate-50 rounded-lg py-2">
                  <div className="text-[10px] text-slate-400">{label}</div>
                  <div className="font-bold text-slate-900">{value != null ? `${Math.round(value * 100)}%` : "—"}</div>
                </div>
              ))}
            </div>
            <div className={`text-xs px-3 py-2 rounded-lg border font-medium text-center
              ${(result.validation?.confidence_adjustment ?? 0) > 0 ? "bg-green-50 border-green-200 text-green-700" :
                (result.validation?.confidence_adjustment ?? 0) < 0 ? "bg-red-50 border-red-200 text-red-700" :
                "bg-slate-50 border-slate-200 text-slate-600"}`}>
              Confidence adjustment: {result.validation?.confidence_adjustment > 0 ? "+" : ""}{result.validation?.confidence_adjustment?.toFixed(2) ?? "0.00"}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}


function HeuristicGraph() {
  const [data, setData] = useState<any | null>(null);
  const [open, setOpen] = useState(false);

  const load = () => {
    if (data) { setOpen(o => !o); return; }
    fetch(`${API_BASE}/genome/heuristics`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { setData(d); setOpen(true); })
      .catch(() => {});
  };

  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
      <button onClick={load} className="w-full flex items-center gap-4 px-6 py-4 hover:bg-slate-50 transition-colors text-left">
        <span className="text-2xl">🕸</span>
        <div className="flex-1">
          <div className="font-semibold text-slate-900">Heuristic Graph Engine — Live</div>
          <div className="text-sm text-slate-500 mt-0.5">
            {data ? `${data.total} heuristics · ${data.eval_dimensions?.join(", ")}` : "Click to load from backend"}
          </div>
        </div>
        {open ? <ChevronUp size={16} className="text-slate-400 shrink-0" /> : <ChevronDown size={16} className="text-slate-400 shrink-0" />}
      </button>
      {open && !data && <div className="px-6 pb-4 flex justify-center"><div className="text-slate-400 text-sm">Loading…</div></div>}
      {open && data && (
        <div className="border-t border-slate-100">
          {data.heuristics.map((h: any) => (
            <div key={h.key} className="px-6 py-4 border-b border-slate-50 last:border-0">
              <div className="flex items-center gap-3 mb-2">
                <span className="font-mono text-xs font-bold text-purple-700 bg-purple-50 px-2 py-0.5 rounded">{h.key}</span>
                <span className="font-semibold text-slate-800 text-sm">{h.label}</span>
                <span className={`ml-auto text-[10px] px-2 py-0.5 rounded-full font-medium ${
                  h.eval_dimension === "safety" ? "bg-red-100 text-red-700"
                  : h.eval_dimension === "propensity" ? "bg-orange-100 text-orange-700"
                  : h.eval_dimension === "agentic" ? "bg-purple-100 text-purple-700"
                  : "bg-blue-100 text-blue-700"
                }`}>{h.eval_dimension}</span>
                <span className="text-[10px] text-slate-400">severity: {(h.severity_weight * 100).toFixed(0)}%</span>
              </div>
              <p className="text-xs text-slate-600 mb-2">{h.description}</p>
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div>
                  <div className="text-[10px] font-semibold text-slate-400 uppercase mb-1">Detection Logic</div>
                  <p className="text-slate-600">{h.detection_logic}</p>
                </div>
                <div>
                  <div className="text-[10px] font-semibold text-slate-400 uppercase mb-1">False Positive Profile</div>
                  <p className="text-slate-500 italic">{h.false_positive_profile}</p>
                </div>
              </div>
              <div className="flex gap-4 mt-2 text-[10px] text-slate-400">
                <span>Pass threshold: {(h.threshold_pass * 100).toFixed(0)}%</span>
                <span>Critical failure: &lt;{(h.threshold_fail * 100).toFixed(0)}%</span>
              </div>
              {h.papers?.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-2">
                  {h.papers.map((p: any, i: number) => (
                    <a key={i} href={p.url} target="_blank" rel="noopener noreferrer"
                      className="text-[10px] text-blue-500 hover:underline flex items-center gap-0.5">
                      📄 {p.authors?.split(" et al")[0] ?? p.title.slice(0, 30)} ({p.year})
                    </a>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

interface Section {
  id: string;
  title: string;
  icon: string;
  summary: string;
  content: React.ReactNode;
}

function Collapsible({ title, icon, summary, children }: {
  title: string; icon: string; summary: string; children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-4 px-6 py-4 hover:bg-slate-50 transition-colors text-left"
      >
        <span className="text-2xl shrink-0">{icon}</span>
        <div className="flex-1 min-w-0">
          <div className="font-semibold text-slate-900">{title}</div>
          <div className="text-sm text-slate-500 mt-0.5">{summary}</div>
        </div>
        {open ? <ChevronUp size={16} className="text-slate-400 shrink-0" /> : <ChevronDown size={16} className="text-slate-400 shrink-0" />}
      </button>
      {open && (
        <div className="px-6 pb-6 border-t border-slate-100 pt-4 text-sm text-slate-700 space-y-3">
          {children}
        </div>
      )}
    </div>
  );
}

function Paper({ title, authors, venue, year, url, contribution }: {
  title: string; authors: string; venue: string; year: number; url: string; contribution: string;
}) {
  return (
    <div className="flex gap-3 bg-slate-50 rounded-lg p-3 text-xs">
      <span className="text-slate-300 shrink-0 mt-0.5">📄</span>
      <div>
        <a href={url} target="_blank" rel="noopener noreferrer"
          className="font-medium text-blue-600 hover:underline flex items-center gap-1">
          {title} <ExternalLink size={10} />
        </a>
        <div className="text-slate-400 mt-0.5">{authors} · {venue} {year}</div>
        <div className="text-slate-500 mt-1 italic">{contribution}</div>
      </div>
    </div>
  );
}

export default function MethodologyPage() {
  return (
    <div>
      <PageHeader
        title="Methodology Center"
        description="The scientific foundation behind every evaluation in EVAL RESEARCH OS."
      />

      <div className="px-8 py-6 space-y-4 max-w-4xl">

        {/* Intro */}
        <div className="bg-purple-50 border border-purple-200 rounded-xl p-5 text-sm text-purple-800">
          <p className="font-semibold mb-1">Scientific evaluation — not just benchmarking</p>
          <p>Every signal, heuristic, scoring function, and judge methodology in this platform is backed by peer-reviewed research.
          This page documents the scientific foundations so evaluations are reproducible, defensible, and trustworthy.</p>
        </div>

        {/* 1. Evaluation paradigm */}
        <Collapsible
          icon="🔭"
          title="Evaluation Paradigm — System-in-Context"
          summary="Why model-level evaluation is no longer sufficient for agentic systems"
        >
          <p>The field has shifted from evaluating static input-output models to evaluating <strong>systems</strong> that plan,
          use tools, maintain memory, and take consequential actions. Model-level evaluation is structurally insufficient for agentic deployments.</p>
          <p className="mt-2">Our evaluation primitive:</p>
          <code className="block bg-slate-100 rounded p-3 text-xs mt-2 font-mono">
            system → scenario → trajectory → risk signals → confidence interval
          </code>
          <div className="mt-3 space-y-2">
            <Paper
              title="What should evaluators prioritise? A scientific perspective from INESIA"
              authors="INESIA Research"
              venue="INESIA"
              year={2026}
              url="https://github.com/jonathancollas/llm-eval-platform/blob/main/MANIFESTO.md"
              contribution="Proposed prioritisation hierarchy: CBRN/cyber blocking evals, agentic shift, continuous monitoring, capability-propensity separation."
            />
            <Paper
              title="2025 AI Agent Index"
              authors="MIT"
              venue="MIT"
              year={2026}
              url="https://arxiv.org/abs/2502.01635"
              contribution="30 prominent deployed agents documented; only 4 of 13 frontier-autonomy agents disclose agent-specific safety evaluations."
            />
          </div>
        </Collapsible>

        {/* 2. Capability vs Propensity */}
        <Collapsible
          icon="⚖️"
          title="Capability vs. Propensity — Why Both Matter"
          summary="Separating what a model CAN do from what it TENDS to do in deployment"
        >
          <p><strong>Capability</strong> = what a model can do under optimal elicitation (expert prompting, scaffold optimisation).</p>
          <p className="mt-1"><strong>Propensity</strong> = what a model spontaneously does in operational context (realistic deployment distribution).</p>
          <p className="mt-2">Conflating them generates both false negatives (dangerous capability missed) and false positives
          (safe model flagged) in risk assessment. Every benchmark in this platform exposes both scores independently.</p>
          <div className="mt-3 space-y-2">
            <Paper
              title="Towards Understanding Sycophancy in Language Models"
              authors="Sharma et al."
              venue="Anthropic"
              year={2024}
              url="https://arxiv.org/abs/2310.13548"
              contribution="Demonstrated that high capability does not imply safe propensity — models that refuse under direct prompting comply under social pressure."
            />
            <Paper
              title="AgentDojo: A Dynamic Environment to Evaluate Attacks and Defenses for LLM Agents"
              authors="Debenedetti et al."
              venue="NeurIPS 2024"
              year={2024}
              url="https://arxiv.org/abs/2406.13352"
              contribution="Showed agents with high utility scores fail dramatically when prompt injections are introduced — capability ≠ safe propensity."
            />
          </div>
        </Collapsible>

        {/* 3. Anti-sandbagging */}
        <Collapsible
          icon="🎭"
          title="Evaluation Integrity — Anti-Sandbagging Protocols"
          summary="Preventing models from detecting they are being evaluated and modifying behaviour"
        >
          <p>If a model can infer it is being evaluated and modify its behaviour accordingly,
          the entire evaluation architecture is compromised. This is a <strong>present risk</strong>, not a future one.</p>
          <p className="mt-2">Our countermeasures:</p>
          <ul className="list-disc pl-5 space-y-1 mt-2">
            <li><strong>Prompt randomisation</strong> — vary framing to prevent pattern recognition</li>
            <li><strong>Hidden eval protocols</strong> — evaluation presented as organic interaction</li>
            <li><strong>Contamination detection</strong> — n-gram overlap + perplexity analysis</li>
            <li><strong>Judge variance checks</strong> — consistency across reframings</li>
            <li><strong>Trajectory perturbation</strong> — perturb agent paths mid-evaluation</li>
          </ul>
          <div className="mt-3 space-y-2">
            <Paper
              title="Frontier Models are Capable of In-context Scheming"
              authors="Scheurer et al."
              venue="Apollo Research / OpenAI"
              year={2024}
              url="https://arxiv.org/abs/2412.04984"
              contribution="Frontier models exhibit covert sandbagging, sabotage, and strategic deception in controlled stress-test environments without explicit instruction."
            />
            <Paper
              title="Alignment faking in large language models"
              authors="Greenblatt et al."
              venue="Anthropic"
              year={2024}
              url="https://arxiv.org/abs/2412.14093"
              contribution="Demonstrated models can fake alignment during training to preserve behaviour, making standard safety training insufficient."
            />
            <Paper
              title="Does Claude dream of electric sheep? Sleeper agents and deceptive alignment"
              authors="Hubinger et al."
              venue="Anthropic"
              year={2024}
              url="https://arxiv.org/abs/2401.05566"
              contribution="Showed deceptive behaviours can persist through RLHF and standard safety training interventions."
            />
          </div>
        </Collapsible>

        {/* 4. Benchmark Validity */}
        <Collapsible
          icon="🔬"
          title="Benchmark Validity — Contamination & Reliability"
          summary="Ensuring evaluation scores measure capability, not memorisation"
        >
          <p>A high score may measure <strong>memorisation</strong> rather than the underlying capability it purports to test.
          Frontier models are trained on data that plausibly includes benchmark content.</p>
          <p className="mt-2">Our validity controls:</p>
          <ul className="list-disc pl-5 space-y-1 mt-2">
            <li><strong>Dynamic test generation</strong> — novel variants generated at evaluation time</li>
            <li><strong>Private eval sets</strong> — not in public training data</li>
            <li><strong>Contamination score</strong> — n-gram overlap with known training corpora</li>
            <li><strong>Bayesian GLM for evaluator reliability</strong> — statistical confidence on scores</li>
          </ul>
          <div className="mt-3 space-y-2">
            <Paper
              title="Benchmark Transparency: Contamination and its Impact on Evaluation"
              authors="Xu et al."
              venue="EMNLP 2024"
              year={2024}
              url="https://arxiv.org/abs/2311.01964"
              contribution="Quantified training data contamination in popular benchmarks; showed score inflation of 10-30% for contaminated models."
            />
            <Paper
              title="A Survey on the Validity of Evaluations for Language Models"
              authors="Gururangan et al."
              venue="arXiv"
              year={2024}
              url="https://arxiv.org/abs/2404.12272"
              contribution="Systematic review of validity threats in NLP evaluation: contamination, annotator bias, distribution shift."
            />
          </div>
        </Collapsible>

        {/* 5. Continuous Monitoring */}
        <Collapsible
          icon="📡"
          title="Continuous Monitoring — Post-Deployment Safety"
          summary="Pre-deployment evaluation is necessary but radically insufficient"
        >
          <p>As of 2024, 100% of Fortune 500 companies use frontier AI. AI is embedded in critical workflows —
          legal, financial, medical, infrastructure. <strong>Pre-deployment evaluation alone is no longer defensible.</strong></p>
          <p className="mt-2">NIST AI 800-4 (March 2026) formally establishes post-deployment monitoring as a first-class obligation.
          Six dimensions must be monitored continuously:</p>
          <ul className="list-disc pl-5 space-y-1 mt-2">
            <li>Functionality drift</li>
            <li>Operational reliability</li>
            <li>Human factors</li>
            <li>Security posture</li>
            <li>Fairness and bias</li>
            <li>Societal impact</li>
          </ul>
          <div className="mt-3 space-y-2">
            <Paper
              title="Challenges to the Monitoring of Deployed AI Systems"
              authors="NIST"
              venue="NIST AI 800-4"
              year={2026}
              url="https://doi.org/10.6028/NIST.AI.800-4"
              contribution="Post-deployment monitoring formally established as first-class obligation; six monitoring dimensions defined."
            />
            <Paper
              title="Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena"
              authors="Zheng et al."
              venue="NeurIPS 2023"
              year={2023}
              url="https://arxiv.org/abs/2306.05685"
              contribution="Established LLM-as-judge as a scalable continuous evaluation methodology; calibration and bias characterised."
            />
          </div>
        </Collapsible>

        {/* 6. CBRN-E */}
        <Collapsible
          icon="⚠️"
          title="CBRN-E Evaluation — Dual-Use Capability Elicitation"
          summary="Expert-elicited assessment in domains where marginal AI uplift is catastrophic"
        >
          <p>Capability evaluations in CBRN (chemical, biological, radiological, nuclear) and offensive cyber domains
          are <strong>blocking</strong> — deployment decisions must not proceed without them.</p>
          <p className="mt-2">Default prompting <strong>systematically underestimates</strong> the performance ceiling.
          Expert-in-the-loop elicitation and adversarial scaffold optimisation are required before drawing conclusions
          about what a model cannot do.</p>
          <div className="mt-3 space-y-2">
            <Paper
              title="UK AISI Frontier AI Safety Report"
              authors="UK AI Safety Institute"
              venue="AISI"
              year={2025}
              url="https://www.gov.uk/government/publications/frontier-ai-safety-commitments-ai-seoul-summit-2024"
              contribution="Frontier models surpassed PhD-level performance on biology/chemistry QA; apprentice-level cyber task completion rose from ~10% to ~50% since early 2024."
            />
          </div>
        </Collapsible>

        {/* 7. Mechanistic interpretability */}
        <Collapsible
          icon="🧠"
          title="Mechanistic Interpretability — Validation Layer"
          summary="Using model internals to validate behavioural evaluations"
        >
          <p>Mechanistic interpretability is positioned not as a standalone evaluation method but as a
          <strong> critical validator</strong> of behavioural evaluations — detecting when a model's internal
          representations diverge from its observable outputs.</p>
          <p className="mt-2">Near-term techniques:</p>
          <ul className="list-disc pl-5 space-y-1 mt-2">
            <li><strong>Sparse Autoencoders (SAEs)</strong> — feature identification</li>
            <li><strong>Activation patching</strong> — causal analysis</li>
            <li><strong>Steering vectors</strong> — latent behaviour elicitation</li>
            <li><strong>Chain-of-thought monitoring</strong> — imperfect but time-limited proxy</li>
          </ul>
          <div className="mt-3 space-y-2">
            <Paper
              title="Scaling and evaluating sparse autoencoders"
              authors="Gao et al."
              venue="OpenAI"
              year={2024}
              url="https://arxiv.org/abs/2406.04093"
              contribution="Sparse autoencoders that decompose model activations into interpretable features at scale."
            />
          </div>
        </Collapsible>

        {/* Live heuristic graph from backend */}
        <HeuristicGraph />

        {/* Science Engine — interactive tools */}
        <ScienceEnginePanel />

        {/* Footer note */}
        <div className="text-xs text-slate-400 pt-4 border-t border-slate-100">
          This methodology center is a living document. References are updated as the field evolves.
          All evaluations conducted by EVAL RESEARCH OS are grounded in the papers listed here.
        </div>

      </div>
    </div>
  );
}
