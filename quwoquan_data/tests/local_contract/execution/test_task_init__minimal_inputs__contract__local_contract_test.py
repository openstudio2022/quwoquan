"""task init 只要求一份 round spec：逐 carrier 的 demand/bindings 与机械字段由脚本派生，输入可放任意路径、任意排版。

spec_ref: discovery-content/object-homepage-coverage-scaling/multi-carrier-release/GWT-020
"""
from __future__ import annotations

import copy
import hashlib
import importlib
import json
import os
import sys
from pathlib import Path

import pytest

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from content.execution.task_init import (  # noqa: E402
    ENTITY_CATALOG_SOURCE_REF,
    TaskInitConflict,
    TaskInitError,
    execution_target_ref,
    initialize_round,
    initialize_task,
)
from content.execution.workspace import (  # noqa: E402
    entity_catalog_digest,
    load_frozen_execution_manifest,
    load_frozen_target_set,
)
from core.schema import assert_valid  # noqa: E402
from core import paths  # noqa: E402
from verify.verify_task_init_contract import issues as task_init_issues  # noqa: E402

_HOMEPAGE_ID = "20260906--travel-homepage-minimal--contract--pilot-001"
_IMAGE_ID = "20260906--travel-image-minimal--contract--pilot-001"


@pytest.fixture(autouse=True)
def _symlink_free_output_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # task init 用 O_NOFOLLOW 逐段打开输出根；macOS 的 /var -> /private/var 会被判为 symlink，
    # 因此把隔离根解析成 realpath 再重载 paths（conftest 在测试后恢复隔离根）。
    real_output = Path(os.path.realpath(tmp_path / "output"))
    real_output.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(real_output))
    importlib.reload(paths)


def _write_pretty(path: Path, value: dict) -> Path:
    # 刻意用非 canonical 排版（缩进、键序）证明 init 自行规范化。
    value = copy.deepcopy(value)
    for target in value.get("targets", []):
        target.setdefault("entityRef", "/entity/sanfang-qixiang")
        target.setdefault("entityId", "entity:sanfang-qixiang")
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False), encoding="utf-8")
    return path


def test_one_round_spec_creates_every_declared_carrier_and_derives_mechanical_fields(tmp_path: Path) -> None:
    round_spec = _write_pretty(
        tmp_path / "round.json",
        {
            "schema": "quwoquan_data.round_spec",
            "executions": {"homepage": _HOMEPAGE_ID, "image": _IMAGE_ID},
            "targets": [
                {"carrier": "homepage", "name": "三坊七巷", "entityType": "地点/景区", "region": "中国/福建省/福州市"},
                {"carrier": "image", "name": "三坊七巷", "entityType": "地点/景区", "publishAngle": "街巷", "publishTitle": "三坊七巷夜色"},
            ],
        },
    )

    result = initialize_round(round_spec_path=round_spec)

    assert [row["status"] for row in result["executions"]] == ["created", "created"]
    root = paths.DATA_EXECUTIONS_ROOT / _HOMEPAGE_ID
    request = json.loads((root / "0.plan/request.json").read_text(encoding="utf-8"))
    target_set = json.loads((root / "0.plan/target_set.json").read_text(encoding="utf-8"))
    assert request["quota"] == 1 and request["candidateCount"] == 1
    assert request["familyRef"] == "content/travel/homepage/homepage"
    assert target_set["entityCatalogDigest"] == entity_catalog_digest(ENTITY_CATALOG_SOURCE_REF)
    token = hashlib.sha256(b"/entity/sanfang-qixiang").hexdigest()
    assert target_set["targetRefs"] == [f"entities/地点/景区/entity-{token}"]
    assert target_set["targets"][0]["entityRef"] == "/entity/sanfang-qixiang"
    assert target_set["targets"][0]["entityId"] == "entity:sanfang-qixiang"
    copied = json.loads((root / "0.plan/inputs/candidate_bindings.json").read_text(encoding="utf-8"))
    assert copied["candidateCount"] == 1 and copied["entityCatalogDigest"] == target_set["entityCatalogDigest"]
    assert request["carrierDemand"]["ref"].endswith("0.plan/inputs/carrier_demand.json")
    assert load_frozen_execution_manifest(_HOMEPAGE_ID)["executionId"] == _HOMEPAGE_ID
    assert load_frozen_target_set(_HOMEPAGE_ID) == target_set
    assert task_init_issues(_HOMEPAGE_ID) == []

    image_set = json.loads((paths.DATA_EXECUTIONS_ROOT / _IMAGE_ID / "0.plan/target_set.json").read_text(encoding="utf-8"))
    assert image_set["targetRefs"] == ["posts/image/街巷/三坊七巷夜色/1"]
    assert image_set["targets"][0]["publishSeq"] == 1
    assert task_init_issues(_IMAGE_ID) == []

    # 同样输入重放为 replayed，不产生第二份工作包。
    assert [row["status"] for row in initialize_round(round_spec_path=round_spec)["executions"]] == ["replayed", "replayed"]


def test_homepage_target_without_resolvable_region_fails_at_init(tmp_path: Path) -> None:
    round_spec = _write_pretty(
        tmp_path / "round.json",
        {
            "schema": "quwoquan_data.round_spec",
            "executions": {"homepage": _HOMEPAGE_ID},
            "targets": [{"carrier": "homepage", "name": "不存在之地", "entityType": "地点/景区", "region": "中国/不存在省"}],
        },
    )

    with pytest.raises(TaskInitError, match="region"):
        initialize_round(round_spec_path=round_spec)


def test_round_spec_rejects_carrier_without_execution_or_execution_without_targets(tmp_path: Path) -> None:
    orphan_target = _write_pretty(
        tmp_path / "orphan.json",
        {
            "schema": "quwoquan_data.round_spec",
            "executions": {"homepage": _HOMEPAGE_ID},
            "targets": [{"carrier": "image", "name": "三坊七巷", "entityType": "地点/景区", "publishAngle": "街巷", "publishTitle": "夜色"}],
        },
    )
    with pytest.raises(TaskInitError, match="没有对应 executionId"):
        initialize_round(round_spec_path=orphan_target)

    idle_execution = _write_pretty(
        tmp_path / "idle.json",
        {
            "schema": "quwoquan_data.round_spec",
            "executions": {"homepage": _HOMEPAGE_ID, "image": _IMAGE_ID},
            "targets": [{"carrier": "homepage", "name": "三坊七巷", "entityType": "地点/景区", "region": "中国/福建省/福州市"}],
        },
    )
    with pytest.raises(TaskInitError, match="没有任何 target"):
        initialize_round(round_spec_path=idle_execution)


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-040
@pytest.mark.parametrize("post_carrier", ["article", "image", "video"])
def test_same_name_regions_freeze_distinct_homepages_and_exact_post_bindings(tmp_path: Path, post_carrier: str) -> None:
    post_id = f"20260909--travel-{post_carrier}-identity--contract--pilot-001"
    targets = []
    for sequence, region in enumerate(("中国/浙江省/杭州市", "中国/福建省/福州市"), 1):
        identity = {
            "name": "西湖", "entityType": "地点/景区", "region": region,
            "entityRef": f"/entity/lake-{sequence}", "entityId": f"entity:lake-{sequence}",
        }
        targets.extend([
            {"carrier": "homepage", **identity},
            {"carrier": post_carrier, **identity, "publishAngle": "风景", "publishTitle": "西湖", "publishSeq": sequence},
        ])
    round_spec = _write_pretty(tmp_path / "round.json", {
        "schema": "quwoquan_data.round_spec",
        "executions": {"homepage": _HOMEPAGE_ID, post_carrier: post_id},
        "targets": targets,
    })
    assert all(row["status"] == "created" for row in initialize_round(round_spec_path=round_spec)["executions"])
    homepage_set = load_frozen_target_set(_HOMEPAGE_ID)
    post_set = load_frozen_target_set(post_id)
    assert len(set(homepage_set["targetRefs"])) == 2
    assert all("中国" not in ref and "西湖" not in ref for ref in homepage_set["targetRefs"])
    for execution_id, target_set in ((_HOMEPAGE_ID, homepage_set), (post_id, post_set)):
        root = paths.DATA_EXECUTIONS_ROOT / execution_id
        bindings = json.loads((root / "0.plan/inputs/candidate_bindings.json").read_bytes())
        manifest = load_frozen_execution_manifest(execution_id)
        assert bindings["targets"] == target_set["targets"]
        assert manifest["submittedInputs"]["immutableCandidateBindings"] == bindings
        assert task_init_issues(execution_id) == []
        assert [execution_target_ref(target, carrier=target_set["carrier"]) for target in bindings["targets"]] == target_set["targetRefs"]
        assert {t["region"]: (t["entityRef"], t["entityId"]) for t in target_set["targets"]} == {
            "中国/浙江省/杭州市": ("/entity/lake-1", "entity:lake-1"),
            "中国/福建省/福州市": ("/entity/lake-2", "entity:lake-2"),
        }
    # 目标顺序不参与身份；两个载体重放保持 exact bytes。
    document = json.loads(round_spec.read_bytes())
    document["targets"].reverse()
    _write_pretty(round_spec, document)
    assert all(row["status"] == "replayed" for row in initialize_round(round_spec_path=round_spec)["executions"])


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-023
@pytest.mark.parametrize("field", ["entityRef", "entityId"])
def test_new_round_and_candidate_schema_reject_missing_identity(tmp_path: Path, field: str) -> None:
    target = {"name": "西湖", "entityType": "地点/景区", "region": "中国/浙江省/杭州市", "entityRef": "/entity/lake", "entityId": "entity:lake"}
    target.pop(field)
    bindings = {"schema": "quwoquan_data.immutable_candidate_bindings", "executionId": _HOMEPAGE_ID, "carrier": "homepage", "targets": [target]}
    with pytest.raises(ValueError, match=field):
        assert_valid(bindings, "execution", "immutable_candidate_bindings")
    # 不经测试构造器补值，以实际 init 输入验证硬切。
    round_path = tmp_path / "missing.json"
    round_path.write_text(json.dumps({"schema": "quwoquan_data.round_spec", "executions": {"homepage": _HOMEPAGE_ID}, "targets": [{"carrier": "homepage", **target}]}), encoding="utf-8")
    with pytest.raises(ValueError, match=field):
        initialize_round(round_spec_path=round_path)
    assert not (paths.DATA_EXECUTIONS_ROOT / _HOMEPAGE_ID).exists()


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-024
@pytest.mark.parametrize("conflict", ["entityId", "entityRef", "entityType", "region", "duplicate"])
def test_identity_conflicts_fail_before_any_execution_write(tmp_path: Path, conflict: str) -> None:
    first = {"carrier": "homepage", "name": "西湖", "entityType": "地点/景区", "region": "中国/浙江省/杭州市", "entityRef": "/entity/lake", "entityId": "entity:lake"}
    second = dict(first)
    if conflict != "duplicate":
        second[conflict] = {"entityId": "entity:other", "entityRef": "/entity/other", "entityType": "地点/公园", "region": "中国/福建省/福州市"}[conflict]
    round_path = _write_pretty(tmp_path / "conflict.json", {"schema": "quwoquan_data.round_spec", "executions": {"homepage": _HOMEPAGE_ID}, "targets": [first, second]})
    with pytest.raises(TaskInitError, match="DATA.EXECUTION.TARGET_IDENTITY_CONFLICT|targetRef 重复"):
        initialize_round(round_spec_path=round_path)
    assert not (paths.DATA_EXECUTIONS_ROOT / _HOMEPAGE_ID).exists()


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-040
def test_candidate_entry_preserves_opaque_identity_and_ignores_publish_location(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    demand = _write_pretty(tmp_path / "demand.json", {"schema": "quwoquan_data.carrier_demand", "executionId": _HOMEPAGE_ID, "carrier": "homepage", "familyRef": "content/travel/homepage/homepage"})
    # 既有路径形状 ref 也是 opaque 值，不能重新编码成新 ID。
    bindings = _write_pretty(tmp_path / "bindings.json", {"schema": "quwoquan_data.immutable_candidate_bindings", "executionId": _HOMEPAGE_ID, "carrier": "homepage", "targets": [{"name": "西湖", "entityType": "地点/景区", "region": "中国/浙江省/杭州市", "entityRef": "/entity/地点/景区/西湖", "entityId": "entity:old-lake-id"}]})
    assert initialize_task(carrier_demand_path=demand, candidate_bindings_path=bindings)["status"] == "created"
    frozen = load_frozen_target_set(_HOMEPAGE_ID)
    assert frozen["targets"][0]["entityRef"] == "/entity/地点/景区/西湖"
    assert frozen["targets"][0]["entityId"] == "entity:old-lake-id"
    monkeypatch.setattr(paths, "PUBLISH_ROOT", tmp_path / "missing-publish-tree")
    assert initialize_task(carrier_demand_path=demand, candidate_bindings_path=bindings)["status"] == "replayed"
    # 同一显式身份移到新 execution、修正地域和名称，不改变身份或目录叶子。
    new_id = _HOMEPAGE_ID.replace("pilot-001", "pilot-002")
    demand_doc = json.loads(demand.read_bytes())
    candidate_doc = json.loads(bindings.read_bytes())
    demand_doc["executionId"] = candidate_doc["executionId"] = new_id
    candidate_doc["targets"][0].update(region="中国/福建省/福州市", name="西湖公园")
    _write_pretty(demand, demand_doc)
    _write_pretty(bindings, candidate_doc)
    assert initialize_task(carrier_demand_path=demand, candidate_bindings_path=bindings)["status"] == "created"
    moved = load_frozen_target_set(new_id)
    assert moved["targetRefs"] == frozen["targetRefs"]
    assert moved["targets"][0]["entityRef"] == frozen["targets"][0]["entityRef"]
    assert moved["targets"][0]["entityId"] == frozen["targets"][0]["entityId"]
    assert execution_target_ref(moved["targets"][0], carrier="homepage") == frozen["targetRefs"][0]
    assert task_init_issues(new_id) == []


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-024
@pytest.mark.parametrize("entity_ref", ["/entity/", "/entity//", "/entity/../x", "/entity/x/..", "/entity/x\x00", " /entity/x"])
def test_round_schema_rejects_invalid_explicit_reference(tmp_path: Path, entity_ref: str) -> None:
    round_path = _write_pretty(tmp_path / "invalid.json", {"schema": "quwoquan_data.round_spec", "executions": {"homepage": _HOMEPAGE_ID}, "targets": [{"carrier": "homepage", "name": "西湖", "entityType": "地点/景区", "region": "中国/浙江省/杭州市", "entityRef": entity_ref}]})
    with pytest.raises(ValueError, match="entityRef"):
        initialize_round(round_spec_path=round_path)
    assert not (paths.DATA_EXECUTIONS_ROOT / _HOMEPAGE_ID).exists()


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-024
def test_cross_carrier_identity_conflict_is_rejected_before_creating_homepage(tmp_path: Path) -> None:
    round_path = _write_pretty(tmp_path / "conflict.json", {"schema": "quwoquan_data.round_spec", "executions": {"homepage": _HOMEPAGE_ID, "image": _IMAGE_ID}, "targets": [
        {"carrier": "homepage", "name": "西湖", "entityType": "地点/景区", "region": "中国/浙江省/杭州市", "entityRef": "/entity/lake", "entityId": "entity:lake"},
        {"carrier": "image", "name": "西湖", "entityType": "地点/景区", "entityRef": "/entity/lake", "entityId": "entity:different", "publishAngle": "风景", "publishTitle": "西湖"},
    ]})
    with pytest.raises(TaskInitError, match="DATA.EXECUTION.TARGET_IDENTITY_CONFLICT"):
        initialize_round(round_spec_path=round_path)
    assert not (paths.DATA_EXECUTIONS_ROOT / _HOMEPAGE_ID).exists()
    assert not (paths.DATA_EXECUTIONS_ROOT / _IMAGE_ID).exists()


# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-041
def test_legacy_frozen_inputs_and_receipt_are_never_rewritten(tmp_path: Path) -> None:
    root = paths.DATA_EXECUTIONS_ROOT / _HOMEPAGE_ID
    (root / "0.plan").mkdir(parents=True)
    receipt = root / "_shared/receipts/001-1.download.json"
    receipt.parent.mkdir(parents=True)
    old = {
        root / "execution_manifest.json": b'{"legacy":true}\n',
        root / "0.plan/target_set.json": b'{ "targets": [{"name":"old"}] }\n',
        receipt: b'{"schema":"historical.receipt", "verdict":"pass"}\n',
    }
    for path, raw in old.items():
        path.write_bytes(raw)
    round_path = _write_pretty(tmp_path / "legacy.json", {"schema": "quwoquan_data.round_spec", "executions": {"homepage": _HOMEPAGE_ID}, "targets": [{"carrier": "homepage", "name": "西湖", "entityType": "地点/景区", "region": "中国/浙江省/杭州市"}]})
    with pytest.raises(TaskInitConflict, match="内容不同"):
        initialize_round(round_spec_path=round_path)
    assert {path: path.read_bytes() for path in old} == old
    with pytest.raises(ValueError):
        load_frozen_target_set(_HOMEPAGE_ID)
    assert {path: path.read_bytes() for path in old} == old
