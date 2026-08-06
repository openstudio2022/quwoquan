# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/geo-content-trinity/spec.md
"""promote_post_object must be idempotent when canonical already matches package."""
from __future__ import annotations

import inspect
from pathlib import Path

from content.release.canonical import post_promotion as subject
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
    result = subject.promote_post_object(execution_id, post_ref)
    assert result["canonicalObjectRef"] == f"posts/{post_ref}"
    assert apply_calls == []
    assert package_object  # silence unused in lint-free path
