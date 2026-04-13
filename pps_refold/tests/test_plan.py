"""Tests for pps_refold.extern.plan module."""

import pytest

from pps_refold.extern.plan import (
    count_plan_moves,
    deserialize_yaml,
    plan_delete_empty,
    plan_to_move_map,
    serialize_yaml,
    validate_plan,
)
from pps_refold.models import Lang, MoveOp, RefactorPlan

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_plan(
    moves=None,
    root="/project",
    version="1",
    delete_empty=True,
    created_at="2026-01-01T00:00:00",
):
    if moves is None:
        moves = [
            MoveOp(source="src/a.py", destination="lib/a.py", lang=Lang.PYTHON),
            MoveOp(source="src/b.js", destination="lib/b.js", lang=Lang.JAVASCRIPT),
        ]
    return RefactorPlan(
        version=version,
        root=root,
        moves=moves,
        delete_empty=delete_empty,
        created_at=created_at,
    )


# ---------------------------------------------------------------------------
# Serialization / Deserialization
# ---------------------------------------------------------------------------


def test_serialize_deserialize_roundtrip():
    plan = _make_plan()
    yaml_text = serialize_yaml(plan)
    restored = deserialize_yaml(yaml_text)

    assert restored.version == plan.version
    assert restored.root == plan.root
    assert restored.delete_empty == plan.delete_empty
    assert restored.created_at == plan.created_at
    assert len(restored.moves) == len(plan.moves)
    for orig, rest in zip(plan.moves, restored.moves):
        assert rest.source == orig.source
        assert rest.destination == orig.destination
        assert rest.lang == orig.lang


def test_serialize_yaml_format():
    plan = _make_plan()
    yaml_text = serialize_yaml(plan)

    assert "version:" in yaml_text
    assert "root:" in yaml_text
    assert "moves:" in yaml_text
    assert "delete_empty:" in yaml_text


def test_deserialize_invalid_yaml():
    with pytest.raises(ValueError, match="Invalid YAML"):
        deserialize_yaml("{{{\x00bad")


def test_deserialize_not_mapping():
    with pytest.raises(ValueError, match="mapping"):
        deserialize_yaml("- list item")


def test_deserialize_missing_keys():
    with pytest.raises(ValueError, match="Missing top-level keys"):
        deserialize_yaml("version: 1\n")


def test_deserialize_invalid_lang():
    yaml_text = (
        "version: 1\n"
        "root: /tmp\n"
        "delete_empty: true\n"
        "created_at: '2026-01-01'\n"
        "moves:\n"
        "  - source: a.py\n"
        "    destination: b.py\n"
        "    lang: FOOBAR\n"
    )
    with pytest.raises(ValueError, match="invalid lang"):
        deserialize_yaml(yaml_text)


def test_deserialize_moves_not_list():
    yaml_text = (
        "version: 1\nroot: /tmp\ndelete_empty: true\ncreated_at: '2026-01-01'\nmoves: string\n"
    )
    with pytest.raises(ValueError, match="must be a list"):
        deserialize_yaml(yaml_text)


def test_deserialize_move_not_mapping():
    yaml_text = (
        "version: 1\nroot: /tmp\ndelete_empty: true\ncreated_at: '2026-01-01'\nmoves:\n  - 42\n"
    )
    with pytest.raises(ValueError, match="not a mapping"):
        deserialize_yaml(yaml_text)


def test_deserialize_move_missing_keys():
    yaml_text = (
        "version: 1\n"
        "root: /tmp\n"
        "delete_empty: true\n"
        "created_at: '2026-01-01'\n"
        "moves:\n"
        "  - source: a.py\n"
    )
    with pytest.raises(ValueError, match="missing keys"):
        deserialize_yaml(yaml_text)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_validate_plan_all_good(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True)
    (src_dir / "a.py").write_text("pass")
    (src_dir / "b.js").write_text("//js")

    plan = _make_plan(
        root=str(tmp_path),
        moves=[
            MoveOp(source="src/a.py", destination="lib/a.py", lang=Lang.PYTHON),
            MoveOp(source="src/b.js", destination="lib/b.js", lang=Lang.JAVASCRIPT),
        ],
    )
    errors = validate_plan(plan, str(tmp_path))
    assert errors == []


def test_validate_plan_source_missing(tmp_path):
    plan = _make_plan(
        root=str(tmp_path),
        moves=[
            MoveOp(source="nonexistent.py", destination="dest.py", lang=Lang.PYTHON),
        ],
    )
    errors = validate_plan(plan, str(tmp_path))
    assert len(errors) == 1
    assert "does not exist" in errors[0]
    assert "nonexistent.py" in errors[0]


def test_validate_plan_duplicate_dest():
    plan = _make_plan(
        moves=[
            MoveOp(source="a.py", destination="same.py", lang=Lang.PYTHON),
            MoveOp(source="b.py", destination="same.py", lang=Lang.PYTHON),
        ],
    )
    errors = validate_plan(plan, "/nonexistent")
    dupl_errors = [e for e in errors if "Duplicate destination" in e]
    assert len(dupl_errors) == 1
    assert "same.py" in dupl_errors[0]


def test_validate_plan_dest_collision(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True)
    (src_dir / "a.py").write_text("pass")
    # existing file at the destination that is NOT a source
    (tmp_path / "dest.py").write_text("old")

    plan = _make_plan(
        root=str(tmp_path),
        moves=[
            MoveOp(source="src/a.py", destination="dest.py", lang=Lang.PYTHON),
        ],
    )
    errors = validate_plan(plan, str(tmp_path))
    collision_errors = [e for e in errors if "collides" in e.lower()]
    assert len(collision_errors) == 1
    assert "dest.py" in collision_errors[0]


def test_validate_plan_dest_collision_swap(tmp_path):
    (tmp_path / "a.py").write_text("content_a")
    (tmp_path / "b.py").write_text("content_b")

    plan = _make_plan(
        root=str(tmp_path),
        moves=[
            MoveOp(source="a.py", destination="b.py", lang=Lang.PYTHON),
            MoveOp(source="b.py", destination="a.py", lang=Lang.PYTHON),
        ],
    )
    errors = validate_plan(plan, str(tmp_path))
    collision_errors = [e for e in errors if "collides" in e.lower()]
    assert collision_errors == []


def test_validate_plan_lang_mismatch():
    plan = _make_plan(
        moves=[
            MoveOp(source="app.py", destination="app2.py", lang=Lang.JAVASCRIPT),
        ],
    )
    errors = validate_plan(plan, "/nonexistent")
    mismatch_errors = [e for e in errors if "mismatch" in e.lower()]
    assert len(mismatch_errors) == 1
    assert "app.py" in mismatch_errors[0]


def test_validate_plan_lang_other_no_check():
    plan = _make_plan(
        moves=[
            MoveOp(source="notes.txt", destination="docs/notes.txt", lang=Lang.OTHER),
        ],
    )
    errors = validate_plan(plan, "/nonexistent")
    mismatch_errors = [e for e in errors if "mismatch" in e.lower()]
    assert mismatch_errors == []


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------


def test_plan_to_move_map():
    plan = _make_plan()
    result = plan_to_move_map(plan)
    assert result == {
        "src/a.py": "lib/a.py",
        "src/b.js": "lib/b.js",
    }


def test_count_plan_moves():
    plan = _make_plan()
    assert count_plan_moves(plan) == 2


def test_plan_delete_empty_true():
    plan = _make_plan(delete_empty=True)
    assert plan_delete_empty(plan) is True


def test_plan_delete_empty_false():
    plan = _make_plan(delete_empty=False)
    assert plan_delete_empty(plan) is False
