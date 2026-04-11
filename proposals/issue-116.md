# Issue #116: [P0][Security] Authentication & RBAC — all API routes currently unprotected

## Faisabilité

**Priorité:** P0 — Urgente (sécurité critique)  
**Complexité estimée:** Moyenne (1–2 sprints)  
**Risque technique:** Moyen (impact large, tous les routers)

### Problème actuel

Le middleware `api_key_auth` est **actif uniquement si `ADMIN_API_KEY` est défini**.  
Sans cette variable d'env, TOUTES les routes passent sans authentification.

`require_tenant` existe dans `core/auth.py` mais n'est câblé sur aucun router.

**Routes non protégées (exemples) :**
- `POST /api/models/` — ajouter n'importe quel modèle
- `DELETE /api/benchmarks/{id}` — supprimer un benchmark
- `GET /api/results/` — lire tous les résultats de tous les tenants

### Composants impactés

- `core/auth.py` — middleware d'authentification
- `api/routers/*.py` — tous les routers
- `api/main.py` — configuration globale de l'app FastAPI
- `db/models.py` — modèle `ApiKey` (à implémenter)

## Proposition de mise en œuvre

### Phase 1 — Rendre l'auth obligatoire (P0)
- [ ] Passer `api_key_auth` de optionnel à obligatoire (lever 401 si pas de clé)
- [ ] Ajouter `ADMIN_API_KEY` comme variable d'env REQUISE au démarrage
- [ ] Appliquer `require_tenant` sur tous les routers dans `api/main.py`

### Phase 2 — RBAC basique (P1)
- [ ] Définir les rôles : `admin`, `researcher`, `viewer`
- [ ] Créer table `api_keys` avec champs : tenant_id, role, key_hash, created_at
- [ ] Middleware de vérification du rôle par endpoint

### Phase 3 — Isolation tenant
- [ ] S'assurer que chaque query filtre par `tenant_id`
- [ ] Tests d'isolation : tenant A ne peut pas voir les données de tenant B
- [ ] Audit des queries existantes

### Phase 4 — Gestion des clés API
- [ ] Endpoint admin pour créer/révoquer des clés API
- [ ] Rotation de clés avec période de grâce
- [ ] Logging des accès (qui, quand, quelle route)

## Critères d'acceptance

- [ ] Toutes les routes retournent 401 sans clé valide
- [ ] Isolation tenant vérifiée par tests
- [ ] RBAC appliqué sur les routes sensibles
- [ ] Démarrage du serveur échoue si `ADMIN_API_KEY` non défini
