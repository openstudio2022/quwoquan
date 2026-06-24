"""Shared fixtures for content-plan source gate tests."""



from __future__ import annotations

import os

import sys

import tempfile

import struct

import zlib

from io import BytesIO

from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")

SCRIPTS_ROOT = DATA_ROOT / "scripts"

for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

_TMP = tempfile.mkdtemp(prefix="qwq_content_plan_test_")

os.environ["QWQ_RUNTIME_ROOT"] = _TMP

from _common import content_object, content_plan as cp

from _common import ops_governance as og

from _common.base_draft import assign_base_draft, base_draft_candidates, base_draft_fidelity_issues, extract_base_draft_body, load_base_draft_text

from _common.io import write_json

from _common.paths import STAGE_COMPOSE, batch_content_plan_packet_path, batch_results_dir, batch_root

from _common.source_unit import resolve_entity_object_dir, write_source_unit

TASK = "旅行/地域/四川省/景区/景区精选"

BATCH = "test_batch_reject"

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
    asset_file.write_bytes(_real_jpeg(len(label)))
    write_json(
        asset_dir / "index.json",
        {
            "assets": [
                {
                    "fileName": asset_file.name,
                    "sourceAssetId": f"asset_{label}",
                    "sha256": f"sha256:{label}",
                    "sourceCollectionId": f"article:{label}",
                    "license": "CC-BY-4.0",
                    "credit": "fixture",
                    "sourceUrl": "https://example.com/image.jpg",
                    "termsUrl": "https://example.com/terms",
                    "usageScope": "commercial_editorial",
                    "caption": "与正文底稿同源的配图",
                    "relevance": "与景区正文段落同源相关",
                }
            ]
        },
    )
    return asset_file

def _seed():
    reject_dir = batch_results_dir(TASK, BATCH, "download", "source_screen")
    write_json(reject_dir / "reject1.json", {"sourceId": "reject1", "decision": "reject"})
    write_json(reject_dir / "keep1.json", {"sourceId": "keep1", "decision": "retain"})
    packet = {
        "schemaVersion": cp.CONTENT_PLAN_SCHEMA,
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
    write_json(batch_content_plan_packet_path(TASK, BATCH), packet)



__all__ = sorted(name for name in globals() if name != "__all__" and not name.startswith("__"))

