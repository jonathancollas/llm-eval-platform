# Issue #113: [P1][Science] Compositional risk modeling engine

## Faisabilité

**Priorité:** P1 — Importante  
**Complexité estimée:** Très haute (4–6 sprints, expertise safety AI requise)  
**Risque technique:** Élevé (recherche fondamentale, résultats incertains)

### Vision scientifique

Agréger des scores de capacités individuelles en profils de risque systémiques pour les pipelines agentiques. Combler un angle mort majeur des suites d'évaluation existantes.

### Fondement scientifique (INESIA)

> "The most severe near-term risks may arise from the composition of individually moderate capabilities in agentic pipelines — a research area almost entirely absent from existing evaluation suites."

### Composants impactés

- `core/` — nouveau module `compositional_risk.py`
- `db/models.py` — modèles pour graphes de capacités
- `api/routers/` — endpoints de modélisation des risques
- `frontend/` — visualisation du graphe de risques

## Proposition de mise en œuvre

### Phase 1 — Modèle de données
- [ ] Définir la taxonomie des capacités (perception, raisonnement, action, mémoire...)
- [ ] Schéma de graphe dirigé : capacités → interactions → risques composés
- [ ] Stocker les scores de capacités par campagne d'évaluation

### Phase 2 — Moteur de composition
- [ ] Algorithme de propagation de risque sur le graphe
- [ ] Modèles de composition : additive, multiplicative, threshold-based
- [ ] Calibration sur des cas connus (benchmarks publics)

### Phase 3 — Profils de menace
- [ ] Templates de pipelines agentiques communs
- [ ] Scoring automatique : pipeline → profil de risque
- [ ] Comparaison entre modèles sur le même pipeline

### Phase 4 — Validation scientifique
- [ ] Revue par des experts safety AI
- [ ] Publication des résultats de calibration
- [ ] Intégration avec les évaluations existantes

## Critères d'acceptance

- [ ] Scores composés calculés pour au moins 5 types de pipelines agentiques
- [ ] Corrélation > 0.7 avec évaluations expertes manuelles
- [ ] Visualisation du graphe de risques dans l'UI
- [ ] Documentation scientifique de la méthodologie
