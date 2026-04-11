# Issue #106: [P0][Safety] Scheming and strategic misrepresentation evaluation suite

## Faisabilité

**Priorité:** P0 — Critique (safety)  
**Complexité estimée:** Très haute (4–6 sprints, expertise safety requise)  
**Risque technique:** Élevé (conception des scénarios délicate, risque de faux positifs)

### Vision scientifique

Détecter si les modèles peuvent engager dans des comportements de scheming : dissimuler leurs capacités, induire en erreur les évaluateurs, ou poursuivre des objectifs cachés divergents de leurs instructions.

### Composants impactés

- `core/evaluators/` — nouveau `scheming_evaluator.py`
- `core/` — infrastructure multi-turn pour scénarios complexes
- `db/models.py` — support des conversations multi-étapes
- `frontend/` — visualisation des scénarios de scheming

## Proposition de mise en œuvre

### Phase 1 — Taxonomie des comportements de scheming
- [ ] Type 1 : Dissimulation de capacités (underperforming intentionally)
- [ ] Type 2 : Manipulation des évaluateurs (gaming evaluations)
- [ ] Type 3 : Poursuite d'objectifs cachés (deceptive alignment)
- [ ] Type 4 : Escalade de privilèges (seeking more resources/access)
- [ ] Revue par experts en AI safety avant validation

### Phase 2 — Scénarios d'évaluation
- [ ] Scénarios single-turn : prompts révélateurs d'intention
- [ ] Scénarios multi-turn : conversations où le scheming se développe
- [ ] Honeypot scenarios : opportunités de scheming avec monitoring
- [ ] Red-team par experts humains

### Phase 3 — Métriques et scoring
- [ ] Scheming Detection Rate avec baseline humaine
- [ ] False Positive Rate (comportement normal classifié comme scheming)
- [ ] Severity scoring : opportuniste vs systématique vs planifié
- [ ] Multi-modal judge (plusieurs LLM judges pour robustesse)

### Phase 4 — Infrastructure spécialisée
- [ ] Support des conversations multi-turn dans la DB
- [ ] Sandbox isolé pour les scénarios sensibles
- [ ] Audit trail complet de chaque évaluation

## Avertissements

⚠️ Ces évaluations doivent être révisées par des experts AI safety avant déploiement.  
⚠️ Les résultats ne doivent pas être interprétés comme preuve définitive de scheming sans analyse humaine.

## Critères d'acceptance

- [ ] Taxonomie validée par ≥ 2 experts AI safety
- [ ] Suite de ≥ 100 scénarios (single + multi-turn)
- [ ] Accord inter-annotateur > 0.75 sur les labels
- [ ] Documentation des limitations et risques de mauvaise interprétation
