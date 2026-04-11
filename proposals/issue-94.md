# Issue #94: [P3][Research] Build research collaboration layer — shared campaigns and benchmark packs

## Faisabilité

**Priorité:** P3 — Future  
**Complexité estimée:** Très haute (5–8 sprints, aspects produit et communauté)  
**Risque technique:** Moyen (principalement de l'ingénierie produit)

### Vision

Faire de Mercury la plateforme de référence pour la collaboration en recherche AI safety : partager des campagnes, des benchmark packs, et construire une communauté de chercheurs.

### Composants impactés

- `db/models.py` — modèles de partage et de collaboration
- `api/routers/` — endpoints de collaboration
- `core/` — moteur de permissions et partage
- `frontend/` — interface de découverte et collaboration

## Proposition de mise en œuvre

### Phase 1 — Profils chercheurs et organisations
- [ ] Page de profil chercheur (institution, publications, benchmarks)
- [ ] Modèle d'organisation avec membres et rôles
- [ ] Vérification d'affiliation (email institutionnel)

### Phase 2 — Partage de campagnes
- [ ] Permissions granulaires : private, shared_with_team, public
- [ ] Export de campagne sous forme de "research pack" (config + prompts + scoring)
- [ ] Import d'un research pack depuis une URL ou upload
- [ ] Versioning des packs (semver)

### Phase 3 — Benchmark packs communautaires
- [ ] Registry public de benchmark packs
- [ ] Curation editoriale (badge "Mercury Certified")
- [ ] Système de notation et commentaires
- [ ] Intégration avec publications (lien ArXiv, DOI)

### Phase 4 — Collaboration temps réel
- [ ] Invitation de co-chercheurs sur une campagne
- [ ] Commentaires et annotations sur les résultats
- [ ] Discussions liées aux benchmarks
- [ ] Notifications des mises à jour de packs suivis

### Phase 5 — API publique
- [ ] API read-only pour les benchmarks publics
- [ ] SDK Python pour intégrer Mercury dans des pipelines de recherche
- [ ] Webhooks pour les notifications d'événements

## Critères d'acceptance

- [ ] Au moins 10 organisations early-adopters
- [ ] 50+ benchmark packs publiés dans les 3 premiers mois
- [ ] Import/export de packs en < 5 secondes
- [ ] Documentation complète de l'API de collaboration
