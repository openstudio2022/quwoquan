"""Shared fixtures for content-plan source gate tests."""



from __future__ import annotations

import shutil

import hashlib

import sys

import struct

import zlib

from io import BytesIO

from pathlib import Path

import pytest

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")

SCRIPTS_ROOT = DATA_ROOT / "scripts"

for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from content.post import object_index as content_object
from content.post import content_plan_validation as cp
from content.post import content_plan_state

from core import ops_governance as og

from content.post.article.base_draft import assign_base_draft, base_draft_candidates, extract_base_draft_body, load_base_draft_text
from content.post.fidelity import base_draft_fidelity_issues

from core.io import write_json

from core.paths import STAGE_COMPOSE, execution_content_plan_packet_path, execution_results_dir, execution_root

from content.source.source_unit import resolve_entity_object_dir, write_source_unit
from support.execution_manifest_fixture import build_execution_fixture

EXECUTION_ID = "20260711--travel-article-contract--test-content-plan--pilot-903"
IMAGE_EXECUTION_ID = "20260711--travel-image-contract--test-content-plan--pilot-904"


@pytest.fixture(autouse=True)
def isolated_content_plan_execution():
    """每个合约用例拥有干净的 execution 工作包，禁止跨用例复用运行证据。"""
    root = execution_root(EXECUTION_ID)
    image_root = execution_root(IMAGE_EXECUTION_ID)
    shutil.rmtree(root, ignore_errors=True)
    shutil.rmtree(image_root, ignore_errors=True)
    build_execution_fixture(EXECUTION_ID)
    build_execution_fixture(IMAGE_EXECUTION_ID)
    yield
    shutil.rmtree(root, ignore_errors=True)
    shutil.rmtree(image_root, ignore_errors=True)

def _real_jpeg(seed: int = 0) -> bytes:
    from PIL import Image

    width, height = 320, 220
    img = Image.new("RGB", (width, height))
    for y in range(height):
        for x in range(width):
            img.putpixel(
                (x, y),
                (
                    (x * 5 + seed * 17) % 256,
                    (y * 7 + seed * 29) % 256,
                    ((x + y) * 3 + seed * 11) % 256,
                ),
            )
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()

def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )

def _oversized_png_header(width: int = 9000, height: int = 6000) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _png_chunk(b"IEND", b"")
    )

def _write_article_source_asset(source_dir: Path, *, label: str) -> Path:
    asset_dir = source_dir / "assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    asset_file = asset_dir / f"{label}.jpg"
    asset_bytes = _real_jpeg(hashlib.sha256(label.encode("utf-8")).digest()[0])
    asset_file.write_bytes(asset_bytes)
    write_json(
        asset_dir / "index.json",
        {
            "assets": [
                {
                    "fileName": asset_file.name,
                    "sourceAssetId": f"asset_{label}",
                    "sha256": "sha256:" + hashlib.sha256(asset_bytes).hexdigest(),
                    "sourceCollectionId": f"article:{label}",
                    "acquisitionStatus": "acquired",
                    "platform": "fixture",
                    "capturedAt": "2026-08-05T00:00:00Z",
                    "license": "CC-BY-4.0",
                    "credit": "fixture",
                    "sourceUrl": "https://example.com/image.jpg",
                    "termsUrl": "https://example.com/terms",
                    "authorizationProof": "https://example.com/image.jpg",
                    "authorizationRequired": False,
                    "distributionDecision": "commercial_allowed",
                    "usageScope": "commercial_editorial",
                    "rightsAuditStatus": "verified",
                    "rightsAuditIssues": [],
                    "caption": "与正文底稿同源的配图",
                    "relevance": "与景区正文段落同源相关",
                }
            ]
        },
    )
    return asset_file

def _seed():
    reject_dir = execution_results_dir(EXECUTION_ID, "source", "source_screen")
    write_json(reject_dir / "reject1.json", {"sourceId": "reject1", "decision": "reject"})
    write_json(reject_dir / "keep1.json", {"sourceId": "keep1", "decision": "retain"})
    packet = {
        "schema": cp.CONTENT_PLAN_SCHEMA,
        "items": [
            {
                "ref": "x",
                "kind": "entity",
                "title": "样例",
                "entityRefs": ["e1"],
                "evidenceRefs": ["1.download/sources/reject1.md"],
                "rationale": "r",
                "writingIntent": "planning_consultation",
                "baseSourceRef": "1.download/sources/reject1.md",
            }
        ],
    }
    write_json(execution_content_plan_packet_path(EXECUTION_ID), packet)



__all__ = sorted(name for name in globals() if name != "__all__" and not name.startswith("__"))
