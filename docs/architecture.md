# Architecture

<!-- TODO: document the platform architecture -->

Mercury Retrograde follows a modular architecture built around:

- **FastAPI** backend
- **Next.js** frontend
- **SQLite / PostgreSQL** for persistence
- **Redis + Celery** for async task execution
- **Docker** for deployment
- Multi-tenant support
