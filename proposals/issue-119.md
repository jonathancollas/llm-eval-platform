# Issue #119: [P1][Architecture] Normalize DB model — replace JSON string fields with proper relations

## Faisabilité

**Priorité:** P1 — Critique  
**Complexité estimée:** Haute (2–3 sprints)  
**Risque technique:** Élevé (migration de données, breaking changes API)

### Problème actuel

Relations critiques stockées en JSON text :

| Table | Colonne | Actuel | Problème |
|---|---|---|---|
| `campaigns` | `model_ids` | `"[1,2,3]"` | Pas de FK, parsing répété |
| `campaigns` | `prompt_ids` | `"[1,2,3]"` | Idem |
| `results` | `metadata` | JSON blob | Requêtes non indexables |

### Composants impactés

- `db/models.py` — modèles SQLAlchemy
- `db/migrations/` — nouvelles migrations Alembic
- `api/routers/campaigns.py` — CRUD campaigns
- `core/scoring.py` — accès aux relations

## Proposition de mise en œuvre

### Phase 1 — Tables de jointure
- [ ] Créer table `campaign_models` (campaign_id, model_id)
- [ ] Créer table `campaign_prompts` (campaign_id, prompt_id)
- [ ] Ajouter les relations SQLAlchemy avec `relationship()`

### Phase 2 — Migration de données
- [ ] Script Alembic : lire JSON → insérer dans tables de jointure
- [ ] Tester migration sur dump de production anonymisé
- [ ] Rollback plan documenté

### Phase 3 — Mise à jour API
- [ ] Adapter les endpoints CRUD (créer/lire/modifier campaigns)
- [ ] Mettre à jour les schémas Pydantic
- [ ] Versionner l'API si breaking change

### Phase 4 — Nettoyage
- [ ] Supprimer les colonnes JSON dans une 2e migration
- [ ] Supprimer le code de parsing JSON résiduel
- [ ] Ajouter des index sur les FK

## Critères d'acceptance

- [ ] Toutes les relations ont des FK réelles
- [ ] Les migrations sont idempotentes
- [ ] Tests d'intégration couvrent les nouvelles relations
- [ ] Aucune régression fonctionnelle
