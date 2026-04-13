"""Tests for codebase_refactor.extern.reporting."""

from __future__ import annotations

import json
import re

from codebase_refactor.extern.reporting import serialize_report, timestamp_now

# -- serialize_report ----------------------------------------------------------


def test_serialize_report_structure():
    result = serialize_report(
        log=["step1", "step2"],
        files_moved=3,
        imports_patched=5,
        docs_patched=2,
        dirs_cleaned=1,
        dirs_created=4,
        backup_complete=True,
        dry_run=False,
    )
    data = json.loads(result)

    expected_keys = {
        "dry_run",
        "backup_complete",
        "files_moved",
        "imports_patched",
        "docs_patched",
        "dirs_cleaned",
        "dirs_created",
        "log",
    }
    assert set(data.keys()) == expected_keys

    assert data["files_moved"] == 3
    assert data["imports_patched"] == 5
    assert data["docs_patched"] == 2
    assert data["dirs_cleaned"] == 1
    assert data["dirs_created"] == 4
    assert data["backup_complete"] is True
    assert data["dry_run"] is False


def test_serialize_report_dry_run_flag():
    result = serialize_report(
        log=[],
        files_moved=0,
        imports_patched=0,
        docs_patched=0,
        dirs_cleaned=0,
        dirs_created=0,
        backup_complete=False,
        dry_run=True,
    )
    data = json.loads(result)
    assert data["dry_run"] is True


def test_serialize_report_log_included():
    log_entries = ["initialized", "scanned 42 files", "done"]
    result = serialize_report(
        log=log_entries,
        files_moved=0,
        imports_patched=0,
        docs_patched=0,
        dirs_cleaned=0,
        dirs_created=0,
        backup_complete=False,
        dry_run=False,
    )
    data = json.loads(result)
    assert data["log"] == log_entries


# -- timestamp_now -------------------------------------------------------------


def test_timestamp_now_format():
    ts = timestamp_now()

    # Must contain "T" separating date and time.
    assert "T" in ts

    # Must end with a UTC offset: either "+00:00" or "Z".
    assert ts.endswith("+00:00") or ts.endswith("Z"), (
        f"Timestamp does not end with a UTC marker: {ts}"
    )

    # Basic ISO 8601 shape check: YYYY-MM-DDTHH:MM:SS...
    assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", ts)


def test_timestamp_now_returns_string():
    ts = timestamp_now()
    assert isinstance(ts, str)
