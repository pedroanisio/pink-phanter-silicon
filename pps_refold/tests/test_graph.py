"""Tests for pps_refold.extern.graph."""

from __future__ import annotations

from pps_refold.extern.graph import build_reverse_graph, detect_smells
from pps_refold.models import FileEntry, Lang

# -- helpers ------------------------------------------------------------------


def _entry(path: str, lang: Lang = Lang.PYTHON) -> FileEntry:
    return FileEntry(path=path, lang=lang, size_bytes=100, hash="deadbeef")


# -- build_reverse_graph ------------------------------------------------------


def test_build_reverse_graph_simple():
    """A imports B -- reverse graph must contain B -> [A]."""
    inventory = {
        "A.py": _entry("A.py"),
        "B.py": _entry("B.py"),
    }
    file_index = {"B_module": "B.py"}
    sources = {"A.py": "import B_module", "B.py": ""}

    def extract_fn(source: str, lang: Lang) -> list[str]:
        if "B_module" in source:
            return ["B_module"]
        return []

    def resolve_fn(target: str, importer: str, idx: dict[str, str], lang: Lang) -> str | None:
        return idx.get(target)

    def read_fn(rel_path: str) -> str:
        return sources[rel_path]

    result = build_reverse_graph(inventory, extract_fn, resolve_fn, file_index, read_fn)
    assert "B.py" in result
    assert result["B.py"] == ["A.py"]


def test_build_reverse_graph_no_imports():
    """Files with no imports produce an empty reverse graph."""
    inventory = {
        "A.py": _entry("A.py"),
        "B.py": _entry("B.py"),
    }

    def extract_fn(source: str, lang: Lang) -> list[str]:
        return []

    def resolve_fn(target: str, importer: str, idx: dict[str, str], lang: Lang) -> str | None:
        return None

    def read_fn(rel_path: str) -> str:
        return ""

    result = build_reverse_graph(inventory, extract_fn, resolve_fn, {}, read_fn)
    assert result == {}


def test_build_reverse_graph_unresolved():
    """If resolve_fn returns None, the import is not added to the graph."""
    inventory = {"A.py": _entry("A.py")}

    def extract_fn(source: str, lang: Lang) -> list[str]:
        return ["unknown_module"]

    def resolve_fn(target: str, importer: str, idx: dict[str, str], lang: Lang) -> str | None:
        return None

    def read_fn(rel_path: str) -> str:
        return "import unknown_module"

    result = build_reverse_graph(inventory, extract_fn, resolve_fn, {}, read_fn)
    assert result == {}


# -- detect_smells: circular dependency ----------------------------------------


def test_detect_circular_dependency():
    """A imports B and B imports A -- should detect a circular dependency."""
    reverse_graph = {
        "B.py": ["A.py"],
        "A.py": ["B.py"],
    }
    inventory = {
        "A.py": _entry("A.py"),
        "B.py": _entry("B.py"),
    }
    smells = detect_smells(reverse_graph, inventory, "/root")
    circular = [s for s in smells if "Circular" in s]
    assert len(circular) >= 1


# -- detect_smells: god module -------------------------------------------------


def test_detect_god_module():
    """A file imported by 11 others (threshold=10) triggers 'God module'."""
    importers = [f"importer_{i}.py" for i in range(11)]
    reverse_graph = {"god.py": importers}
    inventory = {"god.py": _entry("god.py")}
    for imp in importers:
        inventory[imp] = _entry(imp)

    smells = detect_smells(reverse_graph, inventory, "/root", god_module_threshold=10)
    god_smells = [s for s in smells if "God module" in s]
    assert len(god_smells) == 1
    assert "god.py" in god_smells[0]


def test_detect_god_module_below_threshold():
    """A file imported by only 5 others (threshold=10) must not be flagged."""
    importers = [f"importer_{i}.py" for i in range(5)]
    reverse_graph = {"popular.py": importers}
    inventory = {"popular.py": _entry("popular.py")}
    for imp in importers:
        inventory[imp] = _entry(imp)

    smells = detect_smells(reverse_graph, inventory, "/root", god_module_threshold=10)
    god_smells = [s for s in smells if "God module" in s]
    assert god_smells == []


# -- detect_smells: orphan file ------------------------------------------------


def test_detect_orphan_file():
    """A file with no importers and no imports (not a test, not __init__) is orphan."""
    reverse_graph: dict[str, list[str]] = {}
    inventory = {"lonely.py": _entry("lonely.py")}

    smells = detect_smells(reverse_graph, inventory, "/root")
    orphan_smells = [s for s in smells if "Orphan" in s]
    assert len(orphan_smells) == 1
    assert "lonely.py" in orphan_smells[0]


def test_no_orphan_for_test_file():
    """A file named test_something.py must not be flagged as orphan."""
    reverse_graph: dict[str, list[str]] = {}
    inventory = {"test_something.py": _entry("test_something.py")}

    smells = detect_smells(reverse_graph, inventory, "/root")
    orphan_smells = [s for s in smells if "Orphan" in s]
    assert orphan_smells == []


def test_no_orphan_for_init():
    """__init__.py must not be flagged as orphan."""
    reverse_graph: dict[str, list[str]] = {}
    inventory = {"pkg/__init__.py": _entry("pkg/__init__.py")}

    smells = detect_smells(reverse_graph, inventory, "/root")
    orphan_smells = [s for s in smells if "Orphan" in s]
    assert orphan_smells == []


# -- detect_smells: deep nesting -----------------------------------------------


def test_detect_deep_nesting():
    """A file at depth 6 (more than 5 slashes) should trigger 'Deep nesting'."""
    deep_path = "a/b/c/d/e/f/module.py"  # 6 slashes
    reverse_graph: dict[str, list[str]] = {}
    inventory = {deep_path: _entry(deep_path)}

    smells = detect_smells(reverse_graph, inventory, "/root")
    deep_smells = [s for s in smells if "Deep nesting" in s]
    assert len(deep_smells) == 1
    assert deep_path in deep_smells[0]


def test_no_deep_nesting_at_5():
    """A file at depth 5 (exactly 5 slashes) should NOT trigger 'Deep nesting'."""
    path = "a/b/c/d/e/module.py"  # 5 slashes
    reverse_graph: dict[str, list[str]] = {}
    inventory = {path: _entry(path)}

    smells = detect_smells(reverse_graph, inventory, "/root")
    deep_smells = [s for s in smells if "Deep nesting" in s]
    assert deep_smells == []
