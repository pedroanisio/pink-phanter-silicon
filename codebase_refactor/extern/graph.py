from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

from ..models import FileEntry, Lang


def build_reverse_graph(
    file_inventory: dict[str, FileEntry],
    extract_fn: Callable[[str, Lang], list[str]],
    resolve_fn: Callable[[str, str, dict[str, str], Lang], str | None],
    file_index: dict[str, str],
    read_fn: Callable[[str], str],
) -> dict[str, list[str]]:
    reverse: dict[str, list[str]] = defaultdict(list)

    for rel_path, entry in file_inventory.items():
        source = read_fn(rel_path)
        raw_imports = extract_fn(source, entry.lang)
        for target in raw_imports:
            resolved = resolve_fn(target, rel_path, file_index, entry.lang)
            if resolved is not None:
                reverse[resolved].append(rel_path)

    return dict(reverse)


def detect_smells(
    reverse_graph: dict[str, list[str]],
    file_inventory: dict[str, FileEntry],
    root: str,  # noqa: ARG001
    god_module_threshold: int = 10,
) -> list[str]:
    smells: list[str] = []

    # -- Circular dependencies (DFS on forward graph) --------------------------
    forward: dict[str, list[str]] = defaultdict(list)
    for imported_file, importers in reverse_graph.items():
        for importer in importers:
            forward[importer].append(imported_file)

    visited: set[str] = set()
    in_stack: set[str] = set()

    for start in forward:
        if start in visited:
            continue
        stack = [start]
        while stack:
            node = stack[-1]
            if node not in visited:
                visited.add(node)
                in_stack.add(node)
                for neighbour in forward.get(node, []):
                    if neighbour in in_stack:
                        smells.append(f"Circular dependency: {node} <-> {neighbour}")
                    elif neighbour not in visited:
                        stack.append(neighbour)
                        break
                else:
                    in_stack.discard(node)
                    stack.pop()
                continue
            in_stack.discard(node)
            stack.pop()

    # -- God modules -----------------------------------------------------------
    for file_path, importers in reverse_graph.items():
        if len(importers) > god_module_threshold:
            smells.append(f"God module: {file_path} ({len(importers)} importers)")

    # -- Orphan files ----------------------------------------------------------
    files_that_import: set[str] = set()
    for importers in reverse_graph.values():
        files_that_import.update(importers)

    for rel_path in file_inventory:
        basename = Path(rel_path).name
        if basename == "__init__.py":
            continue
        if "test" in basename.lower() or "test" in rel_path.lower():
            continue
        has_importers = rel_path in reverse_graph and len(reverse_graph[rel_path]) > 0
        has_imports = rel_path in files_that_import
        if not has_importers and not has_imports:
            smells.append(f"Orphan file: {rel_path}")

    # -- Deep nesting ----------------------------------------------------------
    for rel_path in file_inventory:
        depth = rel_path.replace("\\", "/").count("/")
        if depth > 5:
            smells.append(f"Deep nesting: {rel_path} ({depth} levels deep)")

    return smells
