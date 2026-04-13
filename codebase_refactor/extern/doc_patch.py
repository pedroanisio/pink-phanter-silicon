from __future__ import annotations

import re


def patch_doc_paths(content: str, renames: dict[str, str]) -> str:
    for old_path in sorted(renames.keys(), key=len, reverse=True):
        pattern = re.compile(r"(?<![^\s\'\"(`/])" + re.escape(old_path) + r"(?![^\s\'\")`/])")
        content = pattern.sub(renames[old_path], content)
    return content
