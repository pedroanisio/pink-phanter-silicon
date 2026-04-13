from __future__ import annotations

import datetime
import json


def serialize_report(
    log: list[str],
    files_moved: int,
    imports_patched: int,
    docs_patched: int,
    dirs_cleaned: int,
    dirs_created: int,
    backup_complete: bool,
    dry_run: bool,
) -> str:
    return json.dumps(
        {
            "dry_run": dry_run,
            "backup_complete": backup_complete,
            "files_moved": files_moved,
            "imports_patched": imports_patched,
            "docs_patched": docs_patched,
            "dirs_cleaned": dirs_cleaned,
            "dirs_created": dirs_created,
            "log": log,
        },
        indent=2,
    )


def timestamp_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()
