# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-027.t11
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-027.t12
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-027.t13
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-027.t14
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-027.t15
"""local_contract：全景接片的源像素上限只在 media_processing.policy.yaml 声明一次。

现场缺陷：郎木寺一张 2.01 亿像素的 Commons 全景接片在 `1.download` 被判
`DATA.ACQUIRE.MIME_MISMATCH`——真正的失败点是 PIL 默认 1.79 亿像素的解压炸弹阈值，
它在策略文件之外构成了一条看不见的第二阈值。策略把上限提到 `maxSourcePixels` 后，
派生必须用 JPEG draft 在解码前降到交付宽度，否则一张 1920 宽交付体要先解压数 GiB。
"""
from __future__ import annotations

import hashlib
import io
import json
import socket
import sys
import warnings
from pathlib import Path

import pytest
from PIL import Image

DATA_ROOT = next(
    parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data"
)
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from content.source import acquire as acquire_module  # noqa: E402
from core import paths  # noqa: E402
from core.image_decode import (  # noqa: E402
    MAX_SOURCE_PIXELS,
    ImageDecodeFailure,
    draft_to_display_width,
    probe_image_bytes,
)
from core.image_variants import build_local_variants, derive_budget_compliant_variant  # noqa: E402
from core.media_asset_url import effective_delivery_width  # noqa: E402
from core.media_processing_policy import MEDIA_PROCESSING_POLICY  # noqa: E402

# Pillow 出厂的解压炸弹阈值；策略必须显式高于它，全景接片才可能进入。
_PIL_FACTORY_PIXEL_LIMIT = 178_956_970
# 20000×9000 = 1.8 亿像素：高于 Pillow 出厂阈值、低于策略上限、高于可发布像素上限。
_PANORAMA_SIZE = (20000, 9000)
_PANORAMA: bytes | None = None


def _panorama_jpeg() -> bytes:
    """单色灰度 JPEG：栅格真实存在（解码必须走 draft 才省内存），字节却远小于对象预算。"""

    global _PANORAMA
    if _PANORAMA is None:
        buffer = io.BytesIO()
        Image.new("L", _PANORAMA_SIZE, color=128).save(buffer, format="JPEG", quality=60)
        _PANORAMA = buffer.getvalue()
    return _PANORAMA


def test_source_pixel_limit_is_declared_once_and_aligns_pillow():
    assert MAX_SOURCE_PIXELS == MEDIA_PROCESSING_POLICY.max_source_pixels
    assert MAX_SOURCE_PIXELS >= MEDIA_PROCESSING_POLICY.max_publishable_image_pixels
    assert MAX_SOURCE_PIXELS > _PIL_FACTORY_PIXEL_LIMIT
    assert Image.MAX_IMAGE_PIXELS == MAX_SOURCE_PIXELS


def test_panorama_between_pillow_default_and_policy_probes_without_warning():
    payload = _panorama_jpeg()
    assert _PANORAMA_SIZE[0] * _PANORAMA_SIZE[1] > _PIL_FACTORY_PIXEL_LIMIT
    assert _PANORAMA_SIZE[0] * _PANORAMA_SIZE[1] <= MAX_SOURCE_PIXELS

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        probe = probe_image_bytes(payload)
    assert probe.succeeded
    assert (probe.width, probe.height) == _PANORAMA_SIZE


def test_source_above_policy_limit_is_typed_rejection():
    payload = _panorama_jpeg()
    original = Image.MAX_IMAGE_PIXELS
    try:
        # 模拟策略上限低于该图：PIL 阈值被拉低到策略之下时，结论仍是 typed 判否而非告警。
        Image.MAX_IMAGE_PIXELS = _PANORAMA_SIZE[0] * _PANORAMA_SIZE[1] - 1
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            probe = probe_image_bytes(payload)
    finally:
        Image.MAX_IMAGE_PIXELS = original
    assert probe.failure is ImageDecodeFailure.PIXEL_LIMIT_EXCEEDED


def test_jpeg_draft_decodes_below_source_but_not_below_target():
    payload = _panorama_jpeg()
    probe = probe_image_bytes(payload)
    target = effective_delivery_width("full", stored_width=probe.width)
    assert target < probe.width

    with Image.open(io.BytesIO(payload)) as image:
        draft_to_display_width(image, probe=probe, target_width=target)
        decoded_width, decoded_height = image.size
    assert target <= decoded_width < probe.width
    # 缩放档等比：高度与宽度按同一因子收缩（DCT 缩放的取整误差不超过 1 像素）。
    assert abs(decoded_height - decoded_width * probe.height / probe.width) <= 1


def test_panorama_variants_match_full_decode_geometry():
    payload = _panorama_jpeg()
    probe = probe_image_bytes(payload)

    variants = build_local_variants(payload, base_name="panorama")
    assert variants, "全景接片必须能派生交付档"
    for variant in variants:
        expected_w = effective_delivery_width(variant["profile"], stored_width=probe.width)
        assert variant["width"] == expected_w
        assert abs(variant["height"] - round(probe.height * expected_w / probe.width)) <= 1
        with Image.open(io.BytesIO(variant["bytes"])) as encoded:
            assert encoded.size == (variant["width"], variant["height"])

    derived = derive_budget_compliant_variant(payload, budget_bytes=10 * 1024 * 1024)
    assert derived is not None
    assert (derived["sourceWidth"], derived["sourceHeight"]) == _PANORAMA_SIZE
    assert derived["width"] == effective_delivery_width("full", stored_width=probe.width)


# ── 下载截面：像素超发布上限但字节在预算内的候选同样降采样 ────────────────────

EXECUTION_ID = "20260908--travel-image-six-step--ingest--pilot-002"
TARGET = "posts/image/风光/郎木寺全景/1"


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


@pytest.fixture()
def execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    def _refuse(*_args, **_kwargs):
        raise AssertionError("task acquire 不得发起任何网络连接")

    monkeypatch.setattr(socket, "socket", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)
    tasks = tmp_path / "data/tasks"
    monkeypatch.setattr(paths, "DATA_EXECUTIONS_ROOT", tasks)
    monkeypatch.delenv("QWQ_LIBRARY_ROOT", raising=False)
    root = tasks / EXECUTION_ID
    _write(
        root / "execution_manifest.json",
        _canonical({"schema": "quwoquan_data.content_execution_manifest", "executionId": EXECUTION_ID}),
    )
    _write(
        root / "0.plan/target_set.json",
        _canonical(
            {
                "schema": "quwoquan_data.target_set",
                "executionId": EXECUTION_ID,
                "carrier": "image",
                "selectionPolicy": "frozen",
                "entityCatalogDigest": "sha256:" + "0" * 64,
                "candidateBinding": {
                    "scope": "output",
                    "ref": "x.json",
                    "digest": "sha256:" + "1" * 64,
                    "candidateCount": 1,
                },
                "targetCount": 1,
                "targetRefs": [TARGET],
                "targets": [
                    {
                        "name": "郎木寺",
                        "entityType": "地点/景区",
                        "publishAngle": "风光",
                        "publishTitle": "郎木寺全景",
                        "publishSeq": 1,
                    }
                ],
            }
        ),
    )
    return root


def test_acquire_downsamples_panorama_above_publishable_pixels_even_within_byte_budget(
    execution: Path, tmp_path: Path
) -> None:
    body = _panorama_jpeg()
    assert len(body) <= MEDIA_PROCESSING_POLICY.object_storage_budget_bytes_by_carrier["default"]
    assert _PANORAMA_SIZE[0] * _PANORAMA_SIZE[1] > MEDIA_PROCESSING_POLICY.max_publishable_image_pixels

    image = _write(tmp_path / "downloads/langmusi.jpg", body)
    manifest = _write(
        tmp_path / "ingest.json",
        _canonical(
            {
                "schema": "quwoquan_data.ingest_manifest",
                "executionId": EXECUTION_ID,
                "targets": [
                    {
                        "targetRef": TARGET,
                        "sources": [
                            {
                                "kind": "image",
                                "sourceUrl": "https://commons.wikimedia.org/wiki/File:Langmusi_panorama.jpg",
                                "directUrl": "https://upload.wikimedia.org/wikipedia/commons/1/1a/Langmusi_panorama.jpg",
                                "filePath": str(image),
                                "sha1": hashlib.sha1(body).hexdigest(),
                                "license": "CC BY-SA 4.0",
                                "licenseUrl": "https://creativecommons.org/licenses/by-sa/4.0",
                                "creator": "Gisling",
                                "description": "郎木寺全景接片",
                                "relevance": "实体本身的全景图",
                                "watermarkStatus": "absent",
                                "watermarkKind": "none",
                            }
                        ],
                    }
                ],
            }
        ),
    )

    result = acquire_module.acquire(execution_id=EXECUTION_ID, request_path=manifest)

    assert result["ingested"] == 1 and result["failed"] == 0, result
    refs = json.loads((execution / TARGET / "1.download/source_refs.json").read_bytes())
    unit = execution / refs["sources"][0]["metaRef"].rsplit("/", 1)[0]
    index = json.loads((unit / "assets/index.json").read_bytes())
    asset = index["assets"][0]
    assert asset["width"] * asset["height"] <= MEDIA_PROCESSING_POLICY.max_publishable_image_pixels
    assert asset["width"] == effective_delivery_width("full", stored_width=_PANORAMA_SIZE[0])
    assert "resize" in asset["derivedModifications"]
    meta = json.loads((unit / "meta.json").read_bytes())
    # 单元身份仍由原件决定：降采样不改变 unit 归属。
    assert meta["rawSha256"] == "sha256:" + hashlib.sha256(body).hexdigest()
