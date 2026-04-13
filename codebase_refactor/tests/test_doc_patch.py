"""Tests for codebase_refactor.extern.doc_patch."""

from __future__ import annotations

from codebase_refactor.extern.doc_patch import patch_doc_paths


def test_simple_rename():
    content = "See src/foo.py for details"
    renames = {"src/foo.py": "lib/foo.py"}
    result = patch_doc_paths(content, renames)
    assert result == "See lib/foo.py for details"


def test_no_match():
    content = "Nothing to replace here."
    renames = {"src/foo.py": "lib/foo.py"}
    result = patch_doc_paths(content, renames)
    assert result == content


def test_longest_first():
    """The longer path 'src/utils.py.bak' must be tried before 'src/utils.py'
    so that 'src/utils.py.bak' is not partially matched by the shorter key."""
    content = "Check src/utils.py.bak and src/utils.py"
    renames = {
        "src/utils.py": "lib/utils.py",
        "src/utils.py.bak": "lib/utils.py.bak",
    }
    result = patch_doc_paths(content, renames)
    assert result == "Check lib/utils.py.bak and lib/utils.py"


def test_multiple_occurrences():
    content = "Import src/foo.py and also src/foo.py again"
    renames = {"src/foo.py": "lib/foo.py"}
    result = patch_doc_paths(content, renames)
    assert result == "Import lib/foo.py and also lib/foo.py again"


def test_boundary_safety_no_partial():
    """'a' is a non-boundary char (not in {whitespace, quotes, parens, backtick, /}),
    so 'asrc/foo.py' must NOT be replaced. Whitespace and quote boundaries must work."""
    renames = {"src/foo.py": "lib/foo.py"}

    # preceded by 'a' -> lookbehind fails, no replacement
    assert patch_doc_paths("asrc/foo.py", renames) == "asrc/foo.py"

    # preceded by space -> replaced
    assert patch_doc_paths(" src/foo.py", renames) == " lib/foo.py"

    # wrapped in single quotes -> replaced
    assert patch_doc_paths("'src/foo.py'", renames) == "'lib/foo.py'"


def test_empty_renames():
    content = "Nothing changes"
    assert patch_doc_paths(content, {}) == content


def test_path_in_backticks():
    content = "`src/foo.py`"
    renames = {"src/foo.py": "lib/foo.py"}
    result = patch_doc_paths(content, renames)
    assert result == "`lib/foo.py`"


def test_path_after_slash():
    content = "/src/foo.py"
    renames = {"src/foo.py": "lib/foo.py"}
    result = patch_doc_paths(content, renames)
    assert result == "/lib/foo.py"
