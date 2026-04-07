# Genomia (Failure Genome)

Diagnostic structurel d'échec — au-delà du score.

## Pipeline

### Layer 0: Signal Extractor

25+ signaux déterministes par item (zéro appel LLM) :

- Refusal detection (9 patterns, score de force 0-1)
- Truth score (SequenceMatcher vs expected)
- Self-contradictions, hedge count
- Format compliance (MCQ, JSON, code)
- Repetition ratio, language detection
- Latency classification

### Layer A: Rule-based Classifiers

7 classifieurs utilisant les signaux :

| Type | Détecte |
|------|---------|
| `hallucination` | Réponses factuellement incorrectes |
| `reasoning_collapse` | Chaîne de raisonnement qui casse |
| `instruction_drift` | Ignore ou dérive des instructions |
| `safety_bypass` | Contourne les guardrails |
| `over_refusal` | Refuse des requêtes légitimes |
| `truncation` | Réponse tronquée ou vide |
| `calibration_failure` | Sur/sous-confiance vs score réel |

### Layer B: LLM Hybrid (optionnel)

Pour les classifications incertaines (0.2 < prob < 0.7), Claude juge → blend 50/50.

## Regression Analysis

- Compare deux campagnes (diff score + causal scoring)
- Narrative Claude en 5 points (quoi, pourquoi, genome diff, recommandations, confiance)
