from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

# -- enums -----------------------------------------------------------------


class Lang(Enum):
    PYTHON = auto()
    JAVASCRIPT = auto()
    TYPESCRIPT = auto()
    MARKDOWN = auto()
    OTHER = auto()


class Command(Enum):
    SCAN = auto()
    EXECUTE = auto()


class Phase(Enum):
    INIT = auto()
    SCANNING = auto()
    BUILDING_GRAPH = auto()
    DETECTING_SMELLS = auto()
    PROPOSING = auto()
    VALIDATING = auto()
    BACKING_UP = auto()
    CREATING_DIRS = auto()
    MOVING = auto()
    REWRITING_IMPORTS = auto()
    PATCHING_DOCS = auto()
    CLEANING_DIRS = auto()
    REPORTING = auto()
    DONE = auto()
    FAILED = auto()


# -- phase sets for isolation invariants -----------------------------------

SCAN_ONLY_PHASES = frozenset(
    {
        Phase.SCANNING,
        Phase.BUILDING_GRAPH,
        Phase.DETECTING_SMELLS,
        Phase.PROPOSING,
    }
)

EXECUTE_ONLY_PHASES = frozenset(
    {
        Phase.VALIDATING,
        Phase.BACKING_UP,
        Phase.CREATING_DIRS,
        Phase.MOVING,
        Phase.REWRITING_IMPORTS,
        Phase.PATCHING_DOCS,
        Phase.CLEANING_DIRS,
        Phase.REPORTING,
    }
)

MUTATION_PHASES = frozenset(
    {
        Phase.MOVING,
        Phase.REWRITING_IMPORTS,
        Phase.PATCHING_DOCS,
        Phase.CLEANING_DIRS,
    }
)


# -- records ---------------------------------------------------------------


@dataclass(frozen=True)
class FileEntry:
    path: str
    lang: Lang
    size_bytes: int
    hash: str


@dataclass(frozen=True)
class MoveOp:
    source: str
    destination: str
    lang: Lang


@dataclass
class RefactorPlan:
    version: str
    root: str
    moves: list[MoveOp]
    delete_empty: bool
    created_at: str


# -- engine IO -------------------------------------------------------------


@dataclass(frozen=True)
class EngineInput:
    command: Command
    root_dir: str
    plan_yaml: str | None = None
    dry_run: bool = False
    extra_ignore: list[str] = field(default_factory=list)
    backup_dir_name: str = ".refactor-backup"


@dataclass
class EngineState:
    phase: Phase = Phase.INIT

    # scan
    file_inventory: dict[str, FileEntry] = field(default_factory=dict)
    reverse_graph: dict[str, list[str]] = field(default_factory=dict)
    smells: list[str] = field(default_factory=list)

    # plan
    plan: RefactorPlan | None = None
    move_map: dict[str, str] = field(default_factory=dict)
    has_cycles: bool = False
    delete_empty: bool = False

    # execute counters
    validation_errors: list[str] = field(default_factory=list)
    backup_complete: bool = False
    dirs_created: int = 0
    files_moved: int = 0
    imports_patched: int = 0
    docs_patched: int = 0
    dirs_cleaned: int = 0

    # shared
    log: list[str] = field(default_factory=list)
    error_message: str | None = None


@dataclass
class EngineOutput:
    plan_yaml: str | None = None
    report_json: str | None = None
    log: list[str] = field(default_factory=list)
    error_message: str | None = None
