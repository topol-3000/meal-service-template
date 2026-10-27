"""Every link and every code reference in the rendered agent docs must resolve.

usage, from the rendered service (its venv imports the package and the libraries):
    uv run python <template repo>/tools/docs-check/check_refs.py .

Checked: AGENTS.md, README.md, docs/**/*.md, .claude/skills/*/SKILL.md.
- Links: relative targets exist; `#anchors` match a heading of the target.
- Inline code in prose (not fenced blocks), each token must be one of:
  a path in the service (placeholders like `<feature>` check the part before them),
  a `make` target, an env variable `Settings` reads or `.env.example` lists, a name defined
  in src/ or tests/ (module, class, function, fixture, attribute, constant), a string
  literal in src/ or tests/ (log events, metric names, attribute values), text that
  appears verbatim in src/ or tests/, a name defined by an example in docs/ or a skill
  (AGENTS.md and README.md only name what exists), a skill name, or an external name from
  EXTERNAL, which is imported to prove it exists.
  ILLUSTRATIVE lists made-up names the docs use as examples of a naming style.
"""

import ast
import builtins
import importlib
import keyword
import re
import sys
from pathlib import Path

from check_examples import FENCE, agent_docs  # same files and fences as the example checker

# Library names the docs mention, with where they live. Each is imported.
EXTERNAL = {
    "Annotated": "typing.Annotated", "Protocol": "typing.Protocol", "TypedDict": "typing.TypedDict",
    "Literal": "typing.Literal", "Self": "typing.Self", "NewType": "typing.NewType",
    "typing.Self": "typing.Self", "typing.override": "typing.override", "@typing.override": "typing.override",
    "typing.Protocol": "typing.Protocol", "Any": "typing.Any", "cast": "typing.cast", "Optional": "typing.Optional",
    "Union": "typing.Union", "List": "typing.List", "Dict": "typing.Dict", "TypeVar": "typing.TypeVar",
    "typing.Optional": "typing.Optional", "typing.Union": "typing.Union", "typing.List": "typing.List",
    "typing.Dict": "typing.Dict", "StrEnum": "enum.StrEnum", "Sequence": "collections.abc.Sequence",
    "Mapping": "collections.abc.Mapping", "Iterable": "collections.abc.Iterable",
    "AsyncIterator": "collections.abc.AsyncIterator", "Callable": "collections.abc.Callable",
    "collections.abc": "collections.abc", "dataclasses.replace": "dataclasses.replace",
    "@dataclass": "dataclasses.dataclass", "AsyncExitStack": "contextlib.AsyncExitStack",
    "asyncio.to_thread": "asyncio.to_thread", "time.sleep": "time.sleep", "os.environ": "os.environ",
    "unittest.mock": "unittest.mock", "logging.getLogger": "logging.getLogger", "print": "builtins.print",
    "BaseModel": "pydantic.BaseModel", "Field": "pydantic.Field", "SecretStr": "pydantic.SecretStr",
    "HttpUrl": "pydantic.HttpUrl", "PositiveFloat": "pydantic.PositiveFloat", "PositiveInt": "pydantic.PositiveInt",
    "field_validator": "pydantic.field_validator", "ConfigDict": "pydantic.ConfigDict",
    "model_dump_json": "pydantic.BaseModel.model_dump_json", "model_validate_json": "pydantic.BaseModel.model_validate_json",
    "model_dump_json()": "pydantic.BaseModel.model_dump_json", "model_validate_json()": "pydantic.BaseModel.model_validate_json",
    "HTTPException": "fastapi.HTTPException", "Depends": "fastapi.Depends", "TestClient": "fastapi.testclient.TestClient",
    "httpx2.AsyncClient": "httpx2.AsyncClient", "httpx2.MockTransport": "httpx2.MockTransport",
    "Mapped": "sqlalchemy.orm.Mapped", "mapped_column": "sqlalchemy.orm.mapped_column",
    "mapped_column()": "sqlalchemy.orm.mapped_column", "selectinload": "sqlalchemy.orm.selectinload",
    "selectinload()": "sqlalchemy.orm.selectinload", "select()": "sqlalchemy.select", "text()": "sqlalchemy.text",
    "DeclarativeBase": "sqlalchemy.orm.DeclarativeBase", "Query": "sqlalchemy.orm.Query",
    "session.query": "sqlalchemy.orm.Session.query", "session.execute()": "sqlalchemy.ext.asyncio.AsyncSession.execute",
    "session.scalars()": "sqlalchemy.ext.asyncio.AsyncSession.scalars", "session.get()": "sqlalchemy.ext.asyncio.AsyncSession.get",
    "commit()": "sqlalchemy.ext.asyncio.AsyncSession.commit", "rollback()": "sqlalchemy.ext.asyncio.AsyncSession.rollback",
    "AsyncSession": "sqlalchemy.ext.asyncio.AsyncSession", "async_sessionmaker": "sqlalchemy.ext.asyncio.async_sessionmaker",
    "IntegrityError": "sqlalchemy.exc.IntegrityError", "sa.table()": "sqlalchemy.table",
    "op.execute()": "alembic.op.execute", "op.get_context().autocommit_block()": "alembic.runtime.migration.MigrationContext.autocommit_block",
    "autocommit_block()": "alembic.runtime.migration.MigrationContext.autocommit_block",
    "Redis": "redis.asyncio.Redis", "redis.asyncio": "redis.asyncio",
    "pytest.raises": "pytest.raises", "@pytest.mark.parametrize": "pytest.mark.parametrize",
    "@pytest.mark.integration": "pytest.mark", "pytestmark": "pytest.mark", "capsys": "_pytest.capture.capsys",
    "monkeypatch": "_pytest.monkeypatch.monkeypatch", "uvicorn.run": "uvicorn.run",
    "InMemorySpanExporter": "opentelemetry.sdk.trace.export.in_memory_span_exporter.InMemorySpanExporter",
    "InMemoryLogRecordExporter": "opentelemetry.sdk._logs.export.InMemoryLogRecordExporter",
    "InMemoryMetricReader": "opentelemetry.sdk.metrics.export.InMemoryMetricReader",
    "fastapi": "fastapi", "starlette": "starlette", "sqlalchemy": "sqlalchemy", "httpx2": "httpx2",
    "redis": "redis", "pydantic_settings": "pydantic_settings", "requests": None, "aiohttp": None,
    "httpx": None, "valkey": None, "valkey-glide": None, "dependency-injector": None, "fastapi-class": None,
    "fastapi-utils": None, "uv_build": None,
    ".get_secret_value()": "pydantic.SecretStr.get_secret_value",
    "span.set_attribute": "opentelemetry.trace.Span.set_attribute",
}
# Terms of the tools around the code (Valkey commands, PostgreSQL and Alembic names, naming
# styles) and paths in the meal-platform repository.
TERMS = {
    "MONITOR", "SLOWLOG", "SCAN", "REINDEX CONCURRENTLY", "INVALID", "alembic_version", ":name",
    "snake_case", "PascalCase", "UPPER_SNAKE", "**kwargs", "contracts/", "contracts/openapi/",
}
# Names in a naming-style example, not references to code. Kept short on purpose.
ILLUSTRATIVE = {
    "recipe.imported", "recipes.imported", "plan.generate", "recipe.id", "GeneratePlan",
    "generate_plan.py", "RecipeRepositoryInterface", "test_plan_days_2", "LlmSettings",
    "LLM__API_KEY", "api_key: SecretStr", "if provider == ...", "note: str | None = None",
    "utils.py", "helpers.py",
}
# Semantic-convention and OTel names set by libraries, not by this code.
OTEL = {
    "db.query.text", "db.system.name", "http.server.request.duration", "http.request.method",
    "OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_METRIC_EXPORT_INTERVAL", "OTEL_RESOURCE_ATTRIBUTES",
    "OTEL_*", "trace_id", "span_id", "GET ?", "cache_lookups_total",
}
PATH_EXT = (".py", ".md", ".toml", ".yml", ".yaml", ".lock", ".example", ".cfg")
COMMAND = re.compile(r"^(uv|uvx|python|git|docker|cp|curl|alembic)\b")


def slug(heading: str) -> str:
    text = re.sub(r"`", "", heading.strip().lower())
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def prose(text: str) -> str:
    return FENCE.sub("", text)


def index(root: Path, package: str) -> tuple[set[str], set[str], str]:
    names: set[str] = set()
    strings: set[str] = set()
    source = []
    for path in [*root.glob("src/**/*.py"), *root.glob("tests/**/*.py")]:
        text = path.read_text()
        source.append(text)
        rel = path.relative_to(root / "src") if "src" in path.parts else path.relative_to(root)
        module = ".".join(rel.with_suffix("").parts).removesuffix(".__init__")
        names.update({module, module.split(".")[-1]})
        names_and_strings(text, names, strings)
    for config in ("pyproject.toml", "Makefile", ".env.example", ".gitignore", "Dockerfile", ".copier-answers.yml"):
        source.append((root / config).read_text())
    return names, strings, "\n".join(source)


def names_and_strings(code: str, names: set[str], strings: set[str]) -> None:
    for node in ast.walk(ast.parse(code)):
        if isinstance(node, ast.ClassDef):
            for member in node.body:
                if isinstance(member, ast.FunctionDef | ast.AsyncFunctionDef):
                    names.add(f"{node.name}.{member.name}")
                elif isinstance(member, ast.AnnAssign) and isinstance(member.target, ast.Name):
                    names.add(f"{node.name}.{member.target.id}")
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store):
            names.add(node.attr)
        elif isinstance(node, ast.TypeAlias):
            names.add(node.name.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            strings.add(node.value)


def example_names(root: Path) -> tuple[set[str], set[str], str]:
    names: set[str] = set()
    strings: set[str] = set()
    text = []
    for name in agent_docs(root):
        for match in FENCE.finditer((root / name).read_text()):
            lang, code = match[1], match[2]
            text.append(code)
            first = code.splitlines()[0] if code else ""
            if m := re.fullmatch(r"# (?:add to )?(\S+\.py)", first):
                parts = Path(m[1]).parts
                names.update({m[1], *("/".join(parts[i:]) for i in range(len(parts)))})
                names.update("/".join(parts[i:-1]) + "/" for i in range(len(parts) - 1))
            if lang == "diff":
                code = "\n".join(l[1:] for l in code.splitlines() if l[:1] == "+" and not l.startswith("+++"))
            try:
                names_and_strings(code, names, strings)
            except SyntaxError:
                pass
    return names, strings, "\n".join(text)


def env_names(root: Path, package: str) -> set[str]:
    sys.path.insert(0, str(root / "src"))
    settings = importlib.import_module(f"{package}.settings")
    found: set[str] = set()
    for field, info in settings.Settings.model_fields.items():
        found.add(field.upper())
        sub = info.annotation
        if isinstance(sub, type) and hasattr(sub, "model_fields"):
            found.update(f"{field.upper()}__{name.upper()}" for name in sub.model_fields)
    for line in (root / ".env.example").read_text().splitlines():
        if m := re.match(r"#?\s*([A-Z][A-Z0-9_]+)=", line):
            found.add(m[1])
    return found


def importable(path: str | None) -> bool:
    if path is None:  # a banned or absent package: named, never imported
        return True
    parts = path.split(".")
    for i in range(len(parts), 0, -1):
        try:
            obj = importlib.import_module(".".join(parts[:i]))
        except ImportError:
            continue
        try:
            for attr in parts[i:]:
                obj = getattr(obj, attr)
        except AttributeError:
            return False
        return True
    return False


def check(root: Path) -> list[str]:
    package = next(p.name for p in (root / "src").iterdir() if p.is_dir())
    names, strings, source = index(root, package)
    envs = env_names(root, package)
    targets = set(re.findall(r"^([a-z][a-z-]*):", (root / "Makefile").read_text(), re.M))
    examples = example_names(root)
    docs = [root / "AGENTS.md", root / "README.md", *(root / name for name in agent_docs(root))]
    problems: list[str] = []

    for doc in docs:
        rel = doc.relative_to(root)
        ex_names, ex_strings, ex_text = examples if doc.name not in ("AGENTS.md", "README.md") else (set(), set(), "")
        text = prose(doc.read_text())

        for target in re.findall(r"\]\(([^)\s]+)\)", text):
            if target.startswith(("http://", "https://")):
                continue
            file_part, _, anchor = target.partition("#")
            target_path = (doc.parent / file_part).resolve() if file_part else doc
            if not target_path.exists():
                problems.append(f"{rel}: link to missing {target}")
                continue
            if anchor:
                headings = {slug(h) for h in re.findall(r"^#+ (.+)$", prose(target_path.read_text()), re.M)}
                if anchor not in headings:
                    problems.append(f"{rel}: link to missing anchor {target}")

        for span in re.findall(r"`([^`\n]+)`", text):
            if not resolves(span, root, package, names, strings, source, envs, targets,
                            ex_names, ex_strings, ex_text):
                problems.append(f"{rel}: unresolved `{span}`")
    return problems


def resolves(token, root, package, names, strings, source, envs, targets, ex_names, ex_strings, ex_text) -> bool:  # noqa: PLR0911, PLR0912
    t = token.strip()
    if t in ILLUSTRATIVE or t in OTEL or t in TERMS or t in ex_names or t in ex_strings:
        return True
    if t in EXTERNAL and importable(EXTERNAL[t]):
        return True
    if t.startswith("make "):
        return t.split()[1] in targets
    if t.startswith("python -m "):
        return t.split()[2] == package
    if COMMAND.match(t) or "://" in t or re.fullmatch(r"[\d.\s%]+|true|false|None", t):
        return True
    if "<" in t:  # a placeholder path or name: check what comes before it
        prefix = t.split("<", 1)[0]
        if not prefix or prefix in ("$",):
            return True
        prefix = prefix.rsplit("/", 1)[0] + "/" if "/" in prefix else prefix
        return resolves(prefix.rstrip("_:"), root, package, names, strings, source, envs, targets,
                        ex_names, ex_strings, ex_text) if prefix.strip("_:") else True
    if "/" in t or t.endswith(PATH_EXT) or (t.startswith(".") and len(t) > 1):
        bare = t.rstrip("/")
        for base in (root, root / "src" / package, root / "src" / package / "infrastructure" / "db"):
            if (base / bare).exists():
                return True
        return t in ex_names or bare + "/" in ex_names or t in source
    if (root / ".claude" / "skills" / t / "SKILL.md").exists():
        return True
    if re.fullmatch(r"[A-Z][A-Z0-9_]+", t) and t not in ("T20", "UP", "FBT"):
        return t in envs or t in names or t in strings or t in ex_names
    if t in strings or t in names or keyword.iskeyword(t) or hasattr(builtins, t):
        return True
    head = re.split(r"[(\[ =]", t, maxsplit=1)[0].rstrip(".")
    if head and (head in names or head in ex_names or (head in EXTERNAL and importable(EXTERNAL[head]))):
        return True
    for candidate in {t, head, head.removeprefix("@")}:
        if candidate and (candidate in source or candidate in ex_text):
            return True
    dotted = head.removeprefix(f"{package}.")
    if importable(f"{package}.{dotted}") if dotted != head else False:
        return True
    return False


if __name__ == "__main__":
    problems = check(Path(sys.argv[1]).resolve())
    print("\n".join(problems) or "all links and references resolve")
    sys.exit(1 if problems else 0)
