# meal-service-template

[Copier](https://copier.readthedocs.io) template for FamilyMeal services.

```bash
uvx copier copy --trust gh:topol-3000/meal-service-template meal-recipes
cd meal-recipes && make install && make check
```

A generated service has:

- **uv** project, Python 3.14, `src/` layout with domain / application / infrastructure / api layers
- **FastAPI** with `/health/live` and `/health/ready`, pydantic-settings
- **OpenTelemetry**: traces, metrics and logs over OTLP; FastAPI and httpx auto-instrumented;
  stable HTTP semantic conventions; trace context helpers for Redis Streams messages
- **structlog**: JSON logs with `trace_id`/`span_id`, the same records exported to Loki
- **ruff**, **pyright** strict, **pytest** (+ coverage, tests asserting spans and logs), **pre-commit**
- **Dockerfile** (multi-stage, uv, non-root, healthcheck) and **GitHub Actions** CI publishing to GHCR
- **AGENTS.md** (+ `CLAUDE.md` importing it) and Claude Code **skills**:
  `add-endpoint`, `add-event-handler`, `verify-observability`

Update a service to the latest template: `make update-template` inside the service.

Start [meal-platform](https://github.com/topol-3000/meal-platform) to see telemetry in Grafana.
