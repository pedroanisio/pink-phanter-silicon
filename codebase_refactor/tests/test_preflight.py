"""Tests for codebase_refactor.extern.preflight."""

from __future__ import annotations

import os

from codebase_refactor.extern.preflight import preflight_moves, preflight_rewrites


# -- preflight_moves ----------------------------------------------------------


def test_preflight_moves_all_ok(tmp_path):
    """Source file exists and destination parent directory exists."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "a.py").write_text("content")

    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()

    move_map = {"src/a.py": "dst/a.py"}
    assert preflight_moves(move_map, str(tmp_path)) is True


def test_preflight_moves_source_missing(tmp_path):
    """Source file does not exist on disk."""
    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()

    move_map = {"src/a.py": "dst/a.py"}
    assert preflight_moves(move_map, str(tmp_path)) is False


def test_preflight_moves_dest_parent_missing(tmp_path):
    """Destination parent directory does not exist."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "a.py").write_text("content")

    move_map = {"src/a.py": "dst/a.py"}
    assert preflight_moves(move_map, str(tmp_path)) is False


def test_preflight_moves_dest_collision(tmp_path):
    """An existing file at destination that is NOT itself a source."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "a.py").write_text("source content")

    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()
    (dst_dir / "a.py").write_text("collision content")

    move_map = {"src/a.py": "dst/a.py"}
    assert preflight_moves(move_map, str(tmp_path)) is False


def test_preflight_moves_swap_ok(tmp_path):
    """A and B both exist; A->B and B->A is valid because both dests are sources."""
    dir_a = tmp_path / "a"
    dir_a.mkdir()
    (dir_a / "file.py").write_text("content A")

    dir_b = tmp_path / "b"
    dir_b.mkdir()
    (dir_b / "file.py").write_text("content B")

    move_map = {"a/file.py": "b/file.py", "b/file.py": "a/file.py"}
    assert preflight_moves(move_map, str(tmp_path)) is True


# -- preflight_rewrites -------------------------------------------------------


def test_preflight_rewrites_all_accessible(tmp_path):
    """All files under root are readable and writable."""
    (tmp_path / "one.py").write_text("x")
    (tmp_path / "two.py").write_text("y")

    move_map = {"one.py": "two.py"}
    assert preflight_rewrites(move_map, str(tmp_path)) is True


def test_preflight_rewrites_empty_dir(tmp_path):
    """An empty root directory has no files to check -- should pass."""
    assert preflight_rewrites({}, str(tmp_path)) is True
