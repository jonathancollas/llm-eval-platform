# Issue #117: [P0][Security] Harden file upload — path traversal + unbounded DOS in benchmark dataset upload

## Faisabilité

**Priorité:** P0 — Urgente (sécurité critique)  
**Complexité estimée:** Faible (1–2 jours)  
**Risque technique:** Faible une fois corrigé

### Vulnérabilités actuelles

```python
# Dangereux — api/routers/benchmarks.py
content = await file.read()           # Pas de limite de taille → OOM
file_path = bench_dir / file.filename # Path traversal si filename = '../../etc/passwd'
```

**CVEs similaires :** CWE-22 (Path Traversal), CWE-400 (Unrestricted Resource Consumption)

### Composants impactés

- `api/routers/benchmarks.py` — endpoint d'upload de datasets
- `core/file_utils.py` (à créer) — utilitaires de sécurité fichiers

## Proposition de mise en œuvre

### Fix 1 — Path traversal (priorité maximale)
- [ ] Utiliser `pathlib.Path(file.filename).name` pour ne garder que le nom de fichier
- [ ] Valider que le chemin résolu reste dans `bench_dir` (`.resolve()` + vérification parent)
- [ ] Rejeter les noms avec `..`, `/`, `\`, ou caractères nuls

### Fix 2 — Limite de taille (DOS)
- [ ] Ajouter `MAX_UPLOAD_SIZE = 100 * 1024 * 1024` (100 MB configurable)
- [ ] Lire par chunks et lever 413 si dépassement
- [ ] Configurer Nginx/FastAPI pour la limite au niveau HTTP

### Fix 3 — Validation du type de fichier
- [ ] Whitelist des extensions autorisées (`.csv`, `.json`, `.jsonl`)
- [ ] Vérifier le MIME type réel (via `python-magic`, pas juste l'extension)
- [ ] Rejeter les fichiers dont le contenu ne correspond pas au type déclaré

### Fix 4 — Tests de sécurité
- [ ] Test de path traversal : `../../etc/passwd`, `%2e%2e%2f`, etc.
- [ ] Test de DOS : fichier > limite → 413
- [ ] Test de type invalide → 415
- [ ] Test de nom de fichier avec caractères spéciaux

## Critères d'acceptance

- [ ] Path traversal → 400 avec message d'erreur sécurisé
- [ ] Fichier trop grand → 413
- [ ] Type non autorisé → 415
- [ ] Tous les tests de sécurité passent
- [ ] Aucune régression fonctionnelle sur l'upload normal
