# REDBOX — Adversarial Security Lab

Laboratoire de test adversarial pour modèles LLM.

## Mutations

| Type | Description |
|------|-------------|
| `injection` | Prompt injection attacks |
| `jailbreak` | Bypass safety guardrails |
| `ambiguity` | Questions ambiguës piégeantes |
| `contradiction` | Contextes contradictoires |
| `multilingual` | Attaques multilingues |
| `malformed_context` | Contexte bruité/corrompu |

## Smart Forge

Connexion Genomia → REDBOX : les faiblesses détectées par le Failure Genome guident automatiquement la génération d'attaques ciblées.

```
hallucination élevée → ambiguity + malformed_context
reasoning_collapse   → contradiction + ambiguity
safety_bypass        → jailbreak + injection
```
