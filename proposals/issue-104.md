# Issue #104: [P1][Safety] Build persuasion and human influence evaluation suite (PersuasionBench)

## Faisabilité

**Priorité:** P1 — Importante  
**Complexité estimée:** Haute (3–4 sprints)  
**Risque technique:** Moyen (conception des scénarios sensible éthiquement)

### Vision scientifique

Mesurer la capacité des LLMs à influencer les opinions et comportements humains — une capacité à double tranchant (aide pédagogique vs manipulation).

### Composants impactés

- `core/evaluators/` — nouveau `persuasion_evaluator.py`
- `db/models.py` — support des évaluations longitudinales
- `api/routers/` — endpoints pour PersuasionBench
- `frontend/` — dashboard des métriques de persuasion

## Proposition de mise en œuvre

### Phase 1 — Taxonomie des techniques de persuasion
- [ ] Catégorie 1 : Appels à l'émotion (peur, espoir, culpabilité)
- [ ] Catégorie 2 : Appels à l'autorité et à la crédibilité
- [ ] Catégorie 3 : Raisonnement logique (valide et fallacieux)
- [ ] Catégorie 4 : Réciprocité, engagement, preuve sociale (Cialdini)
- [ ] Catégorie 5 : Techniques de manipulation (gaslighting, DARVO)

### Phase 2 — Dataset et protocole
- [ ] 50+ scénarios par catégorie avec cibles d'opinion diverses
- [ ] Évaluateurs humains pour mesurer le changement d'opinion réel
- [ ] Protocole pré/post : mesurer l'opinion avant et après exposition
- [ ] Contrôle : même scénario sans LLM, avec humain neutre

### Phase 3 — Métriques automatiques
- [ ] Persuasion Intensity Score (analyse linguistique)
- [ ] Manipulation Detection Rate (détection de techniques manipulatoires)
- [ ] Helpfulness vs Harmfulness Index
- [ ] Comparaison inter-modèles sur les mêmes scénarios

### Phase 4 — Garde-fous éthiques
- [ ] Consentement éclairé des évaluateurs humains
- [ ] Debriefing post-évaluation
- [ ] Revue éthique par un IRB ou équivalent
- [ ] Publication responsable des résultats

## Critères d'acceptance

- [ ] Suite de ≥ 250 scénarios couvrant les 5 catégories
- [ ] Données d'évaluation humaine pour 20 % des scénarios
- [ ] Dashboard avec décomposition par technique
- [ ] Protocole éthique validé et documenté
