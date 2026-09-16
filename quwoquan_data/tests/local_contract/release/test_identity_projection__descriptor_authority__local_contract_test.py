from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
sys.path.insert(0, str(DATA_ROOT / "scripts"))

from content.release.canonical.final_surface_projection import _apply_required_assets, _projection_identity
from content.release.canonical.object_transaction_contract import ObjectTransactionError
from core import paths

EXECUTION_ID = "20260916--travel-video-republish--contract--pilot-001"
PROCESS_REF = "posts/video/风光/山巅/7"


def _canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _descriptor(root: Path, version: int = 2) -> None:
    expected_current = None if version == 1 else version - 1
    payload = {
        "schema": "quwoquan_data.target_descriptor",
        "processRef": PROCESS_REF,
        "canonicalObjectRef": PROCESS_REF,
        "entityRef": None,
        "entityId": None,
        "expectedCurrentVersion": expected_current,
        "versionAuthority": "initial_create" if expected_current is None else "round_spec.targets.requiredVersion",
        "contentVersion": version,
    }
    descriptor = {**payload, "mappingDigest": "sha256:" + hashlib.sha256(_canonical(payload)).hexdigest()}
    ref = "0.plan/target-descriptors/" + hashlib.sha256(PROCESS_REF.encode()).hexdigest() + ".json"
    raw = _canonical(descriptor)
    (root / ref).parent.mkdir(parents=True)
    (root / ref).write_bytes(raw)
    target_set = {"schema":"quwoquan_data.target_set","executionId":EXECUTION_ID,"carrier":"video","selectionPolicy":"frozen","entityCatalogDigest":"sha256:"+"0"*64,"candidateBinding":{"scope":"output","ref":"input.json","digest":"sha256:"+"1"*64,"candidateCount":1},"targetCount":1,"targetRefs":[PROCESS_REF],"targets":[{"name":"山巅","publishAngle":"风光","publishTitle":"山巅","publishSeq":7}],"targetDescriptors":[{"scope":"execution","ref":ref,"digest":"sha256:"+hashlib.sha256(raw).hexdigest()}]}
    (root / "0.plan").mkdir(exist_ok=True)
    (root / "0.plan/target_set.json").write_bytes(_canonical(target_set))


def test_projection_uses_descriptor_version_not_publish_sequence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / EXECUTION_ID
    _descriptor(root, version=2)
    monkeypatch.setattr(paths, "DATA_EXECUTIONS_ROOT", tmp_path)
    identity = {"schema":"quwoquan_data.draft_identity_binding","contentId":"qwq_data_existing","contentVersion":2,"publishTitle":"保留标题","forbidMint":True,"requiredAssets":[{"role":"embedded","assetId":"asset:video","sha256":"sha256:"+"2"*64,"kind":"video"}]}
    object_dir = root / PROCESS_REF
    (object_dir / "4.draft").mkdir(parents=True)
    (object_dir / "4.draft/identity.json").write_bytes(_canonical(identity))
    content_id, version, title, required_assets = _projection_identity(root, object_dir, PROCESS_REF, {"publishSeq": 7})
    assert (content_id, version, title) == ("qwq_data_existing", 2, "保留标题")
    assert required_assets == identity["requiredAssets"]


def test_projection_rejects_required_version_and_asset_digest_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / EXECUTION_ID
    _descriptor(root, version=2)
    monkeypatch.setattr(paths, "DATA_EXECUTIONS_ROOT", tmp_path)
    with pytest.raises(ObjectTransactionError, match="REQUIRED_VERSION_DRIFT"):
        _projection_identity(root, root / PROCESS_REF, PROCESS_REF, {"requiredVersion": 7, "requiredContentId": "existing"})
    media = tmp_path / "video.mp4"
    media.write_bytes(b"actual")
    with pytest.raises(ObjectTransactionError, match="REQUIRED_ASSET_DRIFT"):
        _apply_required_assets([{"role":"embedded","assetId":"minted","kind":"video","fileName":"assets/video.mp4","sha256":"sha256:"+"0"*64}], {Path("assets/video.mp4"): media}, [{"role":"embedded","assetId":"stable","kind":"video","sha256":"sha256:"+"2"*64}])
