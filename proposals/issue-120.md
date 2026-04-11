# Issue #120: [P1][Quality] Critical test coverage gaps — auth, uploads, concurrency, migrations

## Faisabilité

**Priorité:** P1 — Critique  
**Complexité estimée:** Haute (3–5 sprints)  
**Risque technique:** Élevé si non traité

### Périmètre fonctionnel

Les zones à risque identifiées par l'audit CTO :

| Zone | Risque | Couverture actuelle |
|---|---|---|
| Auth / tenant isolation | P0 | ❌ Non testée |
| File upload security | P0 | ❌ Non testée |
| Campaign queue / cancel / resume | P1 | ❌ Non testée |
| DB migrations (idempotence) | P1 | ❌ Non testée |
| Concurrent campaign runs | P1 | ❌ Non testée |

### Composants impactés

- `api/routers/` — tous les routers (auth, benchmarks, campaigns, models)
- `core/auth.py` — middleware authentification et isolation tenant
- `core/job_queue.py` — file de tâches asynchrones
- `db/migrations/` — scripts Alembic
- `api/routers/benchmarks.py` — upload de datasets

## Proposition de mise en œuvre

### Phase 1 — Auth & tenant isolation (P0)
- [ ] Tests d'intégration `pytest` pour chaque router avec/sans clé API valide
- [ ] Tests d'isolation multi-tenant : un tenant ne peut pas accéder aux ressources d'un autre
- [ ] Mock de `ADMIN_API_KEY` dans les fixtures pytest

### Phase 2 — File upload security (P0)
- [ ] Tests de path traversal (`../../etc/passwd`, `../`, etc.)
- [ ] Tests de limite de taille (fichier > seuil → 413)
- [ ] Tests de types MIME non autorisés
- [ ] Fixtures avec fichiers malveillants simulés

### Phase 3 — Campaign queue (P1)
- [ ] Tests de création, annulation et reprise de campagnes
- [ ] Tests de comportement lors d'un restart serveur (persistance)
- [ ] Tests de concurrence (plusieurs workers, même campagne)

### Phase 4 — DB Migrations (P1)
- [ ] Vérifier idempotence de chaque migration Alembic
- [ ] Tests d'upgrade/downgrade complets sur DB de test
- [ ] CI qui applique les migrations sur une DB vide

### Phase 5 — Concurrence (P1)
- [ ] Tests d'accès concurrent aux mêmes ressources
- [ ] Tests de race conditions sur la queue de jobs

## Stratégie de tests

- Framework : `pytest` + `pytest-asyncio` pour le code async
- DB de test : SQLite en mémoire ou PostgreSQL via `testcontainers`
- Fixtures : factory pattern pour créer des objets de test réalistes
- CI : intégrer dans GitHub Actions (bloquer merge si coverage < seuil)

## Critères d'acceptance

- [ ] Couverture ≥ 80 % sur les zones P0/P1 identifiées
- [ ] Tous les tests passent en CI
- [ ] Aucune régression sur les tests existants
- [ ] Documentation des fixtures et patterns de test
