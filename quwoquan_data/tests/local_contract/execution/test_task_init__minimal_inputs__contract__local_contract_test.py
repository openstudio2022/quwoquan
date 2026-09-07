"""task init 只要求一份 round spec：逐 carrier 的 demand/bindings 与机械字段由脚本派生，输入可放任意路径、任意排版。

spec_ref: discovery-content/object-homepage-coverage-scaling/multi-carrier-release/GWT-020
"""
from __future__ import annotations

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
    TaskInitError,
    initialize_round,
)
from content.execution.workspace import entity_catalog_digest  # noqa: E402
from core import paths  # noqa: E402
from verify.verify_task_init_contract import issues as task_init_issues  # noqa: E402

_HOMEPAGE_ID = "20260906--travel-homepage-minimal--contract--pilot-001"
_IMAGE_ID = "20260906--travel-image-minimal--contract--pilot-001"


@pytest.fixture(autouse=True)
def _symlink_free_output_root(monkeypatch: pytest.MonkeyPatch) -> None:
    # task init 用 O_NOFOLLOW 逐段打开输出根；macOS 的 /var -> /private/var 会被判为 symlink，
    # 因此把隔离根解析成 realpath 再重载 paths（conftest 在测试后恢复隔离根）。
    real_output = Path(os.path.realpath(paths.OUTPUT_ROOT))
    real_output.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(real_output))
    importlib.reload(paths)


def _write_pretty(path: Path, value: dict) -> Path:
    # 刻意用非 canonical 排版（缩进、键序）证明 init 自行规范化。
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
    assert target_set["targetRefs"] == ["entities/地点/景区/三坊七巷"]
    copied = json.loads((root / "0.plan/inputs/candidate_bindings.json").read_text(encoding="utf-8"))
    assert copied["candidateCount"] == 1 and copied["entityCatalogDigest"] == target_set["entityCatalogDigest"]
    assert request["carrierDemand"]["ref"].endswith("0.plan/inputs/carrier_demand.json")
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
