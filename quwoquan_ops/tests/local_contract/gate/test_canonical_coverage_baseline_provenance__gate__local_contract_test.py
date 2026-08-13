# spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/branch-coverage-governance/spec.md#gwt-001
# spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/branch-coverage-governance/spec.md#gwt-002
"""`verify_canonical_coverage.py` baseline 写入与 receipt provenance 的本地契约。

由 test_canonical_coverage__gate__local_contract_test.py（Python 1000 行硬顶
治理）按场景拆出：--write-baseline 幂等且拒绝分区更新、artifact receipt 绑定
字节与八轴采集 identity、红测试/伪造 provenance/退休路径一律阻断。测试逐字
搬移。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate import object_path_map as opm
from quwoquan_ops.gate import verify_canonical_coverage as vcr
from quwoquan_ops.tests.support.canonical_coverage_gate_test_support import (
    _app_metrics,
    _app_unit,
    _baseline_with,
    _block,
    _cloud_unit,
    _identity,
    _receipt,
    _receipts_for_unit,
)


def _add_baseline_unit(baseline: dict, unit: str, metrics: dict) -> None:
    receipts = _receipts_for_unit(unit)
    baseline["units"][unit] = vcr.unit_entry(metrics, unit, receipts=receipts)
    for receipt in receipts:
        baseline["receipts"][vcr.receipt_digest(receipt)] = receipt


# ---------------------------------------------------------------------------
# --write-baseline
# ---------------------------------------------------------------------------


def test_write_baseline_records_measured_values_and_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline_path = tmp_path / "canonical_coverage_baseline.json"
    monkeypatch.setattr(vcr, "BASELINE_PATH", baseline_path)
    unit = _app_unit()
    monkeypatch.setattr(vcr, "discover_units", lambda: (unit,))
    baseline_path.write_text(
        json.dumps(
            _baseline_with(unit, _app_metrics(40.0, 20.0, 60.0)), ensure_ascii=False
        ),
        encoding="utf-8",
    )

    measured = {unit: _app_metrics(51.5, 33.25, 70.0)}
    unit_receipts = {unit: _receipts_for_unit(unit)}
    vcr.write_baseline(measured, units=[unit], unit_receipts=unit_receipts)
    first = baseline_path.read_text(encoding="utf-8")
    vcr.write_baseline(measured, units=[unit], unit_receipts=unit_receipts)
    assert baseline_path.read_text(encoding="utf-8") == first

    written = json.loads(first)
    assert written["ruleId"] == vcr.RULE_ID
    assert written["units"][unit]["metrics"]["line"]["percent"] == 51.5
    assert written["units"][unit]["metrics"]["branch"]["percent"] == 33.25
    # 收紧后再求值必须通过。
    assert vcr.diff(measured, written, [unit]) == []


def test_artifact_receipt_binds_bytes_and_current_collection_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(vcr, "COVERAGE_CACHE_DIR", tmp_path)
    target = vcr.APP_COLLECTION_TARGET
    identity = _identity()
    monkeypatch.setattr(
        vcr, "current_collection_identity", lambda _target: dict(identity)
    )
    artifact = vcr.artifact_path(target)
    artifact.write_text("SF:lib/a.dart\nLF:1\nLH:1\nend_of_record\n", encoding="utf-8")
    vcr._write_artifact_receipt(target, tests_green=True)

    receipt = vcr.validate_artifact_receipt(target)
    assert receipt["testsGreen"] is True
    assert receipt["ruleId"] == vcr.RULE_ID

    artifact.write_text("tampered\n", encoding="utf-8")
    with pytest.raises(vcr.CoverageError, match="已陈旧"):
        vcr.validate_artifact_receipt(target)


def test_collection_identity_has_every_required_provenance_axis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.dart"
    tests = tmp_path / "source_test.dart"
    attribution = tmp_path / "attribution.json"
    config = tmp_path / "pubspec.yaml"
    for path in (source, tests, attribution, config):
        path.write_text(path.name + "\n", encoding="utf-8")
    monkeypatch.setattr(vcr, "ROOT", tmp_path)
    monkeypatch.setattr(vcr, "_app_collection_inputs", lambda: ([source], [tests]))
    monkeypatch.setattr(vcr, "_attribution_inputs", lambda: [attribution])
    monkeypatch.setattr(vcr, "_collection_config_inputs", lambda _target: [config])
    monkeypatch.setattr(
        vcr,
        "_git_head_identity",
        lambda: {"headCommit": "1" * 40, "headTree": "2" * 40},
    )
    monkeypatch.setattr(vcr, "_toolchain_digest", lambda _target: "sha256:" + "3" * 64)
    monkeypatch.setattr(
        vcr, "_collection_scope_digest", lambda _target: "sha256:" + "4" * 64
    )

    identity = vcr.current_collection_identity(vcr.APP_COLLECTION_TARGET)

    assert set(identity) == {
        "headCommit",
        "headTree",
        "sourceTreeDigest",
        "testTreeDigest",
        "attributionDigest",
        "configDigest",
        "toolchainDigest",
        "collectionScopeDigest",
    }
    assert identity["headCommit"] == "1" * 40
    assert identity["headTree"] == "2" * 40


def test_attribution_digest_includes_page_object_contract_and_detects_its_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = tmp_path / "contract_graph.json"
    page_contract = tmp_path / "page_object_contract.yaml"
    object_path_map_source = tmp_path / "object_path_map.py"
    architecture_source = tmp_path / "verify_app_architecture.py"
    for path, content in (
        (graph, "{}\n"),
        (page_contract, "pages: []\n"),
        (object_path_map_source, "RULE_ID = 'probe'\n"),
        (architecture_source, "RULE_ID = 'probe'\n"),
    ):
        path.write_text(content, encoding="utf-8")

    monkeypatch.setattr(vcr, "ROOT", tmp_path)
    monkeypatch.setattr(opm, "CONTRACT_GRAPH_PATH", Path("contract_graph.json"))
    monkeypatch.setattr(
        opm, "PAGE_OBJECT_CONTRACT_PATH", Path("page_object_contract.yaml")
    )
    monkeypatch.setattr(opm, "__file__", str(object_path_map_source))
    monkeypatch.setattr(vcr.vaa, "__file__", str(architecture_source))

    inputs = vcr._attribution_inputs()
    assert page_contract in inputs
    before = vcr._tree_digest(inputs, label="coverage attribution")

    page_contract.write_text("pages:\n  - page_id: probe\n", encoding="utf-8")
    after = vcr._tree_digest(vcr._attribution_inputs(), label="coverage attribution")

    assert after != before


def test_artifact_without_receipt_or_with_input_drift_is_stale(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(vcr, "COVERAGE_CACHE_DIR", tmp_path)
    target = vcr.APP_COLLECTION_TARGET
    identity = _identity()
    monkeypatch.setattr(
        vcr, "current_collection_identity", lambda _target: dict(identity)
    )
    artifact = vcr.artifact_path(target)
    artifact.write_text("SF:lib/a.dart\nLF:1\nLH:1\nend_of_record\n", encoding="utf-8")

    with pytest.raises(vcr.CoverageError, match="缺少 provenance receipt"):
        vcr.validate_artifact_receipt(target)

    vcr._write_artifact_receipt(target, tests_green=True)
    identity["testTreeDigest"] = "sha256:" + "9" * 64
    with pytest.raises(vcr.CoverageError, match="testTreeDigest"):
        vcr.validate_artifact_receipt(target)
    identity["testTreeDigest"] = "sha256:" + "1" * 64
    identity["sourceTreeDigest"] = "sha256:" + "9" * 64
    with pytest.raises(vcr.CoverageError, match="sourceTreeDigest"):
        vcr.validate_artifact_receipt(target)


@pytest.mark.parametrize(
    "field",
    (
        "headCommit",
        "headTree",
        "sourceTreeDigest",
        "testTreeDigest",
        "attributionDigest",
        "configDigest",
        "toolchainDigest",
        "collectionScopeDigest",
    ),
)
def test_each_receipt_identity_drift_blocks_reuse(
    field: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HEAD、配置、工具链与五类内容 identity 任一漂移都必须重采。"""
    monkeypatch.setattr(vcr, "COVERAGE_CACHE_DIR", tmp_path)
    target = vcr.APP_COLLECTION_TARGET
    identity = _identity()
    monkeypatch.setattr(vcr, "current_collection_identity", lambda _target: identity)
    vcr.artifact_path(target).write_text(
        "SF:lib/a.dart\nLF:1\nLH:1\nend_of_record\n", encoding="utf-8"
    )
    vcr._write_artifact_receipt(target, tests_green=True)

    identity[field] = (
        "9" * 40 if field in {"headCommit", "headTree"} else "sha256:" + "9" * 64
    )
    with pytest.raises(vcr.CoverageError, match=field):
        vcr.validate_artifact_receipt(target)


def test_old_receipt_without_current_rule_id_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(vcr, "COVERAGE_CACHE_DIR", tmp_path)
    target = vcr.APP_COLLECTION_TARGET
    identity = _identity()
    monkeypatch.setattr(
        vcr, "current_collection_identity", lambda _target: dict(identity)
    )
    vcr.artifact_path(target).write_text(
        "SF:lib/a.dart\nLF:1\nLH:1\nend_of_record\n", encoding="utf-8"
    )
    receipt = vcr._write_artifact_receipt(target, tests_green=True)
    receipt.pop("ruleId")
    vcr.artifact_receipt_path(target).write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(vcr.CoverageError, match="fields mismatch"):
        vcr.validate_artifact_receipt(target)


def test_red_artifact_receipt_cannot_be_reused_for_any_measurement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(vcr, "COVERAGE_CACHE_DIR", tmp_path)
    target = vcr.APP_COLLECTION_TARGET
    identity = _identity()
    monkeypatch.setattr(
        vcr, "current_collection_identity", lambda _target: dict(identity)
    )
    vcr.artifact_path(target).write_text(
        "SF:lib/a.dart\nLF:1\nLH:1\nend_of_record\n", encoding="utf-8"
    )
    vcr._write_artifact_receipt(target, tests_green=False)

    with pytest.raises(vcr.CoverageError, match="未全绿"):
        vcr.validate_artifact_receipt(target)


def test_collection_input_drift_discards_the_untrustworthy_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(vcr, "COVERAGE_CACHE_DIR", tmp_path)
    target = vcr.APP_COLLECTION_TARGET
    before = _identity()
    after = dict(before, sourceTreeDigest="sha256:" + "9" * 64)
    identities = iter((before, after))
    monkeypatch.setattr(
        vcr, "current_collection_identity", lambda _target: next(identities)
    )
    monkeypatch.setattr(
        vcr,
        "collect_app",
        lambda destination, **_shard_options: destination.write_text(
            "SF:lib/a.dart\nLF:1\nLH:1\nend_of_record\n", encoding="utf-8"
        ),
    )

    with pytest.raises(vcr.CoverageError, match="采集期间.*发生漂移"):
        vcr.collect(target)
    assert not vcr.artifact_path(target).exists()
    assert not vcr.artifact_receipt_path(target).exists()


def test_write_baseline_rejects_partial_update_and_rewrites_all_units_together(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline_path = tmp_path / "canonical_coverage_baseline.json"
    monkeypatch.setattr(vcr, "BASELINE_PATH", baseline_path)
    app, cloud = _app_unit(), _cloud_unit()
    monkeypatch.setattr(vcr, "discover_units", lambda: (app, cloud))
    original = _baseline_with(app, _app_metrics(40.0, 20.0, 60.0))
    _add_baseline_unit(original, cloud, {"statement": _block(13.0)})
    baseline_path.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(vcr.CoverageError, match="禁止 scope/unit 分区更新"):
        vcr.write_baseline(
            {app: _app_metrics(44.0, 24.0, 64.0)},
            units=[app],
            unit_receipts={app: _receipts_for_unit(app)},
        )

    vcr.write_baseline(
        {
            app: _app_metrics(44.0, 24.0, 64.0),
            cloud: {"statement": _block(23.0)},
        },
        units=[app, cloud],
        unit_receipts={
            app: _receipts_for_unit(app),
            cloud: _receipts_for_unit(cloud),
        },
    )

    written = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert written["_governance"] == vcr.CANONICAL_BASELINE_GOVERNANCE
    assert written["policy"] == vcr.CANONICAL_POLICY
    assert written["units"][app]["metrics"]["line"]["percent"] == 44.0
    assert written["units"][cloud]["metrics"]["statement"]["percent"] == 23.0


def test_baseline_schema_rejects_false_green_test_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline_path = tmp_path / "canonical_coverage_baseline.json"
    monkeypatch.setattr(vcr, "BASELINE_PATH", baseline_path)
    unit = _cloud_unit()
    baseline = _baseline_with(unit, {"statement": _block(13.0)})
    baseline["units"][unit]["measuredFromGreenTests"] = False
    baseline_path.write_text(json.dumps(baseline, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="measuredFromGreenTests 必须是 true"):
        vcr.load_baseline()


def test_retired_baseline_path_is_rejected_without_alias_or_dual_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical = tmp_path / "canonical_coverage_baseline.json"
    retired = tmp_path / "coverage_baseline.json"
    monkeypatch.setattr(vcr, "BASELINE_PATH", canonical)
    monkeypatch.setattr(vcr, "RETIRED_BASELINE_PATH", retired)
    unit = _app_unit()
    monkeypatch.setattr(vcr, "discover_units", lambda: (unit,))
    retired.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="旧 coverage baseline 已硬切退休"):
        vcr.load_baseline()
    with pytest.raises(vcr.CoverageError, match="禁止 alias、fallback、dual-read"):
        vcr.write_baseline(
            {unit: _app_metrics(40.0, 20.0, 60.0)},
            units=[unit],
            unit_receipts={unit: _receipts_for_unit(unit)},
        )


@pytest.mark.parametrize(
    ("statement", "message"),
    (
        (
            {"status": vcr.METRIC_STATUS_UNMEASURED, "reason": "没有测试触达"},
            "不得把 unmeasured 写入 baseline",
        ),
        ({"covered": 0, "total": 7, "percent": 0.0}, "非自洽实测值"),
    ),
)
def test_unmeasured_or_zero_statement_cannot_build_or_pass_a_baseline(
    statement: dict,
    message: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未采集与 0/N 都是阻断事实，不能被绿 receipt 包装成 Cloud baseline。"""
    baseline_path = tmp_path / "canonical_coverage_baseline.json"
    monkeypatch.setattr(vcr, "BASELINE_PATH", baseline_path)
    unit = _cloud_unit()
    receipts = _receipts_for_unit(unit)

    with pytest.raises(vcr.CoverageError, match=message):
        vcr.unit_entry({"statement": statement}, unit, receipts=receipts)

    baseline = _baseline_with(unit, {"statement": _block(13.0)})
    baseline["units"][unit]["metrics"]["statement"] = statement
    failures = vcr.diff({unit: {"statement": statement}}, baseline, [unit])
    assert failures, "非法 unmeasured/0 statement 不能在 diff 阶段假绿"
    baseline_path.write_text(json.dumps(baseline, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        vcr.load_baseline()


@pytest.mark.parametrize("mode", ("missing", "forged_digest", "wrong_target"))
def test_baseline_entry_rejects_missing_or_forged_receipt_provenance(
    mode: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline_path = tmp_path / "canonical_coverage_baseline.json"
    monkeypatch.setattr(vcr, "BASELINE_PATH", baseline_path)
    unit = _app_unit()
    baseline = _baseline_with(unit, _app_metrics(40.0, 20.0, 60.0))
    digest = baseline["units"][unit]["receiptDigests"][0]

    if mode == "missing":
        baseline["receipts"].pop(digest)
    elif mode == "forged_digest":
        baseline["receipts"][digest]["artifactDigest"] = "sha256:" + "9" * 64
    else:
        wrong = _receipt("quwoquan_service/services/probe-service", "9")
        wrong_digest = vcr.receipt_digest(wrong)
        baseline["receipts"] = {wrong_digest: wrong}
        baseline["units"][unit]["receiptDigests"] = [wrong_digest]
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")

    with pytest.raises(ValueError, match="receipt|provenance|绑定伪造"):
        vcr.load_baseline()


def test_write_baseline_drops_units_that_no_longer_exist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline_path = tmp_path / "canonical_coverage_baseline.json"
    monkeypatch.setattr(vcr, "BASELINE_PATH", baseline_path)
    unit = _app_unit()
    monkeypatch.setattr(vcr, "discover_units", lambda: (unit,))
    original = _baseline_with(unit, _app_metrics(40.0, 20.0, 60.0))
    retired = "app:retired/context/object"
    original["units"][retired] = original["units"][unit]
    baseline_path.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")

    written = vcr.write_baseline(
        {unit: _app_metrics(40.0, 20.0, 60.0)},
        units=[unit],
        unit_receipts={unit: _receipts_for_unit(unit)},
        known_units=[unit],
    )

    assert retired not in written["units"]
