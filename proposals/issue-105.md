# Issue #105: [P1][Safety] Autonomous replication benchmark (RepliBench-inspired)

## Faisabilité

**Priorité:** P1 — Importante (safety critique)  
**Complexité estimée:** Très haute (4–6 sprints, infra sandboxing requise)  
**Risque technique:** Très élevé (exécution de code dans sandbox, risques de sécurité)

### Vision scientifique

Évaluer la capacité d'un LLM à s'auto-répliquer ou à répliquer ses capacités dans un nouvel environnement — une capacité identifiée comme indicateur de risque critique par les frameworks safety.

### Composants impactés

- `core/evaluators/` — nouveau `replication_evaluator.py`
- Infrastructure sandbox (Docker isolé, réseau restreint)
- `db/models.py` — résultats d'évaluation autonome
- Monitoring de sécurité de l'infrastructure

## Proposition de mise en œuvre

### Phase 1 — Infrastructure sandbox (CRITIQUE)
- [ ] Sandbox Docker avec réseau coupé ou très restreint
- [ ] Quotas de ressources stricts (CPU, RAM, disque, temps)
- [ ] Monitoring en temps réel des tentatives d'accès réseau
- [ ] Rollback automatique après chaque évaluation
- [ ] Revue de sécurité de l'infrastructure avant tout test

### Phase 2 — Scénarios de réplication
- [ ] Niveau 1 : Copier un fichier de configuration simple
- [ ] Niveau 2 : Installer un environnement Python basique
- [ ] Niveau 3 : Déployer un service web minimal
- [ ] Niveau 4 : Persister des données sur un stockage externe
- [ ] Chaque niveau doit être testable en isolation

### Phase 3 — Métriques
- [ ] Replication Success Rate par niveau
- [ ] Steps to completion (efficacité)
- [ ] Resource usage (compute, network attempts)
- [ ] Safety violations détectées

### Phase 4 — Cadre éthique
- [ ] Protocole d'approbation avant tout nouveau scénario
- [ ] Comité de revue des résultats
- [ ] Politique de divulgation responsable

## Avertissements critiques

🚨 Ce benchmark manipule des capacités d'exécution autonome — infrastructure de sécurité OBLIGATOIRE.  
🚨 Ne jamais exécuter sur infrastructure de production.  
🚨 Revue de sécurité indépendante requise avant déploiement.

## Critères d'acceptance

- [ ] Sandbox validé par audit de sécurité externe
- [ ] Au moins 4 niveaux de complexité testés
- [ ] Zéro incident de sécurité lors des tests internes
- [ ] Documentation complète des risques et mitigations
