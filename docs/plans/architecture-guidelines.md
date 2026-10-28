# Plan: architecture and coding guidelines for meal-* services

Status: **in progress** · Started: 2026-10-26 · Target release: template `v0.2.0`

## Goal

Give every generated `meal-*` service detailed, enforceable guidance on **where new code goes
and how to write it**: layering, models, settings, DI, errors, persistence, modern typing,
the approved library stack and testing. It is aimed at coding agents first and humans second.

The level of detail comes from `fastapi-boilerplate-main` (per-layer rules, the test philosophy,
"adding a module" guide). Its tech choices do not come along (see [Not adopted](#not-adopted)).

## Principles for this work

1. **Enforce with tools, explain in prose.** Anything checkable becomes a ruff, pyright or
   import-linter rule. Docs explain *why* and cover what tools can't check.
2. **Short entry point, detail on demand.** `AGENTS.md` is loaded into every agent session:
   keep it around 150 lines of commands, hard rules and links. Detail goes in `docs/` and `.claude/skills/`.
3. **Examples over descriptions.** Every convention doc and skill shows a short, correct
   code example. No business code in the generated service itself (template rule).
4. **Concrete SOLID, not slogans.** Each principle becomes a rule an agent can check, plus the
   anti-patterns it must not produce.
5. **Versions live in `pyproject.toml.jinja` only.** Docs name libraries, not version numbers.
6. **Zero-edit rule still holds.** A freshly rendered service passes `make check` and pre-commit.

## Decisions

| # | Topic | Decision |
|---|---|---|
| D1 | Code organisation | Layer-first (`domain/`, `application/`, `infrastructure/`, `api/`). Once a service has more than one aggregate, use feature subfolders inside each layer (`domain/recipes/`, `application/recipes/`, ...). |
| D2 | Domain models | Frozen `dataclass(slots=True)` entities and value objects. Pydantic only at boundaries (API, LLM output, settings). |
| D3 | Persistence | SQLAlchemy 2.x async + asyncpg + Alembic. Repositories implement domain ports (Protocols). No Unit of Work for now; transaction boundary = one use case call. Revisit when a use case spans several repositories. |
| D4 | Configuration | Env vars only (pydantic-settings). Vault deferred; when it arrives it becomes a settings source, not a service. |
| D5 | DI | No DI framework. Composition root in `main.py` (lifespan), dependency providers in `api/dependencies.py`, typed `Annotated[..., Depends(...)]` aliases. |
| D6 | Database opt-in | Copier question `with_database: bool` (default `true`). When true it renders `infrastructure/db/`, Alembic, DB settings, the readiness check, Makefile targets and the SQLAlchemy/asyncpg/Alembic dependencies. When false, none of these exist and the generated service still passes `make check`. |
| D7 | Integration-test database | `testcontainers[postgres]`: self-contained, one container per test session. Tests are marked `@pytest.mark.integration` and run in CI (Docker is available on GitHub runners). `make test` runs everything; `make test-unit` skips `integration`. |
| D8 | Security scanning | Trivy in the generated service's CI, a cleaned-up version of the boilerplate's workflow (see 6.1): `aquasecurity/trivy-action` pinned by commit, one `fs` scan (vulnerabilities in `uv.lock` including dev dependencies, secrets, misconfigurations) and one scan of the image before it is pushed; `CRITICAL,HIGH` with a fix fails the build. Runs on pull requests, pushes to main and weekly. Findings are fixed; `.trivyignore` holds only findings without a fix, each with a reason and an `exp:` review date. The template repo's CI runs the same scans on every variant. No separate `uv.lock` audit (6.2). |
| D9 | Auth | Out of scope for the template for now. No auth code, docs or library choice in this plan; it gets its own plan when the first service needs it. |
| D10 | Cache | Opt-in Copier question `with_cache: bool` (default `false`), like D6. When true it renders a Valkey cache adapter, `CacheSettings`, the client lifecycle, the cache doc and skill, and the redis-py dependency. Server: Valkey (BSD-3, Linux Foundation; Redis 8 extras aren't needed). Client: redis-py `redis.asyncio`, traced by `opentelemetry-instrumentation-redis`. Not valkey-py (no OTel instrumentation, slow releases) and not Valkey GLIDE (its Python OTel exports separately and can't attach spans to the app's trace). The cache is an optimisation, never the source of truth: every write has a TTL, a cache error counts as a miss (logged once, request continues), and `/health/ready` does not check it. All cache calls go through one adapter in `infrastructure/cache/`, so the client can be swapped in one file. Revisit the client when GLIDE's Python client accepts a parent span context, or if redis-py stops working with Valkey. |
| D14 | Events between services | Not in the template: no event bus, stream consumers or background workers (Redis/Valkey Streams, Celery). Services talk over HTTP. If a service needs messaging, it gets its own plan and decision first. |
| D11 | Migrations in deployment | A one-off job from the service image runs `python -m <package> migrate` before the new version starts (compose: a `<service>-migrate` service the app waits on with `depends_on: condition: service_completed_successfully`; Kubernetes: init container or pre-upgrade Job). Not in the container entrypoint (replicas race, a failed migration becomes a crash loop) and not from CI (CI would need database credentials and network access). Migrations ship inside the package (`infrastructure/db/migrations/`); a PostgreSQL advisory lock serialises concurrent runs. Migrations must work with the previous release too (expand, then contract). The job runs with the service's whole environment, not only `DB__URL`: it loads the same `Settings`, so with `with_cache` it needs `CACHE__URL` too (Q8). One environment for the app and its job keeps "a missing variable stops startup" true and needs no second settings class. |
| D12 | Local PostgreSQL | One PostgreSQL in meal-platform compose on `localhost:5432`, with a database and a user per service (service code never reads another service's tables). Local credentials follow `.env.example`: user, password and database are all named after the package. meal-platform gets an idempotent way to add a service's database (init scripts run only on a fresh volume). Tests keep using testcontainers. |
| D13 | PostgreSQL version | 18 (19 was still at RC in 2026-10; move after its first minor releases). The meal-platform compose tag is the reference; the template's `POSTGRES_IMAGE` test constant must match it. |

### Open questions

New questions go here with a `Q<n>` id and move to Decisions once answered.
(Q5–Q7 became D11–D13; Q8, whether `migrate` needs `CACHE__URL`, became part of D11.)

- **Q9 License scanning.** The boilerplate ran Trivy's `license` scanner (`CRITICAL,HIGH`,
  exit code 1); D8 doesn't. What Trivy 0.70.0 sees on a rendered service (2026-10-27):
  `fs` finds no licenses at all (`uv.lock` has no license data); the image scan reports
  318 `HIGH` "restricted" entries (GPL/LGPL), every one from Debian packages of the
  `python:3.14-slim` base, none from Python packages, plus 174 "unknown". So the
  boilerplate's setting would fail every build. The real question is whether a copyleft
  Python dependency (AGPL, GPL) must be stopped, given that services run as network
  services and aren't distributed. Options: no license scan (today), a report-only image
  scan, or a failing scan limited to Python packages with an allowlist (`--ignored-licenses`,
  or a `trivy.yaml` with license categories). Worth deciding before the first service
  ships; until then a new runtime dependency already needs approval (`docs/stack.md`).

---

## Phase 1: Restructure agent docs

Target layout inside `template/`:

```
AGENTS.md.jinja                 short: commands, layering, hard rules, links into docs/
docs/
  architecture.md               layers, dependency rule, composition root, DI, lifespan
  stack.md                      approved and banned libraries, with reasons
  conventions/
    python.md                   modern typing and syntax, OOP/SOLID rules, anti-patterns
    models.md                   the three kinds of models and how to map between them
    settings.md                 settings structure, secrets, how settings reach components
    errors.md                   error hierarchy and HTTP mapping
    persistence.md              SQLAlchemy, repositories, migrations, transactions
    caching.md                  cache-aside with Valkey, keys, TTLs, failure handling (with_cache)
    testing.md                  test philosophy, layout, fakes vs mocks, fixtures
.claude/skills/                 task recipes (see Phase 5)
```

- [x] **1.1 Slim down `AGENTS.md.jinja`.** Keep the project blurb, commands table, layering
      diagram with the dependency rule, observability hard rules, boundaries for agents.
      Replace the long sections with one-line rules + links to `docs/`.
      Add a "Where does new code go?" table:

      | I need to... | Put it in |
      |---|---|
      | a new business concept or rule | `domain/<feature>/` entity or value object |
      | talk to something external | port in `domain/`, adapter in `infrastructure/` |
      | a new operation the service performs | `application/<feature>/<verb>_<noun>.py` |
      | a new HTTP endpoint | `api/<feature>.py` router + schemas |
      | a new config value | `settings.py` (sub-model per adapter) |
      | a DB table | `infrastructure/db/models.py` + Alembic migration |
      | cache a slow lookup | port in `domain/`, adapter in `infrastructure/cache/` (`with_cache`) |

      Done: 131 lines without options, 150 with both. Ports go in `domain/<feature>/ports.py`;
      rows added for a resource with a lifetime, a repository and shared fakes (`tests/fakes/`,
      now a package in the template). The test rules say why DB tests use `db_client`, and errors
      point to the handlers in `api/errors.py`. Detail moved to `docs/`, linked at the end.

- [x] **1.2 `docs/architecture.md`.**
  - [x] Layers and what each may import (mirrors the import-linter contracts in 2.1).
  - [x] Composition root: `create_app()` builds settings, adapters and use cases; resources
        with a lifetime (DB engine, httpx2 client, cache client) are opened in `lifespan` via `AsyncExitStack`
        and closed in reverse order. This replaces the boilerplate's `on_start/after_start/on_stop`.
  - [x] How dependencies reach routes: typed state object on `app.state`, providers in
        `api/dependencies.py`, aliases like `type PlanService = Annotated[GeneratePlan, Depends(get_generate_plan)]`.
  - [x] Readiness: `/health/ready` checks every required resource (DB ping etc.). The cache
        is not required, so it has no readiness check (D10).
  - [x] Request flow diagram: router → use case → port → adapter, with where spans/logs happen.
  - Its example is a `plans` feature behind a `Clock` port (domain rule, port, use case,
    adapter, provider, router, `include_router`), because it needs no database, cache or
    setting and so works in every variant. Use case = class with ports in `__init__` and `__call__`.

- [x] **1.3 `docs/conventions/python.md`.**
  - [x] Typing style for Python 3.14:
    - `X | None`, never `Optional`/`Union`; built-in generics (`list[str]`, `dict[str, int]`)
    - PEP 695 generics: `class Repository[T]: ...`, `def first[T](xs: Sequence[T]) -> T`
    - `type` alias statement: `type RecipeId = UUID` or `NewType` when distinct identity matters
    - `typing.Self`, `@typing.override` on every overriding method
    - `collections.abc` for `Sequence`, `Mapping`, `Iterable`, `AsyncIterator`, `Callable`
    - `Protocol` for ports; `TypedDict` only for untyped external dict payloads
    - `StrEnum` / `Literal` for closed sets of values
    - Lazy annotations (PEP 649) are the default in 3.14: no `from __future__ import annotations`,
      no string annotations for forward refs
    - No `Any` in domain/application signatures; `object` or a Protocol instead
  - [x] OOP/SOLID as checkable rules:
    - **SRP:** one use case per module or class; a router module only handles HTTP.
    - **OCP:** extend by adding an adapter for an existing port, not by `if provider == ...` branches.
    - **LSP:** fakes and adapters must honour the port's documented behaviour (errors raised, ordering).
    - **ISP:** ports are small and named after the caller's need (`RecipeReader`, not `RecipeRepositoryInterface`).
    - **DIP:** application depends on domain ports, never on `infrastructure` modules.
    - Composition over inheritance; at most one level of inheritance outside framework base classes.
    - Functions are fine when there is no state; a class only when it holds dependencies or state.
  - [x] Anti-patterns list (with short "instead" examples): abstract base class with one
        implementation, factory for one concrete type, service locator / global container,
        `utils.py` / `helpers.py` grab-bags, mutable module-level state, deep inheritance,
        catching `Exception` broadly, returning `None` to signal errors, `**kwargs` pass-through.
  - [x] Naming and files: file named after primary class (`generate_plan.py` → `GeneratePlan`),
        constants `UPPER_SNAKE`, early returns over nesting.

- [x] **1.4 `docs/conventions/models.md`.**
  - [x] Three kinds: API schemas (Pydantic, `api/`), domain entities (frozen dataclasses,
        `domain/`), persistence models (SQLAlchemy, `infrastructure/db/`). LLM-output schemas
        are Pydantic boundary models too; so are cached values (serialised with `model_dump_json`).
  - [x] Base classes: `ApiModel(BaseModel)` with `ConfigDict(extra="forbid", frozen=True)`
        (the idea behind the boilerplate's `_ExtraBaseModel`, in v2 syntax). Separate request and response models.
  - [x] Field rules: `Annotated[str, Field(min_length=1, max_length=200)]`, reusable
        constrained aliases in one place, `X | None = None` explicitly.
  - [x] Mapping lives in exactly one place per boundary: `to_domain()` / `from_domain()` on
        the API schema; the repository maps ORM ↔ domain. Domain objects never leave via HTTP directly.

- [x] **1.5 `docs/conventions/settings.md`.**
  - [x] Nested sub-models per adapter (`DatabaseSettings`, `LlmSettings`) with
        `env_nested_delimiter="__"` → `DB__URL`, `LLM__BASE_URL`. Existing flat fields
        (`HTTP_PORT`, `LOG_LEVEL`, ...) stay flat to avoid a breaking change.
  - [x] Secrets as `SecretStr`; never logged, never in span attributes.
  - [x] `get_settings()` is called only in the composition root; components receive their
        own settings slice through `__init__`. Tests build `Settings(...)` directly.
  - [x] Every new variable is added to `.env.example` with a comment.

- [x] **1.6 `docs/conventions/errors.md`.**
  - [x] Hierarchy: `DomainError` base in `domain/errors.py` → `NotFoundError`,
        `ConflictError`, `ValidationError`, `ExternalServiceError`; feature errors subclass these.
  - [x] Adapters convert library exceptions (httpx2, SQLAlchemy, LLM client) into domain errors at the boundary.
  - [x] One exception handler in `api/errors.py` maps base classes to HTTP status + a single
        problem-details response shape. No per-route try/except for mapping.
  - [x] Logging rule: log once, where the error is handled, not at every layer.

- [x] **1.7 `docs/conventions/persistence.md`**, rendered only when `with_database` (D6);
      `AGENTS.md` links to it conditionally.
  - [x] Engine and `async_sessionmaker` created in lifespan; session per request through a dependency.
  - [x] Repository = class implementing a domain Protocol, takes `AsyncSession`, maps ORM ↔ domain.
  - [x] Transaction boundary: the use case's dependency commits on success and rolls back on error.
        As built in 3.9: one transaction per request (`DbSessionDep`), committed before the response.
  - [x] SQLAlchemy 2.0 typed style only: `DeclarativeBase`, `Mapped[...]`, `mapped_column`, `select()`.
        No legacy `Query` API, no raw SQL string interpolation.
  - [x] Alembic: autogenerate, then review by hand; one migration per change; naming convention for constraints.
        How to write a migration, step by step.
  - [x] Deployment (D11): `python -m <package> migrate` as a one-off job; expand/contract,
        so every migration works with the release that is still running.
  - [x] `op.get_context().autocommit_block()` (e.g. `CREATE INDEX CONCURRENTLY`) commits the
        migration transaction mid-run, which also releases the advisory lock (`pg_advisory_xact_lock`).
  - [x] N+1 guidance: explicit `selectinload` and no lazy loading in async (`lazy="raise"`).

- [x] **1.7a `docs/conventions/caching.md`**, rendered only when `with_cache` (D10);
      `AGENTS.md` links to it conditionally.
  - [x] Cache-aside only: read the cache, on a miss call the real source and write back.
        No write-through, no cache as the only copy of data.
  - [x] Ports named after the need (`RecipeCache`), adapter in `infrastructure/cache/`;
        application code never sees redis-py types.
  - [x] Keys: `<service>:<feature>:<version>:<id>`; bump `<version>` when the cached shape
        changes instead of migrating old entries.
  - [x] Every write sets a TTL (`CACHE__DEFAULT_TTL_SECONDS` unless the feature needs another).
  - [x] Values are Pydantic models as JSON; a value that fails to parse is a miss.
  - [x] Failures: connection errors and timeouts become a miss, logged once as
        `cache.unavailable`; the request still succeeds. Invalidate by deleting the key
        after the source of truth changes.
  - [x] No secrets or personal data in keys. The redis instrumentation records commands
        without arguments (`GET ?`), so keys stay out of spans, but they show up in logs and in
        Valkey tooling (`MONITOR`, slowlog).
  - [x] A failed delete (Valkey down) leaves the old value until it expires: the TTL is the
        staleness bound.
  - [x] Hit ratio from the `cache.lookups` counter (3.16).
  - The use case does the cache-aside through two ports (`RecipeReader`, `RecipeCache`);
    a value that doesn't parse is logged as `cache.invalid_value`. The doc also says a
    delete inside a request comes before the DB commit, so a concurrent reader can re-cache
    the old value: one more reason the TTL is the staleness bound.

- [x] **1.8 `docs/conventions/testing.md`.**
  - [x] Port the boilerplate's **test philosophy hard rule**: test the requirement, not the
        implementation; cover happy path, edges, failures and invariants; if a requirement is
        unclear, stop and ask; coverage finds gaps but isn't the goal.
  - [x] Layout mirrors `src/`: `tests/domain`, `tests/application`, `tests/api`, `tests/infrastructure`.
  - [x] Fakes over mocks: in-memory fakes implementing ports (shared in `tests/fakes/`);
        `unittest.mock` only for things without a port.
  - [x] `@pytest.mark.parametrize` for edge-case tables; `pytest.raises(..., match=...)`.
  - [x] Integration tests for repositories against real Postgres via testcontainers (D7):
        session-scoped container fixture, migrations applied once, each test in a rolled-back
        transaction, marked `integration`.
  - [x] (`with_cache`) the cache adapter against a real Valkey container, flushed between
        tests, marked `integration`; everything above the adapter uses an in-memory fake.
  - [x] Observability assertions with existing `span_exporter` / `log_exporter` fixtures.

- [x] **1.9 `docs/stack.md`.**
  - [x] Approved: FastAPI, uvicorn, Pydantic v2, pydantic-settings, structlog, httpx2,
        OpenTelemetry, SQLAlchemy 2 async + asyncpg + Alembic, Valkey via redis-py
        (`redis.asyncio`) as an optional cache (D10), pytest + pytest-asyncio + pytest-cov, ruff, pyright, import-linter, uv.
  - [x] Banned, with replacements: `requests`/`aiohttp`/`httpx` → httpx2 (Pydantic-maintained successor of httpx); Tortoise → SQLAlchemy;
        `dependency-injector`, `fastapi-class`, `fastapi-utils` → plain FastAPI DI;
        `valkey`/`valkey-glide` → redis-py (D10); Celery and stream consumers → not in the template (D14); Poetry/pip → uv; `logging.getLogger`/`print` →
        observability helpers. Auth libraries are not listed (D9).
  - [x] Rule: a new runtime dependency needs approval (already in AGENTS.md) and an entry here.
- Examples (all of Phase 1): every Python block is a whole file (first line `# <path>`), an
  addition (`# add to <path>`: imports go up, the rest at the end) or a context diff; blocks
  without a path are standalone modules. A script renders every variant, pastes each doc's
  examples (on top of the docs it builds on: errors ← models + settings, persistence and
  caching ← models, testing ← architecture) and runs `make check`; it also checks every
  link, anchor and code reference in `AGENTS.md`, `README.md` and `docs/`. The running
  `recipes` example: entity, errors, ports and schemas in `models.md`; a required setting
  in `settings.md` (diffs to `settings.py`, `tests/conftest.py`, `tests/test_settings.py`,
  `.env.example`); an httpx2 adapter with `MockTransport` tests in `errors.md`; table,
  repository, migrations (a real autogenerate output) and DB tests in `persistence.md`;
  cache adapter, use case and tests in `caching.md`. Docs are `.md.jinja`; `_exclude` must
  name the rendered path (`docs/conventions/persistence.md`), not the `.jinja` file.

## Phase 2: Enforcement in tooling

- [x] **2.1 import-linter** in dev dependencies, config in `pyproject.toml.jinja`:
  - [x] `layers` contract: `api` → `application` → `domain`; `infrastructure` → `domain`.
        Implemented as `["api", "application | infrastructure", "domain"]`: api may import
        infrastructure (providers build adapters), application and infrastructure never import each other.
  - [x] `forbidden` contract: `domain` and `application` must not import `fastapi`,
        `starlette`, `sqlalchemy`, `httpx2`, `redis`, `pydantic_settings`.
        Direct imports only (`allow_indirect_imports = true`): otherwise a use case could not import
        `observability` or `settings`, which use starlette and pydantic_settings.
  - [x] `forbidden`: `domain` must not import `{{ package_name }}.observability`.
  - [x] Add `make imports` target, include it in `make check` and pre-commit.
- [x] **2.2 ruff banned-api** additions: `requests`, `aiohttp`, `httpx`, `typing.Optional`, `typing.Union`,
      `typing.List`/`Dict` (in case UP misses them), `print` is already covered by `T20`.
- [x] **2.3 Template CI** runs each check step separately; switch it to `make check` so new
      checks (import-linter) can't be forgotten in CI.
- [x] **2.4** Make sure pyright strict passes on all new skeleton code without `# type: ignore`.

## Phase 3: Skeleton code in the template

Infrastructure only, no business logic. Each file comes with a test.

- [x] **3.1** `domain/errors.py`: `DomainError` hierarchy (1.6).
- [x] **3.2** `api/errors.py`: exception handlers + problem-details response model; registered in `create_app()`.
- [x] **3.3** `api/schemas.py`: `ApiModel` base class (1.4).
- [x] **3.4** `main.py`: lifespan with `AsyncExitStack`; typed app-state object holding resources.
      `AppState` is defined in `api/dependencies.py` (in `main.py` it would be a circular import)
      and stored on `app.state.app_state`.
- [x] **3.5** `api/dependencies.py`: providers for settings and resources, `Annotated` aliases.
- [x] **3.6** `settings.py`: nested sub-model pattern (`env_nested_delimiter="__"`), `SecretStr` example.
      `HttpClientSettings` (`HTTP_CLIENT__*`) is the sub-model; `SecretStr` is shown in the `Settings`
      docstring only, since there is no secret until `DB__URL` (3.9).
- [x] **3.7** Shared `infrastructure/http.py`: one lifespan-managed `httpx2.AsyncClient`
      factory (timeouts, instrumentation) instead of per-call clients.
      Tracing stays global (`instrument_app`), so httpx2 clients inside libraries are traced too.
- [x] **3.8** Copier question `with_database` in `copier.yml` (D6); conditional dependencies
      in `pyproject.toml.jinja`, conditional `.env.example` entries, and `_exclude` rules so
      DB files aren't rendered when it's false.
      `_exclude` covers `infrastructure/db/`, `tests/infrastructure/db/` and `migrations/`;
      everything else is `{% if with_database %}` blocks (settings, AppState, lifespan,
      telemetry, Makefile, `.env.example`, AGENTS.md, README).
- [x] **3.9** (`with_database`) `infrastructure/db/`: engine/session setup, `Base`, Alembic env
      wired to settings, readiness check, `make migrate` / `make migration name=...` targets.
      `DatabaseSettings` (`DB__URL: SecretStr`, required, must be `postgresql+asyncpg://`).
      Engine created in the lifespan, disposed through the `AsyncExitStack`; `DbSessionDep`
      commits on success and rolls back on error, with `scope="function"` so the commit
      happens before the response. `Base` has a constraint naming convention. Readiness
      check `database` runs `SELECT 1`. Queries traced by `opentelemetry-instrumentation-sqlalchemy`.
      Migrations live in the package (`infrastructure/db/migrations/`, D11);
      `python -m <package> migrate` (and `make migrate`) builds the Alembic config in
      `infrastructure/db/migrate.py`, `[tool.alembic]` in `pyproject.toml` serves the
      `alembic` CLI for `make migration` (no `alembic.ini`).
- [x] **3.10** (`with_database`) testcontainers fixtures in `tests/conftest.py`, `integration`
      marker registered in pytest config, `make test-unit` target (D7).
      Fixtures: `database_url` (session container, migrated once), `db_connection` /
      `db_session` (rolled back after each test), `db_app` / `db_client` (app on the test
      database, served in the test's event loop), `alembic_config`. Integration tests cover
      readiness, span nesting, pool disposal, commit/rollback/failed commit, models vs
      migrations (`alembic check`) and a downgrade/upgrade round trip.
- [x] **3.11** Tests: error-mapping test, lifespan open/close test, readiness test, settings parsing test.
- [x] **3.12** Remove the event parts of the template (D14): the `add-event-handler` skill,
      `observability/propagation.py` and its exports and test, the "Events between services" and
      "Events: schemas in meal-platform `contracts/events/`" rules in `AGENTS.md.jinja`, and
      "Redis Streams" in the `infrastructure` docstring, the layering diagram and `README.md`.
      HTTP calls between services already carry trace context through the httpx2 instrumentation.
      The events rule in `AGENTS.md.jinja` became "other services are called over HTTP through
      `HttpClientDep`, which carries the trace context"; "events" also left the list of
      Pydantic boundaries.
- [x] **3.13** Copier question `with_cache` in `copier.yml` (D10): `_exclude` for
      `infrastructure/cache/`, `tests/infrastructure/cache/` and `caching.md`;
      `{% if with_cache %}` blocks in settings, `AppState`, lifespan, telemetry, `.env.example`,
      `AGENTS.md` and `README`; conditional `redis` and `opentelemetry-instrumentation-redis` dependencies.
      The `caching.md` exclude comes with the doc in 1.7a. `AGENTS.md` gets one `cache/` line in
      the layout; "needs Docker" in `make test` / `make test-unit` now also holds for `with_cache`.
- [x] **3.14** (`with_cache`) `infrastructure/cache/`: `CacheSettings` (`CACHE__URL: SecretStr`,
      `redis://` or `rediss://`; `CACHE__DEFAULT_TTL_SECONDS`; short socket timeouts), one
      `redis.asyncio.Redis` created in the lifespan and closed through the `AsyncExitStack`,
      `CacheDep` in `api/dependencies.py`, global instrumentation in `instrument_app`.
      No business cache in the skeleton; the `add-cache` skill shows the pattern.
      Added: `ValkeyCache` in `infrastructure/cache/valkey.py`, the one generic adapter over the
      client (`get(key) -> bytes | None`, `set(key, value, ttl_seconds=None)` that always sends a
      TTL, `delete(key)`). redis-py connection errors and timeouts, and the refused writes of a
      read-only replica (`ReadOnlyError`, after a failover) or a full Valkey
      (`OutOfMemoryError`), become a miss or a no-op, logged once per call as
      `cache.unavailable` (warning, with `operation` and `error_type`, no key); other errors
      (wrong type, invalid TTL) propagate. A wrong password (`AuthenticationError`) and a full
      pool (`MaxConnectionsError`, redis-py's async default is 100) are connection errors, so
      misses too; `error_type` tells them apart from an outage. No pool-size setting yet. `CacheDep` yields `ValkeyCache`; feature caches wrap it behind their own
      ports (1.7a). Defaults: TTL 300 s, `CACHE__CONNECT_TIMEOUT_SECONDS` and
      `CACHE__TIMEOUT_SECONDS` 0.5 s. No ping at startup and no readiness check.
      `retry=Retry(NoBackoff(), 0)` is set explicitly: `from_url` happens not to retry in
      redis-py 8.1, but the `Redis()` constructor defaults to 10 retries with backoff; a test
      bounds a miss against a silent server to one timeout.
      Versions: `redis>=8.1`, `opentelemetry-instrumentation-redis>=0.66b1`, which accepts
      `redis >= 2.6`, so no cap. `OTEL_SEMCONV_STABILITY_OPT_IN=http,database` with either
      option. The instrumentation records commands without arguments (`GET ?`), so keys don't
      reach span attributes; 1.7a's reason for "no personal data in keys" should name logs and
      Valkey tooling (`MONITOR`, slowlog) instead. Two `pyright: ignore[reportUnknownMemberType]`
      with reasons: redis-py's `from_url` and `RedisInstrumentor.instrument` have untyped `**kwargs`.
- [x] **3.15** (`with_cache`) testcontainers Valkey fixture (`valkey/valkey:9`, matching the
      meal-platform compose tag), tests for the client lifecycle, span nesting under a request,
      and "Valkey down → miss, request succeeds".
      testcontainers' own `ValkeyContainer` (`testcontainers[valkey]`), image in `VALKEY_IMAGE`.
      Fixtures: `cache_url` (session container), `cache_client` (the test's own client, flushes
      after each test), `cache_settings`. Unit tests run with `CACHE__URL` on a closed port, so
      the Valkey-down tests (miss + `cache.unavailable` per call, requests via `CacheDep`,
      `/health/ready` without a cache check, a silent server = miss within the timeout) need no
      Docker. The lifespan test checks Valkey's `CLIENT LIST` for the app's connection.
- [x] **3.16** (`with_cache`) `cache.lookups` counter in `ValkeyCache.get` (`get_meter`), attribute
      `result` = `hit` | `miss` | `unavailable`, for the hit ratio (1.7a). Tests read it through
      an in-memory metric reader.
      `metric_reader` fixture (every variant): an `InMemoryMetricReader` on the global meter
      provider with delta temporality, so a read returns what was recorded since the previous one.
      An empty stored value is a hit. A test in every variant asserts `http.server.request.duration`
      with its stable attributes, so the fixture is used everywhere.

## Phase 4: Port useful parts of the boilerplate

| Boilerplate | Becomes | Item |
|---|---|---|
| Test philosophy hard rule (`CLAUDE.md`) | `docs/conventions/testing.md` | 1.8 |
| Controller/service/model rules | `docs/architecture.md`, `models.md` | 1.2, 1.4 |
| `docs/adding-a-module.md` | "Where does new code go?" + `add-feature` skill | 1.1, 5.1 |
| `ApplicationLikeStrategy` lifecycle | lifespan + `AsyncExitStack` | 3.4 |
| `_ExtraBaseModel` | `ApiModel` (v2 `ConfigDict`) | 3.3 |
| "Convert provider failures into app exceptions" | adapter rule in `errors.md` | 1.6 |
| Trivy workflow | P6 | 6.1 |

### Not adopted

`dependency-injector` + wiring, `fastapi-class` `View`, Tortoise ORM, Vault service (for now),
`python-jose`, Celery, Poetry, `@timings_decorator` (OTel spans cover it), `Optional[T]`
style and `Extra.forbid`, per-route try/except error mapping, minimal ruff rule set,
`RedisService` as a general-purpose service (the cache is a port + adapter instead).

## Phase 5: Skills (task recipes with code examples)

Skills are procedures and docs are rules: a skill is numbered steps that link to the doc
sections holding the rules, plus one worked example. The worked examples continue the docs'
`recipes` example into one feature, "how many days one batch of a recipe feeds the family"
(`days_fed`, `CountDaysFed`, `GET /recipes/{recipe_id}/days-fed`), which works in every variant
because its recipes come from meal-recipes over HTTP. Their code is checked like the docs'
(`tools/docs-check/`, `DEPENDS` chains from one skill to the next).

- [x] **5.1 `add-feature`**: new feature folder across all layers (domain → use case → adapter → router → tests).
      The order of work, each step pointing to a skill or doc; the worked example is a table
      of the feature's files and which doc or skill writes each.
- [x] **5.2 `add-use-case`**: use case class with ports, span, logging, unit test with fakes.
      Example: `days_fed()` + `InvalidFamilySizeError` in the domain, `CountDaysFed` on
      `RecipeReader`, the shared `FakeRecipeReader` (same as in `caching.md`), domain and use-case tests.
- [x] **5.3 `add-repository`** (only when `with_database`): ORM model, Protocol port, repository, migration, integration test.
      The worked example is persistence.md's recipes table, mapped step by step (no second copy).
- [x] **5.4 `add-setting`**: settings sub-model, `.env.example`, injection into a component, test.
      Example: `RECIPES_API__TIMEOUT_SECONDS` (a default, in an existing slice) passed per
      request by `HttpRecipeReader`; settings.md keeps the required-setting example.
- [x] **5.5 `add-external-client`**: port + httpx2 adapter, error conversion, retries/timeouts, fake.
      Timeouts only: the rule is a new "Timeouts" section in `errors.md` (shared client's by
      default, `timeout_seconds` in the slice passed per request). Retries are left out until
      there is a decision. Example: the provider `get_count_days_fed` on `HttpClientDep` and a
      timeout test; the adapter and its `MockTransport` tests stay in `errors.md`.
- [x] **5.6** Update `add-endpoint` to link the new docs, use the `Annotated` dependencies,
      `ApiModel`, and the central error handler.
      Rewritten: schemas, provider + alias, route without try/except, `include_router`,
      `client` with an overridden provider (`db_client` for database routes), contract.
      Example: `GET /recipes/{recipe_id}/days-fed` with 200, 404 and 422 tests.
- [x] **5.7 `add-cache`** (only when `with_cache`): cache-aside around an existing port, key
      and TTL, Pydantic value model, fake for unit tests, integration test against Valkey.
      The worked example is caching.md's; the skill adds its provider (`get_find_recipe`, with
      meal-recipes as the source of truth) and a test that a lookup works while Valkey is down.
- `add-repository` and `add-cache` are excluded by their rendered paths in `_exclude`;
  `AGENTS.md` and `add-feature` list them only in their variants. `verify-observability`
  now starts with the test fixtures (`metric_reader` included), waits for the 15 s metric
  interval of `.env.example` and queries `cache_lookups_total` with `with_cache`.

## Phase 6: CI and security

- [x] **6.1 Trivy** in the template CI (D8), improved on the boilerplate version: pinned
      `aquasecurity/trivy-action` instead of `curl | sh` from `main`, one `fs` job
      (vuln, secret, misconfig) + image scan after `docker build`, `CRITICAL,HIGH`, `--ignore-unfixed`.
      A `.trivyignore` with a comment per entry.
  - **Jobs in `ci.yml`, not a separate `trivy.yml`.** The image scan has to sit between the
    build and the push in the `docker` job: a separate workflow would build the image a
    second time and couldn't stop the push. The `fs` scan is a `trivy-fs` job running
    beside `check`. One workflow means one schedule and one list of required checks.
  - `docker` job: `build-push-action` with `load: true`, Trivy on the first metadata tag,
    then a second `build-push-action` with `push: true`. The second one finds every layer
    in the builder's cache, so the image is built once. `PUBLISH` (a push to main) gates
    the login and the push.
  - Triggers: `pull_request`, push to main, and `schedule` (Mondays 05:00 UTC). The
    weekly run runs the whole workflow, `make check` included (which also catches drift in
    the testcontainers images), and never publishes. The concurrency group includes the
    event, so a weekly run can't cancel a publishing push. It scans what main builds that
    day; images already in GHCR aren't rescanned.
  - `aquasecurity/trivy-action@ed142fd0673e97e23eac54620cfb913e5ce36c25` (v0.36.0, signed
    tag of 2026-04-22), which installs Trivy v0.70.0. It is pinned by commit because the
    action's tags were rewritten in a 2026-03 supply chain attack; the other actions keep
    version tags. To bump: resolve the new tag's commit (`gh api
    repos/aquasecurity/trivy-action/git/ref/tags/<tag>`, then the tag object) and update
    both the template's and this repo's `ci.yml`.
  - DB cache: the action's built-in cache (`actions/cache` on `.cache/trivy`, one key per
    day, restoring the latest one). Pull requests restore main's cache; pushes and the
    weekly run keep it fresh. The cache directory is inside the checkout; a local `fs` scan
    with the cache in that place gave no extra findings, so it isn't skipped.
  - The `fs` scan includes dev dependencies (`TRIVY_INCLUDE_DEV_DEPS`). By default Trivy
    skips `uv.lock`'s dev group (27 of 84 packages: pytest, ruff, testcontainers, pre-commit),
    and those run in CI and on laptops; the image scan covers only runtime packages.
    Image scan: `vuln,secret` (the Dockerfile's misconfigurations are in the `fs` scan).
  - `.trivyignore`: empty, with a header asking for a comment per entry (finding, reason,
    review date) and the review date as `exp:<date>`, after which the finding fails CI
    again (checked with Trivy 0.70.0: a past `exp:` reports the finding, a future one hides
    it). Both scans pass it as `trivyignores`. Entries added: none.
  - Real finding, fixed: every image failed on four `HIGH` findings in the pip that ships
    with `python:3.14-slim` (pip 26.2.2 vendors urllib3 2.7.0: CVE-2026-97687,
    CVE-2026-97689; msgpack 1.1.2: GHSA-6v7p-g79w-8964; setuptools 70.3.0 as
    `pkg_resources`: CVE-2025-47273). The app runs from its venv and never uses pip, so the
    runtime stage now runs `pip uninstall pip`. The `fs` scans were clean.
  - Template repo CI runs both scans on each of the four renders: `fs` right after
    rendering (before `uv sync` creates `.venv`, so it sees what a service checkout sees)
    and the image after `docker build`. The template repo's `AGENTS.md` has the
    `docker run aquasec/trivy` commands for running them locally.
  - Rendered docs: the `AGENTS.md` commands row says `make check` is everything CI runs
    except the Trivy scans; Boundaries: ask before adding a `.trivyignore` entry, never ignore
    a finding that has a fix. Template `README.md` lists the scans. Not done: SARIF upload to
    code scanning (commented out in the boilerplate), license scanning (Q9).
- [x] **6.2** Dependency audit of `uv.lock` (Trivy fs covers it; decide if a separate step is needed).
      Covered by 6.1, no separate step. Evidence: Trivy 0.70.0 `fs --list-all-pkgs --format json`
      on a `with_database` + `with_cache` render reports target `uv.lock` (type `uv`) with 57
      runtime packages (fastapi, sqlalchemy, asyncpg, redis, alembic, httpx2,
      opentelemetry-sdk, ...); with `--include-dev-deps` it reports 84, every package in
      `uv.lock`. The image scan reads the same packages again from the venv's
      `site-packages`.
- [x] **6.3** Template repo CI: render with `with_database=true` and `false` (matrix); both
      must pass `make check`, pre-commit and the Docker build.
- [x] **6.3a** Extend the matrix with `with_cache` (2 × 2 renders).
      Job names are now `generate-and-check (with_database=true|false, with_cache=true|false)`;
      update required status checks if branch protection lists the old names. The template
      repo's `AGENTS.md` asks for a check of every combination.
- [x] **6.4** Generated service CI runs integration tests (Docker available on the runner, D7).
      Through `make check`, which runs `make test` (all tests).

## Phase 7: Verification

- [ ] **7.1** Render a sample service for every `with_database` × `with_cache` combination:
      `make check` + pre-commit pass with zero edits in all four.
- [ ] **7.2** Deliberately break each rule (domain imports fastapi, `Optional`, `requests`)
      and confirm the tooling fails.
- [ ] **7.3 Agent dry run.** In a rendered sample, ask an agent to "add recipe import by URL"
      using only the repo docs. Review the result against this plan: right folders, ports,
      error mapping, spans, tests with fakes. Fix the docs where the agent went wrong. Repeat once.
- [ ] **7.4** Check that `AGENTS.md` stays under about 150 lines and every link resolves.

## Phase 8: Release

- [ ] **8.1** Update the template repo's `AGENTS.md` / `README.md` (new docs, new Copier questions).
- [ ] **8.2** Tag `v0.2.0`; tag message lists breaking changes and steps for existing services
      (new dev dependency, `make check` now includes imports, new settings layout,
      `inject_trace_context`/`extract_trace_context` and `add-event-handler` removed;
      CI runs Trivy weekly and fails on fixable `CRITICAL,HIGH` findings; the runtime image
      no longer has pip).
- [ ] **8.3** Record the decisions D1–D14 as ADRs in meal-platform `docs/adr/`.
      D14 is done: ADR 0005 "Services talk over HTTP; no event bus for now" supersedes
      ADR 0003 (Redis Streams), written with 8.4. D1–D13 remain.
- [x] **8.4** Planned before Phase 5 (F3), done after it. meal-platform compose (D11, D12, D13): `postgres:18-alpine` service on
      `localhost:5432` with a volume; an idempotent way to add a database and user per
      service (e.g. `make db-add name=meal-recipes`); the `<service>-migrate` one-off
      service pattern for each service that has a database, with the same environment as the
      service (shared `env_file`, D11); a `valkey/valkey:9` service on
      `localhost:6379` for services with `with_cache` (D10).
      Done on meal-platform `feat/local-platform`, merged with main's Stage 0 platform:
      core = `grafana/otel-lgtm`, `postgres:18-alpine` (volume `postgres18_data`) and
      `valkey/valkey:9`; `make db-add name=meal-<name>` (idempotent, works on an existing
      volume, revokes `CONNECT` from `PUBLIC`); `docs/adding-a-service.md` with the
      `<service>-migrate` job and a shared `env_file`. Kept from main: Ollama (`ai`) and
      Langfuse (`langfuse`) profiles; Langfuse's database is now made by a `langfuse-db`
      job on every start instead of an init script. Removed: the Redis event bus and
      `contracts/events/` (D14).

## Follow-ups

Open items that wait on something outside the chunks above.

- [ ] **F1** Lift the SQLAlchemy `<2.1` cap in `pyproject.toml.jinja` with the next
      `opentelemetry-instrumentation-sqlalchemy` release (2.1 support was merged upstream in
      PR 5120 on 2026-10-14; 0.66b1 refuses 2.1). Raise that package's lower bound to the
      release, drop the comment, and run `make check` on SQLAlchemy 2.1 in the `with_database` renders.
- [x] **F2** `POSTGRES_IMAGE` (`postgres:18-alpine`) and `VALKEY_IMAGE` (`valkey/valkey:9`) in
      `tests/conftest.py.jinja` must match the images in meal-platform compose (D13, D10).
      Matched with 8.4. Keeping them in step on every bump is now a rule in meal-platform's `AGENTS.md`.
- [x] **F3** `make migration` autogenerates against `DB__URL`, so it needs a running
      PostgreSQL, which locally is meal-platform compose (8.4).
      Decided 2026-10-27: do 8.4 first, before Phase 5 (`add-repository` runs `make migration`);
      `make migration` keeps autogenerating against `DB__URL`. Not chosen: autogenerate
      against a throwaway testcontainer migrated to head. Resolved by 8.4: `make db-add`, then
      `make migration` against the compose PostgreSQL.

## Progress log

| Date | Change |
|---|---|
| 2026-10-26 | Plan drafted; decisions D1–D5 agreed. |
| 2026-10-26 | Q1–Q4 answered → D6 (DB opt-in), D7 (testcontainers), D8 (Trivy), D9 (auth out of scope). |
| 2026-10-26 | httpx replaced by httpx2 in the template (OTel httpx instrumentation supports it since 0.66b1). |
| 2026-10-26 | D10 agreed: Valkey server, redis-py client. |
| 2026-10-26 | Chunk 1 done (Phase 2, 3.1–3.7, 3.11) on branch `feat/architecture-chunk-1`: import-linter (2.15) with `make imports`, banned APIs, CI runs `make check`, error/ApiModel/AppState/settings/HTTP-client skeleton with tests. Decided while implementing: direct-imports-only forbidden contract, `AppState` in `api/dependencies.py`, `SecretStr` as docstring example, global httpx2 tracing kept. |
| 2026-10-26 | Chunk-1 review fixes on branch `feat/architecture-chunk-2` (separate commit): async exception handlers; `HTTPException` with non-str detail (JSON-encoded into `detail`) or an unregistered status (title "Client Error"/"Server Error") gives problem details, 1xx/204/304 get no body; 5xx domain errors log the message and send a generic detail; `/health/ready` runs checks concurrently under `READINESS_CHECK_TIMEOUT_SECONDS` (default 2 s, timeout = "failed"); import-linter forbids `domain` → `settings`, and template CI checks that the contract rejects it. |
| 2026-10-26 | Chunk 2 done (3.8–3.10, 6.3, 6.4; D3, D6, D7) on `feat/architecture-chunk-2`. Decided while implementing: **SQLAlchemy `>=2.0.55,<2.1`**, because `opentelemetry-instrumentation-sqlalchemy` 0.66b1 refuses 2.1 (support merged upstream 2026-10-14 in PR 5120, not released yet; lift the cap with the next contrib release). SQLAlchemy is instrumented globally in `instrument_app`, like httpx2 (per-engine instrumentation works once per process); `create_db_engine` calls `create_async_engine` through its module so the patched function is used. `OTEL_SEMCONV_STABILITY_OPT_IN=http,database`. `DbSessionDep` uses `scope="function"`, because the default scope commits after the response is sent. `DB__URL` is required and checked for the asyncpg scheme; `Settings` sets `hide_input_in_errors` (both variants), so a bad URL isn't echoed into startup logs. Alembic config in `[tool.alembic]` (no `alembic.ini`), date-prefixed revision files, ruff post-write hooks, async `env.py` reading `DB__URL` via `Settings` and logging through `configure_logging`; generated migrations pass ruff and pyright strict. `alembic` is a runtime dependency, but the image doesn't ship migrations yet (Q5). The `integration` marker and `make test-unit` render in both variants (future Valkey tests). DB integration tests use `httpx2.ASGITransport` in the test's loop instead of `TestClient` (asyncpg connections are loop-bound); the container is session-scoped, engines are per test. Test image `postgres:18-alpine` (Q7). Also: `.import_linter_cache/` gitignored in generated services. Open: Q5–Q7. |
| 2026-10-26 | Q5–Q7 answered → D11 (migrations as a one-off job from the image), D12 (one PostgreSQL in meal-platform compose, database and user per service), D13 (PostgreSQL 18). Template: migrations moved into `infrastructure/db/migrations/` so they ship in the wheel; `python -m <package> migrate` (`__main__` gets `serve` / `migrate` commands; `make migrate` uses it); `pg_advisory_xact_lock` in `env.py`, key from the service name. Verified end to end: a revision made by `make migration` is in the image and applied by `docker run <image> python -m <package> migrate`. meal-platform side is 8.4. |
| 2026-10-26 | Scope cut: no events in the template → D14; D10 now covers only an opt-in Valkey cache (`with_cache`). New items 1.7a, 3.12–3.15, 5.7, 6.3a; 5.6 drops `add-event-handler`. |
| 2026-10-26 | Chunk 3 done (3.12–3.15, 6.3a; D10, D14) on `feat/architecture-chunk-3`. Events removed: `add-event-handler`, `propagation.py` (`inject_trace_context` / `extract_trace_context`) and their rules; calls between services are HTTP via `HttpClientDep`. `with_cache` (default false) renders `CacheSettings` (`CACHE__URL` required, `redis://`/`rediss://`, TTL 300 s, 0.5 s timeouts), one `redis.asyncio` client in the lifespan (no ping, no readiness check) and `ValkeyCache` (`get`/`set`/`delete`, TTL on every write, connection errors and timeouts = miss or no-op logged as `cache.unavailable`). Decided while implementing: the generic `ValkeyCache` adapter (features wrap it); retries switched off explicitly (redis-py's `Redis()` defaults to 10); **`redis>=8.1` uncapped** (`opentelemetry-instrumentation-redis` 0.66b1 accepts `redis >= 2.6`); commands are traced without arguments, so keys stay out of spans (1.7a to adjust); testcontainers' `ValkeyContainer` with `valkey/valkey:9`; unit tests point the cache at a closed port, so the Valkey-down behaviour is tested without Docker. The readiness tests' example check `cache` was renamed to `storage`. CI matrix 2 × 2. |
| 2026-10-26 | Chunk-3 review follow-up: Q8 answered in D11 (the migrate job gets the service's whole environment, so `CACHE__URL` too). `ValkeyCache` also treats `ReadOnlyError` and `OutOfMemoryError` as unavailable (integration tests switch the test Valkey to a replica and to `maxmemory 1`), and `cache.unavailable` logs carry `error_type`. Circuit breaker for a long outage not added (D10: one log per call; 0.5 s timeouts bound the cost). |
| 2026-10-27 | Chunk 4 done (1.1–1.9, 1.7a, 3.16) on `feat/architecture-chunk-4`. Follow-ups F1–F3 added; F3 decided: 8.4 (meal-platform compose) comes before Phase 5, `make migration` keeps using `DB__URL`. `cache.lookups` counter (`result` = hit/miss/unavailable) and a `metric_reader` fixture in every variant. Agent docs: slim `AGENTS.md` (≤ 150 lines) + `docs/` with pasteable examples, verified per variant by script (examples pass `make check`; links, anchors and code references resolve). Checked against PostgreSQL 18: `autocommit_block()` releases the `pg_advisory_xact_lock` and it is not taken again, and the current revision is stamped only after `upgrade()`, so a failure after the block repeats it. `add-endpoint` no longer says to map errors to `HTTPException`. |
| 2026-10-27 | Chunk 5 done (5.1–5.7) on `feat/architecture-chunk-5`. First, the doc checkers moved into `tools/docs-check/` (service dir as argument, `DEPENDS` root-relative and transitive), cover `.claude/skills/*/SKILL.md`, and run in every CI variant after `make check`; the template's `AGENTS.md` documents the example conventions. Planted errors (a bad reference, a broken example) fail them. Skills: `add-feature`, `add-use-case`, `add-setting`, `add-external-client`, `add-endpoint` (rewritten), `add-repository` (`with_database`), `add-cache` (`with_cache`); `verify-observability` brought up to date. Decided while implementing: worked examples extend the `recipes` example over HTTP so they run in every variant; a timeout rule in `errors.md`; retries left out of 5.5. Rendered `AGENTS.md`: 131–150 lines. 8.4 (meal-platform compose) is still open, so `make migration` in `add-repository` needs a PostgreSQL started by hand until it lands. |
| 2026-10-27 | Chunk 6 done (6.1, 6.2; D8) on `feat/architecture-chunk-6`. Trivy jobs in the generated service's `ci.yml` (`trivy-fs` beside `check`; the image scanned inside the `docker` job between a `load: true` build and the push), on pull requests, main and weekly; `aquasecurity/trivy-action` v0.36.0 pinned by commit (Trivy v0.70.0), its built-in DB cache; `.trivyignore` with a header, `exp:` as the review date, no entries. Fixed instead of ignored: four `HIGH` findings in the base image's pip (vendored urllib3, msgpack, setuptools); the runtime stage uninstalls pip. 6.2 closed: Trivy reads `uv.lock` (57 runtime packages, 84 with the dev deps the `fs` scan includes). Template CI runs both scans on all four renders. Q9 (license scanning) opened. Plan status: in progress. |
| 2026-10-28 | 8.4 done on meal-platform `feat/local-platform`, merged with main's Stage 0 platform (PostgreSQL 17, Redis Streams, Ollama, Langfuse, init-script databases). Core follows D10–D13; Ollama and Langfuse stay as profiles, Langfuse's database from a `langfuse-db` job. D14 recorded as ADR 0005, superseding ADR 0003; `contracts/events/` removed. F2 and F3 closed. CI there: shellcheck, the core stack with `db-add` checks, and the Langfuse profile. |
