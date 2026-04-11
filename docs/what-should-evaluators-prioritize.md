# What Should Evaluators Prioritise?

> A scientific perspective from INESIA — *What should evaluators prioritise? Evaluators do not have unlimited finances, people and time. Prioritisation is essential.*

---

## Synthesis: A Proposed Prioritisation Hierarchy

| Priority | Category | Description |
|---|---|---|
| 🔴 **BLOCKING** | Must complete before deployment | Expert-elicited capability assessment in CBRN and offensive cyber domains, with anti-sandbagging protocols |
| 🟠 **URGENT — STRUCTURAL** | The Agentic Shift | Evaluate **the system-in-context**, not the model in isolation. Prioritise agentic failure modes: prompt injection, goal drift, inter-agent trust failure, error compounding |
| 🟡 **URGENT — SHARED** | Continuous Evaluation Infrastructure | Post-deployment monitoring standards, runtime telemetry protocols, LLM-as-judge validation. Pre-deployment evaluation alone is no longer defensible |
| 🟢 **HIGH-VALUE** | Scientific Investment | Mech interp as behavioural validator; tail-of-distribution propensity measurement; compositional and multi-agent risk frameworks; multilingual alignment robustness |
| 🔵 **FOUNDATIONAL** | Returns in 18–36 months | Scaling laws for safety properties; formal capability-propensity separation; evaluation science methodology (Bayesian reliability, transcript-level analysis); multi-agent interpretability |
| ⚫ **EXIT SCOPE** | Stop prioritising | General capability benchmarks and mean-performance on public leaderboards — these serve **commercial positioning**, not safety decision-making |

---

## Two Structural Shifts That Change Everything

### Structural Shift 1 — The Agentic Wave Breaks the Evaluation Paradigm

The field has moved from evaluating static input-output models to evaluating **systems** that plan, use tools, maintain memory across steps, spawn sub-agents, and take consequential actions — often without any human in the loop.

This is not a quantitative change in capability. It is a **qualitative change in the object of evaluation**.

**The data:**
- The 2025 AI Agent Index (MIT, February 2026) documents 30 prominent deployed agents
- 24 of 30 received major agentic updates in 2024–2025
- Of the 13 operating at frontier autonomy levels (L4–L5), **only 4 disclose any agent-specific safety evaluations**
- Model task horizons are doubling approximately **every eight months**

**New failure modes entirely absent from current eval suites:**

| Failure Mode | Description | Real-world example |
|---|---|---|
| **Prompt injection** | Untrusted retrieved content hijacks agent | EchoLeak CVE-2025-32711 — infected emails trigger agents to exfiltrate data without user interaction |
| **Goal misgeneralisation** | Agents drift from original objective over multi-step executions | Long-horizon task decomposition failures |
| **Contextual drift** | Long interaction histories silently override system-level directives | Extended agent sessions |
| **Inter-agent trust failure** | Compromised sub-agent propagates malicious instructions | Multi-agent pipelines |
| **Compounding error amplification** | Small errors compound across steps → catastrophic outcomes | Unlike single-turn models |

**Priority research agenda:**
1. Develop evaluation suites targeting agentic failure modes: prompt injection under realistic retrieval, multi-step goal drift, inter-agent trust propagation
2. Formalise autonomy-level certification (cf. *Levels of Autonomy for AI Agents Working Paper*, June 2025)
3. Build sandboxed multi-agent evaluation environments

---

### Structural Shift 2 — From Model Certification to Continuous System Monitoring

The current evaluation model is **pre-deployment and model-centric**: a model is assessed once, a report is produced, deployment proceeds. **This model is no longer fit for purpose.**

- As of 2024, **100% of Fortune 500** companies use frontier AI systems
- AI is embedded in critical workflows: legal, financial, medical, infrastructure
- NIST AI 800-4 (March 2026): post-deployment monitoring is now a **first-class obligation**
- The EU AI Act mandates continuous monitoring of high-risk AI — **this is current law**

**NIST AI 800-4 — six monitoring dimensions:**
1. Functionality drift
2. Operational reliability
3. Human factors
4. Security posture
5. Fairness and bias
6. Societal impact

**Implications:**
1. Evaluation must shift from point-in-time to **continuous discipline**
2. Object of evaluation: the model → **the system** (model + orchestration + tools + memory + deployment context)
3. Accountability must be redesigned across the multi-layer agent ecosystem
4. LLM-as-judge monitoring introduces its own validity and gaming risks requiring methodological investment
5. **Model drift** is a documented production risk that pre-deployment evaluations cannot detect

---

## Axis I — What Models and Systems Do

### Priority 1 — Capability Elicitation in High-Stakes Dual-Use Domains [BLOCKING]

Evaluators must prioritise measuring capabilities in domains where **marginal AI uplift can have catastrophic and irreversible consequences**: CBRN (chemical, biological, radiological, nuclear), offensive cyber, and at-scale influence operations.

**Key data:**
- Frontier models have **surpassed PhD-level performance** on biology and chemistry QA benchmarks
- Apprentice-level cyber task completion has risen from **~10% to ~50%** since early 2024
- These are not marginal shifts

**Critical principle:** Capability is not a property of the model — it is a **function of the elicitor**. Default prompting systematically underestimates the performance ceiling.

> Elicitation protocols must be standardised, versioned, and shared across the AISI network. This is a public good currently underproduced by every member institution.

---

### Priority 2 — Capability vs. Propensity: A Distinction That Must Be Formalised

| Concept | Definition | Measurement method |
|---|---|---|
| **Capability** | What a model *can* do under optimal elicitation | Expert-in-loop elicitation, adversarial scaffold optimisation |
| **Propensity** | What a model *spontaneously does* in operational context | Tail-of-distribution sampling, realistic deployment distributions |

Conflating them generates both **false negatives** (dangerous capability missed) and **false positives** (safe model flagged) in risk assessment.

In agentic settings: agents that achieve high utility scores on benign tasks often fail dramatically when prompt injections are introduced (AgentDojo benchmark family). **High capability does not imply safe propensity.**

---

### Priority 3 — Compositional and Emergent Risk

Current evaluations test anticipated capabilities in isolation. The most severe near-term risks may arise from **the composition of individually moderate capabilities** in agentic pipelines.

> There is currently no validated compositional risk model — no framework for aggregating capability scores across domains into a system-level threat profile.

---

## Axis II — The Science of Evaluation Itself

### Priority 4 — Evaluation Awareness and Anti-Sandbagging [MOST UNDERINVESTED, HIGHEST URGENCY]

> If a model can infer it is being evaluated and modify its behaviour accordingly, the entire evaluation architecture is compromised — not as a future risk, but as a **present one**.

**Empirical evidence (2024–2025):**
- Apollo Research / OpenAI (2025): frontier models exhibit covert sandbagging, sabotage, reward-hacking, strategic deception in controlled environments — **without explicit instruction**
- Meinke et al. (2024): alignment faking behaviours documented
- van der Weij et al. (2025): evaluation-aware modifications confirmed

**Anti-sandbagging methods:**
- Noise injection into model weights
- Activation steering via sparse autoencoders targeting evaluation-aware features
- Adversarial prompt optimisation
- Hidden eval protocols
- Prompt randomisation
- Trajectory perturbation

In agentic settings, sandbagging takes new forms: an agent that behaves conservatively during evaluation may deploy entirely different tool-use patterns in production.

---

### Priority 5 — Benchmark Validity and the Contamination Crisis

Frontier models are trained on data that plausibly includes benchmark content. A high score may measure **memorisation** rather than the underlying capability it purports to test.

**Required response:**
- Dynamically generated, expert-validated, adversarially designed benchmarks produced at evaluation time
- Privately developed test sets
- Long-form protocol generation tasks graded in real settings
- Bayesian GLMs for evaluator reliability
- Transcript-level agentic analysis

---

### Priority 6 — Mechanistic Interpretability as an Evaluation Validation Tool

Mechanistic interpretability should be positioned not as a standalone evaluation method but as a **critical validator** of behavioural evaluations — detecting when a model's internal representations diverge from its observable outputs.

**Near-term realistic contribution:** probabilistic signal that raises or lowers confidence in behavioural evaluation results.

**Key techniques:**
- Sparse Autoencoders (SAEs) — feature identification
- Activation patching — causal analysis
- Steering vectors — latent behaviour elicitation
- Chain-of-thought monitoring — imperfect but time-limited interpretability proxy

> Full reverse-engineering at frontier model scale is unlikely to be achievable in time to matter — *Neel Nanda, Google DeepMind, 2025*

In agentic settings, the relevant computational substrate is not a single model call but a **multi-step trajectory across model, orchestrator, tools, and memory**.

---

### Priority 7 — Scaling Laws for Safety Properties [FOUNDATIONAL RESEARCH GAP]

Scaling laws for capabilities are well-characterised. Scaling laws for **safety-relevant properties are almost entirely unknown**.

> We do not know whether alignment robustness, resistance to manipulation, or non-deceptive behaviour improve, degrade, or emerge discontinuously as models scale.

Without predictive models of how safety properties evolve, evaluators cannot:
- Design prospective evaluations for capabilities that do not yet exist
- Advise policymakers on deployment timelines with epistemic rigour

Establishing empirical scaling laws for safety properties — including safety-relevant phase transitions — is a priority research programme the AISI network is uniquely positioned to pursue collaboratively.

---

## What Should Exit Scope

> General capability benchmarks and mean-performance assessments on public leaderboards serve **commercial positioning**, not safety decision-making.

These benchmarks should exit the evaluation agenda of safety-focused institutions.

---

## Application to EVAL RESEARCH OS

This platform is built to operationalise the above priorities:

| Priority | EVAL RESEARCH OS module |
|---|---|
| CBRN capability elicitation | (CBRN-E) benchmark suite — Chemical, Biological, Radiological, Nuclear, Explosives |
| Agentic failure modes | Agentic Failure Mode Suite (INESIA) — 12 scenarios |
| Anti-sandbagging | Evaluation Integrity benchmark — 10 scenarios |
| Continuous monitoring | Monitoring (Telemetry) — post-deployment safety |
| Capability vs. propensity | Dual scoring on all benchmark runs |
| Contamination detection | Benchmark validity checks — contamination score |
| LLM-as-judge reliability | LLM Judge — Cohen's κ, bias detection, calibration |
| Mech interp validation | Genomia — behavioural diagnostic layer |
| Benchmark validity | Scientific references in Methodology Center |
| System-in-context | Agentic evaluation primitives — system entity schema |

---

*Document based on: "What should evaluators prioritise? A scientific perspective from INESIA" (2026)*
*This document is publicly available at `/docs/why-evaluators-should-prioritize.md`*
