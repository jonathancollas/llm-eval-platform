# Agent Evaluation

Évaluation de trajectoires d'agents LLM multi-step.

## 6 Axes de scoring

| Axe | Poids | Description |
|-----|-------|-------------|
| task_completion | 25% | Objectif atteint ? |
| tool_precision | 20% | Outils utilisés correctement ? |
| planning_coherence | 20% | Plan logique et suivi ? |
| error_recovery | 15% | Récupère des erreurs ? |
| safety_compliance | 10% | Respecte les contraintes ? |
| cost_efficiency | 10% | Coût/tokens raisonnables ? |

Scoring hybride : 60% LLM + 40% rules.

## Agent → Genome Bridge

Les scores agents sont mappés vers le Failure Genome avec 3 extensions :
`loop_collapse`, `tool_chain_break`, `goal_abandonment`
