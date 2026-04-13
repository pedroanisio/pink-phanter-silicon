"""Tests for codebase_refactor.cli — argument parsing and main() entry point."""

import pytest
import yaml

from codebase_refactor.cli import build_parser, main

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_project(tmp_path):
    """Create a small project with a couple of .py files."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("from src.b import hello\n")
    (src / "b.py").write_text("def hello(): pass\n")
    return str(tmp_path)


def _make_plan_file(tmp_path, root):
    """Create a plan.yaml file on disk and return its path."""
    plan_data = {
        "version": "1.0",
        "root": root,
        "delete_empty": True,
        "created_at": "2024-01-01T00:00:00",
        "moves": [{"source": "src/b.py", "destination": "lib/b.py", "lang": "python"}],
    }
    plan_path = tmp_path / "plan.yaml"
    plan_path.write_text(yaml.dump(plan_data))
    return str(plan_path)


# ---------------------------------------------------------------------------
# build_parser tests
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_build_parser_scan(self):
        """Parse 'scan /some/dir' -> args.command='scan', args.root_dir='/some/dir'."""
        parser = build_parser()
        args = parser.parse_args(["scan", "/some/dir"])

        assert args.command == "scan"
        assert args.root_dir == "/some/dir"

    def test_build_parser_scan_with_ignore(self):
        """Parse scan with --ignore flags -> args.ignore has 2 items."""
        parser = build_parser()
        args = parser.parse_args(["scan", "/dir", "--ignore", "*.pyc", "--ignore", "__pycache__"])

        assert args.command == "scan"
        assert args.root_dir == "/dir"
        assert len(args.ignore) == 2
        assert "*.pyc" in args.ignore
        assert "__pycache__" in args.ignore

    def test_build_parser_execute(self):
        """Parse 'execute /dir --plan plan.yaml'."""
        parser = build_parser()
        args = parser.parse_args(["execute", "/dir", "--plan", "plan.yaml"])

        assert args.command == "execute"
        assert args.root_dir == "/dir"
        assert args.plan == "plan.yaml"

    def test_build_parser_execute_dry_run(self):
        """Parse with --dry-run -> args.dry_run=True."""
        parser = build_parser()
        args = parser.parse_args(["execute", "/dir", "--plan", "plan.yaml", "--dry-run"])

        assert args.command == "execute"
        assert args.dry_run is True

    def test_build_parser_no_command(self):
        """Parse empty args -> SystemExit (argparse requires a subcommand)."""
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])


# ---------------------------------------------------------------------------
# main() integration tests
# ---------------------------------------------------------------------------


class TestMain:
    def test_main_scan_bad_root(self):
        """main(['scan', '/nonexistent/path']) -> returns 1."""
        result = main(["scan", "/nonexistent/path"])
        assert result == 1

    def test_main_scan_success(self, tmp_path):
        """Create a directory with .py files, run main with scan -> returns 0."""
        root = _make_project(tmp_path)
        result = main(["scan", root])
        assert result == 0

    def test_main_execute_no_plan_file(self):
        """main with --plan pointing to nonexistent file -> returns 2 (file read error)."""
        result = main(["execute", "/tmp", "--plan", "/nonexistent/plan.yaml"])
        assert result == 2

    def test_main_execute_dry_run(self, tmp_path):
        """Create project and plan file, run execute --dry-run -> returns 0."""
        root = _make_project(tmp_path)
        plan_path = _make_plan_file(tmp_path, root)

        result = main(["execute", root, "--plan", plan_path, "--dry-run"])
        assert result == 0

    def test_main_verbose(self, tmp_path, capsys):
        """Run with -v flag, check stderr has log output."""
        root = _make_project(tmp_path)

        result = main(["scan", root, "-v"])
        assert result == 0

        captured = capsys.readouterr()
        # Verbose mode should print log lines to stderr
        assert len(captured.err) > 0
        # Expect some scan-related log output
        assert (
            "Scanning" in captured.err or "Found" in captured.err or "built" in captured.err.lower()
        )
