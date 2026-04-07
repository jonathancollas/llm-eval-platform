# Core Eval

Le moteur d'évaluation central de Mercury Retrograde.

## Composants

- **Model Registry** — 300+ modèles OpenRouter + Ollama local
- **Benchmark Library** — 68 INESIA + 60+ lm-eval + HuggingFace import
- **Campaigns** — N modèles × M benchmarks, progression per-item
- **LiveFeed** — Résultats streamés en temps réel
- **Reports** — Narratifs Claude async avec export HTML
- **Leaderboard** — 7 domaines thématiques

## Pipeline d'exécution

```
Campaign.run()
    → asyncio.gather(model × benchmark)
        → BaseBenchmarkRunner.run()
            → for each item: LLM call → score → stream to DB
        → HarnessRunner._run_sync() (thread executor)
    → Auto Genome computation
    → Auto Judge (30 items)
```

## Contamination Detection

4 méthodes : n-gram overlap, verbatim reproduction, confidence anomaly, first-token probability.
