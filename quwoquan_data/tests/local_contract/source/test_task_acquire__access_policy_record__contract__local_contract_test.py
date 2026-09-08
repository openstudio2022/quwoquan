# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-037.t12
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-037.t13
"""accessPolicy 只记录不阻断：来源行申报的站点 robots/ToS 态度原样进入 meta.json 与资产行，
闭集外取值被 schema 拒绝；未申报的来源行不含该字段，也不被补为 open。"""
from __future__ import annotations

import hashlib
import io
import json
import socket
import sys
from pathlib import Path

import pytest
from PIL import Image

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from content.source import acquire as acquire_module  # noqa: E402
from core import paths  # noqa: E402

EXECUTION_ID = "20260908--travel-image-six-step--ingest--pilot-003"
TARGET_A = "posts/image/风光/稻城亚丁牛奶海/1"
TARGET_B = "posts/image/风光/稻城亚丁五色海/1"
TARGET_PAGE = "posts/image/风光/稻城亚丁央迈勇/1"


def _canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _write(path: Path, data: bytes | str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    return path


def _jpeg(color: tuple[int, int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), color).save(buffer, "JPEG")
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _refuse(*_args, **_kwargs):
        raise AssertionError("task acquire 不得发起任何网络连接")

    monkeypatch.setattr(socket, "socket", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)


@pytest.fixture()
def execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    tasks = tmp_path / "data/tasks"
    monkeypatch.setattr(paths, "DATA_EXECUTIONS_ROOT", tasks)
    monkeypatch.delenv("QWQ_LIBRARY_ROOT", raising=False)
    root = tasks / EXECUTION_ID
    _write(root / "execution_manifest.json", _canonical({"schema": "quwoquan_data.content_execution_manifest", "executionId": EXECUTION_ID}))
    _write(root / "0.plan/target_set.json", _canonical({
        "schema": "quwoquan_data.target_set", "executionId": EXECUTION_ID, "carrier": "image",
        "selectionPolicy": "frozen", "entityCatalogDigest": "sha256:" + "0" * 64,
        "candidateBinding": {"scope": "output", "ref": "x.json", "digest": "sha256:" + "1" * 64, "candidateCount": 3},
        "targetCount": 3, "targetRefs": [TARGET_A, TARGET_B, TARGET_PAGE],
        "targets": [
            {"name": "稻城亚丁", "entityType": "地点/景区", "publishAngle": "风光", "publishTitle": "稻城亚丁牛奶海", "publishSeq": 1},
            {"name": "稻城亚丁", "entityType": "地点/景区", "publishAngle": "风光", "publishTitle": "稻城亚丁五色海", "publishSeq": 1},
            {"name": "稻城亚丁", "entityType": "地点/景区", "publishAngle": "风光", "publishTitle": "稻城亚丁央迈勇", "publishSeq": 1},
        ],
    }))
    return root


def _tuchong_source(file_path: Path, body: bytes, **overrides) -> dict:
    source = {
        "kind": "image",
        "sourceUrl": "https://tuchong.com/1234567/98765432/",
        "directUrl": "https://photo.tuchong.com/1234567/f/98765432.jpg",
        "filePath": str(file_path),
        "license": "图虫用户协议（版权保留）",
        "licenseUrl": "https://tuchong.com/agreement/",
        "creator": "某摄影师（https://tuchong.com/1234567/）",
        "description": "牛奶海秋色",
        "relevance": "图片作品本体：主会话已目视",
        "watermarkStatus": "absent",
        "watermarkKind": "none",
    }
    source.update(overrides)
    return source


def _manifest(path: Path, targets: list[dict]) -> Path:
    return _write(path, _canonical({"schema": "quwoquan_data.ingest_manifest", "executionId": EXECUTION_ID, "targets": targets}))


def _unit_of(execution: Path, target: str) -> Path:
    refs = json.loads((execution / target / "1.download/source_refs.json").read_bytes())
    return execution / refs["sources"][0]["metaRef"].rsplit("/", 1)[0]


def test_declared_access_policy_is_transcribed_and_absent_stays_absent(execution: Path, tmp_path: Path) -> None:
    restricted_body = _jpeg((200, 30, 30))
    plain_body = _jpeg((30, 200, 30))
    restricted = _write(tmp_path / "downloads/restricted.jpg", restricted_body)
    plain = _write(tmp_path / "downloads/plain.jpg", plain_body)
    manifest = _manifest(tmp_path / "ingest.json", [
        {"targetRef": TARGET_A, "sources": [_tuchong_source(restricted, restricted_body, accessPolicy="tos_restricted")]},
        {"targetRef": TARGET_B, "sources": [_tuchong_source(plain, plain_body)]},
    ])

    result = acquire_module.acquire(execution_id=EXECUTION_ID, request_path=manifest)
    assert result["ingested"] == 2 and result["failed"] == 0, result

    restricted_unit = _unit_of(execution, TARGET_A)
    meta = json.loads((restricted_unit / "meta.json").read_bytes())
    asset = json.loads((restricted_unit / "assets/index.json").read_bytes())["assets"][0]
    assert meta["accessPolicy"] == "tos_restricted"
    assert asset["accessPolicy"] == "tos_restricted"
    # 权利仍按 license 白名单派生，accessPolicy 不改变它，也不阻断入池。
    assert asset["rightsStatus"] == "unverified" and asset["authorizationRequired"] is True

    plain_unit = _unit_of(execution, TARGET_B)
    plain_meta = json.loads((plain_unit / "meta.json").read_bytes())
    plain_asset = json.loads((plain_unit / "assets/index.json").read_bytes())["assets"][0]
    assert "accessPolicy" not in plain_meta
    assert "accessPolicy" not in plain_asset


def test_access_policy_outside_closed_set_is_schema_rejected(execution: Path, tmp_path: Path) -> None:
    body = _jpeg((1, 2, 3))
    image = _write(tmp_path / "downloads/x.jpg", body)
    manifest = _manifest(tmp_path / "bad.json", [
        {"targetRef": TARGET_A, "sources": [_tuchong_source(image, body, accessPolicy="paywalled")]},
    ])
    with pytest.raises(ValueError):
        acquire_module.acquire(execution_id=EXECUTION_ID, request_path=manifest)
    assert not (execution / TARGET_A / "1.download").exists()


def test_page_source_access_policy_lands_in_unit_meta(execution: Path, tmp_path: Path) -> None:
    page = _write(tmp_path / "sources/mafengwo.source.md", "# 稻城亚丁三日徒步\n\n第一天从亚丁村出发……\n")
    manifest = _manifest(tmp_path / "page.json", [
        {"targetRef": TARGET_PAGE, "sources": [{
            "kind": "page",
            "sourceUrl": "https://www.mafengwo.cn/i/12345678.html",
            "title": "稻城亚丁三日徒步",
            "sourceMarkdownPath": str(page),
            "license": "马蜂窝用户协议（版权保留）",
            "licenseUrl": "https://www.mafengwo.cn/about/terms.html",
            "creator": "某游记作者",
            "relevance": "文章事实参考（factual_reference_only）",
            "accessPolicy": "robots_disallowed",
        }]},
    ])

    result = acquire_module.acquire(execution_id=EXECUTION_ID, request_path=manifest)
    assert result["ingested"] == 1, result
    meta = json.loads((_unit_of(execution, TARGET_PAGE) / "meta.json").read_bytes())
    assert meta["accessPolicy"] == "robots_disallowed"
    assert meta["sourceClass"] == "web_page"
