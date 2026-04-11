# Issue #91: [P2][Vision] Write product manifesto and North Star document

## Faisabilité

**Priorité:** P2 — Importante  
**Complexité estimée:** Faible (1–3 jours)  
**Risque technique:** Très faible (documentation)

### Contexte

Un document North Star est essentiel pour aligner l'équipe, les contributeurs et la communauté sur la vision à long terme de Mercury. Il sert de référence pour prioriser les features et évaluer les décisions architecturales.

**Note :** Un premier document North Star a déjà été créé dans le PR #123 (commit 5efc344). Cette issue vise à le finaliser et l'enrichir si nécessaire.

### Composants impactés

- `docs/` — nouveau fichier `NORTH_STAR.md` ou `MANIFESTO.md`
- `README.md` — lien vers le document
- `docs/` — vérifier cohérence avec la documentation existante

## Proposition de mise en œuvre

### Phase 1 — Audit du document existant
- [ ] Lire le North Star créé dans #123
- [ ] Identifier les lacunes : vision produit, valeurs, métriques de succès
- [ ] Recueillir feedback de l'équipe core

### Phase 2 — Structure du manifeste
- [ ] **Pourquoi Mercury** : problème que nous résolvons
- [ ] **Vision à 5 ans** : impact souhaité sur l'AI safety
- [ ] **Valeurs** : reproductibilité, transparence, collaboration
- [ ] **Public cible** : qui sont nos utilisateurs prioritaires
- [ ] **Métriques North Star** : comment mesurer le succès

### Phase 3 — Publication
- [ ] Revue par l'équipe (au moins 2 relecteurs)
- [ ] Mise à jour du README avec lien proéminent
- [ ] Partage avec la communauté (blog post ?)

## Critères d'acceptance

- [ ] Document de 1000–2000 mots, clair et inspirant
- [ ] Validé par au moins 2 membres de l'équipe core
- [ ] Lié depuis le README et la documentation principale
- [ ] Cohérent avec les issues et roadmap existantes
