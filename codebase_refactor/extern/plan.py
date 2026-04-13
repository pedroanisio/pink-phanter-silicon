"""Serialize, deserialize, and validate RefactorPlan objects."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ..models import Lang, MoveOp, RefactorPlan

# ---------------------------------------------------------------------------
# Extension-to-Lang mapping used by validate_plan
# ---------------------------------------------------------------------------

_EXT_TO_LANG: dict[str, Lang] = {
    ".py": Lang.PYTHON,
    ".js": Lang.JAVASCRIPT,
    ".ts": Lang.TYPESCRIPT,
    ".tsx": Lang.TYPESCRIPT,
    ".md": Lang.MARKDOWN,
}


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def serialize_yaml(plan: RefactorPlan) -> str:
    """Dump a *RefactorPlan* to a YAML string."""
    data: dict[str, Any] = {
        "version": plan.version,
        "root": plan.root,
        "delete_empty": plan.delete_empty,
        "created_at": plan.created_at,
        "moves": [
            {
                "source": m.source,
                "destination": m.destination,
                "lang": m.lang.name.lower(),
            }
            for m in plan.moves
        ],
    }
    return yaml.dump(data, default_flow_style=False, sort_keys=False)


# ---------------------------------------------------------------------------
# Deserialization
# ---------------------------------------------------------------------------


def deserialize_yaml(yaml_text: str) -> RefactorPlan:
    """Parse a YAML string and hydrate a *RefactorPlan*.

    Raises ``ValueError`` when the document is malformed (missing keys,
    unknown lang values, etc.).
    """
    try:
        raw = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError("Top-level YAML value must be a mapping")

    required_keys = {"version", "root", "delete_empty", "created_at", "moves"}
    missing = required_keys - raw.keys()
    if missing:
        raise ValueError(f"Missing top-level keys: {', '.join(sorted(missing))}")

    raw_moves = raw["moves"]
    if not isinstance(raw_moves, list):
        raise ValueError("'moves' must be a list")

    moves: list[MoveOp] = []
    for idx, entry in enumerate(raw_moves):
        if not isinstance(entry, dict):
            raise ValueError(f"Move entry {idx} is not a mapping")

        move_keys = {"source", "destination", "lang"}
        move_missing = move_keys - entry.keys()
        if move_missing:
            raise ValueError(f"Move entry {idx} missing keys: {', '.join(sorted(move_missing))}")

        lang_str = str(entry["lang"]).upper()
        try:
            lang = Lang[lang_str]
        except KeyError:
            raise ValueError(f"Move entry {idx} has invalid lang '{entry['lang']}'") from None

        moves.append(
            MoveOp(
                source=entry["source"],
                destination=entry["destination"],
                lang=lang,
            )
        )

    return RefactorPlan(
        version=str(raw["version"]),
        root=str(raw["root"]),
        moves=moves,
        delete_empty=bool(raw["delete_empty"]),
        created_at=str(raw["created_at"]),
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_plan(plan: RefactorPlan, root: str) -> list[str]:
    """Return a list of human-readable error strings (empty on success).

    Checks performed:
    1. Every source path exists under *root*.
    2. No duplicate destinations.
    3. No destination collides with an existing file that is **not** also a
       plan source.
    4. Language annotations match file extensions.
    """
    errors: list[str] = []
    sources: set[str] = {m.source for m in plan.moves}

    # 1. Source existence
    for move in plan.moves:
        full_path = Path(root) / move.source
        if not full_path.is_file():
            errors.append(f"Source file does not exist: {move.source}")

    # 2. Duplicate destinations
    seen_destinations: dict[str, int] = {}
    for move in plan.moves:
        seen_destinations[move.destination] = seen_destinations.get(move.destination, 0) + 1
    for dest, count in seen_destinations.items():
        if count > 1:
            errors.append(f"Duplicate destination ({count} moves): {dest}")

    # 3. Destination collision with existing file not in sources
    for move in plan.moves:
        dest_path = Path(root) / move.destination
        if dest_path.is_file() and move.destination not in sources:
            errors.append(f"Destination collides with existing file: {move.destination}")

    # 4. Language / extension consistency
    for move in plan.moves:
        ext = Path(move.source).suffix
        expected_lang = _EXT_TO_LANG.get(ext)
        if expected_lang is not None and move.lang != expected_lang:
            errors.append(
                f"Lang mismatch for {move.source}: "
                f"annotated {move.lang.name} but extension '{ext}' "
                f"implies {expected_lang.name}"
            )

    return errors


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------


def plan_to_move_map(plan: RefactorPlan) -> dict[str, str]:
    """Return ``{source: destination}`` for every move in the plan."""
    return {m.source: m.destination for m in plan.moves}


def count_plan_moves(plan: RefactorPlan) -> int:
    """Return the number of moves in the plan."""
    return len(plan.moves)


def plan_delete_empty(plan: RefactorPlan) -> bool:
    """Return whether empty directories should be removed after moves."""
    return plan.delete_empty
