# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/geo-content-trinity/spec.md
"""promote_post_object must be idempotent when canonical already matches package."""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from content.release.canonical import post_promotion as subject
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
)
from core.io import write_json
from core.tree_integrity import tree_integrity_stats


def test_promote_post_object_uses_fenced_inventory_not_full_publish_scan() -> None:
    source = inspect.getsource(subject.promote_post_object)

    assert "tree_integrity_stats(PUBLISH_ROOT)" not in source
    assert "validate_publish_invariants" not in source
    assert "refresh_canonical_tag_snapshots" not in source
    assert "load_or_bootstrap_inventory(PUBLISH_ROOT)" in source


def test_promote_post_object_skips_apply_when_canonical_matches_package(
    tmp_path: Path,
    monkeypatch,
) -> None:
    publish = tmp_path / "publish"
    output = tmp_path / "output"
    execution_id = "20260731--travel-image-idempotent--test-region-a--pilot-901"
    post_ref = "image/摄影/已发布/1"
    root = tmp_path / "execution"
    post_root = root / "posts" / post_ref
    write_json(
        post_root / "manifest.json",
        {"contentType": "image", "title": "已发布"},
    )
    write_json(
        post_root / "5.review/attestation.json",
        {"decision": "approved"},
    )
    package_object = (
        root
        / "evidence/object-transactions"
        / f"{execution_id}--post-placeholder"
        / "object"
    )
    # package path is computed inside promote; we monkeypatch builders instead.
    monkeypatch.setattr(subject, "PUBLISH_ROOT", publish)
    monkeypatch.setattr(subject, "OUTPUT_ROOT", output)
    monkeypatch.setattr(subject, "execution_root", lambda _eid: root)
    monkeypatch.setattr(
        subject,
        "_qualified_post_refs",
        lambda _eid: (post_ref,),
    )
    monkeypatch.setattr(
        subject,
        "_assert_cross_publish_image_unique",
        lambda **_kwargs: None,
    )

    def fake_build(**kwargs):
        package_root = kwargs["package_root"]
        obj = package_root / "object"
        write_json(
            obj / "manifest.json",
            {
                "contentType": "image",
                "assets": [
                    {
                        "assetId": "image-1",
                        "kind": "image",
                        "sha256": "sha256:" + "a" * 64,
                        "perceptualHash": "0" * 16,
                    }
                ],
            },
        )
        canonical = publish / "posts" / post_ref
        write_json(
            canonical / "manifest.json",
            {
                "contentType": "image",
                "assets": [
                    {
                        "assetId": "image-1",
                        "kind": "image",
                        "sha256": "sha256:" + "a" * 64,
                        "perceptualHash": "0" * 16,
                    }
                ],
            },
        )
        assert (
            tree_integrity_stats(canonical)["merkleRoot"]
            == tree_integrity_stats(obj)["merkleRoot"]
        )

    apply_calls: list[str] = []

    def fake_apply(**_kwargs):
        apply_calls.append("apply")
        raise AssertionError("apply must not run for matching canonical")

    monkeypatch.setattr(subject, "build_post_object_transaction_package", fake_build)
    monkeypatch.setattr(subject, "audit_object_transaction", lambda **_k: {})
    monkeypatch.setattr(subject, "apply_object_transaction", fake_apply)
    monkeypatch.setattr(
        subject,
        "repair_applied_post_pool_record_drift",
        lambda **_kwargs: False,
    )
    result = subject.promote_post_object(
        execution_id,
        post_ref,
        pool_delivery_intent={"schema": "test.pool_delivery_intent"},
    )
    assert result["canonicalObjectRef"] == f"posts/{post_ref}"
    assert apply_calls == []
    assert package_object  # silence unused in lint-free path


@pytest.mark.parametrize(
    ("drift_key", "canonical_value"),
    (
        ("executionId", "a-different-execution"),
        ("sourceDigest", {"algorithm": "sha256", "digest": "b" * 64}),
        ("title", "a different Merkle payload"),
    ),
)
def test_promote_post_object_rejects_existing_canonical_identity_or_merkle_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    drift_key: str,
    canonical_value: object,
) -> None:
    publish = tmp_path / "publish"
    output = tmp_path / "output"
    execution_id = "20260731--travel-image-idempotent--test-region-a--pilot-902"
    post_ref = "image/摄影/已发布/2"
    root = tmp_path / execution_id
    post_root = root / "posts" / post_ref
    write_json(post_root / "manifest.json", {"contentType": "image"})
    write_json(post_root / "5.review/attestation.json", {"decision": "approved"})
    package_manifest = {
        "contentType": "image",
        "executionId": execution_id,
        "sourceDigest": {"algorithm": "sha256", "digest": "a" * 64},
        "title": "expected payload",
    }

    monkeypatch.setattr(subject, "PUBLISH_ROOT", publish)
    monkeypatch.setattr(subject, "OUTPUT_ROOT", output)
    monkeypatch.setattr(subject, "execution_root", lambda _eid: root)
    monkeypatch.setattr(subject, "_qualified_post_refs", lambda _eid: (post_ref,))
    monkeypatch.setattr(
        subject,
        "_assert_cross_publish_image_unique",
        lambda **_kwargs: None,
    )

    def fake_build(**kwargs: object) -> None:
        package_root = kwargs["package_root"]
        assert isinstance(package_root, Path)
        write_json(package_root / "object/manifest.json", package_manifest)
        canonical_manifest = dict(package_manifest)
        canonical_manifest[drift_key] = canonical_value
        write_json(
            publish / "posts" / post_ref / "manifest.json",
            canonical_manifest,
        )

    monkeypatch.setattr(subject, "build_post_object_transaction_package", fake_build)
    monkeypatch.setattr(
        subject,
        "audit_object_transaction",
        lambda **_kwargs: pytest.fail("drifted canonical must not be audited/applied"),
    )
    monkeypatch.setattr(
        subject,
        "apply_object_transaction",
        lambda **_kwargs: pytest.fail("drifted canonical must not be applied"),
    )

    with pytest.raises(
        ObjectTransactionError,
        match="completed post transaction canonical object drift",
    ):
        subject.promote_post_object(
            execution_id,
            post_ref,
            pool_delivery_intent={"schema": "test.pool_delivery_intent"},
        )


def test_promote_execution_posts_does_not_count_existing_canonical_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution_id = "20260731--travel-image-idempotent--test-region-a--pilot-903"
    post_ref = "image/摄影/冲突/1"
    publish = tmp_path / "publish"
    write_json(
        publish / "posts" / post_ref / "manifest.json",
        {"executionId": "a-different-execution"},
    )
    publish_ref_writes: list[tuple[str, tuple[str, ...]]] = []
    root = tmp_path / "execution"
    write_json(
        root / "_shared/pool_delivery_intents/one.json",
        {
            "schema": "test.pool_delivery_intent",
            "contentObjectDir": f"posts/{post_ref}",
        },
    )

    monkeypatch.setattr(subject, "PUBLISH_ROOT", publish)
    monkeypatch.setattr(subject, "execution_root", lambda _eid: root)
    monkeypatch.setattr(subject, "_qualified_post_refs", lambda _eid: (post_ref,))
    monkeypatch.setattr(
        subject,
        "promote_post_object",
        lambda _eid, _ref, *, pool_delivery_intent: (_ for _ in ()).throw(
            ObjectTransactionError("canonical identity drift")
        ),
    )
    monkeypatch.setattr(
        subject,
        "write_publish_ref",
        lambda eid, *, post_refs, publish_discards: publish_ref_writes.append(
            (eid, tuple(post_refs))
        ),
    )

    with pytest.raises(ObjectTransactionError, match="finalized zero objects"):
        subject.promote_execution_posts(execution_id)

    assert publish_ref_writes == []


def test_promote_execution_posts_writes_only_succeeded_refs_and_typed_discard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution_id = "20260731--travel-image-partial--test-region-a--pilot-904"
    refs = tuple(f"image/摄影/对象-{index}/1" for index in range(3))
    root = tmp_path / "execution"
    for index, ref in enumerate(refs):
        write_json(
            root / f"_shared/pool_delivery_intents/{index}.json",
            {
                "schema": "test.pool_delivery_intent",
                "contentObjectDir": f"posts/{ref}",
            },
        )
    writes: list[dict[str, object]] = []
    monkeypatch.setattr(subject, "execution_root", lambda _eid: root)
    monkeypatch.setattr(subject, "_qualified_post_refs", lambda _eid: refs)

    def promote(_eid, ref, *, pool_delivery_intent):
        assert pool_delivery_intent["contentObjectDir"] == f"posts/{ref}"
        if ref == refs[1]:
            raise ObjectTransactionError("object admission rejected")
        return {"canonicalObjectRef": f"posts/{ref}"}

    monkeypatch.setattr(subject, "promote_post_object", promote)
    monkeypatch.setattr(
        subject,
        "write_publish_ref",
        lambda eid, **values: writes.append({"executionId": eid, **values}),
    )

    promoted = subject.promote_execution_posts(execution_id)

    assert promoted == (refs[0], refs[2])
    assert writes == [
        {
            "executionId": execution_id,
            "post_refs": [refs[0], refs[2]],
            "publish_discards": [
                {
                    "objectRef": refs[1],
                    "issues": ["DATA.PUBLISH.OBJECT_ADMISSION_FAILED"],
                }
            ],
        }
    ]
