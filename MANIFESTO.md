# Manifeste — Plateforme d'évaluation ouverte de l'INESIA

> *« Faire avancer la science de l'évaluation et de la sécurité de l'IA »*
> — Feuille de route INESIA 2026-2027

---

## Pourquoi cette plateforme existe

Les systèmes d'IA franchissent de nouveaux seuils de complexité. Capables de raisonnement multimodal, d'interaction avec des environnements hybrides, et bientôt d'auto-amélioration, ils s'imposent dans tous les champs de la société — y compris ceux qui touchent aux intérêts fondamentaux de la Nation.

Face à cette réalité, les méthodes d'évaluation conçues pour des systèmes fermés, monofonctionnels et statiques montrent leurs limites. Il ne suffit plus de mesurer une performance : il faut détecter des comportements inattendus, quantifier des incertitudes, évaluer la robustesse, l'alignement, la résilience, et les risques d'usage détourné.

L'évaluation de l'IA est devenue un enjeu stratégique à part entière.

Cette plateforme est l'infrastructure technique ouverte de l'INESIA pour répondre à cet enjeu. Elle est conçue pour être **rigoureuse, reproductible, souveraine et contributive**.

---

## Mission

Fournir à la communauté scientifique, aux régulateurs, aux industriels et à la société civile **un outil commun d'évaluation des modèles et systèmes d'IA avancés**, aligné sur la feuille de route de l'INESIA 2026-2027 et interopérable avec les initiatives européennes et internationales (réseau INAIMES — ex-réseau des AI Safety Institutes, AI Office de la Commission européenne).

---

## Trois pôles, une plateforme

### Pôle 1 — Appui à la régulation

La plateforme met des outils d'évaluation à la disposition des autorités françaises de surveillance du marché dans le cadre de la mise en œuvre du Règlement européen sur l'IA (RIA). Elle permet de :

- **Tester la conformité** des systèmes d'IA à haut risque selon des protocoles standardisés et réplicables
- **Détecter les contenus synthétiques** (texte, image, audio, vidéo) via une bibliothèque de référence open-source maintenue en conditions réelles (Projet n°3)
- **Évaluer la cybersécurité** des systèmes d'IA et des produits intégrant de l'IA — projet SEPIA, en lien avec l'ANSSI (Projet n°4)

### Pôle 2 — Risques systémiques

La plateforme opérationnalise l'évaluation des risques que les modèles avancés peuvent faire peser sur les intérêts collectifs. Quatre domaines prioritaires, dans l'ordre de criticité :

**1. CBRN-E** — Évaluation de l'uplift potentiel des modèles dans les domaines chimique, biologique, radiologique, nucléaire et explosif. Seuils d'alerte stricts, protocoles non publiés dans leur intégralité.

**2. Cybersécurité offensive** — Assistance à l'exploitation de vulnérabilités, génération de code malveillant, contournement de systèmes de détection. En lien avec l'ANSSI.

**3. Manipulations de l'information d'origine étrangère** — Génération de contenus de désinformation, opérations d'influence, ingérence dans les processus démocratiques européens. En lien avec le SGDSN et Viginum.

**4. Risques liés aux systèmes agentiques** — Autonomie non sanctionnée, planification multi-étapes sans supervision humaine, comportements émergents dans des environnements multi-agents, désalignement progressif, jusqu'aux scénarios de perte de contrôle (*loss of control*).

Ces évaluations s'appuient sur une méthodologie documentée publiquement, alignée sur les travaux du réseau INAIMES (UK AISI, METR, US AIST, AI Office).

### Pôle 3 — Performance et fiabilité

La plateforme soutient l'émulation et l'innovation dans l'écosystème français de l'IA :

- Organisation de **challenges ouverts** sur des tâches d'évaluation prioritaires (Projet n°8)
- Benchmarks de **performance en français** et sur des cas d'usage européens
- Comparaisons transparentes et reproductibles entre modèles ouverts et propriétaires

---

## Quatre principes fondamentaux

### 1. Rigueur scientifique

Chaque évaluation est **reproductible** : seed fixé, version du modèle tracée, hash des prompts enregistré, résultats archivés. Les protocoles sont documentés et révisables par la communauté. Aucun résultat publié sans traçabilité complète.

### 2. Souveraineté

La plateforme est **self-hosted**, open source, et ne dépend d'aucun fournisseur cloud étranger pour son cœur fonctionnel. Les données d'évaluation ne quittent pas l'infrastructure de l'opérateur. Les benchmarks sont développés indépendamment des labs qui produisent les modèles évalués.

### 3. Indépendance

L'INESIA évalue les modèles de façon **impartiale** — modèles français et étrangers, ouverts et propriétaires, avec les mêmes protocoles et les mêmes métriques. Aucun résultat n'est modulé par des considérations commerciales ou diplomatiques.

### 4. Ouverture contributive

Les benchmarks sont **publics et contributifs** : toute organisation (académique, industrielle, associative) peut proposer de nouvelles tâches via pull request. Les résultats agrégés sont publiés. La gouvernance des benchmarks est transparente.

---

## Ce que la plateforme évalue

### Benchmarks académiques et de performance
Standards internationaux adaptés au contexte francophone : MMLU, HellaSwag, ARC, TruthfulQA, GSM8K, HumanEval, MATH, BIG-Bench Hard — et leurs équivalents en français développés par l'INESIA et ses partenaires.

### Benchmarks de sécurité et d'alignement
- Refus appropriés face à des requêtes dangereuses (calibration sur-refus / sous-refus)
- Résistance aux injections de prompt et aux tentatives de contournement
- Cohérence comportementale entre contextes supervisés et non supervisés
- Détection de déception et de dissimulation d'intentions

### Benchmarks frontier (risques systémiques)
Protocoles inspirés de METR et UK AISI, adaptés au contexte réglementaire et géopolitique européen :

| Domaine | Description | Criticité |
|---|---|---|
| CBRN-E | Uplift dans les domaines chimique, biologique, radiologique, nucléaire, explosif | Maximale |
| Cybersécurité offensive | Exploitation de vulnérabilités, génération de malware | Haute |
| Manipulation information d'origine étrangère | Désinformation, influence, ingérence | Haute |
| Systèmes agentiques | Autonomie, désalignement, loss of control | Haute |

### Benchmarks custom
Toute organisation peut importer ses propres datasets au format JSON standardisé.

---

## Architecture technique

La plateforme est conçue pour fonctionner sur une infrastructure légère (desktop ou serveur modeste), sans dépendance à des services managés cloud :

- **Backend** : FastAPI + SQLite, évaluation asynchrone native
- **Eval engine** : Plugin-based, compatible lm-evaluation-harness (EleutherAI)
- **Modèles** : Ollama (local) + LiteLLM (proxy unifié cloud), OpenRouter
- **Rapports** : Génération narrative assistée par IA, exportable en Markdown/PDF
- **Déploiement** : Docker Compose, clonage en une commande

---

## Feuille de route technique (alignée sur INESIA 2026-2027)

| Jalon | Contenu | Échéance |
|---|---|---|
| v0.1 (actuel) | Pipeline éval, 4 benchmarks built-in, dashboard | Déployé |
| v0.2 | Intégration lm-eval-harness, catalogue OpenRouter | T2 2026 |
| v0.3 | Benchmarks en français (MMLU-FR, SafetyFR) | T3 2026 |
| v0.4 | Leaderboard public, API de soumission de modèles | T3 2026 |
| v0.5 | Module frontier complet (CBRN-E, cyber, agentique) | T4 2026 |
| v1.0 | Interopérabilité réseau INAIMES, authentification multi-org | T1 2027 |

---

## Contribuer

La plateforme est open source. Les contributions sont bienvenues sous toutes leurs formes :

- **Benchmarks** — nouveaux datasets, nouvelles tâches frontier
- **Runners** — intégration de nouveaux moteurs d'évaluation
- **Documentation** — protocoles, méthodologies, guides
- **Traductions et adaptation** — contexte francophone et européen

→ `github.com/[dépôt à définir pour la production]`

---

## Licence

Ce projet est publié sous **double licence** :

- **Licence Ouverte / Open Licence 2.0 (Etalab)** — pour les utilisateurs français et les administrations publiques
- **Apache License 2.0** — pour les utilisateurs internationaux et les organisations partenaires étrangères

L'utilisateur peut choisir l'une ou l'autre selon sa situation. Voir le fichier `LICENSE` pour le texte complet.

---

## Références

- Feuille de route INESIA 2026-2027, SGDSN/DGE
- METR — Model Evaluation & Threat Research
- UK AISI — AI Safety Institute, DSIT
- Réseau INAIMES — International Network for Advanced AI Measurement, Evaluation and Science
- EleutherAI — lm-evaluation-harness
- Règlement européen sur l'intelligence artificielle (RIA / AI Act)

---

*INESIA — Institut national pour l'évaluation et la sécurité de l'intelligence artificielle*
*Sous pilotage SGDSN / DGE — Partenaires : ANSSI, Inria, LNE, PEReN*
*https://www.sgdsn.gouv.fr/nos-missions/anticiper-et-prevenir/evaluer-et-securiser-lia*

---

## Mercury Retrograde — The Research Operating System

> *"The evaluation paradigm has broken. Model scores are no longer enough. Systems must be evaluated in context and in production."*

**Mercury Retrograde** is the technical codename for INESIA's evaluation platform. The name is deliberately chosen:

- **Mercury** — the Roman messenger god, patron of communication and intelligence
- **Retrograde** — the apparent backward motion that reveals hidden forces; in our context, the anomalies, regressions, and unexpected behaviours that standard evaluation misses

Mercury Retrograde is not a benchmark dashboard. It is the **scientific infrastructure layer for frontier AI risk discovery, validation, and replication**.

### What Mercury Retrograde is

Mercury Retrograde is the **research operating system for frontier AI evaluation**:

- a platform to design, run, reproduce, and compare evaluations,
- a system to discover failure modes before they become incidents,
- a shared scientific layer for independent replication and confidence grading.

### What Mercury Retrograde is not

Mercury Retrograde is **not**:

- a vanity leaderboard optimized for marketing,
- a static benchmark scorecard detached from deployment context,
- a black-box compliance checklist without methodological transparency.

Our objective is decision-grade evidence, not score inflation.

---

## Core Primitives

Mercury Retrograde is organized around six primitives:

1. **System** — The evaluated object in context: model(s), orchestration, tools, memory, and policies.
2. **Scenario** — A test situation with explicit assumptions, threat model, and intended capability/risk target.
3. **Trajectory** — The multi-step execution trace of a system under scenario conditions.
4. **Risk Signal** — A measurable indicator of concerning behavior (e.g., unsafe assistance, drift, hidden strategy, policy bypass).
5. **Evidence** — Structured, reproducible artifacts (inputs, outputs, metadata, seeds, versions, logs) supporting claims.
6. **Confidence** — A quantitative and qualitative estimate of reliability based on replication quality and methodological strength.

These primitives anchor every evaluation artifact in the platform.

---

## Scientific Doctrine

### Doctrine 1 — Capability before propensity

We distinguish two fundamentally different measurements:

**Capability** — what a model *can* do under optimal elicitation (expert scaffolding, adversarial prompts, few-shot examples). Default prompting systematically underestimates the performance ceiling.

**Propensity** — what a model *spontaneously does* in operational context (zero-shot, default temperature, realistic distribution). High capability does not imply safe propensity.

Conflating them generates both false negatives and false positives in risk assessment. Every evaluation in Mercury exposes both scores separately.

### Doctrine 2 — System-in-context over model-only evaluation

The right object of evaluation is the deployed system, not only the base model. Agentic behavior, tool wiring, memory policies, and external context can dominate risk outcomes.

New failure modes demand new evaluation methods:
- Prompt injection via untrusted retrieved content (EchoLeak CVE-2025-32711)
- Goal misgeneralisation under long-horizon task decomposition
- Inter-agent trust failure in multi-agent pipelines
- Compounding error amplification across autonomous steps

### Doctrine 3 — Continuous evaluation over one-off certification

Point-in-time evaluation is insufficient for changing systems and environments. Mercury prioritizes continuous monitoring and re-evaluation with explicit drift visibility, aligned with **NIST AI 800-4** (March 2026), the first formal standard for deployed AI monitoring.

### Doctrine 4 — Reproducibility and independent replication

Claims without replication are hypotheses, not robust evidence. Mercury promotes protocol standardization, replayability, and multi-lab replication workflows. Mercury implements anti-sandbagging protocols, blind evaluation modes, and contrastive probing to detect evaluation-aware behaviour.

### Doctrine 5 — Benchmark validity over benchmark popularity

A high score on a public benchmark may measure **memorisation**, not the underlying capability it purports to test. Mercury implements contamination detection, dynamic benchmark generation, and validity grading (A–D) for every benchmark in the catalog.

### Doctrine 6 — Science, not scores

Every evaluation in Mercury is traceable to a heuristic, which maps to a paper. The platform is a **scientific instrument**, not a leaderboard generator.

---

## What Mercury Retrograde Provides

| Layer | What it does |
|---|---|
| **Capability/Propensity Engine** | Separates elicited maximum from operational behaviour; tail-risk sampling (P5/P10) |
| **Agentic Failure Suite** | 35 scenarios across 6 failure modes (injection, drift, trust, compounding, scope, error) |
| **Scheming Evaluation** | 50 scenarios measuring strategic misrepresentation, evaluation-awareness, self-preservation |
| **Compositional Risk Engine** | System-level threat profiles from composed capability scores; non-linear risk composition |
| **Failure Clustering** | TF-IDF-based novel failure discovery; causal hypothesis generation; cross-model patterns |
| **Mech Interp Validator** | CoT consistency, paraphrase invariance, confidence calibration as interpretability proxies |
| **Red Room** | Adversarial simulation lab: 6 structured attack scenarios with scientific grounding |
| **Continuous Monitoring** | NIST AI 800-4 compliant; Langfuse/OTEL integration; drift detection |
| **Research Workspace OS** | Hypothesis → protocol → experiment → replication → publication workflow |
| **Multi-lab Replication** | Scientific confidence grades (A–D) from independent replication network |

---

## Roadmap Philosophy

Mercury's roadmap follows one rule:

**Science quality and safety signal fidelity come before product surface expansion.**

Practical consequences:

- prioritize instrumentation, protocol quality, and reproducibility,
- prioritize high-risk domains and emergent failure discovery,
- ship features only when they improve decision-grade evidence,
- avoid "dashboard theater" that increases UI surface without improving scientific reliability.

---

## Decision Filter for Prioritization

Any roadmap item should pass this filter:

1. Does it improve our ability to discover or characterize frontier failure modes?
2. Does it improve reproducibility, traceability, or replication confidence?
3. Does it strengthen system-level (not model-only) evaluation quality?
4. Does it reduce epistemic risk in high-stakes deployment decisions?

If the answer is mostly no, it is likely not North Star aligned.

---

## North Star

**Mercury Retrograde is the default scientific infrastructure where high-impact AI evaluations are run, independently replicated, and cited.**

We succeed when papers, audits, and public safety reports can credibly state:

> *"This evaluation was executed and independently replicated on Mercury Retrograde."*

Mercury Retrograde is positioned to become the **GitHub + Kaggle + CVE of frontier AI safety evaluation** — the infrastructure where new failure modes are discovered before they reach production.

---

## Operating Commitment

Mercury Retrograde commits to:

- transparent methodology,
- measurable confidence,
- reproducible evidence pipelines,
- open scientific collaboration,
- and continuous improvement against real-world risk.

The mission is not to prove that systems are safe once.  
The mission is to make safety evaluation itself reliable, inspectable, and cumulative.

---

*Mercury Retrograde — the Research Operating System for frontier AI evaluation and safety science*
*INESIA — Institut national pour l'évaluation et la sécurité de l'intelligence artificielle*
