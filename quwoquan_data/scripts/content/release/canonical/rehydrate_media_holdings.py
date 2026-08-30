#!/usr/bin/env python3
"""Admit the golden tree's media bytes into the content library.

Canonical publish carries references and never bodies, and the library that owns
those bodies lives outside the working tree so that a routine clean cannot
destroy them. A fresh checkout therefore owns no media at all, and every closure
check fails for want of bytes rather than for any defect in the tree.

The bytes are carried in version control beside the tree. Refetching them from
the upstream each asset was captured from is not an option: the encoded video,
its poster and the creator avatars are derived artifacts that no upstream can
reproduce byte for byte, and the upstream that holds the rest refuses automated
bulk retrieval. Provenance and licence stay recorded in the rights documents;
this step only moves bytes the repository already owns into the library.

Admission verifies bytes against the digest they are filed under, so a corrupted
or substituted reference file cannot enter the library under a digest it does
not hash to.
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(SCRIPTS_ROOT))

from content.release.canonical.media_holding_closure import (  # noqa: E402
    media_references_in_tree,
)
from core.content_library import (  # noqa: E402
    MediaHoldingError,
    admit_library_entry,
    carried_media_entry,
    resolve_media_holding,
)
from core.paths import PUBLISH_ROOT, carried_media_root  # noqa: E402
MEDIA_KIND = "media"


def required_digests(publish_root: Path) -> set[str]:
    """Every media digest the canonical tree references, counted once.

    Which references the library is expected to hold is decided by the closure
    module, not by a second scan here: two scans would eventually disagree about
    whether a rights snapshot or a reclaimed source original counts, and this
    step would then admit — or fail to admit — a different set than the closure
    check judges.
    """

    return {reference.digest for reference in media_references_in_tree(publish_root)}


def reference_entry(digest: str) -> Path | None:
    """The carried bytes for one holding, whatever container it was filed as."""

    return carried_media_entry(digest)


def rehydrate_one(digest: str) -> str:
    """Admit one holding and report which route honoured it."""

    try:
        resolve_media_holding(digest)
        return "already_held"
    except (MediaHoldingError, ValueError):
        pass
    entry = reference_entry(digest)
    if entry is None:
        return "unresolved_no_reference_bytes"
    admit_library_entry(entry, kind=MEDIA_KIND, sha256=digest)
    return "admitted"


def main(publish_root: Path | None = None) -> int:
    # 测试进程把 PUBLISH_ROOT 隔离到空临时根，照那里扫会一条都扫不到，
    # 于是"零条holdings"被当成成功；调用方要判的是哪棵树就把哪棵树交进来。
    digests = required_digests(publish_root or PUBLISH_ROOT)
    outcomes: dict[str, list[str]] = {}
    for digest in sorted(digests):
        outcomes.setdefault(rehydrate_one(digest), []).append(digest)
    for outcome in sorted(outcomes):
        print(f"[rehydrate_media_holdings] {outcome}: {len(outcomes[outcome])}")
    unresolved = outcomes.get("unresolved_no_reference_bytes", [])
    if unresolved:
        print("[rehydrate_media_holdings] FAIL")
        for digest in sorted(unresolved):
            print(
                f"  - holding has no carried bytes: {digest} "
                f"(expected {carried_media_root()}/{digest}.<ext>)"
            )
        return 1
    print(f"[rehydrate_media_holdings] OK: {len(digests)} holdings")
    return 0
