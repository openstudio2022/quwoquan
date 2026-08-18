#!/usr/bin/env python3
"""Verify every content library entry is addressed by the digest of its own bytes.

The library is content-addressed: an entry's path *is* the sha256 of what it
holds, and every consumer resolves bytes by asking for that digest. Both
admission seams keep that invariant on write — `admit_library_entry` verifies
the bytes against the declared digest before the entry becomes visible, and
`admit_library_bytes` derives the address from the content it is given. Nothing
re-checks it on read: `resolve_media_holding` answers reachability and, when
asked, size, so an entry whose bytes were replaced out of band resolves and
flows into a release as if it were genuine. This gate is that missing read-side
check, and it is deliberately whole-library rather than publish-scoped: an
entry is shared by digest, so a corrupt one is a hazard to every future
reference, not only to the objects that happen to cite it today.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path


SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_ROOT))

from core.content_library import library_cas_root
from core.paths import LIBRARY_CAS_ROOT_BY_KIND

_READ_CHUNK = 1024 * 1024


def _content_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_READ_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def library_addressing_issues() -> list[dict[str, str]]:
    """Return one issue per entry whose bytes disagree with the address holding them."""

    issues: list[dict[str, str]] = []
    for kind in sorted(LIBRARY_CAS_ROOT_BY_KIND):
        root = library_cas_root(kind)
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                issues.append(
                    {
                        "code": "library_entry_symlink",
                        "kind": kind,
                        "ref": path.relative_to(root).as_posix(),
                    }
                )
                continue
            if not path.is_file():
                continue
            address = path.name.split(".")[0]
            observed = _content_digest(path)
            if observed != address:
                issues.append(
                    {
                        "code": "library_entry_address_drift",
                        "kind": kind,
                        "ref": f"{address}: holds {observed}",
                    }
                )
    return issues


def _entry_count() -> int:
    total = 0
    for kind in LIBRARY_CAS_ROOT_BY_KIND:
        root = library_cas_root(kind)
        if root.is_dir():
            total += sum(1 for path in root.rglob("*") if path.is_file())
    return total


def main() -> int:
    issues = library_addressing_issues()
    if issues:
        print("[verify_content_library_addressing] FAIL")
        for issue in issues:
            print(f"  - {issue['code']} [{issue['kind']}]: {issue['ref']}")
        return 1
    print(f"[verify_content_library_addressing] OK entries={_entry_count()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
