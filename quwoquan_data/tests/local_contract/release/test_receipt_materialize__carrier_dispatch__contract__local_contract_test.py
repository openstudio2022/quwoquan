"""receipt 物化按 writing_pack.carrier 分发，冻结输入缺失即 fail closed（DEC-027）。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from content.release.canonical.receipt_materialize import (
    ReceiptMaterializeError,
    materialize_receipt_post,
)


def _object_dir(
    tmp_path: Path,
    *,
    carrier: str,
    pack_overrides: dict | None = None,
    decision: str = "approved",
) -> Path:
    object_dir = tmp_path / "posts" / carrier / "攻略" / "对象" / "1"
    (object_dir / "3.compose").mkdir(parents=True)
    (object_dir / "4.draft").mkdir(parents=True)
    (object_dir / "5.review").mkdir(parents=True)
    pack = {
        "carrier": carrier,
        "ref": f"posts/{carrier}/攻略/对象/1",
        "vertical": "travel",
        "title": "对象标题",
        "creatorProfileRef": "creator-profile-001",
        "tagRefs": ["Topic/旅行"],
        **(pack_overrides or {}),
    }
    (object_dir / "3.compose/writing_pack.json").write_text(
        json.dumps(pack, ensure_ascii=False), encoding="utf-8"
    )
    (object_dir / "5.review/attestation.json").write_text(
        json.dumps({"decision": decision}, ensure_ascii=False), encoding="utf-8"
    )
    return object_dir


_TARGET = {
    "entityType": "地点/景区",
    "name": "对象",
    "publishAngle": "攻略",
    "publishTitle": "对象",
    "publishSeq": 1,
}


def test_unapproved_attestation_fails_closed(tmp_path: Path) -> None:
    object_dir = _object_dir(
        tmp_path,
        carrier="article",
        pack_overrides={"baseSourceRef": "sources/base/meta.json"},
        decision="rejected",
    )
    (object_dir / "4.draft/draft.article.md").write_text("正文", encoding="utf-8")
    with pytest.raises(ReceiptMaterializeError, match="not approved"):
        materialize_receipt_post("exec-x", object_dir=object_dir, target=_TARGET)


def test_article_requires_frozen_draft(tmp_path: Path) -> None:
    object_dir = _object_dir(
        tmp_path,
        carrier="article",
        pack_overrides={"baseSourceRef": "sources/base/meta.json"},
    )
    with pytest.raises(ReceiptMaterializeError, match="draft.article.md"):
        materialize_receipt_post("exec-x", object_dir=object_dir, target=_TARGET)


def test_video_requires_frozen_script_and_meta(tmp_path: Path) -> None:
    object_dir = _object_dir(tmp_path, carrier="video")
    with pytest.raises(ReceiptMaterializeError, match="video_script.json"):
        materialize_receipt_post("exec-x", object_dir=object_dir, target=_TARGET)


def test_video_pack_requires_admitted_source_video(tmp_path: Path) -> None:
    object_dir = _object_dir(tmp_path, carrier="video")
    (object_dir / "4.draft/video_script.json").write_text("{}", encoding="utf-8")
    (object_dir / "4.draft/draft_meta.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ReceiptMaterializeError, match="sourceVideo"):
        materialize_receipt_post("exec-x", object_dir=object_dir, target=_TARGET)


def test_image_pack_requires_assets(tmp_path: Path) -> None:
    object_dir = _object_dir(tmp_path, carrier="image")
    with pytest.raises(ReceiptMaterializeError, match="assets"):
        materialize_receipt_post("exec-x", object_dir=object_dir, target=_TARGET)


def test_carrier_outside_closed_set_fails(tmp_path: Path) -> None:
    object_dir = _object_dir(tmp_path, carrier="micro")
    with pytest.raises(ReceiptMaterializeError, match="does not support carrier"):
        materialize_receipt_post("exec-x", object_dir=object_dir, target=_TARGET)
