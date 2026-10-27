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
- **Dockerfile** (multi-stage, uv, non-root, healthcheck, no pip in the runtime image) and
  **GitHub Actions** CI publishing to GHCR
- **Trivy** in CI on pull requests, main and weekly: dependencies from `uv.lock`, secrets and
  Dockerfile checks on the repository, then the image before it is pushed (`CRITICAL,HIGH`
  with a fix fail the build; accepted findings go in `.trivyignore`, each with a reason)
- **AGENTS.md** (+ `CLAUDE.md` importing it), `docs/` (architecture, stack, conventions) and
  Claude Code **skills**: `add-feature`, `add-use-case`, `add-endpoint`, `add-external-client`,
  `add-setting`, `add-repository` (database), `add-cache` (cache), `verify-observability`

Update a service to the latest template: `make update-template` inside the service.

Start [meal-platform](https://github.com/topol-3000/meal-platform) to see telemetry in Grafana.
