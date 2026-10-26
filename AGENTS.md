# AGENTS.md: meal-service-template

Copier template for every FamilyMeal service (`meal-*`). Architecture, system map and
decisions are in the **meal-platform** repo (`AGENTS.md`, `docs/adr/`).

## Layout

- `copier.yml`: questions and post-generation tasks (`uv lock`, `git init`).
- `template/`: what a generated service gets. Files ending in `.jinja` are rendered;
  everything else is copied as is (so `${{ }}` in GitHub workflows needs no escaping
  unless the file is `.jinja`).
- `template/AGENTS.md.jinja` and `template/.claude/skills/`: the agent instructions every
  service inherits. Changes there change how agents work in all services.

## Working on the template

Render and check a sample service after every change, once per combination of
`with_database` and `with_cache` (`true` needs Docker for the integration tests). This is
what CI does:

```bash
uvx copier copy --trust --defaults --vcs-ref HEAD -d service_name=meal-sample \
  -d with_database=true -d with_cache=true . /tmp/meal-sample
cd /tmp/meal-sample && make check && git add -A && uv run pre-commit run --all-files
```

`--vcs-ref HEAD` renders the last commit, so commit (locally) before rendering.
Optional parts are Copier questions: their files are listed in `_exclude` in `copier.yml`,
and shared files use `{% if with_database %}` / `{% if with_cache %}` blocks. Check that every
variant renders.

## Rules

- A generated service must pass `make check` and pre-commit with zero edits.
- Keep the generated service minimal: health endpoints, observability, layering skeleton.
  Business code never goes into the template.
- Dependency lower bounds in `pyproject.toml.jinja` track the latest tested versions.
- Releases are git tags (`v0.1.0`, ...); services pull them with `make update-template`.
  Describe breaking changes for services in the tag message.
