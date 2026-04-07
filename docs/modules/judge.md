# LLM-as-Judge

Évaluation multi-juges avec métriques d'accord et calibration.

## Juges supportés

Claude Sonnet, GPT-4o, Gemini Pro, Llama 3

## Métriques

- **Cohen's κ** — accord inter-juges pairwise
- **Pearson r** — corrélation scores
- **CJE** — calibration sur labels oracle (humain)
- **Bias detection** — biais de longueur + préférence modèle

## Auto-judge

Après chaque campagne, Claude évalue automatiquement 30 items (non-blocking, skip si déjà fait).
