# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-037.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-037.t2
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-037.t3
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-037.t4
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-037.t5
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-037.t6
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-037.t7
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-037.t8
"""task acquire 是零网络 ingest：只从 AI 已下载的本地字节与申报事实派生硬事实。

全程在 socket 被禁用的环境下运行；任何出网尝试都会让测试直接失败。
"""
from __future__ import annotations

import hashlib
import io
import json
import re
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

EXECUTION_ID = "20260906--travel-image-six-step--ingest--pilot-001"
TARGET_A = "posts/image/风光/云和梯田全景/1"
TARGET_B = "posts/image/风光/云和梯田瀑布/1"
FILE_PAGE = "https://commons.wikimedia.org/wiki/File:云和梯田.jpg"
DIRECT_URL = "https://upload.wikimedia.org/wikipedia/commons/6/6c/%E4%BA%91%E5%92%8C%E6%A2%AF%E7%94%B0.jpg"


def _canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _write(path: Path, data: bytes | str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    return path


def _png(color: tuple[int, int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), color).save(buffer, "PNG")
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _refuse(*_args, **_kwargs):
        raise AssertionError("task acquire 不得发起任何网络连接")

    monkeypatch.setattr(socket, "socket", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)
    monkeypatch.setattr(socket, "getaddrinfo", _refuse)


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
        "candidateBinding": {"scope": "output", "ref": "x.json", "digest": "sha256:" + "1" * 64, "candidateCount": 2},
        "targetCount": 2, "targetRefs": [TARGET_A, TARGET_B],
        "targets": [
            {"name": "云和梯田", "entityType": "地点/景区", "publishAngle": "风光", "publishTitle": "云和梯田全景", "publishSeq": 1},
            {"name": "云和梯田", "entityType": "地点/景区", "publishAngle": "风光", "publishTitle": "云和梯田瀑布", "publishSeq": 1},
        ],
    }))
    return root


def _media_source(file_path: Path, body: bytes, **overrides) -> dict:
    source = {
        "kind": "image",
        "sourceUrl": FILE_PAGE,
        "directUrl": DIRECT_URL,
        "filePath": str(file_path),
        "sha1": hashlib.sha1(body).hexdigest(),
        "license": "CC BY-SA 4.0",
        "licenseUrl": "https://creativecommons.org/licenses/by-sa/4.0",
        "creator": "唐代吉",
        "description": "云和梯田的层叠全景",
        "relevance": "实体本身的全景图",
        "watermarkStatus": "absent",
        "watermarkKind": "none",
    }
    source.update(overrides)
    return source


def _manifest(path: Path, targets: list[dict]) -> Path:
    return _write(path, _canonical({"schema": "quwoquan_data.ingest_manifest", "executionId": EXECUTION_ID, "targets": targets}))


def test_ingest_derives_hard_facts_from_local_bytes_without_network(execution: Path, tmp_path: Path) -> None:
    body = _png((200, 30, 30))
    image = _write(tmp_path / "downloads/yunhe.png", body)
    manifest = _manifest(tmp_path / "ingest.json", [{"targetRef": TARGET_A, "sources": [_media_source(image, body)]}])

    result = acquire_module.acquire(execution_id=EXECUTION_ID, request_path=manifest)

    assert result["ingested"] == 1 and result["failed"] == 0
    row = result["targets"][0]
    assert row["status"] == "ingested" and row["sources"][0]["rightsStatus"] == "verified"
    assert row["sources"][0]["watermarkStatus"] == "absent"
    refs = json.loads((execution / TARGET_A / "1.download/source_refs.json").read_bytes())
    assert len(refs["sources"]) == 1
    unit = execution / refs["sources"][0]["metaRef"].rsplit("/", 1)[0]
    meta = json.loads((unit / "meta.json").read_bytes())
    assert meta["acquisition"]["contentSha256"] == "sha256:" + hashlib.sha256(body).hexdigest()
    index = json.loads((unit / "assets/index.json").read_bytes())
    asset = index["assets"][0]
    assert asset["mimeType"] == "image/png" and (asset["width"], asset["height"]) == (64, 48)
    assert asset["sha256"] == meta["acquisition"]["contentSha256"]
    assert asset["watermarkStatus"] == "absent" and asset["watermarkKind"] == "none"
    assert asset["derivedModifications"] == []
    assert asset["sourceAttribution"]["watermarkStatus"] == "absent"
    assert asset["sourceAttribution"]["modelReleaseStatus"] == "unverified"
    assert asset["sourceAttribution"]["authorizationProofUrl"] is None
    assert asset["authorizationProof"] == "" and asset["authorizationRequired"] is True
    linked = unit / "assets" / asset["fileName"]
    library = tmp_path / "content_library"
    assert linked.read_bytes() == body
    assert any(candidate.read_bytes() == body for candidate in library.rglob("*") if candidate.is_file())


def test_source_side_has_no_network_egress() -> None:
    egress = re.compile(r"urllib\.request|urlopen|http\.client|import requests|import socket|\bcurl\b|aiohttp|httpx")
    offenders = []
    for root in (SCRIPTS_ROOT / "content/source", SCRIPTS_ROOT / "content/execution", SCRIPTS_ROOT / "core"):
        for path in root.rglob("*.py"):
            if egress.search(path.read_text(encoding="utf-8")):
                offenders.append(path.relative_to(SCRIPTS_ROOT).as_posix())
    assert offenders == [], offenders


def test_sha1_drift_fails_only_that_target(execution: Path, tmp_path: Path) -> None:
    good = _png((10, 200, 10))
    bad = _png((10, 10, 200))
    good_path = _write(tmp_path / "downloads/good.png", good)
    bad_path = _write(tmp_path / "downloads/bad.png", bad)
    manifest = _manifest(tmp_path / "ingest.json", [
        {"targetRef": TARGET_A, "sources": [_media_source(good_path, good)]},
        {"targetRef": TARGET_B, "sources": [_media_source(bad_path, bad, sha1="0" * 40)]},
    ])

    result = acquire_module.acquire(execution_id=EXECUTION_ID, request_path=manifest)

    assert result["ingested"] == 1 and result["failed"] == 1
    by_ref = {row["targetRef"]: row for row in result["targets"]}
    assert by_ref[TARGET_A]["status"] == "ingested"
    assert by_ref[TARGET_B]["status"] == "failed"
    assert by_ref[TARGET_B]["issue"]["code"] == "DATA.ACQUIRE.SOURCE_SHA1_DRIFT"
    assert (execution / TARGET_A / "1.download/source_refs.json").is_file()
    assert not (execution / TARGET_B / "1.download/source_refs.json").exists()


def test_missing_rights_fields_are_schema_rejected_not_defaulted(execution: Path, tmp_path: Path) -> None:
    body = _png((1, 2, 3))
    image = _write(tmp_path / "downloads/x.png", body)
    source = _media_source(image, body)
    del source["licenseUrl"]
    manifest = _manifest(tmp_path / "ingest.json", [{"targetRef": TARGET_A, "sources": [source]}])
    with pytest.raises(ValueError):
        acquire_module.acquire(execution_id=EXECUTION_ID, request_path=manifest)
    assert not (execution / TARGET_A / "1.download").exists()


@pytest.mark.parametrize("rights_status", ["verified", "unverified", "restricted", "unknown"])
def test_declared_rights_are_preserved_without_authorization_upgrade(execution: Path, tmp_path: Path, rights_status: str) -> None:
    body = _png((9, 9, 9))
    image = _write(tmp_path / "downloads/x.png", body)
    declared = _media_source(
        image, body, rightsStatus=rights_status, rightsIssues=["授权范围待核实"],
        license="CC BY-NC 4.0", licenseUrl="https://creativecommons.org/licenses/by-nc/4.0",
        usageScope="internal_reference", modelReleaseStatus="editorial_only",
        propertyReleaseStatus="unverified", audioRightsStatus="unverified",
        authorizationProof=None, commercialAuthorizationStatus="unverified",
    )
    manifest = _manifest(tmp_path / "declared.json", [{"targetRef": TARGET_A, "sources": [declared]}])
    result = acquire_module.acquire(execution_id=EXECUTION_ID, request_path=manifest)
    assert result["ingested"] == 1 and result["failed"] == 0
    refs = json.loads((execution / TARGET_A / "1.download/source_refs.json").read_bytes())
    unit = execution / refs["sources"][0]["metaRef"].rsplit("/", 1)[0]
    asset = json.loads((unit / "assets/index.json").read_bytes())["assets"][0]
    assert asset["rightsStatus"] == rights_status
    assert asset["rightsIssues"] == ["授权范围待核实"]
    assert asset["usageScope"] == "internal_reference"
    assert asset["license"] == "CC BY-NC 4.0"
    assert asset["distributionDecision"] == "production_allowed"
    assert asset["authorizationProof"] == "" and asset["authorizationRequired"] is True
    attribution = asset["sourceAttribution"]
    assert attribution["publicationAdmission"] == "production_release"
    assert attribution["authorizationProofUrl"] is None
    assert attribution["commercialAuthorizationStatus"] == "unverified"
    assert attribution["audioRightsStatus"] == "unverified"
    assert attribution["modelReleaseStatus"] == "editorial_only"
    assert attribution["propertyReleaseStatus"] == "unverified"


def test_watermark_fields_are_transcribed_and_present_requires_kind_and_note(execution: Path, tmp_path: Path) -> None:
    body = _png((77, 77, 77))
    image = _write(tmp_path / "downloads/x.png", body)
    incomplete = _media_source(image, body, watermarkStatus="present", watermarkKind="none")
    manifest = _manifest(tmp_path / "incomplete.json", [{"targetRef": TARGET_A, "sources": [incomplete]}])
    with pytest.raises(ValueError):
        acquire_module.acquire(execution_id=EXECUTION_ID, request_path=manifest)

    signed = _media_source(image, body, watermarkStatus="present", watermarkKind="author_signature", watermarkNote="右下角手写签名")
    manifest = _manifest(tmp_path / "signed.json", [{"targetRef": TARGET_A, "sources": [signed]}])
    result = acquire_module.acquire(execution_id=EXECUTION_ID, request_path=manifest)
    refs = json.loads((execution / TARGET_A / "1.download/source_refs.json").read_bytes())
    unit = execution / refs["sources"][0]["metaRef"].rsplit("/", 1)[0]
    asset = json.loads((unit / "assets/index.json").read_bytes())["assets"][0]
    assert result["targets"][0]["sources"][0]["watermarkStatus"] == "present"
    assert asset["watermarkKind"] == "author_signature" and asset["watermarkNote"] == "右下角手写签名"
    assert asset["sourceAttribution"]["watermarkKind"] == "author_signature"


def test_page_source_takes_agent_written_markdown(execution: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    article_id = "20260906--travel-article-six-step--ingest--pilot-001"
    article_ref = "posts/article/风光/云和梯田：千层田/1"
    root = paths.DATA_EXECUTIONS_ROOT / article_id
    _write(root / "execution_manifest.json", _canonical({"schema": "quwoquan_data.content_execution_manifest", "executionId": article_id}))
    _write(root / "0.plan/target_set.json", _canonical({
        "schema": "quwoquan_data.target_set", "executionId": article_id, "carrier": "article", "selectionPolicy": "frozen",
        "entityCatalogDigest": "sha256:" + "0" * 64,
        "candidateBinding": {"scope": "output", "ref": "x.json", "digest": "sha256:" + "1" * 64, "candidateCount": 1},
        "targetCount": 1, "targetRefs": [article_ref],
        "targets": [{"name": "云和梯田", "entityType": "地点/景区", "publishAngle": "风光", "publishTitle": "云和梯田：千层田", "publishSeq": 1}],
    }))
    source_md = _write(tmp_path / "downloads/yunhe.source.md", "# 云和梯田\n\n云和梯田位于浙江丽水云和县。\n\n## 信息区\n\n- 海拔：200–1400 米\n")
    manifest = _write(tmp_path / "ingest.json", _canonical({
        "schema": "quwoquan_data.ingest_manifest", "executionId": article_id,
        "targets": [{"targetRef": article_ref, "sources": [{
            "kind": "page", "sourceUrl": "https://zh.wikipedia.org/wiki/云和梯田", "title": "云和梯田",
            "sourceMarkdownPath": str(source_md), "license": "CC BY-SA 4.0",
            "licenseUrl": "https://creativecommons.org/licenses/by-sa/4.0/", "creator": "云和梯田条目贡献者",
            "revisionId": 123, "relevance": "文章事实来源",
        }]}],
    }))

    result = acquire_module.acquire(execution_id=article_id, request_path=manifest)

    assert result["ingested"] == 1
    refs = json.loads((root / article_ref / "1.download/source_refs.json").read_bytes())
    unit = root / refs["sources"][0]["metaRef"].rsplit("/", 1)[0]
    assert (unit / "source.md").read_text(encoding="utf-8") == source_md.read_text(encoding="utf-8")
    meta = json.loads((unit / "meta.json").read_bytes())
    assert meta["sourceClass"] == "encyclopedia" and meta["sourceUseMode"] == "factual_reference_only"
    assert meta["rawSha256"] == "sha256:" + hashlib.sha256(source_md.read_bytes()).hexdigest()


@pytest.mark.skipif(__import__("shutil").which("ffmpeg") is None or __import__("shutil").which("ffprobe") is None, reason="ffmpeg/ffprobe not on PATH")
def test_transcoded_video_replay_keeps_one_source_unit_per_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """派生体（转码）字节逐次不同，但 unit 身份必须由下载原件决定：同一清单重放不得为同一 target 再生成第二个 unit。"""
    import subprocess

    video_id = "20260906--travel-video-six-step--ingest--pilot-001"
    video_ref = "posts/video/风光/云和梯田航拍/1"
    root = paths.DATA_EXECUTIONS_ROOT / video_id
    _write(root / "execution_manifest.json", _canonical({"schema": "quwoquan_data.content_execution_manifest", "executionId": video_id}))
    _write(root / "0.plan/target_set.json", _canonical({
        "schema": "quwoquan_data.target_set", "executionId": video_id, "carrier": "video", "selectionPolicy": "frozen",
        "entityCatalogDigest": "sha256:" + "0" * 64,
        "candidateBinding": {"scope": "output", "ref": "x.json", "digest": "sha256:" + "1" * 64, "candidateCount": 1},
        "targetCount": 1, "targetRefs": [video_ref],
        "targets": [{"name": "云和梯田", "entityType": "地点/景区", "publishAngle": "风光", "publishTitle": "云和梯田航拍", "publishSeq": 1}],
    }))
    source = tmp_path / "downloads/source.mpg"
    source.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=24:duration=2", "-c:v", "mpeg1video", "-q:v", "4", str(source)], check=True, capture_output=True)
    body = source.read_bytes()
    manifest = _write(tmp_path / "video.json", _canonical({"schema": "quwoquan_data.ingest_manifest", "executionId": video_id, "targets": [{"targetRef": video_ref, "sources": [{
        "kind": "video", "sourceUrl": "https://commons.wikimedia.org/wiki/File:Yunhe.mpg", "directUrl": "https://upload.wikimedia.org/wikipedia/commons/1/11/Yunhe.mpg",
        "filePath": str(source), "sha1": hashlib.sha1(body).hexdigest(), "license": "CC BY-SA 4.0", "licenseUrl": "https://creativecommons.org/licenses/by-sa/4.0",
        "creator": "唐代吉", "description": "云和梯田航拍", "relevance": "实体实景", "hasAudio": False, "watermarkStatus": "unknown", "watermarkKind": "unknown",
    }]}]}))
    first = acquire_module.acquire(execution_id=video_id, request_path=manifest)
    assert first["ingested"] == 1
    refs_path = root / video_ref / "1.download/source_refs.json"
    before = json.loads(refs_path.read_bytes())
    assert len(before["sources"]) == 1
    unit = root / before["sources"][0]["metaRef"].rsplit("/", 1)[0]
    meta = json.loads((unit / "meta.json").read_bytes())
    assert meta["rawSha256"] == "sha256:" + hashlib.sha256(body).hexdigest(), "unit 身份取下载原件摘要"
    asset = json.loads((unit / "assets/index.json").read_bytes())["assets"][0]
    assert asset["mimeType"] == "video/mp4" and asset["derivativeBinding"]["originalSha256"] == meta["rawSha256"]

    second = acquire_module.acquire(execution_id=video_id, request_path=manifest)
    assert second["ingested"] == 1
    after = json.loads(refs_path.read_bytes())
    assert after == before, "重放不得为同一 target 追加第二个 source unit"
    assert len([p for p in (root / "sources").iterdir() if p.name.startswith("wikimedia_commons_video__")]) == 1


def test_replay_is_byte_identical_and_library_deduplicates_across_executions(execution: Path, tmp_path: Path) -> None:
    body = _png((5, 6, 7))
    image = _write(tmp_path / "downloads/x.png", body)
    manifest = _manifest(tmp_path / "ingest.json", [{"targetRef": TARGET_A, "sources": [_media_source(image, body)]}])
    first = acquire_module.acquire(execution_id=EXECUTION_ID, request_path=manifest)
    refs_path = execution / TARGET_A / "1.download/source_refs.json"
    before = refs_path.read_bytes()
    unit = execution / json.loads(before)["sources"][0]["metaRef"].rsplit("/", 1)[0]
    meta_before = (unit / "meta.json").read_bytes()

    second = acquire_module.acquire(execution_id=EXECUTION_ID, request_path=manifest)

    assert second["targets"][0]["sources"][0]["sourceUnitId"] == first["targets"][0]["sources"][0]["sourceUnitId"]
    assert refs_path.read_bytes() == before and (unit / "meta.json").read_bytes() == meta_before

    # 同一字节在另一个 execution 里 ingest，content library 仍只持有一份。
    other_id = "20260906--travel-image-six-step--ingest--pilot-002"
    other_root = paths.DATA_EXECUTIONS_ROOT / other_id
    _write(other_root / "execution_manifest.json", _canonical({"schema": "quwoquan_data.content_execution_manifest", "executionId": other_id}))
    _write(other_root / "0.plan/target_set.json", _canonical({
        "schema": "quwoquan_data.target_set", "executionId": other_id, "carrier": "image", "selectionPolicy": "frozen",
        "entityCatalogDigest": "sha256:" + "0" * 64,
        "candidateBinding": {"scope": "output", "ref": "x.json", "digest": "sha256:" + "1" * 64, "candidateCount": 1},
        "targetCount": 1, "targetRefs": [TARGET_B],
        "targets": [{"name": "云和梯田", "entityType": "地点/景区", "publishAngle": "风光", "publishTitle": "云和梯田瀑布", "publishSeq": 1}],
    }))
    other_manifest = _write(tmp_path / "other.json", _canonical({"schema": "quwoquan_data.ingest_manifest", "executionId": other_id, "targets": [{"targetRef": TARGET_B, "sources": [_media_source(image, body)]}]}))
    acquire_module.acquire(execution_id=other_id, request_path=other_manifest)
    library = tmp_path / "content_library"
    holders = [candidate for candidate in library.rglob("*") if candidate.is_file() and candidate.read_bytes() == body]
    assert len(holders) == 1
