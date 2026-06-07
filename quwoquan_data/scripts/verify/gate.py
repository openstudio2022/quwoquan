"""Exit gate for verify command（纯决策，逻辑在 _common.post_verify）。"""
from __future__ import annotations

from _common.evidence_contract import quality_payload_contract_issues
from _common.post_verify import verify_scope
from _common.stage_reports import iter_stage_envelopes


def gate_verify(*, task: str | None = None, batch: str | None = None, release: str | None = None, scope: str = "current"):
    """返回 (roots, issues)。issues 非空即门禁失败。"""
    roots, issues = verify_scope(task=task, batch=batch, release=release, scope=scope)
    if task and batch:
        issues.extend(_verify_runtime_stage_payloads(task, batch))
    return roots, issues


def _verify_runtime_stage_payloads(task: str, batch: str) -> list[str]:
    issues: list[str] = []
    issues.extend(_verify_quality_analysis(task, batch))
    # 目录与资产证据链静态门（对象同构 + 来源内聚 + 相对路径 + 文风 + 受控来源类目）。
    from verify.verify_directory_evidence_chain import scan_batch

    issues.extend(scan_batch(task, batch))
    return issues


def _verify_quality_analysis(task: str, batch: str) -> list[str]:
    issues: list[str] = []
    for ref, envelope in iter_stage_envelopes(task, batch, "produce", "quality_analysis"):
        payload = envelope.get("payload") or {}
        for issue in quality_payload_contract_issues(payload):
            issues.append(f"{ref}.json: {issue}")
    return issues
