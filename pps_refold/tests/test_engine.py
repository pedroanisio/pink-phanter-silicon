"""Tests for pps_refold.engine — state machine, scan & execute pipelines."""

import json
import os

import pytest
import yaml

from pps_refold.engine import Engine
from pps_refold.models import (
    EXECUTE_ONLY_PHASES,
    SCAN_ONLY_PHASES,
    Command,
    EngineInput,
    Phase,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_project(tmp_path):
    """Create a small project: src/a.py imports src/b.py"""
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("from src.b import hello\n")
    (src / "b.py").write_text("def hello(): pass\n")
    return str(tmp_path)


def _make_plan_yaml(root):
    return yaml.dump(
        {
            "version": "1.0",
            "root": root,
            "delete_empty": True,
            "created_at": "2024-01-01T00:00:00",
            "moves": [{"source": "src/b.py", "destination": "lib/b.py", "lang": "python"}],
        }
    )


def _make_plan_yaml_no_delete(root):
    return yaml.dump(
        {
            "version": "1.0",
            "root": root,
            "delete_empty": False,
            "created_at": "2024-01-01T00:00:00",
            "moves": [{"source": "src/b.py", "destination": "lib/b.py", "lang": "python"}],
        }
    )


def _make_swap_plan_yaml(root):
    return yaml.dump(
        {
            "version": "1.0",
            "root": root,
            "delete_empty": True,
            "created_at": "2024-01-01T00:00:00",
            "moves": [
                {"source": "src/a.py", "destination": "src/b.py", "lang": "python"},
                {"source": "src/b.py", "destination": "src/a.py", "lang": "python"},
            ],
        }
    )


# ---------------------------------------------------------------------------
# Scan pipeline tests
# ---------------------------------------------------------------------------


class TestScanPipeline:
    def test_scan_bad_root(self):
        """SCAN with nonexistent root_dir -> FAILED, error mentions 'does not exist'."""
        inp = EngineInput(
            command=Command.SCAN,
            root_dir="/nonexistent/path/that/does/not/exist",
        )
        engine = Engine(inp)
        output = engine.run()

        assert engine.state.phase == Phase.FAILED
        assert output.error_message is not None
        assert "does not exist" in output.error_message

    def test_scan_full_pipeline(self, tmp_path):
        """Run SCAN on a small project and verify plan_yaml is produced."""
        root = _make_project(tmp_path)

        inp = EngineInput(
            command=Command.SCAN,
            root_dir=root,
        )
        engine = Engine(inp)
        output = engine.run()

        assert engine.state.phase == Phase.DONE
        assert output.plan_yaml is not None
        assert output.error_message is None


# ---------------------------------------------------------------------------
# Execute pipeline tests
# ---------------------------------------------------------------------------


class TestExecutePipeline:
    def test_execute_no_plan(self):
        """EXECUTE with plan_yaml=None -> FAILED, 'No plan file provided'."""
        inp = EngineInput(
            command=Command.EXECUTE,
            root_dir="/tmp",
            plan_yaml=None,
        )
        engine = Engine(inp)
        output = engine.run()

        assert engine.state.phase == Phase.FAILED
        assert output.error_message is not None
        assert "No plan file provided" in output.error_message

    def test_execute_bad_root(self):
        """EXECUTE with plan_yaml set but nonexistent root -> FAILED, 'does not exist'."""
        inp = EngineInput(
            command=Command.EXECUTE,
            root_dir="/nonexistent/path/that/does/not/exist",
            plan_yaml="version: '1.0'\nroot: /fake\ndelete_empty: true\n"
            "created_at: '2024-01-01'\nmoves: []\n",
        )
        engine = Engine(inp)
        output = engine.run()

        assert engine.state.phase == Phase.FAILED
        assert output.error_message is not None
        assert "does not exist" in output.error_message

    def test_execute_validation_fail(self, tmp_path):
        """Plan references source file that does not exist -> FAILED, 'Plan validation failed'."""
        root = str(tmp_path)
        # Plan refers to src/b.py which does not exist on disk
        plan_yaml = _make_plan_yaml(root)

        inp = EngineInput(
            command=Command.EXECUTE,
            root_dir=root,
            plan_yaml=plan_yaml,
        )
        engine = Engine(inp)
        output = engine.run()

        assert engine.state.phase == Phase.FAILED
        assert output.error_message is not None
        assert "Plan validation failed" in output.error_message

    def test_execute_dry_run(self, tmp_path):
        """Dry-run execute: reaches DONE, report_json produced, no files actually moved."""
        root = _make_project(tmp_path)
        plan_yaml = _make_plan_yaml(root)

        inp = EngineInput(
            command=Command.EXECUTE,
            root_dir=root,
            plan_yaml=plan_yaml,
            dry_run=True,
        )
        engine = Engine(inp)
        output = engine.run()

        assert engine.state.phase == Phase.DONE
        assert output.report_json is not None
        assert output.error_message is None

        # Original file should still be in place (dry run)
        assert os.path.isfile(os.path.join(root, "src", "b.py"))
        # Destination should NOT have been created
        assert not os.path.isfile(os.path.join(root, "lib", "b.py"))

        # Parse report and verify dry_run flag
        report = json.loads(output.report_json)
        assert report["dry_run"] is True

    def test_execute_live(self, tmp_path):
        """Live execute: reaches DONE, files actually moved on disk."""
        root = _make_project(tmp_path)
        plan_yaml = _make_plan_yaml(root)

        inp = EngineInput(
            command=Command.EXECUTE,
            root_dir=root,
            plan_yaml=plan_yaml,
            dry_run=False,
        )
        engine = Engine(inp)
        output = engine.run()

        assert engine.state.phase == Phase.DONE
        assert output.report_json is not None
        assert output.error_message is None

        # src/b.py should be gone
        assert not os.path.isfile(os.path.join(root, "src", "b.py"))
        # lib/b.py should exist
        assert os.path.isfile(os.path.join(root, "lib", "b.py"))

        report = json.loads(output.report_json)
        assert report["dry_run"] is False
        assert report["files_moved"] >= 1


# ---------------------------------------------------------------------------
# Invariant tests
# ---------------------------------------------------------------------------


class TestInvariants:
    def test_invariant_backup_before_mutation(self, tmp_path):
        """Run with check_invariants=True, verify no assertion error on normal execution."""
        root = _make_project(tmp_path)
        plan_yaml = _make_plan_yaml(root)

        inp = EngineInput(
            command=Command.EXECUTE,
            root_dir=root,
            plan_yaml=plan_yaml,
            dry_run=True,
        )
        engine = Engine(inp, check_invariants=True)
        # Should complete without AssertionError
        output = engine.run()
        assert engine.state.phase == Phase.DONE

    def test_invariant_failed_is_terminal(self):
        """All failure paths set error_message. Verify scan_bad_root, execute_no_plan, execute_bad_root."""
        # scan_bad_root
        inp1 = EngineInput(command=Command.SCAN, root_dir="/nonexistent/xyz")
        out1 = Engine(inp1).run()
        assert out1.error_message is not None

        # execute_no_plan
        inp2 = EngineInput(command=Command.EXECUTE, root_dir="/tmp", plan_yaml=None)
        out2 = Engine(inp2).run()
        assert out2.error_message is not None

        # execute_bad_root
        inp3 = EngineInput(
            command=Command.EXECUTE,
            root_dir="/nonexistent/xyz",
            plan_yaml="version: '1.0'\nroot: /fake\ndelete_empty: true\n"
            "created_at: '2024-01-01'\nmoves: []\n",
        )
        out3 = Engine(inp3).run()
        assert out3.error_message is not None

    def test_invariant_scan_isolation(self, tmp_path):
        """Run SCAN, collect all phases visited. None should be in EXECUTE_ONLY_PHASES."""
        root = _make_project(tmp_path)
        inp = EngineInput(command=Command.SCAN, root_dir=root)
        engine = Engine(inp)

        visited_phases = []
        while engine.state.phase not in (Phase.DONE, Phase.FAILED):
            visited_phases.append(engine.state.phase)
            engine.step()
        visited_phases.append(engine.state.phase)

        for phase in visited_phases:
            assert phase not in EXECUTE_ONLY_PHASES, f"Scan visited execute-only phase: {phase}"

    def test_invariant_execute_isolation(self, tmp_path):
        """Run EXECUTE with valid plan, collect phases. None should be in SCAN_ONLY_PHASES."""
        root = _make_project(tmp_path)
        plan_yaml = _make_plan_yaml(root)

        inp = EngineInput(
            command=Command.EXECUTE,
            root_dir=root,
            plan_yaml=plan_yaml,
            dry_run=True,
        )
        engine = Engine(inp)

        visited_phases = []
        while engine.state.phase not in (Phase.DONE, Phase.FAILED):
            visited_phases.append(engine.state.phase)
            engine.step()
        visited_phases.append(engine.state.phase)

        for phase in visited_phases:
            assert phase not in SCAN_ONLY_PHASES, f"Execute visited scan-only phase: {phase}"

    def test_invariant_done_has_scan_output(self, tmp_path):
        """Run SCAN to DONE, assert plan_yaml not None."""
        root = _make_project(tmp_path)
        inp = EngineInput(command=Command.SCAN, root_dir=root)
        engine = Engine(inp)
        output = engine.run()

        assert engine.state.phase == Phase.DONE
        assert output.plan_yaml is not None

    def test_invariant_done_has_execute_output(self, tmp_path):
        """Run EXECUTE to DONE, assert report_json not None."""
        root = _make_project(tmp_path)
        plan_yaml = _make_plan_yaml(root)

        inp = EngineInput(
            command=Command.EXECUTE,
            root_dir=root,
            plan_yaml=plan_yaml,
            dry_run=True,
        )
        engine = Engine(inp)
        output = engine.run()

        assert engine.state.phase == Phase.DONE
        assert output.report_json is not None

    def test_step_no_rule_matches(self):
        """Manually set state.phase to an unusual value; step() -> RuntimeError."""
        inp = EngineInput(command=Command.SCAN, root_dir="/tmp")
        engine = Engine(inp)
        # Manually set phase to DONE so no rule matches
        engine.state.phase = Phase.DONE
        with pytest.raises(RuntimeError, match="No rule matched"):
            engine.step()


# ---------------------------------------------------------------------------
# Move strategy tests
# ---------------------------------------------------------------------------


class TestMoveStrategies:
    def test_execute_with_cycles(self, tmp_path):
        """A->B, B->A swap plan. Staged move should swap both files correctly."""
        root = _make_project(tmp_path)
        plan_yaml = _make_swap_plan_yaml(root)

        original_a = (tmp_path / "src" / "a.py").read_text()
        original_b = (tmp_path / "src" / "b.py").read_text()

        inp = EngineInput(
            command=Command.EXECUTE,
            root_dir=root,
            plan_yaml=plan_yaml,
            dry_run=False,
        )
        engine = Engine(inp)
        output = engine.run()

        assert engine.state.phase == Phase.DONE
        assert output.report_json is not None

        # After swap: src/a.py should have original b content, src/b.py should have original a content
        assert (tmp_path / "src" / "a.py").read_text() == original_b
        assert (tmp_path / "src" / "b.py").read_text() == original_a

    def test_patch_docs_skip_clean(self, tmp_path):
        """Plan with delete_empty=False. CLEANING_DIRS phase should be skipped."""
        root = _make_project(tmp_path)
        plan_yaml = _make_plan_yaml_no_delete(root)

        inp = EngineInput(
            command=Command.EXECUTE,
            root_dir=root,
            plan_yaml=plan_yaml,
            dry_run=True,
        )
        engine = Engine(inp)

        visited_phases = []
        while engine.state.phase not in (Phase.DONE, Phase.FAILED):
            visited_phases.append(engine.state.phase)
            engine.step()
        visited_phases.append(engine.state.phase)

        # CLEANING_DIRS should NOT appear in the visited phases
        assert Phase.CLEANING_DIRS not in visited_phases, (
            "CLEANING_DIRS should be skipped when delete_empty=False"
        )

        # Should go from PATCHING_DOCS directly to REPORTING
        assert Phase.PATCHING_DOCS in visited_phases
        assert Phase.REPORTING in visited_phases

        # Verify report shows 0 dirs cleaned
        engine._finalize_output()
        assert engine.output.report_json is not None
        report = json.loads(engine.output.report_json)
        assert report["dirs_cleaned"] == 0
