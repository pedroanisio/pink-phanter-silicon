"""Tests for codebase_refactor.extern.filesystem."""

from __future__ import annotations

import hashlib
import re

from codebase_refactor.extern.filesystem import (
    copy_file,
    detect_lang,
    dir_exists,
    dir_is_empty,
    file_exists,
    hash_file,
    mkdir,
    move_file,
    parent_dirs,
    read_file,
    rmdir,
    walk_tree,
    write_file,
)
from codebase_refactor.models import Lang

# -- detect_lang ---------------------------------------------------------------


def test_detect_lang_python():
    assert detect_lang("src/app.py") is Lang.PYTHON


def test_detect_lang_js():
    assert detect_lang("index.js") is Lang.JAVASCRIPT


def test_detect_lang_ts():
    assert detect_lang("index.ts") is Lang.TYPESCRIPT
    assert detect_lang("component.tsx") is Lang.TYPESCRIPT


def test_detect_lang_md():
    assert detect_lang("README.md") is Lang.MARKDOWN


def test_detect_lang_other():
    assert detect_lang("data.txt") is Lang.OTHER
    assert detect_lang("config.json") is Lang.OTHER


def test_detect_lang_case_insensitive():
    assert detect_lang("SCRIPT.PY") is Lang.PYTHON


# -- dir_exists ----------------------------------------------------------------


def test_dir_exists_true(tmp_path):
    d = tmp_path / "mydir"
    d.mkdir()
    assert dir_exists(str(d)) is True


def test_dir_exists_false(tmp_path):
    assert dir_exists(str(tmp_path / "nonexistent")) is False


# -- file_exists ---------------------------------------------------------------


def test_file_exists_true(tmp_path):
    f = tmp_path / "hello.txt"
    f.write_text("hi")
    assert file_exists(str(f)) is True


def test_file_exists_false(tmp_path):
    assert file_exists(str(tmp_path / "nope.txt")) is False


# -- hash_file -----------------------------------------------------------------


def test_hash_file(tmp_path):
    f = tmp_path / "data.bin"
    content = b"deterministic content for hashing"
    f.write_bytes(content)

    expected = hashlib.sha256(content).hexdigest()
    assert hash_file(str(f)) == expected


# -- dir_is_empty --------------------------------------------------------------


def test_dir_is_empty_true(tmp_path):
    d = tmp_path / "empty"
    d.mkdir()
    assert dir_is_empty(str(d)) is True


def test_dir_is_empty_false(tmp_path):
    d = tmp_path / "notempty"
    d.mkdir()
    (d / "file.txt").write_text("content")
    assert dir_is_empty(str(d)) is False


# -- parent_dirs ---------------------------------------------------------------


def test_parent_dirs(tmp_path):
    root = tmp_path / "a"
    nested = root / "b" / "c"
    nested.mkdir(parents=True)
    target = nested / "file.py"
    target.touch()

    result = parent_dirs(str(target), str(root))

    # Should include "a/b/c" and "a/b" (child-first order) but NOT "a" itself.
    assert len(result) == 2
    # The first entry is the immediate parent of the file.
    assert result[0] == str(nested)
    assert result[1] == str(root / "b")


# -- read_file -----------------------------------------------------------------


def test_read_file_utf8(tmp_path):
    f = tmp_path / "utf8.txt"
    content = "Hello, world! \u00e9\u00e8\u00ea"
    f.write_text(content, encoding="utf-8")

    assert read_file(str(f)) == content


def test_read_file_latin1_fallback(tmp_path):
    f = tmp_path / "latin1.txt"
    # 0xe9 = 'e-acute' in latin-1, invalid as a standalone byte in utf-8
    raw = b"caf\xe9"
    f.write_bytes(raw)

    result = read_file(str(f))
    assert result == raw.decode("latin-1")


# -- walk_tree -----------------------------------------------------------------


def test_walk_tree_basic(tmp_path):
    (tmp_path / "a.py").write_text("# python")
    (tmp_path / "b.js").write_text("// js")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.ts").write_text("// ts")

    entries = walk_tree(str(tmp_path), ignore_patterns=set())

    assert "a.py" in entries
    assert "b.js" in entries
    assert "sub/c.ts" in entries
    assert entries["a.py"].lang is Lang.PYTHON
    assert entries["b.js"].lang is Lang.JAVASCRIPT
    assert entries["sub/c.ts"].lang is Lang.TYPESCRIPT


def test_walk_tree_ignore(tmp_path):
    (tmp_path / "keep.py").write_text("keep")
    (tmp_path / "skip.pyc").write_text("skip")
    hidden = tmp_path / ".hidden"
    hidden.mkdir()
    (hidden / "secret.py").write_text("secret")

    entries = walk_tree(str(tmp_path), ignore_patterns={"*.pyc", ".hidden"})

    assert "keep.py" in entries
    assert "skip.pyc" not in entries
    # The entire .hidden directory should be pruned.
    assert all(not key.startswith(".hidden") for key in entries)


def test_walk_tree_hashes(tmp_path):
    (tmp_path / "f.py").write_text("content")

    entries = walk_tree(str(tmp_path), ignore_patterns=set())
    h = entries["f.py"].hash

    # SHA-256 hex digest is exactly 64 hex characters.
    assert len(h) == 64
    assert re.fullmatch(r"[0-9a-f]{64}", h)


# -- write_file ----------------------------------------------------------------


def test_write_file(tmp_path):
    target = tmp_path / "out.txt"
    write_file(str(target), "hello", dry_run=False)
    assert target.read_text() == "hello"


def test_write_file_dry_run(tmp_path):
    target = tmp_path / "ghost.txt"
    result = write_file(str(target), "hello", dry_run=True)
    assert result is True
    assert not target.exists()


# -- move_file -----------------------------------------------------------------


def test_move_file(tmp_path):
    src = tmp_path / "src.txt"
    dst = tmp_path / "dst.txt"
    src.write_text("move me")

    result = move_file(str(src), str(dst), dry_run=False)
    assert result is True
    assert not src.exists()
    assert dst.read_text() == "move me"


def test_move_file_dry_run(tmp_path):
    src = tmp_path / "src.txt"
    dst = tmp_path / "dst.txt"
    src.write_text("stay put")

    result = move_file(str(src), str(dst), dry_run=True)
    assert result is True
    assert src.exists()
    assert not dst.exists()


# -- mkdir ---------------------------------------------------------------------


def test_mkdir(tmp_path):
    target = tmp_path / "a" / "b" / "c"
    result = mkdir(str(target), dry_run=False)
    assert result is True
    assert target.is_dir()


def test_mkdir_dry_run(tmp_path):
    target = tmp_path / "x" / "y"
    result = mkdir(str(target), dry_run=True)
    assert result is True
    assert not target.exists()


# -- rmdir ---------------------------------------------------------------------


def test_rmdir(tmp_path):
    target = tmp_path / "removeme"
    target.mkdir()
    assert target.is_dir()

    result = rmdir(str(target), dry_run=False)
    assert result is True
    assert not target.exists()


def test_rmdir_dry_run(tmp_path):
    target = tmp_path / "keepme"
    target.mkdir()

    result = rmdir(str(target), dry_run=True)
    assert result is True
    assert target.is_dir()


# -- copy_file -----------------------------------------------------------------


def test_copy_file(tmp_path):
    src = tmp_path / "orig.txt"
    dst = tmp_path / "copy.txt"
    src.write_text("duplicate")

    result = copy_file(str(src), str(dst), dry_run=False)
    assert result is True
    assert src.exists()
    assert dst.read_text() == "duplicate"


def test_copy_file_dry_run(tmp_path):
    src = tmp_path / "orig.txt"
    dst = tmp_path / "copy.txt"
    src.write_text("original")

    result = copy_file(str(src), str(dst), dry_run=True)
    assert result is True
    assert src.exists()
    assert not dst.exists()
