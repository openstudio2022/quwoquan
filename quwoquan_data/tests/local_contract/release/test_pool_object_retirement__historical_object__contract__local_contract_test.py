# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/on-demand-content-pool-admission/spec.md#gwt-005.t4
"""退役路径只表达「退出可选集」，不能用来伪造溯源也不能下架合格对象。

绑定 `GWT-005.t4` 的唯一入池路径子句：池内每个对象都能被解释为「在可选集内」或
「已留回执退役」，不存在第三种既不可选又不可退役的状态。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

DATA_ROOT = Path(__file__).resolve().parents[3]
for _path in (DATA_ROOT / "scripts", DATA_ROOT / "tests"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from content.release.canonical.content_pool_record import (  # noqa: E402
    pool_payload_digest,
)
from content.release.canonical.object_transaction_contract import (  # noqa: E402
    ObjectTransactionError,
)
from content.release.canonical.pool_inspection import inspect_pool  # noqa: E402
from content.release.canonical.pool_object_retirement import (  # noqa: E402
    RETIREMENT_RECEIPT_RELATIVE_PATH,
    pool_object_retirement,
    retire_pool_object,
)
from core.control_types import PoolObjectRetirementReason  # noqa: E402
from core.io import write_json  # noqa: E402
from core.schema import assert_valid  # noqa: E402
from support.pool_object_retirement_fixture import (  # noqa: E402
    HISTORICAL_GENERATOR as _HISTORICAL_GENERATOR,
)
from support.pool_object_retirement_fixture import (  # noqa: E402
    pool_with_one_historical_object as _pool_with_one_historical_object,
)
from support.pool_object_retirement_fixture import post as _post  # noqa: E402

_RETIRED_AT = "2026-08-28T00:00:00Z"
_REASON = PoolObjectRetirementReason.HISTORICAL_GENERATOR_NOT_AGENT.value


def _retire(publish: Path, *, object_ref: str, **overrides: object) -> dict[str, object]:
    arguments: dict[str, object] = {
        "publish_root": publish,
        "object_type": "content",
        "object_ref": object_ref,
        "reason": _REASON,
        "retired_at": _RETIRED_AT,
        "apply": True,
    }
    arguments.update(overrides)
    return retire_pool_object(**arguments)  # type: ignore[arg-type]


def _code(exc: ObjectTransactionError) -> str:
    return str(exc).split(":", 1)[0]


def test_retirement_writes_only_the_receipt_and_never_rewrites_evidence(
    tmp_path: Path,
) -> None:
    """该路径不改写 generator，也不补写缺失的审核回执——只落一份独立回执。"""

    publish = tmp_path / "publish"
    root = _pool_with_one_historical_object(publish)
    manifest_bytes = (root / "manifest.json").read_bytes()
    attestation_bytes = (root / "attestation.json").read_bytes()
    payload_digest_before = pool_payload_digest(root)
    files_before = {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    }

    report = _retire(publish, object_ref="image/historical/1")

    assert report["result"] == "retired"
    assert report["receiptRef"] == (
        f"posts/image/historical/1/{RETIREMENT_RECEIPT_RELATIVE_PATH}"
    )
    files_after = {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    }
    assert files_after - files_before == {RETIREMENT_RECEIPT_RELATIVE_PATH}
    assert (root / "manifest.json").read_bytes() == manifest_bytes
    assert (root / "attestation.json").read_bytes() == attestation_bytes
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["generator"] == _HISTORICAL_GENERATOR
    assert pool_payload_digest(root) == payload_digest_before

    receipt = pool_object_retirement(root)
    assert receipt is not None
    assert_valid(
        receipt,
        "release",
        "pool_object_retirement_receipt",
        label="pool_object_retirement_receipt",
    )
    assert receipt["payloadDigest"] == payload_digest_before
    assert receipt["inadmissibility"] == {
        "gate": "quality",
        "code": "DATA.POOL.GENERATOR_PROVENANCE_INVALID",
    }


def test_retirement_of_an_admissible_object_is_refused(tmp_path: Path) -> None:
    """合格可选对象的退役请求判否，退役不能当成绕过审核的下架后门。"""

    publish = tmp_path / "publish"
    _pool_with_one_historical_object(publish)
    ready_root = publish / "posts/image/ready/1"

    with pytest.raises(ObjectTransactionError) as failure:
        _retire(publish, object_ref="image/ready/1")

    assert _code(failure.value) == "DATA.POOL.RETIREMENT_OBJECT_ADMISSIBLE"
    assert not (ready_root / RETIREMENT_RECEIPT_RELATIVE_PATH).exists()
    assert pool_object_retirement(ready_root) is None


def test_declared_reason_must_match_the_observed_typed_verdict(tmp_path: Path) -> None:
    """判据由 discovery 层给出：观测到另一条 typed 原因时判否且零写入。"""

    publish = tmp_path / "publish"
    _pool_with_one_historical_object(publish)
    drifted = _post(publish, carrier="image", work="no-entity")
    manifest_path = drifted / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["entityRefs"] = ["/entity/地点/景区/尚未追加的实体"]
    write_json(manifest_path, manifest)
    record_path = drifted / "_pool/versions/1.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["payloadDigest"] = record["canonicalObjectDigest"] = pool_payload_digest(
        drifted
    )
    write_json(record_path, record)

    with pytest.raises(ObjectTransactionError) as failure:
        _retire(publish, object_ref="image/no-entity/1")

    assert _code(failure.value) == "DATA.POOL.RETIREMENT_REASON_MISMATCH"
    assert not (drifted / RETIREMENT_RECEIPT_RELATIVE_PATH).exists()


def test_reason_outside_the_closed_set_and_object_type_mismatch_are_separate(
    tmp_path: Path,
) -> None:
    """闭集外 reason 与 reason/objectType 不配对是两个独立 typed 结论。"""

    publish = tmp_path / "publish"
    root = _pool_with_one_historical_object(publish)

    with pytest.raises(ObjectTransactionError) as reason_failure:
        _retire(publish, object_ref="image/historical/1", reason="operator_decision")
    assert _code(reason_failure.value) == "DATA.POOL.RETIREMENT_REASON_INVALID"

    with pytest.raises(ObjectTransactionError) as type_failure:
        _retire(publish, object_ref="image/historical/1", object_type="homepage")
    assert (
        _code(type_failure.value)
        == "DATA.POOL.RETIREMENT_REASON_OBJECT_TYPE_MISMATCH"
    )

    assert not (root / RETIREMENT_RECEIPT_RELATIVE_PATH).exists()


def test_receipt_is_create_once_and_drifted_input_conflicts(tmp_path: Path) -> None:
    """同参数重入返回既有回执；参数不同是 typed conflict 且零写入。"""

    publish = tmp_path / "publish"
    root = _pool_with_one_historical_object(publish)

    first = _retire(publish, object_ref="image/historical/1")
    frozen = (root / RETIREMENT_RECEIPT_RELATIVE_PATH).read_bytes()

    replay = _retire(publish, object_ref="image/historical/1")
    assert first["result"] == "retired"
    assert replay["result"] == "replayed"
    assert replay["receipt"] == first["receipt"]
    assert (root / RETIREMENT_RECEIPT_RELATIVE_PATH).read_bytes() == frozen

    with pytest.raises(ObjectTransactionError) as failure:
        _retire(
            publish,
            object_ref="image/historical/1",
            retired_at="2026-08-29T00:00:00Z",
        )

    assert _code(failure.value) == "DATA.POOL.RETIREMENT_RECEIPT_CONFLICT"
    assert (root / RETIREMENT_RECEIPT_RELATIVE_PATH).read_bytes() == frozen


def test_retirement_turns_quality_and_eligibility_passed_without_moving_counts(
    tmp_path: Path,
) -> None:
    """退役后 quality/eligibility 转 passed，supply 计数与准入结论逐项不变。"""

    publish = tmp_path / "publish"
    _pool_with_one_historical_object(publish)

    before = inspect_pool(
        publish_root=publish,
        include_issues=True,
        strict_delivery=True,
    )
    assert before["checks"]["quality"] == "failed"
    assert before["retired"] == {"objectCount": 0, "objects": []}
    assert [
        row["code"]
        for row in before["issues"]
        if row["ref"] == "posts/image/historical/1"
    ] == ["DATA.POOL.GENERATOR_PROVENANCE_INVALID"]

    _retire(publish, object_ref="image/historical/1")

    after = inspect_pool(
        publish_root=publish,
        include_issues=True,
        strict_delivery=True,
    )

    assert_valid(after, "release", "pool_inspection", label="pool_inspection")
    assert after["checks"]["quality"] == "passed"
    assert after["checks"]["eligibility"] == "passed"
    assert after["retired"] == {
        "objectCount": 1,
        "objects": [
            {
                "objectType": "content",
                "objectRef": "posts/image/historical/1",
                "reason": _REASON,
            }
        ],
    }
    assert after["supply"] == before["supply"]
    assert after["usageScope"] == before["usageScope"]
    assert after["environmentCapacity"] == before["environmentCapacity"]
    assert after["nextWave"] == before["nextWave"]
    # 退役只移除该对象的判否结论；同批其它对象的 issue 逐条不变。
    assert after["issues"] == [
        row for row in before["issues"] if row["ref"] != "posts/image/historical/1"
    ]


def test_broken_receipt_shapes_are_each_their_own_typed_conclusion(
    tmp_path: Path,
) -> None:
    """回执不可读、缺必需字段、reason 越界、字节漂移各自独立，不静默恢复也不默认退役。"""

    publish = tmp_path / "publish"
    root = _pool_with_one_historical_object(publish)
    _retire(publish, object_ref="image/historical/1")
    receipt_path = root / RETIREMENT_RECEIPT_RELATIVE_PATH
    frozen = json.loads(receipt_path.read_text(encoding="utf-8"))

    receipt_path.write_text("{not json", encoding="utf-8")
    assert _retirement_issue(publish) == "DATA.POOL.RETIREMENT_RECEIPT_UNREADABLE"

    missing_field = {key: value for key, value in frozen.items() if key != "objectId"}
    write_json(receipt_path, missing_field)
    assert _retirement_issue(publish) == "DATA.POOL.RETIREMENT_RECEIPT_INVALID"

    write_json(receipt_path, {**frozen, "reason": "operator_decision"})
    assert _retirement_issue(publish) == "DATA.POOL.RETIREMENT_REASON_INVALID"

    write_json(receipt_path, {**frozen, "payloadDigest": "sha256:" + "f" * 64})
    assert _retirement_issue(publish) == "DATA.POOL.RETIREMENT_PAYLOAD_DRIFT"


def _retirement_issue(publish: Path) -> str:
    """Return the single retirement conclusion the report attributes to the object."""

    report = inspect_pool(
        publish_root=publish,
        include_issues=True,
        strict_delivery=True,
    )
    assert report["retired"] == {"objectCount": 0, "objects": []}
    assert report["checks"]["eligibility"] == "failed"
    codes = [
        row["code"]
        for row in report["issues"]
        if row["ref"] == "posts/image/historical/1"
    ]
    assert len(codes) == 1
    return codes[0]
