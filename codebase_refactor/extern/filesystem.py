from __future__ import annotations

import hashlib
import os
import shutil
from fnmatch import fnmatch
from pathlib import Path

from codebase_refactor.models import FileEntry, Lang

# ---- extension map --------------------------------------------------------

_EXT_TO_LANG: dict[str, Lang] = {
    ".py": Lang.PYTHON,
    ".js": Lang.JAVASCRIPT,
    ".ts": Lang.TYPESCRIPT,
    ".tsx": Lang.TYPESCRIPT,
    ".md": Lang.MARKDOWN,
}


# ---- pure helpers ---------------------------------------------------------

def detect_lang(path: str) -> Lang:
    ext = Path(path).suffix.lower()
    return _EXT_TO_LANG.get(ext, Lang.OTHER)


def dir_exists(path: str) -> bool:
    return Path(path).is_dir()


def file_exists(path: str) -> bool:
    return Path(path).is_file()


def hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def dir_is_empty(path: str) -> bool:
    return not any(Path(path).iterdir())


def parent_dirs(path: str, root: str) -> list[str]:
    """Return parent directories from *path* up to (not including) *root*.

    The list is ordered child-first: the immediate parent of *path* comes
    first, and the direct child-directory of *root* comes last.
    """
    result: list[str] = []
    current = Path(path).parent
    root_resolved = Path(root).resolve()
    while True:
        resolved = current.resolve()
        if resolved == root_resolved:
            break
        result.append(str(current))
        current = current.parent
        # Safety: stop if we've gone above the filesystem root
        if resolved == current.resolve():
            break
    return result


# ---- read / walk ----------------------------------------------------------

def read_file(path: str) -> str:
    p = Path(path)
    try:
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return p.read_text(encoding="latin-1")


def walk_tree(root: str, ignore_patterns: set[str]) -> dict[str, FileEntry]:
    """Recursively walk *root*, returning ``{relative_path: FileEntry}``.

    *ignore_patterns* are fnmatch-style patterns matched against individual
    directory and file names.  Matching directories are pruned entirely.
    Relative paths use forward slashes regardless of the OS.
    """
    entries: dict[str, FileEntry] = {}
    root_path = Path(root)

    def _ignored(name: str) -> bool:
        return any(fnmatch(name, pat) for pat in ignore_patterns)

    for dirpath, dirnames, filenames in os.walk(root_path):
        # Prune ignored directories in-place so os.walk skips them.
        dirnames[:] = [d for d in dirnames if not _ignored(d)]

        for fname in filenames:
            if _ignored(fname):
                continue
            full = Path(dirpath) / fname
            rel = full.relative_to(root_path).as_posix()
            size = full.stat().st_size
            entries[rel] = FileEntry(
                path=rel,
                lang=detect_lang(fname),
                size_bytes=size,
                hash=hash_file(str(full)),
            )

    return entries


# ---- mutating operations --------------------------------------------------

def write_file(path: str, content: str, dry_run: bool) -> bool:
    if dry_run:
        return True
    Path(path).write_text(content, encoding="utf-8")
    return True


def move_file(src: str, dst: str, dry_run: bool) -> bool:
    if dry_run:
        return True
    shutil.move(src, dst)
    return True


def mkdir(path: str, dry_run: bool) -> bool:
    if dry_run:
        return True
    Path(path).mkdir(parents=True, exist_ok=True)
    return True


def rmdir(path: str, dry_run: bool) -> bool:
    if dry_run:
        return True
    Path(path).rmdir()
    return True


def copy_file(src: str, dst: str, dry_run: bool) -> bool:
    if dry_run:
        return True
    shutil.copy2(src, dst)
    return True
