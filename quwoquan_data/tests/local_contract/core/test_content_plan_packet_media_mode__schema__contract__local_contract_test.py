from __future__ import annotations

import shutil

import pytest

from content.execution.controller.content_plan_output import write_content_plan_packet
from content.post.content_plan_state import load_content_plan_packet
from core.paths import execution_root


EXECUTION_ID = "20260822--travel-article-media-mode--local-contract--scale-997"


@pytest.fixture(autouse=True)
def _clean_execution() -> None:
    shutil.rmtree(execution_root(EXECUTION_ID), ignore_errors=True)
    yield
    shutil.rmtree(execution_root(EXECUTION_ID), ignore_errors=True)


def _text_only_item() -> dict[str, object]:
    return {
        "ref": "九寨沟_explicit_media_mode",
        "kind": "entity",
        "carrier": "article",
        "researchLane": "article",
        "title": "九寨沟行前攻略",
        "entityRefs": ["/entity/地点/景区/九寨沟"],
        "evidenceRefs": ["sources/article/source.md"],
        "rationale": "显式媒体模式写盘合同",
        "publishMediaMode": "text_only",
        "assetRefs": [],
    }


def test_content_plan_packet_persists_explicit_text_only_mode() -> None:
    write_content_plan_packet(
        EXECUTION_ID,
        items=[_text_only_item()],
        source_site=None,
    )

    packet = load_content_plan_packet(EXECUTION_ID)
    assert packet is not None
    assert packet["items"][0]["publishMediaMode"] == "text_only"
    assert packet["items"][0]["assetRefs"] == []


def test_content_plan_packet_rejects_missing_article_media_mode() -> None:
    item = _text_only_item()
    item.pop("publishMediaMode")

    with pytest.raises(ValueError, match="publishMediaMode"):
        write_content_plan_packet(EXECUTION_ID, items=[item], source_site=None)


def test_content_plan_packet_rejects_text_only_assets() -> None:
    item = {
        **_text_only_item(),
        "assetRefs": ["sources/article/assets/cover.jpg"],
    }

    with pytest.raises(ValueError, match="maxItems"):
        write_content_plan_packet(EXECUTION_ID, items=[item], source_site=None)


def test_content_plan_packet_rejects_illustrated_shortfall() -> None:
    item = {
        **_text_only_item(),
        "publishMediaMode": "illustrated",
        "assetRefs": ["sources/article/assets/cover.jpg"],
        "articleSourceUnitFreeze": {
            "receiptRef": "0.plan/article_source_unit_freezes/article.json",
            "freezeDigest": "sha256:" + "1" * 64,
            "sourceUnitId": "article",
            "sourceUnitRef": "sources/article",
            "executionSourceDigest": "sha256:" + "2" * 64,
        },
    }

    with pytest.raises(ValueError, match="minItems"):
        write_content_plan_packet(EXECUTION_ID, items=[item], source_site=None)
