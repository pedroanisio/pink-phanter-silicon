from __future__ import annotations

import os


def preflight_moves(move_map: dict[str, str], root: str) -> bool:
    sources = set(move_map.keys())

    for src in sources:
        if not os.path.isfile(os.path.join(root, src)):
            return False

    for dst in move_map.values():
        full_dst = os.path.join(root, dst)
        parent = os.path.dirname(full_dst)
        if not os.path.isdir(parent):
            return False
        if os.path.isfile(full_dst) and dst not in sources:
            return False

    return True


def preflight_rewrites(move_map: dict[str, str], root: str) -> bool:
    _ = move_map
    for dirpath, _dirnames, filenames in os.walk(root):
        for fname in filenames:
            path = os.path.join(dirpath, fname)
            if not os.access(path, os.R_OK | os.W_OK):
                return False
    return True
