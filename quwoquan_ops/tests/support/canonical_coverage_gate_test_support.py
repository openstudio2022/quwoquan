"""canonical coverage gate 契约测试的共享构造 helper。

`test_canonical_coverage*__gate__local_contract_test.py` 系列由 Python 1000 行
硬顶治理从单文件按场景拆分而来；被多个场景文件共用的构造 helper 逐字下沉到
本模块，构造语义与拆分前完全一致。
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate import verify_canonical_coverage as vcr


GATE_SOURCE_PATH = ROOT / "quwoquan_ops" / "gate" / "verify_canonical_coverage.py"
# 实现单轨落在 canonical_coverage/ 包内；源码文本断言必须同时覆盖薄入口与包内模块。
GATE_PACKAGE_ROOT = ROOT / "quwoquan_ops" / "gate" / "canonical_coverage"


def _identity(marker: str = "1") -> dict[str, str]:
    return {
        "headCommit": marker * 40,
        "headTree": marker * 40,
        "sourceTreeDigest": "sha256:" + marker * 64,
        "testTreeDigest": "sha256:" + marker * 64,
        "attributionDigest": "sha256:" + marker * 64,
        "configDigest": "sha256:" + marker * 64,
        "toolchainDigest": "sha256:" + marker * 64,
        "collectionScopeDigest": "sha256:" + marker * 64,
    }


def _receipt(target: str, marker: str = "1") -> dict:
    return {
        "schema": vcr.ARTIFACT_RECEIPT_SCHEMA,
        "ruleId": vcr.RULE_ID,
        "target": target,
        "artifactRef": vcr._display(vcr.artifact_path(target)),
        "artifactDigest": "sha256:" + marker * 64,
        **_identity(marker),
        "testsGreen": True,
    }


def _receipts_for_unit(unit: str) -> list[dict]:
    markers = "123456789abcdef"
    return [
        _receipt(target, markers[index % len(markers)])
        for index, target in enumerate(vcr.collection_targets([unit]))
    ]


def _gate_source_files() -> list[Path]:
    """门禁实现源码全集：薄入口 + canonical_coverage 包内全部模块。"""
    return [GATE_SOURCE_PATH, *sorted(GATE_PACKAGE_ROOT.glob("*.py"))]


_APP_UNIT = "app:probe_service/probe_context/probe_object"


def _attribution(files: dict[str, str]) -> SimpleNamespace:
    units: dict[str, set[str]] = {_APP_UNIT: set()}
    for library_relative, unit in files.items():
        units.setdefault(unit, set()).add(library_relative)
    return SimpleNamespace(unit_of=dict(files), files_by_unit=units)


def _label(entry: str) -> str:
    """取阻断消息的主语（`app:<domain>/<context>/<object>/<metric>` 等）。

    单元名本身含 `:`，不能按 `:` 切；消息统一用 `": "` 分隔主语与说明。
    """
    return entry.split(": ", 1)[0]



def _app_unit() -> str:
    return _APP_UNIT


def _cloud_unit() -> str:
    return next(
        unit
        for unit in vcr.discover_cloud_units()
        if not unit.startswith(vcr.CLOUD_CROSS_CUTTING_UNIT_PREFIX)
    )


def _block(percent_value: float, total: int = 10000) -> dict:
    covered = round(percent_value * total / 100.0)
    return {
        "covered": covered,
        "total": total,
        "percent": vcr.percent(covered, total),
    }


def _app_metrics(line: float, branch: float, file: float) -> dict:
    return {"line": _block(line), "branch": _block(branch), "file": _block(file)}


def _baseline_with(unit: str, metrics: dict, **policy_overrides) -> dict:
    policy = {
        "tolerance_percentage_points": 0.3,
        "tolerance_reason": "r",
        "improvement_slack_percentage_points": 3.0,
        "improvement_slack_reason": "r",
        "granularity_units": 2.0,
        "granularity_units_reason": "r",
    }
    policy.update(policy_overrides)
    receipts = _receipts_for_unit(unit)
    baseline = {
        "_governance": {"owner": "o", "reason": "r", "expires_when": "w"},
        "schema": vcr.BASELINE_SCHEMA,
        "ruleId": vcr.RULE_ID,
        "policy": policy,
        "receipts": {vcr.receipt_digest(receipt): receipt for receipt in receipts},
        "units": {unit: vcr.unit_entry(metrics, unit, receipts=receipts)},
    }
    return baseline
