# Issue #109: [P2][Community] Benchmark fork and citation lineage graph

## Faisabilité

**Priorité:** P2 — Importante  
**Complexité estimée:** Haute (2–3 sprints)  
**Risque technique:** Faible-Moyen (principalement de l'ingénierie classique)

### Vision

Chaque benchmark doit être "forkable" comme un repo git, avec un tracking complet de la lignée de citations. Cela crée du crédit académique, de l'attribution scientifique et des effets de réseau communautaires.

### Composants impactés

- `db/models.py` — champs `parent_id`, `fork_type` sur `Benchmark`
- `api/routers/benchmarks.py` — endpoints fork/lineage
- `frontend/` — visualisation du graphe de lignée
- `core/` — moteur de citation et attribution

## Proposition de mise en œuvre

### Phase 1 — Modèle de données
- [ ] Ajouter `parent_benchmark_id` (FK nullable) sur `Benchmark`
- [ ] Ajouter `fork_type` : `extension`, `translation`, `subset`, `adversarial`
- [ ] Table `citations` : source_benchmark_id, target_benchmark_id, citation_type

### Phase 2 — Mécanisme de fork
- [ ] Endpoint `POST /api/benchmarks/{id}/fork`
- [ ] Clone du benchmark avec lien parent
- [ ] Preserve les métadonnées d'attribution (auteur original, licence)

### Phase 3 — Graphe de lignée
- [ ] API de traversée du graphe (ascendants + descendants)
- [ ] Visualisation D3.js / force-directed graph dans le frontend
- [ ] Calcul de métriques : profondeur du fork, nombre de dérivés

### Phase 4 — Attribution académique
- [ ] Génération automatique de citations (BibTeX, APA)
- [ ] DOI pour les benchmarks publiés
- [ ] Page publique d'impact : "ce benchmark a été forké N fois"

## Critères d'acceptance

- [ ] Fork d'un benchmark fonctionne en 1 clic
- [ ] Graphe de lignée visualisable pour tout benchmark
- [ ] Attribution automatique dans les exports
- [ ] Tests couvrant les opérations de fork et la traversée de graphe
