"""Extract, resolve, and rewrite import statements across Python and JS/TS."""

from __future__ import annotations

import ast
import os
import re
from pathlib import PurePosixPath

from ..models import Lang

# ---------------------------------------------------------------------------
# JS/TS import regex
# ---------------------------------------------------------------------------

_JS_IMPORT_RE = re.compile(
    r"""(?:import|export)\s+.*?\s+from\s+['"]([^'"]+)['"]"""
    r"""|require\s*\(\s*['"]([^'"]+)['"]\s*\)"""
    r"""|import\s*\(\s*['"]([^'"]+)['"]\s*\)""",
    re.MULTILINE | re.DOTALL,
)

# ---------------------------------------------------------------------------
# extract_imports
# ---------------------------------------------------------------------------


def extract_imports(source: str, lang: Lang) -> list[str]:
    """Dispatch to the appropriate language-specific import extractor."""
    if lang is Lang.PYTHON:
        return _extract_imports_python(source)
    if lang in (Lang.JAVASCRIPT, Lang.TYPESCRIPT):
        return _extract_imports_js(source)
    return []


def _extract_imports_python(source: str) -> list[str]:
    """Walk the Python AST and collect imported module names."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.append(node.module)
    return modules


def _extract_imports_js(source: str) -> list[str]:
    """Use regex to extract JS/TS import paths."""
    results: list[str] = []
    for match in _JS_IMPORT_RE.finditer(source):
        results.extend(group for group in match.groups() if group is not None)
    return results


# ---------------------------------------------------------------------------
# resolve_import
# ---------------------------------------------------------------------------


def resolve_import(
    import_target: str,
    importer_path: str,
    file_index: dict[str, str],
    lang: Lang,
) -> str | None:
    """Map an import string to an absolute file path using *file_index*."""
    if lang is Lang.PYTHON:
        return _resolve_python(import_target, file_index)
    if lang in (Lang.JAVASCRIPT, Lang.TYPESCRIPT):
        return _resolve_js(import_target, importer_path, file_index)
    return None


def _resolve_python(import_target: str, file_index: dict[str, str]) -> str | None:
    rel = import_target.replace(".", "/")
    for candidate in (f"{rel}.py", f"{rel}/__init__.py"):
        if candidate in file_index:
            return file_index[candidate]
    return None


def _resolve_js(
    import_target: str,
    importer_path: str,
    file_index: dict[str, str],
) -> str | None:
    if import_target.startswith(("./", "../")):
        base_dir = str(PurePosixPath(importer_path).parent)
        path = os.path.normpath(os.path.join(base_dir, import_target))
    else:
        path = import_target

    candidates = [
        path,
        f"{path}.js",
        f"{path}.ts",
        f"{path}.tsx",
        f"{path}/index.js",
        f"{path}/index.ts",
    ]
    for candidate in candidates:
        if candidate in file_index:
            return file_index[candidate]
    return None


# ---------------------------------------------------------------------------
# rewrite_imports
# ---------------------------------------------------------------------------


def rewrite_imports(
    source: str,
    renames: dict[str, str],
    lang: Lang,
    current_file: str,
) -> str:
    """Rewrite import paths in *source* according to the *renames* mapping."""
    if lang is Lang.PYTHON:
        return _rewrite_imports_python(source, renames)
    if lang in (Lang.JAVASCRIPT, Lang.TYPESCRIPT):
        return _rewrite_imports_js(source, renames, current_file)
    return source


def _path_to_dotted(path: str) -> str:
    """Convert a file path like ``foo/bar.py`` to a dotted module ``foo.bar``."""
    # strip .py suffix
    path = path.removesuffix(".py")
    # strip trailing /__init__
    path = path.removesuffix("/__init__")
    return path.replace("/", ".")


def _rewrite_imports_python(source: str, renames: dict[str, str]) -> str:
    """Line-by-line regex rewrite of Python imports for formatting fidelity."""
    # Build old-dotted -> new-dotted mapping
    dot_map: dict[str, str] = {}
    for old_path, new_path in renames.items():
        old_mod = _path_to_dotted(old_path)
        new_mod = _path_to_dotted(new_path)
        if old_mod != new_mod:
            dot_map[old_mod] = new_mod

    if not dot_map:
        return source

    lines = source.split("\n")
    new_lines: list[str] = []

    # Pattern for "from <module> import ..."
    from_re = re.compile(r"^(\s*from\s+)(\S+)(\s+import\s+.*)$")
    # Pattern for "import <module>" (possibly with comma-separated modules)
    import_re = re.compile(r"^(\s*import\s+)(.+)$")

    for line in lines:
        m = from_re.match(line)
        if m:
            prefix, module, suffix = m.groups()
            if module in dot_map:
                line = f"{prefix}{dot_map[module]}{suffix}"
            new_lines.append(line)
            continue

        m = import_re.match(line)
        if m:
            prefix, rest = m.groups()
            parts = [p.strip() for p in rest.split(",")]
            changed = False
            new_parts: list[str] = []
            for part in parts:
                # Handle "module as alias"
                tokens = part.split()
                mod = tokens[0]
                if mod in dot_map:
                    tokens[0] = dot_map[mod]
                    changed = True
                new_parts.append(" ".join(tokens))
            if changed:
                line = prefix + ", ".join(new_parts)
            new_lines.append(line)
            continue

        new_lines.append(line)

    return "\n".join(new_lines)


def _rewrite_imports_js(
    source: str,
    renames: dict[str, str],
    current_file: str,
) -> str:
    """Regex-replace old relative imports with new relative imports in JS/TS."""
    cur_dir = str(PurePosixPath(current_file).parent)

    for old_path, new_path in renames.items():
        old_rel = os.path.relpath(old_path, cur_dir)
        new_rel = os.path.relpath(new_path, cur_dir)

        # Ensure relative paths start with ./
        if not old_rel.startswith("."):
            old_rel = "./" + old_rel
        if not new_rel.startswith("."):
            new_rel = "./" + new_rel

        # Normalise to forward slashes (for Windows compat, though unlikely)
        old_rel = old_rel.replace(os.sep, "/")
        new_rel = new_rel.replace(os.sep, "/")

        # Strip known extensions so we match bare specifiers too
        for ext in (".js", ".ts", ".tsx"):
            if old_rel.endswith(ext):
                old_rel_bare = old_rel[: -len(ext)]
                break
        else:
            old_rel_bare = old_rel

        for ext in (".js", ".ts", ".tsx"):
            if new_rel.endswith(ext):
                new_rel_bare = new_rel[: -len(ext)]
                break
        else:
            new_rel_bare = new_rel

        # Replace both with-extension and bare forms inside string literals
        for old_variant, new_variant in (
            (old_rel, new_rel),
            (old_rel_bare, new_rel_bare),
        ):
            escaped = re.escape(old_variant)
            source = re.sub(
                r"(?<=['\"])" + escaped + r"(?=['\"])",
                new_variant,
                source,
            )

    return source
