# AGENTS.md: meal-service-template

Copier template for every FamilyMeal service (`meal-*`). Architecture, system map and
decisions are in the **meal-platform** repo (`AGENTS.md`, `docs/adr/`).

## Layout

- `copier.yml`: questions and post-generation tasks (`uv lock`, `git init`).
- `template/`: what a generated service gets. Files ending in `.jinja` are rendered;
  everything else is copied as is (so `${{ }}` in GitHub workflows needs no escaping
  unless the file is `.jinja`).
- `template/AGENTS.md.jinja`, `template/docs/` and `template/.claude/skills/`: the agent
  instructions every service inherits. Changes there change how agents work in all services.
  Docs hold the rules; a skill is numbered steps that link to those rules, plus one worked
  example. `tools/docs-check/` checks them (see [Agent docs](#agent-docs)).

## Working on the template

Render and check a sample service after every change, once per combination of
`with_database` and `with_cache` (`true` needs Docker for the integration tests). This is
what CI does:

```bash
uvx copier copy --trust --defaults --vcs-ref HEAD -d service_name=meal-sample \
  -d with_database=true -d with_cache=true . /tmp/meal-sample
cd /tmp/meal-sample && make check && git add -A && uv run pre-commit run --all-files
uv run python "$OLDPWD/tools/docs-check/check_refs.py" .
python3 "$OLDPWD/tools/docs-check/check_examples.py" .
```

`--vcs-ref HEAD` renders the last commit, so commit (locally) before rendering.

CI also runs the service's two Trivy scans on every render. To run them locally (same Trivy
version as the action's `version` default; the fs scan before `uv sync`, as on a checkout):

```bash
docker run --rm -v trivy-cache:/root/.cache/trivy -v /tmp/meal-sample:/src:ro -w /src \
  aquasec/trivy:0.70.0 fs . --scanners vuln,secret,misconfig --include-dev-deps \
  --severity CRITICAL,HIGH --ignore-unfixed --exit-code 1
docker build -t meal-sample:ci /tmp/meal-sample
docker run --rm -v trivy-cache:/root/.cache/trivy -v /var/run/docker.sock:/var/run/docker.sock \
  -v /tmp/meal-sample/.trivyignore:/.trivyignore:ro aquasec/trivy:0.70.0 image meal-sample:ci \
  --scanners vuln,secret --severity CRITICAL,HIGH --ignore-unfixed --exit-code 1 \
  --ignorefile /.trivyignore
```

Fix a finding in the template (dependency bound, Dockerfile, base image) rather than adding
it to `template/.trivyignore`.
Optional parts are Copier questions: their files are listed in `_exclude` in `copier.yml`,
and shared files use `{% if with_database %}` / `{% if with_cache %}` blocks. Check that every
variant renders.

## Agent docs

Every name, path and example in the rendered `AGENTS.md`, `README.md`, `docs/` and
`.claude/skills/*/SKILL.md` must exist and pass `make check`, in every variant. Two
checkers in `tools/docs-check/` take the rendered service as their argument; CI runs both
after `make check`.

`check_examples.py` pastes the fenced examples of one file at a time into a clean checkout
and runs `make check`. A `python` or `diff` block is one of:

- a whole new file: first line `# src/<package>/...py` or `# tests/...py`;
- an addition: first line `# add to <path>`; its leading imports go after the file's
  imports, the rest at the end;
- a diff: `--- <path>` / `+++ <path>`, hunks start with a bare `@@`; context and `-` lines
  must match the file exactly once;
- a standalone module: no path line (becomes `_doc_example_N.py`, or a test module when it
  defines tests).

Other languages (`bash`, `text`, `json`, ...) are not run. A file that builds on another
one's examples (a skill extending a doc's `recipes` example) names it in `DEPENDS`
(paths relative to the service, followed transitively); a dependency the variant doesn't
render is skipped.

`check_refs.py` (run in the service's venv) checks that links and `#anchors` resolve and
that every inline code span in prose names something real: a path, `make` target, env
variable, name or string in `src/` or `tests/`, a name from any doc's or skill's example, or
a skill. Library names go in `EXTERNAL` (each is imported); made-up names that show a
naming style go in `ILLUSTRATIVE`; tool terms and OTel names in `TERMS` / `OTEL`.

When one fails:

- `FAIL <file>` from `check_examples.py` prints the `make check` output: fix the example
  (or the doc it builds on), not the checker. "hunk context found 0 times" means a diff's
  context lines no longer match the rendered file: render the variant and copy them again.
  "exists already" means two files in one `DEPENDS` chain create the same file.
- `unresolved` from `check_refs.py`: the name is misspelt, was renamed in the code, or
  exists only in another variant (wrap the sentence in `{% if with_... %}`). Add to
  `EXTERNAL` / `ILLUSTRATIVE` only for library and made-up names.
- To try one file: `python3 tools/docs-check/check_examples.py <service> .claude/skills/<name>/SKILL.md`.

## Rules

- A generated service must pass `make check` and pre-commit with zero edits.
- Keep the generated service minimal: health endpoints, observability, layering skeleton.
  Business code never goes into the template.
- Dependency lower bounds in `pyproject.toml.jinja` track the latest tested versions.
- Releases are git tags (`v0.1.0`, ...); services pull them with `make update-template`.
  Describe breaking changes for services in the tag message.
