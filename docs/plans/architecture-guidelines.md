# Plan: architecture and coding guidelines for meal-* services

Status: **draft** · Started: 2026-10-26 · Target release: template `v0.2.0`

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
| D2 | Domain models | Frozen `dataclass(slots=True)` entities and value objects. Pydantic only at boundaries (API, events, LLM output, settings). |
| D3 | Persistence | SQLAlchemy 2.x async + asyncpg + Alembic. Repositories implement domain ports (Protocols). No Unit of Work for now; transaction boundary = one use case call. Revisit when a use case spans several repositories. |
| D4 | Configuration | Env vars only (pydantic-settings). Vault deferred; when it arrives it becomes a settings source, not a service. |
| D5 | DI | No DI framework. Composition root in `main.py` (lifespan), dependency providers in `api/dependencies.py`, typed `Annotated[..., Depends(...)]` aliases. |
| D6 | Database opt-in | Copier question `with_database: bool` (default `true`). When true it renders `infrastructure/db/`, Alembic, DB settings, the readiness check, Makefile targets and the SQLAlchemy/asyncpg/Alembic dependencies. When false, none of these exist and the generated service still passes `make check`. |
| D7 | Integration-test database | `testcontainers[postgres]`: self-contained, one container per test session. Tests are marked `@pytest.mark.integration` and run in CI (Docker is available on GitHub runners). `make test` runs everything; `make test-unit` skips `integration`. |
| D8 | Security scanning | Trivy in the template CI, a cleaned-up version of the boilerplate's workflow (see 6.1). |
| D9 | Auth | Out of scope for the template for now. No auth code, docs or library choice in this plan; it gets its own plan when the first service needs it. |
| D10 | Event bus | Valkey server (BSD-3, Linux Foundation; Streams are all we use, Redis 8 extras aren't needed). Client is redis-py `redis.asyncio`, traced by `opentelemetry-instrumentation-redis`. Not valkey-py (no OTel instrumentation, slow releases) and not Valkey GLIDE (its Python OTel exports separately and can't attach spans to the app's trace). All Valkey calls go through one adapter in `infrastructure/` so the client can be swapped in one file. Revisit when GLIDE's Python client accepts a parent span context, or if redis-py stops working with Valkey. |

### Open questions

None right now. New questions go here with a `Q<n>` id and move to Decisions once answered.

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
    testing.md                  test philosophy, layout, fakes vs mocks, fixtures
.claude/skills/                 task recipes (see Phase 5)
```

- [ ] **1.1 Slim down `AGENTS.md.jinja`.** Keep the project blurb, commands table, layering
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

- [ ] **1.2 `docs/architecture.md`.**
  - [ ] Layers and what each may import (mirrors the import-linter contracts in 2.1).
  - [ ] Composition root: `create_app()` builds settings, adapters and use cases; resources
        with a lifetime (DB engine, httpx2 client) are opened in `lifespan` via `AsyncExitStack`
        and closed in reverse order. This replaces the boilerplate's `on_start/after_start/on_stop`.
  - [ ] How dependencies reach routes: typed state object on `app.state`, providers in
        `api/dependencies.py`, aliases like `type PlanService = Annotated[GeneratePlan, Depends(get_generate_plan)]`.
  - [ ] Readiness: `/health/ready` checks every registered resource (DB ping etc.).
  - [ ] Request flow diagram: router → use case → port → adapter, with where spans/logs happen.

- [ ] **1.3 `docs/conventions/python.md`.**
  - [ ] Typing style for Python 3.14:
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
  - [ ] OOP/SOLID as checkable rules:
    - **SRP:** one use case per module or class; a router module only handles HTTP.
    - **OCP:** extend by adding an adapter for an existing port, not by `if provider == ...` branches.
    - **LSP:** fakes and adapters must honour the port's documented behaviour (errors raised, ordering).
    - **ISP:** ports are small and named after the caller's need (`RecipeReader`, not `RecipeRepositoryInterface`).
    - **DIP:** application depends on domain ports, never on `infrastructure` modules.
    - Composition over inheritance; at most one level of inheritance outside framework base classes.
    - Functions are fine when there is no state; a class only when it holds dependencies or state.
  - [ ] Anti-patterns list (with short "instead" examples): abstract base class with one
        implementation, factory for one concrete type, service locator / global container,
        `utils.py` / `helpers.py` grab-bags, mutable module-level state, deep inheritance,
        catching `Exception` broadly, returning `None` to signal errors, `**kwargs` pass-through.
  - [ ] Naming and files: file named after primary class (`generate_plan.py` → `GeneratePlan`),
        constants `UPPER_SNAKE`, early returns over nesting.

- [ ] **1.4 `docs/conventions/models.md`.**
  - [ ] Three kinds: API schemas (Pydantic, `api/`), domain entities (frozen dataclasses,
        `domain/`), persistence models (SQLAlchemy, `infrastructure/db/`). Event and LLM-output
        schemas are Pydantic boundary models too.
  - [ ] Base classes: `ApiModel(BaseModel)` with `ConfigDict(extra="forbid", frozen=True)`
        (the idea behind the boilerplate's `_ExtraBaseModel`, in v2 syntax). Separate request and response models.
  - [ ] Field rules: `Annotated[str, Field(min_length=1, max_length=200)]`, reusable
        constrained aliases in one place, `X | None = None` explicitly.
  - [ ] Mapping lives in exactly one place per boundary: `to_domain()` / `from_domain()` on
        the API schema; the repository maps ORM ↔ domain. Domain objects never leave via HTTP directly.

- [ ] **1.5 `docs/conventions/settings.md`.**
  - [ ] Nested sub-models per adapter (`DatabaseSettings`, `LlmSettings`) with
        `env_nested_delimiter="__"` → `DB__URL`, `LLM__BASE_URL`. Existing flat fields
        (`HTTP_PORT`, `LOG_LEVEL`, ...) stay flat to avoid a breaking change.
  - [ ] Secrets as `SecretStr`; never logged, never in span attributes.
  - [ ] `get_settings()` is called only in the composition root; components receive their
        own settings slice through `__init__`. Tests build `Settings(...)` directly.
  - [ ] Every new variable is added to `.env.example` with a comment.

- [ ] **1.6 `docs/conventions/errors.md`.**
  - [ ] Hierarchy: `DomainError` base in `domain/errors.py` → `NotFoundError`,
        `ConflictError`, `ValidationError`, `ExternalServiceError`; feature errors subclass these.
  - [ ] Adapters convert library exceptions (httpx2, SQLAlchemy, LLM client) into domain errors at the boundary.
  - [ ] One exception handler in `api/errors.py` maps base classes to HTTP status + a single
        problem-details response shape. No per-route try/except for mapping.
  - [ ] Logging rule: log once, where the error is handled, not at every layer.

- [ ] **1.7 `docs/conventions/persistence.md`**, rendered only when `with_database` (D6);
      `AGENTS.md` links to it conditionally.
  - [ ] Engine and `async_sessionmaker` created in lifespan; session per request through a dependency.
  - [ ] Repository = class implementing a domain Protocol, takes `AsyncSession`, maps ORM ↔ domain.
  - [ ] Transaction boundary: the use case's dependency commits on success and rolls back on error.
  - [ ] SQLAlchemy 2.0 typed style only: `DeclarativeBase`, `Mapped[...]`, `mapped_column`, `select()`.
        No legacy `Query` API, no raw SQL string interpolation.
  - [ ] Alembic: autogenerate, then review by hand; one migration per change; naming convention for constraints.
  - [ ] N+1 guidance: explicit `selectinload` and no lazy loading in async (`lazy="raise"`).

- [ ] **1.8 `docs/conventions/testing.md`.**
  - [ ] Port the boilerplate's **test philosophy hard rule**: test the requirement, not the
        implementation; cover happy path, edges, failures and invariants; if a requirement is
        unclear, stop and ask; coverage finds gaps but isn't the goal.
  - [ ] Layout mirrors `src/`: `tests/domain`, `tests/application`, `tests/api`, `tests/infrastructure`.
  - [ ] Fakes over mocks: in-memory fakes implementing ports (shared in `tests/fakes/`);
        `unittest.mock` only for things without a port.
  - [ ] `@pytest.mark.parametrize` for edge-case tables; `pytest.raises(..., match=...)`.
  - [ ] Integration tests for repositories against real Postgres via testcontainers (D7):
        session-scoped container fixture, migrations applied once, each test in a rolled-back
        transaction, marked `integration`.
  - [ ] Observability assertions with existing `span_exporter` / `log_exporter` fixtures.

- [ ] **1.9 `docs/stack.md`.**
  - [ ] Approved: FastAPI, uvicorn, Pydantic v2, pydantic-settings, structlog, httpx2,
        OpenTelemetry, SQLAlchemy 2 async + asyncpg + Alembic, Valkey via redis-py
        (`redis.asyncio`) for Streams (D10), pytest + pytest-asyncio + pytest-cov, ruff, pyright, import-linter, uv.
  - [ ] Banned, with replacements: `requests`/`aiohttp`/`httpx` → httpx2 (Pydantic-maintained successor of httpx); Tortoise → SQLAlchemy;
        `dependency-injector`, `fastapi-class`, `fastapi-utils` → plain FastAPI DI;
        `valkey`/`valkey-glide` → redis-py (D10); Celery → Redis Streams events; Poetry/pip → uv; `logging.getLogger`/`print` →
        observability helpers. Auth libraries are not listed (D9).
  - [ ] Rule: a new runtime dependency needs approval (already in AGENTS.md) and an entry here.

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
- [ ] **3.8** Copier question `with_database` in `copier.yml` (D6); conditional dependencies
      in `pyproject.toml.jinja`, conditional `.env.example` entries, and `_exclude` rules so
      DB files aren't rendered when it's false.
- [ ] **3.9** (`with_database`) `infrastructure/db/`: engine/session setup, `Base`, Alembic env
      wired to settings, readiness check, `make migrate` / `make migration name=...` targets.
- [ ] **3.10** (`with_database`) testcontainers fixtures in `tests/conftest.py`, `integration`
      marker registered in pytest config, `make test-unit` target (D7).
- [x] **3.11** Tests: error-mapping test, lifespan open/close test, readiness test, settings parsing test.

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
style and `Extra.forbid`, per-route try/except error mapping, minimal ruff rule set.

## Phase 5: Skills (task recipes with code examples)

- [ ] **5.1 `add-feature`**: new feature folder across all layers (domain → use case → adapter → router → tests).
- [ ] **5.2 `add-use-case`**: use case class with ports, span, logging, unit test with fakes.
- [ ] **5.3 `add-repository`** (only when `with_database`): ORM model, Protocol port, repository, migration, integration test.
- [ ] **5.4 `add-setting`**: settings sub-model, `.env.example`, injection into a component, test.
- [ ] **5.5 `add-external-client`**: port + httpx2 adapter, error conversion, retries/timeouts, fake.
- [ ] **5.6** Update `add-endpoint` and `add-event-handler` to link the new docs, use the
      `Annotated` dependencies, `ApiModel`, and the central error handler.

## Phase 6: CI and security

- [ ] **6.1 Trivy** in the template CI (D8), improved on the boilerplate version: pinned
      `aquasecurity/trivy-action` instead of `curl | sh` from `main`, one `fs` job
      (vuln, secret, misconfig) + image scan after `docker build`, `CRITICAL,HIGH`, `--ignore-unfixed`.
      A `.trivyignore` with a comment per entry.
- [ ] **6.2** Dependency audit of `uv.lock` (Trivy fs covers it; decide if a separate step is needed).
- [ ] **6.3** Template repo CI: render with `with_database=true` and `false` (matrix); both
      must pass `make check`, pre-commit and the Docker build.
- [ ] **6.4** Generated service CI runs integration tests (Docker available on the runner, D7).

## Phase 7: Verification

- [ ] **7.1** Render a sample service with and without the database: `make check` +
      pre-commit pass with zero edits in both.
- [ ] **7.2** Deliberately break each rule (domain imports fastapi, `Optional`, `requests`)
      and confirm the tooling fails.
- [ ] **7.3 Agent dry run.** In a rendered sample, ask an agent to "add recipe import by URL"
      using only the repo docs. Review the result against this plan: right folders, ports,
      error mapping, spans, tests with fakes. Fix the docs where the agent went wrong. Repeat once.
- [ ] **7.4** Check that `AGENTS.md` stays under about 150 lines and every link resolves.

## Phase 8: Release

- [ ] **8.1** Update the template repo's `AGENTS.md` / `README.md` (new docs, new Copier question).
- [ ] **8.2** Tag `v0.2.0`; tag message lists breaking changes and steps for existing services
      (new dev dependency, `make check` now includes imports, new settings layout).
- [ ] **8.3** Record the decisions D1–D10 as ADRs in meal-platform `docs/adr/`.

## Progress log

| Date | Change |
|---|---|
| 2026-10-26 | Plan drafted; decisions D1–D5 agreed. |
| 2026-10-26 | Q1–Q4 answered → D6 (DB opt-in), D7 (testcontainers), D8 (Trivy), D9 (auth out of scope). |
| 2026-10-26 | httpx replaced by httpx2 in the template (OTel httpx instrumentation supports it since 0.66b1). |
| 2026-10-26 | D10 agreed: Valkey server, redis-py client. |
| 2026-10-26 | Chunk 1 done (Phase 2, 3.1–3.7, 3.11) on branch `feat/architecture-chunk-1`: import-linter (2.15) with `make imports`, banned APIs, CI runs `make check`, error/ApiModel/AppState/settings/HTTP-client skeleton with tests. Decided while implementing: direct-imports-only forbidden contract, `AppState` in `api/dependencies.py`, `SecretStr` as docstring example, global httpx2 tracing kept. |
