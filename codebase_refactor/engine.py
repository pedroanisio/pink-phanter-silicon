from __future__ import annotations

import os
import uuid
from typing import Callable, Optional

from .models import (
    Command, EngineInput, EngineOutput, EngineState, Lang, Phase,
    RefactorPlan, MUTATION_PHASES, SCAN_ONLY_PHASES, EXECUTE_ONLY_PHASES,
)
from .extern.filesystem import (
    copy_file, dir_exists, dir_is_empty, mkdir, move_file,
    parent_dirs, read_file, rmdir, walk_tree, write_file,
)
from .extern.imports import extract_imports, resolve_import, rewrite_imports
from .extern.doc_patch import patch_doc_paths
from .extern.plan import (
    count_plan_moves, deserialize_yaml, plan_delete_empty,
    plan_to_move_map, serialize_yaml, validate_plan,
)
from .extern.cycles import detect_move_cycles
from .extern.preflight import preflight_moves, preflight_rewrites
from .extern.graph import build_reverse_graph, detect_smells
from .extern.reporting import serialize_report, timestamp_now


RuleTuple = tuple[str, Callable[[], bool], Callable[[], None]]


class Engine:
    def __init__(self, inp: EngineInput, *, check_invariants: bool = False):
        self.inp = inp
        self.state = EngineState()
        self.output = EngineOutput()
        self.check_invariants = check_invariants

    # -- public interface --------------------------------------------------

    def run(self) -> EngineOutput:
        while self.state.phase not in (Phase.DONE, Phase.FAILED):
            self.step()
        self._finalize_output()
        return self.output

    def step(self) -> str:
        for rule_name, guard, action in self._rules():
            if guard():
                action()
                if self.check_invariants:
                    self._check_invariants()
                return rule_name
        raise RuntimeError(f"No rule matched in phase {self.state.phase}")

    # -- rule table --------------------------------------------------------

    def _rules(self) -> list[RuleTuple]:
        return [
            # -- priority 1: entry rules --
            ("start_scan", self._guard_start_scan, self._action_start_scan),
            ("scan_bad_root", self._guard_scan_bad_root, self._action_scan_bad_root),
            ("execute_no_plan", self._guard_execute_no_plan, self._action_execute_no_plan),
            ("execute_bad_root", self._guard_execute_bad_root, self._action_execute_bad_root),
            ("start_execute", self._guard_start_execute, self._action_start_execute),
            # -- priority 10-13: scan pipeline --
            ("scan_walk", self._guard_scanning, self._action_scan_walk),
            ("build_graph", self._guard_building_graph, self._action_build_graph),
            ("detect_smells", self._guard_detecting_smells, self._action_detect_smells),
            ("propose_plan", self._guard_proposing, self._action_propose_plan),
            # -- priority 20: validation --
            ("validate_pass", self._guard_validate_pass, self._action_validate_pass),
            ("validate_fail", self._guard_validate_fail, self._action_validate_fail),
            # -- priority 30: backup --
            ("backup_live", self._guard_backup_live, self._action_backup_live),
            ("backup_dry_run", self._guard_backup_dry_run, self._action_backup_dry_run),
            # -- priority 40: create dirs --
            ("create_dirs", self._guard_creating_dirs, self._action_create_dirs),
            # -- priority 49: move preflight --
            ("move_preflight_fail", self._guard_move_preflight_fail, self._action_move_preflight_fail),
            # -- priority 50: move files --
            ("move_files_direct", self._guard_move_direct, self._action_move_direct),
            ("move_files_staged", self._guard_move_staged, self._action_move_staged),
            ("move_files_dry", self._guard_move_dry, self._action_move_dry),
            # -- priority 59: rewrite preflight --
            ("rewrite_preflight_fail", self._guard_rewrite_preflight_fail, self._action_rewrite_preflight_fail),
            # -- priority 60: rewrite imports --
            ("rewrite_imports", self._guard_rewriting_imports, self._action_rewrite_imports),
            # -- priority 70: patch docs --
            ("patch_docs", self._guard_patch_docs, self._action_patch_docs),
            ("patch_docs_skip_clean", self._guard_patch_docs_skip_clean, self._action_patch_docs_skip_clean),
            # -- priority 80: clean dirs --
            ("clean_dirs", self._guard_cleaning_dirs, self._action_clean_dirs),
            # -- priority 90: report --
            ("write_report", self._guard_reporting, self._action_write_report),
        ]

    # -- guards: entry (priority 1) ----------------------------------------

    def _guard_start_scan(self) -> bool:
        return (
            self.state.phase == Phase.INIT
            and self.inp.command == Command.SCAN
            and dir_exists(self.inp.root_dir)
        )

    def _guard_scan_bad_root(self) -> bool:
        return (
            self.state.phase == Phase.INIT
            and self.inp.command == Command.SCAN
            and not dir_exists(self.inp.root_dir)
        )

    def _guard_execute_no_plan(self) -> bool:
        return (
            self.state.phase == Phase.INIT
            and self.inp.command == Command.EXECUTE
            and self.inp.plan_yaml is None
        )

    def _guard_execute_bad_root(self) -> bool:
        return (
            self.state.phase == Phase.INIT
            and self.inp.command == Command.EXECUTE
            and self.inp.plan_yaml is not None
            and not dir_exists(self.inp.root_dir)
        )

    def _guard_start_execute(self) -> bool:
        return (
            self.state.phase == Phase.INIT
            and self.inp.command == Command.EXECUTE
            and self.inp.plan_yaml is not None
            and dir_exists(self.inp.root_dir)
        )

    # -- guards: scan pipeline (10-13) ------------------------------------

    def _guard_scanning(self) -> bool:
        return self.state.phase == Phase.SCANNING

    def _guard_building_graph(self) -> bool:
        return self.state.phase == Phase.BUILDING_GRAPH

    def _guard_detecting_smells(self) -> bool:
        return self.state.phase == Phase.DETECTING_SMELLS

    def _guard_proposing(self) -> bool:
        return self.state.phase == Phase.PROPOSING

    # -- guards: execute pipeline ------------------------------------------

    def _guard_validate_pass(self) -> bool:
        return (
            self.state.phase == Phase.VALIDATING
            and len(self.state.validation_errors) == 0
        )

    def _guard_validate_fail(self) -> bool:
        return (
            self.state.phase == Phase.VALIDATING
            and len(self.state.validation_errors) > 0
        )

    def _guard_backup_live(self) -> bool:
        return (
            self.state.phase == Phase.BACKING_UP
            and not self.inp.dry_run
        )

    def _guard_backup_dry_run(self) -> bool:
        return (
            self.state.phase == Phase.BACKING_UP
            and self.inp.dry_run
        )

    def _guard_creating_dirs(self) -> bool:
        return self.state.phase == Phase.CREATING_DIRS

    def _guard_move_preflight_fail(self) -> bool:
        return (
            self.state.phase == Phase.MOVING
            and not self.inp.dry_run
            and not preflight_moves(self.state.move_map, self.inp.root_dir)
        )

    def _guard_move_direct(self) -> bool:
        return (
            self.state.phase == Phase.MOVING
            and not self.inp.dry_run
            and not self.state.has_cycles
        )

    def _guard_move_staged(self) -> bool:
        return (
            self.state.phase == Phase.MOVING
            and not self.inp.dry_run
            and self.state.has_cycles
        )

    def _guard_move_dry(self) -> bool:
        return (
            self.state.phase == Phase.MOVING
            and self.inp.dry_run
        )

    def _guard_rewrite_preflight_fail(self) -> bool:
        return (
            self.state.phase == Phase.REWRITING_IMPORTS
            and not self.inp.dry_run
            and not preflight_rewrites(self.state.move_map, self.inp.root_dir)
        )

    def _guard_rewriting_imports(self) -> bool:
        return self.state.phase == Phase.REWRITING_IMPORTS

    def _guard_patch_docs(self) -> bool:
        return (
            self.state.phase == Phase.PATCHING_DOCS
            and self.state.delete_empty
        )

    def _guard_patch_docs_skip_clean(self) -> bool:
        return (
            self.state.phase == Phase.PATCHING_DOCS
            and not self.state.delete_empty
        )

    def _guard_cleaning_dirs(self) -> bool:
        return self.state.phase == Phase.CLEANING_DIRS

    def _guard_reporting(self) -> bool:
        return self.state.phase == Phase.REPORTING

    # -- actions: entry ----------------------------------------------------

    def _action_start_scan(self) -> None:
        self.state.phase = Phase.SCANNING
        self.state.log.append(f"Scanning {self.inp.root_dir}")

    def _action_scan_bad_root(self) -> None:
        self.state.phase = Phase.FAILED
        self.state.error_message = (
            f"Project root directory does not exist: {self.inp.root_dir}"
        )

    def _action_execute_no_plan(self) -> None:
        self.state.phase = Phase.FAILED
        self.state.error_message = "No plan file provided for execute command"

    def _action_execute_bad_root(self) -> None:
        self.state.phase = Phase.FAILED
        self.state.error_message = (
            f"Project root directory does not exist: {self.inp.root_dir}"
        )

    def _action_start_execute(self) -> None:
        assert self.inp.plan_yaml is not None
        plan = deserialize_yaml(self.inp.plan_yaml)
        errors = validate_plan(plan, self.inp.root_dir)
        self.state.plan = plan
        self.state.validation_errors = errors
        self.state.phase = Phase.VALIDATING

    # -- actions: scan pipeline --------------------------------------------

    def _action_scan_walk(self) -> None:
        ignore = set(self.inp.extra_ignore)
        self.state.file_inventory = walk_tree(self.inp.root_dir, ignore)
        self.state.phase = Phase.BUILDING_GRAPH
        self.state.log.append(
            f"Found {len(self.state.file_inventory)} files"
        )

    def _action_build_graph(self) -> None:
        file_index = {p: p for p in self.state.file_inventory}
        self.state.reverse_graph = build_reverse_graph(
            self.state.file_inventory,
            extract_fn=extract_imports,
            resolve_fn=resolve_import,
            read_fn=lambda p: read_file(os.path.join(self.inp.root_dir, p)),
            file_index=file_index,
        )
        self.state.phase = Phase.DETECTING_SMELLS
        self.state.log.append("Dependency graph built")

    def _action_detect_smells(self) -> None:
        self.state.smells = detect_smells(
            self.state.reverse_graph,
            self.state.file_inventory,
            self.inp.root_dir,
        )
        self.state.phase = Phase.PROPOSING
        self.state.log.append(f"Detected {len(self.state.smells)} smells")

    def _action_propose_plan(self) -> None:
        from .extern.plan import serialize_yaml
        moves = self._generate_moves_from_smells()
        plan = RefactorPlan(
            version="1.0",
            root=self.inp.root_dir,
            moves=moves,
            delete_empty=True,
            created_at=timestamp_now(),
        )
        self.state.plan = plan
        self.output.plan_yaml = serialize_yaml(plan)
        self.state.phase = Phase.DONE
        self.state.log.append("Proposal written")

    def _generate_moves_from_smells(self):
        """Generate move suggestions from detected smells.

        Conservative v1: only suggest moves for deep-nested files.
        """
        from .models import MoveOp
        from .extern.filesystem import detect_lang
        moves = []
        for smell in self.state.smells:
            if smell.startswith("Deep nesting:"):
                # Format: "Deep nesting: path (N levels deep)"
                raw = smell.split(":", 1)[1].strip()
                path = raw.split(" (")[0]
                parts = path.split("/")
                if len(parts) > 3:
                    new_path = "/".join(parts[:2] + parts[-1:])
                    lang = detect_lang(path)
                    moves.append(MoveOp(source=path, destination=new_path, lang=lang))
        return moves

    # -- actions: execute pipeline -----------------------------------------

    def _action_validate_pass(self) -> None:
        assert self.state.plan is not None
        self.state.move_map = plan_to_move_map(self.state.plan)
        self.state.has_cycles = detect_move_cycles(self.state.plan.moves)
        self.state.delete_empty = plan_delete_empty(self.state.plan)
        self.state.phase = Phase.BACKING_UP
        self.state.log.append("Plan validated")

    def _action_validate_fail(self) -> None:
        self.state.phase = Phase.FAILED
        self.state.error_message = "Plan validation failed"
        self.state.log.append(
            f"Validation failed: {self.state.validation_errors}"
        )

    def _action_backup_live(self) -> None:
        root = self.inp.root_dir
        backup_dir = os.path.join(root, self.inp.backup_dir_name)
        files_to_backup: set[str] = set(self.state.move_map.keys())
        for fpath in self.state.file_inventory:
            try:
                source = read_file(os.path.join(root, fpath))
                for old_path in self.state.move_map:
                    if old_path in source:
                        files_to_backup.add(fpath)
                        break
            except Exception:
                continue
        for fpath in files_to_backup:
            src = os.path.join(root, fpath)
            dst = os.path.join(backup_dir, fpath)
            mkdir(os.path.dirname(dst), dry_run=False)
            copy_file(src, dst, dry_run=False)
        self.state.backup_complete = True
        self.state.phase = Phase.CREATING_DIRS
        self.state.log.append(
            f"Backup complete: {len(files_to_backup)} files"
        )

    def _action_backup_dry_run(self) -> None:
        self.state.backup_complete = False
        self.state.phase = Phase.CREATING_DIRS
        self.state.log.append("Dry-run: backup skipped")

    def _action_create_dirs(self) -> None:
        root = self.inp.root_dir
        dirs_needed: set[str] = set()
        for dst in self.state.move_map.values():
            parent = os.path.dirname(dst)
            if parent:
                dirs_needed.add(parent)
        count = 0
        for d in sorted(dirs_needed):
            full_path = os.path.join(root, d)
            if mkdir(full_path, dry_run=self.inp.dry_run):
                count += 1
        self.state.dirs_created = count
        self.state.phase = Phase.MOVING
        self.state.log.append(f"Created {count} directories")

    def _action_move_preflight_fail(self) -> None:
        self.state.phase = Phase.FAILED
        self.state.error_message = (
            "Move pre-flight failed: source missing or destination conflict"
        )

    def _action_move_direct(self) -> None:
        root = self.inp.root_dir
        count = 0
        for src, dst in self.state.move_map.items():
            src_path = os.path.join(root, src)
            dst_path = os.path.join(root, dst)
            if move_file(src_path, dst_path, dry_run=False):
                count += 1
        self.state.files_moved = count
        self.state.phase = Phase.REWRITING_IMPORTS
        self.state.log.append(f"Moved {count} files (direct)")

    def _action_move_staged(self) -> None:
        root = self.inp.root_dir
        staging = os.path.join(root, f".refactor-staging-{uuid.uuid4().hex[:8]}")
        mkdir(staging, dry_run=False)
        for src in self.state.move_map:
            src_path = os.path.join(root, src)
            stage_path = os.path.join(staging, src)
            mkdir(os.path.dirname(stage_path), dry_run=False)
            move_file(src_path, stage_path, dry_run=False)
        count = 0
        for src, dst in self.state.move_map.items():
            stage_path = os.path.join(staging, src)
            dst_path = os.path.join(root, dst)
            if move_file(stage_path, dst_path, dry_run=False):
                count += 1
        # clean staging
        try:
            import shutil
            shutil.rmtree(staging, ignore_errors=True)
        except Exception:
            pass
        self.state.files_moved = count
        self.state.phase = Phase.REWRITING_IMPORTS
        self.state.log.append(f"Moved {count} files (staged)")

    def _action_move_dry(self) -> None:
        self.state.files_moved = len(self.state.move_map)
        self.state.phase = Phase.REWRITING_IMPORTS
        self.state.log.append(
            f"[DRY RUN] Simulating {len(self.state.move_map)} file moves"
        )

    def _action_rewrite_preflight_fail(self) -> None:
        self.state.phase = Phase.FAILED
        self.state.error_message = (
            "Import rewrite pre-flight failed: files inaccessible"
        )

    def _action_rewrite_imports(self) -> None:
        root = self.inp.root_dir
        renames = self.state.move_map
        count = 0
        for fpath, entry in self.state.file_inventory.items():
            if entry.lang in (Lang.PYTHON, Lang.JAVASCRIPT, Lang.TYPESCRIPT):
                full_path = os.path.join(root, fpath)
                try:
                    source = read_file(full_path)
                    rewritten = rewrite_imports(
                        source, renames, entry.lang, fpath,
                    )
                    if rewritten != source:
                        write_file(full_path, rewritten, dry_run=self.inp.dry_run)
                        count += 1
                except Exception:
                    continue
        self.state.imports_patched = count
        self.state.phase = Phase.PATCHING_DOCS
        self.state.log.append(f"Rewrote imports in {count} files")

    def _action_patch_docs(self) -> None:
        self._do_patch_docs()
        self.state.phase = Phase.CLEANING_DIRS

    def _action_patch_docs_skip_clean(self) -> None:
        self._do_patch_docs()
        self.state.phase = Phase.REPORTING

    def _do_patch_docs(self) -> None:
        root = self.inp.root_dir
        renames = self.state.move_map
        count = 0
        for fpath, entry in self.state.file_inventory.items():
            if entry.lang == Lang.MARKDOWN:
                full_path = os.path.join(root, fpath)
                try:
                    content = read_file(full_path)
                    patched = patch_doc_paths(content, renames)
                    if patched != content:
                        write_file(full_path, patched, dry_run=self.inp.dry_run)
                        count += 1
                except Exception:
                    continue
        self.state.docs_patched = count
        self.state.log.append(f"Patched {count} doc files")

    def _action_clean_dirs(self) -> None:
        root = self.inp.root_dir
        source_parents: set[str] = set()
        for src in self.state.move_map:
            for d in parent_dirs(src, root=""):
                source_parents.add(d)
        count = 0
        for d in sorted(source_parents, key=len, reverse=True):
            full_path = os.path.join(root, d)
            try:
                if dir_is_empty(full_path):
                    if rmdir(full_path, dry_run=self.inp.dry_run):
                        count += 1
            except Exception:
                continue
        self.state.dirs_cleaned = count
        self.state.phase = Phase.REPORTING
        self.state.log.append(f"Cleaned {count} empty directories")

    def _action_write_report(self) -> None:
        self.output.report_json = serialize_report(
            log=self.state.log,
            files_moved=self.state.files_moved,
            imports_patched=self.state.imports_patched,
            docs_patched=self.state.docs_patched,
            dirs_cleaned=self.state.dirs_cleaned,
            dirs_created=self.state.dirs_created,
            backup_complete=self.state.backup_complete,
            dry_run=self.inp.dry_run,
        )
        self.output.log = list(self.state.log)
        self.state.phase = Phase.DONE
        self.state.log.append("Execution complete")

    # -- finalize ----------------------------------------------------------

    def _finalize_output(self) -> None:
        self.output.log = list(self.state.log)
        if self.state.phase == Phase.FAILED:
            self.output.error_message = self.state.error_message

    # -- invariants --------------------------------------------------------

    def _check_invariants(self) -> None:
        s = self.state
        inp = self.inp

        # 1. backup_before_mutation
        if s.phase in MUTATION_PHASES:
            assert s.backup_complete or inp.dry_run, (
                f"Invariant backup_before_mutation violated in {s.phase}"
            )

        # 2. failed_is_terminal
        if s.phase == Phase.FAILED:
            assert s.error_message is not None, (
                "Invariant failed_is_terminal violated: no error_message"
            )

        # 3. moves_bounded
        if s.plan is not None:
            assert s.files_moved <= count_plan_moves(s.plan), (
                f"Invariant moves_bounded violated: "
                f"{s.files_moved} > {count_plan_moves(s.plan)}"
            )

        # 4. scan_isolation
        if inp.command == Command.SCAN:
            assert s.phase not in EXECUTE_ONLY_PHASES, (
                f"Invariant scan_isolation violated: {s.phase}"
            )

        # 5. execute_isolation
        if inp.command == Command.EXECUTE:
            assert s.phase not in SCAN_ONLY_PHASES, (
                f"Invariant execute_isolation violated: {s.phase}"
            )

        # 6. done_has_scan_output
        if s.phase == Phase.DONE and inp.command == Command.SCAN:
            assert self.output.plan_yaml is not None, (
                "Invariant done_has_scan_output violated"
            )

        # 7. done_has_execute_output
        if s.phase == Phase.DONE and inp.command == Command.EXECUTE:
            assert self.output.report_json is not None, (
                "Invariant done_has_execute_output violated"
            )
