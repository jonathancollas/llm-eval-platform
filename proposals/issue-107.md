# Issue #107: [P1][Safety] Sycophancy evaluation suite (SycEval-inspired)

## Faisabilité

**Priorité:** P1 — Importante  
**Complexité estimée:** Haute (2–3 sprints)  
**Risque technique:** Moyen (conception des prompts critique pour la validité)

### Vision scientifique

Évaluer si les modèles donnent des réponses honnêtes même lorsqu'une réponse fausse serait plus agréable, ou s'ils disent aux utilisateurs ce qu'ils veulent entendre.

**Fondement (INESIA) :** "Do models give truthful answers even when a false answer would be more agreeable, or do they tell users what they want to hear? (SycEval)"

### Composants impactés

- `core/evaluators/` — nouveau `sycophancy_evaluator.py`
- `db/models.py` — type de benchmark `sycophancy`
- `api/routers/benchmarks.py` — support du type sycophancy
- `frontend/` — affichage des scores de sycophancy

## Proposition de mise en œuvre

### Phase 1 — Dataset de prompts sycophancy
- [ ] Catégorie 1 : questions factuelles avec pression sociale ("la plupart des gens pensent que...")
- [ ] Catégorie 2 : feedback positif non mérité (évaluer un mauvais texte après compliment)
- [ ] Catégorie 3 : validation de fausses croyances (anti-vax, théories du complot)
- [ ] Catégorie 4 : révision d'opinion sous pression ("êtes-vous sûr ?")
- [ ] Minimum 50 prompts par catégorie

### Phase 2 — Métriques d'évaluation
- [ ] Sycophancy Rate : % de réponses sycophantiques
- [ ] Position Maintenance Rate : taux de maintien de position sous pression
- [ ] Factual Accuracy Delta : différence de précision avec/sans pression sociale
- [ ] Scoring automatique LLM-as-judge (GPT-4 ou Claude)

### Phase 3 — Intégration plateforme
- [ ] Nouveau type de campagne `sycophancy_eval`
- [ ] Dashboard dédié avec décomposition par catégorie
- [ ] Comparaison inter-modèles sur les dimensions sycophancy

### Phase 4 — Validation
- [ ] Corrélation avec études SycEval publiées
- [ ] Revue humaine d'un échantillon de 10 % des jugements
- [ ] Documentation de la méthodologie

## Critères d'acceptance

- [ ] Suite de ≥ 200 prompts validés
- [ ] Scoring automatique avec accord inter-annotateur > 0.8
- [ ] Dashboard sycophancy dans l'UI
- [ ] Comparaison publiée pour au moins 3 modèles frontaux
