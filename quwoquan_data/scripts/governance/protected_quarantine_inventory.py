"""Immutable tree inventory for protected quarantine evidence."""

from __future__ import annotations

import stat

from governance.protected_quarantine_evidence import (
    Path,
    ProtectedQuarantineEvidenceError,
    _canonical_digest,
    _safe_symlink_entry,
    _sha256_bytes,
    os,
)


def _tree_inventory(root: Path) -> dict[str, object]:
    directories: list[str] = []
    files: list[dict[str, object]] = []
    symlinks: list[dict[str, str]] = []
    byte_count = 0
    for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        retained: list[str] = []
        for name in sorted(dirnames):
            child = current_path / name
            if child.is_symlink():
                symlinks.append(_safe_symlink_entry(child, root=root))
            else:
                mode = child.lstat().st_mode
                if not stat.S_ISDIR(mode):
                    raise ProtectedQuarantineEvidenceError(
                        f"unsupported quarantine entry: {child}"
                    )
                directories.append(child.relative_to(root).as_posix())
                retained.append(name)
        dirnames[:] = retained
        for name in sorted(filenames):
            child = current_path / name
            if child.is_symlink():
                symlinks.append(_safe_symlink_entry(child, root=root))
                continue
            mode = child.lstat().st_mode
            if not stat.S_ISREG(mode):
                raise ProtectedQuarantineEvidenceError(
                    f"unsupported quarantine entry: {child}"
                )
            body = child.read_bytes()
            byte_count += len(body)
            files.append(
                {
                    "path": child.relative_to(root).as_posix(),
                    "byteCount": len(body),
                    "sha256": _sha256_bytes(body),
                }
            )
    if not files:
        raise ProtectedQuarantineEvidenceError(
            "protected quarantine must contain files"
        )
    tree = {
        "directories": sorted(directories),
        "files": sorted(files, key=lambda item: str(item["path"])),
        "symlinks": sorted(symlinks, key=lambda item: item["path"]),
    }
    return {
        **tree,
        "directoryCount": len(tree["directories"]),
        "fileCount": len(tree["files"]),
        "symlinkCount": len(tree["symlinks"]),
        "byteCount": byte_count,
        "treeDigest": _canonical_digest(tree),
    }
