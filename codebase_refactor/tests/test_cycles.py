"""Tests for codebase_refactor.extern.cycles."""

from __future__ import annotations

from codebase_refactor.models import MoveOp, Lang
from codebase_refactor.extern.cycles import detect_move_cycles


# -- helper -------------------------------------------------------------------


def _move(s: str, d: str) -> MoveOp:
    return MoveOp(source=s, destination=d, lang=Lang.PYTHON)


# -- tests --------------------------------------------------------------------


def test_no_moves():
    assert detect_move_cycles([]) is False


def test_single_move():
    assert detect_move_cycles([_move("A", "B")]) is False


def test_two_moves_no_cycle():
    moves = [_move("A", "B"), _move("C", "D")]
    assert detect_move_cycles(moves) is False


def test_simple_swap():
    moves = [_move("A", "B"), _move("B", "A")]
    assert detect_move_cycles(moves) is True


def test_three_way_cycle():
    moves = [_move("A", "B"), _move("B", "C"), _move("C", "A")]
    assert detect_move_cycles(moves) is True


def test_chain_no_cycle():
    moves = [_move("A", "B"), _move("B", "C")]
    assert detect_move_cycles(moves) is False


def test_self_loop():
    assert detect_move_cycles([_move("A", "A")]) is True


def test_mixed_cycle_and_non_cycle():
    moves = [_move("A", "B"), _move("B", "A"), _move("C", "D")]
    assert detect_move_cycles(moves) is True
