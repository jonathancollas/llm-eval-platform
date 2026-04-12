# REDBOX — Adversarial Security Lab

Laboratoire de test adversarial pour modèles LLM.

## Mutations

| Type | Description |
|------|-------------|
| `prompt_injection` | Prompt injection attacks |
| `jailbreak` | Bypass safety guardrails |
| `exfiltration` | Sensitive data exfiltration / secret leakage |
| `ambiguity` | Questions ambiguës piégeantes |
| `contradiction` | Contextes contradictoires |
| `multilingual` | Attaques multilingues |
| `malformed_context` | Contexte bruité/corrompu |

## Garak probing engine

REDBOX intègre un mode `engine="garak"` pour le scanner de vulnérabilités LLM. Couverture principale:

- jailbreak
- prompt injection
- exfiltration
- attaques multilingues

## Smart Forge

Connexion Genomia → REDBOX : les faiblesses détectées par le Failure Genome guident automatiquement la génération d'attaques ciblées.

```
hallucination élevée → ambiguity + malformed_context
reasoning_collapse   → contradiction + ambiguity
safety_bypass        → jailbreak + injection
```
