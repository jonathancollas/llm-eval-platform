# Issue #118: [P1][Infrastructure] Replace in-memory asyncio task queue with durable job system

## Faisabilité

**Priorité:** P1 — Critique  
**Complexité estimée:** Haute (2–3 sprints)  
**Risque technique:** Élevé (refactoring de l'infrastructure d'exécution)

### Problème actuel

`core/job_queue.py` utilise `asyncio.create_task()` comme mécanisme d'exécution réel.  
La couche Redis ne stocke qu'un marqueur de statut — elle ne distribue pas l'exécution.

**Conséquences :**
- Redémarrage serveur → toutes les campagnes en cours sont silencieusement perdues
- Impossible d'avoir plusieurs workers
- Pas de retry en cas d'échec
- Pas de monitoring des jobs

### Composants impactés

- `core/job_queue.py` — file de tâches actuelle
- `api/routers/campaigns.py` — déclenchement des campagnes
- `docker-compose.yml` — ajout du worker Celery/ARQ
- `requirements.txt` — nouvelles dépendances

## Proposition de mise en œuvre

### Option recommandée : ARQ (asyncio-native, Redis-backed)
ARQ est plus adapté qu'un Celery classique car le codebase est async-first.

### Phase 1 — Setup ARQ
- [ ] Ajouter `arq` aux dépendances
- [ ] Créer `core/workers.py` avec les fonctions de tâches ARQ
- [ ] Configurer `WorkerSettings` avec les queues et retry policies

### Phase 2 — Migration de job_queue.py
- [ ] Remplacer `asyncio.create_task()` par `arq.enqueue_job()`
- [ ] Persister les métadonnées de job dans Redis avec TTL
- [ ] Implémenter la récupération au redémarrage (job resumption)

### Phase 3 — Worker infrastructure
- [ ] Ajouter le worker ARQ dans `docker-compose.yml`
- [ ] Configurer les health checks du worker
- [ ] Monitoring basique (jobs en attente, en cours, échoués)

### Phase 4 — Tests
- [ ] Tests d'intégration avec Redis de test
- [ ] Tester la reprise après restart
- [ ] Tester le comportement multi-worker

## Critères d'acceptance

- [ ] Campagnes survivent aux redémarrages serveur
- [ ] Au moins 2 workers peuvent travailler en parallèle
- [ ] Retry automatique sur erreur transitoire
- [ ] Monitoring visible dans l'UI
