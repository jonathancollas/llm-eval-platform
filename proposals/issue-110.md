# Issue #110: [P2][Science] Multi-lab independent replication workflow

## Faisabilité

**Priorité:** P2 — Importante  
**Complexité estimée:** Haute (3–4 sprints)  
**Risque technique:** Moyen (coordination inter-organisations)

### Vision scientifique

La reproductibilité est le fondement de la crédibilité scientifique. Aucun résultat d'évaluation ne devrait être considéré comme solide sans réplication indépendante.

### Workflow cible

1. **Publish** : un chercheur publie un workspace d'évaluation
2. **Request replication** : d'autres labs peuvent demander à répliquer
3. **Run** : le lab réplicateur exécute avec ses propres ressources
4. **Compare** : comparaison automatique des résultats
5. **Publish** : badge de réplication sur le benchmark

### Composants impactés

- `db/models.py` — modèles `ReplicationRequest`, `ReplicationResult`
- `api/routers/` — nouveaux endpoints de réplication
- `core/` — moteur de comparaison de résultats
- `frontend/` — UI de demande et suivi de réplication

## Proposition de mise en œuvre

### Phase 1 — Modèle de données
- [ ] `ReplicationRequest` : benchmark_id, requesting_lab, status, created_at
- [ ] `ReplicationResult` : original_result_id, replica_result_id, concordance_score
- [ ] Workflow d'approbation : published → replication_requested → in_progress → completed

### Phase 2 — Export de workspace
- [ ] Format d'export standardisé (benchmark config + prompts + scoring)
- [ ] Import dans une instance tierce (CLI ou API)
- [ ] Versionning des configs pour reproductibilité exacte

### Phase 3 — Comparaison automatique
- [ ] Métriques de concordance : Cohen's kappa, Krippendorff's alpha
- [ ] Détection des divergences significatives
- [ ] Rapport de réplication automatisé

### Phase 4 — Badges et certification
- [ ] Badge "Répliqué par N labs"
- [ ] Niveau de confiance basé sur le nombre de réplications
- [ ] Page publique des réplications par benchmark

## Critères d'acceptance

- [ ] Workflow complet de demande/exécution/publication de réplication
- [ ] Métriques de concordance calculées automatiquement
- [ ] Badges visibles sur les benchmarks publics
- [ ] Documentation du format d'export pour labs tiers
