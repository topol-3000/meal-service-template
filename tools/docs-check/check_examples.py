"""Paste every code example of the rendered agent docs into the service and run `make check`.

usage: python3 tools/docs-check/check_examples.py <rendered service dir> [file ...]

Files are paths relative to the service: docs/**/*.md and .claude/skills/*/SKILL.md (all of
them by default). Block kinds (fenced code):
- ```python whose first line is `# src/...py` or `# tests/...py`: a new file at that path.
- ```python whose first line is `# add to <path>`: its leading imports go after the file's
  imports, the rest is appended (then `ruff check --fix --select I` + `ruff format`).
- ```diff with `--- <path>`: hunks split at `@@` lines; context/`-` lines must match the
  file exactly once and are replaced by context/`+` lines.
- ```python without a path: a standalone module (src/<pkg>/_doc_example_N.py, or
  tests/test_doc_example_N.py when it defines tests).
Each file is applied on top of the files it builds on (DEPENDS, followed transitively; a file
the variant does not render is skipped), in a clean checkout, and the service's
`make check` (ruff, pyright strict, import-linter, pytest) must pass. The service dir must be
a git repository: the checker commits what is there as a base and resets to it after each file.
"""

import ast
import re
import subprocess
import sys
from pathlib import Path

# File -> the files whose examples it builds on. Followed transitively.
DEPENDS = {
    "docs/conventions/errors.md": ["docs/conventions/models.md", "docs/conventions/settings.md"],
    "docs/conventions/testing.md": ["docs/architecture.md"],
    "docs/conventions/persistence.md": ["docs/conventions/models.md"],
    "docs/conventions/caching.md": ["docs/conventions/models.md"],
}
FENCE = re.compile(r"^```(\w*)\n(.*?)^```", re.M | re.S)


def agent_docs(root: Path) -> list[str]:
    """The files with examples, relative to the service root."""
    files = [*(root / "docs").rglob("*.md"), *(root / ".claude" / "skills").glob("*/SKILL.md")]
    return sorted(str(p.relative_to(root)) for p in files)


def chain(root: Path, name: str) -> list[str]:
    """`name` after everything it builds on, each once, dependencies first."""
    ordered: list[str] = []
    for dependency in DEPENDS.get(name, []):
        if (root / dependency).exists():
            ordered += [d for d in chain(root, dependency) if d not in ordered]
    return [*ordered, name]


def blocks(doc: Path) -> list[tuple[str, str]]:
    return [(m[1], m[2]) for m in FENCE.finditer(doc.read_text())]


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)


def ensure_packages(root: Path, path: Path) -> None:
    directory = path.parent
    while directory not in (root, root / "src"):
        init = directory / "__init__.py"
        if not init.exists():
            init.write_text("")
        directory = directory.parent


def add_to(target: Path, code: str) -> None:
    tree = ast.parse(code)
    lines = code.splitlines(keepends=True)
    import_end = 0
    for node in tree.body:
        if isinstance(node, ast.Import | ast.ImportFrom):
            import_end = node.end_lineno or 0
        else:
            break
    imports, rest = "".join(lines[:import_end]), "".join(lines[import_end:])
    text = target.read_text()
    file_lines = text.splitlines(keepends=True)
    last = max(
        (n.end_lineno or 0 for n in ast.parse(text).body if isinstance(n, ast.Import | ast.ImportFrom)),
        default=0,
    )
    text = "".join(file_lines[:last]) + imports + "".join(file_lines[last:])
    target.write_text(text.rstrip("\n") + "\n\n\n" + rest.strip("\n") + "\n")


def apply_diff(root: Path, code: str) -> Path:
    lines = code.splitlines()
    path = root / lines[0].removeprefix("--- ").strip()
    text = path.read_text()
    hunks: list[list[str]] = []
    for line in lines[2:]:
        if line.startswith("@@"):
            hunks.append([])
        else:
            hunks[-1].append(line)
    for hunk in hunks:
        old = [l[1:] for l in hunk if l[:1] in (" ", "-") or l == ""]
        new = [l[1:] for l in hunk if l[:1] in (" ", "+") or l == ""]
        old_text, new_text = "\n".join(old) + "\n", "\n".join(new) + "\n"
        count = text.count(old_text)
        if count != 1:
            raise ValueError(f"{path}: hunk context found {count} times:\n{old_text}")
        text = text.replace(old_text, new_text)
    path.write_text(text)
    return path


def apply(root: Path, package: str, doc: Path, counter: list[int]) -> list[Path]:
    touched: list[Path] = []
    for lang, code in blocks(doc):
        first = code.splitlines()[0] if code.strip() else ""
        if lang == "diff":
            touched.append(apply_diff(root, code))
        elif lang == "python":
            if m := re.fullmatch(r"# add to (\S+\.py)", first):
                target = root / m[1]
                add_to(target, code.split("\n", 1)[1])
                touched.append(target)
            elif m := re.fullmatch(r"# ((?:src|tests)/\S+\.py)", first):
                target = root / m[1]
                if target.exists():
                    raise ValueError(f"{doc.relative_to(root)}: {m[1]} exists already")
                target.parent.mkdir(parents=True, exist_ok=True)
                ensure_packages(root, target)
                # The path line tells the reader where the file goes; it is not content.
                target.write_text(code.split("\n", 1)[1])
            else:
                counter[0] += 1
                if re.search(r"^(async )?def test_", code, re.M):
                    target = root / f"tests/test_doc_example_{counter[0]}.py"
                else:
                    target = root / f"src/{package}/_doc_example_{counter[0]}.py"
                target.write_text(code)
    return touched


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    package = next(p.name for p in (root / "src").iterdir() if p.is_dir())
    wanted = sys.argv[2:] or agent_docs(root)
    if run(["git", "status", "--porcelain"], root).stdout.strip():
        run(["git", "add", "-A"], root)
        run(["git", "commit", "-qm", "base", "--no-verify"], root)
    status = 0
    for name in wanted:
        files = chain(root, name)
        if not any(lang in ("python", "diff") for lang, _ in blocks(root / name)):
            continue
        counter = [0]
        try:
            touched = [p for d in files for p in apply(root, package, root / d, counter)]
            if touched:
                paths = sorted({str(p) for p in touched})
                run(["uv", "run", "ruff", "check", "--fix", "--select", "I", *paths], root)
                run(["uv", "run", "ruff", "format", *paths], root)
            result = run(["make", "check"], root)
            ok = result.returncode == 0
            summary = re.findall(r"\d+ passed[^\n=]*", result.stdout)
            print(f"{'OK  ' if ok else 'FAIL'} {name} (+{', '.join(files[:-1]) or 'nothing'}) {summary[-1] if summary else ''}")
            if not ok:
                status = 1
                print(result.stdout[-6000:], result.stderr[-3000:])
        except Exception as exc:  # noqa: BLE001
            status = 1
            print(f"FAIL {name}: {exc}")
        finally:
            run(["git", "checkout", "-q", "--", "."], root)
            run(["git", "clean", "-fdq"], root)
    return status


if __name__ == "__main__":
    sys.exit(main())
