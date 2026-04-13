"""Tests for codebase_refactor.models."""

from __future__ import annotations

import pytest

from codebase_refactor.models import (
    Lang,
    Command,
    Phase,
    FileEntry,
    MoveOp,
    RefactorPlan,
    EngineInput,
    EngineState,
    EngineOutput,
    SCAN_ONLY_PHASES,
    EXECUTE_ONLY_PHASES,
    MUTATION_PHASES,
)


# -- enum membership ----------------------------------------------------------


def test_lang_enum():
    expected = {"PYTHON", "JAVASCRIPT", "TYPESCRIPT", "MARKDOWN", "OTHER"}
    actual = {member.name for member in Lang}
    assert actual == expected


def test_command_enum():
    assert Command.SCAN is not None
    assert Command.EXECUTE is not None
    assert len(Command) == 2


def test_phase_enum():
    expected = {
        "INIT",
        "SCANNING",
        "BUILDING_GRAPH",
        "DETECTING_SMELLS",
        "PROPOSING",
        "VALIDATING",
        "BACKING_UP",
        "CREATING_DIRS",
        "MOVING",
        "REWRITING_IMPORTS",
        "PATCHING_DOCS",
        "CLEANING_DIRS",
        "REPORTING",
        "DONE",
        "FAILED",
    }
    actual = {member.name for member in Phase}
    assert actual == expected
    assert len(Phase) == 15


# -- phase-set invariants -----------------------------------------------------


def test_phase_sets_are_disjoint():
    overlap = SCAN_ONLY_PHASES & EXECUTE_ONLY_PHASES
    assert overlap == frozenset(), f"Unexpected overlap: {overlap}"


def test_mutation_phases_subset_of_execute():
    assert MUTATION_PHASES <= EXECUTE_ONLY_PHASES, (
        f"MUTATION_PHASES has members not in EXECUTE_ONLY_PHASES: "
        f"{MUTATION_PHASES - EXECUTE_ONLY_PHASES}"
    )


# -- frozen dataclasses -------------------------------------------------------


def test_file_entry_frozen():
    entry = FileEntry(path="a.py", lang=Lang.PYTHON, size_bytes=42, hash="abc123")
    assert entry.path == "a.py"
    assert entry.lang is Lang.PYTHON
    assert entry.size_bytes == 42
    assert entry.hash == "abc123"

    with pytest.raises(AttributeError):
        entry.path = "b.py"  # type: ignore[misc]


def test_move_op_frozen():
    op = MoveOp(source="old.py", destination="new.py", lang=Lang.PYTHON)
    assert op.source == "old.py"
    assert op.destination == "new.py"
    assert op.lang is Lang.PYTHON

    with pytest.raises(AttributeError):
        op.source = "other.py"  # type: ignore[misc]


# -- mutable dataclasses with defaults ----------------------------------------


def test_engine_state_defaults():
    state = EngineState()

    assert state.phase is Phase.INIT
    assert state.file_inventory == {}
    assert state.reverse_graph == {}
    assert state.smells == []
    assert state.plan is None
    assert state.move_map == {}
    assert state.has_cycles is False
    assert state.delete_empty is False
    assert state.validation_errors == []
    assert state.backup_complete is False
    assert state.dirs_created == 0
    assert state.files_moved == 0
    assert state.imports_patched == 0
    assert state.docs_patched == 0
    assert state.dirs_cleaned == 0
    assert state.log == []
    assert state.error_message is None


def test_engine_input_defaults():
    inp = EngineInput(command=Command.SCAN, root_dir="/tmp/test")

    assert inp.command is Command.SCAN
    assert inp.root_dir == "/tmp/test"
    assert inp.plan_yaml is None
    assert inp.dry_run is False
    assert inp.extra_ignore == []
    assert inp.backup_dir_name == ".refactor-backup"


def test_engine_output_defaults():
    out = EngineOutput()

    assert out.plan_yaml is None
    assert out.report_json is None
    assert out.log == []
    assert out.error_message is None


def test_refactor_plan():
    moves = [
        MoveOp(source="a.py", destination="pkg/a.py", lang=Lang.PYTHON),
        MoveOp(source="b.js", destination="pkg/b.js", lang=Lang.JAVASCRIPT),
    ]
    plan = RefactorPlan(
        version="1.0",
        root="/project",
        moves=moves,
        delete_empty=True,
        created_at="2026-04-12T00:00:00+00:00",
    )

    assert plan.version == "1.0"
    assert plan.root == "/project"
    assert len(plan.moves) == 2
    assert plan.moves[0].source == "a.py"
    assert plan.moves[1].lang is Lang.JAVASCRIPT
    assert plan.delete_empty is True
    assert plan.created_at == "2026-04-12T00:00:00+00:00"
