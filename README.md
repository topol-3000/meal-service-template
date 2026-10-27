# meal-service-template

[Copier](https://copier.readthedocs.io) template for FamilyMeal services.

```bash
uvx copier copy --trust gh:topol-3000/meal-service-template meal-recipes
cd meal-recipes && make install && make check
```

A generated service has:

- **uv** project, Python 3.14, `src/` layout with domain / application / infrastructure / api layers
- **FastAPI** with `/health/live` and `/health/ready`, pydantic-settings
- **PostgreSQL** (question `with_database`, default yes): SQLAlchemy 2 async + asyncpg, Alembic,
  session per request, readiness check, traced queries, testcontainers integration tests
- **Valkey cache** (question `with_cache`, default no): redis-py async client, a `ValkeyCache`
  adapter (TTL on every write, Valkey down = miss), traced commands, testcontainers integration tests
- **OpenTelemetry**: traces, metrics and logs over OTLP; FastAPI and httpx2 auto-instrumented;
  stable HTTP semantic conventions
- **structlog**: JSON logs with `trace_id`/`span_id`, the same records exported to Loki
- **ruff**, **pyright** strict, **pytest** (+ coverage, tests asserting spans and logs), **pre-commit**
- **Dockerfile** (multi-stage, uv, non-root, healthcheck) and **GitHub Actions** CI publishing to GHCR
- **AGENTS.md** (+ `CLAUDE.md` importing it) and Claude Code **skills**:
  `add-endpoint`, `verify-observability`

Update a service to the latest template: `make update-template` inside the service.

Start [meal-platform](https://github.com/topol-3000/meal-platform) to see telemetry in Grafana.
