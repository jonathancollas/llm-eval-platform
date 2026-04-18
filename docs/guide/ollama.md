# Ollama — Modèles locaux

## Installation

```bash
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull llama3.2
ollama pull gemma2
```

## Intégration

Au démarrage, Mercury Retrograde détecte Ollama automatiquement et importe les modèles. Badge 🦙 LOCAL dans l'interface.

Dans le wizard campagne, filtre **🦙 Local** pour sélectionner les modèles Ollama (gratuit, zéro latence réseau).

## Configuration selon l'environnement

### Lancement natif (hors Docker)

Le backend tourne directement sur votre machine avec `uvicorn`. Ollama écoute sur `localhost:11434` — aucune configuration requise.

```env
OLLAMA_BASE_URL=http://localhost:11434
```

### Lancement via Docker (`docker-compose up`)

À l'intérieur d'un conteneur Docker, `localhost` désigne le conteneur lui-même et non votre machine hôte. Il faut donc utiliser `host.docker.internal` qui pointe vers la machine hôte :

```env
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

> **Note :** Le fichier `docker-compose.yml` utilise déjà `host.docker.internal:11434` comme valeur par défaut. Ce problème ne survient que si vous avez copié `.env.example` vers `.env` et que la ligne `OLLAMA_BASE_URL=http://localhost:11434` est active — elle écrase la valeur par défaut du compose.

**Solution rapide :** Dans votre `.env`, commentez ou remplacez la ligne `OLLAMA_BASE_URL` :

```env
# Pour Docker :
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

Puis redémarrez le backend : `docker-compose restart backend worker`

### Linux sans Docker Desktop

Sur certaines distributions Linux (sans Docker Desktop), `host.docker.internal` peut ne pas être résolu automatiquement. Dans ce cas, ajoutez l'entrée DNS manuellement dans `docker-compose.yml` (déjà présent) :

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

Cette ligne est déjà présente dans `docker-compose.yml` — aucune modification nécessaire.
