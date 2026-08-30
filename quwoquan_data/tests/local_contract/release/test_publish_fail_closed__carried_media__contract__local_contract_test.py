# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-022.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-022.t2
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-022.t3
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-022.t4
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-022.t5
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-022.t6
"""An object cannot reach `approved` holding bytes only a single machine can serve.

The content library answers every runtime resolution but lives outside the working
tree and cannot be rebuilt from version control. A transaction that admitted a body
there and stopped produced an object that is approved on the machine that made it
and undeliverable everywhere else — and the way that surfaced was a release build,
much later, reporting a digest missing long after the execution evidence that would
explain it had been reclaimed.

So the carried reference is a precondition of the apply, not a follow-up chore.
These anchors judge the transaction core directly, because that is the single place
deciding which of a package's files become canonical files and which become bodies.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
)
from content.release.canonical.object_transaction_delta import (
    apply_forward_delta,
    build_transaction_delta,
)
from content.release.canonical.canonical_inventory import load_or_bootstrap_inventory
from core.content_library import (
    MEDIA_KIND,
    MediaHoldingError,
    carried_media_entry,
    carry_media_reference,
    library_cas_root,
    resolve_media_holding,
)
from core.paths import carried_media_root
from support.object_transaction_fixtures import (
    OBJECT_REF,
    build_canonical,
    build_package,
)


def _frozen_package(package_root: Path) -> dict[str, object]:
    package = json.loads(
        (package_root / "object_transaction_package.json").read_text(encoding="utf-8")
    )
    closure = package["closure"]
    return {
        "transactionId": package["transactionId"],
        "executionId": package["executionId"],
        "objectKind": package["target"]["objectKind"],
        "objectRef": package["target"]["objectRef"],
        "objectRoot": package_root / package["target"]["packageObjectRef"],
        "creatorRefs": closure["creatorRefs"],
        "tagRefs": closure["tagRefs"],
        "casRows": closure["casRefs"],
    }


def _commit(publish: Path, package_root: Path, run_root: Path) -> dict[str, object]:
    delta, _after = build_transaction_delta(
        publish_root=publish,
        run_root=run_root,
        package_root=package_root,
        package=_frozen_package(package_root),
        before_inventory=load_or_bootstrap_inventory(publish),
    )
    apply_forward_delta(publish_root=publish, run_root=run_root, manifest=delta)
    return delta


def _cited_asset(publish: Path) -> dict[str, object]:
    manifest = json.loads(
        (publish / "entities" / OBJECT_REF / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    return manifest["assets"][0]


def test_committed_object_owns_its_body_in_both_homes(tmp_path: Path) -> None:
    publish = build_canonical(tmp_path)
    package_root = build_package(tmp_path, publish)
    source_body = (package_root / "cas/image.jpg").read_bytes()

    _commit(publish, package_root, tmp_path / "run")

    asset = _cited_asset(publish)
    digest = str(asset["sha256"])

    # The library is what a consumer resolves against on this machine.
    entry = resolve_media_holding(digest, expected_bytes=int(asset["bytes"]))
    assert entry.is_relative_to(library_cas_root(MEDIA_KIND))

    # The carried reference is what a different checkout rebuilds from. Same bytes,
    # addressed by the same digest the canonical document froze.
    carried = carried_media_entry(digest)
    assert carried is not None, sorted(
        path.name for path in carried_media_root().glob("*")
    )
    assert carried.read_bytes() == source_body


def test_transaction_fails_closed_when_the_body_cannot_be_carried(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish = build_canonical(tmp_path)
    package_root = build_package(tmp_path, publish)

    # A carried root that cannot accept bytes stands in for every reason the
    # version-controlled home can refuse one: absent, read-only, out of space.
    blocked = tmp_path / "blocked_carried_root"
    blocked.write_text("not a directory", encoding="utf-8")
    monkeypatch.setenv("QWQ_CARRIED_MEDIA_ROOT", str(blocked))

    with pytest.raises(ObjectTransactionError) as failure:
        _commit(publish, package_root, tmp_path / "run")

    assert "cannot be owned for publish" in str(failure.value)

    # Fail closed means the object did not land. An approved-but-undeliverable
    # object is exactly the state this anchor exists to prevent.
    assert not (publish / "entities" / OBJECT_REF / "manifest.json").exists()


def test_carrying_refuses_bytes_that_disagree_with_the_declared_digest(
    tmp_path: Path,
) -> None:
    body = tmp_path / "substituted.jpg"
    body.write_bytes(b"substituted-bytes")
    declared = "0" * 64

    with pytest.raises(MediaHoldingError) as failure:
        carry_media_reference(body, sha256=declared, suffix=".jpg")

    assert "carried media drift" in str(failure.value)
    # A refused carry leaves nothing behind, so a retry is not competing with a
    # partial write from the attempt that failed.
    assert carried_media_entry(declared) is None
    assert list(carried_media_root().glob(f"{declared}.*")) == []


def test_carrying_the_same_body_twice_converges_on_one_entry(tmp_path: Path) -> None:
    import hashlib

    body = tmp_path / "cover.webp"
    payload = b"cover-bytes"
    body.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()

    first = carry_media_reference(body, sha256=digest, suffix=".webp")
    second = carry_media_reference(body, sha256=digest, suffix=".webp")

    assert first == second
    assert [path.name for path in carried_media_root().glob(f"{digest}.*")] == [
        f"{digest}.webp"
    ]


def test_a_second_commit_of_the_same_object_stays_idempotent(tmp_path: Path) -> None:
    publish = build_canonical(tmp_path)
    package_root = build_package(tmp_path, publish)

    _commit(publish, package_root, tmp_path / "run")
    carried_before = sorted(path.name for path in carried_media_root().glob("*"))

    # Re-running the same transaction must not multiply carried bodies: the digest
    # already carried is the same digest the object still cites.
    _commit(publish, package_root, tmp_path / "run_again")

    assert sorted(path.name for path in carried_media_root().glob("*")) == carried_before
