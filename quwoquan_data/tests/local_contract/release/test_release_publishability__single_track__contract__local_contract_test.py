"""「可发布」谓词单轨：唯一定义点判定 + 消费点不得复述 phase 规则。"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "quwoquan_data" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.release.canonical.supply_chain_drill_support import (  # noqa: E402
    SupplyChainDrillError,
    readiness_phase,
)
from verify.release_publishability import (  # noqa: E402
    READINESS_PHASES,
    evaluate_release_readiness_receipt,
    main,
    phase_lifecycle_alignment_issue,
    readiness_phase_issue,
)

# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001


def _receipt(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "readinessPhase": "commercial",
        "releaseClass": "commercial",
        "productLifecycleState": "commercial",
        "passed": True,
    }
    base.update(overrides)
    return base


def test_phase_closed_set_matches_schema_enum() -> None:
    import json

    schema = json.loads(
        (
            ROOT
            / "quwoquan_data/schema/release/environment_release_readiness.schema.json"
        ).read_text(encoding="utf-8")
    )
    assert READINESS_PHASES == frozenset(
        schema["properties"]["readinessPhase"]["enum"]
    )


def test_phase_issue_rejects_unknown_and_accepts_closed_set() -> None:
    for phase in sorted(READINESS_PHASES):
        assert readiness_phase_issue(phase) is None
    assert readiness_phase_issue("import") is not None
    assert readiness_phase_issue("") is not None


def test_alignment_binds_research_and_commercial_but_not_consumer() -> None:
    assert (
        phase_lifecycle_alignment_issue("research", "research", "research") is None
    )
    assert (
        phase_lifecycle_alignment_issue("commercial", "research", "research")
        is not None
    )
    # consumer 跟随 release header，不强制对齐——schema allOf 无 consumer 分支。
    assert (
        phase_lifecycle_alignment_issue("consumer", "commercial", "commercial")
        is None
    )


def test_verdict_publishable_for_aligned_passed_commercial_receipt() -> None:
    verdict = evaluate_release_readiness_receipt(_receipt())
    assert verdict.publishable is True
    assert verdict.phase == "commercial"
    assert verdict.issues == ()


def test_verdict_blocks_research_without_isolation_evidence() -> None:
    verdict = evaluate_release_readiness_receipt(
        _receipt(
            readinessPhase="research",
            releaseClass="research",
            productLifecycleState="research",
        )
    )
    assert verdict.publishable is False
    assert any("researchIsolationVerificationRef" in issue for issue in verdict.issues)


def test_verdict_blocks_unpassed_or_misaligned_or_unknown_phase() -> None:
    assert evaluate_release_readiness_receipt(_receipt(passed=False)).publishable is False
    assert (
        evaluate_release_readiness_receipt(
            _receipt(releaseClass="research")
        ).publishable
        is False
    )
    assert (
        evaluate_release_readiness_receipt(
            _receipt(readinessPhase="import")
        ).publishable
        is False
    )


def test_cli_fails_closed_on_unreadable_and_non_contract_receipt(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--receipt", str(tmp_path / "absent.json")]) == 1
    assert "unreadable receipt" in capsys.readouterr().out

    partial = tmp_path / "partial.json"
    partial.write_text('{"readinessPhase": "commercial"}', encoding="utf-8")
    assert main(["--receipt", str(partial)]) == 1
    assert "schema violation" in capsys.readouterr().out


def test_drill_support_fails_closed_on_unknown_phase(tmp_path: Path) -> None:
    receipt = tmp_path / "release-readiness.json"
    receipt.write_text('{"readinessPhase": "importing"}', encoding="utf-8")
    with pytest.raises(SupplyChainDrillError, match="readinessPhase"):
        readiness_phase(receipt)
    receipt.write_text('{"readinessPhase": "consumer"}', encoding="utf-8")
    assert readiness_phase(receipt) == "consumer"


def _phase_literal_lines(source: str) -> list[int]:
    """AST 级扫描：集合/元组/列表字面量恰为三相位闭集，或 dict 键恰为三相位。

    比字符串匹配更强：换行、换序、单双引号、注释混排均无法绕过。
    """
    phase_set = {"research", "consumer", "commercial"}
    hits: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.Set, ast.Tuple, ast.List)):
            values = {
                element.value
                for element in node.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            }
            if values == phase_set:
                hits.append(node.lineno)
        elif isinstance(node, ast.Dict):
            keys = {
                key.value
                for key in node.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
            if keys == phase_set:
                hits.append(node.lineno)
    return hits


def test_consumers_do_not_restate_phase_closed_set() -> None:
    """单轨防回潮：谓词之外不得再出现 phase 闭集或对齐映射的第二份实现。

    扫描面 = quwoquan_data/scripts 全部 .py（谓词模块自身除外），
    新消费方自动进入扫描面，不依赖人工维护清单。
    """
    predicate = SCRIPTS / "verify" / "release_publishability.py"
    offenders: list[str] = []
    for path in sorted(SCRIPTS.rglob("*.py")):
        if path == predicate:
            continue
        lines = _phase_literal_lines(path.read_text(encoding="utf-8"))
        offenders.extend(
            f"{path.relative_to(ROOT)}:{line}" for line in lines
        )
    assert not offenders, (
        "readinessPhase 闭集/对齐映射只允许定义在 release_publishability：\n"
        + "\n".join(offenders)
    )
    assert _phase_literal_lines(predicate.read_text(encoding="utf-8")), (
        "谓词模块必须仍持有唯一闭集定义（扫描器自校验）"
    )
