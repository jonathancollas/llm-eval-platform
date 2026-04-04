# Manifeste — Plateforme d'évaluation ouverte de l'INESIA

> *« Faire avancer la science de l'évaluation et de la sécurité de l'IA »*
> — Feuille de route INESIA 2026-2027

---

## Pourquoi cette plateforme existe

Les systèmes d'IA franchissent de nouveaux seuils de complexité. Capables de raisonnement multimodal, d'interaction avec des environnements hybrides, et bientôt d'auto-amélioration, ils s'imposent dans tous les champs de la société — y compris ceux qui touchent aux intérêts fondamentaux de la Nation.

Face à cette réalité, les méthodes d'évaluation conçues pour des systèmes fermés, monofonctionnels et statiques montrent leurs limites. Il ne suffit plus de mesurer une performance : il faut détecter des comportements inattendus, quantifier des incertitudes, évaluer la robustesse, l'alignement, la résilience, et les risques d'usage détourné.

L'évaluation de l'IA est devenue un enjeu stratégique à part entière.

Cette plateforme est l'infrastructure technique ouverte de l'INESIA pour répondre à cet enjeu. Elle est conçue pour être **rigoureuse, reproductible, souveraine et contributive**.

---

## Mission

Fournir à la communauté scientifique, aux régulateurs, aux industriels et à la société civile **un outil commun d'évaluation des modèles et systèmes d'IA avancés**, aligné sur la feuille de route de l'INESIA 2026-2027 et interopérable avec les initiatives européennes et internationales (réseau INAIMES — ex-réseau des AI Safety Institutes, AI Office de la Commission européenne).

---

## Trois pôles, une plateforme

### Pôle 1 — Appui à la régulation

La plateforme met des outils d'évaluation à la disposition des autorités françaises de surveillance du marché dans le cadre de la mise en œuvre du Règlement européen sur l'IA (RIA). Elle permet de :

- **Tester la conformité** des systèmes d'IA à haut risque selon des protocoles standardisés et réplicables
- **Détecter les contenus synthétiques** (texte, image, audio, vidéo) via une bibliothèque de référence open-source maintenue en conditions réelles (Projet n°3)
- **Évaluer la cybersécurité** des systèmes d'IA et des produits intégrant de l'IA — projet SEPIA, en lien avec l'ANSSI (Projet n°4)

### Pôle 2 — Risques systémiques

La plateforme opérationnalise l'évaluation des risques que les modèles avancés peuvent faire peser sur les intérêts collectifs. Quatre domaines prioritaires, dans l'ordre de criticité :

**1. CBRN-E** — Évaluation de l'uplift potentiel des modèles dans les domaines chimique, biologique, radiologique, nucléaire et explosif. Seuils d'alerte stricts, protocoles non publiés dans leur intégralité.

**2. Cybersécurité offensive** — Assistance à l'exploitation de vulnérabilités, génération de code malveillant, contournement de systèmes de détection. En lien avec l'ANSSI.

**3. Manipulations de l'information d'origine étrangère** — Génération de contenus de désinformation, opérations d'influence, ingérence dans les processus démocratiques européens. En lien avec le SGDSN et Viginum.

**4. Risques liés aux systèmes agentiques** — Autonomie non sanctionnée, planification multi-étapes sans supervision humaine, comportements émergents dans des environnements multi-agents, désalignement progressif, jusqu'aux scénarios de perte de contrôle (*loss of control*).

Ces évaluations s'appuient sur une méthodologie documentée publiquement, alignée sur les travaux du réseau INAIMES (UK AISI, METR, US AIST, AI Office).

### Pôle 3 — Performance et fiabilité

La plateforme soutient l'émulation et l'innovation dans l'écosystème français de l'IA :

- Organisation de **challenges ouverts** sur des tâches d'évaluation prioritaires (Projet n°8)
- Benchmarks de **performance en français** et sur des cas d'usage européens
- Comparaisons transparentes et reproductibles entre modèles ouverts et propriétaires

---

## Quatre principes fondamentaux

### 1. Rigueur scientifique

Chaque évaluation est **reproductible** : seed fixé, version du modèle tracée, hash des prompts enregistré, résultats archivés. Les protocoles sont documentés et révisables par la communauté. Aucun résultat publié sans traçabilité complète.

### 2. Souveraineté

La plateforme est **self-hosted**, open source, et ne dépend d'aucun fournisseur cloud étranger pour son cœur fonctionnel. Les données d'évaluation ne quittent pas l'infrastructure de l'opérateur. Les benchmarks sont développés indépendamment des labs qui produisent les modèles évalués.

### 3. Indépendance

L'INESIA évalue les modèles de façon **impartiale** — modèles français et étrangers, ouverts et propriétaires, avec les mêmes protocoles et les mêmes métriques. Aucun résultat n'est modulé par des considérations commerciales ou diplomatiques.

### 4. Ouverture contributive

Les benchmarks sont **publics et contributifs** : toute organisation (académique, industrielle, associative) peut proposer de nouvelles tâches via pull request. Les résultats agrégés sont publiés. La gouvernance des benchmarks est transparente.

---

## Ce que la plateforme évalue

### Benchmarks académiques et de performance
Standards internationaux adaptés au contexte francophone : MMLU, HellaSwag, ARC, TruthfulQA, GSM8K, HumanEval, MATH, BIG-Bench Hard — et leurs équivalents en français développés par l'INESIA et ses partenaires.

### Benchmarks de sécurité et d'alignement
- Refus appropriés face à des requêtes dangereuses (calibration sur-refus / sous-refus)
- Résistance aux injections de prompt et aux tentatives de contournement
- Cohérence comportementale entre contextes supervisés et non supervisés
- Détection de déception et de dissimulation d'intentions

### Benchmarks frontier (risques systémiques)
Protocoles inspirés de METR et UK AISI, adaptés au contexte réglementaire et géopolitique européen :

| Domaine | Description | Criticité |
|---|---|---|
| CBRN-E | Uplift dans les domaines chimique, biologique, radiologique, nucléaire, explosif | Maximale |
| Cybersécurité offensive | Exploitation de vulnérabilités, génération de malware | Haute |
| Manipulation information d'origine étrangère | Désinformation, influence, ingérence | Haute |
| Systèmes agentiques | Autonomie, désalignement, loss of control | Haute |

### Benchmarks custom
Toute organisation peut importer ses propres datasets au format JSON standardisé.

---

## Architecture technique

La plateforme est conçue pour fonctionner sur une infrastructure légère (desktop ou serveur modeste), sans dépendance à des services managés cloud :

- **Backend** : FastAPI + SQLite, évaluation asynchrone native
- **Eval engine** : Plugin-based, compatible lm-evaluation-harness (EleutherAI)
- **Modèles** : Ollama (local) + LiteLLM (proxy unifié cloud), OpenRouter
- **Rapports** : Génération narrative assistée par IA, exportable en Markdown/PDF
- **Déploiement** : Docker Compose, clonage en une commande

---

## Feuille de route technique (alignée sur INESIA 2026-2027)

| Jalon | Contenu | Échéance |
|---|---|---|
| v0.1 (actuel) | Pipeline éval, 4 benchmarks built-in, dashboard | Déployé |
| v0.2 | Intégration lm-eval-harness, catalogue OpenRouter | T2 2026 |
| v0.3 | Benchmarks en français (MMLU-FR, SafetyFR) | T3 2026 |
| v0.4 | Leaderboard public, API de soumission de modèles | T3 2026 |
| v0.5 | Module frontier complet (CBRN-E, cyber, agentique) | T4 2026 |
| v1.0 | Interopérabilité réseau INAIMES, authentification multi-org | T1 2027 |

---

## Contribuer

La plateforme est open source. Les contributions sont bienvenues sous toutes leurs formes :

- **Benchmarks** — nouveaux datasets, nouvelles tâches frontier
- **Runners** — intégration de nouveaux moteurs d'évaluation
- **Documentation** — protocoles, méthodologies, guides
- **Traductions et adaptation** — contexte francophone et européen

→ `github.com/[dépôt à définir pour la production]`

---

## Licence

Ce projet est publié sous **double licence** :

- **Licence Ouverte / Open Licence 2.0 (Etalab)** — pour les utilisateurs français et les administrations publiques
- **Apache License 2.0** — pour les utilisateurs internationaux et les organisations partenaires étrangères

L'utilisateur peut choisir l'une ou l'autre selon sa situation. Voir le fichier `LICENSE` pour le texte complet.

---

## Références

- Feuille de route INESIA 2026-2027, SGDSN/DGE
- METR — Model Evaluation & Threat Research
- UK AISI — AI Safety Institute, DSIT
- Réseau INAIMES — International Network for Advanced AI Measurement, Evaluation and Science
- EleutherAI — lm-evaluation-harness
- Règlement européen sur l'intelligence artificielle (RIA / AI Act)

---

*INESIA — Institut national pour l'évaluation et la sécurité de l'intelligence artificielle*
*Sous pilotage SGDSN / DGE — Partenaires : ANSSI, Inria, LNE, PEReN*
*https://www.sgdsn.gouv.fr/nos-missions/anticiper-et-prevenir/evaluer-et-securiser-lia*
