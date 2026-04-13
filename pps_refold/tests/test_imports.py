"""Tests for pps_refold.extern.imports module."""

from pps_refold.extern.imports import (
    extract_imports,
    resolve_import,
    rewrite_imports,
)
from pps_refold.models import Lang

# ---------------------------------------------------------------------------
# extract_imports -- Python
# ---------------------------------------------------------------------------


def test_extract_python_import():
    result = extract_imports("import os", Lang.PYTHON)
    assert result == ["os"]


def test_extract_python_from_import():
    result = extract_imports("from os.path import join", Lang.PYTHON)
    assert result == ["os.path"]


def test_extract_python_multiple():
    source = "import os\nfrom sys import argv\n"
    result = extract_imports(source, Lang.PYTHON)
    assert "os" in result
    assert "sys" in result


def test_extract_python_syntax_error():
    result = extract_imports("def (", Lang.PYTHON)
    assert result == []


# ---------------------------------------------------------------------------
# extract_imports -- JS/TS
# ---------------------------------------------------------------------------


def test_extract_js_import_from():
    result = extract_imports('import foo from "bar"', Lang.JAVASCRIPT)
    assert result == ["bar"]


def test_extract_js_require():
    result = extract_imports('const x = require("mod")', Lang.JAVASCRIPT)
    assert result == ["mod"]


def test_extract_js_dynamic_import():
    result = extract_imports('import("chunk")', Lang.JAVASCRIPT)
    assert result == ["chunk"]


def test_extract_js_export_from():
    result = extract_imports('export { default } from "./utils"', Lang.JAVASCRIPT)
    assert result == ["./utils"]


def test_extract_js_multiple():
    source = 'import foo from "bar"\nconst x = require("mod")\n'
    result = extract_imports(source, Lang.JAVASCRIPT)
    assert "bar" in result
    assert "mod" in result


# ---------------------------------------------------------------------------
# extract_imports -- Other
# ---------------------------------------------------------------------------


def test_extract_other_lang():
    result = extract_imports("# some markdown", Lang.MARKDOWN)
    assert result == []


# ---------------------------------------------------------------------------
# resolve_import -- Python
# ---------------------------------------------------------------------------


def test_resolve_python_module():
    file_index = {"foo/bar.py": "foo/bar.py"}
    result = resolve_import("foo.bar", "", file_index, Lang.PYTHON)
    assert result == "foo/bar.py"


def test_resolve_python_package():
    file_index = {"foo/__init__.py": "foo/__init__.py"}
    result = resolve_import("foo", "", file_index, Lang.PYTHON)
    assert result == "foo/__init__.py"


def test_resolve_python_not_found():
    result = resolve_import("nonexistent.module", "", {}, Lang.PYTHON)
    assert result is None


# ---------------------------------------------------------------------------
# resolve_import -- JS/TS
# ---------------------------------------------------------------------------


def test_resolve_js_relative():
    file_index = {"src/utils.js": "src/utils.js"}
    result = resolve_import("./utils", "src/app.js", file_index, Lang.JAVASCRIPT)
    assert result == "src/utils.js"


def test_resolve_js_with_extension():
    file_index = {"src/utils.js": "src/utils.js"}
    result = resolve_import("./utils.js", "src/app.js", file_index, Lang.JAVASCRIPT)
    assert result == "src/utils.js"


def test_resolve_js_index():
    file_index = {"src/lib/index.js": "src/lib/index.js"}
    result = resolve_import("./lib", "src/app.js", file_index, Lang.JAVASCRIPT)
    assert result == "src/lib/index.js"


def test_resolve_js_not_found():
    result = resolve_import("./missing", "src/app.js", {}, Lang.JAVASCRIPT)
    assert result is None


# ---------------------------------------------------------------------------
# resolve_import -- Other
# ---------------------------------------------------------------------------


def test_resolve_other_lang():
    result = resolve_import("anything", "file.md", {}, Lang.MARKDOWN)
    assert result is None


# ---------------------------------------------------------------------------
# rewrite_imports -- Python
# ---------------------------------------------------------------------------


def test_rewrite_python_from():
    source = "from foo.bar import baz"
    renames = {"foo/bar.py": "biz/bar.py"}
    result = rewrite_imports(source, renames, Lang.PYTHON, "main.py")
    assert result == "from biz.bar import baz"


def test_rewrite_python_import():
    source = "import foo.bar"
    renames = {"foo/bar.py": "biz/bar.py"}
    result = rewrite_imports(source, renames, Lang.PYTHON, "main.py")
    assert result == "import biz.bar"


def test_rewrite_python_no_match():
    source = "from other.module import thing"
    renames = {"foo/bar.py": "biz/bar.py"}
    result = rewrite_imports(source, renames, Lang.PYTHON, "main.py")
    assert result == source


def test_rewrite_python_syntax_error():
    source = "this is just plain text, not real python"
    renames = {"foo/bar.py": "biz/bar.py"}
    result = rewrite_imports(source, renames, Lang.PYTHON, "main.py")
    assert result == source


# ---------------------------------------------------------------------------
# rewrite_imports -- JS/TS
# ---------------------------------------------------------------------------


def test_rewrite_js_relative():
    source = 'import x from "./utils"'
    renames = {"src/utils.js": "lib/utils.js"}
    result = rewrite_imports(source, renames, Lang.JAVASCRIPT, "src/app.js")
    # After rename, from src/app.js the new relative path to lib/utils.js
    # is ../lib/utils (bare, without .js extension in the specifier).
    assert "./utils" not in result
    assert "lib/utils" in result


# ---------------------------------------------------------------------------
# rewrite_imports -- Other
# ---------------------------------------------------------------------------


def test_rewrite_other_lang():
    source = "# just some markdown content"
    renames = {"foo/bar.py": "biz/bar.py"}
    result = rewrite_imports(source, renames, Lang.MARKDOWN, "readme.md")
    assert result == source
