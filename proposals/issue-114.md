# Issue #114: [P2][Science] Failure clustering and emergent risk discovery engine

## Faisabilité

**Priorité:** P2 — Importante  
**Complexité estimée:** Très haute (3–5 sprints, ML expertise requise)  
**Risque technique:** Élevé (composant R&D, résultats incertains)

### Vision scientifique

Détecter automatiquement des modes de défaillance nouveaux et non anticipés en regroupant les résultats d'évaluation par similarité sémantique et comportementale.

### Composants impactés

- `core/` — nouveau module `failure_clustering.py`
- `api/routers/` — nouveaux endpoints d'analyse
- `frontend/` — visualisation des clusters
- `db/models.py` — stockage des clusters et métadonnées

## Proposition de mise en œuvre

### Phase 1 — Infrastructure de données
- [ ] Définir le schéma de stockage des embeddings de résultats
- [ ] Choisir la DB vecteur (pgvector, Qdrant, ou Chroma)
- [ ] Pipeline d'embedding des réponses LLM (OpenAI, Sentence-BERT)

### Phase 2 — Algorithme de clustering
- [ ] Implémenter HDBSCAN ou UMAP + K-Means sur les embeddings
- [ ] Labellisation automatique des clusters (LLM-based)
- [ ] Scoring de gravité par cluster (fréquence × impact)

### Phase 3 — Détection de nouveaux modes
- [ ] Baseline des clusters connus
- [ ] Détection d'anomalies (nouveaux clusters qui émergent)
- [ ] Alertes automatiques sur les clusters critiques

### Phase 4 — Interface
- [ ] Visualisation 2D/3D des clusters (UMAP projection)
- [ ] Drill-down par cluster : exemples représentatifs
- [ ] Export des clusters pour revue humaine

## Critères d'acceptance

- [ ] Clustering automatique sur N > 100 résultats
- [ ] Nouveaux modes détectés avec < 10 % de faux positifs
- [ ] Visualisation interactive dans le dashboard
- [ ] Performance acceptable (< 30s pour 1000 résultats)
